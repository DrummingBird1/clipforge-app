# tests/dataviz/test_dataviz_smart_create.py
#
# 20.10.2026: עורך הגרפים החכם, פריט 14 - "📂→🎬 תיקייה ← טיוטת פרק": פרק חדש מתיקייה (רק הקבצים הרלוונטיים מועתקים,
# המקור לא משתנה, config.yaml = המיפוי בלבד), וכל בחירה עריכתית כטיוטה בקובץ השינויים עם 🤖 סיבה וביטחון - בהגדרות
# הסופיות, בביטול לכל בחירה, ובשאלה אחת כשהביטחון נמוך. אירועים בלי שורת כותרת נכנסים לטיוטה.
import hashlib
import os

import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.smart import create
from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web_app import app

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _tree(root):
    return {os.path.relpath(os.path.join(d, n), root): hashlib.md5(open(os.path.join(d, n), "rb").read()).hexdigest()
            for d, _dirs, files in os.walk(root) for n in files}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    source = tmp_path / "medals"
    source.mkdir()
    lines = ["year,country,total_medals"]
    for year in range(1980, 1996):
        lines += [f"{year},צרפת,20", f"{year},יפן,{5 + (60 if year >= 1988 else 0)}", f"{year},איטליה,8", f"{year},קנדה,3"]
    (source / "medals_per_games.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (source / "medal_table_raw_UNUSED.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (source / "milestones.csv").write_text("1988-09-17,פתיחת אולימפיאדת סיאול\n1992-07-25,ברצלונה\n", encoding="utf-8")
    (source / "SOURCES.md").write_text("# SOURCES\n- **Source:** Olympedia, medal tables.\n", encoding="utf-8")
    return {"data": str(data), "source": str(source)}


def test_a_folder_becomes_an_episode_with_an_explained_draft(env):
    before = _tree(env["source"])
    resp = client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_auto"})
    assert resp.status_code == 200, resp.text
    record = resp.json()
    folder = de.episode_folder(env["data"], "medals_auto")
    assert sorted(os.listdir(folder)) == ["SOURCES.md", "config.yaml", "medals_per_games.csv", "milestones.csv"]   # בלי הגולמי
    config = yaml.safe_load(open(os.path.join(folder, "config.yaml"), encoding="utf-8"))
    assert set(config) == {"title", "sources"} and config["sources"][0]["value"] == {"column": "total_medals"}
    overrides = de.load_overrides_for_path(folder)
    assert overrides["chart"] == "bar_race" and overrides["title"] == "מי מוביל במדליות האולימפיות?"
    assert overrides["events"] == [{"date": "1988-09-17", "label": "פתיחת אולימפיאדת סיאול"}, {"date": "1992-07-25", "label": "ברצלונה"}]
    assert overrides["outro"]["credits"] == ["Olympedia, medal tables"]
    assert all(c["reason"] and 0 < c["confidence"] <= 1 for c in record["choices"])
    assert {c["path"] for c in record["choices"] if c["where"] == "override"} >= {"chart", "title", "intro.question", "story.pauses"}
    assert _tree(env["source"]) == before                                              # המקור רק נקרא
    assert client.get("/api/dataviz/smart/thumbnail", params={"episode": "medals_auto"}).headers["content-type"] == "image/png"
    rows = {r["path"]: r for r in client.get("/api/dataviz/episodes/final_config", params={"episode": "medals_auto"}).json()["rows"]}
    assert rows["title"]["auto"]["reason"] and 0 < rows["chart"]["auto"]["confidence"] < 1
    assert "auto" not in rows["video.fps"]


def test_undo_one_choice_and_bad_requests(env):
    client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_auto"})
    assert client.post("/api/dataviz/smart/undo", json={"episode": "medals_auto", "path": "title"}).status_code == 200
    folder = de.episode_folder(env["data"], "medals_auto")
    assert "title" not in de.load_overrides_for_path(folder)                          # חזר לקובץ
    assert "title" not in create.auto_marks(env["data"], "medals_auto")
    assert client.post("/api/dataviz/smart/undo", json={"episode": "medals_auto", "path": "nope"}).status_code == 404
    assert client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_auto"}).status_code == 409
    assert client.post("/api/dataviz/smart/draft", json={"path": env["source"] + "_missing"}).status_code == 404
    empty = os.path.join(os.path.dirname(env["source"]), "empty")
    os.makedirs(empty)
    assert client.post("/api/dataviz/smart/draft", json={"path": empty}).status_code == 400
    assert client.get("/api/dataviz/smart/record", params={"episode": "nope"}).status_code == 404


def test_accept_marks_choices_without_changing_the_episode(env):
    # 21.10.2026: "✓ מאשר" במסך הסקירה - רק מסמן ברשומה; path ריק = כל מה שעוד פתוח (לא מה שבוטל)
    client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_auto"})
    folder = de.episode_folder(env["data"], "medals_auto")
    before = de.load_overrides_for_path(folder)
    assert client.post("/api/dataviz/smart/accept", json={"episode": "medals_auto", "path": "chart"}).json()["accepted"] == ["chart"]
    client.post("/api/dataviz/smart/undo", json={"episode": "medals_auto", "path": "title"})
    rest = client.post("/api/dataviz/smart/accept", json={"episode": "medals_auto", "path": ""}).json()["accepted"]
    assert "title" not in rest and "chart" in rest
    choices = {c["path"]: c for c in client.get("/api/dataviz/smart/record", params={"episode": "medals_auto"}).json()["choices"] if c["where"] == "override"}
    assert choices["chart"]["accepted"] and not choices["title"].get("accepted")
    assert {k: v for k, v in de.load_overrides_for_path(folder).items() if k != "title"} == {k: v for k, v in before.items() if k != "title"}
    assert client.post("/api/dataviz/smart/accept", json={"episode": "medals_auto", "path": "nope"}).status_code == 404


def test_a_folder_with_a_config_is_imported_as_is(env):
    # 21.10.2026: "➕ פרק חדש" -> "📂 מתיקייה" עם use_config: תיקייה עם config.yaml מועתקת כמו שהיא (כמו "📂 ייבא תיקייה"), בלי טיוטה
    with open(os.path.join(env["source"], "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "מדליות", "sources": [{"path": "medals_per_games.csv", "time": {"column": "year", "period": "year"},
                        "entity": {"column": "country"}, "value": {"column": "total_medals"}}]}, f, allow_unicode=True)
    before = _tree(env["source"])
    resp = client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_ready", "use_config": True})
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] and resp.json()["episode"] == "medals_ready"
    folder = de.episode_folder(env["data"], "medals_ready")
    assert "medal_table_raw_UNUSED.csv" in os.listdir(folder)                           # כל התיקייה, כמו שהיא
    assert create.load_record(env["data"], "medals_ready") is None and not de.load_overrides_for_path(folder)
    assert _tree(env["source"]) == before
    # בלי use_config - טיוטה חכמה גם כשיש config.yaml (כמו קודם)
    assert client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_smart"}).json()["choices"]


def test_low_confidence_asks_one_question(env, tmp_path):
    vague = tmp_path / "vague"
    vague.mkdir()
    lines = ["year,entity,x"] + [f"{2000 + i},{e},{v}" for i in range(6) for e, v in (("a", 10 + i * 3), ("b", 12 + (i % 2) * 5), ("c", 7))]
    (vague / "numbers.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    record = create.create_from_folder(env["data"], str(vague), "vague", thumbnail=False)
    question = record["question"]
    assert question and question["about"] in ("kind", "chart") and len(question["options"]) >= 2
    answer = next(o["value"] for o in question["options"] if o["value"] != question["current"])
    assert client.post("/api/dataviz/smart/answer", json={"episode": "vague", "value": answer}).status_code == 200
    overrides = de.load_overrides_for_path(de.episode_folder(env["data"], "vague"))
    if question["about"] == "chart":
        assert overrides["chart"] == answer
    else:
        assert all((s.get("kind") == "level") == (answer == "level") for s in overrides["sources"])
    assert create.load_record(env["data"], "vague")["question"]["answered"] == answer
    assert client.post("/api/dataviz/smart/answer", json={"episode": "vague", "value": "zzz"}).status_code == 400


def test_the_record_goes_to_the_trash_with_the_episode(env):
    client.post("/api/dataviz/smart/draft", json={"path": env["source"], "name": "medals_auto"})
    trash_id = client.post("/api/dataviz/episodes/delete", json={"episode": "medals_auto"}).json()["trash_id"]
    assert create.load_record(env["data"], "medals_auto") is None
    assert os.path.isfile(os.path.join(env["data"], "dataviz_trash", trash_id, "smart"))


def test_a_source_on_another_drive_and_a_map_draft(env, tmp_path, monkeypatch):
    import json
    geo = tmp_path / "geo"
    geo.mkdir()
    names = ["צפון", "דרום", "מרכז"]
    (geo / "unemployment.csv").write_text("year,district,unemployment_pct\n" + "".join(f"{y},{n},{3 + i}\n" for y in range(2010, 2015)
                                                                                        for i, n in enumerate(names)), encoding="utf-8")
    features = [{"type": "Feature", "properties": {"code": i, "name_he": n}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
                for i, n in enumerate(names)]
    (geo / "districts.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    real = os.path.commonpath

    def other_drive(paths):
        raise ValueError("Paths don't have the same drive")
    monkeypatch.setattr(os.path, "commonpath", other_drive)
    record = create.create_from_folder(env["data"], str(geo), "geo", thumbnail=False)
    monkeypatch.setattr(os.path, "commonpath", real)
    overrides = de.load_overrides_for_path(de.episode_folder(env["data"], "geo"))
    assert overrides["chart"] == "map_race" and overrides["map"] == {"geojson": "districts.geojson", "key": "name_he"}
    assert record["skipped"] == [] and os.path.isfile(os.path.join(de.episode_folder(env["data"], "geo"), "districts.geojson"))
