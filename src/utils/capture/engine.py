# utils/capture/engine.py
#
# 16.11.2026 (2.0): שני מנועי הקלטה מאחורי ממשק אחד - המסך בממשק לא יודע מי מהם עובד:
#   - FfmpegEngine: ההקלטה המובנית (command.py) - מסך / כרטיס לכידה, replay buffer (ring_buffer.py), שמע המשחק (loopback.py).
#   - ObsEngine: שליטה ב-OBS דרך obs-websocket v5 (simpleobsws): הקלטה, replay buffer, סצנות. OBS שומר את הקובץ בעצמו.
# כל שמירה (סוף הקלטה / replay) קוראת ל-on_clip(path, source) - השרת מעביר את זה לשרשור האוטומטי, כמו מאזין ה-OBS.
#
# 17.11.2026 (2.0.1), מהבדיקה המעמיקה:
#   - ffmpeg מת יחד עם השרת (utils/shared/child_guard.py), ובעלייה נסגר מה שנשאר מריצה קודמת ונמחק המטמון שלה (orphans.py).
#   - שמע המשחק: ההקלטה מתחילה רק אחרי שהשולח התחבר. אם הוא נכשל (התקן שמע שלא נפתח) - ההקלטה מתחילה בלי שמע המשחק, עם
#     הודעה, במקום ffmpeg שמחכה לנצח בזמן שהמסך אומר "מקליט".
#   - ddagrab שלא עלה (משחק במסך מלא בלעדי, מחשב ישן) - ניסיון שני עם gdigrab. עד עכשיו הנפילה הזו הייתה קיימת רק בקוד.
#   - הקלטה מלאה נשמרת ב-record_dir ומדווחת כ-"recording"; קליפ replay תמיד ב-output_dir, גם בזמן הקלטה מלאה.
#   - שם קובץ תפוס מקבל _2 (שתי שמירות באותה שנייה לא דורסות זו את זו); remux שנתקע משאיר את ה-MKV ולא מפיל את העצירה;
#     replay שמת משאיר את התיקייה שלו נקייה בהפעלה הבאה.
#   - OBS: חיבור אחד גם כששתי קריאות מגיעות יחד (קודם כל שמירה טופלה פעמיים), סיסמה שגויה מדווחת כסיסמה שגויה, והקלטה מלאה
#     של OBS מדווחת כ-"recording" ולא נכנסת לשרשור של השורטס.
import asyncio
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from utils.capture import orphans, ring_buffer
from utils.capture.command import CaptureSpec, build_command, remux_command, title_args
from utils.shared import child_guard

ClipCallback = Callable[[str, str], None]
STOP_TIMEOUT_SECONDS = 15
START_GRACE_SECONDS = 0.8          # כמה מחכים לראות ש-ffmpeg לא נפל מיד (מקור שלא נפתח)
AUDIO_CONNECT_SECONDS = 12.0       # כמה מחכים שהשולח של שמע המשחק יתחבר ל-ffmpeg
REMUX_TIMEOUT_SECONDS = 1800
PRUNE_INTERVAL_SECONDS = 5
STDERR_TAIL_LINES = 30


def kill_tree(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            os.kill(pid, 9)
    except (OSError, subprocess.SubprocessError):
        pass


class FfmpegProcess:
    """תהליך ffmpeg אחד: הפעלה, עצירה מסודרת ('q' ב-stdin - הקובץ נסגר תקין), ו-30 שורות ה-stderr האחרונות לשגיאות."""

    def __init__(self, cmd: List[str], creationflags: int = 0, popen: Callable[..., Any] = subprocess.Popen):
        self.cmd = cmd
        self.tail: List[str] = []
        self._proc = popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           creationflags=creationflags)
        self.pid = getattr(self._proc, "pid", None)
        self.guarded = child_guard.tie_to_this_process(self._proc)   # מת יחד עם השרת
        self._reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()

    def _read_stderr(self) -> None:
        stream = self._proc.stderr
        if stream is None:
            return
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self.tail = (self.tail + [line])[-STDERR_TAIL_LINES:]

    @property
    def running(self) -> bool:
        return self._proc.poll() is None

    @property
    def returncode(self) -> Optional[int]:
        return self._proc.poll()

    def stop(self) -> Optional[int]:
        if self.running:
            try:
                self._proc.stdin.write(b"q")
                self._proc.stdin.flush()
            except (OSError, ValueError):
                pass
            try:
                self._proc.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                kill_tree(self._proc.pid)
                self._proc.wait(timeout=STOP_TIMEOUT_SECONDS)
        return self._proc.returncode

    def kill(self) -> None:
        """בלי 'q': ffmpeg שתקוע בפתיחת קלט לא קורא את המקלדת."""
        if self.running:
            kill_tree(self._proc.pid)
            try:
                self._proc.wait(timeout=STOP_TIMEOUT_SECONDS)
            except Exception:
                pass


def free_path(folder: str, name: str, ext: str) -> str:
    """folder/name.ext אם הוא פנוי, אחרת name_2, name_3... - שתי שמירות באותה שנייה לא דורסות זו את זו."""
    candidate, n = os.path.join(folder, name + ext), 2
    while os.path.exists(candidate):
        candidate, n = os.path.join(folder, f"{name}_{n}{ext}"), n + 1
    return candidate


class CaptureError(RuntimeError):
    pass


class FfmpegEngine:
    name = "ffmpeg"

    def __init__(self, ffmpeg_exe: str, cache_dir: str, output_dir: Callable[[], str], on_clip: Optional[ClipCallback] = None,
                 creationflags: int = 0, process_factory: Callable[..., FfmpegProcess] = FfmpegProcess,
                 loopback_factory: Optional[Callable[..., Any]] = None, record_dir: Optional[Callable[[], str]] = None):
        self.ffmpeg_exe = ffmpeg_exe
        self.cache_dir = cache_dir
        self.output_dir = output_dir             # קליפי replay
        self.record_dir = record_dir or output_dir   # הקלטות מלאות
        self.on_clip = on_clip
        self.creationflags = creationflags
        self._factory = process_factory
        self._loopback_factory = loopback_factory
        self._lock = threading.Lock()
        self._record: Optional[FfmpegProcess] = None
        self._record_path = ""
        self._replay: Optional[FfmpegProcess] = None
        self._replay_dir = ""
        self._replay_spec: Optional[CaptureSpec] = None
        self._record_spec: Optional[CaptureSpec] = None
        self._loopbacks: Dict[str, Any] = {}
        self._pruner_stop = threading.Event()
        self.last_error: Optional[str] = None
        self.notice: Optional[str] = None        # לא שגיאה: "מקליט בלי שמע המשחק", "עברתי ל-gdigrab"
        self._pid_file = os.path.join(cache_dir, "capture_pids.json")
        orphans.kill_leftovers(self._pid_file)   # ffmpeg שנשאר מריצה קודמת שמתה באמצע
        orphans.sweep_replay_cache(cache_dir)

    # --- עזר ---
    def _with_loopback(self, spec: CaptureSpec, slot: str) -> Any:
        if spec.source != "screen" or not spec.game_audio_port or self._loopback_factory is None:
            return None
        sender = self._loopback_factory(spec.game_audio_port, spec.game_audio_rate, spec.game_audio_channels)
        if hasattr(sender, "start_mono"):
            sender.start_mono = spec.clock_mono
        sender.start()
        self._loopbacks[slot] = sender
        return sender

    def _stop_loopback(self, slot: str) -> None:
        sender = self._loopbacks.pop(slot, None)
        if sender is not None:
            sender.stop()
            if getattr(sender, "error", None):
                self.last_error = sender.error

    def _forget(self, process: Optional[FfmpegProcess]) -> None:
        if process is not None:
            orphans.forget(self._pid_file, getattr(process, "pid", None))

    def _launch(self, spec: CaptureSpec, slot: str) -> FfmpegProcess:
        """מפעיל ffmpeg ומחכה שהוא באמת מקליט: לא נפל מיד, ושמע המשחק (אם יש) התחבר."""
        spec.clock_wall, spec.clock_mono = time.time(), time.monotonic()   # רגע ההתחלה המשותף לכל הקלטים (command.py)
        process = self._factory(build_command(self.ffmpeg_exe, spec), creationflags=self.creationflags)
        orphans.remember(self._pid_file, getattr(process, "pid", None))
        sender = self._with_loopback(spec, slot)
        connected = getattr(sender, "connected", None)
        deadline = time.monotonic() + (AUDIO_CONNECT_SECONDS if connected is not None else START_GRACE_SECONDS)
        while process.running and time.monotonic() < deadline:
            if connected is not None and (connected.is_set() or getattr(sender, "error", None)):
                break
            time.sleep(0.05)
        if connected is not None and process.running and connected.is_set():
            time.sleep(START_GRACE_SECONDS)      # גם אחרי החיבור: מקור וידאו שנופל מיד
        if connected is not None and process.running and not connected.is_set():
            reason = getattr(sender, "error", None) or "ffmpeg לא קיבל את חיבור השמע"
            process.kill()
            self._forget(process)
            self._loopbacks.pop(slot, None)
            sender.stop()
            spec.game_audio_port = 0
            self.notice = "מקליט בלי שמע המשחק: שמע המחשב לא נפתח"
            print(f"[recording] game audio did not open: {reason}", flush=True)
            return self._launch(spec, slot)
        if not process.running:
            self._stop_loopback(slot)
            self._forget(process)
            detail = " | ".join(process.tail[-3:]) or f"קוד {process.returncode}"
            if spec.source == "screen" and not spec.use_gdigrab:
                spec.use_gdigrab = True
                if spec.game_audio_port:
                    spec.game_audio_port = self._new_port()
                self.notice = "לכידת המסך המהירה לא עלתה, ולכן ההקלטה בלכידה הרגילה (איטית יותר)"
                print(f"[recording] ddagrab failed, trying gdigrab: {detail}", flush=True)
                try:
                    return self._launch(spec, slot)
                except CaptureError:
                    pass                          # גם gdigrab נפל: מדווחים על הכשל הראשון, הוא המועיל
            raise CaptureError("ההקלטה לא התחילה: " + detail)
        return process

    @staticmethod
    def _new_port() -> int:
        from utils.capture import loopback
        return loopback.free_port()

    def _start(self, spec: CaptureSpec, slot: str) -> FfmpegProcess:
        self.last_error = None
        self.notice = None
        return self._launch(spec, slot)

    def _notify(self, path: str, source: str) -> None:
        if self.on_clip:
            try:
                self.on_clip(path, source)
            except Exception as e:   # השרשור האוטומטי לא מפיל את ההקלטה
                self.last_error = f"השרשור אחרי השמירה נכשל: {e}"

    # --- הקלטה רגילה ---
    def start_record(self, spec: CaptureSpec, name: str) -> str:
        with self._lock:
            if self._record and self._record.running:
                raise CaptureError("כבר מקליט")
            folder = self.record_dir()
            os.makedirs(folder, exist_ok=True)
            self._record_path = free_path(folder, name, ".mkv")
            spec.mode, spec.output = "record", self._record_path
            self._record = self._start(spec, "record")
            self._record_spec = spec
            return self._record_path

    def stop_record(self) -> Optional[str]:
        with self._lock:
            if not self._record:
                return None
            process, self._record = self._record, None      # המצב מתנקה לפני כל דבר שיכול להיכשל
            mkv = self._record_path
            try:
                process.stop()
            finally:
                self._stop_loopback("record")
                self._forget(process)
        if not os.path.isfile(mkv) or os.path.getsize(mkv) == 0:
            raise CaptureError("ההקלטה לא נשמרה (קובץ ריק)")
        mp4 = free_path(os.path.dirname(mkv), os.path.splitext(os.path.basename(mkv))[0], ".mp4")
        final = mkv
        try:
            result = subprocess.run(remux_command(self.ffmpeg_exe, mkv, mp4, self._record_spec), capture_output=True, timeout=REMUX_TIMEOUT_SECONDS,
                                    creationflags=self.creationflags)
            if result.returncode == 0 and os.path.isfile(mp4) and os.path.getsize(mp4) > 0:
                os.remove(mkv)
                final = mp4
        except (OSError, subprocess.SubprocessError):
            self.notice = "ההמרה ל-MP4 לא הסתיימה, וההקלטה נשמרה כ-MKV"
        self._notify(final, "recording")
        return final

    # --- replay buffer ---
    def start_replay(self, spec: CaptureSpec, keep_seconds: int, max_bytes: int = ring_buffer.DEFAULT_MAX_BYTES) -> None:
        with self._lock:
            if self._replay and self._replay.running:
                raise CaptureError("ה-replay כבר פועל")
        if self._replay is not None or self._replay_dir:
            self.stop_replay()                   # replay קודם שמת: עוצרים את המנקה שלו ומוחקים את התיקייה שלו
        with self._lock:
            self._replay_dir = free_path(os.path.join(self.cache_dir, "replay"), time.strftime("%Y%m%d_%H%M%S"), "")
            os.makedirs(self._replay_dir, exist_ok=True)
            spec.mode, spec.output = "replay", self._replay_dir
            self._replay_spec = spec
            try:
                self._replay = self._start(spec, "replay")
            except CaptureError:
                folder, self._replay_dir = self._replay_dir, ""
                try:
                    os.rmdir(folder)             # ריקה: ffmpeg לא הספיק לכתוב
                except OSError:
                    pass
                raise
            self._pruner_stop = threading.Event()   # אירוע לכל ריצה: מנקה ישן לא חוזר לחיים כשמתחילים replay חדש
            threading.Thread(target=self._prune_loop, args=(self._pruner_stop, self._replay_dir, keep_seconds, max_bytes,
                                                            spec.segment_seconds), daemon=True).start()

    def _prune_loop(self, stop: threading.Event, folder: str, keep_seconds: int, max_bytes: int, segment_seconds: int) -> None:
        while not stop.wait(PRUNE_INTERVAL_SECONDS):
            for segment in ring_buffer.to_delete(ring_buffer.list_segments(folder), keep_seconds, segment_seconds, max_bytes):
                try:
                    os.remove(segment.path)
                except OSError:
                    pass

    def save_replay(self, seconds: int, name: str) -> str:
        spec = self._replay_spec
        if not (self._replay and self._replay.running and spec):
            raise CaptureError("ה-replay לא פועל")
        picked = ring_buffer.select_for_save(ring_buffer.list_segments(self._replay_dir), seconds, spec.segment_seconds)
        if not picked:
            raise CaptureError("אין עדיין מספיק הקלטה בזיכרון")
        folder = self.output_dir()
        os.makedirs(folder, exist_ok=True)
        list_path = os.path.join(self._replay_dir, f"save_{int(time.time() * 1000)}.txt")
        with open(list_path, "w", encoding="utf-8") as f:
            f.write(ring_buffer.concat_list([s.path for s in picked]))
        out = free_path(folder, name, ".mp4")
        try:
            result = subprocess.run(ring_buffer.save_command(self.ffmpeg_exe, list_path, out, names=title_args(spec, "handler_name")),
                                    capture_output=True, timeout=600,
                                    creationflags=self.creationflags)
            failure = result.stderr.decode("utf-8", errors="replace")[-300:] if result.returncode != 0 else ""
        except (OSError, subprocess.SubprocessError) as e:
            failure = str(e)
        try:
            os.remove(list_path)
        except OSError:
            pass
        if failure or not os.path.isfile(out):
            raise CaptureError("שמירת ה-replay נכשלה: " + failure)
        self._notify(out, "replay")
        return out

    def stop_replay(self) -> None:
        with self._lock:
            self._pruner_stop.set()
            process, self._replay = self._replay, None
            if process:
                try:
                    process.stop()
                finally:
                    self._stop_loopback("replay")
                    self._forget(process)
            folder, self._replay_dir = self._replay_dir, ""
        if folder:
            for segment in ring_buffer.list_segments(folder):
                try:
                    os.remove(segment.path)
                except OSError:
                    pass
            try:
                os.rmdir(folder)
            except OSError:
                pass

    def status(self) -> Dict[str, Any]:
        recording = bool(self._record and self._record.running)
        replay = bool(self._replay and self._replay.running)
        segments = ring_buffer.list_segments(self._replay_dir) if replay else []
        spec = self._replay_spec
        buffered = max(0, len(segments) - 1) * (spec.segment_seconds if spec else ring_buffer.DEFAULT_SEGMENT_SECONDS)
        errors = [p.tail[-1] for p in (self._record, self._replay) if p and not p.running and p.tail]
        return {"engine": self.name, "recording": recording, "recording_path": self._record_path if recording else "",
                "replay": replay, "replay_buffered_seconds": buffered,
                "error": self.last_error or (errors[0] if errors else None), "notice": self.notice}

    def shutdown(self) -> None:
        if self._record:
            try:
                self.stop_record()
            except CaptureError:
                pass
        self.stop_replay()


class ObsEngine:
    """obs-websocket v5 על asyncio loop משלו (thread). הסיסמה מהכספת (OBS_WEBSOCKET_PASSWORD), כמו obs_replay_watcher."""
    name = "obs"

    def __init__(self, url: str, password: str, on_clip: Optional[ClipCallback] = None, client_factory: Optional[Callable[..., Any]] = None):
        self.url, self.password, self.on_clip = url, password, on_clip
        self._client_factory = client_factory
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="clipforge-obs", daemon=True)
        self._thread.start()
        self._ws: Any = None
        self._connecting: Optional[asyncio.Lock] = None   # נוצר על ה-loop של המנוע
        self.last_error: Optional[str] = None
        self.notice: Optional[str] = None
        self._state = {"recording": False, "replay": False}

    def _run(self, coro, timeout: float = 15):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _ensure(self):
        if self._connecting is None:
            self._connecting = asyncio.Lock()
        async with self._connecting:             # שתי קריאות יחד (המסך שואל status ו-scenes) - חיבור אחד, callback אחד
            if self._ws is not None:
                return self._ws
            if self._client_factory is not None:
                ws = self._client_factory(url=self.url, password=self.password)
            else:
                import simpleobsws
                ws = simpleobsws.WebSocketClient(url=self.url, password=self.password or "")
            await ws.connect()
            if await ws.wait_until_identified() is False:
                try:
                    await ws.disconnect()
                except Exception:
                    pass
                raise CaptureError("OBS דחה את החיבור - הסיסמה של WebSocket Server לא נכונה, או שלא הוגדרה ב-ClipForge "
                                   "(OBS_WEBSOCKET_PASSWORD).")
            ws.register_event_callback(self._on_event)
            self._ws = ws
            return ws

    async def _on_event(self, event_type, event_data):
        data = event_data or {}
        if event_type == "ReplayBufferSaved" and data.get("savedReplayPath") and self.on_clip:
            self.on_clip(data["savedReplayPath"], "obs")
        elif event_type == "RecordStateChanged":
            self._state["recording"] = bool(data.get("outputActive"))
            if data.get("outputState") == "OBS_WEBSOCKET_OUTPUT_STOPPED" and data.get("outputPath") and self.on_clip:
                self.on_clip(data["outputPath"], "recording")   # הקלטה מלאה: חומר גלם, לא נכנסת לשרשור של השורטס
        elif event_type == "ReplayBufferStateChanged":
            self._state["replay"] = bool(data.get("outputActive"))

    async def _call(self, request_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import simpleobsws
        ws = await self._ensure()
        response = await ws.call(simpleobsws.Request(request_type, data or {}))
        if not response.ok():
            raise CaptureError(f"OBS: {request_type} נכשל ({getattr(response, 'requestStatus', None)})")
        return response.responseData or {}

    def call(self, request_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            return self._run(self._call(request_type, data))
        except CaptureError:
            raise
        except Exception as e:
            self._ws = None
            raise CaptureError(f"אין חיבור ל-OBS ({e}). ודא ש-OBS פתוח ו-obs-websocket מופעל (Tools > WebSocket Server Settings).")

    def start_record(self, spec=None, name: str = "") -> str:
        self.call("StartRecord")
        self._state["recording"] = True
        return ""

    def stop_record(self) -> Optional[str]:
        path = self.call("StopRecord").get("outputPath") or None
        self._state["recording"] = False
        return path

    def start_replay(self, spec=None, keep_seconds: int = 0, max_bytes: int = 0) -> None:
        self.call("StartReplayBuffer")
        self._state["replay"] = True

    def save_replay(self, seconds: int = 0, name: str = "") -> str:
        self.call("SaveReplayBuffer")   # הנתיב מגיע באירוע ReplayBufferSaved -> on_clip
        return ""

    def stop_replay(self) -> None:
        self.call("StopReplayBuffer")
        self._state["replay"] = False

    def scenes(self) -> Dict[str, Any]:
        data = self.call("GetSceneList")
        return {"current": data.get("currentProgramSceneName"), "scenes": [s.get("sceneName") for s in data.get("scenes", [])][::-1]}

    def switch_scene(self, scene: str) -> None:
        self.call("SetCurrentProgramScene", {"sceneName": scene})

    def status(self) -> Dict[str, Any]:
        try:
            record = self.call("GetRecordStatus")
            replay = self.call("GetReplayBufferStatus")
            self._state = {"recording": bool(record.get("outputActive")), "replay": bool(replay.get("outputActive"))}
            error = None
        except CaptureError as e:
            error = str(e)
            if self._ws is None:                 # אין חיבור: לא יודעים, ולכן לא "מקליט" - אחרת ההגדרות ננעלות על מצב ישן
                self._state = {"recording": False, "replay": False}
        return {"engine": self.name, "recording": self._state["recording"], "recording_path": "",
                "replay": self._state["replay"], "replay_buffered_seconds": None, "error": error, "notice": None}

    def shutdown(self) -> None:
        if self._ws is not None:
            try:
                self._run(self._ws.disconnect(), timeout=5)
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
