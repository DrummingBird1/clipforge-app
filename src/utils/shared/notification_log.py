# utils/shared/notification_log.py
#
# 23.10.2026: מרכז ההתראות - אירועים שכדאי לראות גם אחרי שעברת מסך או סגרת את הטאב: ריצה שהסתיימה או נכשלה, תיקיית
# ייצוא שלא הייתה זמינה, בוט שהפסיק לעלות. נשמר באותו DB כמו job_history (data_paths.BOT_DB), בטבלה משלו, עם
# "נקרא" אחד לכולם - המחשב והטלפון רואים אותו מונה. נרשם בצד השרת, ברגע האירוע: לולאת ה-/ws רצה רק כשטאב מחובר.
import time
from contextlib import contextmanager
from typing import Iterator, List, Optional

from utils.shared import db
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)
KEEP = 300                                  # הישנות נמחקות כשנוספת חדשה - זו רשימת התראות, לא היסטוריה
LEVELS = ("info", "ok", "warn", "bad")
MAX_TEXT = 500


@contextmanager
def _open(path: str) -> Iterator:
    """חיבור שנסגר בסוף (with של sqlite3 רק עושה commit - ב-Windows חיבור פתוח נועל את הקובץ)."""
    conn = db.connect(path or DB_PATH)
    try:
        with conn:
            _ensure_table(conn)
            yield conn
    finally:
        conn.close()


def _ensure_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            kind TEXT NOT NULL,
            level TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            target TEXT NOT NULL DEFAULT '',
            read INTEGER NOT NULL DEFAULT 0
        )
    """)


def add(kind: str, title: str, body: str = "", level: str = "info", target: str = "", path: str = "") -> int:
    """target: לאן לחיצה על ההתראה מובילה - שם מסך (outputs, bot, globalsettings) או scripts."""
    with _open(path) as conn:
        cursor = conn.execute(
            "INSERT INTO notifications (created_at, kind, level, title, body, target) VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), kind, level if level in LEVELS else "info", title[:MAX_TEXT], (body or "")[:MAX_TEXT], target),
        )
        new_id = cursor.lastrowid or 0
        conn.execute("DELETE FROM notifications WHERE id <= ?", (new_id - KEEP,))
    return new_id


def recent(limit: int = 50, path: str = "") -> List[dict]:
    with _open(path) as conn:
        rows = conn.execute(
            "SELECT id, created_at, kind, level, title, body, target, read FROM notifications ORDER BY id DESC LIMIT ?",
            (max(1, min(int(limit), KEEP)),),
        ).fetchall()
    keys = ("id", "created_at", "kind", "level", "title", "body", "target", "read")
    return [{**dict(zip(keys, row)), "read": bool(row[7])} for row in rows]


def unread(path: str = "") -> dict:
    """{"unread": כמה לא נקראו, "latest": המזהה האחרון (0 כשאין)} - בשביל המונה, שאלה אחת קטנה."""
    with _open(path) as conn:
        count, latest = conn.execute("SELECT COALESCE(SUM(read = 0), 0), COALESCE(MAX(id), 0) FROM notifications").fetchone()
    return {"unread": int(count), "latest": int(latest)}


def mark_read(up_to: Optional[int] = None, path: str = "") -> None:
    """עד המזהה שהוצג (כולל) - התראה שהגיעה בזמן שהרשימה הייתה פתוחה נשארת לא-נקראה."""
    with _open(path) as conn:
        if up_to is None:
            conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        else:
            conn.execute("UPDATE notifications SET read = 1 WHERE read = 0 AND id <= ?", (int(up_to),))
