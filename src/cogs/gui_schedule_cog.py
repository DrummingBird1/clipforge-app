# cogs/gui_schedule_cog.py
#
# צפייה/עריכה מרחוק (דרך דיסקורד) במשימות המתוזמנות שנוצרות ב-GUI השולחני
# (ui/scheduler_tab.py, מאוחסנות ב-utils/bot/scheduler_store.py) - עד כה הדרך
# היחידה לראות/לשנות אותן הייתה לפתוח את ה-GUI על המחשב עצמו. בכוונה לא כולל
# "הוספת" משימה חדשה מהדיסקורד - זו טופס עם כמה שדות תלויים-זה-בזה (סוג
# תזמון -> שעה/יום/מספר שעות) שמתאים הרבה יותר לטופס GUI מאשר לפקודת slash
# בודדת; toggle/remove/list מכסים את השימוש המרכזי ("אני לא ליד המחשב, תראה
# לי/תכבה משימה") בלי לבנות אשף רב-שלבי.
import discord
from discord.ext import commands
from discord import app_commands

from utils.bot import scheduler_store
from utils.shared.script_metadata import get_script_metadata

WEEKDAY_LABELS_HE = {
    "sun": "ראשון", "mon": "שני", "tue": "שלישי", "wed": "רביעי",
    "thu": "חמישי", "fri": "שישי", "sat": "שבת",
}


def _describe_schedule(task):
    if task["schedule_type"] == "daily":
        return f"כל יום ב-{task['time']}"
    if task["schedule_type"] == "weekly":
        weekday = WEEKDAY_LABELS_HE.get(task["weekday"], task["weekday"])
        return f"כל {weekday} ב-{task['time']}"
    return f"כל {task['interval_hours']} שעות"


def _task_label(task):
    """תווית קריאה לזיהוי המשימה ב-autocomplete - שם הסקריפט + תיאור התזמון,
    לא ה-UUID הפנימי (task['id']) שאף אחד לא זוכר בעל פה."""
    script_name = get_script_metadata(task["script_path"])["name"]
    status = "פעיל" if task["enabled"] else "כבוי"
    return f"{script_name} - {_describe_schedule(task)} ({status})"


class GuiScheduleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _task_autocomplete(self, interaction: discord.Interaction, current: str):
        tasks = scheduler_store.load_tasks()
        choices = []
        for task in tasks:
            label = _task_label(task)
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=task["id"]))
        return choices[:25]

    @app_commands.command(name="schedule_list", description="מציג את כל המשימות המתוזמנות שהוגדרו ב-GUI השולחני")
    async def schedule_list(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        tasks = scheduler_store.load_tasks()
        if not tasks:
            await interaction.response.send_message("ℹ️ אין משימות מתוזמנות עדיין - ניתן להוסיף מטאב '⏰ מתוזמן' ב-GUI.", ephemeral=True)
            return

        embed = discord.Embed(title="⏰ משימות מתוזמנות", color=discord.Color.blurple())
        for task in tasks:
            icon = "🟢" if task["enabled"] else "⚪"
            last_run = task.get("last_run_at") or "מעולם לא רץ"
            embed.add_field(
                name=f"{icon} {get_script_metadata(task['script_path'])['name']}",
                value=f"{_describe_schedule(task)}\nריצה אחרונה: {last_run}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="schedule_toggle", description="מפעיל/מכבה משימה מתוזמנת")
    @app_commands.describe(task="המשימה לשינוי")
    @app_commands.autocomplete(task=_task_autocomplete)
    async def schedule_toggle(self, interaction: discord.Interaction, task: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        tasks = scheduler_store.load_tasks()
        match = next((t for t in tasks if t["id"] == task), None)
        if match is None:
            await interaction.response.send_message("❌ משימה לא נמצאה (ייתכן שנמחקה כבר).", ephemeral=True)
            return

        new_state = not match["enabled"]
        scheduler_store.set_enabled(task, new_state)
        status_text = "הופעלה 🟢" if new_state else "כובתה ⚪"
        await interaction.response.send_message(f"✅ המשימה '{_task_label(match)}' {status_text}.", ephemeral=True)

    @app_commands.command(name="schedule_remove", description="מוחק משימה מתוזמנת")
    @app_commands.describe(task="המשימה למחיקה")
    @app_commands.autocomplete(task=_task_autocomplete)
    async def schedule_remove(self, interaction: discord.Interaction, task: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        tasks = scheduler_store.load_tasks()
        match = next((t for t in tasks if t["id"] == task), None)
        if match is None:
            await interaction.response.send_message("❌ משימה לא נמצאה (ייתכן שנמחקה כבר).", ephemeral=True)
            return

        label = _task_label(match)
        scheduler_store.remove_task(task)
        await interaction.response.send_message(f"🗑️ המשימה '{label}' נמחקה.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(GuiScheduleCog(bot))
