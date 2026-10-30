# utils/shared/log_cleanup.py
#
# מדיניות ניקוי לוגים (item 26) - utils/shared/logging_setup.py כבר מגביל את גודל
# כל קובץ לוג בודד (RotatingFileHandler, 5MB לקובץ, עד 3 גיבויים), אבל זו
# הגנת-גודל בלבד: קובץ גיבוי שנוצר ונשאר קטן (תהליך שרץ לעיתים רחוקות, כמו
# web_dashboard.py) יכול תיאורטית להישאר על הדיסק לצמיתות בלי סיבה. השכבה
# השנייה כאן מוסיפה הגנת-זמן: קובץ גיבוי (לא הקובץ הפעיל עצמו!) שעבר
# max_age_days נמחק, בלי קשר לגודלו.
import glob
import os
import time

from utils.shared import data_paths

LOGS_DIR = data_paths.path(data_paths.LOGS)
DEFAULT_MAX_AGE_DAYS = 30


def purge_old_log_backups(logs_dir=LOGS_DIR, max_age_days=DEFAULT_MAX_AGE_DAYS):
    """מוחק קבצי-גיבוי של לוגים מתגלגלים (gui.log.1, web_app.log.2 וכו' -
    התבנית שבה RotatingFileHandler משתמש) שעברו max_age_days ימים. בכוונה
    *לא* נוגע בקובץ ה-.log הפעיל עצמו (בלי סיומת מספרית) - הוא עשוי להיות
    פתוח כרגע ב-handle של תהליך חי (GUI/בוט/web_app), ומחיקת קובץ פתוח
    ב-Windows עלולה להיכשל או להתנהג בצורה לא צפויה. מחזיר רשימת שמות
    הקבצים שנמחקו בפועל (לצורך לוג/דיווח לקורא)."""
    cutoff = time.time() - max_age_days * 86400
    deleted = []
    # *.log.* וגם *.jsonl.* - item: לוגים מובנים (JSON-lines) הוסיף קובץ .jsonl
    # מתגלגל לצד כל .log, עם אותה תבנית גיבוי בדיוק (RotatingFileHandler), אז
    # אותה מדיניות-זמן חלה על שניהם.
    patterns = ("*.log.*", "*.jsonl.*")
    for pattern in patterns:
        for path in glob.glob(os.path.join(logs_dir, pattern)):
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    deleted.append(os.path.basename(path))
            except OSError:
                pass
    return deleted
