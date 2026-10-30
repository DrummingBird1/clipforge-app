# tests/bot/test_super_manager.py
#
# my_scripts/tools/super_manager.py ("מנהל-העל") מאחד את disk_scanner.py +
# report_to_excel.py + duplicate_cleaner.py לסקריפט אחד עם בורר-מצב (--mode).
# הבדיקות כאן מתמקדות במנגנון-הבורר עצמו (טעינה דינמית + סינון sys.argv
# נכון לכל מצב) - לא בלוגיקת הסריקה/הניקוי עצמה, שכבר מכוסה במלואה ע"י
# tests/bot/test_disk_scanner_excel_default.py/test_duplicate_cleaner.py הקיימים
# (אותם קבצי מקור בדיוק, super_manager.py רק קורא ל-main() שלהם). E2E אמיתי
# דרך subprocess, בדיוק כמו test_duplicate_cleaner.py.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys
import time

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "tools", "super_manager.py")


def _run(args, timeout=60):
    cmd = [sys.executable, SCRIPT, *args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=timeout)


def test_scan_mode_finds_duplicates_and_writes_report(tmp_path):
    (tmp_path / "a.txt").write_text("same content")
    (tmp_path / "b.txt").write_text("same content")
    report_path = tmp_path / "report.json"

    result = _run(["--mode", "scan", "--target_dir", str(tmp_path), "--output", str(report_path), "--no-excel", "--no-html"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total_files_scanned"] == 2
    assert report["duplicate_groups_found"] == 1


def test_scan_mode_is_the_default_when_mode_omitted(tmp_path):
    (tmp_path / "solo.txt").write_text("just one file")
    report_path = tmp_path / "report.json"

    result = _run(["--target_dir", str(tmp_path), "--output", str(report_path), "--no-excel", "--no-html"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert report_path.exists()


def test_report_mode_converts_existing_json_to_excel(tmp_path):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total_files_scanned": 3, "duplicate_groups_found": 0, "junk_files_found": 0, "media_files_analyzed": 0,
        "duplicates": [], "junk_files": [], "media_files": [], "errors": [],
    }), encoding="utf-8")
    excel_path = tmp_path / "report.xlsx"

    result = _run(["--mode", "report", "--input", str(report_path), "--output", str(excel_path)])

    assert result.returncode == 0, result.stdout + result.stderr
    assert excel_path.exists()


def test_clean_mode_dry_run_does_not_move_files(tmp_path):
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.txt"
    older.write_text("dup")
    time.sleep(0.05)
    newer.write_text("dup")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "duplicates": [{"hash": "x", "size_bytes": 3, "count": 2, "files": [str(older), str(newer)]}],
    }), encoding="utf-8")

    result = _run(["--mode", "clean", "--input", str(report_path)])

    assert result.returncode == 0, result.stdout + result.stderr
    assert older.exists() and newer.exists()
    assert '"executed": false' in result.stdout


def test_clean_mode_execute_moves_the_non_kept_copy(tmp_path):
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.txt"
    older.write_text("dup")
    time.sleep(0.05)
    newer.write_text("dup")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "duplicates": [{"hash": "x", "size_bytes": 3, "count": 2, "files": [str(older), str(newer)]}],
    }), encoding="utf-8")

    result = _run(["--mode", "clean", "--input", str(report_path), "--execute"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert older.exists(), "the oldest copy should be kept by default"
    assert not newer.exists(), "the newer duplicate should have been moved to the recycle bin"


def test_invalid_mode_rejected_by_argparse_choices():
    result = _run(["--mode", "not-a-real-mode"])
    assert result.returncode != 0
    assert "invalid choice" in (result.stderr or "")


def test_report_and_clean_modes_do_not_accidentally_rescan_the_disk(tmp_path):
    # item: כל מצב עצמאי לגמרי - "report"/"clean" קוראים רק ל-report.json קיים,
    # אף פעם לא סורקים דיסק מחדש. --target_dir (רלוונטי רק ל-scan) מועבר בכל
    # זאת ב-passthrough_argv בלי לגרום נזק - argparse הפנימי של report/clean
    # לא מכיר אותו כלל ומתעלם ממנו בשקט (parse_known_args), בלי לנסות לפרש
    # אותו כנתיב-לסריקה.
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total_files_scanned": 0, "duplicate_groups_found": 0, "junk_files_found": 0, "media_files_analyzed": 0,
        "duplicates": [], "junk_files": [], "media_files": [], "errors": [],
    }), encoding="utf-8")

    result = _run(["--mode", "report", "--target_dir", "Z:\\this_drive_does_not_exist", "--input", str(report_path), "--output", str(tmp_path / "out.xlsx")])

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "out.xlsx").exists()
