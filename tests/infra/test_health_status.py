# tests/infra/test_health_status.py


from utils.shared.health_status import format_duration


def test_format_duration_minutes_only():
    assert format_duration(90) == "1ד"


def test_format_duration_under_a_minute_shows_seconds():
    # סבב ייצוב: בדקה האחרונה ההתקדמות הראתה "נותרו כ-0ד"
    assert format_duration(0) == "0שנ׳"
    assert format_duration(45.7) == "45שנ׳"
    assert format_duration(59) == "59שנ׳"
    assert format_duration(60) == "1ד"
    assert format_duration(3600) == "1ש"


def test_format_duration_hours_and_minutes():
    assert format_duration(3 * 3600 + 14 * 60) == "3ש 14ד"


def test_format_duration_days_hours_minutes():
    assert format_duration(2 * 86400 + 3 * 3600 + 14 * 60) == "2י 3ש 14ד"


def test_format_duration_exact_days_omits_zero_parts():
    assert format_duration(2 * 86400) == "2י"


def test_format_duration_negative_clamped_to_zero():
    assert format_duration(-50) == "0שנ׳"
