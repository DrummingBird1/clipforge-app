# tests/web/test_web_app_workspace_env.py
#
# סבב ייצוב: שרת עם CLIPFORGE_WORKSPACE_DIR כותב רק לשם. קודם עשר תיקיות של web_app.py (קליפים, מטמונים, batch
# overrides, כתוביות, שכבות, קובצי בקרה, אצוות פרסום, תיקיות היצוא) היו קבועות ל-<שורש>/workspace, ושרת הבדיקה של
# הסטודיו נאלץ להפנות אותן אחת-אחת. הטסט מייבא את השרת בתהליך נפרד (המשתנה נקרא בייבוא), מפעיל את מי שכותב
# לתיקיות האלה, ובודק שאף נתיב לא יוצא מה-workspace הזמני; ו-use_workspace_dir מפנה את כולן יחד בזמן ריצה.
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys

ROOT = PROJECT_ROOT

_PROBE = r"""
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[1], "src"))
from entrypoints import web_app as W
paths = {}
for name, value in vars(W).items():
    if name.isupper():
        for v in (value if isinstance(value, (list, tuple)) else [value]):
            if isinstance(v, str) and os.path.isabs(v):
                paths.setdefault(name, []).append(v)
written = [W._write_batch_overrides_file({"a.mp4": {"codec": "av1"}}), W._write_layers_file({"layers": [{"type": "text", "text": "x"}]}),
           W._create_run_control_file(), W._prepare_publish_batch([])]
mismatched = [name for name, sub in W.WORKSPACE_SUBDIRS.items() if getattr(W, name) != os.path.join(W.WORKSPACE_DIR, sub)]
print(json.dumps({"paths": paths, "written": written, "default": os.path.join(W.BASE_DIR, "workspace"), "mismatched": mismatched}))
"""


def _under(path, root):
    path, root = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    return path == root or path.startswith(root + os.sep)


def test_a_server_with_its_own_workspace_writes_nothing_to_the_main_one(tmp_path):
    workspace = tmp_path / "ws"
    env = dict(os.environ, CLIPFORGE_WORKSPACE_DIR=str(workspace))
    result = subprocess.run([sys.executable, "-c", _PROBE, ROOT], capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    data = json.loads(result.stdout.strip().splitlines()[-1])
    leaked = {name: values for name, values in data["paths"].items() if any(_under(v, data["default"]) for v in values)}
    assert leaked == {}, f"נתיבים שעדיין מצביעים ל-workspace הראשי: {leaked}"
    for name in ("CLIPS_DIR", "BATCH_OVERRIDES_DIR", "CAPTIONS_EDITS_DIR", "LAYERS_DIR", "RUN_CONTROL_DIR", "PUBLISH_BATCHES_DIR", "WEB_APP_EXPORT_DIRS"):
        assert all(_under(v, workspace) for v in data["paths"][name]), name
    assert all(path and _under(path, workspace) for path in data["written"]), data["written"]
    assert data["mismatched"] == []   # הקבועים שבקוד הם בדיוק המפה של use_workspace_dir - אחרת היא הייתה מפספסת אחד


def test_use_workspace_dir_moves_every_workspace_folder_at_runtime(tmp_path, monkeypatch):
    from entrypoints import web_app
    from utils.bot import approval_store
    from utils.shared import workspace_dir
    approval_dirs = ("CLIPS_REVIEW_DIR", "REJECTED_DIR", "FRIEND_TAGS_CACHE_DIR")
    for module, names in ((web_app, [*web_app.WORKSPACE_SUBDIRS, "WORKSPACE_DIR", "WEB_APP_EXPORT_DIRS"]),
                          (approval_store, approval_dirs), (workspace_dir, ["WORKSPACE_DIR"])):
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))   # מוחזרים בסוף הטסט
    web_app.use_workspace_dir(str(tmp_path))
    assert web_app.WORKSPACE_DIR == workspace_dir.WORKSPACE_DIR == str(tmp_path)
    for name in web_app.WORKSPACE_SUBDIRS:
        assert _under(getattr(web_app, name), tmp_path), name
    assert all(_under(path, tmp_path) for path in web_app.WEB_APP_EXPORT_DIRS)
    # גם אישור הקליפים (הבוט) - אותה תיקיית קליפים כמו השרת
    assert all(_under(getattr(approval_store, name), tmp_path) for name in approval_dirs)
    assert approval_store.CLIPS_REVIEW_DIR == web_app.CLIPS_DIR
    assert _under(web_app._write_batch_overrides_file({"a.mp4": {}}), tmp_path)
