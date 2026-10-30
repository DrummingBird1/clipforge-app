# cogs/approval_cog.py
#
# שלב "אישור לפני פרסום": סורק את תיקיית clips/ (התוצר של story_cutter.py -
# קליפים שכבר עברו סינון AI ראשוני) ומעלה אותם לאישור בדיסקורד עם כפתורי
# ✅ אשר / ❌ דחה, לפני שהם מגיעים לרינדור ה-4K היקר ב-rocket_shorts_publisher.py.
#
# עיצוב מכוון: הכפתור "אשר" פשוט מעביר את הקובץ לתיקיית ה-Import של
# rocket_shorts_publisher.py - כך שהריצה הבאה שלו כבר תעבד אותו כרגיל, בלי
# שום שינוי בסקריפט הרינדור עצמו.

import asyncio
import datetime
import json
import os
import sqlite3
import subprocess

import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils.bot.approval_store import CLIPS_REVIEW_DIR, FRIEND_TAGS_CACHE_DIR, REJECTED_DIR, get_rocket_input_dir
from utils.media.clip_tagger import tags_cache_path as _friend_tags_cache_path
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
FFMPEG_EXE = get_ffmpeg_exe()


class ApprovalView(discord.ui.View):
    def __init__(self, cog, pending_id, video_path, owner_id):
        super().__init__(timeout=None)  # ממתין להחלטה ללא הגבלת זמן - אישור עריכה לא דחוף
        self.cog = cog
        self.pending_id = pending_id
        self.video_path = video_path
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await interaction.client.is_owner(interaction.user):
            await interaction.response.send_message("⛔ רק בעל הבוט יכול לאשר/לדחות קליפים.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ אשר לרינדור", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.resolve_pending(self.pending_id, self.video_path, approved=True)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ **אושר** - ייכלל בריצת הרינדור הבאה.", view=self)

    @discord.ui.button(label="❌ דחה", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.resolve_pending(self.pending_id, self.video_path, approved=False)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ **נדחה** - הועבר לארכיון.", view=self)


# סוף היום - אחרי רוב הפעילות הצפויה. 30.10.2026: בשעון המקומי, כמו DAILY_RUN_TIME ב-cogs/scheduler_cog.py
DAILY_DIGEST_TIME = datetime.time(hour=20, minute=0, tzinfo=datetime.datetime.now().astimezone().tzinfo)


class ApprovalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.review_channel_id = None
        self.scan_loop.start()
        self.daily_digest.start()

    def cog_unload(self):
        self.scan_loop.cancel()
        self.daily_digest.cancel()

    async def _ensure_table(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                channel_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # resolved_at: מתי בפועל אושר/נדחה (לא created_at, שזה מתי הקליפ זוהה
        # לראשונה) - נדרש כדי שהסיכום היומי יספור לפי היום שבו ההחלטה התקבלה.
        # SQLite לא תומך ב-"ADD COLUMN IF NOT EXISTS" - תופסים את השגיאה כשהעמודה
        # כבר קיימת (טבלה שנוצרה לפני שהעמודה הזו נוספה), כמו ב-utils/shared/job_history.py.
        try:
            await self.bot.db.execute("ALTER TABLE pending_approvals ADD COLUMN resolved_at TEXT")
        except sqlite3.OperationalError:
            pass
        await self.bot.db.commit()

    @app_commands.command(name="set_review_channel", description="קובע לאיזה ערוץ יישלחו קליפים לאישור לפני רינדור")
    async def set_review_channel(self, interaction: discord.Interaction, channel_id: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return
        self.review_channel_id = int(channel_id)
        await interaction.response.send_message(f"📬 קליפים לאישור יישלחו מעכשיו לערוץ {channel_id}.", ephemeral=True)

    async def resolve_pending(self, pending_id, video_path, approved):
        try:
            if approved:
                os.makedirs(get_rocket_input_dir(), exist_ok=True)
                dest = os.path.join(get_rocket_input_dir(), os.path.basename(video_path))
            else:
                os.makedirs(REJECTED_DIR, exist_ok=True)
                dest = os.path.join(REJECTED_DIR, os.path.basename(video_path))

            if os.path.exists(video_path):
                os.replace(video_path, dest)

            await self.bot.db.execute(
                "UPDATE pending_approvals SET status = ?, resolved_at = ? WHERE id = ?",
                ("approved" if approved else "rejected", datetime.datetime.now().isoformat(), pending_id)
            )
            await self.bot.db.commit()
        except Exception as e:
            print(f"[approval_cog] שגיאה בטיפול בהחלטת אישור: {e}")

    async def _detect_and_cache_friends(self, video_path):
        """מזהה מי היה בערוץ הקול המוגדר בזמן שהקליפ נשמר (item: friend
        detection via Discord voice channel presence) ושומר למטמון (כדי
        שהגלריה בווב/דסקטוק - תהליכים נפרדים בלי גישה ל-self.bot.db בכלל -
        תוכל להציג את זה בלי לשאול את הבוט). מחזיר את רשימת השמות (גם ריקה),
        לשימוש ישיר בתיאור ה-embed בלי לקרוא שוב למטמון."""
        voice_cog = self.bot.get_cog("VoicePresenceCog")
        friend_names = await voice_cog.get_present_usernames_for_clip(video_path) if voice_cog else []
        try:
            os.makedirs(FRIEND_TAGS_CACHE_DIR, exist_ok=True)
            with open(_friend_tags_cache_path(video_path, FRIEND_TAGS_CACHE_DIR), "w", encoding="utf-8") as f:
                json.dump({"tags": friend_names}, f, ensure_ascii=False)
        except OSError as e:
            print(f"[approval_cog] שגיאה בשמירת מטמון חברים: {e}")
        return friend_names

    def _make_preview_thumb(self, video_path):
        thumb_path = os.path.splitext(video_path)[0] + "_review_thumb.jpg"
        try:
            subprocess.run(
                [FFMPEG_EXE, "-y", "-i", video_path, "-ss", "1", "-vframes", "1", "-vf", "scale=480:-1", thumb_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, creationflags=NO_WINDOW_FLAGS
            )
        except Exception:
            return None
        return thumb_path if os.path.exists(thumb_path) else None

    async def _do_scan(self):
        """הלוגיקה בפועל של סריקת clips/ ושליחת קליפים חדשים לאישור - מופרד
        מ-scan_loop כדי ש-/rescan_clips יוכל להפעיל את אותו קוד מיידית, בלי
        לחכות עד 5 דקות ללולאה התקופתית. מחזיר כמה קליפים חדשים נשלחו."""
        await self._ensure_table()

        if not self.review_channel_id or not os.path.exists(CLIPS_REVIEW_DIR):
            return 0

        channel = self.bot.get_channel(self.review_channel_id)
        if not channel:
            return 0

        sent_count = 0
        for root, _dirs, files in os.walk(CLIPS_REVIEW_DIR):
            for filename in files:
                if not filename.lower().endswith((".mp4", ".mkv", ".mov")):
                    continue
                video_path = os.path.join(root, filename)

                async with self.bot.db.execute(
                    "SELECT id FROM pending_approvals WHERE video_path = ?", (video_path,)
                ) as cursor:
                    existing = await cursor.fetchone()
                if existing:
                    continue

                cursor = await self.bot.db.execute(
                    "INSERT INTO pending_approvals (video_path, status, channel_id) VALUES (?, 'pending', ?)",
                    (video_path, self.review_channel_id)
                )
                await self.bot.db.commit()
                pending_id = cursor.lastrowid

                # 25.10.2026: ffmpeg (עד 20 שניות לקליפ) ב-thread - בתוך הלולאה של הבוט הוא חסם את כל הבוט, גם את ה-heartbeat
                thumb_path = await asyncio.to_thread(self._make_preview_thumb, video_path)
                game_name = os.path.basename(root)
                friend_names = await self._detect_and_cache_friends(video_path)
                description = f"משחק: {game_name}\nלאחר אישור הקליפ ייכלל אוטומטית בריצת הרינדור הבאה."
                if friend_names:
                    description += f"\n👥 עם: {', '.join(friend_names)}"
                embed = discord.Embed(
                    title=f"🎬 קליפ חדש ממתין לאישור - {filename}",
                    description=description,
                    color=discord.Color.blurple()
                )
                view = ApprovalView(self, pending_id, video_path, owner_id=None)

                file = None
                try:
                    if thumb_path:
                        file = discord.File(thumb_path, filename="preview.jpg")
                        embed.set_image(url="attachment://preview.jpg")
                        await channel.send(embed=embed, file=file, view=view)
                    else:
                        await channel.send(embed=embed, view=view)
                    sent_count += 1
                except Exception as e:
                    # 25.10.2026: השורה כבר נרשמה כ-pending, ובלי למחוק אותה הסריקה הבאה דילגה על הקליף לתמיד -
                    # הוא לא הגיע לאישור אף פעם. מוחקים, והוא נשלח שוב בסריקה הבאה
                    print(f"[approval_cog] שגיאה בשליחת קליפ לאישור (ינסה שוב בסריקה הבאה): {e}")
                    await self.bot.db.execute("DELETE FROM pending_approvals WHERE id = ?", (pending_id,))
                    await self.bot.db.commit()
                finally:
                    if file is not None:
                        file.close()
                    if thumb_path and os.path.exists(thumb_path):
                        try:
                            os.remove(thumb_path)   # גם כשהשליחה נכשלה - לא להשאיר _review_thumb.jpg ליד הקליפ
                        except OSError:
                            pass

        return sent_count

    @tasks.loop(minutes=5)
    async def scan_loop(self):
        await self._do_scan()

    @app_commands.command(name="rescan_clips", description="סורק את תיקיית הקליפים מיד (לא מחכה עד 5 דקות ללולאה התקופתית)")
    async def rescan_clips(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return
        if not self.review_channel_id:
            await interaction.response.send_message("⚠️ לא הוגדר ערוץ אישור - הרץ קודם `/set_review_channel`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        sent_count = await self._do_scan()
        if sent_count:
            await interaction.followup.send(f"✅ נמצאו {sent_count} קליפים חדשים ונשלחו לאישור.")
        else:
            await interaction.followup.send("ℹ️ לא נמצאו קליפים חדשים.")

    @scan_loop.before_loop
    async def before_scan(self):
        await self.bot.wait_until_ready()

    @tasks.loop(time=DAILY_DIGEST_TIME)
    async def daily_digest(self):
        """סיכום יומי (בניגוד ל-utils/bot/weekly_digest.py הקיים, שהוא שבועי ולא
        ספציפי לאישורי קליפים) - כמה קליפים אושרו/נדחו היום, לערוץ האישורים
        עצמו. מדלג בשקט אם אין ערוץ מוגדר או שלא הייתה שום פעילות היום."""
        if not self.review_channel_id:
            return
        channel = self.bot.get_channel(self.review_channel_id)
        if not channel:
            return

        await self._ensure_table()
        today_prefix = datetime.date.today().isoformat()
        async with self.bot.db.execute(
            "SELECT status, COUNT(*) FROM pending_approvals WHERE resolved_at LIKE ? GROUP BY status",
            (f"{today_prefix}%",)
        ) as cursor:
            rows = await cursor.fetchall()

        counts = dict(rows)
        approved = counts.get("approved", 0)
        rejected = counts.get("rejected", 0)
        if approved == 0 and rejected == 0:
            return  # אין מה לסכם - לא הייתה שום פעילות היום

        embed = discord.Embed(title="📋 סיכום אישורי קליפים - היום", color=discord.Color.blurple())
        embed.add_field(name="✅ אושרו", value=str(approved), inline=True)
        embed.add_field(name="❌ נדחו", value=str(rejected), inline=True)
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"[approval_cog] שגיאה בשליחת סיכום יומי: {e}")

    @daily_digest.before_loop
    async def before_daily_digest(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ApprovalCog(bot))
