# cogs/batch_approval_cog.py
#
# אישור/דחייה בבת אחת לכל הקליפים הממתינים (cogs/approval_cog.py) - עד כה
# הדרך היחידה הייתה ללחוץ ✅/❌ על כל קליפ בנפרד, שורה-שורה. קוד נפרד לגמרי
# מ-approval_cog.py (לא נוגע בו בכלל, לא בקובץ ולא בהתנהגות הקיימת) - מתחבר
# אליו רק דרך bot.get_cog("ApprovalCog") וקורא ל-resolve_pending() הקיים שלו,
# בדיוק כמו שה-View של קליפ בודד כבר עושה.

import discord
from discord.ext import commands
from discord import app_commands


class BatchApprovalCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_pending_rows(self):
        """מחזיר (approval_cog, rows) - approval_cog הוא None אם cogs/approval_cog.py
        לא נטען מסיבה כלשהי (לא אמור לקרות בפועל, אבל עדיף הודעה ברורה מ-
        AttributeError). _ensure_table() נקרא ישירות (לא "פרטי" באמת בפייתון) כי
        זו בדיוק אותה הגנה שכל שאר הקוד ב-approval_cog.py כבר סומך עליה לפני
        כל שאילתה על pending_approvals."""
        approval_cog = self.bot.get_cog("ApprovalCog")
        if approval_cog is None:
            return None, []
        await approval_cog._ensure_table()
        async with self.bot.db.execute(
            "SELECT id, video_path FROM pending_approvals WHERE status = 'pending'"
        ) as cursor:
            rows = await cursor.fetchall()
        return approval_cog, rows

    async def _resolve_all(self, interaction, approved):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return

        approval_cog, rows = await self._get_pending_rows()
        if approval_cog is None:
            await interaction.response.send_message("⚠️ מודול האישורים (approval_cog) לא נטען.", ephemeral=True)
            return
        if not rows:
            await interaction.response.send_message("ℹ️ אין קליפים ממתינים לאישור כרגע.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        for pending_id, video_path in rows:
            await approval_cog.resolve_pending(pending_id, video_path, approved=approved)

        from utils.bot import audit_log
        audit_log.record_action(
            "discord", "approve_all_pending" if approved else "reject_all_pending",
            details=f"{len(rows)} קליפים", user_id=interaction.user.id, username=str(interaction.user),
        )

        if approved:
            await interaction.followup.send(f"✅ אושרו {len(rows)} קליפים בבת אחת - ייכללו בריצת הרינדור הבאה.")
        else:
            await interaction.followup.send(f"❌ נדחו {len(rows)} קליפים בבת אחת - הועברו לארכיון.")

    @app_commands.command(name="approve_all_pending", description="מאשר את כל הקליפים הממתינים לאישור בבת אחת, במקום אחד-אחד")
    async def approve_all_pending(self, interaction: discord.Interaction):
        await self._resolve_all(interaction, approved=True)

    @app_commands.command(name="reject_all_pending", description="דוחה את כל הקליפים הממתינים לאישור בבת אחת, במקום אחד-אחד")
    async def reject_all_pending(self, interaction: discord.Interaction):
        await self._resolve_all(interaction, approved=False)


async def setup(bot):
    await bot.add_cog(BatchApprovalCog(bot))
