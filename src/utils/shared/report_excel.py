# utils/shared/report_excel.py
#
# ממיר דוח JSON (בפורמט שדיסק_scanner.py מפיק) לקובץ Excel מעוצב עם כמה גיליונות
# מסודרים - הרבה יותר נוח לעיון/מיון/סינון ידני מ-JSON גולמי. משותף בין
# disk_scanner.py (יוצר אותו כברירת מחדל בסוף כל סריקה) ל-report_to_excel.py (המרה
# עצמאית של דוח JSON קיים) כדי שלא תהיה לוגיקת עיצוב כפולה בשני מקומות.

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
RTL_ALIGN = Alignment(horizontal="right", readingOrder=2)  # readingOrder=2 = RTL


def style_sheet(ws, headers, rows, col_widths):
    """מעצב גיליון openpyxl אחיד (RTL, כותרת מודגשת/ממולאת, auto-filter,
    freeze panes) - ציבורי (בלי קו-תחתי) כי גם utils/video/video_editor_report.py
    (item: דוח ייצוא לעורך-העל) משתמש בו, לא רק write_excel_report כאן."""
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = RTL_ALIGN
    for row in rows:
        ws.append(row)
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(horizontal="right", readingOrder=2, vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _bytes_to_mb(size_bytes):
    return round((size_bytes or 0) / (1024 ** 2), 2)


def write_excel_report(report, output_path):
    """report: אותו dict בדיוק שנכתב ל-report.json. output_path: נתיב ל-.xlsx."""
    wb = Workbook()

    # --- סיכום ---
    ws = wb.active
    ws.title = "סיכום"
    summary_rows = [
        ("תיקיית יעד", report.get("target_directory", "")),
        ("תאריך תחילת סריקה", report.get("scan_started_at", "")),
        ("תאריך סיום סריקה", report.get("scan_finished_at", "")),
        ("משך סריקה (שניות)", report.get("scan_duration_seconds", "")),
        ("סה\"כ קבצים שנסרקו", report.get("total_files_scanned", 0)),
        ("סה\"כ נפח (GB)", round((report.get("total_size_bytes", 0) or 0) / (1024 ** 3), 2)),
        ("קבצי מדיה שנותחו", report.get("media_files_analyzed", 0)),
        ("קבוצות כפילויות שנמצאו", report.get("duplicate_groups_found", 0)),
        ("נפח לשחזור מכפילויות (GB)", round((report.get("duplicate_wasted_bytes", 0) or 0) / (1024 ** 3), 2)),
        ("קבצי זבל שנמצאו", report.get("junk_files_found", 0)),
        ("תיקיות Junction/Symlink שדולגו", report.get("skipped_reparse_points_count", 0)),
        ("שגיאות גישה", len(report.get("errors", []))),
    ]
    style_sheet(ws, ["מדד", "ערך"], summary_rows, [32, 40])

    # --- כפילויות ---
    ws = wb.create_sheet("כפילויות")
    dup_rows = []
    for i, group in enumerate(report.get("duplicates", []), start=1):
        for file_path in group.get("files", []):
            dup_rows.append((i, file_path, _bytes_to_mb(group.get("size_bytes")), group.get("hash", "")[:16] + "…"))
    style_sheet(ws, ["קבוצה #", "נתיב קובץ", "גודל (MB)", "Hash (מקוצר)"], dup_rows, [10, 80, 14, 20])

    # --- קבצי זבל ---
    ws = wb.create_sheet("קבצי זבל")
    junk_rows = [
        (j.get("path", ""), _bytes_to_mb(j.get("size_bytes")), j.get("reason", ""))
        for j in report.get("junk_files", [])
    ]
    style_sheet(ws, ["נתיב קובץ", "גודל (MB)", "סיבה"], junk_rows, [80, 14, 35])

    # --- קבצי מדיה ---
    ws = wb.create_sheet("קבצי מדיה")
    media_rows = []
    for m in report.get("media_files", []):
        resolution = f"{m['width']}x{m['height']}" if m.get("width") and m.get("height") else ""
        duration = round(m["duration_seconds"], 1) if m.get("duration_seconds") else ""
        bitrate_kbps = round(m["bitrate"] / 1000, 0) if m.get("bitrate") else ""
        media_rows.append((
            m.get("path", ""), _bytes_to_mb(m.get("size_bytes")), m.get("video_codec") or "",
            m.get("audio_codec") or "", bitrate_kbps, duration, resolution,
            (m.get("full_hash") or m.get("quick_hash") or "")[:16] + "…",
        ))
    style_sheet(
        ws, ["נתיב קובץ", "גודל (MB)", "קודק וידאו", "קודק אודיו", "ביטרייט (kbps)", "משך (שנ')", "רזולוציה", "Hash (מקוצר)"],
        media_rows, [80, 14, 14, 14, 16, 12, 14, 20]
    )

    # --- שגיאות (רק אם יש) ---
    errors = report.get("errors", [])
    if errors:
        ws = wb.create_sheet("שגיאות")
        error_rows = [(e.get("path", ""), e.get("error", "")) for e in errors]
        style_sheet(ws, ["נתיב קובץ", "שגיאה"], error_rows, [80, 60])

    wb.save(output_path)
