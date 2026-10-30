# tests/bot/test_read_only_scripts_do_not_mutate_files.py
#
# אכיפה סטטית (item: sandboxing/safety enforcement) של "# Safety: read-only"
# (utils/shared/script_metadata.py convention, נבדק תחבירית ב-test_script_metadata_conventions.py) -
# עד כה זה היה תיוג תיעודי בלבד, בלי שום בדיקה שהסקריפט אכן לא נוגע בקבצי
# המשתמש. סורק את ה-AST של כל סקריפט read-only ומאתר קריאות למחיקה/העברה/
# שינוי-שם אמיתיים של קובץ (os.remove/unlink/rmdir/rename/replace,
# shutil.rmtree/move, send2trash) - לא open() (כתיבת קובץ *חדש* כמו דוח JSON
# היא בדיוק מה ש"read-only" מתיר, ראו disk_scanner.py's report.json).
#
# "read-only" בקודבייס הזה אומר "לא מוחק/מזיז את קבצי הקלט של המשתמש" - לא
# "אף פעם לא נוגע בדיסק בכלל". סקריפט שמנקה קובץ זמני שהוא עצמו יצר (temp
# frame, temp concat-list) הוא עדיין read-only במובן הזה. במקום ניתוח
# data-flow אמיתי (שהיה דורש להבין אם הנתיב הגיע מ-glob על תיקיית הקלט או
# מ-tempfile), קריאה כזו פשוט צריכה הערה "# safe: ..." על אותה שורה שמסבירה
# למה - זה גם מסמן במפורש למי שקורא את הקוד, וגם נותן דרך מודעת ומכוונת
# לחרוג מהבדיקה כשבאמת בטוח, בלי לבטל את הבדיקה כליל.
import ast
from tests import PROJECT_ROOT
import glob
import os


import pytest

BASE_DIR = PROJECT_ROOT
ALL_SCRIPTS = sorted(glob.glob(os.path.join(BASE_DIR, "my_scripts", "**", "*.py"), recursive=True))

DANGEROUS_ATTR_CALLS = {
    ("os", "remove"), ("os", "unlink"), ("os", "rmdir"), ("os", "rename"), ("os", "replace"),
    ("shutil", "rmtree"), ("shutil", "move"),
}
DANGEROUS_BARE_NAMES = {"send2trash"}  # from send2trash import send2trash - נקרא בלי prefix מודול
SAFE_MARKER = "# safe:"


def is_read_only_script(path):
    with open(path, "r", encoding="utf-8") as f:
        for _ in range(12):
            line = f.readline()
            if not line:
                break
            stripped = line.strip()
            if stripped.startswith("# Safety:") and stripped[len("# Safety:"):].strip().lower() == "read-only":
                return True
    return False


def find_unmarked_dangerous_calls(path):
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()
    lines = source.splitlines()
    tree = ast.parse(source, filename=path)

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        matched = (
            isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and (func.value.id, func.attr) in DANGEROUS_ATTR_CALLS
        ) or (
            isinstance(func, ast.Name) and func.id in DANGEROUS_BARE_NAMES
        )
        if not matched:
            continue
        line_no = node.lineno
        line_text = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
        if SAFE_MARKER in line_text:
            continue
        try:
            display_path = os.path.relpath(path, BASE_DIR)
        except ValueError:
            display_path = path  # tmp_path בטסטים יכול לשבת על כונן אחר מ-BASE_DIR ב-Windows
        violations.append(f"{display_path}:{line_no}: {line_text.strip()}")
    return violations


READ_ONLY_SCRIPTS = [p for p in ALL_SCRIPTS if is_read_only_script(p)]


def test_at_least_one_read_only_script_exists():
    # רגרסיה על הבדיקה עצמה - אם is_read_only_script אי-פעם נשבר (למשל שינוי
    # במוסכמת הכותרת) ומחזיר [] בלי לזרוק, שאר הבדיקות למטה פשוט "יעברו" על
    # רשימה ריקה בלי לבדוק שום דבר בפועל.
    assert len(READ_ONLY_SCRIPTS) >= 5


@pytest.mark.parametrize("path", READ_ONLY_SCRIPTS, ids=[os.path.relpath(p, BASE_DIR) for p in READ_ONLY_SCRIPTS])
def test_read_only_script_has_no_unmarked_file_mutations(path):
    violations = find_unmarked_dangerous_calls(path)
    assert not violations, (
        "'# Safety: read-only' script calls a file-deleting/moving/renaming function without a "
        "'# safe: ...' justification comment on that exact line. If this call only touches a "
        "temp file the script created itself (not the user's real input), add that comment "
        "explaining why; if it actually touches user files, this script should be tagged "
        "'# Safety: modifies' instead:\n" + "\n".join(violations)
    )


# --- unit tests for the check itself (synthetic fixture scripts, not the real my_scripts/) ---
# מוודאים שהבדיקה באמת תופסת הפרה, לא רק ש"עוברת" על הקודבייס הנוכחי כי
# הוא כבר נקי - בלי זה, בדיקה עם באג שתמיד מחזירה [] הייתה "עוברת" תמיד.

def test_find_unmarked_dangerous_calls_catches_os_remove(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("import os\nos.remove(some_path)\n", encoding="utf-8")
    violations = find_unmarked_dangerous_calls(str(script))
    assert len(violations) == 1
    assert "os.remove" in violations[0]


def test_find_unmarked_dangerous_calls_catches_shutil_move(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("import shutil\nshutil.move(src, dst)\n", encoding="utf-8")
    violations = find_unmarked_dangerous_calls(str(script))
    assert len(violations) == 1


def test_find_unmarked_dangerous_calls_catches_bare_send2trash(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("from send2trash import send2trash\nsend2trash(some_path)\n", encoding="utf-8")
    violations = find_unmarked_dangerous_calls(str(script))
    assert len(violations) == 1


def test_find_unmarked_dangerous_calls_allows_marked_call(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("import os\nos.remove(temp_path)  # safe: temp file this script made\n", encoding="utf-8")
    assert find_unmarked_dangerous_calls(str(script)) == []


def test_find_unmarked_dangerous_calls_ignores_plain_open_calls(tmp_path):
    # open() לכתיבה (דוח JSON חדש וכו') הוא בדיוק מה ש"read-only" מתיר -
    # לא אמור להיתפס כהפרה בכלל.
    script = tmp_path / "fake_script.py"
    script.write_text('open("report.json", "w").write("{}")\n', encoding="utf-8")
    assert find_unmarked_dangerous_calls(str(script)) == []


def test_find_unmarked_dangerous_calls_ignores_unrelated_remove_methods(tmp_path):
    # list.remove()/set.remove() וכו' - לא os.remove - לא אמורים להיתפס
    script = tmp_path / "fake_script.py"
    script.write_text("my_list = [1, 2]\nmy_list.remove(1)\n", encoding="utf-8")
    assert find_unmarked_dangerous_calls(str(script)) == []


def test_is_read_only_script_true_for_read_only_tag(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("# Safety: read-only\nprint('hi')\n", encoding="utf-8")
    assert is_read_only_script(str(script)) is True


def test_is_read_only_script_false_for_modifies_tag(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("# Safety: modifies\nprint('hi')\n", encoding="utf-8")
    assert is_read_only_script(str(script)) is False


def test_is_read_only_script_false_when_no_tag_at_all(tmp_path):
    script = tmp_path / "fake_script.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    assert is_read_only_script(str(script)) is False
