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
