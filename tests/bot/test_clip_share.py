# tests/bot/test_clip_share.py
#
# 16.11.2026 (2.0): "שלח לדיסקורד" - utils/bot/discord_outbox.py (התור ב-DB) ו-cogs/clip_share_cog.py (השליחה), עם ערוץ
# מדומה. בלי דיסקורד אמיתי.
import asyncio
from unittest.mock import AsyncMock, MagicMock

from cogs.clip_share_cog import ClipShareCog, size_problem
from utils.bot import discord_outbox as ob


def test_the_queue_round_trip(tmp_path):
    db = str(tmp_path / "bot.db")
    assert ob.get_channel(db) is None
    ob.set_channel(1234, db)
    assert ob.get_channel(db) == 1234
    row_id = ob.enqueue("C:/a.mp4", "גול!", db_path=db)
    assert [r["id"] for r in ob.pending(db_path=db)] == [row_id]
    ob.mark(row_id, False, "רשת", db_path=db)
    assert ob.pending(db_path=db)[0]["attempts"] == 1
    ob.mark(row_id, True, db_path=db)
    assert ob.pending(db_path=db) == [] and ob.recent(db_path=db)[0]["status"] == "sent"


def test_a_final_failure_is_not_retried(tmp_path):
    db = str(tmp_path / "bot.db")
    row_id = ob.enqueue("C:/missing.mp4", db_path=db)
    ob.mark(row_id, False, "הקובץ לא נמצא", final=True, db_path=db)
    assert ob.pending(db_path=db) == [] and ob.recent(db_path=db)[0]["status"] == "failed"


def test_size_limit_message():
    assert size_problem(5, 10) is None
    assert "דיסקורד" in size_problem(30 * 1024 * 1024, 10 * 1024 * 1024)


def _cog(channel):
    cog = ClipShareCog.__new__(ClipShareCog)
    cog.bot = MagicMock()
    cog.bot.get_channel = MagicMock(return_value=channel)
    return cog


def test_the_cog_sends_the_file_to_the_channel(tmp_path):
    clip = tmp_path / "goal.mp4"
    clip.write_bytes(b"v" * 100)
    channel = MagicMock()
    channel.send = AsyncMock()
    channel.guild.filesize_limit = 10 * 1024 * 1024
    ok, error, final = asyncio.run(_cog(channel).send_row({"path": str(clip), "message": "גול", "channel_id": None}, 55))
    assert (ok, error, final) == (True, "", False)
    assert channel.send.await_args.kwargs["content"] == "גול"


def test_the_cog_refuses_a_file_over_the_servers_limit(tmp_path):
    clip = tmp_path / "big.mp4"
    clip.write_bytes(b"v" * 2000)
    channel = MagicMock()
    channel.send = AsyncMock()
    channel.guild.filesize_limit = 1000
    ok, error, final = asyncio.run(_cog(channel).send_row({"path": str(clip), "channel_id": 1}, None))
    assert not ok and final and "MB" in error
    channel.send.assert_not_awaited()


def test_without_a_channel_it_waits_for_one():
    ok, error, final = asyncio.run(_cog(None).send_row({"path": "x", "channel_id": None}, None))
    assert not ok and not final and "/clip_channel" in error
