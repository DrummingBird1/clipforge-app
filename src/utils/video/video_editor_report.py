# utils/video/video_editor_report.py
#
# ייצוא דוח סיכום ריצה ל-CSV/Excel (item: ייצוא דוח קידוד) עבור
# my_scripts/video/video_editor.py - זמן ריצה, ספירת קבצים, ורשימת כל קובץ
# שנוצר (שם/קודק/רזולוציה/משך/גודל/זמן רינדור). אותו עיקרון בדיוק כמו
# utils/shared/report_excel.py (disk_scanner.py) - report הוא dict טהור, לא תלוי
# ב-video_editor.py עצמו, כדי שהעיצוב יהיה ניתן-לבדיקה בלי להריץ ffmpeg.
# style_sheet/openpyxl משותפים עם report_excel.py (מקור אמת יחיד לעיצוב
# גיליונות בכל הפרויקט), לא לוגיקת-עיצוב כפולה.

import csv

from openpyxl import Workbook

from utils.shared.report_excel import style_sheet

_FILE_COLUMN_HEADERS = (
    "שם קובץ מקור", "שם קובץ פלט", "קודק", "מיכל", "רזולוציה", "FPS",
    "משך (שניות)", "גודל פלט (MB)", "זמן רינדור (שניות)", "HDR",
)


def _file_row(item):
    return (
        item.get("source_filename", ""), item.get("output_filename", ""), item.get("codec", ""),
        item.get("container", ""), item.get("resolution", ""), item.get("fps", ""),
        item.get("duration_seconds", ""), item.get("output_size_mb", ""), item.get("render_seconds", ""),
        "כן" if item.get("hdr") else "לא",
    )


def _summary_rows(report):
    return [
        ("זמן ריצה כולל (שניות)", report.get("elapsed_seconds", "")),
        ("זמן ממוצע לקובץ (שניות)", report.get("avg_seconds_per_file", "")),
        ("קבצים שנוצרו", report.get("files_created", 0)),
        ("קבצים שדולגו (כבר קיימים)", report.get("skipped", 0)),
        ("קבצים שנכשלו", report.get("errors", 0)),
        ("קודק", report.get("codec", "")),
        ("מיכל יצוא", report.get("container", "")),
        ("האצת GPU (hwaccel)", "כן" if report.get("hwaccel") else "לא"),
        ("סרטונים במקביל", report.get("parallel", 1)),
        ("דרגת מאמץ", report.get("effort", "")),
    ]


def write_csv_report(report, output_path):
    """report: dict עם elapsed_seconds/files_created/skipped/errors/codec/
    container/hwaccel/parallel/effort/files (רשימת dict-ים, אחד לכל קובץ
    שנוצר בפועל - ראו _file_row). encoding="utf-8-sig" (BOM) - בלעדיו Excel
    (בניגוד לעורכי-טקסט/Sheets) מציג עברית ב-CSV פשוט כטקסט-מקושקש, לא
    שגיאה גלויה שמישהו היה שם לב לתקן."""
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["דוח ריצה - עורך-העל (video_editor.py)"])
        for label, value in _summary_rows(report):
            writer.writerow([label, value])
        writer.writerow([])
        writer.writerow(_FILE_COLUMN_HEADERS)
        for item in report.get("files", []):
            writer.writerow(_file_row(item))


def write_xlsx_report(report, output_path):
    """כמו write_csv_report, אבל כ-Excel מעוצב עם שני גיליונות (סיכום + רשימת
    קבצים) - style_sheet (utils/shared/report_excel.py) נותן RTL, כותרת מודגשת,
    auto-filter ו-freeze panes, אותו עיצוב בדיוק כמו דוחות disk_scanner.py."""
    wb = Workbook()

    ws = wb.active
    ws.title = "סיכום"
    style_sheet(ws, ["מדד", "ערך"], _summary_rows(report), [28, 30])

    ws2 = wb.create_sheet("קבצים")
    file_rows = [_file_row(item) for item in report.get("files", [])]
    style_sheet(ws2, list(_FILE_COLUMN_HEADERS), file_rows, [30, 32, 10, 8, 12, 10, 12, 14, 14, 8])

    wb.save(output_path)
