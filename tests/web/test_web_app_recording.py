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

    def forget_engine(self):
        if "record/start" in self.calls:
            raise CaptureError("עצור את ההקלטה וה-replay לפני שינוי הסיסמה")
        self.calls.append("forget_engine")


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


def test_the_obs_password_is_saved_to_the_vault_and_never_sent_back(manager, monkeypatch):
    """18.11.2026: המסך אמר "הסיסמה נשמרת בכספת" בלי שום דרך להזין אותה. הכספת כאן מדומה - הטסט לא נוגע ב-Credential Manager."""
    vault, logged = {}, []
    monkeypatch.setattr(web_app, "set_vault_secret", lambda key, value: vault.__setitem__(key, value))
    monkeypatch.setattr(web_app, "is_vault_available", lambda: True)
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: logged.append((a, k)))
    monkeypatch.setattr(rec_routes, "_obs_password_saved", lambda: bool(vault))
    assert client.get("/api/recording/settings").json()["obs_password"] is False
    resp = client.post("/api/recording/obs/password", json={"password": "s3cret-from-obs"})
    assert resp.status_code == 200 and resp.json() == {"ok": True, "obs_password": True}
    assert vault == {"OBS_WEBSOCKET_PASSWORD": "s3cret-from-obs"} and "forget_engine" in manager.calls   # החיבור הבא עם הסיסמה החדשה
    assert "s3cret-from-obs" not in resp.text and "s3cret-from-obs" not in repr(logged)
    settings = client.get("/api/recording/settings")
    assert settings.json()["obs_password"] is True and "s3cret-from-obs" not in settings.text


def test_the_obs_password_route_refuses_what_it_should(manager, monkeypatch):
    vault = {}
    monkeypatch.setattr(web_app, "set_vault_secret", lambda key, value: vault.__setitem__(key, value))
    monkeypatch.setattr(web_app, "is_vault_available", lambda: True)
    assert client.post("/api/recording/obs/password", json={"password": ""}).status_code == 400
    assert client.post("/api/recording/obs/password", json={"password": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403
    client.post("/api/recording/record/start")                                   # באמצע הקלטה: לא מחליפים סיסמה
    busy = client.post("/api/recording/obs/password", json={"password": "x"})
    assert busy.status_code == 400 and "לפני שינוי הסיסמה" in busy.json()["error"] and vault == {}
    monkeypatch.setattr(web_app, "is_vault_available", lambda: False)
    assert client.post("/api/recording/obs/password", json={"password": "x"}).status_code == 400 and vault == {}


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


def test_the_manifest_reports_the_version_for_the_launcher():
    data = client.get("/manifest.json").json()
    assert data["short_name"] == "ClipForge" and data["version"] == web_app.APP_VERSION
