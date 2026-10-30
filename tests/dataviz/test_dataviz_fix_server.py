# tests/dataviz/test_dataviz_fix_server.py
#
# 23.10.2026, סריקת הבאגים - מנה 3 (אבטחה ויציבות בשרת). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ג3 מעבר תיקייה בנתיבי התמונות / ההקלטות והבחירות החכמות; ב5 500 במקום 400; ב6 הורדת כתוביות לפרק עם שם בעברית;
# נ5 שתי העלאות באותה שנייה; נ6 JSON תקין עם טיפוס שגוי מפיל את רשימת הפרקים; ג12 קבצים שהאשף קורא והמנוע לא
# (cp1255, JSON עם BOM, "Date,Label"); ב22 Excel פגום או JSON מעורב מפילים את כל הסריקה.
import base64
import hashlib
import io
import json
import os

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image

from dataviz.smart import create, scan
from dataviz.web import data as dd
from dataviz.web import episodes as de
from dataviz.web import library
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app, raise_server_exceptions=False)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False
ROWS = "".join(f"{y},{c},{v}\n" for y in range(2000, 2012) for c, v in (("Haifa", 280 + y - 2000), ("Tel Aviv", 400 + 2 * (y - 2000)), ("Eilat", 40 + y - 2000)))


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setattr(web_app.worker, "is_running", False)
    write_episode(data / "dataviz_episodes", name="ep1")
    return data


def _png():
    out = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode()


# ---------- ג3 ----------
def test_image_and_recording_paths_stay_inside_the_episode(env, tmp_path):
    outside = tmp_path / "outside"
    (outside / "images").mkdir(parents=True)
    (outside / "images" / "secret.png").write_bytes(b"\x89PNG outside")
    for episode in (str(outside), "..\\..\\outside", "../../outside"):
        assert client.get("/api/dataviz/episodes/image", params={"episode": episode, "name": "secret.png"}).status_code == 404   # קודם: 200
        with pytest.raises(de.EpisodeError):
            library.recording_path(str(env), episode, "x.wav")
    assert (outside / "images" / "secret.png").exists()


def test_smart_actions_refuse_a_path_as_the_episode_name(env, tmp_path):
    victim = tmp_path / "outside" / "victim.json"
    victim.parent.mkdir(parents=True)
    victim.write_text('{"choices": [{"path": "", "where": "override"}]}', encoding="utf-8")
    before = victim.read_bytes()
    resp = client.post("/api/dataviz/smart/accept", json={"episode": "..\\..\\outside\\victim", "path": ""})
    assert resp.status_code == 404 and victim.read_bytes() == before            # קודם: 200 והקובץ נכתב מחדש


# ---------- ב5 ----------
def test_bad_requests_are_400_not_500(env):
    assert client.post("/api/dataviz/episodes/update_data", json={"episode": "ep1", "source": "abc", "csv_text": "a\n1\n"}).status_code == 400
    resp = client.post("/api/dataviz/variants/save", json={"episode": "ep1", "name": "english", "lang": "en", "set": {"audio.path": "missing.mp3"}})
    assert resp.status_code == 400, resp.text
    with pytest.raises(de.EpisodeError):
        de.clean_form({"name": "NUL", "title": "x", "time_column": "t"})       # קודם: OSError ב-Windows


def test_episode_data_that_does_not_build_is_a_400(env):
    write_episode(env / "dataviz_episodes", name="broken", overrides={"sources": [
        {"path": "alarms.csv", "time": {"column": "time"}, "value": "count", "entity": {"column": "nope"}}]})
    assert client.get("/api/dataviz/estimate", params={"episode": "broken"}).status_code == 400   # קודם: 500 (KeyError)
    assert client.get("/api/dataviz/episodes/editor", params={"episode": "broken"}).status_code == 400
    assert client.post("/api/dataviz/readability", json={"episode": "broken"}).status_code == 400
    assert client.post("/api/dataviz/narration_draft", json={"episode": "broken"}).status_code == 400


def test_a_corrupt_wav_and_a_url_source_update_are_clear_errors(env):
    folder = env / "dataviz_episodes" / "ep1"
    (folder / "music.wav").write_bytes(b"RIFF not really a wav")
    with pytest.raises(de.EpisodeError):
        dd.waveform(str(folder), "music.wav")                                   # קודם: wave.Error
    url, cache = "https://example.com/a.csv", env / "dataviz_cache" / "ep1"
    cache.mkdir(parents=True)
    (cache / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".csv")).write_text("time\n2020-01-01\n", encoding="utf-8")   # כבר הורד
    (env / "dataviz_overrides").mkdir(exist_ok=True)
    (env / "dataviz_overrides" / "ep1.json").write_text(json.dumps(
        {"sources": [{"url": url, "time": {"column": "time"}, "value": "count"}], "data": {"cache_dir": str(cache)}}), encoding="utf-8")
    with pytest.raises(de.EpisodeError):
        dd.update_data(str(env), "ep1", 0, "time\n2020-01-01\n", False)         # קודם: KeyError 'path'


# ---------- ב6 ----------
def test_captions_download_for_a_hebrew_episode_name(env):
    write_episode(env / "dataviz_episodes", name="פרק_בדיקה")
    resp = client.get("/api/dataviz/episodes/captions", params={"episode": "פרק_בדיקה", "mode": "test", "download": 1})
    assert resp.status_code == 200 and "filename*=UTF-8''" in resp.headers["content-disposition"]   # קודם: 500


# ---------- נ5 ----------
def test_two_uploads_in_the_same_second_both_save(env, monkeypatch):
    monkeypatch.setattr(library.time, "strftime", lambda fmt, *a: "20261023120000")
    first = library.save_image(str(env), "ep1", "Haifa", "png", _png())
    second = library.save_image(str(env), "ep1", "Haifa", "png", _png())        # קודם: FileExistsError (500)
    assert first["name"] != second["name"]


# ---------- נ6 ----------
def test_wrong_types_in_the_app_files_do_not_break_the_list(env):
    (env / "dataviz_tags.json").write_text(json.dumps({"episodes": {"ep1": "oops"}}), encoding="utf-8")
    (env / "dataviz_hidden.json").write_text(json.dumps({"hidden": 5}), encoding="utf-8")
    resp = client.get("/api/dataviz/episodes")
    assert resp.status_code == 200 and [e["name"] for e in resp.json()["episodes"]] == ["ep1"]   # קודם: 500


# ---------- ג12 ----------
def test_files_the_smart_scan_reads_also_build_an_episode(env, tmp_path):
    cp = tmp_path / "cp1255"
    cp.mkdir()
    (cp / "cities.csv").write_bytes(("שנה,עיר,אוכלוסייה\n" + ROWS.replace("Haifa", "חיפה")).encode("cp1255"))
    assert create.create_from_folder(str(env), str(cp), "cp1", thumbnail=False)   # קודם: UnicodeDecodeError (500)
    bom = tmp_path / "bom"
    bom.mkdir()
    records = [{"year": y, "city": c, "pop": v} for line in ROWS.splitlines() for y, c, v in [line.split(",")]]
    (bom / "cities.json").write_bytes(b"\xef\xbb\xbf" + json.dumps(records).encode("utf-8"))
    assert create.create_from_folder(str(env), str(bom), "bom1", thumbnail=False)   # קודם: JSONDecodeError (BOM)
    ev = tmp_path / "events_caps"
    ev.mkdir()
    (ev / "population.csv").write_text("year,city,population\n" + ROWS, encoding="utf-8")
    (ev / "events.csv").write_text("Date,Label\n2005-06-01,אירוע\n", encoding="utf-8")
    create.create_from_folder(str(env), str(ev), "ev1", thumbnail=False)       # קודם: KeyError 'date' (500)
    config = yaml.safe_load((env / "dataviz_episodes" / "ev1" / "config.yaml").read_text(encoding="utf-8"))
    assert config.get("events") == "events.csv"


# ---------- ב22 ----------
def test_a_corrupt_excel_or_mixed_json_does_not_break_the_scan(tmp_path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "good.csv").write_text("year,city,population\n" + ROWS, encoding="utf-8")
    (folder / "broken.xlsx").write_bytes(b"PK\x03\x04 truncated")
    (folder / "mixed.json").write_text(json.dumps([{"a": 1, "b": 2}] * 25 + [5]), encoding="utf-8")
    result = scan.scan_folder(str(folder))                                     # קודם: BadZipFile / TypeError
    assert any("good.csv" in json.dumps(f, ensure_ascii=False) for f in result.get("files", []))
    assert os.path.isfile(folder / "broken.xlsx")
