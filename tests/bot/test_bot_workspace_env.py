# tests/bot/test_bot_workspace_env.py
#
# סבב ייצוב: עם CLIPFORGE_WORKSPACE_DIR, אישור הקליפים (utils/approval_store - הקליפים לאישור, הנדחים, מטמון
# החברים) והמיון לספרייה (utils/seo_generator - exports) כותבים רק לשם, ובאותן תיקיות כמו השרת. קודם הם היו
# קבועים ל-<שורש>/workspace, ו-CLIPS_REVIEW_DIR לא היה CLIPS_DIR של שרת עם workspace אחר. כמו
# test_web_app_workspace_env.py: ייבוא בתהליך נפרד (המשתנה נקרא בייבוא), ובדיקה שאף נתיב לא יוצא מה-workspace הזמני.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys

ROOT = PROJECT_ROOT

# המיון רק נרשם (makedirs/copy2 מוחלפים) - גם כשהקוד שבור, הטסט לא כותב ל-workspace האמיתי
_PROBE = r"""
import json, os, sys
from unittest import mock
sys.path.insert(0, os.path.join(sys.argv[1], "src"))
from utils.bot import approval_store, seo_generator
from entrypoints import web_app as W
paths = {}
for module in (approval_store, seo_generator):
    for name, value in vars(module).items():
        if name.isupper() and isinstance(value, str) and os.path.isabs(value):
            paths[module.__name__ + "." + name] = value
targets = []
with mock.patch.object(seo_generator.os, "makedirs", lambda *a, **k: None), \
        mock.patch.object(seo_generator.shutil, "copy2", lambda src, dst: targets.append(dst)):
    seo_generator.sort_clip_to_smart_library("C:/clips/rl_clip.mp4")
print(json.dumps({"paths": paths, "targets": targets, "default": os.path.join(W.BASE_DIR, "workspace"),
                  "server_clips": W.CLIPS_DIR, "review_clips": approval_store.CLIPS_REVIEW_DIR}))
"""


def _under(path, root):
    path, root = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    return path == root or path.startswith(root + os.sep)


def test_approvals_and_the_clip_library_follow_the_workspace_env(tmp_path):
    workspace = tmp_path / "ws"
    env = dict(os.environ, CLIPFORGE_WORKSPACE_DIR=str(workspace))
    result = subprocess.run([sys.executable, "-c", _PROBE, ROOT], capture_output=True, text=True,
                            encoding="utf-8", env=env, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    data = json.loads(result.stdout.strip().splitlines()[-1])

    leaked = {name: value for name, value in data["paths"].items() if _under(value, data["default"])}
    assert leaked == {}, f"נתיבים שעדיין מצביעים ל-workspace הראשי: {leaked}"
    for name in ("CLIPS_REVIEW_DIR", "REJECTED_DIR", "FRIEND_TAGS_CACHE_DIR"):
        assert _under(data["paths"]["utils.bot.approval_store." + name], workspace), name
    assert _under(data["paths"]["utils.bot.seo_generator.EXPORTS_DIR"], workspace)
    assert os.path.normcase(data["review_clips"]) == os.path.normcase(data["server_clips"])   # אותה תיקייה כמו השרת
    assert len(data["targets"]) == 1 and _under(data["targets"][0], workspace), data["targets"]
