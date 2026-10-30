# tests/bot/test_disk_scanner_excel_default.py
#
# רגרסיה: --export-excel היה opt-in, אבל ה-GUI (utils/shared/worker.py) לעולם לא
# מזין דגלים ספציפיים-לסקריפט (רק --input_dir הגנרי) - אז לא הייתה שום דרך
# להפעיל את הדגל דרך כפתור ההרצה, וכל סריקה מה-GUI הפיקה JSON בלבד. הוחלף
# ב---no-excel (opt-out): report.xlsx נוצר כברירת מחדל, בלי צורך בשום דגל.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys

BASE_DIR = PROJECT_ROOT
DISK_SCANNER = os.path.join(BASE_DIR, "my_scripts", "tools", "disk_scanner.py")


def _make_small_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "a.txt").write_text("hello")
    (target / "b.txt").write_text("world")
    return target


def _run_scanner(tmp_path, target, output_json, extra_args=()):
    cmd = [sys.executable, DISK_SCANNER, "--target_dir", str(target), "--output", str(output_json), *extra_args]
    # encoding="utf-8" מפורש - בלעדיו subprocess נופל לקידוד ה-locale (cp1255
    # בווינדוס עברי), ופלט disk_scanner.py (עברית+אימוג'ים) קורס עם UnicodeDecodeError.
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, f"disk_scanner.py failed: {result.stdout}\n{result.stderr}"
    return result


def test_excel_and_html_are_created_by_default(tmp_path):
    target = _make_small_target(tmp_path)
    output_json = tmp_path / "report.json"

    _run_scanner(tmp_path, target, output_json)

    output_xlsx = output_json.with_suffix(".xlsx")
    output_html = output_json.with_suffix(".html")
    assert output_json.exists()
    assert output_xlsx.exists(), "report.xlsx should be created by default, with no flag needed"
    assert output_html.exists(), "report.html should be created by default, with no flag needed"

    with open(output_json, encoding="utf-8") as f:
        report = json.load(f)
    assert report["total_files_scanned"] == 2


def test_no_excel_flag_skips_excel(tmp_path):
    target = _make_small_target(tmp_path)
    output_json = tmp_path / "report.json"

    _run_scanner(tmp_path, target, output_json, extra_args=["--no-excel"])

    output_xlsx = output_json.with_suffix(".xlsx")
    assert output_json.exists()
    assert not output_xlsx.exists(), "--no-excel should skip the .xlsx file"


def test_no_html_flag_skips_html(tmp_path):
    target = _make_small_target(tmp_path)
    output_json = tmp_path / "report.json"

    _run_scanner(tmp_path, target, output_json, extra_args=["--no-html"])

    output_html = output_json.with_suffix(".html")
    assert output_json.exists()
    assert not output_html.exists(), "--no-html should skip the .html file"


def test_result_line_is_printed_for_gui_consumption(tmp_path):
    target = _make_small_target(tmp_path)
    output_json = tmp_path / "report.json"

    result = _run_scanner(tmp_path, target, output_json)

    result_lines = [line for line in result.stdout.splitlines() if line.startswith("RESULT:")]
    assert len(result_lines) == 1
    payload = json.loads(result_lines[0][len("RESULT:"):].strip())
    assert payload["files_scanned"] == 2


def test_without_a_target_it_scans_the_home_folder(tmp_path):
    """30.10.2026: ברירת המחדל הייתה D:\ (כונן קבוע) - עכשיו תיקיית הבית. USERPROFILE/HOME מופנים לתיקייה קטנה כאן."""
    home = _make_small_target(tmp_path)
    output_json = tmp_path / "report.json"
    env = {**os.environ, "USERPROFILE": str(home), "HOME": str(home)}
    cmd = [sys.executable, DISK_SCANNER, "--output", str(output_json), "--no-excel", "--no-html"]
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=30, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(output_json.read_text(encoding="utf-8"))["target_directory"] == str(home)
