# utils/shared/install_profile.py
#
# 30.10.2026 (לפני ההפצה הציבורית): הגדרות ב-config.json שהקוד צריך ערך בשבילן - מילות הסינון של RSS (ריק = הכל עובר), אזור
# ושפת החנות של Steam, וקונטיינר ה-Docker שהדסקטופ מפעיל (ריק = בלי) - עם ברירות מחדל ניטרליות (DEFAULTS). והשפה: אין
# config.json = התקנה חדשה ("en"); config.json קיים בלי "language" = התקנה מלפני 30.10.2026 ("he"). ensure() כותב את
# השפה ואת המפתחות החסרים פעם אחת (ensure_language של השרת והבוט קוראים לו); read() רק קורא, עם אותן ברירות מחדל.
import json
from typing import Any, Dict, Optional

from utils.shared.atomic_write import atomic_write_json
from utils.shared.file_lock import file_lock
from utils.shared.ui_language import EXISTING_INSTALL as EXISTING_LANGUAGE, LANGUAGES, NEW_INSTALL as NEW_LANGUAGE

DEFAULTS: Dict[str, Any] = {"rss_keywords": [], "steam_country": "us", "steam_language": "english", "docker_container": ""}
NEW_INSTALL = DEFAULTS   # השם הקודם - טסטים ומודולים שכבר מייבאים אותו


def defaults(_config: Optional[dict] = None) -> Dict[str, Any]:
    """ברירות המחדל למפתח שחסר - אותן בכל התקנה. עותק - בטוח לשנות."""
    return json.loads(json.dumps(DEFAULTS))


def _load(config_file: str):
    """(config, ok): None כשאין קובץ; ok=False לקובץ פגום (לא נוגעים בו)."""
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        return None, True
    except (OSError, ValueError):
        return {}, False
    return (config, True) if isinstance(config, dict) else ({}, False)


def language_of(config: Optional[dict]) -> str:
    """ההחלטה על השפה: מה שנשמר; אחרת "en" להתקנה חדשה (אין config.json) ו-"he" לקיימת. ensure ו-read_language משתמשים בה."""
    saved = (config or {}).get("language")
    return saved if saved in LANGUAGES else (NEW_LANGUAGE if config is None else EXISTING_LANGUAGE)


def read_language(config_file: str) -> str:
    """השפה של ההתקנה בלי לכתוב (ui_language.current). קובץ פגום - עברית, כמו ensure."""
    config, ok = _load(config_file)
    return language_of(config) if ok else EXISTING_LANGUAGE


def read(config_file: str) -> Dict[str, Any]:
    """config.json עם ברירות המחדל של ההתקנה למה שחסר. לא כותב."""
    config, _ok = _load(config_file)
    return {**defaults(config), **(config or {})}


def ensure(config_file: str, lock_file: str) -> Dict[str, Any]:
    """מחליט פעם אחת על השפה ("en" להתקנה חדשה, "he" לקיימת) וכותב ל-config.json אותה ואת המפתחות של DEFAULTS שחסרים.
    קובץ פגום לא נדרס: מחזיר את ברירות המחדל, בעברית. מחזיר את ההגדרות."""
    with file_lock(lock_file):
        config, ok = _load(config_file)
        if not ok:
            return {**defaults({}), "language": EXISTING_LANGUAGE}
        current = config or {}
        language = language_of(config)
        updated = {**defaults({"language": language}), **current, "language": language}
        if updated != config:
            atomic_write_json(config_file, updated, ensure_ascii=False, indent=4)
        return updated
