# tests/infra/test_version_sync.py
#
# 8.11.2026: גרסת האפליקציה כתובה בשני מקומות - pyproject.toml ו-src/utils/shared/version.py (ההערה בקובץ אומרת "בסנכרון ידני"),
# ו-release.yml שולף את הערות הגרסה מהסעיף "## <גרסה>" של CHANGELOG.md. אף בדיקה לא שמרה על זה: bump שנעשה רק באחד מהם
# עבר את כל הטסטים, ו-release.yml היה נכשל או מפרסם "ClipForge <גרסה>" בלי הערות. הבדיקה הזו נכשלת על כל אחד מהמצבים האלה.
import os
import re

from tests import PROJECT_ROOT
from utils.shared.version import APP_VERSION


def _read(name):
    with open(os.path.join(PROJECT_ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_pyproject_and_version_py_have_the_same_version():
    match = re.search(r'^version = "([^"]+)"', _read("pyproject.toml"), re.M)
    assert match, "pyproject.toml has no version line"
    assert match.group(1) == APP_VERSION, f"pyproject.toml says {match.group(1)} but version.py says {APP_VERSION}"


def test_the_changelog_has_a_section_for_the_current_version():
    # אותו ביטוי כמו ב-release.yml, שמדפיס את הסעיף כהערות הגרסה
    assert re.search(rf"^## {re.escape(APP_VERSION)}\b", _read("CHANGELOG.md"), re.M), f"CHANGELOG.md has no '## {APP_VERSION}' section"


def test_the_newest_changelog_section_is_not_older_than_the_current_version():
    def key(version):
        return tuple(int(part) for part in version.split("."))
    top = re.search(r"^## (\d+\.\d+\.\d+)\b", _read("CHANGELOG.md"), re.M)
    assert top and key(top.group(1)) <= key(APP_VERSION), f"CHANGELOG.md starts at {top and top.group(1)}, newer than version {APP_VERSION}"
