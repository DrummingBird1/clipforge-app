# tests/dataviz/test_dataviz_export_folder.py
#
# 23.10.2026, תיקיית הייצוא (utils/shared/export_dir.py) בעורך הגרפים: dataviz_maker.py כותב את התוצרים ל-<תיקייה>/dataviz/outputs/
# <כיוון> (קודם: תמיד workspace), והמסך מציג, מגיש ושולח לסטודיו גם משם וגם מ-workspace (תוצרים מלפני ההגדרה). כשהתיקייה לא
# זמינה - workspace, והמסך אומר למה. ‏--output_dir ממשיך לגבור (test_dataviz_maker.py).
import argparse
import contextlib
import importlib.util
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.episode import load_episode
from entrypoints import web_app
from entrypoints.web_app import app
from tests import PROJECT_ROOT
from tests.dataviz.test_web_app_dataviz import make_package
from tests.dataviz_helpers import write_episode

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture(scope="module")
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_export", os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def roots(tmp_path, monkeypatch):
    exports, workspace = tmp_path / "exports", tmp_path / "workspace"
    exports.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("CLIPFORGE_EXPORT_DIR", str(exports))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return exports, workspace


def _render_target(maker, monkeypatch, tmp_path):
    """הנתיב ש-render_episode מעביר למנוע (בלי לרנדר באמת)."""
    import dataviz
    from utils import render_lock
    targets = []

    def capture(episode, plan, out_path, **kwargs):
        targets.append(out_path)
        raise RuntimeError("בלי רינדור בטסט")
    monkeypatch.setattr(dataviz, "render_video", capture)
    monkeypatch.setattr(render_lock, "render_lock_if_needed", lambda **k: contextlib.nullcontext())
    folder = write_episode(tmp_path / "eps", overrides=SMALL, name="ep")
    args = argparse.Namespace(chart=None, workers=1, target="", output_dir="", captions=False, publish=False, no_publish=True)
    maker.render_episode(folder, "test", args, lambda d, t: None, {"files_created": 0, "errors": 0})
    return targets


def test_the_script_renders_into_the_export_folder(maker, roots, monkeypatch, tmp_path):
    exports, workspace = roots
    assert _render_target(maker, monkeypatch, tmp_path) == [str(exports / "dataviz" / "outputs" / "horizontal" / "ep_test.mp4")]   # קודם: workspace
    config = load_episode(write_episode(tmp_path / "eps2", overrides=SMALL, name="ep")).config
    assert maker.output_paths(config, "full", "W")[0] == os.path.join("W", "dataviz", "outputs", "horizontal")   # ‏--output_dir גובר


def test_an_unavailable_export_folder_falls_back_to_workspace(maker, roots, monkeypatch, tmp_path):
    exports, workspace = roots
    monkeypatch.setenv("CLIPFORGE_EXPORT_DIR", str(tmp_path / "unplugged"))
    assert _render_target(maker, monkeypatch, tmp_path) == [str(workspace / "dataviz" / "outputs" / "horizontal" / "ep_test.mp4")]
    save_to = client.get("/api/dataviz/outputs").json()["save_to"]
    assert save_to["folder"] == str(workspace / "dataviz" / "outputs")                                  # "נשמר ב-..." במסך
    assert save_to["root"] == str(tmp_path / "unplugged") and save_to["problem"]


def test_the_screen_lists_serves_and_hands_off_outputs_from_both_folders(roots):
    exports, workspace = roots
    make_package(exports, "new_ep")                                             # <תיקיית הייצוא>/dataviz/outputs/horizontal
    new = exports / "dataviz" / "outputs" / "horizontal"
    old = workspace / "dataviz" / "outputs" / "horizontal"
    old.mkdir(parents=True)
    (old / "old_ep.mp4").write_bytes(b"old video")
    (old / "new_ep.mp4").write_bytes(b"older copy")                             # אותו שם גם ב-workspace - מוצג ומוגש רק החדש

    outputs = client.get("/api/dataviz/outputs").json()
    assert {o["name"]: o["folder"] for o in outputs["outputs"]} == {"new_ep.mp4": str(new), "old_ep.mp4": str(old)}   # קודם: רק workspace
    assert outputs["save_to"] == {"folder": str(exports / "dataviz" / "outputs"), "root": str(exports), "problem": None}
    assert client.get("/api/dataviz/media/horizontal/new_ep.mp4").content == b"video"
    assert client.get("/api/dataviz/media/horizontal/old_ep.mp4").content == b"old video"
    assert [p["name"] for p in client.get("/api/dataviz/packages").json()] == ["new_ep"]

    resp = client.post("/api/dataviz/outputs/studio", json={"orientation": "horizontal", "name": "new_ep.mp4"})
    assert resp.status_code == 200
    assert resp.json()["folder"] == str(workspace / "dataviz" / "studio_handoff" / "horizontal" / "new_ep")   # ההעברה נשארת ב-workspace
    assert (new / "new_ep.mp4").read_bytes() == b"video"                         # התוצר עצמו לא זז
