# Name: <שם תצוגה בעברית, עם אימוג'י אחד בהתחלה - מוצג בסיידבר>
# Name (EN): <same name in English>
# Description: <מה הסקריפט עושה, עברית - מוצג בפאנל הצדדי כשהסקריפט נבחר>
# Description (EN): <same description in English>
# Concurrency: light
# Safety: read-only
#
# --- קובץ הזה הוא תבנית להעתקה, לא סקריפט אמיתי - לא רץ מהסיידבר. ---
#
# מוסכמות my_scripts/ (ראו utils/shared/script_metadata.py, utils/shared/worker.py):
#
# 1. שורות ה-Name/Description/Concurrency/Safety למעלה חייבות להיות בתוך 12
#    השורות הראשונות של הקובץ. "Concurrency: light" הוא אופציונלי - השמט
#    אותו לגמרי אם הסקריפט משתמש ב-ffmpeg/GPU או אחרת עלול לרוץ זמן רב;
#    ברירת המחדל (heavy) מריצה סקריפטים כאלה בתור סדרתי אחד, כדי לא
#    להתחרות על GPU/דיסק. סמן light רק לסקריפטים מהירים, לא-GPU (קריאת/
#    כתיבת קבצים, קריאות API). "Safety:" לעומת זאת **חובה** - "read-only"
#    אם הסקריפט אף פעם לא מוחק/מזיז/משנה שם של קובץ קיים (יצירת קבצים
#    חדשים זה בסדר), או "modifies" אם כן (גם אם זה הפיך, כמו העברה לסל
#    המיחזור) - זה בדיוק מה שקובע את תג ⚠️/אין-תג בסיידבר, אז דיוק כאן חשוב.
#
# 2. השתמש ב-argparse.parse_known_args() (לא parse_args()) אם אתה לא צריך את
#    --input_dir - ה-GUI (utils/shared/worker.py) תמיד מזין את הדגל הזה (מתוך תיקיית
#    ה"גיימפליי" הנבחרת בטאב ההגדרות), בלי קשר לאיזה סקריפט נבחר. סקריפט
#    שבאמת צריך תיקיית עבודה (כמו file_renamer.py) יכול להגדיר --input_dir
#    כארגומנט אמיתי משלו ולהשתמש ב-parse_args() הרגיל.
#
# 3. פלט התקדמות ל-GUI (אופציונלי): tqdm רגיל מוכר אוטומטית (הבר שלו נסרק
#    ב-regex). לסקריפט שלא משתמש ב-tqdm, אפשר להדפיס שורה נפרדת:
#        print(f"PROGRESS:{pct}")   # 0-100, בלי עשרוני
#
# 4. תוצאה מובנית ל-GUI (אופציונלי, שורה אחרונה): מציגה סיכום קריא בהתראת
#    הסיום (Toast/Discord webhook) והיסטוריית הריצות, במקום רק ✅/❌ גולמי:
#        print("RESULT: " + json.dumps({"files_processed": n, "errors": 0}))
#
# 5. לעולם אל תניח שהתיקייה שהמשתמש בחר בטאב ההגדרות רלוונטית לסקריפט הזה -
#    אם הסקריפט לא צריך תיקיית קלט כללית, אל תגדיר --input_dir בכלל (ראו #2).

import argparse
import json
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

parser = argparse.ArgumentParser(description="<תיאור קצר לשימוש דרך --help>")
parser.add_argument("--example", type=str, default="", help="<דוגמה לארגומנט משלך>")
args, _unknown = parser.parse_known_args()


def main():
    total_items = 3  # דוגמה - בפועל: len(the_real_list_of_things_to_process)
    processed = 0
    errors = 0

    print("🚀 מתחיל...")
    for i in range(1, total_items + 1):
        # <עשה כאן את העבודה האמיתית על הפריט ה-i>
        processed += 1
        print(f"PROGRESS:{int(i / total_items * 100)}")

    print("✅ הסתיים בהצלחה.")
    print("RESULT: " + json.dumps({"processed": processed, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
