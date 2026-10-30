# utils/shared/credential_rotation.py
#
# מעקב "גיל מפתח" (item: key-age tracking) - utils/shared/credential_health.py כבר
# בודק *תוקף* (האם המפתח עדיין מתקבל ע"י Gemini/Twitch/Discord), אבל מפתח
# יכול להיות תקין-לגמרי ועדיין ישן מסוכן (לא הוחלף כבר שנה, למשל). זה עוקב
# אחרי *מתי* כל credential הוחלף לאחרונה, בנפרד לגמרי מהערך עצמו (שנשאר רק
# ב-Windows Credential Manager/.env, ראו utils/shared/secrets_vault.py) - קובץ JSON
# קטן תחת data/, אותו דפוס בדיוק כמו כל state קטן אחר בפרויקט הזה.
#
# record_rotation() נקרא אוטומטית מתוך secrets_vault.set_secret() - כל שמירה
# בפועל (הגירה חד-פעמית או סבב עתידי מהממשק) מעדכנת את חותמת הזמן, בלי
# שהקורא (migrate_secrets_to_vault.py, ה-API של הסבב) יצטרך לזכור לעשות זאת
# בעצמו בנפרד.

import json
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from utils.shared import data_paths

ROTATION_LOG_PATH = data_paths.path(data_paths.CREDENTIAL_ROTATION)

# ברירת המחדל שממנה סבב נחשב "ישן" (item: "לא הוחלף כבר X ימים") - 90 יום,
# תואם למחזורי סבב-סודות נפוצים (רבעוני). ניתנת לדריסה לכל קריאה בנפרד
# (get_age_days/is_stale) בלי לשנות קבוע גלובלי.
DEFAULT_STALE_AFTER_DAYS = 90


def _load() -> Dict[str, str]:
    try:
        with open(ROTATION_LOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_rotation(key: str) -> None:
    """מסמן את key כ"הוחלף עכשיו" (UTC ISO 8601). קריאה חוזרת על אותו key
    פשוט דורסת את החותמת הקודמת - רק החלפה *אחרונה* רלוונטית לגיל."""
    data = _load()
    data[key] = datetime.now(timezone.utc).isoformat()
    os.makedirs(os.path.dirname(ROTATION_LOG_PATH), exist_ok=True)
    with open(ROTATION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_rotation_date(key: str) -> Optional[str]:
    """מחזיר את חותמת הזמן (ISO) של הסבב האחרון, או None אם מעולם לא נרשם -
    כלומר הסוד הוגדר ידנית ב-.env ולא דרך set_secret() אף פעם, ואין לנו שום
    דרך לדעת מתי זה קרה."""
    return _load().get(key)


def get_age_days(key: str) -> Optional[int]:
    """מספר הימים מאז הסבב האחרון, או None אם לא ידוע בכלל (ראו get_rotation_date) -
    None שונה במכוון מ-0: "לא ידוע" אינו "היום", ואסור לדגל את זה כ"טרי"."""
    recorded = get_rotation_date(key)
    if not recorded:
        return None
    try:
        recorded_dt = datetime.fromisoformat(recorded)
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - recorded_dt).days)


def is_stale(key: str, stale_after_days: int = DEFAULT_STALE_AFTER_DAYS) -> bool:
    """False גם כשהגיל לא ידוע בכלל - אין ראיה לסמן את זה כישן, רק "לא ידוע"
    (מוצג אחרת בממשק, לא כאזהרה אדומה)."""
    age = get_age_days(key)
    return age is not None and age >= stale_after_days
