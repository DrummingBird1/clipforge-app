# tests/studio/test_web_app_editor_wave13.py
#
# גל 13 דרך ה-API: הזרמת קובץ המקור לנגן החי (רק קובץ וידאו בשם בתוך תיקייה, עם
# Range לקפיצות), ופרוקסי 480p לקבצים שהדפדפן לא מנגן (ffmpeg אמיתי).
import os
import shutil
import subprocess
import time


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import video_editor_profiles as vep

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "data" / "video_editor_profiles.json"))
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "previews"))


def test_source_stream_serves_video_by_name_with_ranges(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"0123456789" * 100)
    (tmp_path / "notes.txt").write_text("secret", encoding="utf-8")
    full = client.get("/api/video_editor/source_stream", params={"folder": str(tmp_path), "file": "clip.mp4"})
    assert full.status_code == 200 and len(full.content) == 1000
    part = client.get("/api/video_editor/source_stream", params={"folder": str(tmp_path), "file": "clip.mp4"}, headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == b"0123456789"
    for bad in ("notes.txt", "..\\clip.mp4", "sub/clip.mp4", "missing.mp4", ""):
        assert client.get("/api/video_editor/source_stream", params={"folder": str(tmp_path), "file": bad}).status_code == 404, bad


def test_proxy_rejects_unknown_file(tmp_path):
    assert client.post("/api/video_editor/proxy", json={"folder": str(tmp_path), "file": "nope.mp4"}).status_code == 404


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")
def test_proxy_is_built_once_and_served(tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=1280x720:rate=10", "-pix_fmt", "yuv420p", str(tmp_path / "big.mkv")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    body = {"folder": str(tmp_path), "file": "big.mkv"}
    state = client.post("/api/video_editor/proxy", json=body).json()
    deadline = time.time() + 60
    while state["state"] == "working" and time.time() < deadline:
        time.sleep(0.5)
        state = client.post("/api/video_editor/proxy", json=body).json()
    assert state["state"] == "ready", state
    served = client.get(state["url"])
    assert served.status_code == 200 and len(served.content) > 1000
    from utils.media.ffprobe_cache import probe_video
    proxy_path = os.path.join(web_app.PREVIEWS_DIR, state["url"].split("name=")[1])
    assert probe_video(proxy_path)["height"] == 480
