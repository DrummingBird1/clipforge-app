# tests/infra/test_utils_layout.py
#
# 19.10.2026: src/utils/ (115 מודולים שטוחים) פוצלה לתתי-חבילות לפי אזור - video/ (עורך-העל), media/ (עיבוד
# וידאו משותף), bot/ (בוט ופרסום), shared/ (תשתית). בכל נתיב ישן נשאר shim שמחליף את עצמו ב-sys.modules
# במודול האמיתי, כך ש-"utils.X" ו-"utils.<אזור>.X" הם אותו אובייקט - import ישן (ענפים של sessions אחרים,
# Grok) ו-monkeypatch על הנתיב הישן ממשיכים לפגוע במודול שהקוד באמת משתמש בו.
# 24.10.2026 (פריט 15): ה-shims שלאף קובץ בריפו (קוד, טסטים, my_scripts, ענף Grok הפתוח) לא היה בהם שימוש נמחקו -
# 81 מתוך 114. מה שנשאר עדיין מיובא מהנתיב הישן; כשהמשתמש האחרון עובר לנתיב החדש, אפשר למחוק גם אותו.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys

ROOT = PROJECT_ROOT
UTILS = os.path.join(ROOT, "src", "utils")
GROUPS = ("video", "media", "bot", "shared")


def _moved():
    """המודולים שעברו ב-19.10.2026 - אלה שיש להם shim בנתיב הישן. מודול חדש נולד ישר ב-utils/<אזור>/ (בלי shim)."""
    flat = {name for name in os.listdir(UTILS) if name.endswith(".py")}
    return {name[:-3]: group for group in GROUPS for name in os.listdir(os.path.join(UTILS, group))
            if name.endswith(".py") and name != "__init__.py" and name in flat}


def test_every_flat_module_is_a_shim_or_belongs_to_the_graph_editor():
    moved = _moved()
    flat = [name[:-3] for name in os.listdir(UTILS) if name.endswith(".py") and name != "__init__.py"]
    # מודול חדש נכנס לתת-החבילה של האזור שלו, לא לשורש utils/ (dataviz_* - עורך הגרפים מעביר אותם ל-src/dataviz)
    strays = [name for name in flat if name not in moved and not name.startswith("dataviz_")]
    assert strays == [], f"מודולים חדשים בשורש utils/ - להעביר ל-utils/<אזור>/: {strays}"
    for name, group in moved.items():
        source = open(os.path.join(UTILS, name + ".py"), encoding="utf-8").read()
        assert f"from utils.{group} import {name} as _module" in source and "sys.modules[__name__] = _module" in source, name


_PROBE = r"""
import importlib, json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "src"))
moved = json.loads(sys.argv[2])
bad, failed = [], {}
for name, group in sorted(moved.items()):
    try:
        new = importlib.import_module(f"utils.{group}.{name}")
        old = importlib.import_module(f"utils.{name}")
    except Exception as e:  # תלות אופציונלית שחסרה - לא עניין של הפיצול, אבל מדווחים
        failed[name] = repr(e)
        continue
    if old is not new or sys.modules[f"utils.{name}"] is not new or getattr(sys.modules["utils"], name) is not new:
        bad.append(name)
from utils.shared import data_dir, workspace_dir
from utils.bot import approval_store, seo_generator, title_generator, youtube_uploader
from utils.shared import diagnostics, docs_sections, ffmpeg_locator
from utils.media import smart_crop
roots = {m.__name__: getattr(m, "PROJECT_ROOT", None) or m.BASE_DIR for m in (
    data_dir, workspace_dir, approval_store, seo_generator, title_generator, youtube_uploader,
    diagnostics, docs_sections, ffmpeg_locator, smart_crop)}
print(json.dumps({"bad": bad, "failed": failed, "roots": roots}))
"""


def test_old_and_new_paths_are_the_same_module_and_paths_still_reach_the_project_root():
    result = subprocess.run([sys.executable, "-c", _PROBE, ROOT, json.dumps(_moved())], capture_output=True, text=True,
                            encoding="utf-8", timeout=180)
    assert result.returncode == 0, result.stderr[-3000:]
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["failed"] == {}
    assert data["bad"] == []
    # מודול שעבר תיקייה פנימה צריך dirname אחד יותר עד שורש הפרויקט
    wrong = {name: root for name, root in data["roots"].items() if os.path.normcase(os.path.realpath(root)) != os.path.normcase(os.path.realpath(ROOT))}
    assert wrong == {}


def test_monkeypatch_on_the_old_path_reaches_the_code_that_uses_it(monkeypatch):
    import utils.state as old_state
    from utils.shared import state

    monkeypatch.setattr("utils.state.CONFIG_FILE", "patched-through-the-old-path")
    assert old_state is state and state.CONFIG_FILE == "patched-through-the-old-path"
