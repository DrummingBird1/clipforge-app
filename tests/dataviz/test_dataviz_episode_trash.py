# tests/dataviz/test_dataviz_episode_trash.py
#
# 20.10.2026: "🗑️ מחק פרק" - הפרק, השינויים שלו מהדפדפן (dataviz_overrides/<שם>.json ו-<שם>/), המטמון והרשומות שלו
# (הסתרה, תגיות, תור) עוברים לסל של עורך הגרפים data/dataviz_trash/<שם>_<זמן>/ עם manifest - שום דבר לא נמחק.
# "♻️ שחזר" מחזיר הכל (ומסרב לשם תפוס), פרק שרץ או בתור לא נמחק, שם עם ../ נדחה, ו"רוקן סל" רק עם אישור מפורש.
# התוצרים ב-workspace לא נוגעים.
import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web.routes import dataviz as routes
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _tree(root):
    return sorted((os.path.relpath(os.path.join(d, f), root), hashlib.md5(open(os.path.join(d, f), "rb").read()).hexdigest())
                  for d, _dirs, files in os.walk(root) for f in files)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setattr(web_app.worker, "is_running", False)
    routes._RUN_EPISODES.clear()
    write_episode(data / "dataviz_episodes", name="climate")
    write_episode(data / "dataviz_episodes", name="other")
    client.post("/api/dataviz/episodes/override", json={"episode": "climate", "set": {"subtitle": "מהדפדפן"}})
    (data / "dataviz_overrides" / "climate").mkdir(parents=True)
    (data / "dataviz_overrides" / "climate" / "extra.csv").write_text("year,n\n2020,1\n", encoding="utf-8")
    (data / "dataviz_cache" / "climate").mkdir(parents=True)
    (data / "dataviz_cache" / "climate" / "state.json").write_text("{}", encoding="utf-8")
    de.set_hidden(str(data), "climate", True)
    de.set_tags(str(data), "climate", ["אקלים"], "מדע")
    de.set_tags(str(data), "other", ["אחר"], "")
    (data / "dataviz_queue.json").write_text(json.dumps({"episodes": [{"name": "climate", "state": "done", "pct": 100},
                                                                       {"name": "other", "state": "done", "pct": 100}]}), encoding="utf-8")
    outputs = workspace / "dataviz" / "outputs" / "horizontal"
    outputs.mkdir(parents=True)
    (outputs / "climate.mp4").write_bytes(b"video")
    return {"data": data, "workspace": workspace}


def test_delete_moves_everything_to_the_trash_with_a_manifest_and_restore_brings_it_back(env):
    data = env["data"]
    before_episode = _tree(data / "dataviz_episodes" / "climate")
    before_workspace = _tree(env["workspace"])
    resp = client.post("/api/dataviz/episodes/delete", json={"episode": "climate"})
    assert resp.status_code == 200, resp.text
    trash = data / "dataviz_trash" / resp.json()["trash_id"]
    assert resp.json()["trash_id"].startswith("climate_")
    assert not (data / "dataviz_episodes" / "climate").exists() and not (data / "dataviz_overrides" / "climate.json").exists()
    assert not (data / "dataviz_overrides" / "climate").exists() and not (data / "dataviz_cache" / "climate").exists()
    assert _tree(trash / "episode") == before_episode                                   # הכל עבר, כמו שהוא
    assert (trash / "overrides" / "extra.csv").is_file() and (trash / "cache" / "state.json").is_file()
    manifest = json.loads((trash / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "climate" and manifest["hidden"] is True and manifest["tags"] == {"tags": ["אקלים"], "folder": "מדע"}
    assert {i["from"] for i in manifest["items"]} == {"dataviz_episodes/climate", "dataviz_overrides/climate.json",
                                                      "dataviz_overrides/climate", "dataviz_cache/climate",
                                                      "dataviz_history/climate"}   # 20.10.2026: גם היסטוריית הגרסאות
    assert not (data / "dataviz_history" / "climate").exists() and any((trash / "history").iterdir())
    assert manifest["queue"] == [{"name": "climate", "state": "done", "pct": 100}]
    assert "climate" not in de.load_hidden(str(data)) and "climate" not in de.load_tags(str(data)) and "other" in de.load_tags(str(data))
    assert [e["name"] for e in json.loads((data / "dataviz_queue.json").read_text(encoding="utf-8"))["episodes"]] == ["other"]
    assert _tree(env["workspace"]) == before_workspace                                  # התוצרים לא נוגעים
    listed = client.get("/api/dataviz/trash").json()["items"]
    assert [(i["id"], i["name"], i["taken"]) for i in listed] == [(trash.name, "climate", False)]
    # שחזור
    restored = client.post("/api/dataviz/trash/restore", json={"id": trash.name})
    assert restored.status_code == 200, restored.text
    assert _tree(data / "dataviz_episodes" / "climate") == before_episode and not trash.exists()
    assert (data / "dataviz_overrides" / "climate" / "extra.csv").is_file() and (data / "dataviz_cache" / "climate" / "state.json").is_file()
    assert de.load_overrides_for_path(str(data / "dataviz_episodes" / "climate")) == {"subtitle": "מהדפדפן"}
    assert any((data / "dataviz_history" / "climate").iterdir())                        # ההיסטוריה חזרה עם הפרק
    assert "climate" in de.load_hidden(str(data)) and de.load_tags(str(data))["climate"] == {"tags": ["אקלים"], "folder": "מדע"}
    assert client.get("/api/dataviz/trash").json()["items"] == []


def test_two_deletes_of_the_same_name_never_share_a_trash_folder_and_restore_refuses_a_taken_name(env):
    data = env["data"]
    first = client.post("/api/dataviz/episodes/delete", json={"episode": "climate"}).json()["trash_id"]
    write_episode(data / "dataviz_episodes", overrides={"title": "חדש באותו שם"}, name="climate")
    second = client.post("/api/dataviz/episodes/delete", json={"episode": "climate"}).json()["trash_id"]
    assert first != second
    write_episode(data / "dataviz_episodes", overrides={"title": "שלישי"}, name="climate")
    before = _tree(data / "dataviz_episodes" / "climate")
    resp = client.post("/api/dataviz/trash/restore", json={"id": first})
    assert resp.status_code == 409 and _tree(data / "dataviz_episodes" / "climate") == before
    assert (data / "dataviz_trash" / first / "manifest.json").is_file()                 # נשאר בסל, שלם
    assert {i["id"]: i["taken"] for i in client.get("/api/dataviz/trash").json()["items"]} == {first: True, second: True}


def test_an_episode_that_is_running_or_queued_is_not_deleted(env, monkeypatch):
    data = env["data"]
    monkeypatch.setattr(web_app.worker, "is_running", True)
    routes._RUN_EPISODES.update({"climate"})
    assert client.post("/api/dataviz/episodes/delete", json={"episode": "climate"}).status_code == 409
    routes._RUN_EPISODES.clear()
    (data / "dataviz_queue.json").write_text(json.dumps({"episodes": [{"name": "other", "state": "pending", "pct": 0}]}), encoding="utf-8")
    assert client.post("/api/dataviz/episodes/delete", json={"episode": "other"}).status_code == 409
    assert (data / "dataviz_episodes" / "climate").is_dir() and (data / "dataviz_episodes" / "other").is_dir()
    assert client.post("/api/dataviz/episodes/delete", json={"episode": "climate"}).status_code == 200   # לא בריצה ולא בתור


@pytest.mark.parametrize("name", ["../dataviz_episodes/climate", "..", "climate/../other", "..\\climate", "", "nope"])
def test_a_name_outside_the_episodes_is_refused(env, name):
    before = _tree(env["data"])
    assert client.post("/api/dataviz/episodes/delete", json={"episode": name}).status_code == 404
    assert _tree(env["data"]) == before


@pytest.mark.parametrize("trash_id", ["..", "../dataviz_episodes", "nope", ""])
def test_restore_only_takes_a_folder_in_the_trash(env, trash_id):
    client.post("/api/dataviz/episodes/delete", json={"episode": "other"})
    assert client.post("/api/dataviz/trash/restore", json={"id": trash_id}).status_code == 404


def test_emptying_the_trash_needs_an_explicit_confirmation(env):
    data = env["data"]
    client.post("/api/dataviz/episodes/delete", json={"episode": "climate"})
    assert client.post("/api/dataviz/trash/empty", json={}).status_code == 400
    assert len(os.listdir(data / "dataviz_trash")) == 1
    resp = client.post("/api/dataviz/trash/empty", json={"confirm": "empty"})
    assert resp.status_code == 200 and resp.json()["removed"] == 1 and os.listdir(data / "dataviz_trash") == []
    assert (data / "dataviz_episodes" / "other").is_dir()
