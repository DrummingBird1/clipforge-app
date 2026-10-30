# tests/bot/test_report_html.py


from utils.shared.report_html import write_html_report


def _sample_report():
    return {
        "target_directory": "D:\\",
        "scan_finished_at": "2026-01-05T12:00:00",
        "total_files_scanned": 100,
        "total_size_bytes": 5 * 1024**3,
        "duplicate_wasted_bytes": 1024**3,
        "media_files_analyzed": 10,
        "duplicates": [
            {"hash": "abc", "size_bytes": 1024**3, "count": 2, "files": ["D:\\a.mp4", "D:\\b.mp4"]},
        ],
        "junk_files": [
            {"path": "D:\\Thumbs.db", "size_bytes": 1024, "reason": "קובץ זבל מוכר"},
        ],
    }


def test_write_html_report_creates_file_with_summary(tmp_path):
    output_path = tmp_path / "report.html"
    write_html_report(_sample_report(), str(output_path))

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "100" in content  # total_files_scanned
    assert "D:\\a.mp4" in content
    assert "Thumbs.db" in content


def test_write_html_report_handles_empty_report(tmp_path):
    output_path = tmp_path / "report.html"
    write_html_report({}, str(output_path))
    assert output_path.exists()


def test_write_html_report_escapes_html_special_characters(tmp_path):
    report = _sample_report()
    report["junk_files"] = [{"path": "D:\\<script>alert(1)</script>.tmp", "size_bytes": 1, "reason": "x"}]
    output_path = tmp_path / "report.html"

    write_html_report(report, str(output_path))

    content = output_path.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_write_html_report_truncates_long_lists_with_a_note(tmp_path):
    report = _sample_report()
    report["junk_files"] = [{"path": f"D:\\file{i}.tmp", "size_bytes": 1, "reason": "x"} for i in range(80)]
    output_path = tmp_path / "report.html"

    write_html_report(report, str(output_path))

    content = output_path.read_text(encoding="utf-8")
    assert "ועוד 30 קבצים" in content
    assert "file79.tmp" not in content  # מעבר ל-MAX_JUNK_FILES_SHOWN
    assert "file49.tmp" in content
