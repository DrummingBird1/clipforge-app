# tests/infra/test_workspace_cache_dirs.py
#
# 19.10.2026: המטמונים של השרת ושל עורך-העל יושבים תחת workspace/.cache/ - לא כתיקיות נקודה פזורות בשורש ה-workspace
# (.previews, .layers, .run_control, .run_manifests, .thumbnail_cache, .thumbnail_candidates). התיקיות הישנות לא נקראות
# יותר (מטמון נוצר מחדש). קובצי הריצה (run manifests) נכתבים ע"י video_editor.py ונקראים ע"י השרת - אותו נתיב בשניהם.
import os

from entrypoints import web_app
from tests.video_editor_golden import _load
from ui import approvals_tab, stats_tab

CACHES = ("PREVIEWS_DIR", "LAYERS_DIR", "RUN_CONTROL_DIR", "RUN_MANIFESTS_DIR", "THUMBNAIL_CACHE_DIR", "THUMBNAIL_CANDIDATES_DIR")


def test_server_caches_live_under_workspace_dot_cache():
    # המיפוי ולא הקבועים עצמם: conftest מפנה חלק מהם (RUN_CONTROL_DIR) לתיקייה זמנית לכל טסט
    for name in CACHES:
        assert os.path.dirname(web_app.WORKSPACE_SUBDIRS[name]) == ".cache", name


def test_use_workspace_dir_moves_the_caches_too(tmp_path, monkeypatch):
    original = web_app.WORKSPACE_DIR
    try:
        web_app.use_workspace_dir(str(tmp_path))
        for name in CACHES:
            assert os.path.dirname(getattr(web_app, name)) == os.path.join(str(tmp_path), ".cache"), name
    finally:
        web_app.use_workspace_dir(original)


def test_video_editor_writes_run_manifests_where_the_server_reads_them(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", web_app.WORKSPACE_DIR)
    module = _load(str(tmp_path), [], 0)
    assert os.path.normcase(module.RUN_MANIFESTS_DIR) == os.path.normcase(web_app.RUN_MANIFESTS_DIR)


def test_desktop_gui_uses_the_same_thumbnail_caches():
    assert approvals_tab.THUMBNAIL_CACHE_DIR == web_app.THUMBNAIL_CACHE_DIR
    assert stats_tab.THUMBNAIL_CANDIDATES_DIR == web_app.THUMBNAIL_CANDIDATES_DIR
