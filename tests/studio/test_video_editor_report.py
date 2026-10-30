# tests/studio/test_video_editor_report.py
#
# ייצוא דוח קידוד (item) - utils/video/video_editor_report.py, אותו עיקרון בדיוק
# כמו tests/bot/test_report_excel.py (disk_scanner.py): report הוא dict טהור,
# לא תלוי ב-video_editor.py עצמו/ffmpeg.
import csv


from openpyxl import load_workbook

from utils.video.video_editor_report import write_csv_report, write_xlsx_report

SAMPLE_REPORT = {
    "elapsed_seconds": 42.3,
    "avg_seconds_per_file": 21.15,
    "files_created": 2,
    "skipped": 1,
    "errors": 0,
    "codec": "hevc",
    "container": "mp4",
    "hwaccel": True,
    "parallel": 2,
    "effort": "medium",
    "files": [
        {
            "source_filename": "clip1.mp4", "output_filename": "clip1_edited_horizontal.mp4",
            "codec": "hevc", "container": "mp4", "resolution": "1920x1080", "fps": "30",
            "duration_seconds": 12.5, "output_size_mb": 3.4, "render_seconds": 8.1, "hdr": False,
        },
        {
            "source_filename": "clip2.mp4", "output_filename": "clip2_edited_horizontal.mp4",
            "codec": "hevc", "container": "mp4", "resolution": "1080x1920", "fps": "29.97",
            "duration_seconds": 20.0, "output_size_mb": 5.6, "render_seconds": 13.05, "hdr": True,
        },
    ],
}


def test_write_xlsx_report_creates_expected_sheets(tmp_path):
    output_path = tmp_path / "report.xlsx"
    write_xlsx_report(SAMPLE_REPORT, str(output_path))

    assert output_path.exists()
    wb = load_workbook(str(output_path))
    assert wb.sheetnames == ["סיכום", "קבצים"]


def test_xlsx_summary_sheet_contains_computed_values(tmp_path):
    output_path = tmp_path / "report.xlsx"
    write_xlsx_report(SAMPLE_REPORT, str(output_path))

    wb = load_workbook(str(output_path))
    ws = wb["סיכום"]
    rows = {row[0].value: row[1].value for row in ws.iter_rows(min_row=2)}
    assert rows["קבצים שנוצרו"] == 2
    assert rows["קבצים שדולגו (כבר קיימים)"] == 1
    assert rows["קודק"] == "hevc"
    assert rows["האצת GPU (hwaccel)"] == "כן"


def test_xlsx_files_sheet_has_one_row_per_file(tmp_path):
    output_path = tmp_path / "report.xlsx"
    write_xlsx_report(SAMPLE_REPORT, str(output_path))

    wb = load_workbook(str(output_path))
    ws = wb["קבצים"]
    data_rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(data_rows) == 2
    assert data_rows[0][0] == "clip1.mp4"
    assert data_rows[0][1] == "clip1_edited_horizontal.mp4"
    assert data_rows[0][4] == "1920x1080"
    assert data_rows[0][9] == "לא"  # HDR=False
    assert data_rows[1][9] == "כן"  # HDR=True


def test_write_xlsx_report_handles_empty_report(tmp_path):
    output_path = tmp_path / "empty_report.xlsx"
    write_xlsx_report({}, str(output_path))
    assert output_path.exists()
    wb = load_workbook(str(output_path))
    assert list(wb["קבצים"].iter_rows(min_row=2, values_only=True)) == []


def test_write_csv_report_creates_file_with_summary_and_files(tmp_path):
    output_path = tmp_path / "report.csv"
    write_csv_report(SAMPLE_REPORT, str(output_path))

    assert output_path.exists()
    with open(output_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    flat_rows = {row[0]: row[1] for row in rows if len(row) == 2}
    assert flat_rows["קבצים שנוצרו"] == "2"
    assert flat_rows["קודק"] == "hevc"

    file_rows = [row for row in rows if len(row) == 10 and row[0] not in ("שם קובץ מקור",)]
    assert len(file_rows) == 2
    assert file_rows[0][0] == "clip1.mp4"
    assert file_rows[1][0] == "clip2.mp4"


def test_write_csv_report_handles_empty_report(tmp_path):
    output_path = tmp_path / "empty_report.csv"
    write_csv_report({}, str(output_path))
    assert output_path.exists()
