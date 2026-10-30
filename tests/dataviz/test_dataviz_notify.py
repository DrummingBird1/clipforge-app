# tests/dataviz/test_dataviz_notify.py
#
# 20.10.2026: התראה בסיום / כישלון רינדור - Discord webhook אופציונלי שנשמר כסוד (כאן: מאגר סודות מזויף בזיכרון - לא
# Credential Manager אמיתי) ולא חוזר לדפדפן. השליחה רק למקבל מזויף (post=); מתוך pytest בלי post לא נשלח כלום.
import importlib.util
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.web import notify
from entrypoints import web_app
from entrypoints.web_app import app
from tests import PROJECT_ROOT
from utils.shared import secrets_vault

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

URL = "https://discord.com/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyzABCDEF"


class FakeReceiver:
    def __init__(self, status=204):
        self.calls, self.status = [], status

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json, timeout))
        return type("Response", (), {"status_code": self.status})()


@pytest.fixture
def secrets(monkeypatch):
    store = {}
    monkeypatch.setattr(secrets_vault, "get_secret", lambda key, default="": store.get(key, default))
    monkeypatch.setattr(secrets_vault, "set_secret", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(secrets_vault, "delete_secret", lambda key: store.pop(key, None))
    return store


def test_only_discord_webhook_urls_are_accepted():
    assert notify.valid_url(URL) and notify.valid_url(URL.replace("discord.com", "discordapp.com"))
    for bad in ("", "http://discord.com/api/webhooks/1234567/abcdefghijklmnopqrstuv", "https://evil.example/api/webhooks/123456/abcdefghijklmnopqrstuvwx",
                URL + "?wait=true", "https://discord.com/api/webhooks/123/short"):
        assert not notify.valid_url(bad), bad


def test_the_url_is_stored_as_a_secret_and_never_sent_back(secrets):
    assert client.get("/api/dataviz/notify").json() == {"configured": False, "hint": ""}
    assert client.post("/api/dataviz/notify", json={"url": "https://example.com/hook"}).status_code == 400
    resp = client.post("/api/dataviz/notify", json={"url": URL})
    assert resp.status_code == 200 and secrets[notify.SECRET_KEY] == URL
    for body in (resp.text, client.get("/api/dataviz/notify").text):
        assert URL not in body and "abcdefghijklmnop" not in body
    assert client.get("/api/dataviz/notify").json() == {"configured": True, "hint": "…ABCDEF"}
    assert client.post("/api/dataviz/notify", json={"url": ""}).json()["configured"] is False
    assert notify.SECRET_KEY not in secrets


def test_the_test_button_goes_to_the_receiver_only(secrets, monkeypatch):
    receiver = FakeReceiver()
    original = notify.send
    monkeypatch.setattr(notify, "send", lambda url, text, post=None: original(url, text, post=receiver))
    assert client.post("/api/dataviz/notify/test", json={}).status_code == 400            # אין כתובת
    secrets[notify.SECRET_KEY] = URL
    assert client.post("/api/dataviz/notify/test", json={}).json() == {"ok": True}
    assert receiver.calls[0][0] == URL and "בדיקה" in receiver.calls[0][1]["content"]
    receiver.status = 404
    assert client.post("/api/dataviz/notify/test", json={}).status_code == 502


def test_without_a_receiver_nothing_is_sent_from_a_test():
    assert os.environ.get("PYTEST_CURRENT_TEST")
    assert notify.send(URL, "x") is False


def test_the_maker_reports_done_and_failed_with_the_episodes(secrets):
    spec = importlib.util.spec_from_file_location("dataviz_maker_notify", os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py"))
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    receiver = FakeReceiver()
    assert maker.notify_finished({"files_created": 1, "errors": 0}, ["/d/tiny"], "full", 75, post=receiver) is False   # לא מוגדר
    assert receiver.calls == []
    secrets[notify.SECRET_KEY] = URL
    assert maker.notify_finished({"files_created": 1, "errors": 0}, ["/d/tiny"], "full", 75, post=receiver) is True
    assert maker.notify_finished({"files_created": 0, "errors": 2, "skipped": 1}, ["/d/a", "/d/b"], "test", 12, post=receiver) is True
    done, failed = (call[1]["content"] for call in receiver.calls)
    assert done.startswith("✅") and "tiny" in done and "(full)" in done and "1.2 דקות" in done
    assert failed.startswith("❌") and "a, b" in failed and "שגיאות: 2" in failed and "דולגו: 1" in failed
