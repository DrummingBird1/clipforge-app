# utils/bot/approval_store.py
#
# גישה סינכרונית (sqlite3 רגיל, לא aiosqlite) לטבלת pending_approvals -
# cogs/approval_cog.py כבר מנהל את הטבלה הזו אסינכרונית (self.bot.db,
# aiosqlite) מתוך תהליך הבוט; web_app.py/gui_manager.pyw רצים כתהליכים
# נפרדים לגמרי (אין חיבור aiosqlite חי לשתף), אז זו גישה עצמאית לאותו קובץ
# DB - אותו דפוס בדיוק כמו web_app.py's _ensure_bot_tables() ל-rss_feeds/
# steam_games (שכפול מכוון של סכימת הטבלה, לא ייבוא cogs.approval_cog - זה
# היה מכניס תלות ב-discord.py לתהליכים שלא צריכים אותה בכלל). מייצא גם את
# קבועי הנתיבים (CLIPS_REVIEW_DIR/REJECTED_DIR/get_rocket_input_dir) - אלה
# כן מיובאים חזרה מ-approval_cog.py, כדי שלא יהיו שני מקורות אמת לנתיבים.
#
# item: mobile-friendly clip-approval view - מאפשר גם לדסקטופ וגם לווב
# לאשר/לדחות קליפים ישירות, בלי תלות בזה שהבוט עצמו רץ.

import datetime
import json
import os
import sqlite3

from utils.shared import db
from utils.shared.workspace_dir import WORKSPACE_DIR
from utils.shared import data_paths
from utils.shared.data_dir import DATA_DIR

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB_PATH = data_paths.path(data_paths.BOT_DB)
# תחת WORKSPACE_DIR (CLIPFORGE_WORKSPACE_DIR) - אותה תיקייה כמו web_app.CLIPS_DIR; קודם קבוע ל-<שורש>/workspace,
# ושרת עם workspace אחר אישר/דחה קליפים מהתיקייה הראשית
CLIPS_REVIEW_DIR = os.path.join(WORKSPACE_DIR, "clips")
REJECTED_DIR = os.path.join(WORKSPACE_DIR, "clips_rejected")
# item: friend detection via Discord voice channel presence - נפרד מ-
# web_app.py's TAGS_CACHE_DIR (JSON אחר לגמרי: שמות-משתמשים, לא תגיות-AI),
# אבל אותה מוסכמת מטמון (tags_cache_path/read_cached_tags הגנריים ב-
# utils/media/clip_tagger.py, ראו cogs/approval_cog.py's _detect_and_cache_friends).
FRIEND_TAGS_CACHE_DIR = os.path.join(WORKSPACE_DIR, ".friend_tags_cache")


def use_workspace_dir(path):
    """סבב ייצוב: web_app.use_workspace_dir (שרת בדיקה) מזיז בזמן ריצה גם את תיקיות אישור הקליפים - אותו מבנה כמו למעלה."""
    global CLIPS_REVIEW_DIR, REJECTED_DIR, FRIEND_TAGS_CACHE_DIR
    CLIPS_REVIEW_DIR = os.path.join(path, "clips")
    REJECTED_DIR = os.path.join(path, "clips_rejected")
    FRIEND_TAGS_CACHE_DIR = os.path.join(path, ".friend_tags_cache")


def get_rocket_input_dir():
    settings_path = data_paths.path(data_paths.ROCKET_SETTINGS, DATA_DIR)   # DATA_DIR של המודול - טסטים מחליפים אותו
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f).get("input_dir", BASE_DIR)
        except Exception:
            pass
    return BASE_DIR


def _ensure_table():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                channel_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # אותה מיגרציה בדיוק כמו cogs/approval_cog.py's _ensure_table - ראו שם.
        try:
            conn.execute("ALTER TABLE pending_approvals ADD COLUMN resolved_at TEXT")
        except sqlite3.OperationalError:
            pass


def get_pending_approvals():
    """[(id, video_path, created_at), ...] - רק status='pending', מהישן
    לחדש (FIFO - הקליפ שממתין הכי הרבה זמן מוצג ראשון)."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, video_path, created_at FROM pending_approvals WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
    return rows


def validate_pending_video_path(path):
    """מוודא שהנתיב הוא קובץ אמיתי בתוך CLIPS_REVIEW_DIR - זהה לוולידציית
    web_app.py's _validate_clip_path, כדי שהאישור/התמונה הממוזערת לא יהפכו
    לשרת-קבצים כללי לכל נתיב שרירותי."""
    if not path:
        return None
    real_path = os.path.realpath(path)
    real_review_dir = os.path.realpath(CLIPS_REVIEW_DIR)
    if not (real_path == real_review_dir or real_path.startswith(real_review_dir + os.sep)):
        return None
    if not os.path.isfile(real_path):
        return None
    return real_path


def resolve_pending(pending_id, video_path, approved):
    """זהה בעיקרון ל-cogs/approval_cog.py's ApprovalCog.resolve_pending - אותה
    לוגיקה בדיוק (העברת קובץ ל-Import/נדחים + עדכון status/resolved_at), רק
    סינכרוני (sqlite3, לא aiosqlite) כדי לרוץ מתהליך הדסקטופ/הווב."""
    _ensure_table()
    dest_dir = get_rocket_input_dir() if approved else REJECTED_DIR
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(video_path))

    if os.path.exists(video_path):
        os.replace(video_path, dest)

    with db.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE pending_approvals SET status = ?, resolved_at = ? WHERE id = ?",
            ("approved" if approved else "rejected", datetime.datetime.now().isoformat(), pending_id),
        )
