# cogs/voice_presence_cog.py
#
# רושם תמונות-מצב תקופתיות (snapshots) של מי נמצא בכל ערוץ קול (item: friend
# detection via Discord voice channel presence) - בכוונה *לא* מבוסס אירועי
# join/leave (on_voice_state_update): לוג מבוסס-אירועים מפספס משתמשים שכבר
# היו בערוץ לפני שהבוט עלה, ומאבד סנכרון לגמרי אחרי כל נפילה/הפעלה מחדש של
# הבוט (leave-בלי-join-תואם, או להיפך). snapshot תקופתי הוא self-healing
# מטבעו - כל snapshot עצמאי לגמרי מקודמו, אותו רעיון בדיוק כמו
# utils/shared/hardware_history.py's דגימה תקופתית.
#
# הקורלציה בפועל (איזה snapshot-ים רלוונטיים לאיזה קליפ) קורית מאוחר יותר,
# כש-cogs/approval_cog.py סורק קליפים חדשים ב-_do_scan וקורא ל-
# get_present_usernames_for_clip כאן - ראו שם. חלון-קורלציה (לא נקודת-זמן
# מדויקת) כי mtime הקובץ הוא בקירוב "מתי הרגע נשמר", לא "מתי הרגע קרה
# בפועל" - Replay Buffer של OBS שומר את N השניות/הדקות *שקדמו* לרגע השמירה.

import json
import os
from datetime import datetime, timedelta, timezone

from discord.ext import commands, tasks

from utils.shared import data_paths
from utils.shared.data_dir import DATA_DIR

SNAPSHOT_INTERVAL_SECONDS = 60
RETENTION_DAYS = 14
DEFAULT_CORRELATION_WINDOW_SECONDS = 120


def get_capture_voice_channel_id():
    """קורא capture_voice_channel_id מ-data/rocket_settings.json - אותו קובץ
    הגדרות בדיוק שגם utils/bot/approval_store.py's get_rocket_input_dir קורא,
    ניתן להגדרה גם דרך ui/rocket_settings_tab.py וגם web_app.py."""
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS, DATA_DIR)   # DATA_DIR של המודול - טסטים מחליפים אותו
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f).get("capture_voice_channel_id") or None
        except Exception:
            pass
    return None


class VoicePresenceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.snapshot_loop.start()

    def cog_unload(self):
        self.snapshot_loop.cancel()

    async def _ensure_table(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS voice_presence_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER,
                user_id INTEGER,
                username TEXT,
                snapshot_at TEXT
            )
        """)
        await self.bot.db.commit()

    async def _take_snapshot(self):
        await self._ensure_table()
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.bot:
                        continue
                    await self.bot.db.execute(
                        "INSERT INTO voice_presence_snapshots (channel_id, user_id, username, snapshot_at) VALUES (?, ?, ?, ?)",
                        (channel.id, member.id, str(member.display_name), now_iso),
                    )
        # שימור מוגבל (item: personal-data retention hygiene) - זהה בעיקרון
        # ל-utils/shared/hardware_history.py's RETENTION_DAYS, כדי שהטבלה לא תגדל ללא
        # הגבלה על פני חודשים/שנים.
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
        await self.bot.db.execute("DELETE FROM voice_presence_snapshots WHERE snapshot_at < ?", (cutoff_iso,))
        await self.bot.db.commit()

    async def get_present_usernames(self, channel_id, target_timestamp, window_seconds=DEFAULT_CORRELATION_WINDOW_SECONDS):
        """שמות (display_name, ללא כפילויות) של כל מי שנראה ב-channel_id בכל
        נקודה בטווח [target_timestamp - window_seconds, target_timestamp] -
        target_timestamp הוא Unix timestamp (בד"כ os.path.getmtime(clip_path)).
        רשימה ריקה אם channel_id ריק/None, לא שגיאה."""
        if not channel_id:
            return []
        await self._ensure_table()
        start_iso = datetime.fromtimestamp(target_timestamp - window_seconds, tz=timezone.utc).isoformat(timespec="seconds")
        end_iso = datetime.fromtimestamp(target_timestamp, tz=timezone.utc).isoformat(timespec="seconds")
        async with self.bot.db.execute(
            "SELECT DISTINCT username FROM voice_presence_snapshots WHERE channel_id = ? AND snapshot_at BETWEEN ? AND ? ORDER BY username",
            (int(channel_id), start_iso, end_iso),
        ) as cursor:
            rows = await cursor.fetchall()
        return [row[0] for row in rows]

    async def get_present_usernames_for_clip(self, clip_path, window_seconds=DEFAULT_CORRELATION_WINDOW_SECONDS):
        """נוחות מעל get_present_usernames - קורא את capture_voice_channel_id
        המוגדר ומשתמש ב-mtime הקובץ כנקודת הזמן. [] אם אף ערוץ לא הוגדר."""
        channel_id = get_capture_voice_channel_id()
        if not channel_id:
            return []
        return await self.get_present_usernames(channel_id, os.path.getmtime(clip_path), window_seconds)

    @tasks.loop(seconds=SNAPSHOT_INTERVAL_SECONDS)
    async def snapshot_loop(self):
        await self._take_snapshot()

    @snapshot_loop.before_loop
    async def before_snapshot(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(VoicePresenceCog(bot))
