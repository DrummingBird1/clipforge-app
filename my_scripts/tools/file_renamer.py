# Name: ✏️ מחליף-השמות ההמוני
# Name (EN): ✏️ Bulk Renamer
# Description: סקריפט לשינוי שם קבצים עם תמיכה במספור, תחיליות/סיומות והוספת רווח אופציונלי.
# Description (EN): Renames files in bulk with support for numbering, prefixes/suffixes, and optional spacing.
# Concurrency: light
# Safety: modifies

import json
import os
import argparse
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure") and sys.stderr.encoding != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def build_new_name(index, prefix, suffix, do_number, do_space):
    """בונה את שם הקובץ החדש (בלי סיומת) - חולץ מתוך main() כדי שיהיה ניתן לבדיקה ישירה."""
    prefix_part = prefix
    if do_space and prefix_part:
        prefix_part += " "

    number_str = str(index) if do_number else ""
    new_name = f"{prefix_part}{number_str}{suffix}"

    if not new_name.strip():
        new_name = f"renamed_file_{index}"

    return new_name


def main():
    # הגדרת הארגומנטים שה-GUI שולח באופן אוטומטי
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=str, required=True, help="התיקייה שבה נמצאים הקבצים")
    parser.add_argument("--prefix", type=str, default="", help="טקסט להוספה בתחילת שם הקובץ")
    parser.add_argument("--suffix", type=str, default="", help="טקסט להוספה בסוף שם הקובץ (לפני הסיומת)")
    parser.add_argument("--number", type=str, default="True", help="האם להוסיף מספור רץ")
    parser.add_argument("--space", type=str, default="False", help="האם להוסיף רווח מיד אחרי ה-Prefix")
    
    args = parser.parse_args()

    # בדיקת תקינות תיקיית העבודה
    if not os.path.exists(args.input_dir):
        print(f"[ERROR] התיקייה לא נמצאה: {args.input_dir}")
        return

    # המרה של מחרוזות ה-boolean מערכים מהממשק לערכים אמיתיים
    do_number = (args.number.lower() == "true")
    do_space = (args.space.lower() == "true")
    
    # סינון וקבלת רשימת קבצים בלבד (ללא תיקיות פנימיות)
    files = sorted([f for f in os.listdir(args.input_dir) if os.path.isfile(os.path.join(args.input_dir, f))])
    
    if not files:
        print("[WARNING] לא נמצאו קבצים לשינוי שם בתיקייה שנבחרה.")
        return

    # item: בדיקת באגים מקיפה - build_new_name לא כוללת את שם הקובץ המקורי
    # בכלל, אז בלי מספור כל הקבצים עם אותה סיומת מייצרים את אותו שם יעד
    # בדיוק. בעבר זה היה נגמר בשינוי-שם מוצלח לקובץ הראשון בלבד ו-FileExistsError
    # (Windows) על כל השאר, בלי שום רמז מראש למה - נבדק ומדווח כאן פעם אחת,
    # לפני שנוגעים בקובץ כלשהו, במקום כישלון חלקי מבלבל תוך כדי.
    if not do_number:
        ext_counts = {}
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
        colliding_exts = sorted(ext for ext, count in ext_counts.items() if count > 1)
        if colliding_exts:
            print(
                "[ERROR] בלי מספור (--number False), כמה קבצים עם אותה סיומת "
                f"({', '.join(colliding_exts)}) יקבלו בדיוק אותו שם חדש ויתנגשו. "
                "הפעל עם מספור מופעל, או השאר קובץ אחד בלבד לכל סיומת בתיקייה."
            )
            return

    print(f"[PROCESS] מתחיל בשינוי שמות ל-{len(files)} קבצים...")

    renamed_count = 0
    error_count = 0
    total = len(files)
    for i, filename in enumerate(files, start=1):
        # פירוק הקובץ לשם וסיומת
        name_part, ext = os.path.splitext(filename)

        new_name = build_new_name(i, args.prefix, args.suffix, do_number, do_space)

        old_path = os.path.join(args.input_dir, filename)
        new_path = os.path.join(args.input_dir, f"{new_name}{ext}")

        try:
            os.rename(old_path, new_path)
            print(f"[APPROVED] {filename} -> {new_name}{ext}")
            renamed_count += 1
        except Exception as e:
            print(f"[ERROR] נכשל בשינוי השם של הקובץ {filename}: {e}")
            error_count += 1

        # התקדמות מפורשת (ראו EXPLICIT_PROGRESS_PATTERN ב-utils/shared/worker.py) - לא
        # תלוי בפורמט הפס של tqdm, כי הסקריפט הזה לא משתמש בו בכלל.
        print(f"PROGRESS:{int(i / total * 100)}")

    print("[SUCCESS] סיום פעולת שינוי שמות הקבצים!")

    # שורת תוצאה מובנית ל-GUI (ראו RESULT_LINE_PREFIX ב-utils/shared/worker.py).
    print("RESULT: " + json.dumps({"renamed": renamed_count, "errors": error_count, "total": total}, ensure_ascii=False))

if __name__ == "__main__":
    main()