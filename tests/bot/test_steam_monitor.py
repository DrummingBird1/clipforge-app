# tests/bot/test_steam_monitor.py
#
# בודק cogs/steam_monitor.py - bot.db הוא aiosqlite אמיתי (tmp_path, טבלת
# steam_games אמיתית), אותו עיקרון כמו test_approval_cog.py. הרשת (Steam API
# עצמו) מדומה עם FakeSession/FakeResponse - זה החלק החוצה-לתהליך היחיד שאין
# לו טעם להריץ אמיתי בטסט. הcog נבנה עם __new__ (לא __init__) כדי לא להפעיל
# בפועל את check_steam_deals.start() - דורש event loop רץ כבר, אותו דפוס
# בדיוק כמו test_approval_cog.py.
import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import aiosqlite


import cogs.steam_monitor as steam_monitor_module
from cogs.steam_monitor import SteamMonitor


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


def _make_cog(bot):
    cog = SteamMonitor.__new__(SteamMonitor)
    cog.bot = bot
    return cog


def _make_interaction(user_id=1):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def _open_db_with_steam_games(tmp_path, rows=()):
    db = await aiosqlite.connect(str(tmp_path / "test.db"))
    await db.execute("CREATE TABLE steam_games (name TEXT, app_id TEXT, channel_id INTEGER)")
    for name, app_id, channel_id in rows:
        await db.execute("INSERT INTO steam_games (name, app_id, channel_id) VALUES (?, ?, ?)", (name, app_id, channel_id))
    await db.commit()
    return db


class _FakeResponse:
    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json_data = json_data if json_data is not None else {}

    async def json(self, content_type=None):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    """url -> _FakeResponse (החזרה על exact-substring match ראשון) - digs.get()
    מוגן ב-AssertionError במקום להחזיר בשוגג None ל-URL שלא צפינו לו."""

    def __init__(self, responses):
        self._responses = list(responses)

    def get(self, url):
        for substr, resp in self._responses:
            if substr in url:
                return resp
        raise AssertionError(f"unexpected URL requested: {url}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_session(monkeypatch, responses):
    session = _FakeSession(responses)
    monkeypatch.setattr(steam_monitor_module.aiohttp, "ClientSession", lambda: session)
    return session


# --- /steam_watch ---

def test_steam_watch_inserts_a_row_and_confirms(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_watch.callback(cog, interaction, "Hades", "1145360", "555")

            async with db.execute("SELECT name, app_id, channel_id FROM steam_games") as cur:
                rows = await cur.fetchall()
            assert rows == [("Hades", "1145360", 555)]
            assert "Hades" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_steam_watch_rejects_non_numeric_channel_id(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_watch.callback(cog, interaction, "Hades", "1145360", "not-a-number")

            async with db.execute("SELECT * FROM steam_games") as cur:
                rows = await cur.fetchall()
            assert rows == []
            assert "מספרי" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_steam_watch_rejects_non_owner(tmp_path):
    # item: בדיקת באגים מקיפה - steam_watch היה נגיש לכל משתמש, בניגוד לכל
    # שאר פקודות הבוט.
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False))
            interaction = _make_interaction()

            await cog.steam_watch.callback(cog, interaction, "Hades", "1145360", "555")

            async with db.execute("SELECT * FROM steam_games") as cur:
                rows = await cur.fetchall()
            assert rows == []
            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


# --- /steam_list ---

def test_steam_list_shows_tracked_games(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Hades", "1145360", 555)])
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_list.callback(cog, interaction)

            embed = interaction.response.send_message.call_args.kwargs["embed"]
            assert len(embed.fields) == 1
            assert embed.fields[0].name == "Hades"
            assert "1145360" in embed.fields[0].value
        finally:
            await db.close()

    _run(scenario())


def test_steam_list_reports_when_empty(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_list.callback(cog, interaction)

            assert "אין משחקים" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


# --- /steam_wishlist_sync ---

def test_wishlist_sync_rejects_non_owner(tmp_path, monkeypatch):
    # item: בדיקת באגים מקיפה - steam_wishlist_sync היה נגיש לכל משתמש, בניגוד
    # לכל שאר פקודות הבוט - וחושף את ה-Wishlist האישי של הבעל (STEAM_ID) לכל
    # channel_id שרירותי שהתוקף בוחר.
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db, is_owner=False))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            async with db.execute("SELECT * FROM steam_games") as cur:
                rows = await cur.fetchall()
            assert rows == []
            assert "בעל הבוט" in interaction.response.send_message.call_args.args[0]
            interaction.response.defer.assert_not_awaited()
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_requires_steam_id_secret(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: None)

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            assert "STEAM_ID" in interaction.response.send_message.call_args.args[0]
            interaction.response.defer.assert_not_awaited()
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_rejects_non_numeric_channel_id(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "not-a-number")

            assert "מספרי" in interaction.response.send_message.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_adds_new_games_with_fetched_names(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")
    _patch_session(monkeypatch, [
        ("GetWishlist", _FakeResponse(200, {"response": {"items": [{"appid": 1145360}]}})),
        ("appdetails", _FakeResponse(200, {"1145360": {"success": True, "data": {"name": "Hades"}}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            interaction.response.defer.assert_awaited_once_with(ephemeral=True)
            async with db.execute("SELECT name, app_id, channel_id FROM steam_games") as cur:
                rows = await cur.fetchall()
            assert rows == [("Hades", "1145360", 555)]
            assert "Hades" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_skips_games_already_tracked(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")
    _patch_session(monkeypatch, [
        ("GetWishlist", _FakeResponse(200, {"response": {"items": [{"appid": 1145360}]}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Hades", "1145360", 555)])
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            async with db.execute("SELECT COUNT(*) FROM steam_games") as cur:
                (count,) = await cur.fetchone()
            assert count == 1
            assert "כבר נמצאים" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_falls_back_to_app_id_as_name_when_details_fetch_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")
    _patch_session(monkeypatch, [
        ("GetWishlist", _FakeResponse(200, {"response": {"items": [{"appid": 999}]}})),
        ("appdetails", _FakeResponse(500, {})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            async with db.execute("SELECT name FROM steam_games") as cur:
                (name,) = await cur.fetchone()
            assert name == "999"
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_empty_wishlist_message(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")
    _patch_session(monkeypatch, [
        ("GetWishlist", _FakeResponse(200, {"response": {"items": []}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            assert "לא נמצאו פריטים" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_reports_a_failed_wishlist_request(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")
    _patch_session(monkeypatch, [
        ("GetWishlist", _FakeResponse(403, {})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            assert "403" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_reports_unexpected_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")

    class _ExplodingSession:
        async def __aenter__(self):
            raise RuntimeError("network is down")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(steam_monitor_module.aiohttp, "ClientSession", lambda: _ExplodingSession())

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            assert "שגיאה בסנכרון" in interaction.followup.send.call_args.args[0]
        finally:
            await db.close()

    _run(scenario())


# --- check_steam_deals (background loop body, called directly) ---

def test_check_steam_deals_sends_an_embed_when_a_discount_is_found(tmp_path, monkeypatch):
    _patch_session(monkeypatch, [
        ("appdetails", _FakeResponse(200, {"1145360": {"success": True, "data": {
            "is_free": False,
            "price_overview": {"discount_percent": 50, "final_formatted": "50 ₪", "initial_formatted": "100 ₪"},
            "header_image": "https://example.com/hades.jpg",
        }}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Hades", "1145360", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.check_steam_deals.coro(cog)

            assert len(channel.sent) == 1
            embed = channel.sent[0]["embed"]
            assert "Hades" in embed.title
        finally:
            await db.close()

    _run(scenario())


def test_check_steam_deals_does_not_notify_when_there_is_no_discount(tmp_path, monkeypatch):
    _patch_session(monkeypatch, [
        ("appdetails", _FakeResponse(200, {"1145360": {"success": True, "data": {
            "is_free": False,
            "price_overview": {"discount_percent": 0, "final_formatted": "100 ₪", "initial_formatted": "100 ₪"},
        }}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Hades", "1145360", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.check_steam_deals.coro(cog)

            assert channel.sent == []
        finally:
            await db.close()

    _run(scenario())


def test_check_steam_deals_skips_free_games(tmp_path, monkeypatch):
    _patch_session(monkeypatch, [
        ("appdetails", _FakeResponse(200, {"1145360": {"success": True, "data": {"is_free": True}}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Hades", "1145360", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.check_steam_deals.coro(cog)

            assert channel.sent == []
        finally:
            await db.close()

    _run(scenario())


def test_check_steam_deals_swallows_per_game_errors_and_continues(tmp_path, monkeypatch):
    # שני משחקים - הראשון גורם לחריגה אמיתית (price_overview["discount_percent"]
    # חסר, KeyError ממשי - לא רק status לא-200), השני עדיין אמור להיבדק
    # ולשלוח התראה כרגיל, כלומר החריגה על הראשון לא עוצרת את הלולאה.
    _patch_session(monkeypatch, [
        ("appdetails?appids=111", _FakeResponse(200, {"111": {"success": True, "data": {
            "is_free": False, "price_overview": {},
        }}})),
        ("appdetails?appids=222", _FakeResponse(200, {"222": {"success": True, "data": {
            "is_free": False,
            "price_overview": {"discount_percent": 20, "final_formatted": "80 ₪", "initial_formatted": "100 ₪"},
        }}})),
    ])

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Broken", "111", 555), ("Hades", "222", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.check_steam_deals.coro(cog)

            assert len(channel.sent) == 1
            assert channel.sent[0]["embed"].title == "🚨 הנחת Steam מטורפת עבור Hades! 🚨"
        finally:
            await db.close()

    _run(scenario())


def test_check_steam_deals_retries_a_transient_network_error_and_still_sends_the_embed(tmp_path, monkeypatch):
    # item: אימוץ retry/backoff משותף גם ב-Steam - כשל רשת חד-פעמי (לא שגיאת
    # HTTP אמיתית) על appdetails לא אמור לדלג בשקט על המשחק עד הבדיקה הבאה
    # בעוד 12 שעות - ניסיון חוזר אמיתי (_fetch_appdetails) אמור לתפוס אותו.
    import utils.shared.retry as retry_module
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(retry_module.asyncio, "sleep", lambda d: _real_sleep(0))  # לא לחכות באמת בטסט

    attempts = {"n": 0}

    class _FlakyOnceSession(_FakeSession):
        def get(self, url):
            if "appdetails" in url and attempts["n"] == 0:
                attempts["n"] += 1
                raise aiohttp.ClientConnectionError("connection reset")
            return super().get(url)

    session = _FlakyOnceSession([
        ("appdetails", _FakeResponse(200, {"1145360": {"success": True, "data": {
            "is_free": False,
            "price_overview": {"discount_percent": 50, "final_formatted": "50 ₪", "initial_formatted": "100 ₪"},
            "header_image": "https://example.com/hades.jpg",
        }}})),
    ])
    monkeypatch.setattr(steam_monitor_module.aiohttp, "ClientSession", lambda: session)

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path, rows=[("Hades", "1145360", 555)])
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.check_steam_deals.coro(cog)

            assert attempts["n"] == 1, "הכשל הראשון היה אמור לקרות, ואז ניסיון חוזר שהצליח"
            assert len(channel.sent) == 1, "אחרי הניסיון החוזר המוצלח, ההתראה עדיין הייתה אמורה להישלח"
            assert "Hades" in channel.sent[0]["embed"].title
        finally:
            await db.close()

    _run(scenario())


def test_wishlist_sync_swallows_per_item_details_fetch_error_and_uses_app_id(tmp_path, monkeypatch):
    # get() על ה-details_url זורק ישירות (לא רק status לא-200) - מוודא שה-
    # except Exception: pass הפנימי (סביב שליפת השם) באמת תופס את זה.
    class _ExplodingDetailsSession(_FakeSession):
        def get(self, url):
            if "appdetails" in url:
                raise RuntimeError("connection reset")
            return super().get(url)

    session = _ExplodingDetailsSession([("GetWishlist", _FakeResponse(200, {"response": {"items": [{"appid": 777}]}}))])
    monkeypatch.setattr(steam_monitor_module.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(steam_monitor_module, "get_secret", lambda name: "76500000000000000")

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            interaction = _make_interaction()

            await cog.steam_wishlist_sync.callback(cog, interaction, "555")

            async with db.execute("SELECT name FROM steam_games") as cur:
                (name,) = await cur.fetchone()
            assert name == "777"
        finally:
            await db.close()

    _run(scenario())


def test_check_steam_deals_with_no_tracked_games_does_nothing(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            channel = FakeChannel()
            cog = _make_cog(FakeBot(db, channel=channel))

            await cog.check_steam_deals.coro(cog)

            assert channel.sent == []
        finally:
            await db.close()

    _run(scenario())


def test_before_check_waits_until_bot_is_ready(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            bot = FakeBot(db)
            cog = _make_cog(bot)

            await cog.before_check()

            bot.wait_until_ready.assert_awaited_once()
        finally:
            await db.close()

    _run(scenario())


def test_cog_unload_cancels_the_background_loop(tmp_path):
    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            cog = _make_cog(FakeBot(db))
            cog.check_steam_deals = MagicMock()

            cog.cog_unload()

            cog.check_steam_deals.cancel.assert_called_once()
        finally:
            await db.close()

    _run(scenario())


def test_setup_adds_the_cog_to_the_bot(tmp_path, monkeypatch):
    # __init__ האמיתי קורא ל-check_steam_deals.start() - דורש event loop רץ,
    # אז מנטרלים אותו כאן (לא רלוונטי לבדיקת setup() עצמה) בדיוק כמו שאר
    # הטסטים בקובץ הזה שבונים cog עם __new__ במקום __init__.
    monkeypatch.setattr(steam_monitor_module.SteamMonitor, "__init__", lambda self, bot: setattr(self, "bot", bot))

    async def scenario():
        db = await _open_db_with_steam_games(tmp_path)
        try:
            bot = FakeBot(db)
            bot.add_cog = AsyncMock()

            await steam_monitor_module.setup(bot)

            bot.add_cog.assert_awaited_once()
            assert isinstance(bot.add_cog.call_args.args[0], SteamMonitor)
        finally:
            await db.close()

    _run(scenario())
