# tests/dataviz/test_dataviz_wave52.py - גל 52 בעורך הגרפים, "הנתונים": הצעות מיזוג לשמות דומים, קפיצות חשודות ותיקונים
# (פיזור שומר על הסכום), ימים חסרים במקור יומי, מקורות מכתובת / Google Sheets (הורדה רק בלחיצה - כאן עם "רשת"
# מזויפת), זיהוי שינוי, ותזמון דרך ה-Scheduler. קבצי הפרק ו-config.yaml לא משתנים; ההורדות נכתבות ל-data/dataviz_cache.
import hashlib
from tests import PROJECT_ROOT
import importlib.util
import io
import os


import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.cleaning import apply_fixes, find_outliers, name_key, similar_names
from dataviz.config import ConfigError, load_config
from dataviz.episode import load_episode
from dataviz.sources import daily_matrix, read_table
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web import remote as remote

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}
SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py")


# ---------- שמות דומים ----------
def test_name_key_ignores_spelling_noise():
    assert name_key("תל-אביב") == name_key("תל אביב") == name_key("תל  אביב")
    assert name_key("הרצלייה") == name_key("הרצליה")
    assert name_key("ראשון לציון") == name_key("ראשון לציון ") and name_key("ים") == name_key("ימ")
    assert name_key("Tel-Aviv") == name_key("tel aviv")


def test_similar_names_are_grouped_with_the_biggest_as_target():
    totals = {"תל אביב": 500.0, "תל-אביב": 20.0, "ירושלים": 400.0, "ירושליים": 3.0, "חיפה": 100.0, "2023": 9.0, "2024": 8.0}
    groups = similar_names(totals)
    by_target = {g["target"]: g for g in groups}
    assert set(by_target) == {"תל אביב", "ירושלים"}
    assert by_target["תל אביב"]["names"] == ["תל אביב", "תל-אביב"] and by_target["תל אביב"]["reason"] == "same"
    assert by_target["ירושלים"]["names"] == ["ירושלים", "ירושליים"]
    # כבר ממוזגים - לא מוצעים שוב
    assert {g["target"] for g in similar_names(totals, {"תל-אביב": "תל אביב"})} == {"ירושלים"}


# ---------- קפיצות חשודות ותיקונים ----------
def _matrix():
    index = pd.date_range("2024-01-01", periods=60, freq="D")
    frame = pd.DataFrame({"א": 10.0, "ב": 5.0}, index=index)
    frame.loc["2024-02-10", "א"] = 610.0          # דיווח מצטבר שנזרק ליום אחד
    return frame


def test_outliers_are_found_and_fixes_change_the_matrix():
    found = find_outliers(_matrix())
    assert [(o["entity"], o["date"]) for o in found] == [("א", "2024-02-10")]
    assert found[0]["typical"] == 10 and found[0]["ratio"] == pytest.approx(61)
    spread = apply_fixes(_matrix(), [{"entity": "א", "date": "2024-02-10", "action": "spread", "days": 30}])
    assert spread["א"].sum() == pytest.approx(_matrix()["א"].sum())      # הסכום נשמר
    assert spread.loc["2024-02-10", "א"] == 10 and spread.loc["2024-02-09", "א"] == pytest.approx(30)
    smooth = apply_fixes(_matrix(), [{"entity": "א", "date": "2024-02-10", "action": "smooth"}])
    assert smooth.loc["2024-02-10", "א"] == 10 and smooth["א"].sum() == pytest.approx(600)
    manual = apply_fixes(_matrix(), [{"entity": "א", "date": "2024-02-10", "action": "set", "value": 42},
                                     {"entity": "ג", "date": "2024-02-10", "action": "set", "value": 1},       # ישות לא קיימת
                                     {"entity": "א", "date": "2030-01-01", "action": "smooth"}])               # מחוץ לטווח
    assert manual.loc["2024-02-10", "א"] == 42 and manual.shape == _matrix().shape
    assert not find_outliers(spread)


# ---------- ימים חסרים ----------
def _readings(tmp_path, missing):
    folder = tmp_path / missing
    folder.mkdir()
    (folder / "r.csv").write_text("date,city,value\n2024-01-01,א,10\n2024-01-04,א,40\n2024-01-05,א,50\n", encoding="utf-8")
    spec = {"path": "r.csv", "time": {"column": "date"}, "value": {"column": "value"}, "entity": {"column": "city"}, "missing": missing}
    matrix, _ = daily_matrix([read_table(spec, str(folder))], [spec], str(folder))
    return list(matrix["א"])


def test_missing_days_in_a_daily_source(tmp_path):
    assert _readings(tmp_path, "zero") == [10, 0, 0, 40, 50]
    assert _readings(tmp_path, "previous") == [10, 10, 10, 40, 50]
    assert _readings(tmp_path, "interpolate") == [10, 20, 30, 40, 50]


# ---------- מקורות מכתובת ----------
class _Net:
    """רשת מזויפת: כתובת -> תוכן, ורושמת מה הורד."""

    def __init__(self, files):
        self.files, self.calls = dict(files), []

    def __call__(self, url):
        self.calls.append(url)
        if url not in self.files:
            raise OSError("404")
        return io.BytesIO(self.files[url])


CSV = "date,city,value\n2024-01-01,א,10\n2024-01-02,ב,20\n2024-01-03,א,5\n".encode("utf-8")
SHEET = "https://docs.google.com/spreadsheets/d/abc_123/edit#gid=77"
SHEET_CSV = "https://docs.google.com/spreadsheets/d/abc_123/export?format=csv&gid=77"


def test_google_sheets_links_download_as_csv():
    assert remote.download_url(SHEET) == SHEET_CSV
    assert remote.download_url("https://docs.google.com/spreadsheets/d/abc_123/edit") == "https://docs.google.com/spreadsheets/d/abc_123/export?format=csv"
    assert remote.download_url("https://example.com/a.csv") == "https://example.com/a.csv"


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides=SMALL)
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": str(data), "folder": folder, "md5": md5}


def _unchanged(env):
    return {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == env["md5"]


FORM = {"url": SHEET, "time_column": "date", "value_column": "value", "entity_column": "city", "legend": "מהרשת"}


def test_a_url_source_is_downloaded_on_click_and_refresh_detects_changes(env):
    net = _Net({SHEET_CSV: CSV})
    result = remote.add_url_source(env["data"], "tiny", FORM, opener=net)
    assert result["refresh"]["changed"] is True and net.calls == [SHEET_CSV]
    overrides = de.load_overrides_for_path(env["folder"])
    cache = os.path.join(env["data"], "dataviz_cache", "tiny")
    assert overrides["data"]["cache_dir"] == os.path.abspath(cache) and overrides["sources"][-1]["url"] == SHEET
    episode = load_episode(env["folder"], overrides)
    assert {"א", "ב"} <= set(episode.entities)
    assert remote.refresh_sources(env["data"], "tiny", opener=net)["changed"] is False          # אותו תוכן
    net.files[SHEET_CSV] = CSV + "2024-01-04,ב,7\n".encode("utf-8")
    again = remote.refresh_sources(env["data"], "tiny", opener=net)
    assert again["changed"] is True and again["sources"][0]["bytes"] > len(CSV)
    overview = remote.remote_overview(env["data"], "tiny")
    assert overview["sources"][0]["url"] == SHEET and overview["sources"][0]["changed_at"]
    assert os.listdir(cache) and _unchanged(env)
    with pytest.raises(de.EpisodeError, match="כבר בפרק"):
        remote.add_url_source(env["data"], "tiny", FORM, opener=net)


def test_a_url_source_that_fails_is_not_added(env):
    with pytest.raises(de.EpisodeError, match="ההורדה נכשלה"):
        remote.add_url_source(env["data"], "tiny", FORM, opener=_Net({}))
    assert all(not s.get("url") for s in de.load_overrides_for_path(env["folder"]).get("sources", []))
    with pytest.raises(de.EpisodeError, match="לא נוסף"):     # עמודה שלא קיימת בקובץ
        remote.add_url_source(env["data"], "tiny", {**FORM, "time_column": "when"}, opener=_Net({SHEET_CSV: CSV}))
    assert all(not s.get("url") for s in de.load_overrides_for_path(env["folder"]).get("sources", []))
    with pytest.raises(de.EpisodeError, match="כתובת לא תקינה"):
        remote.add_url_source(env["data"], "tiny", {**FORM, "url": "file:///etc/passwd"}, opener=_Net({}))
    load_config(os.path.join(env["folder"], "config.yaml"), de.load_overrides_for_path(env["folder"]))   # הפרק עדיין תקין
    assert _unchanged(env)


def test_a_url_source_that_was_not_downloaded_is_a_clear_error(tmp_path):
    folder = write_episode(tmp_path, overrides={"sources": [{"url": "https://example.com/data.csv", "time": {"column": "date"}}]})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    assert any("עוד לא הורד" in m for m in e.value.errors)
    folder = write_episode(tmp_path / "b", overrides={"sources": [{"url": "ftp://x/y.csv", "time": {"column": "date"}}],
                                                       "data": {"missing": "sometimes", "fixes": [{"entity": "א"}]}})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    text = "\n".join(e.value.errors)
    assert "http://" in text and "data.missing" in text and "data.fixes[0]" in text


# ---------- דרך השרת ----------
def test_cleaning_report_and_fixes_through_the_server(env, monkeypatch):
    rows = "time,origin\n" + "".join(f"2022-03-{d:02d} 10:00:00,South\n" for d in range(1, 29))
    with open(os.path.join(env["folder"], "alarms.csv"), "a", encoding="utf-8") as f:
        f.write(rows)
    report = client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": "clean"}).json()["data"]
    assert report["missing"] == "zero" and report["fixes"] == []
    assert any(o["date"] == "2023-10-07" for o in report["outliers"])     # 800 אזעקות ביום אחד
    resp = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {
        "data.fixes": [{"entity": "2023", "date": "2023-10-07", "action": "spread", "days": "20"}], "data.missing": "previous"}})
    assert resp.status_code == 200, resp.text
    saved = de.load_overrides_for_path(env["folder"])["data"]
    assert saved == {"fixes": [{"entity": "2023", "date": "2023-10-07", "action": "spread", "days": 20}], "missing": "previous"}
    bad = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {"data.fixes": [{"entity": "2023", "date": "x", "action": "spread"}]}})
    assert bad.status_code == 400


def test_url_source_route_uses_the_network_only_when_asked(env, monkeypatch):
    net = _Net({SHEET_CSV: CSV})
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout=30: net(request.full_url))
    assert client.get("/api/dataviz/episodes/remote", params={"episode": "tiny"}).json()["sources"] == []
    assert net.calls == []
    resp = client.post("/api/dataviz/episodes/url_source", json={"episode": "tiny", **FORM})
    assert resp.status_code == 200, resp.text
    assert client.post("/api/dataviz/episodes/refresh", json={"episode": "tiny"}).json()["changed"] is False
    assert net.calls == [SHEET_CSV, SHEET_CSV]
    assert _unchanged(env)


def test_schedule_route_adds_a_task_with_closed_arguments(env, monkeypatch, tmp_path):
    from utils import scheduler_store
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "tasks.json"))
    resp = client.post("/api/dataviz/schedule", json={"episode": "tiny", "mode": "full", "schedule_type": "daily", "time_str": "02:30",
                                                      "refresh": True, "only_if_changed": True})
    assert resp.status_code == 200, resp.text
    task, = scheduler_store.load_tasks()
    assert task["extra_args"] == ["--episode", "tiny", "--mode", "full", "--refresh-data", "--only-if-changed"]
    assert task["time"] == "02:30" and task["script_path"].endswith("dataviz_maker.py") and task["label"] == "📊 tiny"
    assert [s["id"] for s in resp.json()["schedules"]] == [task["id"]]
    for bad in ({"mode": "stills"}, {"schedule_type": "monthly"}, {"time_str": "25:00"}, {"episode": "nope"}, {"weekday": "xyz"}):
        assert client.post("/api/dataviz/schedule", json={"episode": "tiny", "mode": "full", **bad}).status_code in (400, 404)
    assert len(scheduler_store.load_tasks()) == 1


def test_the_script_skips_an_episode_whose_data_did_not_change(monkeypatch):
    spec = importlib.util.spec_from_file_location("dataviz_maker_w52", SCRIPT)
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    from dataviz.web import remote as dataviz_remote
    args = type("Args", (), {"only_if_changed": True})()
    monkeypatch.setattr(dataviz_remote, "refresh_sources", lambda data_dir, name: {"sources": [{"url": "u", "changed": False}], "changed": False})
    results = {}
    assert maker.refresh_episode_data("d", "ep", args, results) is False and results["skipped"] == 1
    monkeypatch.setattr(dataviz_remote, "refresh_sources", lambda data_dir, name: {"sources": [{"url": "u", "changed": True}], "changed": True})
    assert maker.refresh_episode_data("d", "ep", args, results) is True
    monkeypatch.setattr(dataviz_remote, "refresh_sources", lambda data_dir, name: {"sources": [], "changed": False})
    assert maker.refresh_episode_data("d", "ep", args, results) is True      # בלי מקורות מכתובת - מרנדרים כרגיל


def test_yaml_in_cache_dir_is_never_the_episode_folder(env):
    net = _Net({SHEET_CSV: CSV})
    remote.add_url_source(env["data"], "tiny", FORM, opener=net)
    cache = de.load_overrides_for_path(env["folder"])["data"]["cache_dir"]
    assert not os.path.commonpath([os.path.abspath(cache), os.path.abspath(env["folder"])]) == os.path.abspath(env["folder"])
    with open(os.path.join(env["folder"], "config.yaml"), encoding="utf-8") as f:
        assert "url" not in str(yaml.safe_load(f).get("sources"))
