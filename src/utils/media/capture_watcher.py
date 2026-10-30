# utils/media/capture_watcher.py
#
# לוגיקה טהורה וניתנת-לבדיקה עבור my_scripts/stream/capture_folder_watcher.py
# (item: אינטגרציה עם תוכנת לכידה נוספת - Streamlabs/ShadowPlay/כל תוכנה
# אחרת ששומרת לתיקייה) - אותו עיקרון בדיוק כמו utils/media/timelapse.py: הלולאה
# האינסופית/time.sleep נשארים בסקריפט, כאן רק זיהוי-קבצים-חדשים/יציבות/
# כבר-הועתק, כדי שאפשר לבדוק בלי להריץ לולאה אמיתית.

import os

from utils.media.timelapse import VIDEO_EXTENSIONS

# קובץ נחשב "יציב" (הועתק בשלמותו ע"י תוכנת הלכידה, לא עדיין נכתב) רק אחרי
# שגודלו נשאר זהה בין כמה בדיקות תקופתיות ברציפות - קובץ שעדיין נכתב גדל בין
# בדיקה לבדיקה, אז לא ייעתק לפני זמנו (עותק חלקי/פגום).
STABLE_CHECKS_REQUIRED = 2


def list_video_files(folder):
    """מחזיר {שם קובץ: נתיב מלא} לכל קובצי הווידאו (VIDEO_EXTENSIONS) בתיקייה -
    {} אם התיקייה לא קיימת/לא נגישה, לא זורק (התיקייה עשויה עדיין לא להיות
    מוכנה/נגישה, למשל דיסק חיצוני שהתנתק זמנית)."""
    try:
        return {
            entry.name: entry.path
            for entry in os.scandir(folder)
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in VIDEO_EXTENSIONS
        }
    except OSError:
        return {}


def already_copied(filename, target_dir):
    """קובץ עם אותו שם כבר קיים ביעד - כבר הועתק בעבר (item: copy-not-move,
    זהה ל-obs_replay_watcher.py: המקור נשאר במקומו בתיקיית הלכידה, אז ימשיך
    "להתגלות" בכל בדיקה - בדיקת-נוכחות ביעד היא זיכרון עמיד להפעלה-מחדש בלי
    קובץ מצב נפרד)."""
    return os.path.exists(os.path.join(target_dir, filename))


def update_size_history(size_history, filename, size, stable_checks_required=STABLE_CHECKS_REQUIRED):
    """מוסיף מדידת-גודל חדשה לרשימת ההיסטוריה של filename בתוך size_history
    (dict, נערך במקום) ומחזיר True אם הקובץ יציב עכשיו - אותו גודל בדיוק על
    פני stable_checks_required הבדיקות האחרונות ברציפות."""
    history = size_history.setdefault(filename, [])
    history.append(size)
    if len(history) > stable_checks_required:
        history.pop(0)
    return len(history) == stable_checks_required and len(set(history)) == 1
