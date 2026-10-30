# Name: 📊 הדוח לאקסל
# Name (EN): 📊 Report-to-Excel
# Description: ממיר קובץ report.json (מ-disk_scanner.py) לקובץ Excel מעוצב עם גיליונות מסודרים (סיכום/כפילויות/זבל/מדיה).
# Description (EN): Converts a report.json file (from disk_scanner.py) into a formatted Excel file with organized sheets (summary/duplicates/junk/media).
# Concurrency: light
# Safety: read-only

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.disk_report_paths import DEFAULT_REPORT_JSON, default_report_input
from utils.shared.report_excel import write_excel_report

# parse_known_args בכוונה: מתעלם בשקט מ---input_dir שה-GUI מזין תמיד (ראו
# ההערה המקבילה ב-disk_scanner.py) - לסקריפט הזה אין "תיקיית עבודה", יש לו
# קובץ JSON קלט וקובץ Excel פלט.
parser = argparse.ArgumentParser(description="ממיר report.json לקובץ Excel מעוצב")
parser.add_argument("--input", type=str, default="", help="נתיב לקובץ ה-JSON (ברירת מחדל: workspace/reports/disk/report.json, ואם אין - data/report.json הישן)")
parser.add_argument("--output", type=str, default="", help="נתיב לקובץ ה-Excel (ברירת מחדל: אותו שם עם סיומת .xlsx; בלי --input - תמיד ב-workspace/reports/disk/)")
args, _unknown = parser.parse_known_args()

INPUT_PATH = args.input or default_report_input()
# בלי --input ה-Excel נכתב תמיד ליד הדוח החדש - גם כשהקלט הוא data/report.json הישן, כדי לא לכתוב ל-data/
OUTPUT_PATH = args.output or os.path.splitext(args.input or DEFAULT_REPORT_JSON)[0] + ".xlsx"


def main():
    if not os.path.exists(INPUT_PATH):
        print(f"❌ קובץ הדוח לא נמצא: {INPUT_PATH}")
        sys.exit(1)

    try:
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception as e:
        print(f"❌ שגיאה בקריאת קובץ ה-JSON: {e}")
        sys.exit(1)

    print(f"📊 ממיר את {INPUT_PATH} ל-Excel...")
    sys.stdout.flush()
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    write_excel_report(report, OUTPUT_PATH)
    print(f"✅ קובץ Excel נוצר בהצלחה: {OUTPUT_PATH}")
    print(f"   ({report.get('total_files_scanned', 0):,} קבצים | "
          f"{report.get('duplicate_groups_found', 0)} קבוצות כפילויות | "
          f"{report.get('junk_files_found', 0)} קבצי זבל | "
          f"{report.get('media_files_analyzed', 0)} קבצי מדיה)")


if __name__ == "__main__":
    main()
