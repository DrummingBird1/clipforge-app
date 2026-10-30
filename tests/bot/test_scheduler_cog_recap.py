# tests/bot/test_scheduler_cog_recap.py
#
# בודק SchedulerCog._maybe_run_recap (item: ריקאפ תקופתי week/month/year) -
# מחולץ מ-daily_maintenance לפונקציה נפרדת בדיוק כדי שאפשר יהיה לבדוק אותה
# ישירות בלי לעבור על שאר שלבי התחזוקה היומית (גיבוי DB וכו', שנבדקים כל אחד
# בנפרד בקבצים אחרים). datetime.date.today() מוקפא ל-subclass קבוע (לא
# monkeypatch על should_run_recap_today עצמה - זו כבר 100% מכוסה בנפרד
# ב-tests/bot/test_compilation.py, כאן בודקים רק את החיווט).
import asyncio
import datetime
import os
from unittest.mock import AsyncMock


import cogs.scheduler_cog as scheduler_cog


def _run(coro):
    return asyncio.run(coro)


def _freeze_today(monkeypatch, fixed_date):
    class _FrozenDate(datetime.date):
        @classmethod
        def today(cls):
            return fixed_date

    monkeypatch.setattr(scheduler_cog.datetime, "date", _FrozenDate)


class FakeOwner:
    def __init__(self):
        self.send = AsyncMock()


class FakeAppInfo:
    def __init__(self, owner):
        self.owner = owner


class FakeBot:
    def __init__(self, loop):
        self.loop = loop
        self.owner = FakeOwner()
        self.application_info = AsyncMock(return_value=FakeAppInfo(self.owner))


def _make_cog(bot):
    cog = scheduler_cog.SchedulerCog.__new__(scheduler_cog.SchedulerCog)
    cog.bot = bot
    return cog


def test_maybe_run_recap_does_nothing_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: calls.append(a) or ("success", ""))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        await cog._maybe_run_recap({"enable_weekly_recap": False}, {}, "2026-09-13")
        assert calls == []

    _run(scenario())


def test_maybe_run_recap_skips_on_the_wrong_weekday(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 9, 14))  # weekday() == 0 (שני)
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: calls.append(a) or ("success", ""))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        settings = {"enable_weekly_recap": True, "weekly_recap_period": "week", "weekly_recap_day": 6}  # ראשון, לא שני
        await cog._maybe_run_recap(settings, {}, "2026-09-14")
        assert calls == []

    _run(scenario())


def test_maybe_run_recap_already_ran_today_does_nothing(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 9, 13))  # weekday() == 6 (ראשון)
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: calls.append(a) or ("success", ""))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        settings = {"enable_weekly_recap": True, "weekly_recap_period": "week", "weekly_recap_day": 6}
        state = {"last_weekly_recap_date": "2026-09-13"}
        await cog._maybe_run_recap(settings, state, "2026-09-13")
        assert calls == []

    _run(scenario())


def test_maybe_run_recap_runs_on_the_right_weekday_and_updates_state(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 9, 13))  # weekday() == 6 (ראשון)
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: calls.append(a) or ("success", ""))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        settings = {"enable_weekly_recap": True, "weekly_recap_period": "week", "weekly_recap_day": 6}
        state = {}
        await cog._maybe_run_recap(settings, state, "2026-09-13")

        assert len(calls) == 1
        script_relpath, extra_args = calls[0]
        assert script_relpath == os.path.join("video", "weekly_compilation.py")
        assert extra_args == ["--period", "week"]
        assert state["last_weekly_recap_date"] == "2026-09-13"
        cog.bot.owner.send.assert_not_awaited()  # הצליח - אין התראת כישלון

    _run(scenario())


def test_maybe_run_recap_month_period_runs_on_the_first_of_the_month(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 10, 1))
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: calls.append(a) or ("success", ""))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        settings = {"enable_weekly_recap": True, "weekly_recap_period": "month", "weekly_recap_day": 6}
        await cog._maybe_run_recap(settings, {}, "2026-10-01")

        assert len(calls) == 1
        assert calls[0][1] == ["--period", "month"]

    _run(scenario())


def test_maybe_run_recap_month_period_does_not_run_on_other_days(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 10, 15))
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: calls.append(a) or ("success", ""))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        settings = {"enable_weekly_recap": True, "weekly_recap_period": "month"}
        await cog._maybe_run_recap(settings, {}, "2026-10-15")
        assert calls == []

    _run(scenario())


def test_maybe_run_recap_notifies_owner_on_failure(monkeypatch):
    _freeze_today(monkeypatch, datetime.date(2026, 1, 1))
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a: ("failed", "some ffmpeg error"))

    async def scenario():
        cog = _make_cog(FakeBot(asyncio.get_running_loop()))
        settings = {"enable_weekly_recap": True, "weekly_recap_period": "year"}
        state = {}
        await cog._maybe_run_recap(settings, state, "2026-01-01")

        cog.bot.owner.send.assert_awaited_once()
        message = cog.bot.owner.send.call_args.args[0]
        assert "ריקאפ אוטומטי נכשל" in message
        assert "some ffmpeg error" in message
        assert state["last_weekly_recap_date"] == "2026-01-01"  # עדיין מתעדכן - לא ננסה שוב היום

    _run(scenario())


def test_run_script_blocking_appends_extra_args_to_the_subprocess_command(monkeypatch, tmp_path):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler_cog.subprocess, "run", _fake_run)
    monkeypatch.setattr(scheduler_cog, "render_lock", lambda: _NullContext())
    monkeypatch.setattr(scheduler_cog.job_history, "record_job", lambda *a, **k: None)

    scheduler_cog._run_script_blocking(os.path.join("video", "weekly_compilation.py"), ["--period", "month"])

    assert captured["cmd"][-2:] == ["--period", "month"]


def test_run_script_blocking_decodes_utf8_output_regardless_of_system_locale(monkeypatch):
    # item: בדיקת באגים מקיפה (נמצא תוך כדי הוספת רינדור-קנרית) - subprocess.run
    # בלי encoding="utf-8" מפורש היה נופל לקידוד ה-locale של המערכת (cp1255
    # בווינדוס עברי) לפענוח פלט תת-התהליך, שנכשל (UnicodeDecodeError) על תווים
    # אמיתיים ש-video_editor.py כותב ב-UTF-8 (הוא בעצמו עושה stdout.reconfigure
    # ל-UTF-8) אבל cp1255 לא יודע לייצג.
    def _fake_run(cmd, **kwargs):
        assert kwargs.get("encoding") == "utf-8"
        assert kwargs.get("errors") == "replace"
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, stdout="✅ עברית עם אימוג'י שלא קיים ב-cp1255", stderr="")

    monkeypatch.setattr(scheduler_cog.subprocess, "run", _fake_run)
    monkeypatch.setattr(scheduler_cog, "render_lock", lambda: _NullContext())
    monkeypatch.setattr(scheduler_cog.job_history, "record_job", lambda *a, **k: None)

    status, tail = scheduler_cog._run_script_blocking(os.path.join("video", "video_editor.py"))

    assert status == "success"
    assert "עברית" in tail


def test_run_script_blocking_with_no_extra_args_matches_old_behavior(monkeypatch):
    captured = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        import subprocess
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler_cog.subprocess, "run", _fake_run)
    monkeypatch.setattr(scheduler_cog, "render_lock", lambda: _NullContext())
    monkeypatch.setattr(scheduler_cog.job_history, "record_job", lambda *a, **k: None)

    scheduler_cog._run_script_blocking(os.path.join("video", "cleanup_published_sources.py"))

    assert captured["cmd"][-1].endswith("cleanup_published_sources.py")


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
