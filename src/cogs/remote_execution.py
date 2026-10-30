import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import glob
import os
import sqlite3
import subprocess
import sys

from utils.shared.render_lock import CALLER_HOLDS_LOCK_ENV_VAR, acquire as acquire_render_lock, release as release_render_lock
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

STATUS_EDIT_INTERVAL_SECONDS = 3
OUTPUT_TAIL_LINES = 40
DOCKER_TIMEOUT_SECONDS = 10

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RemoteExecution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # מוחלט ועוגן ב-BASE_DIR (לא תלוי בתיקיית העבודה הנוכחית של התהליך) -
        # my_scripts/ מאורגן כעת בתת-תיקיות (video/stream/steam/tools), ולכן
        # הסקריפט מאותר לפי שם קובץ בכל תת-תיקייה, לא רק ישירות תחת my_scripts/
        self.scripts_dir = os.path.join(BASE_DIR, "my_scripts")

    async def owner_only(self, interaction: discord.Interaction) -> bool:
        """מגביל פקודות הרצה מרחוק לבעל הבוט בלבד."""
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return False
        return True

    async def log_action(self, interaction: discord.Interaction, command, details=""):
        """לוג ביקורת - מי הריץ מה ומתי. חשוב במיוחד ל-run_script שמריץ קוד על המחשב המארח,
        אם הרשאות אי פעם יורחבו מעבר לבעלים בלבד."""
        try:
            await self.bot.db.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, username TEXT, command TEXT, details TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # source: "discord" (ברירת מחדל) לעומת "web" - web_app.py כותב
            # לאותה טבלה בדיוק דרך utils/bot/audit_log.py (תהליך נפרד, בלי גישה
            # ל-bot.db הא-סינכרוני הזה) ומריץ את אותה מיגרציה בדיוק; שתי
            # ה-CREATE/ALTER אידמפוטנטיות, לא משנה מי רץ ראשון.
            try:
                await self.bot.db.execute("ALTER TABLE audit_log ADD COLUMN source TEXT DEFAULT 'discord'")
            except sqlite3.OperationalError:
                pass
            await self.bot.db.execute(
                "INSERT INTO audit_log (user_id, username, command, details) VALUES (?, ?, ?, ?)",
                (interaction.user.id, str(interaction.user), command, details)
            )
            await self.bot.db.commit()
        except Exception as e:
            print(f"[remote_execution] שגיאה בכתיבת לוג ביקורת: {e}")

    async def _script_name_autocomplete(self, interaction: discord.Interaction, current: str):
        """מציע שמות קבצים אמיתיים מתוך my_scripts/ תוך כדי הקלדה - בלי זה
        צריך לזכור/להעתיק את שם הקובץ המדויק (כולל .py) בעל פה. דיסקורד
        מגביל ל-25 הצעות מקסימום לכל בקשה."""
        matches = glob.glob(os.path.join(self.scripts_dir, "**", "*.py"), recursive=True)
        basenames = sorted({os.path.basename(m) for m in matches})
        filtered = [name for name in basenames if current.lower() in name.lower()]
        return [app_commands.Choice(name=name, value=name) for name in filtered[:25]]

    @app_commands.command(name="run_script", description="הפעלת סקריפט אוטומציה מרחוק עם התרעות קריסה")
    @app_commands.describe(script_name="שם הקובץ בתיקיית my_scripts (כולל סיומת .py)")
    @app_commands.autocomplete(script_name=_script_name_autocomplete)
    async def run_script(self, interaction: discord.Interaction, script_name: str):
        if not await self.owner_only(interaction):
            return

        # הגנה מפני Path Traversal - מוודא שנשארים בתוך my_scripts ושמדובר בקובץ .py בלבד.
        # my_scripts/ מאורגן בתת-תיקיות (video/stream/steam/tools) ולכן מחפשים לפי
        # שם קובץ בכל תת-תיקייה, ואז מוודאים שהנתיב שנמצא בפועל נשאר בתוך scripts_dir.
        safe_name = os.path.basename(script_name)
        if not safe_name.endswith(".py"):
            await interaction.response.send_message("❌ שם סקריפט לא חוקי.", ephemeral=True)
            return

        matches = glob.glob(os.path.join(self.scripts_dir, "**", safe_name), recursive=True)
        script_path = os.path.abspath(matches[0]) if matches else ""
        if not script_path or not script_path.startswith(self.scripts_dir + os.sep):
            await interaction.response.send_message(f"❌ הסקריפט `{safe_name}` לא נמצא בתיקיית my_scripts.", ephemeral=True)
            return

        await self.log_action(interaction, "run_script", safe_name)

        # אישור מיידי על תחילת הריצה - ה-followup/token של דיסקורד תקף 15 דקות בלבד,
        # ורינדורים ארוכים (4K/GPU) יכולים לחרוג מזה. לכן ההודעות בהמשך נשלחות/מתעדכנות
        # דרך הערוץ עצמו (interaction.channel) ולא דרך followup, כדי שלא יפוגו.
        await interaction.response.send_message(f"▶️ מריץ את `{safe_name}`...", ephemeral=True)
        status_msg = await interaction.channel.send(f"🔄 **{safe_name}** רץ...\n```\n(ממתין לפלט ראשוני...)\n```")

        loop = asyncio.get_event_loop()

        # מנעול חוצה-תהליכים משותף עם ה-GUI (utils/shared/render_lock.py) - מונע
        # מהרצה מרחוק דרך דיסקורד להתנגש עם רינדור כבד שרץ באותו רגע דרך ה-GUI.
        # acquire() חוסם עם time.sleep - חייב לרוץ ב-executor, אחרת קופא את כל
        # לולאת האירועים של הבוט (כולל heartbeat) כל עוד רינדור אחר תפוס.
        try:
            await status_msg.edit(content=f"⏳ **{safe_name}** ממתין לסיום רינדור אחר שרץ כרגע (GUI או הבוט)...")
            # priority=10 - כמו worker.py: הרצה ידנית (כאן דרך דיסקורד) קודמת
            # בתור לג'וב מתוזמן ברקע (cogs/scheduler_cog.py, נשאר בברירת המחדל 0).
            await loop.run_in_executor(None, lambda: acquire_render_lock(priority=10, label=safe_name))
        except Exception as e:
            await status_msg.edit(content=f"❌ שגיאה בתפיסת מנעול הרינדור: {e}")
            return

        try:
            # asyncio.create_subprocess_exec ולא subprocess.Popen+communicate() -
            # הגרסה החוסמת הייתה קופאת את כל לולאת האירועים של הבוט (כולל heartbeat)
            # לאורך כל זמן ריצת הסקריפט.
            process = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=NO_WINDOW_FLAGS,
                # כבר תפסנו את render_lock למעלה - מודיעים לתת-התהליך כדי שאם
                # הוא גם יודע להגן על עצמו (utils.shared.render_lock.render_lock_if_needed)
                # הוא לא ינסה לתפוס את אותו מנעול שוב ויינעל על עצמו.
                env={**os.environ, CALLER_HOLDS_LOCK_ENV_VAR: "1"},
            )
        except Exception as e:
            await status_msg.edit(content=f"❌ שגיאה בלתי צפויה בהפעלת התהליך: {e}")
            release_render_lock()
            return

        try:
            output_lines = []
            last_edit = loop.time()

            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                output_lines.append(line.decode("utf-8", errors="replace"))
                output_lines = output_lines[-OUTPUT_TAIL_LINES:]

                now = loop.time()
                if now - last_edit >= STATUS_EDIT_INTERVAL_SECONDS:
                    tail = "".join(output_lines)[-1500:]
                    try:
                        await status_msg.edit(content=f"🔄 **{safe_name}** רץ...\n```\n{tail}\n```")
                    except discord.HTTPException:
                        pass
                    last_edit = now

            await process.wait()
        finally:
            release_render_lock()

        tail = "".join(output_lines)[-1500:]

        if process.returncode != 0:
            embed = discord.Embed(
                title=f"💥 קריסת סקריפט: {safe_name} 💥",
                description=f"הקובץ נכשל עם קוד יציאה `{process.returncode}`.",
                color=discord.Color.red()
            )
            embed.add_field(name="📁 סוף הפלט", value=f"```\n{tail if tail else 'אין פלט'}\n```", inline=False)
            await status_msg.edit(content=None, embed=embed)
        else:
            await status_msg.edit(content=f"✅ הסקריפט `{safe_name}` הסתיים בהצלחה!\n```\n{tail}\n```")

    @app_commands.command(name="docker_status", description="בדיקת סטטוס קונטיינרים פעילים")
    async def docker_status(self, interaction: discord.Interaction):
        if not await self.owner_only(interaction):
            return
        await self.log_action(interaction, "docker_status")
        await interaction.response.defer()
        try:
            # 25.10.2026: ב-thread ועם timeout - Docker Desktop שנתקע (עולה / תקוע ב-WSL) עצר כאן את כל הבוט, בלי סוף
            result = await asyncio.to_thread(subprocess.run, ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}"],
                                             capture_output=True, text=True, timeout=DOCKER_TIMEOUT_SECONDS, creationflags=NO_WINDOW_FLAGS)
            if result.returncode != 0:
                await interaction.followup.send("❌ Docker לא מותקן או לא נגיש ב-Host הנוכחי.")
                return
            await interaction.followup.send(f"🐳 **סטטוס קונטיינרים ב-Docker:**\n```\n{result.stdout}\n```")
        except subprocess.TimeoutExpired:
            await interaction.followup.send(f"⏳ Docker לא ענה תוך {DOCKER_TIMEOUT_SECONDS} שניות (אולי הוא עדיין עולה).")
        except Exception as e:
            await interaction.followup.send(f"❌ נכשל בניסיון לגשת ל-Docker: {e}")

    @app_commands.command(name="audit_log", description="הצגת פעולות הרצה מרחוק אחרונות (מי הריץ מה ומתי)")
    async def audit_log(self, interaction: discord.Interaction):
        if not await self.owner_only(interaction):
            return
        try:
            async with self.bot.db.execute(
                "SELECT username, command, details, timestamp, source FROM audit_log ORDER BY id DESC LIMIT 15"
            ) as cursor:
                rows = await cursor.fetchall()
        except Exception:
            rows = []

        if not rows:
            await interaction.response.send_message("אין עדיין רשומות בלוג הביקורת.", ephemeral=True)
            return

        embed = discord.Embed(title="📋 לוג ביקורת - פעולות אחרונות", color=discord.Color.dark_gold())
        for username, command, details, ts, source in rows:
            # source יכול להיות None לרשומות ישנות שנכתבו לפני שהעמודה נוספה
            # (ALTER TABLE לא ממלא ערך רטרואקטיבית) - מוצג כ"discord" (ברירת
            # המחדל ההיסטורית, לפני ש-web_app.py בכלל כתב ללוג הזה).
            icon = "🌐" if source == "web" else "🤖"
            label = f"{icon} {command}" + (f" ({details})" if details else "")
            embed.add_field(name=label, value=f"{username} · {ts}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RemoteExecution(bot))