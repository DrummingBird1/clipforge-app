# utils/bot/discord_outbox.py
#
# 16.11.2026 (ClipForge 2.0): "שלח לדיסקורד" מהממשק. השרת והבוט הם שני תהליכים - השרת מכניס בקשה לטבלה ב-DB של הבוט
# (clipforge_data.db, אותו DB של האישורים), והבוט (cogs/clip_share_cog.py) שולף, שולח לערוץ ומסמן. הערוץ נשמר באותו DB
# (נקבע בדיסקורד ב-/clip_channel). בלי תלות ב-discord.py - גם השרת וגם הטסטים משתמשים בזה.
import datetime
import os
import sqlite3
from typing import Any, Dict, List, Optional

from utils.shared import data_paths, db

DB_PATH = data_paths.path(data_paths.BOT_DB)
MAX_ATTEMPTS = 3
RETRY_SECONDS = 60      # 17.11.2026: בין ניסיון לניסיון (כפול מספר הניסיון). קודם שלושה ניסיונות נגמרו תוך 45 שניות.


def _db(db_path: Optional[str]) -> str:
    return db_path or DB_PATH


def ensure_tables(db_path: Optional[str] = None) -> None:
    path = _db(db_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with db.connect(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS discord_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, message TEXT DEFAULT '', channel_id INTEGER,
            status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT, created_at TEXT, sent_at TEXT)""")
        conn.execute("CREATE TABLE IF NOT EXISTS discord_share_settings (key TEXT PRIMARY KEY, value TEXT)")
        if "next_try_at" not in {row[1] for row in conn.execute("PRAGMA table_info(discord_outbox)")}:
            conn.execute("ALTER TABLE discord_outbox ADD COLUMN next_try_at TEXT")


def set_channel(channel_id: int, db_path: Optional[str] = None) -> None:
    ensure_tables(db_path)
    with db.connect(_db(db_path)) as conn:
        conn.execute("INSERT OR REPLACE INTO discord_share_settings (key, value) VALUES ('channel_id', ?)", (str(int(channel_id)),))


def get_channel(db_path: Optional[str] = None) -> Optional[int]:
    ensure_tables(db_path)
    with db.connect(_db(db_path)) as conn:
        row = conn.execute("SELECT value FROM discord_share_settings WHERE key = 'channel_id'").fetchone()
    try:
        return int(row[0]) if row else None
    except (TypeError, ValueError):
        return None


def enqueue(path: str, message: str = "", channel_id: Optional[int] = None, db_path: Optional[str] = None) -> int:
    ensure_tables(db_path)
    with db.connect(_db(db_path)) as conn:
        cur = conn.execute("INSERT INTO discord_outbox (path, message, channel_id, created_at) VALUES (?, ?, ?, ?)",
                           (path, message[:1900], channel_id, datetime.datetime.now().isoformat(timespec="seconds")))
        return int(cur.lastrowid)


def pending(limit: int = 5, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_tables(db_path)
    with db.connect(_db(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM discord_outbox WHERE status = 'pending' AND attempts < ? "
                            "AND (next_try_at IS NULL OR next_try_at <= ?) ORDER BY id LIMIT ?",
                            (MAX_ATTEMPTS, datetime.datetime.now().isoformat(timespec="seconds"), limit)).fetchall()
    return [dict(r) for r in rows]


def mark(row_id: int, ok: bool, error: str = "", final: bool = False, db_path: Optional[str] = None) -> None:
    """ok - נשלח. כשל - attempts+1; final (קובץ חסר / גדול מדי) או אחרי MAX_ATTEMPTS - failed, לא מנסים שוב."""
    with db.connect(_db(db_path)) as conn:
        if ok:
            conn.execute("UPDATE discord_outbox SET status = 'sent', sent_at = ?, error = NULL WHERE id = ?",
                         (datetime.datetime.now().isoformat(timespec="seconds"), row_id))
            return
        attempts = (conn.execute("SELECT attempts FROM discord_outbox WHERE id = ?", (row_id,)).fetchone() or [0])[0] + 1
        retry_at = (datetime.datetime.now() + datetime.timedelta(seconds=RETRY_SECONDS * attempts)).isoformat(timespec="seconds")
        conn.execute("UPDATE discord_outbox SET attempts = ?, error = ?, next_try_at = ? WHERE id = ?", (attempts, error[:500], retry_at, row_id))
        conn.execute("UPDATE discord_outbox SET status = 'failed' WHERE id = ? AND (? OR attempts >= ?)", (row_id, int(final), MAX_ATTEMPTS))


def waiting(row_id: int, reason: str, db_path: Optional[str] = None) -> None:
    """הקליפ מחכה למשהו שאינו כשל (עוד לא נקבע ערוץ): הסיבה נרשמת, הניסיונות לא נספרים, והשורה נשארת בתור."""
    with db.connect(_db(db_path)) as conn:
        conn.execute("UPDATE discord_outbox SET error = ? WHERE id = ? AND status = 'pending'", (reason[:500], row_id))


def get(row_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    ensure_tables(db_path)
    with db.connect(_db(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id, path, status, error, attempts, created_at, sent_at FROM discord_outbox WHERE id = ?",
                           (row_id,)).fetchone()
    return dict(row) if row else None


def recent(limit: int = 10, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    ensure_tables(db_path)
    with db.connect(_db(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, path, status, error, created_at, sent_at FROM discord_outbox ORDER BY id DESC LIMIT ?",
                            (limit,)).fetchall()
    return [dict(r) for r in rows]
