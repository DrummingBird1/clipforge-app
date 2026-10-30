# utils/shared/credential_health.py
#
# בדיקת תקינות credential vault (item: credential vault health-check) -
# utils/shared/secrets_vault.py כבר יודע לשלוף/לשמור סודות, אבל עד כה שום דבר לא
# בדק שהם עדיין *עובדים* בפועל - מפתח Gemini שפג/twitch secret שהוחלף היה
# מתגלה רק כשסקריפט אמיתי נכשל באמצע ריצה, לא לפני.
#
# שני מצבים נפרדים בכוונה:
#   - check_configured() - רק בודק שהסוד קיים/לא ריק (מיידי, בלי רשת בכלל) -
#     זה מה שרץ אוטומטית בתוך utils/shared/diagnostics.py, כי run_diagnostics()
#     אמור להיות מהיר ובטוח בלי לצרוך מכסת API בכל פתיחת הדיאלוג.
#   - check_validity() - קורא בפועל ל-API החיצוני (קריאה קלה - לא צורכת
#     מכסת יצירה/הרצה אמיתית, רק מוודאת שהמפתח מתקבל) - נקרא רק על-פי-בקשה
#     מפורשת (כפתור "🔑 בדוק תוקף"), אותו עיקרון בדיוק כמו utils/media/clip_tagger.py -
#     קריאות רשת/API אמיתיות לא קורות אוטומטית בלי שהמשתמש ביקש את זה.

import requests

from utils.shared.credential_rotation import DEFAULT_STALE_AFTER_DAYS, get_age_days
from utils.shared.secrets_vault import get_secret

CREDENTIAL_NAMES = ("GEMINI_API_KEY", "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "DISCORD_TOKEN")


def check_configured():
    """מחזיר {name: bool} - האם לכל סוד יש ערך לא-ריק (Credential Manager או
    .env). לא בודק תקינות בפועל, רק נוכחות - מיידי, בלי שום קריאת רשת."""
    return {name: bool(get_secret(name)) for name in CREDENTIAL_NAMES}


def get_rotation_status(stale_after_days=DEFAULT_STALE_AFTER_DAYS):
    """מחזיר [(name, configured, age_days_or_None, is_stale), ...] (item:
    key-age tracking) - בלי שום קריאת רשת, כמו check_configured(). age_days
    הוא None אם הסוד הוגדר ידנית ב-.env ולא דרך secrets_vault.set_secret()
    אף פעם (אין לנו שום דרך לדעת מתי) - במקרה כזה is_stale תמיד False, לא
    "לא ידוע" מוצג כאזהרה אדומה."""
    configured = check_configured()
    results = []
    for name in CREDENTIAL_NAMES:
        age_days = get_age_days(name) if configured[name] else None
        stale = age_days is not None and age_days >= stale_after_days
        results.append((name, configured[name], age_days, stale))
    return results


def _validate_gemini(api_key):
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        # models.list() - לא צורך מכסת generate_content, רק מוודא שהמפתח מתקבל.
        next(iter(client.models.list()), None)
        return True, "תקין"
    except Exception as e:
        return False, str(e)


def _validate_twitch(client_id, client_secret):
    try:
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            timeout=10,
        )
        if response.status_code == 200:
            return True, "תקין"
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def _validate_discord(token):
    try:
        response = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return True, "תקין"
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def check_validity():
    """
    מריץ בפועל בדיקת תוקף מול כל שירות (item: credential vault health-check) -
    קריאות רשת אמיתיות, נקרא רק על-פי-בקשה מפורשת של המשתמש (לא אוטומטית,
    לא מתוך run_diagnostics()). מחזיר [(name, configured, valid_or_None, detail), ...] -
    valid=None אם configured=False (אין מה לבדוק).
    """
    configured = check_configured()
    results = []

    gemini_key = get_secret("GEMINI_API_KEY")
    if configured["GEMINI_API_KEY"]:
        valid, detail = _validate_gemini(gemini_key)
        results.append(("GEMINI_API_KEY", True, valid, detail))
    else:
        results.append(("GEMINI_API_KEY", False, None, "לא מוגדר"))

    if configured["TWITCH_CLIENT_ID"] and configured["TWITCH_CLIENT_SECRET"]:
        valid, detail = _validate_twitch(get_secret("TWITCH_CLIENT_ID"), get_secret("TWITCH_CLIENT_SECRET"))
        results.append(("TWITCH_CLIENT_ID/SECRET", True, valid, detail))
    else:
        results.append(("TWITCH_CLIENT_ID/SECRET", False, None, "לא מוגדר"))

    if configured["DISCORD_TOKEN"]:
        valid, detail = _validate_discord(get_secret("DISCORD_TOKEN"))
        results.append(("DISCORD_TOKEN", True, valid, detail))
    else:
        results.append(("DISCORD_TOKEN", False, None, "לא מוגדר"))

    return results
