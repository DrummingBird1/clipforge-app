# utils/shared/script_metadata.py
#
# כל סקריפט תחת my_scripts/ מתחיל בארבע שורות מוסכמה: "# Name: ..." / "# Name (EN): ..."
# (שם תצוגה בעברית ובאנגלית) ו-"# Description: ..." / "# Description (EN): ..."
# (מה הוא עושה, בשתי השפות). כאן קוראים אותן במקום לתחזק מיפוי נפרד שיכול
# להתבדר מהקבצים עצמם - בדיוק אותו עיקרון כמו קטגוריית התיקייה ב-ui/sidebar.py
# (נגזר מהמבנה עצמו, לא ממילון חיצוני שאפשר לשכוח לעדכן).

import os

from utils.shared.state import state

_CACHE: dict[tuple[str, float | None], dict[str, str]] = {}


def _prettify_filename(filename):
    stem = os.path.splitext(filename)[0]
    return stem.replace("_", " ").strip().title()


def get_script_metadata(path):
    """קורא את שורות ה-Name/Description (עברית+אנגלית) מראש קובץ הסקריפט, ומחזיר
    את הגרסה המתאימה לפי state.language. תוצאה נשמרת ב-cache לפי (path, mtime)
    כדי לא לפתוח מחדש כל קובץ בכל רענון של רשימת הסקריפטים."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    cache_key = (path, mtime)
    if cache_key not in _CACHE:
        name_he = None
        name_en = None
        desc_he = ""
        desc_en = ""
        concurrency = "heavy"
        # "modifies" הוא ברירת המחדל השמרנית לסקריפט בלי תגית - עדיף שסקריפט
        # שכותב-הקוד שכח לתייג יוצג כ"נוגע בקבצים" (שמרני מדי) מאשר "בטוח
        # לקריאה" בטעות (אמון שווא). כל 14 הסקריפטים הקיימים מתויגים במפורש.
        safety = "modifies"
        try:
            with open(path, "r", encoding="utf-8") as f:
                # 12 שורות (לא 6) - מוסכמת הכותרת גדלה מ-4 שדות (Name/Description
                # בשתי שפות) ל-6 עם Concurrency/Safety, וכמה סקריפטים (כמו
                # disk_scanner.py) כבר משתמשים בהרבה מהשורות הישנות לשדות עצמם.
                for _ in range(12):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if line.startswith("# Name (EN):"):
                        name_en = line[len("# Name (EN):"):].strip()
                    elif line.startswith("# Name:"):
                        name_he = line[len("# Name:"):].strip()
                    elif line.startswith("# Description (EN):"):
                        desc_en = line[len("# Description (EN):"):].strip()
                    elif line.startswith("# Description:"):
                        desc_he = line[len("# Description:"):].strip()
                    elif line.startswith("# Concurrency:"):
                        value = line[len("# Concurrency:"):].strip().lower()
                        if value == "light":
                            concurrency = "light"
                    elif line.startswith("# Safety:"):
                        value = line[len("# Safety:"):].strip().lower()
                        if value == "read-only":
                            safety = "read-only"
        except OSError:
            pass

        if not name_he:
            name_he = _prettify_filename(os.path.basename(path))
        if not name_en:
            name_en = name_he

        # name_he/desc_he נשארים גולמיים (בלי fix_hebrew_word_order) בכוונה -
        # היה מופעל כאן, אבל זה שבר כל מקום שמרכיב אותם לתוך מחרוזת גדולה יותר
        # (כמו כותרת עם שם קובץ: "סקריפט: {name} ({filename})"): fix_hebrew_word_order
        # הפוך *כבר* פעם אחת כאן, ואז t()/fix_hebrew_word_order על המחרוזת
        # המורכבת הסופית מדלג (כי יש בה תווים לועזיים מה-filename) - כך שקטע
        # השם נשאר הפוך בפועל על המסך, בעוד שאר המשפט מוצג נכון. הפתרון: לעולם
        # לא להפוך כאן; כל קורא שמציג name/description בעצמו (לא רק כחלק
        # ממחרוזת t() גדולה יותר) אחראי להפעיל fix_hebrew_word_order() בעצמו
        # בדיוק על המחרוזת הסופית שנמסרת ל-widget - ראו ui/sidebar.py,
        # ui/widgets.py (CommandPalette), ui/settings_tab.py, ui/scheduler_tab.py.
        _CACHE[cache_key] = {
            "name_he": name_he, "name_en": name_en,
            "desc_he": desc_he, "desc_en": desc_en,
            "concurrency": concurrency, "safety": safety,
        }

    entry = _CACHE[cache_key]
    if state.language == "en":
        result = {"name": entry["name_en"], "description": entry["desc_en"] or entry["desc_he"]}
    else:
        result = {"name": entry["name_he"], "description": entry["desc_he"]}
    result["concurrency"] = entry["concurrency"]
    result["safety"] = entry["safety"]
    return result
