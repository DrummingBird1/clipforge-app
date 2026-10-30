# tests/dataviz/test_dataviz_tool_folder.py
#
# 23.10.2026: לעורך הגרפים תיקייה משלו בתיקיית הייצוא ("תיקייה לכלי מסוים", export_dir.TOOL_FOLDERS). קודם השרת סירב לשמור
# אותה. עכשיו היא גוברת על הכללית: dataviz_maker.py כותב ל-<תיקייה>/outputs/<כיוון>, והמסך מציג ומגיש משם, וגם את מה שכבר
# ב-<כללית>/dataviz וב-workspace. פתיחת תיקייה והגיבוי האוטומטי מכירים אותה, וההודעה בסוף ריצה נבדקת לפי התיקייה שלו.
import importlib.util
import os

import pytest

from dataviz.episode import load_episode
from entrypoints import web_app
from tests import PROJECT_ROOT
from tests.dataviz_helpers import write_episode
from tests.web_app_support import client
from utils.shared import export_dir

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


@pytest.fixture(scope="module")
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_tool_folder", os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)
    monkeypatch.setattr(export_dir, "_announced", False)
    general, own, workspace = tmp_path / "exports", tmp_path / "dataviz_out", tmp_path / "workspace"
    for folder in (general, own, workspace):
        folder.mkdir()
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    export_dir.save_root(str(general))
    return general, own, workspace


def test_a_dataviz_folder_is_saved_and_wins_over_the_general_one(maker, folders, tmp_path):
    general, own, workspace = folders
    assert client.post("/api/export_dir", json={"tool": "dataviz", "root": str(own)}).status_code == 200   # קודם: 400
    tools = {t["tool"]: t for t in client.get("/api/export_dir").json()["tools"]}
    assert tools["dataviz"]["root"] == str(own) and tools["dataviz"]["effective"] == str(own)
    config = load_episode(write_episode(tmp_path / "eps", overrides=SMALL, name="ep")).config
    assert maker.output_paths(config, "full")[0] == str(own / "outputs" / "horizontal")


def test_the_screen_lists_the_dataviz_folder_and_what_is_already_in_the_general_one(folders, tmp_path, monkeypatch):
    general, own, workspace = folders
    export_dir.save_tool_root("dataviz", str(own))
    new, earlier = own / "outputs" / "horizontal", general / "dataviz" / "outputs" / "horizontal"
    new.mkdir(parents=True)
    earlier.mkdir(parents=True)
    (new / "a.mp4").write_bytes(b"new")
    (earlier / "b.mp4").write_bytes(b"earlier")                                 # מלפני שהוגדרה תיקייה לעורך הגרפים

    outputs = client.get("/api/dataviz/outputs").json()
    assert {o["name"]: o["folder"] for o in outputs["outputs"]} == {"a.mp4": str(new), "b.mp4": str(earlier)}   # קודם: בלי b
    assert outputs["save_to"]["folder"] == str(own / "outputs")
    assert client.get("/api/dataviz/media/horizontal/b.mp4").content == b"earlier"
    assert web_app._is_under_workspace(str(new / "a.mp4"))                      # "פתח תיקייה" - קודם: מחוץ לשורשים
    monkeypatch.setattr(web_app, "WEB_APP_EXPORT_DIRS", [])                     # בלי התיקיות של ה-workspace האמיתי
    web_app._mirror_export_dirs(str(tmp_path / "nas"))
    assert (tmp_path / "nas" / "dataviz" / "outputs" / "horizontal" / "a.mp4").read_bytes() == b"new"   # הגיבוי האוטומטי


def test_the_run_note_follows_the_dataviz_folder(folders, tmp_path):
    missing = str(tmp_path / "unplugged")
    export_dir.save_tool_root("dataviz", missing)
    note = web_app._export_fallback_note("dataviz_maker.py")
    assert note and missing in note                                             # קודם: לפי הכללית, שזמינה - בלי הודעה
