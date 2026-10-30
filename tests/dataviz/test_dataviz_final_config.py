# tests/test_dataviz_final_config.py
#
# עורך הגרפים (19.10.2026): "ההגדרות הסופיות" - מה שהרינדור יקבל בפועל (config.yaml + שינויים מהדפדפן + ברירות המחדל),
# ולכל הגדרה מאיפה היא באה. לקריאה בלבד: שום קובץ לא נכתב.
import hashlib


import pytest
import yaml
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    write_episode(data / "dataviz_episodes", overrides={"title": "מהקובץ", "subtitle": "גם מהקובץ"}, name="alarms")
    return data


def _tree(root):
    return sorted((str(p.relative_to(root)), hashlib.md5(p.read_bytes()).hexdigest()) for p in root.rglob("*") if p.is_file())


def test_final_config_merges_the_three_layers_and_says_where_each_value_comes_from(env):
    saved = client.post("/api/dataviz/episodes/override", json={"episode": "alarms", "set": {"subtitle": "מהדפדפן"}})
    assert saved.status_code == 200
    before = _tree(env)
    body = client.get("/api/dataviz/episodes/final_config", params={"episode": "alarms"}).json()
    rows = {row["path"]: row for row in body["rows"]}
    assert rows["subtitle"] == {"path": "subtitle", "value": "מהדפדפן", "source": "override"}
    assert rows["title"] == {"path": "title", "value": "מהקובץ", "source": "file"}
    assert rows["end_screen.seconds"]["source"] == "default"
    final = yaml.safe_load(body["yaml"])
    assert final["subtitle"] == "מהדפדפן" and final["title"] == "מהקובץ" and "base_dir" not in final
    assert body["files"]["override"].replace("\\", "/") == "dataviz_overrides/alarms.json"
    assert _tree(env) == before                                     # לקריאה בלבד


def test_final_config_of_a_missing_episode_is_404(env):
    assert client.get("/api/dataviz/episodes/final_config", params={"episode": "nope"}).status_code == 404
    assert client.get("/api/dataviz/episodes/final_config", params={"episode": "../x"}).status_code == 404
