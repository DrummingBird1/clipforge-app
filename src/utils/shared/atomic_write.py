# utils/shared/atomic_write.py
#
# כתיבה אטומית ל-JSON (item: בדיקת באגים מקיפה) - כותבת לקובץ זמני באותה
# תיקייה בדיוק כמו היעד (כדי ש-os.replace יהיה אטומי על אותה מערכת קבצים -
# תיקיית temp כללית יכולה לשבת על דיסק/partition אחר) ומחליפה את היעד
# בבת-אחת רק אחרי שהכתיבה הצליחה במלואה. קריסה/הריגה של התהליך באמצע כתיבה
# משאירה את הקובץ המקורי שלם ולא נוגע בו, במקום קובץ יעד חצי-כתוב/ריק
# שקריאה עתידית (שכל data/*.json בפרויקט מטפלת בה כ"קובץ פגום" -> איפוס
# שקט לברירות מחדל) הייתה מפרשת כאובדן מוחלט של הנתונים ששם.
#
# לא פותר תחרות בין כמה כותבים בו-זמנית (שני תהליכים/thread-ים שכותבים בו-
# זמנית עדיין יכולים לדרוס אחד את השני - "העדכון האחרון מנצח") - זו רק הגנה
# מפני קובץ פגום מקריסה, לא מנעול הדדי-אכיפה. קבצים שדורשים גם את זה
# (data/config.json, הנכתב גם מהדסקטופ וגם מהווב) נועלים בנפרד סביב הקריאה
# הזו (ראו utils/shared/state.py/web_app.py).

import json
import os
import tempfile


def atomic_write_json(path, data, **json_kwargs):
    """כותבת data כ-JSON ל-path אטומית. **json_kwargs מועבר ישירות ל-json.dump
    (ensure_ascii/indent וכו') כדי שכל קורא ישמור על הפורמט שהיה לו קודם.
    זורקת (OSError/TypeError וכו') בדיוק כמו open()+json.dump ישירים היו
    זורקים - הקוראים הקיימים כבר עוטפים את זה ב-try/except משלהם."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **json_kwargs)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
