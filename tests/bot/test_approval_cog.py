# tests/bot/test_approval_cog.py
#
# בודק את הלוגיקה הטהורה של ApprovalCog מול DB אמיתי (aiosqlite, tmp_path) -
# מיגרציית _ensure_table, עדכון status/resolved_at ב-resolve_pending, ספירת
# _do_scan, ואת שאילתת ה-digest היומי. בלי הרשת: אין חיבור בפועל ל-Discord
# gateway, לא מריצים scan_loop/daily_digest.start() (דורש event loop רץ כבר
# בזמן __init__) - בונים cog עם __new__ וממלאים ידנית רק את מה שנחוץ, בדומה
# לאיך שהקודבייס הזה נמנע מלבדוק אינטגרציית discord.py עצמה.
import asyncio
import datetime
import os
import threading

import aiosqlite


from cogs import approval_cog


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class FakeBot:
    def __init__(self, db, channel=None, voice_cog=None):
        self.db = db
        self._channel = channel
        self._voice_cog = voice_cog

    def get_channel(self, _channel_id):
        return self._channel

    def get_cog(self, _name):
        # item: friend detection via Discord voice channel presence -
        # ApprovalCog._do_scan קורא ל-self.bot.get_cog("VoicePresenceCog");
        # None כברירת מחדל (אין voice cog טעון) הוא בדיוק המצב הנפוץ בטסטים
        # שלא בודקים את התכונה הזו במפורש.
        return self._voice_cog


def _make_cog(bot, review_channel_id=None):
    cog = approval_cog.ApprovalCog.__new__(approval_cog.ApprovalCog)
    cog.bot = bot
    cog.review_channel_id = review_channel_id
    return cog


def _run(coro):
    return asyncio.run(coro)


async def _open_db(tmp_path):
    return await aiosqlite.connect(str(tmp_path / "test.db"))


def test_ensure_table_migration_is_idempotent(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            # טבלה "ישנה" כמו שהייתה קיימת לפני שהעמודה resolved_at נוספה
            await db.execute("""
                CREATE TABLE pending_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_path TEXT UNIQUE,
                    status TEXT DEFAULT 'pending',
                    channel_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()
            cog = _make_cog(FakeBot(db))

            await cog._ensure_table()  # מוסיף resolved_at
            await cog._ensure_table()  # לא אמור להתפוצץ כשהעמודה כבר קיימת

            async with db.execute("PRAGMA table_info(pending_approvals)") as cursor:
                columns = {row[1] for row in await cursor.fetchall()}
            assert "resolved_at" in columns
        finally:
            await db.close()

    _run(scenario())


def test_resolve_pending_approved_sets_status_and_moves_file(tmp_path, monkeypatch):
    rocket_input_dir = tmp_path / "rocket_input"
    monkeypatch.setattr(approval_cog, "get_rocket_input_dir", lambda: str(rocket_input_dir))
    monkeypatch.setattr(approval_cog, "REJECTED_DIR", str(tmp_path / "rejected"))

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            await cog._ensure_table()

            video_path = str(tmp_path / "clip.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video bytes")

            cursor = await db.execute(
                "INSERT INTO pending_approvals (video_path, status, channel_id) VALUES (?, 'pending', ?)",
                (video_path, 123),
            )
            await db.commit()
            pending_id = cursor.lastrowid

            await cog.resolve_pending(pending_id, video_path, approved=True)

            async with db.execute(
                "SELECT status, resolved_at FROM pending_approvals WHERE id = ?", (pending_id,)
            ) as cur:
                status, resolved_at = await cur.fetchone()
            assert status == "approved"
            assert resolved_at is not None
            assert not os.path.exists(video_path)
            assert os.path.exists(rocket_input_dir / "clip.mp4")
        finally:
            await db.close()

    _run(scenario())


def test_resolve_pending_rejected_sets_status_and_moves_file(tmp_path, monkeypatch):
    rejected_dir = tmp_path / "rejected"
    monkeypatch.setattr(approval_cog, "get_rocket_input_dir", lambda: str(tmp_path / "rocket_input"))
    monkeypatch.setattr(approval_cog, "REJECTED_DIR", str(rejected_dir))

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            await cog._ensure_table()

            video_path = str(tmp_path / "clip.mp4")
            with open(video_path, "wb") as f:
                f.write(b"fake video bytes")

            cursor = await db.execute(
                "INSERT INTO pending_approvals (video_path, status, channel_id) VALUES (?, 'pending', ?)",
                (video_path, 123),
            )
            await db.commit()
            pending_id = cursor.lastrowid

            await cog.resolve_pending(pending_id, video_path, approved=False)

            async with db.execute(
                "SELECT status, resolved_at FROM pending_approvals WHERE id = ?", (pending_id,)
            ) as cur:
                status, resolved_at = await cur.fetchone()
            assert status == "rejected"
            assert resolved_at is not None
            assert not os.path.exists(video_path)
            assert os.path.exists(rejected_dir / "clip.mp4")
        finally:
            await db.close()

    _run(scenario())


def test_do_scan_sends_new_clips_once_and_counts_them(tmp_path, monkeypatch):
    clips_dir = tmp_path / "clips" / "SomeGame"
    clips_dir.mkdir(parents=True)
    (clips_dir / "clip1.mp4").write_bytes(b"fake")
    (clips_dir / "clip2.mkv").write_bytes(b"fake")
    (clips_dir / "notes.txt").write_bytes(b"not a video")  # לא סיומת נתמכת - לא נספר

    monkeypatch.setattr(approval_cog, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(approval_cog, "FRIEND_TAGS_CACHE_DIR", str(tmp_path / ".friend_tags_cache"))
    monkeypatch.setattr(approval_cog.ApprovalCog, "_make_preview_thumb", lambda self, video_path: None)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel), review_channel_id=999)

            sent_count = await cog._do_scan()
            assert sent_count == 2
            assert len(channel.sent) == 2

            # ריצה חוזרת לא אמורה לשלוח שוב קליפים שכבר נרשמו בטבלה
            sent_count_again = await cog._do_scan()
            assert sent_count_again == 0
            assert len(channel.sent) == 2
        finally:
            await db.close()

    _run(scenario())


def test_do_scan_returns_zero_without_review_channel(tmp_path, monkeypatch):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    monkeypatch.setattr(approval_cog, "CLIPS_REVIEW_DIR", str(clips_dir))

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db), review_channel_id=None)
            assert await cog._do_scan() == 0
        finally:
            await db.close()

    _run(scenario())


# --- friend detection via Discord voice channel presence ---

class FakeVoiceCog:
    def __init__(self, usernames):
        self._usernames = usernames

    async def get_present_usernames_for_clip(self, video_path):
        return self._usernames


def test_do_scan_includes_friend_names_in_embed_description(tmp_path, monkeypatch):
    clips_dir = tmp_path / "clips" / "SomeGame"
    clips_dir.mkdir(parents=True)
    (clips_dir / "clip1.mp4").write_bytes(b"fake")
    monkeypatch.setattr(approval_cog, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(approval_cog, "FRIEND_TAGS_CACHE_DIR", str(tmp_path / ".friend_tags_cache"))
    monkeypatch.setattr(approval_cog.ApprovalCog, "_make_preview_thumb", lambda self, video_path: None)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            voice_cog = FakeVoiceCog(["Alice", "Bob"])
            cog = _make_cog(FakeBot(db, channel=channel, voice_cog=voice_cog), review_channel_id=999)

            await cog._do_scan()

            embed = channel.sent[0]["embed"]
            assert "Alice" in embed.description
            assert "Bob" in embed.description
        finally:
            await db.close()

    _run(scenario())


def test_do_scan_omits_friends_line_when_none_detected(tmp_path, monkeypatch):
    clips_dir = tmp_path / "clips" / "SomeGame"
    clips_dir.mkdir(parents=True)
    (clips_dir / "clip1.mp4").write_bytes(b"fake")
    monkeypatch.setattr(approval_cog, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(approval_cog, "FRIEND_TAGS_CACHE_DIR", str(tmp_path / ".friend_tags_cache"))
    monkeypatch.setattr(approval_cog.ApprovalCog, "_make_preview_thumb", lambda self, video_path: None)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel, voice_cog=None), review_channel_id=999)

            await cog._do_scan()

            embed = channel.sent[0]["embed"]
            assert "עם:" not in embed.description
        finally:
            await db.close()

    _run(scenario())


def test_do_scan_writes_friend_tags_cache_file(tmp_path, monkeypatch):
    clips_dir = tmp_path / "clips" / "SomeGame"
    clips_dir.mkdir(parents=True)
    clip = clips_dir / "clip1.mp4"
    clip.write_bytes(b"fake")
    friend_cache_dir = tmp_path / ".friend_tags_cache"
    monkeypatch.setattr(approval_cog, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(approval_cog, "FRIEND_TAGS_CACHE_DIR", str(friend_cache_dir))
    monkeypatch.setattr(approval_cog.ApprovalCog, "_make_preview_thumb", lambda self, video_path: None)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            voice_cog = FakeVoiceCog(["Alice"])
            cog = _make_cog(FakeBot(db, channel=channel, voice_cog=voice_cog), review_channel_id=999)

            await cog._do_scan()

            from utils.media.clip_tagger import read_cached_tags
            assert read_cached_tags(str(clip), str(friend_cache_dir)) == ["Alice"]
        finally:
            await db.close()

    _run(scenario())


def test_detect_and_cache_friends_returns_empty_list_without_voice_cog(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_cog, "FRIEND_TAGS_CACHE_DIR", str(tmp_path / ".friend_tags_cache"))

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            clip = tmp_path / "clip.mp4"
            clip.write_bytes(b"fake")
            cog = _make_cog(FakeBot(db, voice_cog=None))

            friends = await cog._detect_and_cache_friends(str(clip))

            assert friends == []
        finally:
            await db.close()

    _run(scenario())


async def _insert_resolved(db, video_path, status, resolved_at):
    await db.execute(
        "INSERT INTO pending_approvals (video_path, status, channel_id, resolved_at) VALUES (?, ?, ?, ?)",
        (video_path, status, 999, resolved_at),
    )
    await db.commit()


def test_daily_digest_counts_only_todays_resolved_rows(tmp_path):
    today = datetime.date.today().isoformat()
    other_day = "2000-01-01"

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel), review_channel_id=999)
            await cog._ensure_table()

            await _insert_resolved(db, "/clips/a.mp4", "approved", f"{today}T09:00:00")
            await _insert_resolved(db, "/clips/b.mp4", "approved", f"{today}T10:00:00")
            await _insert_resolved(db, "/clips/c.mp4", "rejected", f"{today}T11:00:00")
            await _insert_resolved(db, "/clips/d.mp4", "approved", f"{other_day}T09:00:00")  # יום אחר - לא נספר
            await _insert_resolved(db, "/clips/e.mp4", "pending", None)  # לא הוחלט - לא נספר

            await cog.daily_digest.coro(cog)

            assert len(channel.sent) == 1
            embed = channel.sent[0]["embed"]
            values_by_name = {field.name: field.value for field in embed.fields}
            assert values_by_name["✅ אושרו"] == "2"
            assert values_by_name["❌ נדחו"] == "1"
        finally:
            await db.close()

    _run(scenario())


def test_daily_digest_sends_nothing_when_no_activity_today(tmp_path):
    other_day = "2000-01-01"

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel), review_channel_id=999)
            await cog._ensure_table()

            await _insert_resolved(db, "/clips/a.mp4", "approved", f"{other_day}T09:00:00")
            await _insert_resolved(db, "/clips/e.mp4", "pending", None)

            await cog.daily_digest.coro(cog)

            assert channel.sent == []
        finally:
            await db.close()

    _run(scenario())


class FailingOnceChannel(FakeChannel):
    """הניסיון הראשון לשלוח נכשל (רשת / Discord לא זמין), השני מצליח."""
    def __init__(self):
        super().__init__()
        self.failures_left = 1

    async def send(self, **kwargs):
        if self.failures_left:
            self.failures_left -= 1
            raise RuntimeError("Discord לא זמין")
        self.sent.append(kwargs)


def test_do_scan_retries_a_clip_whose_send_failed(tmp_path, monkeypatch):
    """25.10.2026: הקליף נרשם כ-pending לפני השליחה; כשהשליחה נכשלה הוא נשאר רשום ולא נשלח לאישור אף פעם."""
    clips_dir = tmp_path / "clips" / "SomeGame"
    clips_dir.mkdir(parents=True)
    (clips_dir / "clip1.mp4").write_bytes(b"fake")
    thumb = clips_dir / "clip1_review_thumb.jpg"

    threads = []

    def fake_thumb(self, video_path):
        threads.append(threading.get_ident())   # ffmpeg לא בתוך הלולאה של הבוט
        thumb.write_bytes(b"jpg")
        return str(thumb)

    monkeypatch.setattr(approval_cog, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(approval_cog, "FRIEND_TAGS_CACHE_DIR", str(tmp_path / ".friend_tags_cache"))
    monkeypatch.setattr(approval_cog.ApprovalCog, "_make_preview_thumb", fake_thumb)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FailingOnceChannel()
            cog = _make_cog(FakeBot(db, channel=channel), review_channel_id=999)
            assert await cog._do_scan() == 0
            assert not thumb.exists()        # התמונה הזמנית לא נשארת ליד הקליף
            assert await cog._do_scan() == 1  # הסריקה הבאה שולחת אותו
            assert len(channel.sent) == 1
            assert threads and threading.get_ident() not in threads
            async with db.execute("SELECT COUNT(*) FROM pending_approvals") as cursor:
                assert (await cursor.fetchone())[0] == 1
        finally:
            await db.close()

    _run(scenario())
