# tests/web/test_web_app_recording.py
#
# 16.11.2026 (2.0): /api/recording/* (routes/recording.py) - מנהל ההקלטה מדומה, בלי ffmpeg ובלי חומרה.
import pytest

from entrypoints import web_app
from entrypoints.web.routes import recording as rec_routes
from tests.web_app_support import client
from utils.capture import devices as dv
from utils.capture.engine import CaptureError


class FakeManager:
    def __init__(self):
        self.calls = []
        self._settings = {"engine": "ffmpeg", "fps": 60}

    def status(self):
        return {"engine": "ffmpeg", "recording": "record/start" in self.calls, "replay": False, "error": None}

    def settings(self):
        return dict(self._settings)

    def save_settings(self, raw):
        self._settings.update(raw)
        return self.settings()

    def start_record(self):
        self.calls.append("record/start")
        return self.status()

    def stop_record(self):
        self.calls.append("record/stop")
        return self.status()

    def start_replay(self):
        raise CaptureError("ה-replay כבר פועל")

    def save_replay(self, seconds=None):
        self.calls.append(("save", seconds))
        return self.status()

    def stop_replay(self):
        return self.status()

    def scenes(self):
        raise CaptureError("סצנות זמינות רק עם OBS")


@pytest.fixture
def manager(monkeypatch):
    fake = FakeManager()
    monkeypatch.setattr(rec_routes, "_manager", fake)
    return fake


def test_status_and_settings(manager):
    assert client.get("/api/recording/status").json()["engine"] == "ffmpeg"
    data = client.get("/api/recording/settings").json()
    assert data["settings"]["fps"] == 60 and {c["id"] for c in data["consoles"]} >= {"ps5", "switch"}
    assert client.post("/api/recording/settings", json={"fps": 30}).json()["settings"]["fps"] == 30


def test_actions_go_to_the_manager_and_errors_are_400(manager):
    assert client.post("/api/recording/record/start").json()["recording"] is True
    resp = client.post("/api/recording/replay/start")
    assert resp.status_code == 400 and "replay" in resp.json()["error"]
    client.post("/api/recording/replay/save", json={"seconds": 30})
    assert ("save", 30) in manager.calls
    assert client.get("/api/recording/obs/scenes").status_code == 400


def test_a_foreign_origin_cannot_start_a_recording(manager):
    resp = client.post("/api/recording/record/start", headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403 and manager.calls == []


def test_devices_are_listed_by_kind(manager, monkeypatch):
    monkeypatch.setattr(dv, "list_devices", lambda *a, **k: [dv.Device("HD60 X", "video", "@a"), dv.Device("Mic", "audio", "@b")])
    assert client.get("/api/recording/devices").json() == {"video": [{"name": "HD60 X", "alternative": "@a"}],
                                                          "audio": [{"name": "Mic", "alternative": "@b"}]}


def test_a_saved_replay_goes_to_the_auto_chain(monkeypatch):
    events = []
    monkeypatch.setattr(web_app, "_on_clip_ready", events.append)
    rec_routes._on_clip("C:/imports/replay_1.mp4", "replay")
    assert events == [{"script": "recording", "path": "C:/imports/replay_1.mp4", "source": "replay"}]
