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
    assert ob.get(row_id, db)["attempts"] == 1 and ob.get(row_id, db)["status"] == "pending"
    assert ob.pending(db_path=db) == []                    # 2.0.1: מחכה לזמן הניסיון הבא, לא נשרף תוך 45 שניות
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
    assert ok is None and not final and "/clip_channel" in error      # None: מחכה, לא כשל


def test_a_clip_queued_before_the_channel_is_set_waits_and_is_sent_later(tmp_path, monkeypatch):
    # 2.0.0: בלי ערוץ, שלושה ניסיונות נשרפו תוך 45 שניות והקליפ נכשל לתמיד - בדיוק בזמן שהמשתמש הלך להריץ /clip_channel.
    db = str(tmp_path / "bot.db")
    monkeypatch.setattr(ob, "DB_PATH", db)
    clip = tmp_path / "goal.mp4"
    clip.write_bytes(b"v" * 100)
    row_id = ob.enqueue(str(clip))
    cog = _cog(None)
    for _ in range(6):
        asyncio.run(ClipShareCog.send_pending.coro(cog))
    row = ob.get(row_id)
    assert row["status"] == "pending" and row["attempts"] == 0 and "/clip_channel" in row["error"]
    channel = MagicMock()
    channel.send = AsyncMock()
    channel.guild.filesize_limit = 10 * 1024 * 1024
    cog.bot.get_channel = MagicMock(return_value=channel)
    ob.set_channel(77)
    asyncio.run(ClipShareCog.send_pending.coro(cog))
    assert ob.get(row_id)["status"] == "sent" and channel.send.await_count == 1


def test_real_failures_are_spaced_out_and_end_after_three(tmp_path, monkeypatch):
    db = str(tmp_path / "bot.db")
    row_id = ob.enqueue("C:/a.mp4", db_path=db)
    monkeypatch.setattr(ob, "RETRY_SECONDS", 0)            # בלי המתנה - רק סופרים
    for attempt in (1, 2):
        ob.mark(row_id, False, "דיסקורד למטה", db_path=db)
        assert ob.get(row_id, db)["status"] == "pending" and ob.get(row_id, db)["attempts"] == attempt
        assert [r["id"] for r in ob.pending(db_path=db)] == [row_id]
    ob.mark(row_id, False, "דיסקורד למטה", db_path=db)
    assert ob.get(row_id, db)["status"] == "failed" and ob.get(row_id, db)["error"] == "דיסקורד למטה"
    assert ob.get(999, db) is None


def test_the_send_loop_survives_an_error_it_does_not_know(tmp_path, monkeypatch):
    # tasks.loop מפסיק לתמיד על חריגה לא מוכרת (DB נעול לרגע) - ואז "שלח לדיסקורד" מת עד הפעלה מחדש של הבוט
    import sqlite3
    db = str(tmp_path / "bot.db")
    monkeypatch.setattr(ob, "DB_PATH", db)
    cog = _cog(None)
    monkeypatch.setattr(ob, "pending", MagicMock(side_effect=sqlite3.OperationalError("database is locked")))
    asyncio.run(ClipShareCog.send_pending.coro(cog))        # לא זורק
    monkeypatch.undo()
    monkeypatch.setattr(ob, "DB_PATH", db)
    row_id = ob.enqueue("C:/a.mp4")
    cog.send_row = AsyncMock(side_effect=RuntimeError("boom"))
    asyncio.run(ClipShareCog.send_pending.coro(cog))        # שורה אחת שנכשלה לא מפילה את הלולאה
    assert ob.get(row_id)["status"] == "pending"


def test_an_old_queue_table_gets_the_new_column(tmp_path):
    import sqlite3
    db = str(tmp_path / "old.db")
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE discord_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, message TEXT DEFAULT '', channel_id INTEGER,
            status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT, created_at TEXT, sent_at TEXT)""")
        conn.execute("INSERT INTO discord_outbox (path) VALUES ('C:/from_2_0_0.mp4')")
    assert [r["path"] for r in ob.pending(db_path=db)] == ["C:/from_2_0_0.mp4"]
