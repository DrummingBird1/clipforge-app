# utils/shared/data_dir.py
#
# data/ = נתוני המשתמש האמיתיים (הגדרות, מונים, ה-DB, לוגים) - מקור אמת יחיד לנתיב שלה,
# במקום os.path.join(BASE_DIR, "data") משוכפל בכל מודול. CLIPFORGE_DATA_DIR מפנה אותה למקום
# אחר: tests/conftest.py מגדיר אותו לתיקייה זמנית בכל ריצת pytest, לפני שמודול כלשהו מיובא -
# כך ששום טסט, וגם שום תת-תהליך שטסט מריץ (video_editor.py וכו' יורשים את הסביבה), לא כותב
# ל-data/ האמיתית. בלי המשתנה (ריצה רגילה) - data/ בשורש הפרויקט, בדיוק כמו קודם.
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.environ.get("CLIPFORGE_DATA_DIR") or os.path.join(PROJECT_ROOT, "data")
