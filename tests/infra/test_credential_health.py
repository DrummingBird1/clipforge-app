# tests/infra/test_credential_health.py
#
# בודק utils/shared/credential_health.py (item: credential vault health-check) - לא
# קורא לשום API אמיתי (Gemini/Twitch/Discord) - כל קריאת רשת ממופתחת, כדי
# שהטסטים יהיו מהירים, דטרמיניסטיים, ולא תלויים במפתחות אמיתיים/רשת.


import pytest

import utils.shared.credential_health as credential_health
from utils.shared import credential_rotation as cr


@pytest.fixture(autouse=True)
def _isolate_rotation_path(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "ROTATION_LOG_PATH", str(tmp_path / "credential_rotation.json"))


def _fake_response(status_code, text=""):
    return type("FakeResponse", (), {"status_code": status_code, "text": text})()


# --- check_configured (no network at all) ---

def test_check_configured_reports_all_present(monkeypatch):
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "some-value")
    result = credential_health.check_configured()
    assert all(result.values())
    assert set(result.keys()) == set(credential_health.CREDENTIAL_NAMES)


def test_check_configured_reports_missing_as_false(monkeypatch):
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "")
    result = credential_health.check_configured()
    assert not any(result.values())


def test_check_configured_per_key(monkeypatch):
    values = {"GEMINI_API_KEY": "abc", "TWITCH_CLIENT_ID": "", "TWITCH_CLIENT_SECRET": "", "DISCORD_TOKEN": "xyz"}
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": values.get(key, ""))
    result = credential_health.check_configured()
    assert result == {"GEMINI_API_KEY": True, "TWITCH_CLIENT_ID": False, "TWITCH_CLIENT_SECRET": False, "DISCORD_TOKEN": True}


# --- check_validity (network calls mocked) ---

def test_check_validity_reports_not_configured_without_calling_network(monkeypatch):
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "")
    monkeypatch.setattr(credential_health, "_validate_gemini", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))
    monkeypatch.setattr(credential_health, "_validate_twitch", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))
    monkeypatch.setattr(credential_health, "_validate_discord", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))

    results = credential_health.check_validity()

    for _name, configured, valid, _detail in results:
        assert configured is False
        assert valid is None


def test_check_validity_calls_validators_only_when_configured(monkeypatch):
    values = {"GEMINI_API_KEY": "key1", "TWITCH_CLIENT_ID": "", "TWITCH_CLIENT_SECRET": "", "DISCORD_TOKEN": "tok"}
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": values.get(key, ""))
    monkeypatch.setattr(credential_health, "_validate_gemini", lambda key: (True, "ok"))
    monkeypatch.setattr(credential_health, "_validate_twitch", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))
    monkeypatch.setattr(credential_health, "_validate_discord", lambda token: (False, "401"))

    results = {name: (configured, valid, detail) for name, configured, valid, detail in credential_health.check_validity()}

    assert results["GEMINI_API_KEY"] == (True, True, "ok")
    assert results["TWITCH_CLIENT_ID/SECRET"] == (False, None, "לא מוגדר")
    assert results["DISCORD_TOKEN"] == (True, False, "401")


def test_validate_gemini_success(monkeypatch):
    class _FakeModels:
        def list(self):
            return iter(["model-a"])

    class _FakeClient:
        def __init__(self, api_key):
            self.models = _FakeModels()

    fake_genai_module = type("FakeGenaiModule", (), {"Client": _FakeClient})()
    import sys as _sys
    monkeypatch.setitem(_sys.modules, "google", type("FakeGoogleModule", (), {"genai": fake_genai_module})())
    monkeypatch.setitem(_sys.modules, "google.genai", fake_genai_module)

    valid, detail = credential_health._validate_gemini("fake-key")
    assert valid is True
    assert detail == "תקין"


def test_validate_gemini_failure(monkeypatch):
    class _FakeClient:
        def __init__(self, api_key):
            raise RuntimeError("invalid API key")

    fake_genai_module = type("FakeGenaiModule", (), {"Client": _FakeClient})()
    import sys as _sys
    monkeypatch.setitem(_sys.modules, "google", type("FakeGoogleModule", (), {"genai": fake_genai_module})())
    monkeypatch.setitem(_sys.modules, "google.genai", fake_genai_module)

    valid, detail = credential_health._validate_gemini("fake-key")
    assert valid is False
    assert "invalid API key" in detail


def test_validate_twitch_success(monkeypatch):
    monkeypatch.setattr(credential_health.requests, "post", lambda *a, **kw: _fake_response(200))
    valid, detail = credential_health._validate_twitch("id", "secret")
    assert valid is True
    assert detail == "תקין"


def test_validate_twitch_failure(monkeypatch):
    monkeypatch.setattr(credential_health.requests, "post", lambda *a, **kw: _fake_response(401, "invalid client"))
    valid, detail = credential_health._validate_twitch("id", "secret")
    assert valid is False
    assert "401" in detail


def test_validate_twitch_handles_network_error(monkeypatch):
    def _raise(*a, **kw):
        raise ConnectionError("no internet")
    monkeypatch.setattr(credential_health.requests, "post", _raise)
    valid, detail = credential_health._validate_twitch("id", "secret")
    assert valid is False
    assert "no internet" in detail


def test_validate_discord_success(monkeypatch):
    monkeypatch.setattr(credential_health.requests, "get", lambda *a, **kw: _fake_response(200))
    valid, detail = credential_health._validate_discord("token")
    assert valid is True


def test_validate_discord_failure(monkeypatch):
    monkeypatch.setattr(credential_health.requests, "get", lambda *a, **kw: _fake_response(401, "Unauthorized"))
    valid, detail = credential_health._validate_discord("token")
    assert valid is False
    assert "401" in detail


# --- get_rotation_status (item: key-age tracking, no network at all) ---

def test_get_rotation_status_not_configured_has_none_age(monkeypatch):
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "")
    results = {name: (configured, age, stale) for name, configured, age, stale in credential_health.get_rotation_status()}
    for configured, age, stale in results.values():
        assert configured is False
        assert age is None
        assert stale is False


def test_get_rotation_status_configured_but_never_rotated_has_none_age(monkeypatch):
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "some-value")
    results = {name: (configured, age, stale) for name, configured, age, stale in credential_health.get_rotation_status()}
    for configured, age, stale in results.values():
        assert configured is True
        assert age is None  # מוגדר, אבל לא דרך set_secret אף פעם - גיל לא ידוע
        assert stale is False


def test_get_rotation_status_reports_real_age_after_rotation(monkeypatch):
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "some-value")
    cr.record_rotation("GEMINI_API_KEY")
    results = {name: (configured, age, stale) for name, configured, age, stale in credential_health.get_rotation_status()}
    assert results["GEMINI_API_KEY"] == (True, 0, False)


def test_get_rotation_status_flags_stale_key_past_threshold(monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(credential_health, "get_secret", lambda key, default="": "some-value")
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    with open(cr.ROTATION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"GEMINI_API_KEY": old_timestamp}, f)

    results = {name: (configured, age, stale) for name, configured, age, stale in credential_health.get_rotation_status(stale_after_days=90)}

    assert results["GEMINI_API_KEY"] == (True, 200, True)
