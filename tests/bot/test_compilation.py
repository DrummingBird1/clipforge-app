# tests/bot/test_compilation.py
import datetime


from utils.media.compilation import (
    build_chapters_text,
    format_chapter_timestamp,
    recap_label_for_period,
    resolve_period_days,
    should_run_recap_today,
)


def test_resolve_period_days_week():
    assert resolve_period_days("week") == 7


def test_resolve_period_days_month():
    assert resolve_period_days("month") == 30


def test_resolve_period_days_year():
    assert resolve_period_days("year") == 365


def test_resolve_period_days_unknown_period_falls_back_to_week():
    assert resolve_period_days("fortnight") == 7


def test_resolve_period_days_explicit_days_overrides_period():
    assert resolve_period_days("month", explicit_days=3) == 3


def test_recap_label_for_period():
    assert recap_label_for_period("week") == "Weekly"
    assert recap_label_for_period("month") == "Monthly"
    assert recap_label_for_period("year") == "Yearly"


def test_recap_label_for_unknown_period_falls_back_to_weekly():
    assert recap_label_for_period("fortnight") == "Weekly"


def test_format_chapter_timestamp_under_an_hour():
    assert format_chapter_timestamp(0) == "0:00"
    assert format_chapter_timestamp(83) == "1:23"
    assert format_chapter_timestamp(3599) == "59:59"


def test_format_chapter_timestamp_an_hour_or_more():
    assert format_chapter_timestamp(3600) == "1:00:00"
    assert format_chapter_timestamp(3725) == "1:02:05"


def test_build_chapters_text_starts_at_zero_and_accumulates():
    text = build_chapters_text([("clip_a.mp4", 30.0), ("clip_b.mp4", 45.5), ("clip_c.mp4", 10.0)])
    assert text == "0:00 clip_a.mp4\n0:30 clip_b.mp4\n1:15 clip_c.mp4"


def test_build_chapters_text_empty_list_returns_empty_string():
    assert build_chapters_text([]) == ""


def test_should_run_recap_today_week_matches_selected_weekday():
    sunday = datetime.date(2026, 9, 13)  # weekday() == 6
    assert should_run_recap_today("week", recap_weekday=6, today=sunday) is True
    assert should_run_recap_today("week", recap_weekday=0, today=sunday) is False


def test_should_run_recap_today_month_only_on_the_first():
    assert should_run_recap_today("month", recap_weekday=6, today=datetime.date(2026, 9, 1)) is True
    assert should_run_recap_today("month", recap_weekday=6, today=datetime.date(2026, 9, 2)) is False


def test_should_run_recap_today_year_only_on_january_first():
    assert should_run_recap_today("year", recap_weekday=6, today=datetime.date(2026, 1, 1)) is True
    assert should_run_recap_today("year", recap_weekday=6, today=datetime.date(2026, 2, 1)) is False
    assert should_run_recap_today("year", recap_weekday=6, today=datetime.date(2025, 1, 1)) is True


def test_should_run_recap_today_unknown_period_falls_back_to_week_behavior():
    sunday = datetime.date(2026, 9, 13)
    assert should_run_recap_today("fortnight", recap_weekday=6, today=sunday) is True
