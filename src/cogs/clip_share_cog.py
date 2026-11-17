# cogs/clip_share_cog.py
#
# 16.11.2026 (ClipForge 2.0): הצד של הבוט ב"שלח לדיסקורד" (utils/bot/discord_outbox.py). כל 15 שניות שולף בקשות מהטבלה,
# שולח את הקובץ לערוץ שנקבע ב-/clip_channel, ומסמן. קובץ חסר או גדול מהמגבלה של השרת - כשל סופי עם הסבר (לייצא קודם
# ביעד "דיסקורד" בסטודיו, שמקודד לפי הגודל).
import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.bot import discord_outbox


def size_problem(size_bytes: int, limit_bytes: int):
    if size_bytes > limit_bytes:
        return (f"הקובץ {size_bytes / 1024 / 1024:.1f}MB, והמגבלה בשרת הזה {limit_bytes / 1024 / 1024:.0f}MB - "
                f"ייצא אותו ביעד \"דיסקורד\" בסטודיו")
    return None


class ClipShareCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.send_pending.start()

    def cog_unload(self):
        self.send_pending.cancel()

    @app_commands.command(name="clip_channel", description="הערוץ שאליו נשלחים קליפים מ-ClipForge (\"שלח לדיסקורד\")")
    async def clip_channel(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return
        await asyncio.to_thread(discord_outbox.set_channel, interaction.channel_id)
        await interaction.response.send_message("📬 קליפים מ-ClipForge יישלחו לערוץ הזה.", ephemeral=True)

    async def send_row(self, row, default_channel):
        channel_id = row.get("channel_id") or default_channel
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        if channel is None:
            return None, "לא נקבע ערוץ - הרץ /clip_channel בערוץ הרצוי", False   # None: מחכה, לא כשל
        path = row["path"]
        if not os.path.isfile(path):
            return False, "הקובץ לא נמצא", True
        limit = getattr(getattr(channel, "guild", None), "filesize_limit", 10 * 1024 * 1024)
        problem = size_problem(os.path.getsize(path), limit)
        if problem:
            return False, problem, True
        await channel.send(content=row.get("message") or None, file=discord.File(path))
        return True, "", False

    @tasks.loop(seconds=15)
    async def send_pending(self):
        # 17.11.2026: כל חריגה נתפסת. tasks.loop מפסיק לתמיד על חריגה שהוא לא מכיר (למשל DB נעול לרגע), ו"שלח לדיסקורד"
        # היה מת עד הפעלה מחדש של הבוט.
        try:
            rows = await asyncio.to_thread(discord_outbox.pending)
            if not rows:
                return
            default_channel = await asyncio.to_thread(discord_outbox.get_channel)
        except Exception as e:
            print(f"[clip_share] reading the queue failed: {e}")
            return
        for row in rows:
            try:
                try:
                    ok, error, final = await self.send_row(row, default_channel)
                except discord.HTTPException as e:
                    ok, error, final = False, f"דיסקורד דחה את הקובץ: {e}", False
                if ok is None:     # עוד לא נקבע ערוץ: הקליפ מחכה בתור, בלי לשרוף ניסיונות
                    await asyncio.to_thread(discord_outbox.waiting, row["id"], error)
                else:
                    await asyncio.to_thread(discord_outbox.mark, row["id"], ok, error, final)
            except Exception as e:
                print(f"[clip_share] row {row.get('id')} failed: {e}")

    @send_pending.before_loop
    async def _wait_ready(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ClipShareCog(bot))
