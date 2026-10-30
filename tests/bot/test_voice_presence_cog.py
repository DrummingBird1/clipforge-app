# tests/bot/test_voice_presence_cog.py
#
# בודק את VoicePresenceCog (item: friend detection via Discord voice channel
# presence) מול DB אמיתי (aiosqlite, tmp_path) - snapshot תקופתי, קורלציה
# לפי חלון-זמן, וקריאת ההגדרה מ-rocket_settings.json. בלי הרשת: אין חיבור
# בפועל ל-Discord gateway - Guild/VoiceChannel/Member מזויפים בהתאם למינימום
# הנדרש (id, voice_channels, members, bot, display_name), אותו דפוס בדיוק
# כמו tests/bot/test_approval_cog.py.
import asyncio
import datetime
import json

import aiosqlite


from cogs import voice_presence_cog


class FakeMember:
    def __init__(self, user_id, display_name, is_bot=False):
        self.id = user_id
        self.display_name = display_name
        self.bot = is_bot


class FakeVoiceChannel:
    def __init__(self, channel_id, members):
        self.id = channel_id
        self.members = members


class FakeGuild:
    def __init__(self, voice_channels):
        self.voice_channels = voice_channels


class FakeBot:
    def __init__(self, db, guilds=None):
        self.db = db
        self.guilds = guilds or []


def _make_cog(bot):
    return voice_presence_cog.VoicePresenceCog.__new__(voice_presence_cog.VoicePresenceCog)


def _run(coro):
    return asyncio.run(coro)


async def _open_db(tmp_path):
    return await aiosqlite.connect(str(tmp_path / "test.db"))


def test_take_snapshot_records_non_bot_members_only(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            alice = FakeMember(1, "Alice")
            bot_member = FakeMember(2, "SomeBot", is_bot=True)
            channel = FakeVoiceChannel(100, [alice, bot_member])
            guild = FakeGuild([channel])
            bot = FakeBot(db, guilds=[guild])
            cog = _make_cog(bot)
            cog.bot = bot

            await cog._take_snapshot()

            async with db.execute("SELECT username FROM voice_presence_snapshots") as cursor:
                rows = await cursor.fetchall()
            assert [r[0] for r in rows] == ["Alice"]
        finally:
            await db.close()

    _run(scenario())


def test_take_snapshot_records_multiple_channels_and_members(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel_a = FakeVoiceChannel(100, [FakeMember(1, "Alice"), FakeMember(2, "Bob")])
            channel_b = FakeVoiceChannel(200, [FakeMember(3, "Carol")])
            guild = FakeGuild([channel_a, channel_b])
            bot = FakeBot(db, guilds=[guild])
            cog = _make_cog(bot)
            cog.bot = bot

            await cog._take_snapshot()

            async with db.execute("SELECT channel_id, username FROM voice_presence_snapshots ORDER BY username") as cursor:
                rows = await cursor.fetchall()
            assert rows == [(100, "Alice"), (100, "Bob"), (200, "Carol")]
        finally:
            await db.close()

    _run(scenario())


def test_take_snapshot_prunes_rows_older_than_retention(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db, guilds=[])
            cog = _make_cog(bot)
            cog.bot = bot
            await cog._ensure_table()

            old_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=voice_presence_cog.RETENTION_DAYS + 1)).isoformat(timespec="seconds")
            await db.execute(
                "INSERT INTO voice_presence_snapshots (channel_id, user_id, username, snapshot_at) VALUES (?, ?, ?, ?)",
                (100, 1, "OldUser", old_iso),
            )
            await db.commit()

            await cog._take_snapshot()

            async with db.execute("SELECT username FROM voice_presence_snapshots") as cursor:
                rows = await cursor.fetchall()
            assert rows == []
        finally:
            await db.close()

    _run(scenario())


async def _insert_snapshot(db, channel_id, username, dt):
    await db.execute(
        "CREATE TABLE IF NOT EXISTS voice_presence_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "channel_id INTEGER, user_id INTEGER, username TEXT, snapshot_at TEXT)"
    )
    await db.execute(
        "INSERT INTO voice_presence_snapshots (channel_id, user_id, username, snapshot_at) VALUES (?, ?, ?, ?)",
        (channel_id, 1, username, dt.isoformat(timespec="seconds")),
    )
    await db.commit()


def test_get_present_usernames_finds_users_within_window(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot

            now = datetime.datetime.now(datetime.timezone.utc)
            await _insert_snapshot(db, 100, "Alice", now - datetime.timedelta(seconds=30))

            usernames = await cog.get_present_usernames(100, now.timestamp(), window_seconds=120)

            assert usernames == ["Alice"]
        finally:
            await db.close()

    _run(scenario())


def test_get_present_usernames_excludes_snapshots_outside_window(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot

            now = datetime.datetime.now(datetime.timezone.utc)
            await _insert_snapshot(db, 100, "TooEarly", now - datetime.timedelta(seconds=500))

            usernames = await cog.get_present_usernames(100, now.timestamp(), window_seconds=120)

            assert usernames == []
        finally:
            await db.close()

    _run(scenario())


def test_get_present_usernames_excludes_other_channels(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot

            now = datetime.datetime.now(datetime.timezone.utc)
            await _insert_snapshot(db, 999, "WrongChannel", now - datetime.timedelta(seconds=10))

            usernames = await cog.get_present_usernames(100, now.timestamp(), window_seconds=120)

            assert usernames == []
        finally:
            await db.close()

    _run(scenario())


def test_get_present_usernames_deduplicates_repeated_snapshots(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot

            now = datetime.datetime.now(datetime.timezone.utc)
            await _insert_snapshot(db, 100, "Alice", now - datetime.timedelta(seconds=60))
            await _insert_snapshot(db, 100, "Alice", now - datetime.timedelta(seconds=30))

            usernames = await cog.get_present_usernames(100, now.timestamp(), window_seconds=120)

            assert usernames == ["Alice"]
        finally:
            await db.close()

    _run(scenario())


def test_get_present_usernames_returns_empty_list_for_falsy_channel_id(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot

            assert await cog.get_present_usernames(None, 1000.0) == []
            assert await cog.get_present_usernames(0, 1000.0) == []
        finally:
            await db.close()

    _run(scenario())


def test_get_present_usernames_for_clip_uses_configured_channel_and_mtime(tmp_path, monkeypatch):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot
            monkeypatch.setattr(voice_presence_cog, "get_capture_voice_channel_id", lambda: 100)

            clip_path = tmp_path / "clip.mp4"
            clip_path.write_bytes(b"fake")
            now = datetime.datetime.now(datetime.timezone.utc)
            await _insert_snapshot(db, 100, "Alice", now - datetime.timedelta(seconds=10))

            usernames = await cog.get_present_usernames_for_clip(str(clip_path))

            assert usernames == ["Alice"]
        finally:
            await db.close()

    _run(scenario())


def test_get_present_usernames_for_clip_returns_empty_when_no_channel_configured(tmp_path, monkeypatch):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)
            cog.bot = bot
            monkeypatch.setattr(voice_presence_cog, "get_capture_voice_channel_id", lambda: None)

            clip_path = tmp_path / "clip.mp4"
            clip_path.write_bytes(b"fake")

            assert await cog.get_present_usernames_for_clip(str(clip_path)) == []
        finally:
            await db.close()

    _run(scenario())


def test_snapshot_loop_coro_calls_take_snapshot(tmp_path, monkeypatch):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db, guilds=[])
            cog = _make_cog(bot)
            cog.bot = bot

            calls = []
            orig = cog._take_snapshot

            async def _tracked():
                calls.append(1)
                await orig()

            cog._take_snapshot = _tracked
            await voice_presence_cog.VoicePresenceCog.snapshot_loop.coro(cog)

            assert calls == [1]
        finally:
            await db.close()

    _run(scenario())


def test_get_capture_voice_channel_id_reads_from_settings_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "data" / "rocket_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"capture_voice_channel_id": "12345"}), encoding="utf-8")
    monkeypatch.setattr(voice_presence_cog, "DATA_DIR", str(settings_path.parent))

    assert voice_presence_cog.get_capture_voice_channel_id() == "12345"


def test_get_capture_voice_channel_id_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(voice_presence_cog, "DATA_DIR", str(tmp_path / "data"))

    assert voice_presence_cog.get_capture_voice_channel_id() is None


def test_get_capture_voice_channel_id_none_when_empty_string(tmp_path, monkeypatch):
    settings_path = tmp_path / "data" / "rocket_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"capture_voice_channel_id": ""}), encoding="utf-8")
    monkeypatch.setattr(voice_presence_cog, "DATA_DIR", str(settings_path.parent))

    assert voice_presence_cog.get_capture_voice_channel_id() is None
