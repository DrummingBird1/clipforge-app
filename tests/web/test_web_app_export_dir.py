# tests/web/test_web_app_export_dir.py
#
# 23.10.2026: תיקיית הייצוא בשרת - ההגדרה (GET/POST /api/export_dir), הגשה ופתיחה של תוצרים משם, הודעה בתחילת ריצה ובסופה
# כשהתיקייה לא זמינה, והגיבוי האוטומטי. ההגדרה בקובץ זמני לכל טסט, לא ב-data/ המשותף של הריצה.
import os
import queue

import pytest

from entrypoints import web_app
from entrypoints.web.routes import system as system_routes
from tests.web_app_support import client
from utils.shared import export_dir


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)


@pytest.fixture
def exports(tmp_path):
    folder = tmp_path / "exports"
    (folder / "studio" / "horizontal").mkdir(parents=True)
    return folder


def _log_lines():
    lines = []
    while True:
        try:
            lines.append(web_app.worker.log_queue.get_nowait()[0])
        except queue.Empty:
            return lines


def _run(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: None)
    _log_lines()
    assert client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)}).status_code == 200
    return _log_lines()


def test_the_default_is_workspace():
    data = client.get("/api/export_dir").json()
    assert data["root"] == "" and data["effective"] == web_app.WORKSPACE_DIR and data["problem"] is None


def test_saving_a_folder_and_going_back_to_the_default(exports):
    data = client.post("/api/export_dir", json={"root": str(exports)}).json()
    assert data["root"] == str(exports) and data["effective"] == str(exports) and data["free_bytes"] > 0
    assert client.post("/api/export_dir", json={"root": ""}).json()["effective"] == web_app.WORKSPACE_DIR


def test_a_missing_folder_is_offered_creation(tmp_path):
    target = tmp_path / "new" / "exports"
    refused = client.post("/api/export_dir", json={"root": str(target)})
    assert refused.status_code == 400 and refused.json()["missing"] is True and not target.exists()
    created = client.post("/api/export_dir", json={"root": str(target), "create": True})
    assert created.status_code == 200 and target.is_dir() and created.json()["root"] == str(target)


def test_folders_inside_data_or_the_code_are_refused():
    for bad in (os.path.join(web_app.DATA_DIR, "exports"), os.path.join(web_app.BASE_DIR, "src"), "relative\\exports"):
        assert client.post("/api/export_dir", json={"root": bad}).status_code == 400, bad
    assert client.get("/api/export_dir").json()["root"] == ""


def test_outputs_in_the_export_folder_can_be_shown_and_opened(exports, tmp_path, monkeypatch):
    video = exports / "studio" / "horizontal" / "a.mp4"
    video.write_bytes(b"x")
    assert not web_app._is_under_workspace(str(video))
    export_dir.save_root(str(exports))
    assert web_app._is_under_workspace(str(video))                       # thumbnail / stream של הסטודיו
    assert not web_app._is_under_workspace(str(tmp_path / "elsewhere.mp4"))
    opened = []
    monkeypatch.setattr(system_routes.os, "startfile", opened.append, raising=False)
    assert client.post("/api/open_folder", json={"path": str(video)}).status_code == 200
    assert opened == [os.path.dirname(str(video))]


def test_an_unavailable_folder_is_announced_at_the_start_and_the_end(tmp_path, monkeypatch):
    missing = str(tmp_path / "unplugged")
    export_dir.save_root(missing)
    started = _run(tmp_path, monkeypatch)
    assert any(missing in line and "workspace" in line for line in started), started
    web_app._on_task_finished({"returncode": 0})
    assert any(missing in line for line in _log_lines())
    assert web_app._finished_queue.get_nowait() == {"returncode": 0}


def test_no_note_when_the_folder_is_there(exports, tmp_path, monkeypatch):
    export_dir.save_root(str(exports))
    assert not any(str(exports) in line for line in _run(tmp_path, monkeypatch))


def test_auto_backup_also_copies_from_the_export_folder(exports, tmp_path):
    (exports / "studio" / "horizontal" / "a.mp4").write_bytes(b"x")
    export_dir.save_root(str(exports))
    web_app._mirror_export_dirs(str(tmp_path / "nas"))
    assert (tmp_path / "nas" / "studio" / "horizontal" / "a.mp4").exists()


# ---------- שלב 2: תיקייה לכלי ----------
def test_a_tool_folder_is_saved_and_reported(tmp_path):
    studio = tmp_path / "studio_out"
    studio.mkdir()
    assert client.post("/api/export_dir", json={"tool": "studio", "root": str(studio)}).status_code == 200
    tools = {t["tool"]: t for t in client.get("/api/export_dir").json()["tools"]}
    assert tools["studio"]["root"] == str(studio) and tools["studio"]["effective"] == str(studio)
    assert tools["timelapses"]["root"] == "" and tools["timelapses"]["effective"].endswith("timelapses")
    assert client.post("/api/export_dir", json={"tool": "nope", "root": str(studio)}).status_code == 400
    assert client.post("/api/export_dir", json={"tool": "studio", "root": ""}).status_code == 200
    assert export_dir.load_tool_root("studio") == ""


def test_outputs_in_a_tool_folder_can_be_shown_and_backed_up(tmp_path):
    studio = tmp_path / "studio_out"
    (studio / "horizontal").mkdir(parents=True)
    (studio / "horizontal" / "b.mp4").write_bytes(b"x")
    export_dir.save_tool_root("studio", str(studio))
    assert web_app._is_under_workspace(str(studio / "horizontal" / "b.mp4"))
    web_app._mirror_export_dirs(str(tmp_path / "nas"))
    assert (tmp_path / "nas" / "studio" / "horizontal" / "b.mp4").exists()


def test_the_run_note_follows_the_folder_of_the_tool_that_runs(exports, tmp_path, monkeypatch):
    export_dir.save_root(str(exports))
    missing = str(tmp_path / "unplugged_studio")
    export_dir.save_tool_root("studio", missing)
    assert any(missing in line for line in _run(tmp_path, monkeypatch))   # video_editor.py - התיקייה של הסטודיו
    assert web_app._export_fallback_note("timelapse_maker.py") is None    # לטיימלאפס - הכללית, והיא זמינה
