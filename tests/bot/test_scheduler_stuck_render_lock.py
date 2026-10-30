# tests/bot/test_scheduler_stuck_render_lock.py
#
# בודק SchedulerCog.check_stuck_render_lock (item: התראה יזומה אם render_lock
# נשאר תפוס מעבר לזמן סביר) - render_lock.get_status מדומה (לא מנעול קובץ
# אמיתי), FakeBot עם owner.send מדומה (אותו דפוס בדיוק כמו test_scheduler_cog_recap.py).
import asyncio
from unittest.mock import AsyncMock


import cogs.scheduler_cog as scheduler_cog


def _run(coro):
    return asyncio.run(coro)


class FakeOwner:
    def __init__(self):
        self.send = AsyncMock()


class FakeAppInfo:
    def __init__(self, owner):
        self.owner = owner


class FakeBot:
    def __init__(self):
        self.owner = FakeOwner()
        self.application_info = AsyncMock(return_value=FakeAppInfo(self.owner))


def _make_cog(bot):
    cog = scheduler_cog.SchedulerCog.__new__(scheduler_cog.SchedulerCog)
    cog.bot = bot
    return cog


def _isolate_state(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduler_cog, "SCHEDULER_STATE_PATH", str(tmp_path / "scheduler_state.json"))


def test_does_nothing_when_lock_is_free(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    monkeypatch.setattr(scheduler_cog, "get_render_lock_status", lambda: None)

    async def scenario():
        cog = _make_cog(FakeBot())
        await cog.check_stuck_render_lock.coro(cog)
        cog.bot.owner.send.assert_not_awaited()

    _run(scenario())


def test_does_nothing_when_lock_held_below_warning_threshold(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    below_threshold = scheduler_cog.RENDER_LOCK_STUCK_WARNING_SECONDS - 60
    monkeypatch.setattr(
        scheduler_cog, "get_render_lock_status",
        lambda: {"pid": 1234, "acquired_at": 1000.0, "age_seconds": below_threshold, "is_stale": False, "queue_length": 0},
    )

    async def scenario():
        cog = _make_cog(FakeBot())
        await cog.check_stuck_render_lock.coro(cog)
        cog.bot.owner.send.assert_not_awaited()

    _run(scenario())


def test_notifies_owner_when_lock_held_past_warning_threshold(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    above_threshold = scheduler_cog.RENDER_LOCK_STUCK_WARNING_SECONDS + 120
    monkeypatch.setattr(
        scheduler_cog, "get_render_lock_status",
        lambda: {"pid": 4321, "acquired_at": 5000.0, "age_seconds": above_threshold, "is_stale": False, "queue_length": 0},
    )

    async def scenario():
        cog = _make_cog(FakeBot())
        await cog.check_stuck_render_lock.coro(cog)
        cog.bot.owner.send.assert_awaited_once()
        message = cog.bot.owner.send.call_args.args[0]
        assert "מנעול הרינדור תפוס" in message
        assert "4321" in message

    _run(scenario())


def test_does_not_notify_twice_for_the_same_lock_acquisition(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    above_threshold = scheduler_cog.RENDER_LOCK_STUCK_WARNING_SECONDS + 60
    monkeypatch.setattr(
        scheduler_cog, "get_render_lock_status",
        lambda: {"pid": 111, "acquired_at": 9000.0, "age_seconds": above_threshold, "is_stale": False, "queue_length": 0},
    )

    async def scenario():
        cog = _make_cog(FakeBot())
        await cog.check_stuck_render_lock.coro(cog)
        await cog.check_stuck_render_lock.coro(cog)  # אותה acquired_at - עדיין אותו מנעול תקוע
        cog.bot.owner.send.assert_awaited_once()  # לא הוצפנו בהתראה חוזרת כל 15 דקות

    _run(scenario())


def test_notifies_again_for_a_new_lock_acquisition_after_the_previous_one_cleared(monkeypatch, tmp_path):
    _isolate_state(monkeypatch, tmp_path)
    above_threshold = scheduler_cog.RENDER_LOCK_STUCK_WARNING_SECONDS + 60

    async def scenario():
        cog = _make_cog(FakeBot())

        monkeypatch.setattr(
            scheduler_cog, "get_render_lock_status",
            lambda: {"pid": 111, "acquired_at": 1000.0, "age_seconds": above_threshold, "is_stale": False, "queue_length": 0},
        )
        await cog.check_stuck_render_lock.coro(cog)

        # המנעול הזה שוחרר, ונתפס מחדש (acquired_at חדש) - זה עוד תפיסה שגם
        # היא נתקעה, ראויה להתראה משלה, לא "אותה" התראה מודחקת.
        monkeypatch.setattr(
            scheduler_cog, "get_render_lock_status",
            lambda: {"pid": 222, "acquired_at": 2000.0, "age_seconds": above_threshold, "is_stale": False, "queue_length": 0},
        )
        await cog.check_stuck_render_lock.coro(cog)

        assert cog.bot.owner.send.await_count == 2

    _run(scenario())
