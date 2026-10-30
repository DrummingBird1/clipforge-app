# main.py
import asyncio
import datetime
import json
import os
import sys
import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv

# UTF-8 ל-stdout/stderr, כמו בסקריפטים: שרת הדפדפן קורא את הפלט ב-utf-8. בלי זה, ב-Windows בעברית פלט
# לצינור (pipe) יוצא ב-cp1255 - השורה העברית הראשונה הפילה את קורא הלוג בשרת, והוא הפעיל עוד עותק של
# הבוט כאילו הבוט קרס (בזמן שהראשון עדיין רץ).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure") and (_stream.encoding or "").lower() != "utf-8":
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# הגדרת נתיבי בסיס מוחלטים למניעת בעיות תיקיית עבודה
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# src/entrypoints/ תחת שורש הפרויקט - כל קוד המקור הראשוני (cogs/ui/utils/וכו')
# יושב תחת src/, לא בשורש עצמו, אז זה מה שצריך להיות ב-sys.path כדי ש-"utils.*"/
# "cogs.*" למטה ייובאו בהצלחה - לא BASE_DIR (שורש הפרויקט) עצמו.
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# src/cogs/ - לא <שורש>/cogs: מאז שהקוד עבר ל-src/ (6.9.2026) החיפוש בשורש לא מצא כלום,
# והבוט עלה בלי אף cog (בלי פקודות, בלי ניטור RSS/Steam, בלי תזכורות האישור).
COGS_DIR = os.path.join(SRC_DIR, "cogs")

# קוד יציאה לשגיאת הגדרה - אין טוקן, Discord דחה את הטוקן, או חסר Message Content Intent. הפעלה מחדש לא
# תעזור עד שהמשתמש יתקן משהו, ולכן הקוד שונה מקריסה רגילה (1): מי שמפעיל את הבוט ומפעיל אותו מחדש אחרי
# קריסה (_run_bot_process_loop ב-web/bot_process.py) יכול לעצור על הקוד הזה במקום לנסות שוב ושוב.
# לא לשנות את השם: web_app.py קורא אותו מכאן ב-ast, ובלי השם כל יציאה נחשבת קריסה (גם הטסטים קוראים אותו).
CONFIG_ERROR_EXIT_CODE = 2

from utils.shared.data_dir import DATA_DIR
from utils.shared import data_paths
os.makedirs(DATA_DIR, exist_ok=True)

from utils.shared.logging_setup import setup_persistent_logging
setup_persistent_logging("bot")

load_dotenv(os.path.join(BASE_DIR, ".env"))

# טעינת הגדרות בסיסיות בצורה בטוחה
CONFIG_PATH = data_paths.path(data_paths.CONFIG)
# 30.10.2026: ההגדרות שתלויות בהתקנה (שפה, סינון RSS, אזור Steam...) נכתבות פעם אחת - גם כשהבוט עולה לפני הממשק
from utils.shared import install_profile  # noqa: E402 - אחרי data_paths וה-sys.path שלמעלה
try:
    install_profile.ensure(CONFIG_PATH, CONFIG_PATH + ".lock")
except OSError as e:
    print(f"[אזהרה] לא הצלחתי לכתוב את הגדרות ההתקנה ל-data/config.json: {e}")
config = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[אזהרה] שגיאה בקריאת data/config.json: {e}")

from utils.shared.secrets_vault import get_secret
DISCORD_TOKEN = get_secret("DISCORD_TOKEN") or config.get("discord_token")
if not DISCORD_TOKEN:
    print("[שגיאה] לא נמצא DISCORD_TOKEN. הגדר אותו בקובץ .env (מומלץ) או ב-data/config.json.")
    sys.exit(CONFIG_ERROR_EXIT_CODE)


class ClipForgeBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = None
        # UTC כדי לא להסתבך עם אזורי זמן/שעון קיץ - /status (cogs/status_cog.py)
        # רק מחסר משעון UTC נוכחי, אף פעם לא צריך להציג את זה למשתמש ישירות.
        self.started_at = datetime.datetime.now(datetime.timezone.utc)

    async def setup_hook(self):
        # חיבור לבסיס הנתונים בנתיב מוחלט
        db_path = data_paths.path(data_paths.BOT_DB)
        self.db = await aiosqlite.connect(db_path)
        # WAL: מאפשר קריאות מקבילות (מה-GUI/מהתזמון האוטומטי) בזמן שהבוט כותב לאותו
        # קובץ DB, במקום לנעול את כל הקובץ כמו ברירת המחדל של SQLite.
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA busy_timeout=10000")
        await self.init_db()

        # סריקה וטעינה אוטומטית של כל ה-Cogs
        await self.load_all_cogs()

    async def load_all_cogs(self):
        if not os.path.isdir(COGS_DIR):
            print(f"[שגיאה] תיקיית ה-Cogs לא נמצאה: {COGS_DIR} - הבוט עולה בלי פקודות.")
            return
        for filename in sorted(os.listdir(COGS_DIR)):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    cog_name = f"cogs.{filename[:-3]}"
                    if cog_name in self.extensions:
                        await self.reload_extension(cog_name)
                    else:
                        await self.load_extension(cog_name)
                    print(f"המודול {cog_name} נטען/רוען בהצלחה.")
                except Exception as e:
                    print(f"שגיאה בטעינת {filename}: {e}")

    async def init_db(self):
        # יצירת טבלאות בסיס הנתונים
        async with self.db.cursor() as cursor:
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rss_feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    url TEXT,
                    channel_id INTEGER
                )
            """
            )
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS steam_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    app_id TEXT,
                    channel_id INTEGER
                )
            """
            )
            # מחליף את self.seen_urls (set בזיכרון בלבד) ב-rss_monitor.py - היה גדל
            # ללא הגבלה למשך חיי התהליך, וגם מתאפס בכל restart של הבוט (סיכון
            # לפרסום כפול של אותה כתבה אחרי restart).
            await cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_rss_entries (
                    url TEXT PRIMARY KEY,
                    seen_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
        await self.db.commit()

    # --- פונקציות עזר לבסיס הנתונים ---
    async def db_execute(self, query, params=()):
        async with self.db.cursor() as cursor:
            await cursor.execute(query, params)
            await self.db.commit()
            return cursor.lastrowid

    async def db_fetchall(self, query, params=()):
        async with self.db.cursor() as cursor:
            await cursor.execute(query, params)
            return await cursor.fetchall()

    async def close(self):
        if self.db:
            await self.db.close()
        await super().close()


bot = ClipForgeBot()


@bot.event
async def on_ready():
    print(f"[{bot.user.name}] מחובר ומוכן לעבודה!")

    # סנכרון פקודות הסלאש
    try:
        guild_id = config.get("test_guild_id")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(
                f"סונכרנו {len(synced)} פקודות סלאש באופן מיידי לשרת הבדיקות ({guild_id})."
            )
        else:
            synced = await bot.tree.sync()
            print(f"סונכרנו {len(synced)} פקודות סלאש גלובליות בהצלחה.")
    except Exception as e:
        print(f"שגיאה בסנכרון פקודות: {e}")
    print("-----------------------------------")


# פקודת Admin לטעינה מחדש בלייב של ה-Cogs
@bot.command(name="reload_cogs")
@commands.is_owner()
async def reload_cogs_cmd(ctx):
    await bot.load_all_cogs()
    await ctx.send("🔄 כל המודולים (Cogs) רועננו בהצלחה!")


async def main():
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    # שגיאות הגדרה נפוצות - הודעה אחת ברורה במקום traceback ארוך של discord.py בלוג הבוט
    try:
        asyncio.run(main())
    except discord.LoginFailure:
        print("[שגיאה] Discord דחה את ה-DISCORD_TOKEN (טוקן שגוי או שבוטל). צור טוקן חדש בפורטל המפתחים של Discord ועדכן אותו ב-.env או ב-Credential Manager.")
        sys.exit(CONFIG_ERROR_EXIT_CODE)
    except discord.PrivilegedIntentsRequired:
        print("[שגיאה] הבוט צריך את Message Content Intent - הפעל אותו בפורטל המפתחים של Discord (Bot > Privileged Gateway Intents).")
        sys.exit(CONFIG_ERROR_EXIT_CODE)
    except KeyboardInterrupt:
        print("הבוט נעצר.")