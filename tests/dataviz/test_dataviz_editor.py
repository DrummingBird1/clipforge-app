# tests/dataviz/test_dataviz_editor.py - גל 39: עורך ההגדרות המלא של פרק - שינוי שדה-שדה בקובץ override (config.yaml
# לא משתנה), אירועים, צבעים, ישויות, "מה שונה", הטופס הבסיסי שלא מוחק שינויים מתקדמים, וטיוטה בתצוגה החיה.
import hashlib
import json
import os


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    folder = write_episode(data / "dataviz_episodes", name="tiny")
    with open(os.path.join(folder, "config.yaml"), "rb") as f:
        original = hashlib.md5(f.read()).hexdigest()
    return {"data": str(data), "folder": folder, "config_md5": original}


def _config_unchanged(env):
    with open(os.path.join(env["folder"], "config.yaml"), "rb") as f:
        return hashlib.md5(f.read()).hexdigest() == env["config_md5"]


def _overrides(env):
    return de.load_overrides_for_path(env["folder"])


def test_fields_are_set_and_unset_one_by_one(env):
    de.update_override_fields(env["data"], "tiny", {"timing.step": 0.004, "intro.title": "שלום"}, [])
    assert _overrides(env) == {"timing": {"step": 0.004}, "intro": {"title": "שלום"}}
    de.update_override_fields(env["data"], "tiny", {"records.enabled": False}, ["timing.step"])
    assert _overrides(env) == {"intro": {"title": "שלום"}, "records": {"enabled": False}}
    de.update_override_fields(env["data"], "tiny", {}, ["intro.title", "records.enabled"])
    assert _overrides(env) == {} and not os.path.exists(de.overrides_path(env["data"], "tiny"))
    assert _config_unchanged(env)


def test_bad_values_are_refused_and_nothing_is_written(env):
    for change in ({"timing.step": 7}, {"video.width": 1281}, {"colors": {"a": "red"}}, {"events": [{"date": "x", "label": "y"}]},
                   {"theme_overrides.categorical": ["#123456"]}, {"chart": "rocket_race"}, {"entities.exclude": "a"}):
        with pytest.raises(de.EpisodeError):
            de.update_override_fields(env["data"], "tiny", change, [])
    assert _overrides(env) == {}
    with pytest.raises(de.EpisodeError) as e:
        de.update_override_fields(env["data"], "nope", {"timing.step": 0.01}, [])
    assert e.value.status == 404


def test_events_colors_palette_and_entity_rules(env):
    de.update_override_fields(env["data"], "tiny", {
        "events": [{"date": "2023-01-02", "label": " ב "}, {"date": "2022-05-01", "label": "א"}],
        "colors": {"2023": "#AABBCC"},
        "theme_overrides.accent": "#112233",
        "theme_overrides.categorical": ["#111111", "#222222", "#333333"],
        "entities.aliases": {"2021": "שנה ראשונה", "2022": "2022"},
        "entities.exclude": ["2019", "2019"],
    }, [])
    saved = _overrides(env)
    assert saved["events"] == [{"date": "2022-05-01", "label": "א"}, {"date": "2023-01-02", "label": "ב"}]
    assert saved["colors"] == {"2023": "#aabbcc"}
    assert saved["theme_overrides"] == {"accent": "#112233", "categorical": ["#111111", "#222222", "#333333"]}
    assert saved["entities"] == {"aliases": {"2021": "שנה ראשונה"}, "exclude": ["2019"]}
    data = de.editor_data(env["data"], "tiny")
    assert data["events_source"] == "override" and data["events"][0]["label"] == "א"
    assert data["theme"]["accent"] == "#112233" and data["theme"]["overridden"] == ["accent", "categorical"]
    paths = {c["path"] for c in data["changes"]}
    assert {"events", "colors", "theme_overrides.accent", "entities.aliases", "entities.exclude"} <= paths


def test_the_basic_form_keeps_advanced_changes(env):
    de.update_override_fields(env["data"], "tiny", {"timing.step": 0.004}, [])
    de.set_overrides(env["data"], "tiny", {"title": "חדש", "theme": "dark"})
    assert _overrides(env) == {"timing": {"step": 0.004}, "title": "חדש", "theme": "dark"}
    de.set_overrides(env["data"], "tiny", None)   # "איפוס לברירת המקור" - הכל
    assert _overrides(env) == {}


def test_editor_route_override_route_and_schema(env):
    data = client.get("/api/dataviz/episodes/editor", params={"episode": "tiny"}).json()
    assert [g["id"] for g in data["groups"]][:3] == ["basic", "texts", "pacing"]   # גל 59: "⭐ בסיסי" ראשון
    assert data["entities"] and data["date_range"][0] < data["date_range"][1]
    assert data["events_source"] == "file" and data["events_file"] == "events.csv"
    resp = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {"notes": "שורה א\nשורה ב"}})
    assert resp.status_code == 200 and _overrides(env) == {"notes": ["שורה א", "שורה ב"]}
    bad = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {"video.fps": 1000}})
    assert bad.status_code == 400 and "פריימים" in bad.json()["error"]
    assert client.get("/api/dataviz/config_schema").json()["properties"]["timing"]["type"] == "object"
    assert _config_unchanged(env)


def test_draft_changes_show_in_the_preview_without_saving(env):
    base = {"episode": "tiny", "pos": 0.02, "scale": 0.2}
    plain = client.get("/api/dataviz/preview_frame", params=base).content
    draft = client.get("/api/dataviz/preview_frame", params={**base, "draft": json.dumps({"intro.title": "פתיח אחר"})})
    assert draft.status_code == 200 and draft.content != plain
    assert client.get("/api/dataviz/preview_frame", params={**base, "draft": json.dumps({"timing.step": 9})}).status_code == 400
    assert client.get("/api/dataviz/preview_frame", params={**base, "draft": "[1]"}).status_code == 400
    assert _overrides(env) == {}
