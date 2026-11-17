# tests/capture/test_engine.py
#
# utils/capture/engine.py: FfmpegEngine עם ffmpeg אמיתי - המקור (ddagrab/כרטיס) מוחלף ב-testsrc, והיעד (MKV / קטעי replay)
# נשאר מהפקודה שהמנוע בנה. עצירה ב-'q', remux ל-MP4, שמירת replay, וקריאה ל-on_clip. ObsEngine מול לקוח websocket מדומה.
import asyncio
import os
import time

import pytest

from tests.media_support import needs_ffmpeg
from utils.capture.command import CaptureSpec
from utils.capture.engine import CaptureError, FfmpegEngine, FfmpegProcess, ObsEngine
from utils.shared.ffmpeg_locator import get_ffmpeg_exe


def _testsrc_factory(cmd, creationflags=0):
    """אותו יעד כמו הפקודה של המנוע, עם testsrc + שני ערוצי שמע במקום מסך ומיקרופון."""
    start = cmd.index("-c:v")
    tail = cmd[start:]
    tail[tail.index("-c:v") + 1:tail.index("-c:v") + 2] = ["libx264"]
    real = [get_ffmpeg_exe(), "-hide_banner", "-y", "-re", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10",
            "-re", "-f", "lavfi", "-i", "sine=f=440", "-map", "0:v", "-map", "1:a", "-preset", "ultrafast",
            "-c:a", "aac", *tail]
    return FfmpegProcess(real, creationflags=creationflags)


def _engine(tmp_path, clips):
    return FfmpegEngine(get_ffmpeg_exe(), str(tmp_path / "cache"), lambda: str(tmp_path / "out"),
                        on_clip=lambda path, source: clips.append((path, source)), process_factory=_testsrc_factory)


@needs_ffmpeg
def test_a_recording_stops_cleanly_and_becomes_an_mp4(tmp_path):
    clips = []
    engine = _engine(tmp_path, clips)
    mkv = engine.start_record(CaptureSpec(fps=10, video_args=["-c:v", "x"]), "rec_1")
    assert mkv.endswith("rec_1.mkv") and engine.status()["recording"]
    time.sleep(2)
    final = engine.stop_record()
    assert final.endswith("rec_1.mp4") and os.path.getsize(final) > 0 and not os.path.exists(mkv)
    assert clips == [(final, "recording")]
    assert not engine.status()["recording"]


@needs_ffmpeg
def test_replay_saves_the_last_seconds_and_cleans_up(tmp_path):
    clips = []
    engine = _engine(tmp_path, clips)
    engine.start_replay(CaptureSpec(fps=10, segment_seconds=1, video_args=["-c:v", "x"]), keep_seconds=30)
    deadline = time.time() + 20
    while engine.status()["replay_buffered_seconds"] < 3 and time.time() < deadline:
        time.sleep(0.2)
    out = engine.save_replay(2, "replay_1")
    assert os.path.getsize(out) > 0 and clips == [(out, "replay")]
    folder = engine._replay_dir
    engine.stop_replay()
    assert not os.path.exists(folder)
    with pytest.raises(CaptureError):
        engine.save_replay(2, "again")


@needs_ffmpeg
def test_a_command_that_dies_at_once_reports_why(tmp_path):
    def broken(cmd, creationflags=0):
        return FfmpegProcess([get_ffmpeg_exe(), "-hide_banner", "-f", "lavfi", "-i", "nonexistent_source_xyz", "-f", "null", "-"])
    engine = FfmpegEngine(get_ffmpeg_exe(), str(tmp_path / "c"), lambda: str(tmp_path / "o"), process_factory=broken)
    with pytest.raises(CaptureError):
        engine.start_record(CaptureSpec(video_args=["-c:v", "x"]), "x")


def test_a_double_start_is_refused(tmp_path):
    class Running:
        running, tail, returncode = True, [], None

        def __init__(self, cmd, creationflags=0):
            pass

        def stop(self):
            return 0

    engine = FfmpegEngine("ffmpeg", str(tmp_path / "c"), lambda: str(tmp_path / "o"), process_factory=Running)
    engine.start_record(CaptureSpec(video_args=[]), "a")
    with pytest.raises(CaptureError):
        engine.start_record(CaptureSpec(video_args=[]), "b")


# --- OBS ---

class FakeResponse:
    def __init__(self, data=None, ok=True):
        self.responseData, self._ok, self.requestStatus = data or {}, ok, None

    def ok(self):
        return self._ok


class FakeObs:
    instances = []

    def __init__(self, url, password):
        self.url, self.password, self.calls, self.callback = url, password, [], None
        FakeObs.instances.append(self)

    async def connect(self):
        pass

    async def wait_until_identified(self):
        return True

    def register_event_callback(self, callback):
        self.callback = callback

    async def call(self, request):
        self.calls.append((request.requestType, request.requestData))
        if request.requestType == "GetSceneList":
            return FakeResponse({"currentProgramSceneName": "Game", "scenes": [{"sceneName": "BRB"}, {"sceneName": "Game"}]})
        if request.requestType == "StopRecord":
            return FakeResponse({"outputPath": "C:/obs/rec.mkv"})
        return FakeResponse()

    async def disconnect(self):
        pass


def test_obs_engine_drives_obs_and_forwards_saved_replays():
    clips = []
    FakeObs.instances.clear()
    engine = ObsEngine("ws://localhost:4455", "pw", on_clip=lambda p, s: clips.append((p, s)), client_factory=FakeObs)
    try:
        engine.start_replay()
        engine.save_replay()
        assert engine.scenes() == {"current": "Game", "scenes": ["Game", "BRB"]}
        engine.switch_scene("BRB")
        engine.start_record()
        assert engine.stop_record() == "C:/obs/rec.mkv"
        obs = FakeObs.instances[0]
        assert [c[0] for c in obs.calls] == ["StartReplayBuffer", "SaveReplayBuffer", "GetSceneList",
                                             "SetCurrentProgramScene", "StartRecord", "StopRecord"]
        assert obs.calls[3][1] == {"sceneName": "BRB"}
        asyncio.run_coroutine_threadsafe(obs.callback("ReplayBufferSaved", {"savedReplayPath": "C:/obs/r.mp4"}),
                                         engine._loop).result(5)
        assert clips == [("C:/obs/r.mp4", "obs")]
    finally:
        engine.shutdown()


def test_obs_not_running_gives_a_clear_error():
    class Down(FakeObs):
        async def connect(self):
            raise ConnectionRefusedError("refused")

    engine = ObsEngine("ws://localhost:4455", "", client_factory=Down)
    try:
        with pytest.raises(CaptureError, match="OBS"):
            engine.start_record()
        assert engine.status()["error"]
    finally:
        engine.shutdown()



# ---- 2.0.1: מהבדיקה המעמיקה ----

class _FakeProcess:
    """תהליך מדומה: רץ עד kill/stop, או מת מיד (dies=True) עם שורת שגיאה."""

    def __init__(self, cmd, dies=False):
        self.cmd, self.tail, self.pid = cmd, (["cannot open the source"] if dies else []), None
        self.running, self.returncode, self.killed = not dies, (1 if dies else None), False

    def stop(self):
        self.running = False
        return 0

    def kill(self):
        self.running, self.killed = False, True


class _FakeSender:
    def __init__(self, connects):
        import threading
        self.connected, self.error, self.stopped = threading.Event(), None, False
        self._connects = connects

    def start(self):
        if self._connects:
            self.connected.set()
        else:
            self.error = "Invalid number of channels"

    def stop(self):
        self.stopped = True


def _fake_engine(tmp_path, processes, senders=None):
    made = {"cmds": [], "senders": []}

    def factory(cmd, creationflags=0):
        made["cmds"].append(cmd)
        return processes(cmd)

    def loopback_factory(port, rate, channels):
        sender = senders()
        made["senders"].append(sender)
        return sender

    engine = FfmpegEngine("ffmpeg", str(tmp_path / "cache"), lambda: str(tmp_path / "out"), process_factory=factory,
                          loopback_factory=loopback_factory if senders else None, record_dir=lambda: str(tmp_path / "rec"))
    return engine, made


def test_game_audio_that_cannot_open_does_not_leave_a_recording_that_records_nothing(tmp_path, monkeypatch):
    # 2.0.0: השולח נכשל, ffmpeg חיכה לנצח לחיבור השמע, והמסך אמר "מקליט". עכשיו: מתחילים שוב בלי שמע המשחק, עם הודעה.
    from utils.capture import engine as engine_module
    monkeypatch.setattr(engine_module, "START_GRACE_SECONDS", 0.05)
    engine, made = _fake_engine(tmp_path, lambda cmd: _FakeProcess(cmd), senders=lambda: _FakeSender(connects=False))
    engine.start_record(CaptureSpec(fps=30, game_audio_port=50123), "rec")
    first, second = made["cmds"]
    assert any("tcp://127.0.0.1:50123" in part for part in first) and not any("tcp://" in part for part in second)
    assert made["senders"][0].stopped and len(made["senders"]) == 1
    status = engine.status()
    assert status["recording"] and "בלי שמע המשחק" in status["notice"] and status["error"] is None


def test_game_audio_that_connects_keeps_its_track(tmp_path, monkeypatch):
    from utils.capture import engine as engine_module
    monkeypatch.setattr(engine_module, "START_GRACE_SECONDS", 0.05)
    engine, made = _fake_engine(tmp_path, lambda cmd: _FakeProcess(cmd), senders=lambda: _FakeSender(connects=True))
    engine.start_record(CaptureSpec(fps=30, game_audio_port=50123), "rec")
    assert len(made["cmds"]) == 1 and engine.status()["notice"] is None


def test_a_screen_capture_that_fails_tries_the_plain_capture(tmp_path, monkeypatch):
    # ddagrab לא עולה במשחק במסך מלא בלעדי או במחשב ישן. הנפילה ל-gdigrab הייתה קיימת בקוד אבל אף פעם לא הופעלה.
    from utils.capture import engine as engine_module
    monkeypatch.setattr(engine_module, "START_GRACE_SECONDS", 0.05)
    engine, made = _fake_engine(tmp_path, lambda cmd: _FakeProcess(cmd, dies=any("ddagrab" in part for part in cmd)))
    engine.start_record(CaptureSpec(fps=30), "rec")
    assert "gdigrab" in made["cmds"][1] and engine.status()["recording"] and "בלכידה הרגילה" in engine.status()["notice"]
    both, made = _fake_engine(tmp_path, lambda cmd: _FakeProcess(cmd, dies=True))
    with pytest.raises(CaptureError, match="cannot open the source"):
        both.start_record(CaptureSpec(fps=30), "rec")
    assert len(made["cmds"]) == 2 and not both.status()["recording"]
    card, made = _fake_engine(tmp_path, lambda cmd: _FakeProcess(cmd, dies=True))      # כרטיס לכידה: אין מה לנסות במקומו
    with pytest.raises(CaptureError):
        card.start_record(CaptureSpec(fps=30, source="device", device_video="Card"), "rec")
    assert len(made["cmds"]) == 1


def test_a_card_held_by_another_app_says_so(tmp_path, monkeypatch):
    # 17.11.2026, על חומרה אמיתית: OBS היה פתוח עם הכרטיס, וההודעה הייתה שורת ffmpeg גולמית ("Error opening input: I/O error")
    from utils.capture import engine as engine_module
    monkeypatch.setattr(engine_module, "START_GRACE_SECONDS", 0.05)

    class Busy(_FakeProcess):
        def __init__(self, cmd):
            super().__init__(cmd, dies=True)
            self.tail = ["[in#0 @ 000001] Error opening input: I/O error", "Error opening input file video=Card:audio=Card Audio.",
                         "Error opening input files: I/O error"]

    card, _made = _fake_engine(tmp_path, Busy)
    with pytest.raises(CaptureError, match="כרטיס הלכידה תפוס"):
        card.start_record(CaptureSpec(fps=30, source="device", device_video="Card", device_audio="Card Audio"), "rec")
    assert not card.status()["recording"]
    screen, _made = _fake_engine(tmp_path, Busy)                 # אותה שורה בלכידת מסך אינה כרטיס תפוס
    with pytest.raises(CaptureError) as error:
        screen.start_record(CaptureSpec(fps=30), "rec")
    assert "תפוס" not in str(error.value)
    other, _made = _fake_engine(tmp_path, lambda cmd: _FakeProcess(cmd, dies=True))   # כשל אחר של הכרטיס נשאר כמו שהוא
    with pytest.raises(CaptureError, match="cannot open the source"):
        other.start_record(CaptureSpec(fps=30, source="device", device_video="Card"), "rec")


def test_two_saves_in_one_second_get_two_names(tmp_path):
    from utils.capture.engine import free_path
    folder = tmp_path / "out"
    folder.mkdir()
    first = free_path(str(folder), "replay_1", ".mp4")
    open(first, "wb").close()
    second = free_path(str(folder), "replay_1", ".mp4")
    assert first.endswith("replay_1.mp4") and second.endswith("replay_1_2.mp4")


def test_leftovers_of_a_run_that_died_are_cleaned_at_start(tmp_path):
    from utils.capture import orphans
    stale = tmp_path / "cache" / "replay" / "20261116_182838"
    stale.mkdir(parents=True)
    for name in ("seg_000001.ts", "seg_000002.ts", "save_123.txt"):
        (stale / name).write_bytes(b"x" * 10)
    keep = tmp_path / "cache" / "encoders.json"
    keep.write_text("{}", encoding="utf-8")
    FfmpegEngine("ffmpeg", str(tmp_path / "cache"), lambda: str(tmp_path / "out"))
    assert not stale.exists() and keep.exists()
    pid_file = str(tmp_path / "cache" / "capture_pids.json")
    orphans.remember(pid_file, os.getpid())                 # התהליך הזה חי אבל אינו ffmpeg - לא נוגעים בו
    assert orphans.kill_leftovers(pid_file) == 0 and orphans._load(pid_file) == []


@needs_ffmpeg
def test_an_ffmpeg_left_by_a_dead_server_is_closed_at_start(tmp_path):
    import subprocess

    from utils.capture import orphans
    pid_file = str(tmp_path / "cache" / "capture_pids.json")
    orphan = subprocess.Popen([get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-re", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5",
                               "-f", "null", "-"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        orphans.remember(pid_file, orphan.pid)
        FfmpegEngine(get_ffmpeg_exe(), str(tmp_path / "cache"), lambda: str(tmp_path / "out"))
        assert orphan.wait(timeout=15) is not None
    finally:
        if orphan.poll() is None:
            orphan.kill()


@needs_ffmpeg
@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object")
def test_ffmpeg_dies_with_the_server(tmp_path):
    # 2.0.0: שרת שנסגר בכוח השאיר את ffmpeg של ה-replay לכתוב מקטעים עד שהדיסק מתמלא (10GB ב-19 שעות בבדיקה).
    import subprocess
    import sys

    import psutil

    from tests import PROJECT_ROOT
    script = tmp_path / "server.py"
    script.write_text(
        "import sys, time\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from utils.capture.engine import FfmpegProcess\n"
        "p = FfmpegProcess([sys.argv[2], '-hide_banner', '-loglevel', 'error', '-re', '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=5', '-f', 'null', '-'])\n"
        "print(p.pid, p.guarded, flush=True)\n"
        "time.sleep(120)\n", encoding="utf-8")
    server = subprocess.Popen([sys.executable, str(script), os.path.join(PROJECT_ROOT, "src"), get_ffmpeg_exe()],
                              stdout=subprocess.PIPE, text=True)
    try:
        pid, guarded = server.stdout.readline().split()
        assert guarded == "True" and psutil.pid_exists(int(pid))
        subprocess.run(["taskkill", "/PID", str(server.pid), "/F"], capture_output=True)      # בלי /T: רק השרת
        deadline = time.time() + 15
        while psutil.pid_exists(int(pid)) and time.time() < deadline:
            time.sleep(0.2)
        assert not psutil.pid_exists(int(pid))
    finally:
        if server.poll() is None:
            server.kill()


def test_obs_opens_one_connection_for_calls_that_arrive_together():
    # 2.0.0: המסך שואל status ו-scenes יחד - שני לקוחות נפתחו, וכל replay שנשמר טופל פעמיים.
    clients = []

    class SlowObs(FakeObs):
        async def connect(self):
            await asyncio.sleep(0.05)
            await super().connect()

    def factory(url, password):
        clients.append(SlowObs(url, password))
        return clients[-1]

    seen = []
    engine = ObsEngine("ws://localhost:4455", "pw", on_clip=lambda path, source: seen.append((path, source)), client_factory=factory)
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda _: engine.status(), range(4)))
        assert len(clients) == 1
        engine._run(clients[0].callback("RecordStateChanged", {"outputActive": False, "outputState": "OBS_WEBSOCKET_OUTPUT_STOPPED",
                                                               "outputPath": "full.mkv"}))
        assert seen == [("full.mkv", "recording")]         # הקלטה מלאה של OBS: לא "obs" - לא נכנסת לשרשור של השורטס
    finally:
        engine.shutdown()


def test_obs_wrong_password_says_so():
    class Refusing(FakeObs):
        async def wait_until_identified(self, timeout=10):
            return False

    engine = ObsEngine("ws://localhost:4455", "bad", client_factory=lambda url, password: Refusing(url, password))
    try:
        with pytest.raises(CaptureError, match="הסיסמה"):
            engine.start_record()
        status = engine.status()
        assert not status["recording"] and "הסיסמה" in status["error"]
    finally:
        engine.shutdown()
