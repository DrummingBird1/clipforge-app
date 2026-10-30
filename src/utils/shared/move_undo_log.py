# utils/shared/move_undo_log.py
#
# יומן "בטל פעולה אחרונה" (item: undo last file-move operation) - scoped
# ל-my_scripts/video/cleanup_published_sources.py (shutil.move אמיתי לתיקיית
# ארכיון, אז "בטל" הוא פשוט להזיז בחזרה) - לא ל-my_scripts/tools/duplicate_cleaner.py
# (send2trash לסל המיחזור, שכבר יש לו "בטל" ברמת מערכת ההפעלה - שחזור מסל
# המיחזור - בלי API פרוגרמטי פשוט וחוצה-פלטפורמות לשחזור-לפי-נתיב-מקורי).
#
# רק ה-batch האחרון נשמר (לא היסטוריה מלאה) - קובץ JSON יחיד, לא טבלת DB;
# "בטל" הוא פעולה חד-פעמית מטבעה (מוחקת את עצמה אחרי שימוש), לא מידע שצריך
# להישאר שאילתא-בר לטווח ארוך כמו job_history.

import json
import os
import shutil
import time

from utils.shared import data_paths

UNDO_LOG_PATH = data_paths.path(data_paths.MOVE_UNDO_LOG)


def record_move_batch(script_name, moves):
    """moves: [{"src": ..., "dst": ...}, ...] - המקור/יעד המקוריים של כל קובץ
    שהועבר בהצלחה בריצה הזו. דורס כל batch קודם - "הפעולה האחרונה" בלבד, לא
    היסטוריה. moves ריק לא כותב כלום (ריצה שלא הזיזה שום קובץ אין מה לבטל בה,
    ולא רוצים לדרוס batch קודם אמיתי בביטול-של-כלום)."""
    if not moves:
        return
    payload = {"script_name": script_name, "recorded_at": time.time(), "moves": moves}
    os.makedirs(os.path.dirname(UNDO_LOG_PATH), exist_ok=True)
    with open(UNDO_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def get_last_move_batch():
    """None אם אין batch ממתין (אף פעם לא נרשם, כבר בוטל, או שהקובץ פגום)."""
    if not os.path.exists(UNDO_LOG_PATH):
        return None
    try:
        with open(UNDO_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def undo_last_move_batch():
    """מחזיר כל קובץ מה-batch האחרון בחזרה למקורו (dst -> src). מדלג (לא נכשל)
    על קובץ שה-dst שלו כבר לא קיים (הוזז/נמחק ידנית בינתיים), או שה-src כבר
    תפוס (קובץ אחר נוצר שם בינתיים - לא דורסים). מוחק את היומן בסוף בכל מקרה
    (הצליח או לא) - זו פעולה חד-פעמית, אי-אפשר "לבטל את הביטול". מחזיר
    {"restored": [...], "skipped": [...]}, או {"error": "..."} אם אין batch."""
    batch = get_last_move_batch()
    if batch is None:
        return {"restored": [], "skipped": [], "error": "אין פעולה להחזרה"}

    restored = []
    skipped = []
    for move in batch["moves"]:
        src, dst = move["src"], move["dst"]
        if not os.path.exists(dst):
            skipped.append({"src": src, "dst": dst, "reason": "קובץ הפלט כבר לא קיים"})
            continue
        if os.path.exists(src):
            skipped.append({"src": src, "dst": dst, "reason": "כבר קיים קובץ במקור - לא דורסים"})
            continue
        try:
            os.makedirs(os.path.dirname(src), exist_ok=True)
            shutil.move(dst, src)
            restored.append({"src": src, "dst": dst})
        except OSError as e:
            skipped.append({"src": src, "dst": dst, "reason": str(e)})

    try:
        os.remove(UNDO_LOG_PATH)
    except OSError:
        pass

    return {"restored": restored, "skipped": skipped}
