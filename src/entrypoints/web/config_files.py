# entrypoints/web/config_files.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 5): קובצי ההגדרות - config.json, ההגדרות של Rocket והמונה שלו, וטבלאות הבוט ב-DB.
# עבר מ-web_app.py בלי שינוי התנהגות. web_app מייבא את השמות האלה בחזרה (web_app.<שם> נשאר), וה-routes ממשיכים לקרוא W.<שם>.
# כל שם שקיים גם ב-web_app נקרא דרך W. - טסטים מחליפים את web_app.<שם> (CONFIG_FILE, ROCKET_SETTINGS_PATH...), והקוד כאן
# צריך לראות את ההחלפה (tests/web/test_web_app_split.py בודק את זה).
import json
import os

from entrypoints import web_app as W


def _ensure_bot_tables():
    """יוצר את טבלאות RSS/Steam אם צריך - זהה ל-ui/bot_tab.py's _ensure_tables,
    למקרה שהבוט/GUI אף פעם לא רצו על המחשב הזה קודם."""
    with W.db.connect(W.BOT_DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, url TEXT, channel_id INTEGER
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS steam_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, app_id TEXT, channel_id INTEGER
        )""")


def _load_raw_config():
    """קורא את config.json הגולמי מהדיסק בכל פעם (לא דרך utils.shared.state.state,
    שהוא singleton עם עותק בזיכרון שנטען פעם אחת בהפעלת התהליך) - כך שהטופס
    תמיד משקף את המצב הנוכחי בפועל, גם אם ה-GUI השולחני שינה הגדרות בינתיים."""
    if not os.path.exists(W.CONFIG_FILE):
        return {}
    try:
        with open(W.CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_raw_config(config):
    W.atomic_write_json(W.CONFIG_FILE, config, ensure_ascii=False, indent=4)


def _default_config_dict():
    """זהה ל-state.reset_to_defaults()+save_config() ביחד - ראו utils/shared/state.py's
    CONFIG_SCHEMA (מקור אמת יחיד), כדי לא לשכפל את טבלת ברירות המחדל כאן."""
    defaults = {json_key: default for json_key, (_attr, _type, default) in W.CONFIG_SCHEMA.items()}
    defaults["ui_settings"] = dict(W.DEFAULT_UI_SETTINGS)
    return defaults


def _load_rocket_settings():
    if not os.path.exists(W.ROCKET_SETTINGS_PATH):
        return {}
    try:
        with open(W.ROCKET_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_rocket_settings(data):
    os.makedirs(os.path.dirname(W.ROCKET_SETTINGS_PATH), exist_ok=True)
    with open(W.ROCKET_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _get_rocket_counter():
    if os.path.exists(W.ROCKET_COUNTER_PATH):
        try:
            with open(W.ROCKET_COUNTER_PATH, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            pass
    return 1
