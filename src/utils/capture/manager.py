# utils/capture/manager.py
#
# 16.11.2026 (2.0): מנהל ההקלטה של השרת - ההגדרות (data/recording_settings.json), המנוע הפעיל (ffmpeg / OBS), מקשי הקיצור,
# ולאן הולך כל קובץ:
#   - קליפ replay (שמירת X השניות האחרונות) -> Import של Rocket, ומשם לשרשור האוטומטי (on_clip) - כמו replay של OBS עד היום.
#   - הקלטה מלאה -> workspace/recordings (חומר גלם; חיתוך לשורטס - "קליפ ארוך לשורטס"). לא נכנסת לשרשור.
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from utils.capture import devices as dv
from utils.capture import loopback
from utils.capture.command import CaptureSpec
from utils.capture.engine import CaptureError, FfmpegEngine, ObsEngine
from utils.shared.atomic_write import atomic_write_json

DEFAULTS: Dict[str, Any] = {
    "engine": "ffmpeg",            # ffmpeg / obs
    "source": "screen",            # screen / device
    "screen_index": 0,
    "fps": 60,
    "console": "",                 # ps5 / ps4 / xbox_series / xbox_one / switch2 / switch / "" (כרטיס בלי פרופיל)
    "device_video": "",
    "device_audio": "",
    "game_audio": True,            # במחשב: WASAPI loopback
    "mic": "",
    "facecam": "",
    "codec": "hevc",               # h264 / hevc / av1 - hevc/av1 במקודד של הכרטיס (encoders.py)
    "quality": 22,
    "replay_seconds": 60,
    "replay_max_gb": 8,
    "hotkey_save_replay": "ctrl+alt+s",
    "hotkey_toggle_record": "ctrl+alt+r",
}
CHOICES = {"engine": ("ffmpeg", "obs"), "source": ("screen", "device"), "codec": ("h264", "hevc", "av1"),
           "console": ("",) + tuple(p.id for p in dv.CONSOLE_PROFILES)}
LIMITS = {"fps": (10, 240), "quality": (10, 40), "replay_seconds": (10, 600), "replay_max_gb": (1, 100), "screen_index": (0, 8)}


def clean_settings(raw: Any) -> Dict[str, Any]:
    data = dict(DEFAULTS)
    if not isinstance(raw, dict):
        return data
    for key, default in DEFAULTS.items():
        value = raw.get(key, default)
        if key in CHOICES:
            data[key] = value if value in CHOICES[key] else default
        elif key in LIMITS:
            try:
                low, high = LIMITS[key]
                data[key] = max(low, min(high, int(value)))
            except (TypeError, ValueError):
                data[key] = default
        elif isinstance(default, bool):
            data[key] = bool(value)
        else:
            data[key] = str(value or "").strip()[:200]
    return data


def video_args_for(codec: str, quality: int, backend_args: Optional[Callable[[str, int], List[str]]] = None) -> List[str]:
    """h264 - libx264 מהיר (הקלטה בזמן אמת); hevc/av1 - המקודד של הכרטיס דרך backend_args (encoders.py), או NVENC."""
    if codec == "h264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(quality)]
    if backend_args is not None:
        return backend_args(codec, quality)
    return ["-c:v", f"{codec}_nvenc", "-preset", "p4", "-cq", str(quality)]


def build_spec(settings: Dict[str, Any], ffmpeg_exe: str, video_args: List[str], creationflags: int = 0,
               list_modes: Callable[..., List[dv.Mode]] = dv.list_modes,
               audio_format: Callable[[], Optional[tuple]] = loopback.default_format) -> CaptureSpec:
    spec = CaptureSpec(source=settings["source"], fps=settings["fps"], screen_index=settings["screen_index"],
                       mic=settings["mic"], facecam=settings["facecam"], video_args=video_args)
    if settings["source"] == "device":
        if not settings["device_video"]:
            raise CaptureError("לא נבחר כרטיס לכידה")
        spec.device_video, spec.device_audio = settings["device_video"], settings["device_audio"]
        profile = dv.console_profile(settings["console"])
        if profile:
            mode = dv.pick_mode(list_modes(ffmpeg_exe, settings["device_video"], creationflags), profile.width, profile.height, profile.fps)
            if mode:
                spec.device_size, spec.device_codec = f"{mode.width}x{mode.height}", mode.codec
                spec.fps = int(min(profile.fps, mode.max_fps))
    elif settings["game_audio"]:
        fmt = audio_format()
        if fmt:
            spec.game_audio_port = loopback.free_port()
            spec.game_audio_rate, spec.game_audio_channels = fmt
    return spec


class RecorderManager:
    def __init__(self, settings_path: str, ffmpeg_exe: str, workspace_dir: str, import_dir: Callable[[], str],
                 on_clip: Optional[Callable[[str, str], None]] = None, creationflags: int = 0,
                 backend_args: Optional[Callable[[str, int], List[str]]] = None,
                 obs_credentials: Callable[[], tuple] = lambda: ("ws://localhost:4455", ""),
                 hotkeys: Any = None):
        self.settings_path = settings_path
        self.ffmpeg_exe = ffmpeg_exe
        self.workspace_dir = workspace_dir
        self.import_dir = import_dir
        self.on_clip = on_clip
        self.creationflags = creationflags
        self.backend_args = backend_args
        self.obs_credentials = obs_credentials
        self._hotkeys = hotkeys
        self._hotkey_handles: List[Any] = []
        self._engine: Any = None
        self._lock = threading.RLock()
        self.last_saved: Optional[str] = None
        self._import: Dict[str, Any] = {}

    # --- הגדרות ---
    def settings(self) -> Dict[str, Any]:
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                return clean_settings(json.load(f))
        except (OSError, ValueError):
            return dict(DEFAULTS)

    def save_settings(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        if self.busy():
            raise CaptureError("עצור את ההקלטה וה-replay לפני שינוי ההגדרות")
        data = clean_settings({**self.settings(), **(raw or {})})
        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        atomic_write_json(self.settings_path, data, indent=2, ensure_ascii=False)
        self._drop_engine()
        return data

    # --- מנוע ---
    def _clip_saved(self, path: str, source: str) -> None:
        self.last_saved = path
        if self.on_clip:
            self.on_clip(path, source)

    def engine(self):
        with self._lock:
            settings = self.settings()
            if self._engine is not None and self._engine.name == settings["engine"]:
                return self._engine
            self._drop_engine()
            if settings["engine"] == "obs":
                url, password = self.obs_credentials()
                self._engine = ObsEngine(url, password, on_clip=self._clip_saved)
            else:
                self._engine = FfmpegEngine(self.ffmpeg_exe, os.path.join(self.workspace_dir, ".cache"), self.import_dir,
                                            on_clip=self._clip_saved, creationflags=self.creationflags,
                                            loopback_factory=loopback.LoopbackSender)
            return self._engine

    def _drop_engine(self) -> None:
        if self._engine is not None:
            try:
                self._engine.shutdown()
            except Exception:
                pass
            self._engine = None

    def busy(self) -> bool:
        if self._engine is None:
            return False
        status = self._engine.status()
        return bool(status.get("recording") or status.get("replay"))

    def _spec(self) -> CaptureSpec:
        settings = self.settings()
        args = video_args_for(settings["codec"], settings["quality"], self.backend_args)
        return build_spec(settings, self.ffmpeg_exe, args, self.creationflags)

    # --- פעולות ---
    def start_record(self) -> Dict[str, Any]:
        engine = self.engine()
        if isinstance(engine, FfmpegEngine):
            folder = os.path.join(self.workspace_dir, "recordings")
            engine.output_dir = lambda: folder   # הקלטה מלאה - חומר גלם, לא Import
            engine.on_clip = lambda path, source: setattr(self, "last_saved", path)
            engine.start_record(self._spec(), time.strftime("recording_%Y%m%d_%H%M%S"))
        else:
            engine.start_record()
        if not self._hotkey_handles:
            self._register_hotkeys(self.settings())
        return self.status()

    def stop_record(self) -> Dict[str, Any]:
        engine = self.engine()
        path = engine.stop_record()
        if isinstance(engine, FfmpegEngine):
            engine.output_dir, engine.on_clip = self.import_dir, self._clip_saved
        if path:
            self.last_saved = path
        if not engine.status().get("replay"):
            self._unregister_hotkeys()
        return self.status()

    def toggle_record(self) -> Dict[str, Any]:
        return self.stop_record() if self.engine().status().get("recording") else self.start_record()

    def start_replay(self) -> Dict[str, Any]:
        settings = self.settings()
        engine = self.engine()
        if isinstance(engine, FfmpegEngine):
            engine.start_replay(self._spec(), settings["replay_seconds"], settings["replay_max_gb"] * 1024 ** 3)
        else:
            engine.start_replay()
        self._register_hotkeys(settings)
        return self.status()

    def save_replay(self, seconds: Optional[int] = None) -> Dict[str, Any]:
        settings = self.settings()
        engine = self.engine()
        engine.save_replay(int(seconds or settings["replay_seconds"]), time.strftime("replay_%Y%m%d_%H%M%S"))
        return self.status()

    def stop_replay(self) -> Dict[str, Any]:
        self._unregister_hotkeys()
        self.engine().stop_replay()
        return self.status()

    def scenes(self) -> Dict[str, Any]:
        engine = self.engine()
        if not isinstance(engine, ObsEngine):
            raise CaptureError("סצנות זמינות רק עם OBS")
        return engine.scenes()

    def switch_scene(self, scene: str) -> None:
        engine = self.engine()
        if not isinstance(engine, ObsEngine):
            raise CaptureError("סצנות זמינות רק עם OBS")
        engine.switch_scene(scene)

    # --- ייבוא מתוכנות הקלטה וקונסולות (import_presets.py, importer.py) ---
    def import_sources(self, presets_fn: Optional[Callable[[], List[Any]]] = None) -> List[Dict[str, Any]]:
        from utils.capture import import_presets, importer
        manifest = importer.load_manifest(self._manifest_path())
        found = import_presets.available((presets_fn or import_presets.presets)())
        return [{"id": p.id, "label": p.label, "path": p.path, "console": p.console,
                 "new": len(importer.find_new(p, manifest))} for p in found]

    def _manifest_path(self) -> str:
        return os.path.join(self.workspace_dir, ".cache", "import_manifest.json")

    def start_import(self, preset_id: str, presets_fn: Optional[Callable[[], List[Any]]] = None) -> Dict[str, Any]:
        from utils.capture import import_presets, importer
        if self._import.get("running"):
            raise CaptureError("ייבוא כבר רץ")
        preset = next((p for p in (presets_fn or import_presets.presets)() if p.id == preset_id), None)
        if preset is None or not os.path.isdir(preset.path):
            raise CaptureError("המקור לא נמצא (הכונן לא מחובר?)")
        items = importer.find_new(preset, importer.load_manifest(self._manifest_path()))
        self._import = {"running": True, "label": preset.label, "done": 0, "total": len(items), "last": None, "error": None}

        def progress(done, total, path):
            self._import.update(done=done, total=total, last=path)

        def run():
            try:
                importer.import_items(items, self.import_dir(), self._manifest_path(), self.ffmpeg_exe, self.creationflags, progress)
            except Exception as e:
                self._import["error"] = str(e)
            finally:
                self._import["running"] = False

        threading.Thread(target=run, name="clipforge-import", daemon=True).start()
        return self.status()

    def status(self) -> Dict[str, Any]:
        settings = self.settings()
        base = self._engine.status() if self._engine is not None else {
            "engine": settings["engine"], "recording": False, "replay": False, "replay_buffered_seconds": 0, "error": None}
        return {**base, "last_saved": self.last_saved, "hotkeys": bool(self._hotkey_handles), "import": dict(self._import)}

    # --- מקשי קיצור ---
    def _register_hotkeys(self, settings: Dict[str, Any]) -> None:
        self._unregister_hotkeys()
        keyboard = self._hotkeys
        if keyboard is None:
            try:
                import keyboard  # type: ignore[no-redef]
            except Exception:
                return

        def safe(action):
            def run():
                try:
                    action()
                except Exception as e:
                    if self._engine is not None:
                        self._engine.last_error = str(e)
            return run

        for key, action in ((settings["hotkey_save_replay"], lambda: self.save_replay()),
                            (settings["hotkey_toggle_record"], self.toggle_record)):
            if key:
                try:
                    self._hotkey_handles.append((keyboard, keyboard.add_hotkey(key, safe(action))))
                except Exception:
                    pass

    def _unregister_hotkeys(self) -> None:
        for keyboard, handle in self._hotkey_handles:
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass
        self._hotkey_handles = []

    def shutdown(self) -> None:
        self._unregister_hotkeys()
        self._drop_engine()
