# tests/dataviz/test_dataviz_wave45.py - גל 45 בעורך הגרפים: נתוני "לפני / אחרי" במדריך, קריינות מוקלטת (לפי תאריך או שם,
# האחרונה גוברת, וקול של Windows רק למה שלא הוקלט), מפה עם חורים ובהטלת מרקטור, ספריית מפות (קובץ חדש בלבד),
# והקלטות דרך המסך. בלי רינדור, בלי ffmpeg ובלי קול אמיתי; תיקיות הפרקים לא משתנות.
import base64
import hashlib
import json
import os
import struct
import time
import wave


import pytest
import yaml
from fastapi.testclient import TestClient
from matplotlib.path import Path

from dataviz import narration
from dataviz.charts.map_race import _signed_area, polygon_path
from dataviz.config import ConfigError, load_config
from dataviz.geo import geojson_keys, load_geojson
from dataviz.help import help_sections
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web import library as lib

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _square(x, y, size=1.0):
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


GEO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": "A", "code": "a1"},
     "geometry": {"type": "Polygon", "coordinates": [_square(34, 31, 2), _square(34.5, 31.5, 0.5)]}},   # עם חור
    {"type": "Feature", "properties": {"name": "B", "code": "b1"}, "geometry": {"type": "Polygon", "coordinates": [_square(40, 60)]}}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides={"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}})
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": str(data), "folder": folder, "md5": md5}


def _unchanged(env):
    return {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == env["md5"]


def _wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 400)


# ---------- מדריך ----------
def test_help_items_carry_what_before_after_needs():
    items = {i["code"]: i for s in help_sections() if s["id"].startswith("group-") for i in s["items"]}
    assert items["ranking.smoothing"]["field"] == {"type": "number", "min": 0.005, "max": 1, "default": 0.07}
    assert items["records.when"]["field"]["choices"] == ["current_takes_lead", "lead_change"]
    assert items["map.projection"]["field"]["default"] == "mercator"


# ---------- קריינות מוקלטת ----------
def test_a_recording_is_found_by_date_or_name_and_the_newest_wins(tmp_path):
    folder = tmp_path / "rec"
    folder.mkdir()
    _wav(folder / "2023-10-07_1.wav")
    time.sleep(0.02)
    _wav(folder / "2023-10-07_2.wav")
    _wav(folder / "אירוע קטן.wav")
    (folder / "2023-10-07_notes.txt").write_text("x")
    assert narration.find_recording(str(folder), "אירוע גדול", "2023-10-07").endswith("2023-10-07_2.wav")
    assert narration.find_recording(str(folder), "אירוע קטן", "2021-05-10").endswith("אירוע קטן.wav")
    assert narration.find_recording(str(folder), "אחר", "1999-01-01") == ""
    assert narration.find_recording("", "x") == ""


def test_recordings_come_first_and_tts_only_fills_the_rest(tmp_path, monkeypatch):
    rec = tmp_path / "rec"
    rec.mkdir()
    _wav(rec / "2023-10-07.wav")
    video = tmp_path / "ep.mp4"
    video.write_bytes(b"v")
    spans = [{"kind": "event", "start": 1.0, "text": "גדול", "label": "גדול"}, {"kind": "event", "start": 5.0, "text": "קטן", "label": "קטן"}]
    used = []
    monkeypatch.setattr(narration, "add_narration", lambda path, clips, **kw: used.append(list(clips)) or path)
    spoken = []
    config = {"base_dir": str(tmp_path), "audio": {}, "narration": {"events": True, "records": False, "folder": "rec", "tts": True}}
    speak = lambda text, path: spoken.append(text) or _wav(path)  # noqa: E731
    dates = {"גדול": "2023-10-07", "קטן": "2021-05-10"}
    assert narration.narrate_video(str(video), config, spans, ffmpeg="f", duration=9, speak=speak, event_dates=dates) == 2
    assert spoken == ["קטן"] and used[0][0] == (1.0, str(rec / "2023-10-07.wav"))
    config["narration"]["tts"] = False
    assert narration.narrate_video(str(video), config, spans, ffmpeg="f", duration=9, speak=speak, event_dates=dates) == 1
    assert spoken == ["קטן"]


def test_new_settings_are_checked(tmp_path):
    folder = write_episode(tmp_path, overrides={"narration": {"folder": "missing_dir"}, "map": {"projection": "globe"}})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    text = "\n".join(e.value.errors)
    assert "missing_dir" in text and "map.projection" in text


# ---------- מפה: חורים והטלה ----------
def test_holes_are_kept_and_mercator_stretches_the_north(tmp_path):
    path = tmp_path / "m.geojson"
    path.write_text(json.dumps(GEO), encoding="utf-8")
    merc = load_geojson(str(path), "name")
    flat = load_geojson(str(path), "name", "equirect")
    a = merc["features"][0]
    assert len(a["polygons"]) == 1 and len(a["polygons"][0]) == 2 and a["rings"] == [a["polygons"][0][0]]
    north = lambda geo: geo["features"][1]["polygons"][0][0]  # noqa: E731
    height = lambda ring: max(y for _x, y in ring) - min(y for _x, y in ring)  # noqa: E731
    assert height(north(merc)) > 1.9 and abs(height(north(flat)) - 1.0) < 1e-9     # ב-60° מרקטור מותח בערך פי 2
    assert geojson_keys(str(path)) == {"name": ["A", "B"], "code": ["a1", "b1"]}


def test_a_polygon_path_has_its_hole_in_the_other_direction():
    outer = [(0, 0), (0, 4), (4, 4), (4, 0), (0, 0)]           # עם כיוון השעון בקובץ
    hole = [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]            # נגד כיוון השעון בקובץ
    path = polygon_path([outer, hole])
    codes = list(path.codes)
    assert codes.count(Path.MOVETO) == 2 and codes.count(Path.CLOSEPOLY) == 2
    first, second = path.vertices[:4].tolist(), path.vertices[5:9].tolist()
    assert _signed_area(first) > 0 > _signed_area(second)


# ---------- ספריית מפות ----------
def test_the_map_library_never_overwrites_and_matches_entities(env, tmp_path):
    text = json.dumps(GEO)
    assert lib.save_map(env["data"], "מחוזות.geojson", text)["name"] == "מחוזות"
    with pytest.raises(de.EpisodeError) as e:
        lib.save_map(env["data"], "מחוזות.geojson", text)
    assert e.value.status == 409
    with pytest.raises(de.EpisodeError):
        lib.save_map(env["data"], "x.geojson", json.dumps({"type": "FeatureCollection", "features": []}))
    with pytest.raises(de.EpisodeError):
        lib.map_path(env["data"], "../../etc")
    listed = lib.list_maps(env["data"])
    assert [m["name"] for m in listed] == ["מחוזות"] and "code" in listed[0]["keys"]
    report = lib.map_match(env["data"], "tiny", "מחוזות", "name")
    assert report["found"] == [] and report["unused"] == ["A", "B"]
    lib.use_map(env["data"], "tiny", "מחוזות", "name")
    over = de.load_overrides_for_path(env["folder"])
    assert over["map"]["geojson"].endswith("מחוזות.geojson") and over["map"]["key"] == "name"
    assert _unchanged(env)


def test_map_routes(env):
    assert client.get("/api/dataviz/maps").json() == {"maps": []}
    resp = client.post("/api/dataviz/maps/upload", json={"filename": "ערים.json", "text": json.dumps(GEO)})
    assert resp.status_code == 200 and resp.json()["name"] == "ערים"
    assert client.post("/api/dataviz/maps/upload", json={"filename": "ערים.json", "text": json.dumps(GEO)}).status_code == 409
    assert client.get("/api/dataviz/maps").json()["maps"][0]["keys"]["name"] == ["A", "B"]
    assert client.get("/api/dataviz/maps/match", params={"episode": "tiny", "name": "ערים", "key": "code"}).json()["unused"] == ["a1", "b1"]
    assert client.get("/api/dataviz/maps/match", params={"episode": "tiny", "name": "ערים", "projection": "x"}).status_code == 400
    assert client.post("/api/dataviz/maps/use", json={"episode": "tiny", "name": "ערים", "key": "name"}).status_code == 200
    assert client.post("/api/dataviz/maps/use", json={"episode": "tiny", "name": "nope", "key": "name"}).status_code == 404


# ---------- הקלטות דרך המסך ----------
def test_recordings_are_new_files_outside_the_episode(env, monkeypatch):
    audio = base64.b64encode(b"RIFFfake").decode()
    resp = client.post("/api/dataviz/episodes/recordings", json={"episode": "tiny", "date": "2023-10-07", "ext": "webm", "data_base64": audio})
    assert resp.status_code == 200
    name = resp.json()["name"]
    folder = lib.recordings_dir(env["data"], "tiny")
    assert os.path.isfile(os.path.join(folder, name)) and name.startswith("2023-10-07_") and name.endswith(".webm")
    over = de.load_overrides_for_path(env["folder"])
    assert over["narration"]["folder"] == os.path.abspath(folder)
    assert client.get("/api/dataviz/episodes/recordings", params={"episode": "tiny"}).json()["recordings"] == {"2023-10-07": name}
    got = client.get("/api/dataviz/episodes/recording", params={"episode": "tiny", "name": name})
    assert got.status_code == 200 and got.headers["content-type"].startswith("audio/webm")
    assert client.get("/api/dataviz/episodes/recording", params={"episode": "tiny", "name": "../../x.webm"}).status_code == 404
    for bad in ({"date": "7.10.2023", "ext": "webm"}, {"date": "2023-10-07", "ext": "exe"}):
        assert client.post("/api/dataviz/episodes/recordings", json={"episode": "tiny", "data_base64": audio, **bad}).status_code == 400
    trashed = []
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(os.path.basename(p)))
    assert client.post("/api/dataviz/episodes/recordings/trash", json={"episode": "tiny", "name": name}).status_code == 200
    assert trashed == [name]
    load_config(os.path.join(env["folder"], "config.yaml"), over)   # תיקיית ההקלטות קיימת - ההגדרות תקינות
    assert _unchanged(env)
    with open(os.path.join(env["folder"], "config.yaml"), encoding="utf-8") as f:
        assert "narration" not in (yaml.safe_load(f) or {})


# ---------- גל 46: מפות מוכנות (בלי רשת - ההורדה מוחלפת) ----------
class _FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, limit):
        return self.data[:limit]


def test_ready_maps_download_only_from_the_catalog_and_never_overwrite(env):
    assert [m["id"] for m in lib.ready_maps(env["data"])] == ["israel-districts", "israel-subdistricts", "world-countries"]
    seen = []
    opener = lambda url: seen.append(url) or _FakeResponse(json.dumps(GEO).encode())  # noqa: E731
    assert lib.fetch_ready_map(env["data"], "israel-districts", opener=opener)["name"] == "israel-districts"
    assert seen == [lib.READY_MAPS[0]["url"]] and lib.ready_maps(env["data"])[0]["installed"] is True
    with pytest.raises(de.EpisodeError) as e:
        lib.fetch_ready_map(env["data"], "israel-districts", opener=opener)
    assert e.value.status == 409
    with pytest.raises(de.EpisodeError) as e:
        lib.fetch_ready_map(env["data"], "https://evil.example/x.geojson", opener=opener)
    assert e.value.status == 404
    with pytest.raises(de.EpisodeError):
        lib.fetch_ready_map(env["data"], "world-countries", opener=lambda url: _FakeResponse(b"x" * (lib.READY_MAX_BYTES + 10)))
    assert not os.path.exists(os.path.join(lib.maps_dir(env["data"]), "world-countries.geojson"))


def test_ready_map_routes(env, monkeypatch):
    assert [m["installed"] for m in client.get("/api/dataviz/maps/ready").json()["maps"]] == [False, False, False]
    monkeypatch.setattr(lib, "fetch_ready_map", lambda data_dir, map_id: lib.save_map(data_dir, map_id + ".geojson", json.dumps(GEO)))
    resp = client.post("/api/dataviz/maps/ready", json={"id": "world-countries"})
    assert resp.status_code == 200 and resp.json()["name"] == "world-countries"
