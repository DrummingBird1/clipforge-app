# tests/bot/test_report_excel.py


from openpyxl import load_workbook

from utils.shared.report_excel import write_excel_report

SAMPLE_REPORT = {
    "target_directory": "D:\\Gameplay",
    "scan_started_at": "2026-01-01T00:00:00",
    "scan_finished_at": "2026-01-01T00:05:00",
    "scan_duration_seconds": 300,
    "total_files_scanned": 10,
    "total_size_bytes": 2 * 1024 ** 3,
    "media_files_analyzed": 5,
    "duplicate_groups_found": 1,
    "duplicate_wasted_bytes": 500 * 1024 ** 2,
    "junk_files_found": 2,
    "skipped_reparse_points_count": 0,
    "errors": [],
    "duplicates": [
        {"hash": "abcd1234abcd1234", "size_bytes": 100 * 1024 ** 2, "files": ["D:\\a.mp4", "D:\\b.mp4"]},
    ],
    "junk_files": [
        {"path": "D:\\Thumbs.db", "size_bytes": 4096, "reason": "קובץ מערכת"},
    ],
    "media_files": [
        {
            "path": "D:\\a.mp4", "size_bytes": 50 * 1024 ** 2, "video_codec": "h264", "audio_codec": "aac",
            "bitrate": 8_000_000, "duration_seconds": 125.4, "width": 1920, "height": 1080, "full_hash": "abcd1234abcd1234",
        },
    ],
}


def test_write_excel_report_creates_expected_sheets(tmp_path):
    output_path = tmp_path / "report.xlsx"
    write_excel_report(SAMPLE_REPORT, str(output_path))

    assert output_path.exists()
    wb = load_workbook(str(output_path))
    assert wb.sheetnames == ["סיכום", "כפילויות", "קבצי זבל", "קבצי מדיה"]


def test_summary_sheet_contains_computed_values(tmp_path):
    output_path = tmp_path / "report.xlsx"
    write_excel_report(SAMPLE_REPORT, str(output_path))

    wb = load_workbook(str(output_path))
    ws = wb["סיכום"]
    rows = {row[0].value: row[1].value for row in ws.iter_rows(min_row=2)}
    assert rows["סה\"כ קבצים שנסרקו"] == 10
    assert rows["סה\"כ נפח (GB)"] == 2.0


def test_duplicates_sheet_has_one_row_per_file_in_group(tmp_path):
    output_path = tmp_path / "report.xlsx"
    write_excel_report(SAMPLE_REPORT, str(output_path))

    wb = load_workbook(str(output_path))
    ws = wb["כפילויות"]
    data_rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(data_rows) == 2  # שני קבצים באותה קבוצת כפילות אחת
    assert data_rows[0][1] == "D:\\a.mp4"
    assert data_rows[1][1] == "D:\\b.mp4"


def test_errors_sheet_only_created_when_errors_present(tmp_path):
    output_path = tmp_path / "report_no_errors.xlsx"
    write_excel_report(SAMPLE_REPORT, str(output_path))
    wb = load_workbook(str(output_path))
    assert "שגיאות" not in wb.sheetnames

    report_with_errors = dict(SAMPLE_REPORT, errors=[{"path": "D:\\locked.mp4", "error": "Permission denied"}])
    output_path2 = tmp_path / "report_with_errors.xlsx"
    write_excel_report(report_with_errors, str(output_path2))
    wb2 = load_workbook(str(output_path2))
    assert "שגיאות" in wb2.sheetnames


def test_write_excel_report_handles_empty_report(tmp_path):
    output_path = tmp_path / "empty_report.xlsx"
    write_excel_report({}, str(output_path))
    assert output_path.exists()
