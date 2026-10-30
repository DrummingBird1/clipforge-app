# tests/bot/test_rss_monitor.py
#
# בודק cogs/rss_monitor.py - bot.db הוא aiosqlite אמיתי (tmp_path, טבלות
# rss_feeds/seen_rss_entries אמיתיות), אותו עיקרון כמו test_approval_cog.py/
# test_steam_monitor.py. feedparser.parse מדומה (לא קריאת רשת אמיתית) -
# מחזיר entries עם title/link/get("summary") כמו FeedParserDict אמיתי.
# הcog נבנה עם __new__ (לא __init__) כדי לא להפעיל בפועל את
# fetch_rss_feeds.start() - דורש event loop רץ כבר.
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest


import cogs.rss_monitor as rss_monitor_module
from cogs.rss_monitor import RSSMonitor


def _run(coro):
    return asyncio.run(coro)


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class FakeBot:
    def __init__(self, db, channel=None, is_owner=True):
        self.db = db
        self._channel = channel
        self.wait_until_ready = AsyncMock()
        self.is_owner = AsyncMock(return_value=is_owner)

    def get_channel(self, _channel_id):
        return self._channel


def _make_cog(bot, keywords=None):
    cog = RSSMonitor.__new__(RSSMonitor)
    cog.bot = bot
    cog.keywords = keywords if keywords is not None else ["Steam", "NVIDIA"]
    return cog


def _make_interaction(user_id=1):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    return interaction


async def _open_db(tmp_path, feeds=()):
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    await db.execute("CREATE TABLE rss_feeds (name TEXT, url TEXT, channel_id INTEGER)")
    await db.execute("CREATE TABLE seen_rss_entries (url TEXT UNIQUE, seen_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    for name, url, channel_id in feeds:
        await db.execute("INSERT INTO rss_feeds (name, url, channel_id) VALUES (?, ?, ?)", (name, url, channel_id))
    await db.commit()
    return db


class _Entry:
    """מדמה feedparser's FeedParserDict - גישה גם כ-attribute (entry.title)
    וגם כ-dict.get (entry.get("summary", ...)), בדיוק כמו רשומת פיד אמיתית."""

    def __init__(self, title, link, summary=None, published_parsed=None, updated_parsed=None):
        self.title = title
        self.link = link
        self._fields = {"summary": summary, "published_parsed": published_parsed, "updated_parsed": updated_parsed}

    def get(self, key, default=None):
        value = self._fields.get(key)
        return value if value is not None else default


class _FeedResult:
    def __init__(self, entries):
        self.entries = entries


def _patch_feedparser(monkeypatch, entries_by_url):
    def _fake_parse(url):
        return _FeedResult(entries_by_url.get(url, []))

    monkeypatch.setattr(rss_monitor_module.feedparser, "parse", _fake_parse)


# --- /rss_add, /rss_list ---

def test_rss_add_inserts_a_row_and_confirms(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.rss_add.callback(cog, interaction, "Ynet Tech", "https://ynet.example/rss", "555")

            async with db.execute("SELECT name, url, channel_id FROM rss_feeds") as cur:
                rows = await cur.fetchall()
            assert rows == [("Ynet Tech", "https://ynet.example/rss", 555)]
            assert "Ynet Tech" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_rss_add_rejects_non_numeric_channel_id(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.rss_add.callback(cog, interaction, "Ynet Tech", "https://ynet.example/rss", "not-a-number")

            async with db.execute("SELECT * FROM rss_feeds") as cur:
                rows = await cur.fetchall()
            assert rows == []
            assert "מספרי" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_rss_add_rejects_non_owner(tmp_path):
    # item: בדיקת באגים מקיפה - rss_add היה נגיש לכל משתמש (לא רק לבעל הבוט),
    # בניגוד לכל שאר פקודות הבוט - מוסיף URL שרירותי ל-DB שהבוט יביא ממנו
    # תוכן וישדר ל-channel_id שרירותי כל 30 דקות לתמיד.
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False))
            interaction = _make_interaction()

            await cog.rss_add.callback(cog, interaction, "Attacker Feed", "https://evil.example/rss", "555")

            async with db.execute("SELECT * FROM rss_feeds") as cur:
                rows = await cur.fetchall()
            assert rows == []
            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_rss_list_shows_feeds(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Ynet Tech", "https://ynet.example/rss", 555)])
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.rss_list.callback(cog, interaction)

            embed = interaction.response.send_message.call_args.kwargs["embed"]
            assert len(embed.fields) == 1
            assert embed.fields[0].name == "Ynet Tech"
        finally:
            await db.close()

    _run(scenario())


def test_rss_list_reports_when_empty(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.rss_list.callback(cog, interaction)

            assert "אין מקורות" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


# --- _is_seen / _mark_seen ---

def test_is_seen_false_for_a_brand_new_url(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            assert await cog._is_seen("https://example.com/article1") is False
        finally:
            await db.close()

    _run(scenario())


def test_is_seen_true_after_mark_seen(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            await cog._mark_seen("https://example.com/article1")
            assert await cog._is_seen("https://example.com/article1") is True
        finally:
            await db.close()

    _run(scenario())


def test_mark_seen_twice_is_idempotent(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            await cog._mark_seen("https://example.com/article1")
            await cog._mark_seen("https://example.com/article1")  # INSERT OR IGNORE - לא אמור לזרוק

            async with db.execute("SELECT COUNT(*) FROM seen_rss_entries") as cur:
                (count,) = await cur.fetchone()
            assert count == 1
        finally:
            await db.close()

    _run(scenario())


# --- fetch_rss_feeds (background loop body, called directly) ---

def test_fetch_rss_feeds_sends_embed_for_a_matching_new_entry(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA כרטיס מסך חדש", "https://feed.example/a1", summary="פרטים")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert len(channel.sent) == 1
            embed = channel.sent[0]["embed"]
            assert embed.title == "NVIDIA כרטיס מסך חדש"
            assert await cog._is_seen("https://feed.example/a1") is True
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_matches_on_summary_when_title_does_not_match(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("כתבה כללית", "https://feed.example/a1", summary="יש כאן אזכור ל-Steam")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert len(channel.sent) == 1
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_does_not_send_for_a_non_matching_entry_but_still_marks_seen(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("כתבה על משהו אחר לגמרי", "https://feed.example/a1", summary="שום קשר")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert channel.sent == []
            assert await cog._is_seen("https://feed.example/a1") is True
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_skips_entries_already_seen(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA חדש", "https://feed.example/a1", summary="")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))
            await cog._mark_seen("https://feed.example/a1")

            await cog.fetch_rss_feeds.coro(cog)

            assert channel.sent == []
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_skips_a_feed_whose_channel_no_longer_exists(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA חדש", "https://feed.example/a1", summary="")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            cog = _make_cog(FakeBot(db, channel=None))  # get_channel מחזיר None

            await cog.fetch_rss_feeds.coro(cog)

            # לא נזרקה חריגה, ולא סימנו את הכתבה כ"נראתה" - continue לפני שהגענו לזה בכלל
            assert await cog._is_seen("https://feed.example/a1") is False
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_only_processes_the_first_three_entries(tmp_path, monkeypatch):
    entries = [_Entry(f"NVIDIA כתבה {i}", f"https://feed.example/a{i}", summary="") for i in range(5)]
    _patch_feedparser(monkeypatch, {"https://feed.example/rss": entries})

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert len(channel.sent) == 3
            assert await cog._is_seen("https://feed.example/a3") is False
            assert await cog._is_seen("https://feed.example/a4") is False
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_cleans_up_seen_entries_older_than_30_days(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {})

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            await db.execute(
                "INSERT INTO seen_rss_entries (url, seen_at) VALUES (?, datetime('now', '-40 days'))",
                ("https://old.example/a1",),
            )
            await db.execute(
                "INSERT INTO seen_rss_entries (url, seen_at) VALUES (?, datetime('now'))",
                ("https://new.example/a1",),
            )
            await db.commit()
            cog = _make_cog(FakeBot(db))

            await cog.fetch_rss_feeds.coro(cog)

            async with db.execute("SELECT url FROM seen_rss_entries") as cur:
                remaining = {row[0] for row in await cur.fetchall()}
            assert remaining == {"https://new.example/a1"}
        finally:
            await db.close()

    _run(scenario())


def _days_ago(days):
    """struct_time ב-UTC, כמו published_parsed / updated_parsed של feedparser."""
    return time.gmtime(time.time() - days * 86400)


@pytest.mark.parametrize("date_field", ["published_parsed", "updated_parsed"])
def test_old_entry_whose_seen_row_was_cleaned_up_is_not_sent_again(tmp_path, monkeypatch, date_field):
    """פיד איטי, או בוט שלא רץ 40 יום: הניקוי מוחק את הרשומה של כתבה בת 40 יום שכבר נשלחה.
    בלי בדיקת התאריך היא נשלחה שוב לערוץ."""
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA כתבה ישנה", "https://feed.example/old", summary="", **{date_field: _days_ago(40)})],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            await db.execute("INSERT INTO seen_rss_entries (url, seen_at) VALUES (?, datetime('now', '-40 days'))", ("https://feed.example/old",))
            await db.commit()
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert channel.sent == []
            assert await cog._is_seen("https://feed.example/old") is True
        finally:
            await db.close()

    _run(scenario())


async def _seen_age_days(db, url):
    async with db.execute("SELECT julianday('now') - julianday(seen_at) FROM seen_rss_entries WHERE url = ?", (url,)) as cur:
        row = await cur.fetchone()
    return None if row is None else row[0]


def test_seen_at_is_refreshed_for_an_entry_still_in_the_feed(tmp_path, monkeypatch):
    """כתבה בלי תאריך שנשארת בראש פיד איטי: בלי רענון, הניקוי מחק אותה אחרי 30 יום והיא נשלחה שוב."""
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA בלי תאריך", "https://feed.example/undated", summary="")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            await db.execute("INSERT INTO seen_rss_entries (url, seen_at) VALUES (?, datetime('now', '-29 days'))", ("https://feed.example/undated",))
            await db.commit()
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert channel.sent == []
            assert await _seen_age_days(db, "https://feed.example/undated") < 1
        finally:
            await db.close()

    _run(scenario())


def test_undated_entry_still_in_the_feed_after_a_long_bot_downtime_is_not_resent(tmp_path, monkeypatch):
    """הבוט לא רץ 40 יום: הכתבה (בלי תאריך) עדיין בפיד - מרעננים אותה לפני הניקוי, ולכן היא לא נשלחת שוב."""
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA בלי תאריך", "https://feed.example/undated", summary="")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            await db.execute("INSERT INTO seen_rss_entries (url, seen_at) VALUES (?, datetime('now', '-40 days'))", ("https://feed.example/undated",))
            await db.execute("INSERT INTO seen_rss_entries (url, seen_at) VALUES (?, datetime('now', '-40 days'))", ("https://feed.example/gone",))
            await db.commit()
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert channel.sent == []
            assert await _seen_age_days(db, "https://feed.example/undated") < 1
            assert await _seen_age_days(db, "https://feed.example/gone") is None  # יצאה מהפיד - נמחקת כרגיל
        finally:
            await db.close()

    _run(scenario())


def test_recent_entry_is_still_sent_and_undated_entries_keep_the_old_behavior(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [
            _Entry("NVIDIA מלפני יומיים", "https://feed.example/recent", summary="", published_parsed=_days_ago(2)),
            _Entry("NVIDIA בלי תאריך", "https://feed.example/undated", summary=""),
        ],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert [sent["embed"].title for sent in channel.sent] == ["NVIDIA מלפני יומיים", "NVIDIA בלי תאריך"]
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_swallows_cleanup_error_and_still_processes_feeds(tmp_path, monkeypatch):
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("NVIDIA חדש", "https://feed.example/a1", summary="")],
    })

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))
            real_execute = db.execute

            def _failing_execute(sql, *a, **k):
                if "DELETE FROM seen_rss_entries" in sql:
                    raise RuntimeError("db busy")
                return real_execute(sql, *a, **k)

            db.execute = _failing_execute

            await cog.fetch_rss_feeds.coro(cog)  # לא אמור לזרוק, וממשיך לעבד את הפידים בכל זאת

            assert len(channel.sent) == 1
        finally:
            db.execute = real_execute
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_retries_a_transient_network_error_and_still_sends_the_embed(tmp_path, monkeypatch):
    # item: אימוץ retry/backoff משותף גם ב-RSS - כשל רשת חד-פעמי (לא bozo, לא
    # "אין תוצאות") לא אמור לדלג בשקט על הפיד עד הבדיקה הבאה בעוד 30 דקות.
    import utils.shared.retry as retry_module
    real_sleep = asyncio.sleep
    monkeypatch.setattr(retry_module.asyncio, "sleep", lambda d: real_sleep(0))  # לא לחכות באמת בטסט

    attempts = {"n": 0}

    def _flaky_parse(url):
        if attempts["n"] == 0:
            attempts["n"] += 1
            raise TimeoutError("feed server timed out")
        return _FeedResult([_Entry("NVIDIA כרטיס מסך חדש", "https://feed.example/a1", summary="פרטים")])

    monkeypatch.setattr(rss_monitor_module.feedparser, "parse", _flaky_parse)

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert attempts["n"] == 1, "הכשל הראשון היה אמור לקרות, ואז ניסיון חוזר שהצליח"
            assert len(channel.sent) == 1, "אחרי הניסיון החוזר המוצלח, ההתראה עדיין הייתה אמורה להישלח"
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_swallows_per_feed_error_and_continues_to_next_feed(tmp_path, monkeypatch):
    def _fake_parse(url):
        if "broken" in url:
            raise RuntimeError("feed server unreachable")
        return _FeedResult([_Entry("NVIDIA חדש", "https://feed.example/a1", summary="")])

    monkeypatch.setattr(rss_monitor_module.feedparser, "parse", _fake_parse)

    async def scenario():
        db = await _open_db(tmp_path, feeds=[
            ("Broken Feed", "https://broken.example/rss", 555),
            ("Good Feed", "https://feed.example/rss", 555),
        ])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert len(channel.sent) == 1
        finally:
            await db.close()

    _run(scenario())


def test_fetch_rss_feeds_with_no_configured_feeds_does_nothing(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.fetch_rss_feeds.coro(cog)

            assert channel.sent == []
        finally:
            await db.close()

    _run(scenario())


def test_before_rss_waits_until_bot_is_ready(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)

            await cog.before_rss()

            bot.wait_until_ready.assert_awaited_once()
        finally:
            await db.close()

    _run(scenario())


def test_cog_unload_cancels_the_background_loop(tmp_path):
    async def scenario():
        db = await _open_db(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            cog.fetch_rss_feeds = MagicMock()

            cog.cog_unload()

            cog.fetch_rss_feeds.cancel.assert_called_once()
        finally:
            await db.close()

    _run(scenario())


def test_setup_adds_the_cog_to_the_bot(tmp_path, monkeypatch):
    def _fake_init(self, bot):
        self.bot = bot
        self.keywords = []

    monkeypatch.setattr(rss_monitor_module.RSSMonitor, "__init__", _fake_init)

    async def scenario():
        db = await _open_db(tmp_path)
        try:
            bot = FakeBot(db)
            bot.add_cog = AsyncMock()

            await rss_monitor_module.setup(bot)

            bot.add_cog.assert_awaited_once()
            assert isinstance(bot.add_cog.call_args.args[0], RSSMonitor)
        finally:
            await db.close()

    _run(scenario())


def test_without_keywords_every_new_entry_is_sent_and_the_list_comes_from_config(tmp_path, monkeypatch):
    """30.10.2026: מילות הסינון הן "rss_keywords" ב-config.json (utils/shared/install_profile); רשימה ריקה = הכל עובר."""
    _patch_feedparser(monkeypatch, {
        "https://feed.example/rss": [_Entry("כתבה על משהו אחר לגמרי", "https://feed.example/a1", summary="שום קשר")],
    })
    monkeypatch.setattr(rss_monitor_module.install_profile, "read", lambda _path: {"rss_keywords": []})

    async def scenario():
        db = await _open_db(tmp_path, feeds=[("Tech Feed", "https://feed.example/rss", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))
            cog.keywords = None   # כמו ב-__init__ האמיתי: מהקובץ
            await cog.fetch_rss_feeds.coro(cog)
            assert len(channel.sent) == 1
        finally:
            await db.close()

    _run(scenario())
