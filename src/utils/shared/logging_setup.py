# utils/shared/logging_setup.py
#
# הקוד הקיים בכל הפרויקט משתמש ב-print() בלבד (מאות מקומות) - להחליף את כל זה
# ל-logging.getLogger() בכל קובץ זה refactor ענק ומיותר לסיכון שבו. במקום זה,
# "מצטרפים" (tee) ל-stdout/stderr הקיימים: כל print() ממשיך לעבוד בדיוק כמו
# קודם (למסך/ל-textbox של ה-GUI), אבל גם נכתב לקובץ log מתגלגל בדיסק - כדי
# שיהיה אפשר לפתוח מה שקרה אחרי סגירת הטרמינל/GUI (למשל אחרי ריצה שקרסה בלילה).

import io
import json
import logging
import os
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from utils.shared import data_paths

LOGS_DIR = data_paths.path(data_paths.LOGS)

MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

# item: לוגים מובנים (JSON-lines) לצד הלוג הרגיל - קידומות שכל print() בפרויקט
# הזה כבר משתמש בהן בפועל (ראו my_scripts/video/video_editor.py וכו') הופכות
# לשדה level אמיתי, כדי ששאילתה עתידית ("תראה לי רק שגיאות מהשבוע") לא תצטרך
# לפרסר regex על טקסט חופשי. סדר הבדיקה חשוב: "[SUCCESS]"/"[APPROVED]" לפני
# "[SKIP]" וכו' - קידומות ספציפיות יותר קודם, כדי ש-startswith לא יתבלבל בין
# קידומות עם אותה תחילית (לא קיים כרגע בפועל, אבל עמיד לשינוי עתידי).
_LEVEL_PREFIXES = (
    ("[ERROR]", "error"),
    ("[WARNING]", "warning"),
    ("[SUCCESS]", "success"),
    ("[APPROVED]", "success"),
    ("[SKIP]", "skip"),
    ("[INFO]", "info"),
)


def _infer_level(message):
    for prefix, level in _LEVEL_PREFIXES:
        if message.startswith(prefix):
            return level
    return "info"


class _JsonLinesFormatter(logging.Formatter):
    """שורה אחת = רשומת JSON אחת - נבנה כ-Formatter (לא Handler נפרד) כדי
    לרשת בחינם את כל לוגיקת הסיבוב (RotatingFileHandler) הקיימת, בלי לשכפל
    אותה. record.created (לא datetime.now()) - חותמת הזמן האמיתית של הרשומה,
    לא של רגע הכתיבה לדיסק (יכולים להיות שונים תחת עומס)."""

    def format(self, record):
        message = record.getMessage()
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": _infer_level(message),
            "logger": record.name,
            "message": message,
        }
        return json.dumps(payload, ensure_ascii=False)


class _TeeStream(io.TextIOBase):
    """עוטף stream קיים (stdout/stderr) - כל כתיבה ממשיכה גם למקור וגם ל-logger.
    __getattr__ מעביר קריאות לא-מוכרות (כמו .reconfigure()) למקור, כך שקוד קיים
    שמכוון UTF-8 על sys.stdout לפני/אחרי העטיפה הזו ממשיך לעבוד כרגיל.

    _local.in_write (item: בדיקת באגים - RecursionError שהפיל ריצת רינדור
    שלמה) - הגנה מפני רקורסיה אינסופית: כשל אמיתי בתוך handler (למשל
    RotatingFileHandler.doRollover נתקל בקובץ נעול ע"י תהליך אחר, שכיח ב-
    Windows) מפעיל את logging.Handler.handleError() המובנה, שכותב ל-
    sys.stderr כברירת מחדל - וכשזה ה-stderr המשוכפל הזה עצמו, אותה כתיבה
    הייתה חוזרת ל-self._logger.info כאן, דרך אותו logger/handler שבדיוק
    נכשל, שוב ושוב עד RecursionError (שמפיל לא רק את שורת-השגיאה אלא את כל
    הקוד שבדיוק ניסה לכתוב/ללוגג, למשל utils/shared/worker.py's לולאת קריאת-הפלט
    שקוראת ל-print/logger.info עבור כל שורה מתת-תהליך רינדור). threading.local
    (לא flag יחיד על ה-instance) - כדי שכתיבה מקבילה אמיתית מ-thread אחר לא
    תיחסם בטעות בחלון הזמן הקצר הזה."""

    def __init__(self, original_stream, logger):
        self._original = original_stream
        self._logger = logger
        self._local = threading.local()

    def write(self, s):
        try:
            self._original.write(s)
        except Exception:
            pass
        cleaned = s.strip() if isinstance(s, str) else ""
        if cleaned and not getattr(self._local, "in_write", False):
            self._local.in_write = True
            try:
                self._logger.info(cleaned)
            except Exception:
                pass
            finally:
                self._local.in_write = False
        return len(s)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._original, name)


def setup_persistent_logging(log_name, tee_stdio=True):
    """מפעיל שכפול stdout+stderr לקובץ data/logs/<log_name>.log (מתגלגל, עד
    5MB * 4 עותקים), ובמקביל לקובץ data/logs/<log_name>.jsonl מובנה (item:
    לוגים מובנים) - אותה רשומה בדיוק, בשני פורמטים, לא שני מנגנוני לכידה
    נפרדים. קוראים לזה פעם אחת, כמה שיותר מוקדם בקובץ הכניסה הראשי
    (main.py / gui_manager.pyw / web_dashboard.py).

    tee_stdio=False (item: log spam - script_runs logger ב-utils/shared/worker.py)
    - מקבל logger מתגלגל בדיוק כמו כל קורא אחר, בלי לחטוף את stdout/stderr
    הגלובליים של התהליך (הם כבר משוכפלים פעם אחת דרך קריאה אחרת ל-log_name
    שונה מנקודת הכניסה - חטיפה שנייה הייתה מזרימה לשם גם כל print() סתמי,
    לא רק את השורות המפורשות שנשלחות ל-logger.info() ישירות)."""
    import sys

    os.makedirs(LOGS_DIR, exist_ok=True)
    log_path = os.path.join(LOGS_DIR, f"{log_name}.log")
    json_log_path = os.path.join(LOGS_DIR, f"{log_name}.jsonl")

    logger = logging.getLogger(f"persistent.{log_name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(log_path, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(handler)

        json_handler = RotatingFileHandler(json_log_path, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
        json_handler.setFormatter(_JsonLinesFormatter())
        logger.addHandler(json_handler)

    if tee_stdio:
        if not isinstance(sys.stdout, _TeeStream):
            sys.stdout = _TeeStream(sys.stdout, logger)
        if not isinstance(sys.stderr, _TeeStream):
            sys.stderr = _TeeStream(sys.stderr, logger)

    return logger
