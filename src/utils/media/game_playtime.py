# utils/media/game_playtime.py
#
# צובר "שעות משחק" מצטברות לכל משחק (item: personal stats dashboard) - עד כה
# game_detector.check_active_game() רק זיהה משחק פעיל *עכשיו* (למעבר ערכת-נושא/
# מצב טורבו), בלי לשמור שום היסטוריה. gui_manager.pyw's game_loop() כבר בודק כל
# 5 שניות בדיוק בזמן שהדסקטופ פתוח - record_playtime_tick() נקרא משם עם אותם 5
# שניות בכל פעם שזוהה משחק, ומצטבר לפי game_key ל-DB המשותף (אותו data_paths.BOT_DB
# שגם job_history.py/hardware_history.py כותבים אליו).
#
# מגבלה ידועה, לא באג: נצבר רק כשה-GUI הדסקטופי פתוח ורץ (game_loop רק שם) -
# משחק שרץ בזמן שה-launcher סגור לא נספר. זהה במהותו למגבלת turbo mode עצמה
# (גם היא תלויה ב-game_loop הזה בדיוק) - לא תשתית חדשה, אותה תשתית קיימת בדיוק.

from datetime import datetime

from utils.shared import db
from utils.media.game_detector import GAME_DISPLAY_NAMES
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)


def _ensure_table():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_playtime (
                game_key TEXT PRIMARY KEY,
                total_seconds INTEGER NOT NULL DEFAULT 0,
                last_played_at TEXT
            )
        """)
        # פירוק יומי (item: annual "Wrapped" video) - הטבלה למעלה היא סך-הכל
        # מצטבר-לנצח בלבד, בלי שום ציר זמן - אי אפשר לשחזר ממנה "כמה שעות
        # השנה" בדיעבד. טבלה נפרדת (לא שינוי סכימה של הטבלה הקיימת - בלי
        # מיגרציה מסוכנת לנתונים שכבר נצברו) שנכתבת יחד עם game_playtime בכל
        # tick, כדי שצבירה-לפי-תקופה (שנה/חודש) תהיה זמינה מעכשיו והלאה. וידאו
        # "Wrapped" שנוצר סמוך למועד השקת התכונה הזו יראה מספר שעות קטן/אמיתי
        # בכוונה - לא בדוי - בדיוק כמו המגבלה המתועדת כבר למעלה על game_playtime עצמה.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_playtime_daily (
                game_key TEXT NOT NULL,
                day TEXT NOT NULL,
                seconds INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (game_key, day)
            )
        """)


def record_playtime_tick(game_key, seconds):
    """מוסיף seconds לסך המצטבר של game_key (כמו שמוחזר מ-check_active_game -
    למשל "Rocket League"), יוצר שורה חדשה אם זו הפעם הראשונה שהמשחק הזה נראה.
    מעדכן גם game_playtime_daily (ראו שם) - אותו tick בדיוק, בלי לולאת polling נוספת."""
    _ensure_table()
    now = datetime.now()
    now_iso = now.isoformat(timespec="seconds")
    today_iso = now.date().isoformat()
    with db.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO game_playtime (game_key, total_seconds, last_played_at) VALUES (?, ?, ?)
            ON CONFLICT(game_key) DO UPDATE SET
                total_seconds = total_seconds + excluded.total_seconds,
                last_played_at = excluded.last_played_at
            """,
            (game_key, seconds, now_iso),
        )
        conn.execute(
            """
            INSERT INTO game_playtime_daily (game_key, day, seconds) VALUES (?, ?, ?)
            ON CONFLICT(game_key, day) DO UPDATE SET seconds = seconds + excluded.seconds
            """,
            (game_key, today_iso, seconds),
        )


def get_playtime_summary():
    """[(display_name, total_seconds, last_played_at), ...] ממוין מהכי-הרבה
    שעות. display_name דרך GAME_DISPLAY_NAMES (נופל לשם ה-key הגולמי אם משחק
    כלשהו לא נמצא שם - לא אמור לקרות בפועל, אבל לא מונע הצגה אם קרה)."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT game_key, total_seconds, last_played_at FROM game_playtime ORDER BY total_seconds DESC"
        ).fetchall()
    return [(GAME_DISPLAY_NAMES.get(key, key), total_seconds, last_played_at) for key, total_seconds, last_played_at in rows]


def get_playtime_summary_for_year(year):
    """כמו get_playtime_summary, אבל מסונן לשנה קלנדרית ספציפית בלבד (item:
    annual "Wrapped" video) - מבוסס על game_playtime_daily, לא על הסך-הכל
    המצטבר-לנצח. שנה בלי אף tick מוחזרת כרשימה ריקה, לא שגיאה."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT game_key, SUM(seconds) FROM game_playtime_daily WHERE day LIKE ? GROUP BY game_key ORDER BY SUM(seconds) DESC",
            (f"{year}-%",),
        ).fetchall()
    return [(GAME_DISPLAY_NAMES.get(key, key), total_seconds) for key, total_seconds in rows]
