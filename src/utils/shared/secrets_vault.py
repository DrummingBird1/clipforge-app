# utils/shared/secrets_vault.py
#
# שכבת סודות שמעדיפה את Windows Credential Manager (דרך keyring) על פני .env
# בטקסט גלוי, ונופלת חזרה ל-.env אם המפתח לא נמצא ב-vault - כדי שהמעבר יהיה
# הדרגתי ולא שובר כלום למי שעדיין לא מיגר.

import os

try:
    import keyring
except ImportError:
    keyring = None  # type: ignore[assignment]

from utils.shared.credential_rotation import record_rotation

SERVICE_NAME = "RocketLauncher"


def load_project_env(env_path=None):
    """טוען את .env של הפרויקט ל-os.environ (בלי לדרוס משתנים שכבר מוגדרים). סקריפטים (story_cutter,
    title_generator) כבר עושים זאת בעצמם, אבל תהליך שרת הדפדפן לא - ולכן בדיקת התקינות/ה-credentials בשרת
    הראו "חסר" למפתח שנמצא ב-.env. נקרא פעם אחת בעליית השרת. מחזיר True אם הקובץ נמצא."""
    from dotenv import load_dotenv

    path = env_path or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), ".env")
    if not os.path.isfile(path):
        return False
    load_dotenv(path, override=False)
    return True


def get_secret(key, default=""):
    """שולף מ-Windows Credential Manager קודם, ואם לא נמצא - ממשתני הסביבה (.env)."""
    if keyring:
        try:
            value = keyring.get_password(SERVICE_NAME, key)
            if value:
                return value
        except Exception as e:
            print(f"[secrets_vault] שגיאה בקריאה מ-Credential Manager עבור {key}: {e}")
    return os.environ.get(key, default)


def set_secret(key, value):
    """שומר סוד ב-Windows Credential Manager (מוצפן ע"י המערכת). מסמן גם
    (item: key-age tracking) את הרגע הזה כ"סבב אחרון" עבור key - כל שמירה
    בפועל דרך הפונקציה הזו (הגירה חד-פעמית, או סבב עתידי מהממשק) מעדכנת את
    הגיל, בלי שהקורא יצטרך לזכור לעשות זאת בעצמו."""
    if not keyring:
        raise RuntimeError("החבילה 'keyring' אינה מותקנת - לא ניתן לשמור ל-Credential Manager")
    keyring.set_password(SERVICE_NAME, key, value)
    record_rotation(key)


def delete_secret(key):
    if not keyring:
        return
    try:
        keyring.delete_password(SERVICE_NAME, key)
    except Exception:
        pass


def is_vault_available():
    return keyring is not None
