# utils/shared/hardware_history.py
#
# היסטוריית שימוש בחומרה מעבר לחלון הזמן הקצר שכבר קיים בזיכרון (utils/shared/hardware.py's
# cpu_history/ram_history/gpu_history/vram_history - כ-3 דקות בקצב הרענון של
# הסיידבר, ונעלם לגמרי עם restart). נשמר ל-DB כדי שגרף "24 השעות האחרונות"
# (item: historical hardware usage graph) יעבוד גם אחרי סגירה ופתיחה מחדש.
#
# לא כל דגימה נרשמת - get_system_stats() (utils/shared/hardware.py) נקרא כל 1.5-2
# שניות מכמה מקומות (סיידבר הדסקטופ, polling של web_app.py) - לרשום כל קריאה
# היה יוצר עשרות אלפי שורות ביום בלי תועלת אמיתית לגרף. record_sample() דוגם
# לכל היותר פעם ב-RECORD_INTERVAL_SECONDS, ומדלג בשקט על כל קריאה שביניהן.

import time
from datetime import datetime, timedelta

from utils.shared import db
from utils.shared import data_paths

# אותו קובץ DB בדיוק כמו job_history.py/audit_log.py - מחושב באופן עצמאי (לא
# import של job_history.DB_PATH) כדי ש-DB_PATH כאן יהיה ניתן ל-monkeypatch
# בבידוד מלא בטסטים (בדיוק כמו בכל מודול אחר בקודבייס הזה) - אחרת טסט שמחליף
# את job_history.DB_PATH לא היה משפיע על המודול הזה, וקריאות ל-get_recent_samples/
# record_sample במהלך טסטים אחרים (למשל בניית StatsTabComponent) היו נוגעות
# ב-DB האמיתי של הפרויקט בפועל.
DB_PATH = data_paths.path(data_paths.BOT_DB)

RECORD_INTERVAL_SECONDS = 60
RETENTION_DAYS = 7

_last_recorded_at = 0.0


def _ensure_table():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hardware_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recorded_at TEXT,
                cpu REAL,
                ram REAL,
                gpu REAL,
                vram REAL,
                encoder REAL
            )
        """)


def record_sample(cpu, ram, gpu=None, vram=None, encoder=None, force=False):
    """דוגם דגימה אחת (או מדלג בשקט אם עוד לא עבר RECORD_INTERVAL_SECONDS מאז
    הדגימה האחרונה - force=True עוקף את זה, לשימוש בטסטים). gpu/vram/encoder
    יכולים להיות None (אין GPU של NVIDIA זמין, ראו utils/shared/hardware.py)."""
    global _last_recorded_at
    now = time.time()
    if not force and (now - _last_recorded_at) < RECORD_INTERVAL_SECONDS:
        return
    _last_recorded_at = now

    _ensure_table()
    with db.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO hardware_history (recorded_at, cpu, ram, gpu, vram, encoder) VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), cpu, ram, gpu, vram, encoder)
        )
        cutoff_iso = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat(timespec="seconds")
        conn.execute("DELETE FROM hardware_history WHERE recorded_at < ?", (cutoff_iso,))


def get_recent_samples(hours=24):
    """מחזיר [(recorded_at, cpu, ram, gpu, vram, encoder), ...] מה-hours האחרונות,
    ממוין מהישן לחדש (סדר טבעי לציור גרף משמאל לימין)."""
    _ensure_table()
    since_iso = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT recorded_at, cpu, ram, gpu, vram, encoder FROM hardware_history "
            "WHERE recorded_at >= ? ORDER BY recorded_at ASC",
            (since_iso,)
        ).fetchall()
    return rows
