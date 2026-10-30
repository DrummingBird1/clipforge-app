# utils/video/video_editor_counter.py
#
# מונה מתמשך למספור סרטונים (item: מספור סרטונים) עבור video_editor.py
# ("עורך-העל") - אותו עיקרון בדיוק כמו my_scripts/video/rocket_shorts_publisher.py's
# get_next_number()/save_current_number() (קובץ טקסט פשוט עם מספר יחיד תחת
# data/), אבל בקובץ *נפרד* משלו (data/video_editor_counter.txt, לא
# data/counter.txt של rocket_shorts) - שני הסקריפטים הם פייפליינים עצמאיים,
# ושיתוף מונה אחד בין שניהם היה יוצר צימוד לא-רצוי (למשל ריצת עורך-העל
# על חומר לא-קשור-למשחק שמקדמת בטעות את המונה שרוקט-שורטס משתמש בו
# למספור הפרסומים בפועל).
#
# בניגוד לרוקט-שורטס (חד-תהליכי, המונה מוקצה רק פעם אחת פר-ריצה ומתקדם רק
# אחרי הצלחה מוכחת - "לא מקדם מונה" על כשל), כאן get_next_number() מקבל
# פרמטר start (רלוונטי רק בפעם הראשונה שהקובץ לא קיים) ו-save_number() נקראת
# על ידי הקורא (my_scripts/video/video_editor.py) בנפרד - כדי לתמוך גם
# ב---parallel (כמה קבצים בו-זמנית): שם המספר מוקצה ונשמר באופן אטומי
# *מוקדם* (לפני שידוע אם הרינדור יצליח) כרשת-ביטחון למקרה של קריסה/הריגה-
# חיצונית באמצע הבאצ' (כדי שלעולם לא יוקצה אותו מספר פעמיים בין threads),
# אבל בסיום תקין (video_editor.py's persist_final_counter_value(), נקרא
# מ-main() דרך finally) הערך הזה מתוקן כך שישקף רק מספרים שבאמת נוצל עליהם
# קובץ-פלט בהצלחה - קובץ שנכשל/דולג "מוחזר למחזור", לא שורף לצמיתות את
# המספר שהוקצה לו. הריגה חיצונית של התהליך (למשל כפתור Stop ב-GUI) לא
# מגיעה ל-finally בכלל - שם נשאר המחיר של רשת-הביטחון, לא-נמנע בלי IPC נוסף.

import os

from utils.shared import data_paths
# CLIPFORGE_VIDEO_EDITOR_COUNTER_PATH: טסטים מפנים את המונה לתיקייה זמנית - המונה האמיתי
# הוא נתוני-משתמש (נמחק פעם אחת כששני טסטי מספור רצו במקביל ושחזרו זה את זה)
COUNTER_PATH = os.environ.get("CLIPFORGE_VIDEO_EDITOR_COUNTER_PATH") or data_paths.path(data_paths.EDITOR_COUNTER)


def get_next_number(start: int = 1, counter_path: str = COUNTER_PATH) -> int:
    """קורא את המספר הבא מהקובץ - אם לא קיים (ריצה ראשונה, או --number-start
    מפורש) יוצר אותו עם start ומחזיר אותו. תוכן פגום (לא מספר) נופל בחזרה
    ל-start, לא זורק - כדי שקובץ מונה שנפגם לא יפיל את כל הריצה."""
    if not os.path.exists(counter_path):
        save_number(start, counter_path)
        return start
    try:
        with open(counter_path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return start


def save_number(number: int, counter_path: str = COUNTER_PATH) -> None:
    os.makedirs(os.path.dirname(counter_path), exist_ok=True)
    with open(counter_path, "w", encoding="utf-8") as f:
        f.write(str(number))
