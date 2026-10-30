# tests/dataviz/test_dataviz_story_templates.py
#
# 20.10.2026: אשף תבניות סיפור - מרוץ / מגמה / השוואה של שניים / לפני-אחרי, מהשאלה. preview מראה לפני/אחרי לכל הגדרה
# בלי לכתוב; apply כותב לקובץ השינויים (config.yaml לא משתנה).
import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.web import episodes as de
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
    folder = write_episode(data / "dataviz_episodes", name="tiny")
    return {"data": data, "folder": folder}


def _post(action, **body):
    return client.post(f"/api/dataviz/story_templates/{action}", json={"episode": "tiny", **body})


def test_preview_shows_before_and_after_without_writing(env):
    assert [t["id"] for t in client.get("/api/dataviz/story_templates").json()["templates"]] == ["race", "trend", "compare", "before_after"]
    resp = _post("preview", template="trend", question="איך זה השתנה?")
    changes = {c["path"]: c for c in resp.json()["changes"]}
    assert changes["chart"]["before"] == "bar_race" and changes["chart"]["after"] == "line_race"
    assert changes["intro.question"]["before"] == "מי מנצח?" and changes["intro.question"]["after"] == "איך זה השתנה?"
    assert changes["chart"]["label"] == "סוג תרשים"
    assert de.load_overrides_for_path(env["folder"]) == {}                          # רק תצוגה


def test_apply_writes_the_changes_to_the_override_only(env):
    config = open(os.path.join(env["folder"], "config.yaml"), "rb").read()
    assert _post("apply", template="compare", pick=["2020", "2023"]).status_code == 200
    saved = de.load_overrides_for_path(env["folder"])
    assert saved["chart"] == "line_race" and saved["focus"]["entities"] == ["2020", "2023"] and saved["outro"]["title"] == "2020 מול 2023"
    assert hashlib.md5(open(os.path.join(env["folder"], "config.yaml"), "rb").read()).digest() == hashlib.md5(config).digest()
    assert _post("preview", template="compare", pick=["2020", "2023"]).json()["changes"] == []   # כבר הוחל - אין מה לשנות


def test_before_after_adds_periods_and_a_pause_on_the_date(env):
    _post("apply", template="before_after", split="2022-06-01", question="מה השתנה ביוני 2022?")
    story = de.load_overrides_for_path(env["folder"])["story"]
    assert [p["label"] for p in story["periods"]] == ["לפני", "אחרי"] and story["periods"][1]["start"] == "2022-06-01"
    assert story["pauses"] == [{"date": "2022-06-01", "text": "מה השתנה ביוני 2022?"}]
    assert _post("preview", template="before_after", split="1990-01-01").status_code == 400     # מחוץ לפרק
    assert _post("preview", template="before_after").status_code == 400
    assert _post("preview", template="nope").status_code == 404


def test_suggest_proposes_a_type_without_writing(env):
    # 21.10.2026: כלי סיפור אחד - נפתח על הסוג שהעורך החכם מציע (ניתוח של קובצי הפרק, או מה שנשמר ברשומה), ואפשר להחליף
    before = {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])}
    found = client.get("/api/dataviz/story_suggest", params={"episode": "tiny"}).json()
    assert found["value"] in ("race", "trend", "compare", "before_after") and found["reason"] and found["source"] == "analysis"
    assert {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == before
    assert not os.path.exists(os.path.join(env["data"], "dataviz_overrides", "tiny.json"))
    from dataviz.smart import create
    create.save_record(str(env["data"]), "tiny", {"episode": "tiny", "story_type": {"value": "compare", "confidence": 0.7, "reason": "שתי סדרות"}})
    assert client.get("/api/dataviz/story_suggest", params={"episode": "tiny"}).json() == {"value": "compare", "confidence": 0.7, "reason": "שתי סדרות", "source": "record"}
    assert client.get("/api/dataviz/story_suggest", params={"episode": "nope"}).status_code == 404
