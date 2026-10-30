# tests/dataviz/test_dataviz_outputs_layout.py
#
# 19.10.2026: תוצרי עורך הגרפים ב-workspace/dataviz/outputs/<כיוון> (קודם workspace/<כיוון>/dataviz), והתיקייה לסטודיו
# ב-workspace/dataviz/studio_handoff/<כיוון>. עד שסקריפט ההעברה רץ, תוצר ישן בתיקייה הישנה עדיין מופיע, מתנגן ונשלח לסטודיו.
import os

from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz.test_web_app_dataviz import make_package

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def test_old_outputs_are_still_listed_served_and_handed_to_the_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path))
    old = tmp_path / "horizontal" / "dataviz"
    new = tmp_path / "dataviz" / "outputs" / "horizontal"
    make_package(tmp_path, "old_ep")                     # חבילה אמיתית, ואז לתיקייה הישנה - כמו תוצר מלפני ההעברה
    old.mkdir(parents=True)
    for name in os.listdir(new):
        os.replace(new / name, old / name)
    (old / "old_ep.mp4").write_bytes(b"old video")
    (new / "new_ep.mp4").write_bytes(b"new video")

    outputs = client.get("/api/dataviz/outputs").json()
    assert {o["name"] for o in outputs["outputs"]} == {"old_ep.mp4", "new_ep.mp4"}
    assert outputs["folders"]["horizontal"] == str(new)                     # "פתח תיקייה" - החדשה
    assert client.get("/api/dataviz/media/horizontal/old_ep.mp4").content == b"old video"
    assert client.get("/api/dataviz/media/horizontal/new_ep.mp4").content == b"new video"
    assert [p["name"] for p in client.get("/api/dataviz/packages").json()] == ["old_ep"]

    resp = client.post("/api/dataviz/outputs/studio", json={"orientation": "horizontal", "name": "old_ep.mp4"})
    assert resp.status_code == 200
    assert resp.json()["folder"] == str(tmp_path / "dataviz" / "studio_handoff" / "horizontal" / "old_ep")
    assert (old / "old_ep.mp4").read_bytes() == b"old video"                # התוצר עצמו לא זז
