# tests/dataviz/test_dataviz_batch.py
#
# 20.10.2026: דוח תמונות - כמה פריימים לכל פרק בתיקייה (טיוטה / תיקייה אחרת / הפרקים של האפליקציה לפי תיקייה בתגיות),
# פרק שבור נרשם בדוח והשאר ממשיכים, תיקיות המקור לא משתנות, הדוח בתיקייה חדשה, וקבצי הדוח מוגשים רק מתוכה.
import hashlib
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from dataviz.web import batch
from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


def _tree(root):
    out = {}
    for folder, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            out[os.path.relpath(path, root)] = hashlib.md5(open(path, "rb").read()).hexdigest()
    return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    staging = workspace / "dataviz" / "staging"
    staging.mkdir(parents=True)
    write_episode(staging, overrides={"title": "טיוטה טובה", **VIDEO}, name="good")
    broken = write_episode(staging, overrides=VIDEO, name="broken")
    os.remove(os.path.join(broken, "alarms.csv"))                                         # הנתונים חסרים
    (staging / "notes").mkdir()                                                           # לא פרק
    write_episode(data / "dataviz_episodes", overrides=VIDEO, name="a")
    write_episode(data / "dataviz_episodes", overrides=VIDEO, name="b")
    de.set_tags(str(data), "b", ["x"], "מדע")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return {"data": str(data), "workspace": str(workspace), "staging": str(staging)}


def test_finding_the_episodes_of_each_source(env):
    assert [e["name"] for e in batch.find_episodes(env["data"], env["workspace"], "staging")] == ["broken", "good"]
    assert [e["name"] for e in batch.find_episodes(env["data"], env["workspace"], "app")] == ["a", "b"]
    assert [e["name"] for e in batch.find_episodes(env["data"], env["workspace"], "app", folder="מדע")] == ["b"]
    assert [e["name"] for e in batch.find_episodes(env["data"], env["workspace"], "folder", path=env["staging"])] == ["broken", "good"]
    with pytest.raises(de.EpisodeError):
        batch.find_episodes(env["data"], env["workspace"], "folder", path=os.path.join(env["staging"], "nope"))


def test_a_report_with_images_per_episode_and_the_broken_one_listed(env, tmp_path):
    before = _tree(env["staging"])
    out = tmp_path / "out"
    out.mkdir()
    episodes = batch.find_episodes(env["data"], env["workspace"], "staging")
    report = batch.run(env["data"], env["workspace"], episodes, str(out))
    rows = {r["name"]: r for r in report["episodes"]}
    assert report["ok"] == 1 and report["failed"] == 1 and rows["broken"]["error"]
    assert [i["file"] for i in rows["good"]["images"]] == ["good_1.png", "good_2.png", "good_3.png"]
    assert rows["good"]["title"] == "טיוטה טובה"
    assert sorted(os.listdir(out)) == ["good_1.png", "good_2.png", "good_3.png", "index.html", "report.json"]
    page = (out / "index.html").read_text(encoding="utf-8")
    assert 'src="good_2.png"' in page and "❌" in page
    assert _tree(env["staging"]) == before                                               # המקור רק נקרא


def test_the_background_run_and_the_report_files(env):
    resp = client.post("/api/dataviz/batch/start", json={"source": "app", "folder": "מדע"})
    assert resp.status_code == 200 and resp.json()["total"] == 1
    deadline = time.time() + 120
    while client.get("/api/dataviz/batch/status").json()["running"] and time.time() < deadline:
        time.sleep(0.2)
    status = client.get("/api/dataviz/batch/status").json()
    assert status["ok"] == 1 and status["names"] == ["b"]
    batch_id = status["id"]
    assert os.path.isdir(os.path.join(batch.batch_root(env["workspace"]), batch_id))
    page = client.get(f"/api/dataviz/batch/report/{batch_id}/index.html")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert client.get(f"/api/dataviz/batch/report/{batch_id}/b_1.png").headers["content-type"] == "image/png"
    assert json.loads(client.get(f"/api/dataviz/batch/report/{batch_id}/report.json").content)["ok"] == 1
    assert client.get(f"/api/dataviz/batch/report/{batch_id}/..%5Csecret.png").status_code == 404
    assert client.get(f"/api/dataviz/batch/report/{batch_id}/notes.txt").status_code == 404
    assert client.post("/api/dataviz/batch/start", json={"source": "zap"}).status_code == 400
    sources = client.get("/api/dataviz/batch/sources").json()
    assert sources["staging"] == env["staging"] and sources["folders"] == ["מדע"]
