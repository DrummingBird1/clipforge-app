# tests/web/test_web_app_device_pairing.py
#
# 22.10.2026: צימוד מכשיר (routes/devices.py, ה-middleware ב-web_app.py). טלפון / ZimaOS מקבלים טוקן משלהם שנשאר
# אחרי שטוקן המחשב מתחלף (הפעלה מחדש), ביטול מנתק אותם מיד (HTTP ו-WebSocket), וצימוד / רשימה / ביטול / החלפת טוקן -
# רק מהמחשב עצמו (טוקן המחשב + 127.0.0.1). "הטלפון" הוא TestClient מכתובת Tailscale; המאגר בתיקייה זמנית.
import threading

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from entrypoints import web_app
from entrypoints.web_app import app
from utils.shared import device_pairing

web_app.limiter.enabled = False
PHONE_IP = "100.70.0.5"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    devices = device_pairing.DeviceStore(str(tmp_path / "paired_devices.json"))
    monkeypatch.setattr(web_app, "device_store", devices)
    monkeypatch.setattr(web_app, "TAILSCALE_BASE_URL", "http://my-pc.tail1234ab.ts.net:8878")
    monkeypatch.setattr(web_app, "_WS_REVOKE_CHECK_SECONDS", 0.05)
    return devices


def _computer():
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
    return client


def _phone():
    return TestClient(app, client=(PHONE_IP, 50000))


def _new_code(name="טלפון"):
    resp = _computer().post("/api/devices/pair", json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _paired_phone(name="טלפון"):
    phone = _phone()
    resp = phone.post("/pair", data={"code": _new_code(name)["code"]}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/?screen=phone"
    return phone


def test_a_paired_phone_keeps_access_after_the_computer_token_changes(monkeypatch):
    phone = _paired_phone()
    assert phone.get("/api/scripts").status_code == 200
    old_computer = _computer()
    monkeypatch.setattr(web_app, "ACCESS_TOKEN", "a-new-token-after-a-restart")   # כמו הפעלה מחדש של השרת
    assert phone.get("/api/scripts").status_code == 200
    assert old_computer.get("/api/scripts").status_code == 401


def test_the_cookie_is_long_lived_http_only_and_the_token_is_not_stored(store):
    phone = _phone()
    resp = phone.post("/pair", data={"code": _new_code()["code"]}, follow_redirects=False)
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(device_pairing.COOKIE_NAME + "=") and "HttpOnly" in cookie
    assert f"Max-Age={device_pairing.COOKIE_MAX_AGE_SECONDS}" in cookie
    token = phone.cookies.get(device_pairing.COOKIE_NAME)
    with open(store.path, encoding="utf-8") as f:
        assert token not in f.read()
    assert store.list_devices()[0]["last_ip"] == PHONE_IP


def test_opening_the_pair_page_does_not_use_up_the_code():
    code = _new_code("<b>ZimaOS</b>")["code"]
    phone = _phone()
    for _ in range(2):   # סורק QR / תצוגה מקדימה שפותחים את הקישור לפני הדפדפן
        page = phone.get("/pair", params={"code": code})
        assert page.status_code == 200 and "&lt;b&gt;ZimaOS&lt;/b&gt;" in page.text and "<b>ZimaOS</b>" not in page.text
        assert page.headers["cache-control"] == "no-store"
    assert phone.post("/pair", data={"code": code}, follow_redirects=False).status_code == 303


def test_a_code_works_once_and_a_wrong_code_gets_nothing():
    code = _new_code()["code"]
    assert _phone().post("/pair", data={"code": code}, follow_redirects=False).status_code == 303
    second = _phone()
    used = second.post("/pair", data={"code": code}, follow_redirects=False)
    assert used.status_code == 400 and device_pairing.COOKIE_NAME not in second.cookies
    assert second.get("/api/scripts").status_code == 401
    assert _phone().get("/pair", params={"code": "made-up"}).status_code == 400
    assert _phone().post("/api/pair/token", json={"code": "made-up"}).status_code == 400


def test_a_script_gets_its_token_once_and_uses_it_as_bearer():
    resp = _phone().post("/api/pair/token", json={"code": _new_code("ZimaOS")["code"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["device"]["kind"] == "script" and body["device"]["name"] == "ZimaOS"
    script = _phone()
    assert script.get("/api/scripts", headers={"Authorization": "Bearer " + body["token"]}).status_code == 200
    assert script.get("/api/scripts", params={"token": body["token"]}).status_code == 401   # טוקן מכשיר לא בכתובת


def test_unpairing_cuts_off_http_right_away():
    phone = _paired_phone()
    device_id = _computer().get("/api/devices").json()["devices"][0]["id"]
    resp = _computer().post("/api/devices/revoke", json={"id": device_id})
    assert resp.status_code == 200 and resp.json()["devices"] == []
    blocked = phone.get("/api/scripts")
    assert blocked.status_code == 401 and "צמד אותו מחדש" in blocked.json()["error"]
    assert _computer().post("/api/devices/revoke", json={"id": device_id}).status_code == 404


def _close_code(ws, timeout=10):
    """קורא הודעות עד שהשרת סוגר; None אם לא נסגר בזמן (ב-thread - receive לא יודע timeout)."""
    result = {}

    def run():
        try:
            while True:
                ws.receive_json()
        except WebSocketDisconnect as e:
            result["code"] = e.code

    reader = threading.Thread(target=run, daemon=True)
    reader.start()
    reader.join(timeout)
    return result.get("code")


def test_unpairing_closes_an_open_websocket_and_a_new_one_is_refused():
    web_app._LOG_REPLAY_BUFFER.clear()
    phone = _paired_phone()
    with phone.websocket_connect("/ws") as ws:
        _computer().post("/api/devices/revoke_all")
        assert _close_code(ws) == 4401
    with pytest.raises(WebSocketDisconnect) as refused:
        with phone.websocket_connect("/ws") as ws:
            ws.receive_json()
    assert refused.value.code == 4401


@pytest.fixture
def bot_log(monkeypatch):
    """שורה אחת בבאפר של לוג הבוט - /ws/bot שולח אותה מיד אחרי accept, אז חיבור שהתקבל מקבל log_batch."""
    monkeypatch.setattr(web_app, "_bot_log_buffer", web_app.collections.deque(["bot started\n"], maxlen=500))
    while not web_app._bot_log_queue.empty():
        web_app._bot_log_queue.get_nowait()


def _first_bot_message(client, **kwargs):
    with client.websocket_connect("/ws/bot", **kwargs) as ws:
        return ws.receive_json()


def test_the_bot_log_websocket_takes_the_computer_token_and_a_paired_device(bot_log):
    expected = {"type": "log_batch", "lines": [{"line": "bot started\n"}]}
    assert _first_bot_message(_computer()) == expected                                        # עוגיית המחשב
    assert _first_bot_message(_phone(), params={"token": web_app.ACCESS_TOKEN}) == expected   # ?token= של המחשב
    assert _first_bot_message(_paired_phone()) == expected                                    # עוגיית המכשיר


def test_the_bot_log_websocket_refuses_a_wrong_or_unpaired_token(bot_log):
    stranger = _phone()
    stranger.cookies.set("web_app_token", "not-the-token")
    with pytest.raises(WebSocketDisconnect) as wrong:
        _first_bot_message(stranger)
    assert wrong.value.code == 4401

    phone = _paired_phone()
    _computer().post("/api/devices/revoke_all")
    with pytest.raises(WebSocketDisconnect) as unpaired:
        _first_bot_message(phone)
    assert unpaired.value.code == 4401


def test_unpairing_closes_an_open_bot_log_websocket(bot_log):
    phone = _paired_phone()
    with phone.websocket_connect("/ws/bot") as ws:
        assert ws.receive_json()["type"] == "log_batch"
        _computer().post("/api/devices/revoke_all")
        assert _close_code(ws) == 4401


def test_pairing_and_device_management_only_from_this_computer():
    phone = _paired_phone()
    for resp in (phone.get("/api/devices"), phone.post("/api/devices/pair", json={"name": "x"}),
                 phone.post("/api/devices/revoke_all"), phone.post("/api/rotate_token")):
        assert resp.status_code == 403

    # גם טלפון שנכנס עם קישור טוקן המחשב דרך Tailscale - לא מהמחשב עצמו
    with_computer_token = _phone()
    with_computer_token.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
    assert with_computer_token.get("/api/scripts").status_code == 200
    assert with_computer_token.get("/api/devices").status_code == 403
    assert with_computer_token.post("/api/rotate_token").status_code == 403
    assert _computer().get("/api/devices").json()["devices"][0]["name"] == "טלפון"


def test_the_page_learns_whether_it_may_offer_token_rotation(monkeypatch):
    # הדף מסתיר את "🔑 החלף טוקן" לפי השדה הזה (checkForUpdate ב-20-app-shell.js)
    monkeypatch.setattr(web_app, "check_for_update", lambda *_a, **_k: None)
    assert _computer().get("/api/update_check").json()["can_rotate_token"] is True
    assert _paired_phone().get("/api/update_check").json()["can_rotate_token"] is False
    with_computer_token = _phone()
    with_computer_token.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
    assert with_computer_token.get("/api/update_check").json()["can_rotate_token"] is False


def test_a_paired_device_never_receives_the_computer_token():
    phone = _paired_phone()
    assert phone.get("/api/access_token").status_code == 403
    assert phone.get("/api/remote_access").json()["token_url"] is None
    assert web_app.ACCESS_TOKEN in _computer().get("/api/remote_access").json()["token_url"]
    assert _computer().get("/api/access_token").json()["token"] == web_app.ACCESS_TOKEN


def test_the_computer_sees_when_the_phone_paired():
    created = _new_code("טלפון")
    assert created["url"] == f"{web_app.TAILSCALE_BASE_URL}/pair?code={created['code']}"
    status = lambda: _computer().get("/api/devices/pair/status", params={"code": created["code"]}).json()   # noqa: E731
    assert status()["state"] == "pending"
    _phone().post("/pair", data={"code": created["code"]}, follow_redirects=False)
    assert status()["state"] == "paired" and status()["device"]["name"] == "טלפון"


def test_pairing_needs_an_address_another_device_can_reach(monkeypatch):
    monkeypatch.setattr(web_app, "TAILSCALE_BASE_URL", None)
    monkeypatch.setattr(web_app, "LAN_BASE_URL", None)
    assert _computer().post("/api/devices/pair", json={"name": "טלפון"}).status_code == 409


def test_the_expiry_setting_is_saved(store):
    assert _computer().get("/api/devices").json()["expire_unused"] is True
    assert _computer().post("/api/devices/settings", json={"expire_unused": False}).json()["expire_unused"] is False
    assert store.expire_unused is False


def test_a_foreign_origin_cannot_pair_or_unpair():
    foreign = {"Origin": "http://evil.example", "Host": "127.0.0.1:8878"}
    assert _computer().post("/api/devices/pair", json={"name": "x"}, headers=foreign).status_code == 403
    assert _computer().post("/api/devices/revoke_all", headers=foreign).status_code == 403
    code = _new_code()["code"]
    assert _phone().post("/pair", data={"code": code}, headers=foreign, follow_redirects=False).status_code == 403
