# tests/infra/test_tests_layout.py
#
# 19.10.2026: tests/ (289 קבצים שטוחים) עברה לתיקיות לפי אזור - dataviz/, studio/, bot/, web/, gui/, infra/. בשורש
# tests/ נשארים רק conftest.py, __init__.py ומודולי העזר (web_app_support, media_support, dataviz_helpers...). sys.path
# מוגדר פעם אחת (pythonpath ב-pyproject.toml + conftest), ונתיבים בריפו דרך tests.PROJECT_ROOT / tests.TESTS_DIR.
import os
import re

from tests import PROJECT_ROOT, TESTS_DIR

AREAS = {"dataviz", "studio", "bot", "web", "gui", "infra"}


def _areas():
    return sorted(d for d in os.listdir(TESTS_DIR) if os.path.isfile(os.path.join(TESTS_DIR, d, "__init__.py")))


def test_test_files_live_in_area_folders_not_in_the_tests_root():
    strays = sorted(n for n in os.listdir(TESTS_DIR) if n.startswith("test_") and n.endswith(".py"))
    assert strays == [], f"קובצי טסט בשורש tests/ - להעביר ל-tests/<אזור>/ ({', '.join(sorted(AREAS))}): {strays}"


def test_every_area_folder_is_a_package():
    # בלי __init__.py, pytest מכניס את התיקייה עצמה ל-sys.path ושמות קבצים זהים בשני אזורים מתנגשים
    # 25.10.2026: בלי __pycache__ - קובצי .pyc ישנים מלפני המעבר לתיקיות (test_*.cpython-314.pyc) הכשילו את הטסט מקומית
    folders = [d for d in os.listdir(TESTS_DIR) if d != "__pycache__" and os.path.isdir(os.path.join(TESTS_DIR, d))
               and any(n.startswith("test_") for n in os.listdir(os.path.join(TESTS_DIR, d)))]
    assert sorted(folders) == _areas()
    assert set(_areas()) == AREAS


def test_no_test_file_adds_paths_by_its_own_depth():
    # הוספה ל-sys.path לפי עומק הקובץ מתיקיית אזור היה מכניס את tests/ עצמה - ו-tests/dataviz היה מסתיר את src/dataviz
    pattern = re.compile(r"sys\.path\.insert\([^)\n]*__file__|dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)")
    allowed = {"infra/test_tests_never_touch_real_workspace.py"}   # _LEAK_TEST: קוד לקובץ בשורש tests/ של פרויקט זמני
    offenders = []
    for area in _areas():
        for name in sorted(os.listdir(os.path.join(TESTS_DIR, area))):
            if name.endswith(".py") and f"{area}/{name}" not in allowed:
                with open(os.path.join(TESTS_DIR, area, name), encoding="utf-8") as f:
                    offenders += [f"{area}/{name}:{n}" for n, line in enumerate(f, 1) if pattern.search(line)]
    assert offenders == [], f"נתיב לפי עומק התיקייה - להשתמש ב-tests.PROJECT_ROOT / tests.TESTS_DIR: {offenders}"


def test_project_root_is_the_repo_root():
    assert os.path.isfile(os.path.join(PROJECT_ROOT, "pyproject.toml"))
    assert os.path.isfile(os.path.join(TESTS_DIR, "conftest.py"))
