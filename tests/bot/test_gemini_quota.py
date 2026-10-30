# tests/bot/test_gemini_quota.py
#
# utils/media/gemini_quota.py - אזהרות מכסת Gemini בריצת story_cutter במקום אישור אוטומטי שקט:
# זיהוי שגיאת מכסה, אזהרה מוקדמת ב-80% מהתקרה, אזהרה אחת כשנגמרה, ספירת קליפים שאושרו בלי שיפוט.
from utils.media.gemini_quota import MAX_CONSECUTIVE_QUOTA_FAILURES, QuotaWatch, is_quota_error, is_unjudged_reason, messages
from utils.media.local_vision_judge import judge_clip_locally


def test_quota_errors_are_recognised_but_overload_and_auth_are_not():
    assert is_quota_error("429 RESOURCE_EXHAUSTED. You exceeded your current quota")
    assert is_quota_error(RuntimeError("Quota exceeded for metric generate_content_free_tier_requests"))
    assert not is_quota_error("503 UNAVAILABLE: model overloaded")
    assert not is_quota_error("400 API key not valid")


def test_unjudged_marker_matches_what_the_local_judge_really_returns(tmp_path):
    # אין פריימים קריאים -> אישור כברירת מחדל; הסימן חייב להתאים לנוסח האמיתי של המודול
    approved, _game, reason = judge_clip_locally([str(tmp_path / "missing.jpg")])
    assert approved is True and is_unjudged_reason(reason)
    assert not is_unjudged_reason("(local:llava) שחקן מנצח בקרב")
    assert not is_unjudged_reason("חיתוך סאונד בלבד (AI כבוי)")


def test_exhaustion_warns_once_and_says_what_happens_without_ollama():
    watch = QuotaWatch(local_judge_available=False)
    watch.gemini_called()

    first = watch.gemini_failed("429 RESOURCE_EXHAUSTED")
    again = watch.gemini_failed("429 RESOURCE_EXHAUSTED")

    assert first and "בלי שיפוט" in first and "[WARNING]" in first
    assert again is None and watch.quota_errors == 2
    assert watch.gemini_failed("503 overloaded") is None


def test_exhaustion_message_mentions_ollama_when_available():
    watch = QuotaWatch(local_judge_available=True)
    assert "Ollama המקומי" in watch.gemini_failed("429 quota")


def test_early_warning_at_eighty_percent_of_the_configured_limit_once():
    watch = QuotaWatch(daily_limit=10)
    warnings = [watch.gemini_called() for _ in range(10)]

    assert [i + 1 for i, w in enumerate(warnings) if w] == [8]
    assert "80%" in warnings[7]
    assert QuotaWatch().gemini_called() is None                    # בלי תקרה - בלי אזהרה מוקדמת


def test_unjudged_verdicts_are_counted_and_summarised():
    watch = QuotaWatch()
    assert watch.summary() is None
    assert watch.verdict("(gemini) מעניין") is None
    assert "(סה\"כ 1)" in watch.verdict("שיפוט מקומי נכשל (x) - מאשר כברירת מחדל")
    watch.verdict("לא ניתן... (מאשר כברירת מחדל)")

    assert "2 קליפים אושרו בלי שיפוט" in watch.summary()
    assert messages(None, "a", None, "b") == ["a", "b"]

def test_breaker_opens_after_consecutive_quota_failures_and_skips_calls():
    now = [1000.0]
    watch = QuotaWatch(clock=lambda: now[0])
    for _ in range(MAX_CONSECUTIVE_QUOTA_FAILURES - 1):
        watch.gemini_failed("429 RESOURCE_EXHAUSTED")
        assert not watch.tripped and not watch.should_skip_gemini()
    watch.gemini_failed("429 RESOURCE_EXHAUSTED")
    assert watch.tripped and watch.should_skip_gemini() and watch.should_skip_gemini()
    assert watch.skipped_calls == 2


def test_breaker_ignores_non_quota_errors_and_resets_on_success():
    watch = QuotaWatch()
    for _ in range(10):
        watch.gemini_failed("500 internal error")
    assert not watch.tripped
    watch.gemini_failed("429")
    watch.gemini_failed("429")
    watch.gemini_succeeded()
    watch.gemini_failed("429")
    assert watch.consecutive_quota_failures == 1 and not watch.tripped


def test_breaker_tries_once_after_cooldown_and_reopens_on_one_more_failure():
    now = [0.0]
    watch = QuotaWatch(cooldown=60, clock=lambda: now[0])
    for _ in range(MAX_CONSECUTIVE_QUOTA_FAILURES):
        watch.gemini_failed("429")
    now[0] = 59
    assert watch.should_skip_gemini()
    now[0] = 61
    assert watch.should_skip_gemini() is False          # קריאת ניסיון אחת
    watch.gemini_failed("429")
    assert watch.tripped and watch.should_skip_gemini()  # כשל אחד מספיק כדי לפתוח שוב
    now[0] = 130
    assert watch.should_skip_gemini() is False
    watch.gemini_succeeded()
    assert not watch.tripped and not watch.should_skip_gemini()
