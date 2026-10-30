import discord
from discord.ext import commands, tasks
from discord import app_commands
import feedparser
import asyncio
import calendar
import time

from utils.shared.retry import call_with_retry_async
from utils.shared import data_paths, install_profile

# כמה זמן זוכרים כתבה שכבר נראתה (seen_rss_entries). כתבה שפורסמה לפני יותר מזה כבר לא נשלחת:
# הרשומה שלה אולי נמחקה בניקוי, ובלי הבדיקה הזו פיד איטי (3 הכתבות האחרונות בו ישנות מ-30 יום)
# שלח אותן מחדש כל 30 יום - וגם בהפעלה הראשונה אחרי הפסקה ארוכה של הבוט.
SEEN_RETENTION_DAYS = 30


def _entry_age_days(entry, now=None):
    """גיל הכתבה בימים לפי published_parsed (או updated_parsed), או None כשאין לה תאריך.
    feedparser מחזיר struct_time ב-UTC - לכן calendar.timegm ולא time.mktime."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return ((now if now is not None else time.time()) - calendar.timegm(parsed)) / 86400
    except (TypeError, ValueError, OverflowError):
        return None


def _is_retryable_network_error(exc):
    """True אם סביר שניסיון חוזר יעזור - בעיית רשת/timeout זמנית. feedparser
    בדרך כלל לא זורק על כשל רשת (מסמן bozo=1 ומחזיר תוצאה ריקה במקום), אבל
    כשהוא כן זורק (למשל timeout ברמת urllib) זו בדיוק הסיטואציה הזמנית שניסיון
    חוזר עוזר לה."""
    return isinstance(exc, (OSError, TimeoutError))


async def _fetch_feed(loop, url):
    """קריאת feedparser.parse יחידה (ב-executor, לא חוסמת את ה-event loop) עם
    retry/backoff (item: אימוץ retry/backoff משותף - עד עכשיו כשל רשת חד-פעמי
    היה מדלג בשקט על הפיד הזה עד הבדיקה הבאה בעוד 30 דקות)."""
    async def _do_fetch():
        return await loop.run_in_executor(None, feedparser.parse, url)

    return await call_with_retry_async(_do_fetch, max_attempts=3, is_retryable=_is_retryable_network_error, base_delay=2.0)


class RSSMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # 30.10.2026: מילות הסינון - "rss_keywords" ב-config.json (utils/shared/install_profile), נקראות בכל סבב כדי ששינוי
        # ייכנס בלי הפעלה מחדש. רשימה ריקה = כל הכתבות עוברות. None כאן = מהקובץ; טסטים קובעים רשימה ישירות
        self.keywords = None
        self.fetch_rss_feeds.start()

    def cog_unload(self):
        self.fetch_rss_feeds.cancel()

    async def _is_seen(self, url):
        async with self.bot.db.execute("SELECT 1 FROM seen_rss_entries WHERE url = ?", (url,)) as cursor:
            return await cursor.fetchone() is not None

    async def _mark_seen(self, url):
        # upsert ולא INSERT OR IGNORE: כתבה שעדיין בפיד מקבלת seen_at חדש בכל סבב, כך שהניקוי (30 יום)
        # מוחק רק כתבות שכבר יצאו מהפיד. קודם כתבה בלי תאריך שנשארה בראש פיד איטי נשלחה שוב כל 30 יום.
        await self.bot.db.execute(
            "INSERT INTO seen_rss_entries (url) VALUES (?) ON CONFLICT(url) DO UPDATE SET seen_at = CURRENT_TIMESTAMP",
            (url,),
        )
        await self.bot.db.commit()

    async def owner_only(self, interaction: discord.Interaction) -> bool:
        """מגביל את הוספת מקורות RSS לבעל הבוט בלבד - בלעדיו כל משתמש בשרת יכול
        להטמין URL שרירותי שהבוט יביא ממנו תוכן וישדר ל-channel_id שרירותי כל 30
        דקות לתמיד (item: בדיקת באגים מקיפה - נמצא חוסר עקבי מול שאר פקודות הבוט,
        שכולן כבר בודקות is_owner)."""
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="rss_add", description="הוספת מקור RSS חדש למערכת")
    async def rss_add(self, interaction: discord.Interaction, name: str, url: str, channel_id: str):
        if not await self.owner_only(interaction):
            return
        try:
            chan_id_int = int(channel_id)
        except ValueError:
            await interaction.response.send_message("❌ channel_id חייב להיות מספרי.", ephemeral=True)
            return

        async with self.bot.db.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO rss_feeds (name, url, channel_id) VALUES (?, ?, ?)",
                (name, url, chan_id_int)
            )
        await self.bot.db.commit()
        await interaction.response.send_message(f"📰 מקור ה-RSS **{name}** נוסף בהצלחה!", ephemeral=True)

    @app_commands.command(name="rss_list", description="הצגת כל מקורות ה-RSS שנמצאים במעקב")
    async def rss_list(self, interaction: discord.Interaction):
        async with self.bot.db.cursor() as cursor:
            await cursor.execute("SELECT name, url, channel_id FROM rss_feeds")
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("אין מקורות RSS במעקב כרגע.", ephemeral=True)
            return

        embed = discord.Embed(title="📰 מקורות RSS במעקב", color=discord.Color.orange())
        for row in rows:
            embed.add_field(name=row[0], value=f"{row[1]}\nערוץ: {row[2]}", inline=False)
        await interaction.response.send_message(embed=embed)

    async def _cleanup_seen(self):
        # ניקוי כתבות ישנות מהטבלה (מעבר ל-30 יום אין טעם לזכור אותן) - מונע צמיחה
        # בלתי מוגבלת של הטבלה, בדיוק כמו שה-set הישן היה גדל בלי הגבלה בזיכרון.
        # רץ אחרי מעבר הפידים: כתבה שעדיין בפיד כבר קיבלה seen_at חדש (_mark_seen), גם אחרי הפסקה
        # ארוכה של הבוט. כתבה ישנה שנמחקה מכאן לא נשלחת שוב - ראו _entry_age_days.
        try:
            await self.bot.db.execute("DELETE FROM seen_rss_entries WHERE seen_at < datetime('now', ?)", (f"-{SEEN_RETENTION_DAYS} days",))
            await self.bot.db.commit()
        except Exception as e:
            print(f"שגיאה בניקוי seen_rss_entries ישנים: {e}")

    @tasks.loop(minutes=30)
    async def fetch_rss_feeds(self):
        async with self.bot.db.cursor() as cursor:
            await cursor.execute("SELECT name, url, channel_id FROM rss_feeds")
            feeds = await cursor.fetchall()
        keywords = self.keywords if self.keywords is not None else \
            install_profile.read(data_paths.path(data_paths.CONFIG))["rss_keywords"]

        for name, url, channel_id in feeds:
            try:
                # קריאת הפיד בצורה בטוחה שלא תוקעת את ה-Loop
                loop = asyncio.get_event_loop()
                parsed_feed = await _fetch_feed(loop, url)

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                # לוקחים את 3 הכתבות האחרונות בכל סבב
                for entry in parsed_feed.entries[:3]:
                    if await self._is_seen(entry.link):
                        await self._mark_seen(entry.link)  # עדיין בפיד - מרעננים את seen_at
                        continue

                    # ישנה מחלון הזיכרון - כנראה כבר נשלחה פעם (והרשומה נמחקה בניקוי): מסמנים בלי לשלוח.
                    # כתבה בלי תאריך ממשיכה כמו קודם.
                    age_days = _entry_age_days(entry)
                    if age_days is not None and age_days > SEEN_RETENTION_DAYS:
                        await self._mark_seen(entry.link)
                        continue

                    # סינון חכם: בודק אם מילת מפתח קיימת בכותרת או בתקציר (בלי מילים - הכל עובר)
                    title_match = any(kw.lower() in entry.title.lower() for kw in keywords)
                    summary_match = any(kw.lower() in entry.get("summary", "").lower() for kw in keywords)

                    if not keywords or title_match or summary_match:
                        embed = discord.Embed(
                            title=entry.title,
                            url=entry.link,
                            description=entry.get("summary", "אין תקציר זמין לכתבה זו.")[:250] + "...",
                            color=discord.Color.orange()
                        )
                        embed.set_author(name=f"פיד חדש מ: {name}")
                        await channel.send(embed=embed)

                    await self._mark_seen(entry.link)
            except Exception as e:
                print(f"שגיאה בעדכון פיד RSS ({name}): {e}")

        await self._cleanup_seen()

    @fetch_rss_feeds.before_loop
    async def before_rss(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RSSMonitor(bot))