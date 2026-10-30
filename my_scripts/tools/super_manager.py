# Name: 🗂️ מנהל-העל (סריקה/דוח/ניקוי כפילויות)
# Name (EN): 🗂️ Super Manager (Scan/Report/Clean Duplicates)
# Description: מאחד את disk_scanner.py + report_to_excel.py + duplicate_cleaner.py לסקריפט אחד עם בורר-מצב (--mode scan|report|clean) -
# שלושתם כבר היו שרשרת טבעית (סריקה -> report.json -> Excel/ניקוי), רק פזורים בשלושה סקריפטים נפרדים. כל מצב עצמאי לגמרי
# (לא מריץ את שאר המצבים) - בניגוד ל-video_editor.py, אלה שלוש עבודות עם שלושה פלטים שונים, לא שלבים שמרכיבים פלט אחד.
# Description (EN): Unifies disk_scanner.py + report_to_excel.py + duplicate_cleaner.py into one script with a mode selector
# (--mode scan|report|clean) - the three were already a natural pipeline (scan -> report.json -> Excel/cleanup), just spread
# across three separate scripts. Each mode is fully standalone (does not chain into the others) - unlike video_editor.py, these
# are three separate jobs with three separate outputs, not steps composing a single output.
# Concurrency: light
# Safety: modifies
#
# item: איחוד סקריפטי "כלי עזר" ל"מנהל-על" - הוחלט להשאיר את שלושת הסקריפטים
# המקוריים כמו שהם ולקרוא להם מכאן (לא "לפרק" אותם ל-utils/ משותף) - כל אחד
# מהם כבר קובץ קטן ועצמאי, ולוגיקת ה-argparse/main() המקורית שלהם ממשיכה
# לעבוד גם בהרצה ישירה שלהם (למי שירצה, לפני שהועברו לארכיון). הבורר כאן הוא
# עטיפה דקה בלבד: קורא ל-run_scan/run_report/run_clean למטה (שמייבאים
# ומריצים את ה-main() של הסקריפט המקורי, אחרי סינון sys.argv למה שרלוונטי
# למצב הנבחר בלבד - כך שדגלי מצב אחד לא "דולפים" לתוך argparse של מצב אחר).

import argparse
import importlib.util
import os
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser(description="מנהל-העל - סריקת כונן/דוח-Excel/ניקוי-כפילויות, לפי --mode")
parser.add_argument("--mode", choices=["scan", "report", "clean"], default="scan", help="איזו פעולה להריץ.")
# --input_dir (שworker.py מזין תמיד, ראו ההערה המקבילה ב-disk_scanner.py)
# לא מוגדר כאן בכוונה - נופל ל-_unknown ועובר כמות שהוא למצב הפנימי הנבחר,
# ששם *הוא* כבר לא מוגדר (אותה מוסכמה בדיוק) ומושמט בשקט. שאר הדגלים
# (--target_dir/--workers/--no-excel/--no-html עבור scan, --input/--output
# עבור report, --input/--keep/--execute עבור clean) מפוענחים ע"י הסקריפט
# המקורי עצמו למטה - parse_known_args כאן משמיט רק --mode, ומשאיר את כל
# השאר ב-_unknown בשבילו.
args, _unknown = parser.parse_known_args()


def _load_module_from_path(module_name, file_path):
    """טוען סקריפט my_scripts/... כמודול בזיכרון בלי להריץ אותו (spec_from_file_location
    + exec_module נעצר לפני ה-if __name__ == '__main__' שם) - מאפשר לקרוא ל-main() שלו
    ישירות אחרי סינון sys.argv, בלי תת-תהליך נפרד."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_with_filtered_argv(script_filename, module_name, extra_argv):
    """מחליף זמנית את sys.argv לרשימה שמתאימה ל-argparse של הסקריפט המקורי
    (רק הדגלים הרלוונטיים למצב הנבחר, בלי --mode עצמו שהוא לא מוכר לו), טוען
    ומריץ אותו, ומשחזר את sys.argv המקורי אחר-כך גם אם הוא נכשל באמצע."""
    original_argv = sys.argv
    try:
        sys.argv = [script_filename] + extra_argv
        module = _load_module_from_path(module_name, os.path.join(TOOLS_DIR, script_filename))
        module.main()
    finally:
        sys.argv = original_argv


def main():
    # _unknown (מ-parse_known_args למעלה) הוא כבר בדיוק הרשימה הנכונה - כל מה
    # שה-parser העליון (--mode/--input_dir בלבד) לא זיהה. סינון ידני של
    # sys.argv כאן היה עלול להשאיר את הערך של --mode (למשל "scan" כטוקן
    # נפרד) דולף כארגומנט-מיקום יתום לתוך argparse של המצב הפנימי.
    passthrough_argv = _unknown
    if args.mode == "scan":
        _run_with_filtered_argv("disk_scanner.py", "disk_scanner", passthrough_argv)
    elif args.mode == "report":
        _run_with_filtered_argv("report_to_excel.py", "report_to_excel", passthrough_argv)
    else:
        _run_with_filtered_argv("duplicate_cleaner.py", "duplicate_cleaner", passthrough_argv)


if __name__ == "__main__":
    main()
