# tests/dataviz/test_dataviz_history.py
#
# 20.10.2026: היסטוריית גרסאות לפרק - תמונת מצב בכל שמירה (כולל המצב שלפני השמירה הראשונה), בלי כפילויות, תקרה,
# השוואה לעכשיו ושחזור של קובץ השינויים בלבד (config.yaml לא נכתב; השחזור נכנס להיסטוריה).
import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.web import episodes as de
from dataviz.web import history
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
    return {"data": str(data), "folder": write_episode(data / "dataviz_episodes", name="tiny")}


def _save(env, **fields):
    de.update_override_fields(env["data"], "tiny", fields, [])


def test_every_save_is_a_version_and_the_same_state_is_not_repeated(env):
    assert history.versions(env["data"], "tiny")["versions"] == []
    _save(env, title="ראשון")
    _save(env, title="ראשון")                   # אותו מצב - לא עוד גרסה
    _save(env, title="שני")
    rows = history.versions(env["data"], "tiny")["versions"]
    assert [r["note"] for r in rows] == ["", "", "לפני השמירה הראשונה"]     # מהחדשה לישנה
    assert [r["changes"] for r in rows] == [0, 1, 1]
    assert history.diff(env["data"], "tiny", rows[1]["id"])["changes"] == [{"path": "title", "now": "שני", "then": "ראשון"}]


def test_restore_writes_only_the_overrides_and_is_itself_a_version(env):
    config = hashlib.md5(open(os.path.join(env["folder"], "config.yaml"), "rb").read()).digest()
    _save(env, title="ראשון")
    _save(env, title="שני", subtitle="חדש")
    first = history.versions(env["data"], "tiny")["versions"][1]
    resp = client.post("/api/dataviz/history/restore", json={"episode": "tiny", "id": first["id"]})
    assert resp.status_code == 200
    assert de.load_overrides_for_path(env["folder"]) == {"title": "ראשון"}
    assert hashlib.md5(open(os.path.join(env["folder"], "config.yaml"), "rb").read()).digest() == config
    rows = client.get("/api/dataviz/history", params={"episode": "tiny"}).json()["versions"]
    assert len(rows) == 4 and rows[0]["changes"] == 0 and rows[1]["changes"] == 2          # אפשר לחזור מהשחזור


def test_config_yaml_changes_are_reported_not_restored(env):
    _save(env, title="ראשון")
    with open(os.path.join(env["folder"], "config.yaml"), "a", encoding="utf-8") as f:
        f.write("\n# נערך ביד\n")
    version = history.versions(env["data"], "tiny")["versions"][0]
    assert version["config_changed"] is True
    assert history.diff(env["data"], "tiny", version["id"])["config_changed"] is True


def test_the_count_is_capped_and_bad_ids_are_refused(env, monkeypatch):
    monkeypatch.setattr(history, "MAX_VERSIONS", 3)
    for i in range(6):
        _save(env, title=f"גרסה {i}")
    assert len(os.listdir(history.history_dir(env["data"], "tiny"))) == 3
    assert client.get("/api/dataviz/history/diff", params={"episode": "tiny", "id": "../tiny"}).status_code == 404
    assert client.post("/api/dataviz/history/restore", json={"episode": "tiny", "id": "nope"}).status_code == 404
    assert client.get("/api/dataviz/history", params={"episode": "nope"}).status_code == 404


def test_a_snapshot_too_big_is_skipped_without_breaking_the_save(env, monkeypatch):
    monkeypatch.setattr(history, "MAX_BYTES", 50)
    _save(env, title="ראשון")
    assert de.load_overrides_for_path(env["folder"]) == {"title": "ראשון"}
    assert history.versions(env["data"], "tiny")["versions"] == []
