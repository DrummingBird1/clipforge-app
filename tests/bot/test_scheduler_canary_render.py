# tests/bot/test_scheduler_canary_render.py
#
# בודק SchedulerCog._maybe_run_canary_render (item: "רינדור-קנרית" מתוזמן) -
# _run_script_blocking/_run_canary_render עצמם מדומים ברוב הטסטים (אותו דפוס
# כמו test_scheduler_cog_recap.py, כדי שהטסטים ירוצו מהר ולא ידרשו ffmpeg
# אמיתי), אבל _make_canary_clip/_run_canary_render עצמם נבדקים גם בנפרד עם
# ffmpeg/video_editor.py אמיתיים (e2e) - זה בדיוק מה שהם אמורים לבדוק בפועל
# בייצור, ראו tests/studio/test_video_editor_mega_upgrade_e2e.py לאותו עיקרון.
import asyncio
import os
import shutil
from unittest.mock import AsyncMock


import pytest

import cogs.scheduler_cog as scheduler_cog
from utils.shared.ffmpeg_locator import get_ffmpeg_exe


def _run(coro):
    return asyncio.run(coro)


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


# אותו דפוס בדיוק כמו tests/studio/test_video_editor_mega_upgrade_e2e.py - רק שני
# הטסטים שבאמת מריצים ffmpeg (לא כל הקובץ) מדולגים בסביבה בלי ffmpeg זמין
# (למשל CI), כדי שטסטי-החיווט המהירים/מדומים בקובץ הזה עדיין ירוצו שם.
_requires_real_ffmpeg = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()),
    reason="ffmpeg לא זמין בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


class FakeOwner:
    def __init__(self):
        self.send = AsyncMock()


class FakeAppInfo:
    def __init__(self, owner):
        self.owner = owner


class FakeLoop:
    async def run_in_executor(self, _executor, func, *args):
        return func(*args)


class FakeBot:
    def __init__(self):
        self.owner = FakeOwner()
        self.application_info = AsyncMock(return_value=FakeAppInfo(self.owner))
        self.loop = FakeLoop()


def _make_cog(bot):
    cog = scheduler_cog.SchedulerCog.__new__(scheduler_cog.SchedulerCog)
    cog.bot = bot
    return cog


# --- _maybe_run_canary_render (wiring - _run_canary_render מדומה) ---

def test_runs_when_not_yet_run_today_and_succeeds(monkeypatch):
    monkeypatch.setattr(scheduler_cog, "_run_canary_render", lambda: (True, ""))

    async def scenario():
        cog = _make_cog(FakeBot())
        state = {}
        await cog._maybe_run_canary_render(state, "2026-09-18")

        assert state["last_canary_render_date"] == "2026-09-18"
        cog.bot.owner.send.assert_not_awaited()  # הצליח - אין התראה

    _run(scenario())


def test_skips_when_already_run_today(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_canary_render", lambda: (calls.append(1), (True, ""))[1])

    async def scenario():
        cog = _make_cog(FakeBot())
        state = {"last_canary_render_date": "2026-09-18"}
        await cog._maybe_run_canary_render(state, "2026-09-18")

        assert calls == []  # לא רץ שוב היום

    _run(scenario())


def test_notifies_owner_when_canary_fails(monkeypatch):
    monkeypatch.setattr(scheduler_cog, "_run_canary_render", lambda: (False, "ffmpeg: command not found"))

    async def scenario():
        cog = _make_cog(FakeBot())
        state = {}
        await cog._maybe_run_canary_render(state, "2026-09-18")

        assert state["last_canary_render_date"] == "2026-09-18"  # עדיין מתעדכן - לא ננסה שוב היום
        cog.bot.owner.send.assert_awaited_once()
        message = cog.bot.owner.send.call_args.args[0]
        assert "רינדור-קנרית נכשל" in message
        assert "ffmpeg: command not found" in message

    _run(scenario())


def test_runs_regardless_of_user_settings():
    # בניגוד ל-_maybe_run_recap (תלוי enable_weekly_recap) - זו בדיקת-בריאות
    # תשתית, לא פיצ'ר להדלקה/כיבוי, אז אין settings בכלל בחתימה שלה.
    import inspect
    params = list(inspect.signature(scheduler_cog.SchedulerCog._maybe_run_canary_render).parameters)
    assert "settings" not in params


# --- _make_canary_clip / _run_canary_render (e2e - ffmpeg/video_editor.py אמיתיים) ---

@_requires_real_ffmpeg
def test_make_canary_clip_creates_a_real_playable_video_file(tmp_path):
    clip_path = str(tmp_path / "canary.mp4")

    ok = scheduler_cog._make_canary_clip(clip_path)

    assert ok is True
    assert os.path.exists(clip_path)
    assert os.path.getsize(clip_path) > 0


class _NullContext:
    """אותו דפוס בדיוק כמו test_scheduler_cog_recap.py - מדלג על מנעול-הרינדור
    האמיתי (data/render.lock) בטסט, כדי שהריצה לא תיתקע/תתנגש עם רינדור אמיתי
    שרץ במקביל על המכונה הזו."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@_requires_real_ffmpeg
def test_run_canary_render_succeeds_end_to_end_with_real_ffmpeg_and_video_editor(monkeypatch):
    # e2e אמיתי - לא מוק. זה בדיוק מה ש-_run_canary_render אמור להוכיח בייצור:
    # שה-pipeline האמיתי (ffmpeg testsrc + video_editor.py --codec h264) עדיין
    # עובד מקצה לקצה על המכונה הזו.
    monkeypatch.setattr(scheduler_cog, "render_lock", lambda: _NullContext())

    success, tail = scheduler_cog._run_canary_render()

    assert success is True, f"רינדור-הקנרית נכשל בפועל: {tail}"


def test_run_canary_render_fails_gracefully_when_clip_generation_fails(monkeypatch):
    monkeypatch.setattr(scheduler_cog, "_make_canary_clip", lambda path: False)
    calls = []
    monkeypatch.setattr(scheduler_cog, "_run_script_blocking", lambda *a, **k: calls.append(1))

    success, tail = scheduler_cog._run_canary_render()

    assert success is False
    assert "קליפ הבדיקה" in tail
    assert calls == []  # video_editor.py לא אמור לרוץ בכלל בלי קליפ קלט
