import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
from utils.shared.retry import call_with_retry_async
from utils.shared import data_paths, install_profile
from utils.shared.secrets_vault import get_secret


def _is_retryable_network_error(exc):
    """True אם סביר שניסיון חוזר יעזור - בעיית רשת/timeout זמנית, לא שגיאת
    נתונים אמיתית (JSON לא-תקין, מבנה לא-צפוי וכו') שניסיון חוזר לא יתקן."""
    return isinstance(exc, (aiohttp.ClientError, asyncio.TimeoutError, OSError))


async def _fetch_appdetails(session, app_id, country="us", language="english"):
    """קריאת appdetails יחידה עם retry/backoff (item: אימוץ retry/backoff
    משותף - עד עכשיו כשל רשת חד-פעמי היה מדלג בשקט על המשחק הזה עד הבדיקה
    הבאה בעוד 12 שעות, בלי שום ניסיון חוזר מיידי).
    30.10.2026: אזור החנות (מטבע) והשפה - "steam_country"/"steam_language" ב-config.json (utils/shared/install_profile)."""
    async def _do_fetch():
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc={country}&l={language}"
        async with session.get(url) as response:
            if response.status != 200:
                return None
            # appdetails מחזיר content-type לא-JSON - בלי content_type=None כל
            # בדיקה הייתה זורקת ContentTypeError בשקט, כך שהתראות הנחה לא
            # נשלחו אף פעם.
            return await response.json(content_type=None)

    return await call_with_retry_async(_do_fetch, max_attempts=3, is_retryable=_is_retryable_network_error, base_delay=2.0)


class SteamMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_steam_deals.start()

    def cog_unload(self):
        self.check_steam_deals.cancel()

    async def owner_only(self, interaction: discord.Interaction) -> bool:
        """מגביל הוספה/סנכרון מעקב Steam לבעל הבוט בלבד - steam_wishlist_sync
        בפרט חושף את ה-Wishlist האישי של הבעל (STEAM_ID) לכל channel_id שרירותי
        (item: בדיקת באגים מקיפה - נמצא חוסר עקבי מול שאר פקודות הבוט)."""
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("⛔ הפקודה הזו זמינה רק לבעל הבוט.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="steam_watch", description="הוספת משחק Steam למעקב הנחות בבסיס הנתונים")
    async def steam_watch(self, interaction: discord.Interaction, name: str, app_id: str, channel_id: str):
        if not await self.owner_only(interaction):
            return
        try:
            chan_id_int = int(channel_id)
        except ValueError:
            await interaction.response.send_message("❌ channel_id חייב להיות מספרי.", ephemeral=True)
            return

        async with self.bot.db.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO steam_games (name, app_id, channel_id) VALUES (?, ?, ?)",
                (name, app_id.strip(), chan_id_int)
            )
        await self.bot.db.commit()
        await interaction.response.send_message(f"🎮 המשחק **{name}** ({app_id}) נוסף למעקב הנחות!", ephemeral=True)

    @app_commands.command(name="steam_list", description="הצגת כל המשחקים שנמצאים במעקב")
    async def steam_list(self, interaction: discord.Interaction):
        async with self.bot.db.cursor() as cursor:
            await cursor.execute("SELECT name, app_id, channel_id FROM steam_games")
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("אין משחקים במעקב כרגע.", ephemeral=True)
            return

        embed = discord.Embed(title="🎮 משחקי Steam במעקב", color=discord.Color.purple())
        for row in rows:
            embed.add_field(name=row[0], value=f"App ID: {row[1]} | ערוץ: {row[2]}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="steam_wishlist_sync", description="מייבא אוטומטית משחקים חדשים מרשימת המשאלות שלך ב-Steam למעקב הנחות")
    @app_commands.describe(channel_id="ערוץ הדיסקורד שאליו יישלחו התראות הנחה עבור המשחקים החדשים שיתווספו")
    async def steam_wishlist_sync(self, interaction: discord.Interaction, channel_id: str):
        if not await self.owner_only(interaction):
            return
        steam_id = get_secret("STEAM_ID")
        if not steam_id:
            await interaction.response.send_message("❌ לא הוגדר STEAM_ID בקובץ .env בשורש הפרויקט.", ephemeral=True)
            return
        try:
            chan_id_int = int(channel_id)
        except ValueError:
            await interaction.response.send_message("❌ channel_id חייב להיות מספרי.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            async with aiohttp.ClientSession() as session:
                wishlist_url = f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={steam_id}"
                async with session.get(wishlist_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ קריאה ל-Steam נכשלה (קוד {resp.status}).")
                        return
                    data = await resp.json(content_type=None)

                items = data.get("response", {}).get("items", [])
                if not items:
                    await interaction.followup.send(
                        "ℹ️ לא נמצאו פריטים ברשימת המשאלות. ייתכן שהיא ריקה, או שהיא מוגדרת כפרטית "
                        "בהגדרות הפרטיות של Steam (Wishlist Visibility) - צריך שתהיה ציבורית או לחברים."
                    )
                    return

                async with self.bot.db.cursor() as cursor:
                    await cursor.execute("SELECT app_id FROM steam_games")
                    existing_app_ids = {row[0] for row in await cursor.fetchall()}

                added_names = []
                for item in items:
                    app_id = str(item.get("appid", "")).strip()
                    if not app_id or app_id in existing_app_ids:
                        continue

                    name = app_id
                    try:
                        details_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                        async with session.get(details_url) as d_resp:
                            if d_resp.status == 200:
                                d_data = await d_resp.json(content_type=None)
                                if d_data and d_data.get(app_id, {}).get("success"):
                                    name = d_data[app_id]["data"].get("name", app_id)
                    except Exception:
                        pass  # אם שליפת השם נכשלה - עדיין נוסיף את המשחק עם ה-App ID בתור שם

                    async with self.bot.db.cursor() as cursor:
                        await cursor.execute(
                            "INSERT INTO steam_games (name, app_id, channel_id) VALUES (?, ?, ?)",
                            (name, app_id, chan_id_int)
                        )
                    added_names.append(name)
                    existing_app_ids.add(app_id)

                await self.bot.db.commit()
        except Exception as e:
            await interaction.followup.send(f"❌ שגיאה בסנכרון ה-Wishlist: {e}")
            return

        if added_names:
            preview = "\n".join(f"• {n}" for n in added_names[:20])
            more = f"\n...ועוד {len(added_names) - 20}" if len(added_names) > 20 else ""
            await interaction.followup.send(f"✅ נוספו {len(added_names)} משחקים חדשים למעקב הנחות מה-Wishlist:\n{preview}{more}")
        else:
            await interaction.followup.send("ℹ️ כל המשחקים ברשימת המשאלות כבר נמצאים במעקב.")

    @tasks.loop(hours=12) # בדיקה פעמיים ביום
    async def check_steam_deals(self):
        async with self.bot.db.cursor() as cursor:
            await cursor.execute("SELECT name, app_id, channel_id FROM steam_games")
            games = await cursor.fetchall()
        settings = install_profile.read(data_paths.path(data_paths.CONFIG))

        async with aiohttp.ClientSession() as session:
            for name, app_id, channel_id in games:
                try:
                    data = await _fetch_appdetails(session, app_id, settings["steam_country"], settings["steam_language"])
                    if data and data[app_id]["success"]:
                        game_data = data[app_id]["data"]

                        # בדיקה אם המשחק בתשלום ויש עליו הנחה
                        if not game_data.get("is_free") and "price_overview" in game_data:
                            price_info = game_data["price_overview"]
                            discount_pct = price_info["discount_percent"]

                            if discount_pct > 0:
                                channel = self.bot.get_channel(channel_id)
                                if channel:
                                    embed = discord.Embed(
                                        title=f"🚨 הנחת Steam מטורפת עבור {name}! 🚨",
                                        url=f"https://store.steampowered.com/app/{app_id}",
                                        color=discord.Color.green()
                                    )
                                    embed.add_field(name="📉 אחוז ההנחה", value=f"`-{discount_pct}%`", inline=True)
                                    embed.add_field(name="💰 מחיר נוכחי", value=f"`{price_info['final_formatted']}`", inline=True)
                                    embed.add_field(name="❌ מחיר מקורי", value=f"~~{price_info['initial_formatted']}~~", inline=True)
                                    embed.set_thumbnail(url=game_data.get("header_image"))

                                    await channel.send(embed=embed)
                except Exception as e:
                    print(f"שגיאה בבדיקת מחיר עבור App ID {app_id}: {e}")

    @check_steam_deals.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(SteamMonitor(bot))