# tests/infra/test_retry.py
import asyncio


import pytest

from utils.shared.retry import call_with_retry, call_with_retry_async, compute_backoff_delay


def test_compute_backoff_delay_grows_exponentially():
    assert compute_backoff_delay(0, base_delay=1.0, factor=2.0) == 1.0
    assert compute_backoff_delay(1, base_delay=1.0, factor=2.0) == 2.0
    assert compute_backoff_delay(2, base_delay=1.0, factor=2.0) == 4.0


def test_compute_backoff_delay_capped_at_max():
    assert compute_backoff_delay(10, base_delay=1.0, factor=2.0, max_delay=30.0) == 30.0


def test_call_with_retry_succeeds_first_try():
    calls = []

    def func():
        calls.append(1)
        return "ok"

    result = call_with_retry(func, sleep_func=lambda d: None)
    assert result == "ok"
    assert len(calls) == 1


def test_call_with_retry_succeeds_after_failures():
    attempts = {"n": 0}

    def func():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("temporary")
        return "ok"

    sleeps = []
    result = call_with_retry(func, max_attempts=5, sleep_func=sleeps.append)
    assert result == "ok"
    assert attempts["n"] == 3
    assert len(sleeps) == 2  # שני כשלים -> שתי המתנות בין ניסיונות


def test_call_with_retry_raises_after_exhausting_attempts():
    def func():
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        call_with_retry(func, max_attempts=3, sleep_func=lambda d: None)


def test_call_with_retry_non_retryable_raises_immediately():
    calls = []

    def func():
        calls.append(1)
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        call_with_retry(func, max_attempts=5, is_retryable=lambda e: False, sleep_func=lambda d: None)
    assert len(calls) == 1


def test_call_with_retry_passes_attempt_and_delay_to_on_retry():
    seen = []

    def func():
        if len(seen) < 2:
            seen.append(1)
            raise ConnectionError("temp")
        return "ok"

    recorded = []
    call_with_retry(func, max_attempts=5, base_delay=2.0, factor=2.0, sleep_func=lambda d: None, on_retry=lambda attempt, delay, e: recorded.append((attempt, delay)))
    assert recorded == [(0, 2.0), (1, 4.0)]


# --- call_with_retry_async (item: אימוץ retry/backoff גם ב-Steam/RSS) - אותו
# עיקרון בדיוק, אבל func()/sleep_func אסינכרוניים (await, לא חוסם את ה-event
# loop) - נבדק עם asyncio.run(), אותו דפוס כמו tests/bot/test_rss_monitor.py. ---

def _run(coro):
    return asyncio.run(coro)


def test_call_with_retry_async_succeeds_first_try():
    calls = []

    async def func():
        calls.append(1)
        return "ok"

    async def scenario():
        return await call_with_retry_async(func, sleep_func=lambda d: asyncio.sleep(0))

    result = _run(scenario())
    assert result == "ok"
    assert len(calls) == 1


def test_call_with_retry_async_succeeds_after_failures():
    attempts = {"n": 0}

    async def func():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("temporary")
        return "ok"

    async def scenario():
        sleeps = []

        async def fake_sleep(d):
            sleeps.append(d)

        result = await call_with_retry_async(func, max_attempts=5, sleep_func=fake_sleep)
        return result, sleeps

    result, sleeps = _run(scenario())
    assert result == "ok"
    assert attempts["n"] == 3
    assert len(sleeps) == 2  # שני כשלים -> שתי המתנות בין ניסיונות


def test_call_with_retry_async_raises_after_exhausting_attempts():
    async def func():
        raise ConnectionError("always fails")

    async def scenario():
        with pytest.raises(ConnectionError):
            await call_with_retry_async(func, max_attempts=3, sleep_func=lambda d: asyncio.sleep(0))

    _run(scenario())


def test_call_with_retry_async_non_retryable_raises_immediately():
    calls = []

    async def func():
        calls.append(1)
        raise ValueError("not retryable")

    async def scenario():
        with pytest.raises(ValueError):
            await call_with_retry_async(func, max_attempts=5, is_retryable=lambda e: False, sleep_func=lambda d: asyncio.sleep(0))

    _run(scenario())
    assert len(calls) == 1


def test_call_with_retry_async_does_not_block_the_event_loop_while_waiting():
    # ההבדל המהותי מול call_with_retry הרגיל - await asyncio.sleep משחרר את
    # ה-event loop, אז משימה אחרת (למשל פקודת דיסקורד אחרת) יכולה לרוץ
    # במקביל בזמן ההמתנה בין ניסיונות, לא רק אחרי שהריטריי כולו מסתיים.
    async def func():
        raise ConnectionError("temp")

    async def other_task():
        return "ran while waiting"

    async def scenario():
        retry_task = asyncio.create_task(
            call_with_retry_async(func, max_attempts=2, base_delay=0.2, sleep_func=asyncio.sleep)
        )
        await asyncio.sleep(0.05)  # תוך כדי ההמתנה של הריטריי
        other_result = await other_task()
        with pytest.raises(ConnectionError):
            await retry_task
        return other_result

    assert _run(scenario()) == "ran while waiting"
