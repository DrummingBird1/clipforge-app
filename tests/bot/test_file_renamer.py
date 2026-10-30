import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys


from my_scripts.tools.file_renamer import build_new_name

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "tools", "file_renamer.py")


def _run(tmp_path, extra_args=()):
    cmd = [sys.executable, SCRIPT, "--input_dir", str(tmp_path), *extra_args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=30)


def _result_json(stdout):
    for line in stdout.splitlines():
        if line.startswith("RESULT:"):
            return json.loads(line[len("RESULT:"):].strip())
    return None


def test_prefix_and_number():
    assert build_new_name(1, "Clip", "", True, False) == "Clip1"


def test_prefix_with_space_and_number():
    assert build_new_name(3, "Clip", "", True, True) == "Clip 3"


def test_number_disabled():
    assert build_new_name(5, "Clip", "", False, False) == "Clip"


def test_suffix_only():
    assert build_new_name(2, "", "_final", False, False) == "_final"


def test_prefix_suffix_and_number_combined():
    assert build_new_name(7, "RL", "_edit", True, True) == "RL 7_edit"


def test_all_fields_empty_falls_back_to_safe_name():
    assert build_new_name(4, "", "", False, False) == "renamed_file_4"


def test_space_flag_ignored_when_prefix_empty():
    # אין prefix, אז לא אמור להתווסף רווח מיותר בתחילת השם
    assert build_new_name(1, "", "", True, True) == "1"


# --- main() end-to-end (subprocess אמיתי, קבצים אמיתיים על הדיסק) ---

def test_renames_files_with_prefix_and_numbering_in_sorted_order(tmp_path):
    for name in ("b.txt", "a.txt", "c.txt"):
        (tmp_path / name).write_text("x")

    result = _run(tmp_path, extra_args=["--prefix", "Clip", "--space", "true"])

    assert result.returncode == 0
    assert sorted(os.listdir(tmp_path)) == ["Clip 1.txt", "Clip 2.txt", "Clip 3.txt"]
    assert _result_json(result.stdout) == {"renamed": 3, "errors": 0, "total": 3}


def test_number_false_disables_numbering(tmp_path):
    (tmp_path / "only.txt").write_text("x")

    result = _run(tmp_path, extra_args=["--prefix", "Clip", "--number", "False"])

    assert result.returncode == 0
    assert os.listdir(tmp_path) == ["Clip.txt"]


def test_number_false_with_multiple_same_extension_files_is_rejected_upfront(tmp_path):
    # item: בדיקת באגים מקיפה - בעבר זה היה נגמר בשינוי-שם רק לקובץ הראשון
    # ו-FileExistsError על כל השאר, בלי אזהרה מראש. עכשיו נדחה מיד, בלי לגעת
    # באף קובץ, כי שני הקבצים היו מקבלים בדיוק אותו שם ("Clip.txt").
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("x")

    result = _run(tmp_path, extra_args=["--prefix", "Clip", "--number", "False"])

    assert result.returncode == 0
    assert "[ERROR]" in result.stdout
    assert ".txt" in result.stdout
    assert sorted(os.listdir(tmp_path)) == ["a.txt", "b.txt"]  # אף קובץ לא נגע בו
    assert _result_json(result.stdout) is None


def test_number_false_with_different_extensions_is_not_a_collision(tmp_path):
    # אותו שם בסיס אבל סיומות שונות - "Clip.txt"/"Clip.jpg" לא מתנגשים בכלל,
    # אז זה אמור לעבוד בלי מספור.
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.jpg").write_text("x")

    result = _run(tmp_path, extra_args=["--prefix", "Clip", "--number", "False"])

    assert result.returncode == 0
    assert "[ERROR]" not in result.stdout
    assert sorted(os.listdir(tmp_path)) == ["Clip.jpg", "Clip.txt"]


def test_missing_input_dir_reports_error_and_does_not_crash(tmp_path):
    missing = tmp_path / "does_not_exist"

    result = _run(missing)

    assert result.returncode == 0
    assert "[ERROR]" in result.stdout
    assert _result_json(result.stdout) is None


def test_empty_folder_reports_warning(tmp_path):
    result = _run(tmp_path)

    assert result.returncode == 0
    assert "[WARNING]" in result.stdout
    assert _result_json(result.stdout) is None


def test_subfolders_are_not_renamed_only_files(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "a_subfolder").mkdir()

    result = _run(tmp_path, extra_args=["--number", "False"])

    assert result.returncode == 0
    assert _result_json(result.stdout)["total"] == 1
    assert (tmp_path / "a_subfolder").is_dir()


def test_a_failed_rename_is_counted_as_an_error_and_does_not_stop_the_batch(tmp_path):
    # שני קבצים - a.txt ו-b.txt, ממוספרים 1/2 בהתאמה (--number ברירת מחדל True).
    # מקדימים תיקייה בשם "1.txt" - os.rename מקובץ ליעד שהוא כבר תיקייה
    # קיימת נכשל באמת (לא מוק), אבל הקובץ השני עדיין אמור להצליח אחריו.
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.txt").write_text("x")
    (tmp_path / "1.txt").mkdir()

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "[ERROR]" in result.stdout
    assert _result_json(result.stdout) == {"renamed": 1, "errors": 1, "total": 2}
    assert os.path.exists(tmp_path / "2.txt")
