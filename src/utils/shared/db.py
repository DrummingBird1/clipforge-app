# utils/shared/db.py
#
# מקור אמת יחיד לפתיחת חיבור ל-DB המשותף (data_paths.BOT_DB) באופן סינכרוני (sqlite3, לא
# aiosqlite). כמה תהליכים נפרדים ניגשים לאותו קובץ DB בו-זמנית - הבוט (main.py,
# דרך aiosqlite), ה-GUI (job_history.py, ui/bot_tab.py, דרך sqlite3 ישיר), וה-
# תזמון האוטומטי (scheduler_cog.py). מצב journal ברירת המחדל של SQLite (rollback
# journal) נועל את כל הקובץ בזמן כתיבה ומונע קריאה מקבילה - עם WAL, קוראים
# יכולים להמשיך לעבוד בזמן שמישהו אחר כותב. busy_timeout קובע כמה זמן לחכות על
# נעילה לפני שזורקים "database is locked" (Python's sqlite3 מוגדר כברירת מחדל
# ל-5 שניות - כאן מאריכים קצת ובמפורש, בשביל בהירות).

import os
import sqlite3

from utils.shared import data_paths

BUSY_TIMEOUT_MS = 10000


def connect(db_path, timeout=10.0):
    # 30.10.2026: תהליך שחישב את הנתיב לפני ש-data_paths.migrate_bot_db העביר את ה-DB לשם החדש - לא יוצרים DB ריק בשם הישן
    if not os.path.exists(db_path) and data_paths.is_legacy_bot_db(os.path.basename(db_path)):
        db_path = data_paths.path(data_paths.BOT_DB)
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    # WAL נשמר בקובץ עצמו - מעבר אליו רק כשעוד לא שם. המעבר דורש נעילה בלעדית ש-SQLite לא תמיד ממתין לה
    # (busy_timeout לא חל), אז "PRAGMA journal_mode=WAL" בכל חיבור זרק "database is locked" כשכמה תהליכים
    # פותחים חיבור בבת אחת (נמצא ב-16.10.2026 בטסטים במקביל: 14 תהליכים על אותו DB). קריאת המצב לא נועלת.
    if str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower() != "wal":
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass   # תהליך אחר מעביר את הקובץ ל-WAL באותו רגע; החיבור הזה עובד גם בלעדיו, והבא כבר יראה WAL
    return conn
