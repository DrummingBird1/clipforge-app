# tests/test_dataviz_source_kind_mapping.py
#
# 19.10.2026 (מהסיור, באישור המשתמש): בחירת כמות / רמה כבר ב"➕ פרק חדש" (לכל קובץ) וב"➕ קובץ נתונים נוסף", שמות הקבצים
# המקוריים בתיקיית הפרק (ולא data.csv / data_2.csv), ועריכת המיפוי של מקור קיים מהדפדפן - ל-override בלבד.
import hashlib
import os


import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.web import data as dd
from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

TEMP = "year,entity,level\n2019,T,18.3\n2020,T,19.1\n2021,T,18.6\n"
LAKE = "year,entity,level\n2019,K,210.4\n2020,K,209.2\n2021,K,211.0\n"
FORM = {"name": "climate", "title": "אקלים", "chart": "line_race", "time_column": "year", "period": "year",
        "value_column": "level", "group_column": "entity", "kind": "level", "filename": "temperature betdagan.csv", "csv_text": TEMP}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return {"data": data, "episodes": data / "dataviz_episodes"}


def _config(folder):
    with open(os.path.join(folder, "config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_a_new_episode_of_levels_keeps_the_kind_and_the_original_file_names(env):
    extra = {"time_column": "year", "period": "year", "value_column": "level", "group_column": "entity", "kind": "level",
             "filename": "lake_level.xlsx", "csv_text": LAKE}
    same_name = dict(extra, filename="temperature-betdagan.csv", kind="amount")
    resp = client.post("/api/dataviz/episodes/create", json={**FORM, "extra_sources": [extra, same_name]})
    assert resp.status_code == 200, resp.text
    folder = env["episodes"] / "climate"
    sources = _config(folder)["sources"]
    assert [s["path"] for s in sources] == ["temperature_betdagan.csv", "lake_level.csv", "temperature-betdagan.csv"]
    assert [s.get("kind") for s in sources] == ["level", "level", None]   # כמות = בלי kind, כמו תמיד
    assert sorted(os.listdir(folder)) == ["config.yaml", "lake_level.csv", "temperature-betdagan.csv", "temperature_betdagan.csv"]
    from dataviz.episode import load_episode
    episode = load_episode(str(folder))
    # רמות - לא מצטברות (19.1, לא 37.4). 23.10.2026 (ק4): K מופיעה בשני מקורות באותן שנים (כרמה וככמות) - ישות לכל מקור,
    # ולא סכום של השניים
    assert sorted(episode.levels) == ["K (lake_level)", "T"]
    assert sorted(episode.entities) == ["K (lake_level)", "K (temperature-betdagan)", "T"]
    assert abs(float(episode.cum[-1, episode.entities.index("T")]) - 18.6) < 1e-9
    assert abs(float(episode.cum[-1, episode.entities.index("K (lake_level)")]) - 211.0) < 1e-9


def test_without_a_file_name_the_old_names_stay_and_duplicates_get_a_number(env):
    form = {**FORM, "filename": ""}
    assert client.post("/api/dataviz/episodes/create", json={**form, "extra_sources": [dict(form, csv_text=LAKE)]}).status_code == 200
    assert [s["path"] for s in _config(env["episodes"] / "climate")["sources"]] == ["data.csv", "data_2.csv"]
    assert de.csv_file_names({"filename": "a.csv", "extra_sources": [{"filename": "A.csv"}, {"filename": "a.csv"}]}) == ["a.csv", "A_2.csv", "a_3.csv"]
    assert de.safe_csv_name("C:\\Users\\x\\נתונים 2024.json") == "נתונים_2024.csv"


def test_a_level_needs_a_value_column(env):
    resp = client.post("/api/dataviz/episodes/create", json={**FORM, "value_column": ""})
    assert resp.status_code == 400 and "רמה" in resp.json()["error"]
    assert client.post("/api/dataviz/episodes/create", json={**FORM, "kind": "levels"}).status_code == 400
    assert os.listdir(env["episodes"]) == []


def test_an_added_file_can_be_a_level(env):
    write_episode(env["episodes"], name="tiny")
    mapping = {"time_column": "year", "period": "year", "value_column": "level", "group_column": "entity", "kind": "level"}
    saved = dd.add_source(str(env["data"]), "tiny", "lake.csv", LAKE, mapping, confirm=True)
    assert saved["saved"] and de.load_overrides_for_path(str(env["episodes"] / "tiny"))["sources"][2]["kind"] == "level"


def test_the_mapping_of_an_existing_source_is_edited_in_the_override_only(env):
    folder = write_episode(env["episodes"], name="tiny")
    config_md5 = hashlib.md5(open(os.path.join(folder, "config.yaml"), "rb").read()).hexdigest()
    before = dd.sources_overview(folder, {})[0]
    assert before["kind"] == "amount" and before["legend"] == "שנתי"
    resp = client.post("/api/dataviz/episodes/source_mapping", json={"episode": "tiny", "source": 0, "mapping": {
        "time_column": "year", "period": "year", "value_column": "total", "group_column": "", "legend": "סיכום שנתי"}})
    assert resp.status_code == 200, resp.text
    spec = de.load_overrides_for_path(folder)["sources"][0]
    assert spec["legend"] == "סיכום שנתי" and spec["path"] == "annual.csv"
    assert spec["spread"] == {"per": "day", "weights": {"path": "monthly.csv"}} and spec["texture"] == "stripes"   # השאר נשאר
    assert de.load_overrides_for_path(folder)["sources"][1]["path"] == "alarms.csv"
    assert hashlib.md5(open(os.path.join(folder, "config.yaml"), "rb").read()).hexdigest() == config_md5
    # עמודה שלא קיימת / רמה בספירת שורות - שגיאה, וה-override לא משתנה
    saved = de.load_overrides_for_path(folder)
    for mapping in ({"time_column": "nope", "period": "year"}, {"time_column": "time", "value_column": "", "kind": "level"}):
        bad = client.post("/api/dataviz/episodes/source_mapping", json={"episode": "tiny", "source": 1, "mapping": mapping})
        assert bad.status_code == 400 and bad.json()["error"]
    assert de.load_overrides_for_path(folder) == saved
    assert client.post("/api/dataviz/episodes/source_mapping", json={"episode": "tiny", "source": 7, "mapping": {"time_column": "x"}}).status_code == 400
