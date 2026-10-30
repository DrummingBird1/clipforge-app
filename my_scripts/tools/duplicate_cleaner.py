# Name: 🧹 מנקה הכפילויות
# Name (EN): 🧹 Duplicate Sweeper
# Description: קורא את קבוצות הכפילויות מ-report.json (disk_scanner.py), שומר עותק אחד מכל קבוצה ומעביר את השאר לסל המיחזור בלבד (לא מחיקה קבועה). ברירת המחדל היא הצגת תוכנית בלבד - שום קובץ לא זז בלי --execute מפורש.
# Concurrency: light
# Safety: modifies
# Description (EN): Reads duplicate groups from report.json (disk_scanner.py), keeps one copy per group and moves the rest to the Recycle Bin only (never a permanent delete). Default is a dry-run plan - nothing moves without an explicit --execute.
#
# הכלי הזה בכוונה *לא* רץ אוטומטית עד הסוף כשמפעילים אותו מה-GUI: worker.py
# מזין רק --input_dir גנרי (מתעלמים ממנו כאן, כמו בכל שאר my_scripts), אז
# הרצה מה-GUI תמיד נופלת למצב תצוגה-מקדימה (dry-run) - צריך --execute מפורש
# משורת הפקודה כדי שקובץ אחד יזוז בפועל. זה נעשה בכוונה: כלי שמזיז קבצים
# (גם לסל המיחזור, לא מחיקה) צריך הפעלה מודעת ומפורשת, לא לחיצת "הרץ" אחת.

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from send2trash import send2trash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.disk_report_paths import default_report_input

parser = argparse.ArgumentParser(description="מנקה כפילויות שנמצאו על ידי disk_scanner.py - מעביר לסל המיחזור בלבד")
parser.add_argument("--input", type=str, default="", help="נתיב ל-report.json (ברירת מחדל: workspace/reports/disk/report.json, ואם אין - data/report.json הישן)")
parser.add_argument("--keep", choices=["oldest", "newest"], default="oldest", help="איזה עותק לשמור מכל קבוצה (ברירת מחדל: oldest)")
parser.add_argument("--execute", action="store_true", help="מעביר בפועל לסל המיחזור. בלי הדגל הזה - תצוגה מקדימה בלבד, שום קובץ לא זז.")
args, _unknown = parser.parse_known_args()

INPUT_PATH = args.input or default_report_input()


def pick_keeper(files, keep_policy):
    """בוחר איזה קובץ בקבוצה להשאיר, לפי זמן שינוי (mtime). קבצים שכבר לא
    קיימים (נמחקו/הוזזו מאז הסריקה) לא מועמדים - אם כולם נעלמו, מדלגים
    על הקבוצה כולה (שום דבר להשוות/להזיז)."""
    existing = [f for f in files if os.path.exists(f)]
    if not existing:
        return None, []
    existing.sort(key=os.path.getmtime, reverse=(keep_policy == "newest"))
    return existing[0], existing[1:]


def main():
    if not os.path.exists(INPUT_PATH):
        print(f"❌ לא נמצא קובץ דוח: {INPUT_PATH} (הרץ קודם את disk_scanner.py)")
        sys.exit(1)

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        report = json.load(f)

    groups = report.get("duplicates", [])
    if not groups:
        print("✅ לא נמצאו קבוצות כפילויות בדוח - אין מה לנקות.")
        print("RESULT: " + json.dumps({"groups_processed": 0, "files_moved": 0, "bytes_freed": 0, "executed": args.execute}))
        return

    mode_label = "מעביר לסל המיחזור" if args.execute else "תצוגה מקדימה בלבד (לא זז שום קובץ)"
    print(f"🧹 {len(groups)} קבוצות כפילויות בדוח. מצב: {mode_label} (שמירה: {args.keep}).")

    files_moved = 0
    bytes_freed = 0
    errors = []
    total = len(groups)

    for i, group in enumerate(groups, start=1):
        keeper, to_remove = pick_keeper(group.get("files", []), args.keep)
        if keeper is None:
            print(f"⚠️ קבוצה {i}: אף קובץ מהקבוצה כבר לא קיים בדיסק - דילוג.")
        else:
            size = group.get("size_bytes", 0)
            print(f"📁 קבוצה {i}: שומר {keeper}")
            for path in to_remove:
                if args.execute:
                    try:
                        send2trash(path)
                        print(f"   🗑️ הועבר לסל המיחזור: {path}")
                        files_moved += 1
                        bytes_freed += size
                    except Exception as e:
                        print(f"   ❌ נכשל להעביר {path}: {e}")
                        errors.append({"path": path, "error": str(e)})
                else:
                    print(f"   ⏳ היה מועבר לסל המיחזור: {path}")
                    files_moved += 1
                    bytes_freed += size

        print(f"PROGRESS:{int(i / total * 100)}")

    action_word = "הועברו" if args.execute else "היו מועברים"
    print(f"\n✅ הסתיים. {files_moved} קבצים {action_word} לסל המיחזור, {bytes_freed / (1024**3):.2f} GB {'שוחררו' if args.execute else 'היו משוחררים'}.")
    if not args.execute:
        print("ℹ️ זו הייתה תצוגה מקדימה בלבד. להרצה בפועל: הרץ מהשורת פקודה עם --execute.")

    print("RESULT: " + json.dumps({
        "groups_processed": len(groups),
        "files_moved": files_moved,
        "bytes_freed": bytes_freed,
        "executed": args.execute,
        "errors": len(errors),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
