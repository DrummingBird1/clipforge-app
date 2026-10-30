# tests/web/test_web_app_outputs.py
#
# 23.10.2026: מסך "תוצרים" בשרת - GET /api/outputs ו-POST /api/outputs/studio (routes/outputs.py). workspace ותיקיית
# הייצוא זמניים לכל טסט.
import os

import pytest

from dataviz.web import handoff as dataviz_handoff
from tests.web_app_support import client, web_app
from utils.shared import export_dir


@pytest.fixture(autouse=True)
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return workspace


def _video(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_the_list_has_every_tools_outputs(ws):
    video = _video(ws / "studio" / "horizontal" / "a.mp4")
    data = client.get("/api/outputs").json()
    assert [(i["name"], i["tool"], i["path"]) for i in data["outputs"]] == [("a.mp4", "studio", os.path.normpath(video))]
    assert data["tools"] == ["studio", "timelapses", "highlight_reels", "dataviz", "rocket_shorts"]


def test_open_in_studio_gives_the_output_a_folder_of_its_own(ws):
    video = _video(ws / "studio" / "horizontal" / "a.mp4")
    resp = client.post("/api/outputs/studio", json={"path": str(video)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["folder"] == str(ws / "studio" / "studio_handoff" / "horizontal" / "a") and data["file"] == "a.mp4"
    assert data["state"] in ("linked", "copied") and (ws / "studio" / "studio_handoff" / "horizontal" / "a" / "a.mp4").is_file()
    assert video.read_bytes() == b"x"                                                          # התוצר עצמו לא זז
    assert [i["name"] for i in client.get("/api/outputs").json()["outputs"]] == ["a.mp4"]      # והעותק לסטודיו לא ברשימה
    assert client.post("/api/outputs/studio", json={"path": str(video)}).json()["state"] == "ready"


def test_a_dataviz_output_opens_in_the_same_folder_as_from_its_own_screen(ws):
    video = _video(ws / "dataviz" / "outputs" / "vertical" / "ep.mp4")
    data = client.post("/api/outputs/studio", json={"path": str(video)}).json()
    assert data["folder"] == os.path.join(dataviz_handoff.studio_root(str(ws), "vertical"), "ep")


def test_an_output_in_the_export_folder_opens_from_a_workspace_folder(ws, tmp_path):
    exports = tmp_path / "exports"
    video = _video(exports / "timelapses" / "vertical" / "t.mp4")
    export_dir.save_root(str(exports))
    data = client.post("/api/outputs/studio", json={"path": str(video)}).json()
    assert data["folder"] == str(ws / "timelapses" / "studio_handoff" / "vertical" / "t")


def test_only_listed_outputs_open_in_studio(ws, tmp_path):
    outside = _video(tmp_path / "outside.mp4")
    _video(ws / "studio" / "horizontal" / "a.mp4")
    assert client.post("/api/outputs/studio", json={"path": str(outside)}).status_code == 404
    assert client.post("/api/outputs/studio", content=b"not json", headers={"Content-Type": "application/json"}).status_code == 404
    assert client.post("/api/outputs/studio", json=["a"]).status_code == 404
    foreign = client.post("/api/outputs/studio", json={"path": str(ws / "studio" / "horizontal" / "a.mp4")},
                          headers={"origin": "https://evil.example.com"})
    assert foreign.status_code == 403
    assert not (ws / "studio" / "studio_handoff").exists()
