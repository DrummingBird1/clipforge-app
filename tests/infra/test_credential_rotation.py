# tests/infra/test_credential_rotation.py
#
# item: מעקב "גיל מפתח" - utils/shared/credential_rotation.py, קובץ JSON מקומי
# בלבד, בלי שום תלות ב-keyring/רשת.
from datetime import datetime, timedelta, timezone


import pytest

from utils.shared import credential_rotation as cr


@pytest.fixture(autouse=True)
def _isolate_rotation_path(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "ROTATION_LOG_PATH", str(tmp_path / "credential_rotation.json"))


def test_get_rotation_date_returns_none_when_never_recorded():
    assert cr.get_rotation_date("GEMINI_API_KEY") is None


def test_get_age_days_returns_none_when_never_recorded():
    assert cr.get_age_days("GEMINI_API_KEY") is None


def test_is_stale_false_when_never_recorded():
    # "לא ידוע" אינו "ישן" - אין ראיה לסמן זאת כאזהרה.
    assert cr.is_stale("GEMINI_API_KEY") is False


def test_record_rotation_then_get_age_days_is_zero_right_after():
    cr.record_rotation("GEMINI_API_KEY")
    assert cr.get_age_days("GEMINI_API_KEY") == 0


def test_record_rotation_overwrites_previous_timestamp():
    cr.record_rotation("GEMINI_API_KEY")
    first = cr.get_rotation_date("GEMINI_API_KEY")
    cr.record_rotation("GEMINI_API_KEY")
    second = cr.get_rotation_date("GEMINI_API_KEY")
    assert second >= first


def test_is_stale_true_when_older_than_threshold():
    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    with open(cr.ROTATION_LOG_PATH, "w", encoding="utf-8") as f:
        import json
        json.dump({"GEMINI_API_KEY": old_timestamp}, f)
    assert cr.get_age_days("GEMINI_API_KEY") == 120
    assert cr.is_stale("GEMINI_API_KEY", stale_after_days=90) is True


def test_is_stale_false_when_younger_than_threshold():
    recent_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    with open(cr.ROTATION_LOG_PATH, "w", encoding="utf-8") as f:
        import json
        json.dump({"GEMINI_API_KEY": recent_timestamp}, f)
    assert cr.is_stale("GEMINI_API_KEY", stale_after_days=90) is False


def test_multiple_keys_tracked_independently():
    cr.record_rotation("GEMINI_API_KEY")
    assert cr.get_rotation_date("DISCORD_TOKEN") is None
    assert cr.get_rotation_date("GEMINI_API_KEY") is not None


def test_get_rotation_date_returns_none_on_corrupt_json():
    with open(cr.ROTATION_LOG_PATH, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    assert cr.get_rotation_date("GEMINI_API_KEY") is None
