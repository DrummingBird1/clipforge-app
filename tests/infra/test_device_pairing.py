# tests/infra/test_device_pairing.py
#
# 22.10.2026: מאגר המכשירים המצומדים (utils/shared/device_pairing.py) - קוד חד-פעמי לחמש דקות, רק hash בקובץ,
# ביטול, ותפוגה אחרי 90 יום בלי שימוש. שעון מזויף, קובץ בתיקייה זמנית.
import json

import pytest

from utils.shared import device_pairing as dp


class FakeClock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def store(tmp_path):
    clock = FakeClock()
    s = dp.DeviceStore(str(tmp_path / "paired_devices.json"), clock=clock)
    s.test_clock = clock
    return s


def test_a_code_pairs_one_device_once_and_only_the_hash_is_stored(store, tmp_path):
    code = store.create_code("  הטלפון   בסלון ")["code"]
    assert store.peek_code(code) == "הטלפון בסלון"
    token, device = store.redeem(code, kind="browser", ip="100.70.0.5")
    assert device["name"] == "הטלפון בסלון" and device["kind"] == "browser" and device["last_ip"] == "100.70.0.5"
    assert store.verify(token) == device["id"]

    with pytest.raises(dp.PairingError):
        store.redeem(code)   # חד-פעמי
    assert store.peek_code(code) is None

    saved = (tmp_path / "paired_devices.json").read_text(encoding="utf-8")
    assert token not in saved and dp.token_hash(token) in saved
    assert "token_sha256" not in json.dumps(store.list_devices())


def test_a_code_expires_after_five_minutes(store):
    code = store.create_code("ZimaOS")["code"]
    store.test_clock.now += dp.CODE_TTL_SECONDS + 1
    assert store.peek_code(code) is None and store.code_state(code) == ("expired", None)
    with pytest.raises(dp.PairingError):
        store.redeem(code)


def test_code_state_tells_the_computer_when_the_device_paired(store):
    code = store.create_code("טלפון")["code"]
    assert store.code_state(code) == ("pending", None)
    _, device = store.redeem(code, kind="script")
    state, paired = store.code_state(code)
    assert state == "paired" and paired["id"] == device["id"] and paired["kind"] == "script"


def test_the_token_survives_a_new_store_on_the_same_file(store, tmp_path):
    token, device = store.redeem(store.create_code("טלפון")["code"])
    restarted = dp.DeviceStore(str(tmp_path / "paired_devices.json"), clock=store.test_clock)
    assert restarted.verify(token) == device["id"]
    assert restarted.verify("not-a-token") is None and restarted.verify("") is None and restarted.verify(None) is None


def test_revoke_one_and_revoke_all(store):
    token_a, a = store.redeem(store.create_code("א")["code"])
    token_b, b = store.redeem(store.create_code("ב")["code"])
    assert store.revoke(a["id"]) is True and store.revoke(a["id"]) is False
    assert store.verify(token_a) is None and not store.is_active(a["id"])
    assert store.verify(token_b) == b["id"] and store.is_active(b["id"])
    assert store.revoke_all() == 1
    assert store.verify(token_b) is None and store.list_devices() == []


def test_a_device_unused_for_90_days_expires_unless_turned_off(store):
    token, device = store.redeem(store.create_code("טלפון")["code"])
    store.test_clock.now += 89 * 24 * 3600
    assert store.verify(token) == device["id"]   # שימוש מאפס את הספירה
    store.test_clock.now += 89 * 24 * 3600
    assert store.verify(token) == device["id"]

    store.set_expire_unused(False)
    store.test_clock.now += 200 * 24 * 3600
    assert store.verify(token) == device["id"]

    store.set_expire_unused(True)
    store.test_clock.now += 91 * 24 * 3600
    assert store.verify(token) is None and store.list_devices() == []


def test_last_seen_reaches_the_file_at_most_every_ten_minutes(store, tmp_path):
    token, device = store.redeem(store.create_code("טלפון")["code"])
    path = tmp_path / "paired_devices.json"

    def saved_last_seen():
        return json.loads(path.read_text(encoding="utf-8"))["devices"][0]["last_seen"]

    first = saved_last_seen()
    store.test_clock.now += 60
    store.verify(token, ip="100.70.0.9")
    assert saved_last_seen() == first                      # דקה - רק בזיכרון
    assert store.list_devices()[0]["last_ip"] == "100.70.0.9"
    store.test_clock.now += dp.SEEN_WRITE_INTERVAL_SECONDS
    store.verify(token)
    assert saved_last_seen() == store.test_clock.now


def test_a_corrupt_file_means_no_devices(tmp_path):
    path = tmp_path / "paired_devices.json"
    path.write_text("{not json", encoding="utf-8")
    store = dp.DeviceStore(str(path))
    assert store.list_devices() == [] and store.verify("anything") is None


def test_limits_on_devices_and_pending_codes(store, monkeypatch):
    monkeypatch.setattr(dp, "MAX_DEVICES", 2)
    store.redeem(store.create_code("א")["code"])
    late_code = store.create_code("ב")["code"]
    store.redeem(store.create_code("ג")["code"])
    with pytest.raises(dp.PairingError):
        store.create_code("ד")
    with pytest.raises(dp.PairingError):
        store.redeem(late_code)

    store.revoke_all()
    codes = [store.create_code(str(i))["code"] for i in range(dp.MAX_PENDING_CODES + 3)]
    assert store.peek_code(codes[0]) is None and store.peek_code(codes[-1]) == str(dp.MAX_PENDING_CODES + 2)
    assert sum(store.peek_code(c) is not None for c in codes) == dp.MAX_PENDING_CODES


def test_names_are_trimmed_and_get_a_default(monkeypatch):
    from utils.shared import ui_language
    monkeypatch.setattr(ui_language, "current", lambda: "he")
    assert dp.clean_name("") == "מכשיר" and dp.clean_name(None) == "מכשיר"
    monkeypatch.setattr(ui_language, "current", lambda: "en")   # 30.10.2026: בשפת ההתקנה
    assert dp.clean_name("") == "Device"
    assert dp.clean_name("x" * 100) == "x" * dp.NAME_MAX_LENGTH
    assert dp.clean_name("a\n\tb") == "a b"
