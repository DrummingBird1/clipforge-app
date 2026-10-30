# tests/bot/test_duplicate_cleaner.py
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys
import time

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "tools", "duplicate_cleaner.py")


def _make_duplicate_pair(tmp_path):
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.txt"
    older.write_text("duplicate content")
    time.sleep(0.05)
    newer.write_text("duplicate content")
    return str(older), str(newer)


def _write_report(tmp_path, files):
    report_path = tmp_path / "report.json"
    report = {"duplicates": [{"hash": "fake", "size_bytes": 18, "count": len(files), "files": files}]}
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f)
    return str(report_path)


def _run(report_path, extra_args=()):
    cmd = [sys.executable, SCRIPT, "--input", report_path, *extra_args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=30)


def test_dry_run_does_not_move_any_file(tmp_path):
    older, newer = _make_duplicate_pair(tmp_path)
    report_path = _write_report(tmp_path, [older, newer])

    result = _run(report_path)

    assert result.returncode == 0
    assert os.path.exists(older) and os.path.exists(newer)
    assert '"executed": false' in result.stdout


def test_execute_keeps_oldest_by_default(tmp_path):
    older, newer = _make_duplicate_pair(tmp_path)
    report_path = _write_report(tmp_path, [older, newer])

    result = _run(report_path, extra_args=["--execute"])

    assert result.returncode == 0
    assert os.path.exists(older), "the oldest copy should be kept by default"
    assert not os.path.exists(newer), "the newer duplicate should have been moved to the recycle bin"


def test_execute_with_keep_newest(tmp_path):
    older, newer = _make_duplicate_pair(tmp_path)
    report_path = _write_report(tmp_path, [older, newer])

    result = _run(report_path, extra_args=["--execute", "--keep", "newest"])

    assert result.returncode == 0
    assert os.path.exists(newer), "--keep newest should keep the newer copy"
    assert not os.path.exists(older), "the older duplicate should have been moved to the recycle bin"


def test_group_with_no_surviving_files_is_skipped_gracefully(tmp_path):
    report_path = _write_report(tmp_path, [str(tmp_path / "gone_a.txt"), str(tmp_path / "gone_b.txt")])

    result = _run(report_path, extra_args=["--execute"])

    assert result.returncode == 0
    assert '"files_moved": 0' in result.stdout


def test_missing_report_file_fails_clearly(tmp_path):
    result = _run(str(tmp_path / "does_not_exist.json"))

    assert result.returncode != 0
    assert "לא נמצא קובץ דוח" in result.stdout
