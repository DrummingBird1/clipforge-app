# tests/capture/test_manager.py
#
# utils/capture/manager.py: ההגדרות (ניקוי וגבולות), בניית הפקודה לכרטיס לכידה לפי פרופיל קונסולה, לאן הולך כל קובץ,
# ומקשי הקיצור. המנוע מדומה - בלי ffmpeg ובלי חומרה.
import pytest

from utils.capture import devices as dv
from utils.capture import manager as mg
from utils.capture.engine import CaptureError, FfmpegEngine


def test_settings_are_cleaned_and_clamped():
    data = mg.clean_settings({"engine": "vlc", "fps": 9999, "codec": "av1", "console": "ps5", "game_audio": 0,
                              "replay_seconds": "abc", "mic": "  Mic  "})
    assert data["engine"] == "ffmpeg" and data["fps"] == 240 and data["codec"] == "av1" and data["console"] == "ps5"
    assert data["game_audio"] is False and data["replay_seconds"] == mg.DEFAULTS["replay_seconds"] and data["mic"] == "Mic"
    assert mg.clean_settings(None) == mg.DEFAULTS


def test_video_args_use_the_cards_encoder_for_hevc_and_av1():
    assert mg.video_args_for("h264", 20)[:2] == ["-c:v", "libx264"]
    assert mg.video_args_for("hevc", 22, lambda codec, q: ["-c:v", f"{codec}_amf", "-qp", str(q)]) == ["-c:v", "hevc_amf", "-qp", "22"]


def test_a_ps5_on_a_capture_card_records_at_the_best_mode_the_card_has():
    settings = mg.clean_settings({"source": "device", "console": "ps5", "device_video": "HD60 X", "device_audio": "HD60 X Audio"})
    modes = [dv.Mode("nv12", 1920, 1080, 5, 60.0), dv.Mode("mjpeg", 1280, 720, 5, 60.0)]
    spec = mg.build_spec(settings, "ffmpeg", ["-c:v", "x"], list_modes=lambda *a: modes)
    assert (spec.device_size, spec.device_codec, spec.fps) == ("1920x1080", "nv12", 60)
    assert spec.device_audio == "HD60 X Audio"


def test_a_capture_card_must_be_chosen():
    with pytest.raises(CaptureError):
        mg.build_spec(mg.clean_settings({"source": "device"}), "ffmpeg", [])


def test_pc_game_audio_comes_from_loopback_when_there_is_one():
    spec = mg.build_spec(mg.clean_settings({}), "ffmpeg", [], audio_format=lambda: (44100, 2))
    assert spec.game_audio_port > 0 and spec.game_audio_rate == 44100
    silent = mg.build_spec(mg.clean_settings({}), "ffmpeg", [], audio_format=lambda: None)
    assert silent.game_audio_port == 0


class FakeKeyboard:
    def __init__(self):
        self.keys = {}

    def add_hotkey(self, key, action):
        self.keys[key] = action
        return key

    def remove_hotkey(self, handle):
        self.keys.pop(handle, None)


def _manager(tmp_path, keyboard=None, clips=None):
    return mg.RecorderManager(str(tmp_path / "data" / "recording_settings.json"), "ffmpeg", str(tmp_path / "ws"),
                              lambda: str(tmp_path / "imports"), on_clip=lambda p, s: (clips if clips is not None else []).append((p, s)),
                              hotkeys=keyboard)


def test_settings_round_trip_and_changes_are_refused_while_recording(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    saved = manager.save_settings({"fps": 30, "engine": "ffmpeg"})
    assert saved["fps"] == 30 and manager.settings()["fps"] == 30
    monkeypatch.setattr(manager, "busy", lambda: True)
    with pytest.raises(CaptureError):
        manager.save_settings({"fps": 60})


def test_full_recordings_go_to_workspace_recordings_and_replays_to_import(tmp_path, monkeypatch):
    clips = []
    keyboard = FakeKeyboard()
    manager = _manager(tmp_path, keyboard, clips)
    manager.save_settings({"game_audio": False})
    engine = manager.engine()
    assert isinstance(engine, FfmpegEngine)
    seen = {}

    def fake_start_record(spec, name):
        seen["record_dir"] = engine.record_dir()
        seen["replay_dir"] = engine.output_dir()        # 2.0.1: גם בזמן הקלטה מלאה, קליפ replay הולך ל-Import
        engine._record = type("P", (), {"running": True, "tail": [], "stop": lambda self: 0})()
        return ""

    def fake_stop_record():
        engine._record = None
        engine.on_clip("x.mp4", "recording")
        return "x.mp4"

    monkeypatch.setattr(engine, "start_record", fake_start_record)
    monkeypatch.setattr(engine, "stop_record", fake_stop_record)
    manager.start_record()
    assert seen["record_dir"].replace("\\", "/").endswith("ws/recordings")
    assert seen["replay_dir"].replace("\\", "/").endswith("/imports")
    engine.on_clip("during.mp4", "replay")                 # replay שנשמר באמצע הקלטה מלאה נכנס לשרשור
    assert clips == [("during.mp4", "replay")]
    clips.clear()
    assert set(keyboard.keys) == {"ctrl+alt+s", "ctrl+alt+r"}
    manager.stop_record()
    assert clips == []                                     # הקלטה מלאה לא נכנסת לשרשור
    assert engine.output_dir().replace("\\", "/").endswith("/imports")
    assert keyboard.keys == {}
    engine.on_clip("r.mp4", "replay")                      # replay - כן
    assert clips == [("r.mp4", "replay")] and manager.last_saved == "r.mp4"


def test_switching_engine_in_settings_replaces_the_engine(tmp_path):
    manager = _manager(tmp_path)
    first = manager.engine()
    manager.save_settings({"engine": "ffmpeg", "fps": 50})
    assert manager.engine() is not first
    with pytest.raises(CaptureError):
        manager.scenes()


def test_importing_from_a_console_drive_runs_in_the_background_and_reports_progress(tmp_path):
    import os
    import time
    from utils.capture import import_presets as ip
    clips = tmp_path / "usb" / "PS5" / "CREATE" / "Video Clips" / "Game"
    clips.mkdir(parents=True)
    for name in ("a.mp4", "b.webm"):
        (clips / name).write_bytes(b"v")
        os.utime(clips / name, (time.time() - 3600,) * 2)
    preset = ip.Preset("ps5:X", "PlayStation 5 (X)", str(tmp_path / "usb" / "PS5" / "CREATE" / "Video Clips"), "folder", True, True)
    manager = _manager(tmp_path)
    assert manager.import_sources(lambda: [preset])[0]["new"] == 2
    manager.start_import("ps5:X", lambda: [preset])
    deadline = time.time() + 10
    while manager.status()["import"].get("running") and time.time() < deadline:
        time.sleep(0.05)
    state = manager.status()["import"]
    assert (state["done"], state["total"], state["error"]) == (2, 2, None)
    assert sorted(os.listdir(tmp_path / "imports")) == ["a.mp4", "b.webm"]
    assert manager.import_sources(lambda: [preset])[0]["new"] == 0
    with pytest.raises(CaptureError):
        manager.start_import("ps5:Y", lambda: [preset])




class _FakeEngine:
    name = "ffmpeg"

    def __init__(self):
        self.recording = self.replay = False
        self.last_error = self.notice = None
        self.saved = []
        self.replay_spec = None

    def status(self):
        return {"engine": "ffmpeg", "recording": self.recording, "replay": self.replay, "replay_buffered_seconds": 0, "error": None}

    def start_replay(self, spec, keep, max_bytes):
        self.replay, self.replay_spec = True, spec

    def stop_replay(self):
        self.replay = False

    def save_replay(self, seconds, name):
        self.saved.append(name)

    def shutdown(self):
        pass


def test_a_held_hotkey_saves_once_and_stopping_replay_keeps_the_record_hotkey(tmp_path, monkeypatch):
    keyboard = FakeKeyboard()
    manager = _manager(tmp_path, keyboard)
    manager.save_settings({"game_audio": False})
    fake = _FakeEngine()
    monkeypatch.setattr(manager, "engine", lambda: fake)
    monkeypatch.setattr(mg, "FfmpegEngine", _FakeEngine)
    manager._engine = fake
    manager.start_replay()
    for _ in range(30):                                    # מקש מוחזק: Windows שולח אותו עשרות פעמים בשנייה
        keyboard.keys["ctrl+alt+s"]()
    assert len(fake.saved) == 1
    fake.recording = True
    manager.stop_replay()
    assert set(keyboard.keys) == {"ctrl+alt+s", "ctrl+alt+r"}     # הקלטה מלאה עדיין רצה - המקש שעוצר אותה נשאר
    fake.recording = False
    manager.start_replay()
    manager.stop_replay()
    assert keyboard.keys == {}


def test_replay_never_records_av1(tmp_path, monkeypatch):
    # AV1 לא עובר במקטעי MPEG-TS של ה-replay: הקליפ שנשמר יצא פגום. ה-replay מוקלט ב-HEVC, וההקלטה המלאה נשארת AV1.
    manager = _manager(tmp_path)
    manager.backend_args = lambda codec, quality: ["-c:v", f"{codec}_nvenc"]
    manager.save_settings({"game_audio": False, "codec": "av1"})
    assert manager._spec().video_args == ["-c:v", "av1_nvenc"]
    assert manager._spec(replay=True).video_args == ["-c:v", "hevc_nvenc"]
    fake = _FakeEngine()
    monkeypatch.setattr(manager, "engine", lambda: fake)
    monkeypatch.setattr(mg, "FfmpegEngine", _FakeEngine)
    manager.start_replay()
    assert fake.replay_spec.video_args == ["-c:v", "hevc_nvenc"] and "HEVC" in fake.notice


def test_a_capture_card_at_59_94_asks_for_59_94_not_59():
    settings = mg.clean_settings({"source": "device", "console": "ps5", "device_video": "Card"})
    spec = mg.build_spec(settings, "ffmpeg", [], list_modes=lambda *a: [dv.Mode("nv12", 1920, 1080, 5, 59.94)])
    assert spec.fps == 60 and spec.device_fps == "59.94"
    whole = mg.build_spec(settings, "ffmpeg", [], list_modes=lambda *a: [dv.Mode("nv12", 1920, 1080, 5, 60.0)])
    assert whole.fps == 60 and whole.device_fps is None


def test_a_double_click_starts_one_import(tmp_path):
    manager = _manager(tmp_path)
    manager._import = {"running": True}
    with pytest.raises(CaptureError):
        manager.start_import("ps5")
    manager._import = {}
    with pytest.raises(CaptureError):                      # מקור שלא קיים: הדגל משתחרר, אפשר לנסות שוב
        manager.start_import("missing", presets_fn=lambda: [])
    assert manager._import.get("running") is False


def test_the_card_is_measured_once_and_the_user_is_told(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    manager.save_settings({"source": "device", "console": "ps5", "device_video": "usb video", "device_audio": "usb audio"})
    full, small = dv.Mode("mjpeg", 1920, 1080, 10, 60.0), dv.Mode("mjpeg", 1280, 720, 10, 60.0)
    monkeypatch.setattr(dv, "list_modes", lambda *a, **k: [full, small])
    calls = []

    def fake_measure(ffmpeg, device, mode, fps, creationflags=0, seconds=2.0):
        calls.append((device, mode.height, round(fps)))
        return 29.7 if mode.height == 1080 and fps > 31 else float(round(fps))

    monkeypatch.setattr(dv, "measure_mode", fake_measure)
    spec = mg.build_spec(manager.settings(), "ffmpeg", [], list_modes=dv.list_modes,
                         measure=lambda mode, fps: manager._measure("usb video", mode, fps))
    assert (spec.device_size, spec.fps, spec.device_fps) == ("1920x1080", 30, None)
    assert spec.note == "הכרטיס מכריז על 60 פריימים ב-1920x1080 אבל נותן 30. מקליט ב-1920x1080 ב-30 פריימים"
    assert calls == [("usb video", 1080, 60), ("usb video", 1080, 30)]
    mg.build_spec(manager.settings(), "ffmpeg", [], list_modes=dv.list_modes, measure=lambda mode, fps: manager._measure("usb video", mode, fps))
    assert len(calls) == 2                                   # מהמטמון - לא מודדים שוב בכל הקלטה
    again = _manager(tmp_path)                               # גם אחרי הפעלה מחדש
    assert again._measure("usb video", full, 60.0) == 29.7 and len(calls) == 2
    again.forget_measurements()                              # "רענן התקנים"
    assert again._measure("usb video", full, 60.0) == 29.7 and len(calls) == 3
    manager.save_settings({"card_prefer": "fps"})
    smooth = mg.build_spec(manager.settings(), "ffmpeg", [], list_modes=dv.list_modes,
                           measure=lambda mode, fps: manager._measure("usb video", mode, fps))
    assert (smooth.device_size, smooth.fps) == ("1280x720", 60) and "מקליט ב-1280x720 ב-60 פריימים" in smooth.note
    assert mg.clean_settings({"card_prefer": "bogus"})["card_prefer"] == "resolution"


def test_a_card_without_a_console_profile_still_gets_a_mode():
    settings = mg.clean_settings({"source": "device", "device_video": "Card", "fps": 60})
    spec = mg.build_spec(settings, "ffmpeg", [], list_modes=lambda *a: [dv.Mode("nv12", 1920, 1080, 5, 60.0), dv.Mode("nv12", 1280, 720, 5, 60.0)])
    assert (spec.device_size, spec.device_codec, spec.fps, spec.note) == ("1920x1080", "nv12", 60, "")
