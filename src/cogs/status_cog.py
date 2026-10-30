# cogs/status_cog.py
#
# פקודת /status מרוכזת - מאחדת את מה שהיה מפוזר בין כמה פקודות נפרדות
# (docker_status, audit_log ב-cogs/remote_execution.py) פלוס מדדי בריאות שלא
# היו קיימים בכלל בדיסקורד (כמה זמן הבוט למעלה, כמה מקום פנוי בדיסק, מתי
# רצה לאחרונה כל משימת תחזוקה אוטומטית) - תמונת מצב אחת, בלי לזכור אילו 3-4
# פקודות נפרדות להריץ.

import datetime
import json
import os
import shutil
import subprocess

import discord
from discord.ext import commands
from discord import app_commands

from utils.shared.health_status import format_duration
from utils.shared.job_history import get_average_render_durations
from utils.shared.render_lock import get_status as get_render_lock_status
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared import data_paths

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEDULER_STATE_PATH = data_paths.path(data_paths.SCHEDULER_STATE)


def _get_disk_free_gb():
    try:
        _, _, free = shutil.disk_usage(BASE_DIR)
        return round(free / (1024 ** 3), 1)
    except Exception:
        return None


def _get_docker_status_text():
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}: {{.Status}}"],
            capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW_FLAGS
        )
        if result.returncode != 0:
            return "לא מותקן/לא נגיש"
        lines = [line for line in result.stdout.splitlines() if line.strip()]
        return "\n".join(lines) if lines else "אין קונטיינרים פעילים"
    except Exception:
        return "לא מותקן/לא נגיש"


def _load_scheduler_state():
    if os.path.exists(SCHEDULER_STATE_PATH):
        try:
            with open(SCHEDULER_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class StatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="תמונת מצב מרוכזת: זמן פעילות, דיסק, Docker, תחזוקה אוטומטית ופעולה אחרונה")
    async def status(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        started_at = getattr(self.bot, "started_at", None)
        if started_at:
            uptime_str = format_duration((datetime.datetime.now(datetime.timezone.utc) - started_at).total_seconds())
        else:
            uptime_str = "לא ידוע"

        disk_free = _get_disk_free_gb()
        docker_status = _get_docker_status_text()
        scheduler_state = _load_scheduler_state()

        try:
            async with self.bot.db.execute(
                "SELECT username, command, details, timestamp, source FROM audit_log ORDER BY id DESC LIMIT 1"
            ) as cursor:
                last_action = await cursor.fetchone()
        except Exception:
            last_action = None

        embed = discord.Embed(title="🩺 סטטוס מרוכז - ClipForge", color=discord.Color.blurple())
        embed.add_field(name="⏱️ זמן פעילות", value=uptime_str, inline=True)
        embed.add_field(name="💾 שטח פנוי בדיסק", value=f"{disk_free} GB" if disk_free is not None else "לא ידוע", inline=True)
        embed.add_field(name="🐳 Docker", value=docker_status, inline=False)

        maintenance_lines = [
            f"גיבוי DB אחרון: {scheduler_state.get('last_db_backup_date', 'טרם בוצע')}",
            f"ניקוי מקורות אחרון: {scheduler_state.get('last_cleanup_date', 'טרם בוצע')}",
            f"ריקאפ שבועי אחרון: {scheduler_state.get('last_weekly_recap_date', 'טרם בוצע')}",
            f"ניקוי גיבויי-לוג אחרון: {scheduler_state.get('last_log_cleanup_date', 'טרם בוצע')}",
        ]
        embed.add_field(name="🔧 תחזוקה אוטומטית", value="\n".join(maintenance_lines), inline=False)

        lock_status = get_render_lock_status()
        if lock_status is None:
            lock_text = "פנוי"
        else:
            age_text = format_duration(lock_status["age_seconds"]) if lock_status["age_seconds"] is not None else "לא ידוע"
            lock_text = f"תפוס (PID {lock_status['pid']}, {age_text})"
            if lock_status.get("queue_length"):
                lock_text += f" · עוד {lock_status['queue_length']} בתור"
            if lock_status["is_stale"]:
                lock_text += " ⚠️ נראה תקוע - ישוחרר אוטומטית בניסיון התפיסה הבא"
        embed.add_field(name="🔒 מנעול רינדור", value=lock_text, inline=False)

        if last_action:
            username, command, details, ts, source = last_action
            icon = "🌐" if source == "web" else "🤖"
            label = f"{icon} {command}" + (f" ({details})" if details else "")
            embed.add_field(name="📋 פעולה אחרונה בלוג הביקורת", value=f"{label} · {username} · {ts}", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="render_stats", description="זמן רינדור ממוצע לכל סקריפט, מבוסס על היסטוריית ריצות מוצלחות")
    async def render_stats(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        averages = get_average_render_durations()
        embed = discord.Embed(title="⏱️ זמני רינדור ממוצעים", color=discord.Color.blurple())
        if not averages:
            embed.description = "אין עדיין היסטוריית ריצות מוצלחות."
        else:
            for script_name, avg_seconds, run_count in averages:
                embed.add_field(
                    name=script_name,
                    value=f"{format_duration(avg_seconds)} (ממוצע על {run_count} ריצות)",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="help", description="רשימת כל פקודות ה-Slash הזמינות (owner-only) עם הסבר קצר על כל אחת")
    async def help_command(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        # נשלף דינמית מ-bot.tree (לא רשימה קבועה כאן) - כדי שהרשימה תישאר
        # מסונכרנת אוטומטית עם הפקודות בפועל, בלי לתחזק העתק נפרד שיתיישן
        # (בדיוק אותה בעיה שכבר תוקנה כמה פעמים בפרויקט הזה - מקור אמת יחיד).
        commands_list = sorted(self.bot.tree.get_commands(), key=lambda c: c.name)
        embed = discord.Embed(title="📖 פקודות זמינות (owner-only)", color=discord.Color.blurple())
        for cmd in commands_list:
            embed.add_field(name=f"/{cmd.name}", value=cmd.description or "אין תיאור", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(StatusCog(bot))
