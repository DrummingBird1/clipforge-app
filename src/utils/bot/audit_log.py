# utils/bot/audit_log.py
#
# לוג הביקורת (audit_log) נוצר במקור ע"י cogs/remote_execution.py, שכותב
# אליו א-סינכרונית דרך aiosqlite (bot.db) - זמין רק בתוך תהליך הבוט עצמו.
# web_app.py (תהליך FastAPI נפרד לגמרי, בלי גישה ל-bot.db) לא הייתה לו שום
# דרך לתעד פעולות (הרצת/עצירת סקריפט) לאותו לוג - פעולות מהדפדפן פשוט לא
# נראו בכלל ב-/status או ב-/audit_log של הבוט. פונקציה סינכרונית משותפת כאן
# (אותו עיקרון בדיוק כמו utils/shared/job_history.py - db.connect() סינכרוני על
# אותו קובץ DB) נותנת לשני התהליכים לכתוב לאותה טבלה בדיוק.

import sqlite3

from utils.shared import db
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)


def _ensure_table():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, username TEXT, command TEXT, details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # source: "discord" (ברירת המחדל, לפעולות שכבר נכתבו לפני העמודה
        # הזו) או "web" - אותו דפוס מיגרציה אידמפוטנטי בדיוק כמו result_json
        # ב-job_history.py/resolved_at ב-approval_cog.py.
        try:
            conn.execute("ALTER TABLE audit_log ADD COLUMN source TEXT DEFAULT 'discord'")
        except sqlite3.OperationalError:
            pass


def record_action(source, command, details="", user_id=None, username=None):
    """source: "web"/"discord" וכו'. user_id/username רלוונטיים בעיקר לדיסקורד
    (זהות אמיתית) - ל-web_app.py אין זהות משתמש אמיתית (טוקן משותף בלבד),
    אז username יכול להיות כתובת ה-IP של המבקש במקום שם משתמש."""
    try:
        _ensure_table()
        with db.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO audit_log (user_id, username, command, details, source) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, command, details, source)
            )
    except Exception as e:
        print(f"[audit_log] שגיאה בכתיבת לוג ביקורת: {e}")


def get_recent_actions(limit=15):
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT username, command, details, timestamp, source FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return rows
