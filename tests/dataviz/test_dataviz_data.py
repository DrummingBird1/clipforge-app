# tests/dataviz/test_dataviz_data.py - גל 40: הנתונים של פרק - מקורות, בדיקה, מצטבר, קצב, פיזור, המרת Excel/JSON,
# עדכון נתונים עם השוואת סכומים (קובץ חדש בלבד - שום קובץ קיים לא משתנה), ומוזיקה עם גרף גלי קול.
import base64
import hashlib
import io
import json
import os
import struct
import wave


import pandas as pd
import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import DAILY_ROWS, write_episode
from dataviz.web import data as dd
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
    return {"data": str(data), "folder": folder}


def _tree(folder):
    return sorted((name, hashlib.md5(open(os.path.join(folder, name), "rb").read()).hexdigest()) for name in os.listdir(folder))


def test_sources_show_mapping_rows_and_dropped(env):
    sources = dd.sources_overview(env["folder"], {})
    annual, alarms = sources
    assert annual["time"] == {"column": "year", "period": "year"} and annual["spread"]
    assert alarms["columns"] == ["time", "origin"] and len(alarms["rows"]) == dd.PREVIEW_ROWS
    assert alarms["total_rows"] == len(DAILY_ROWS) and alarms["dropped_rows"] >= 1   # "not a date" + North מסונן


def test_check_cumulative_and_pacing(env):
    check = dd.data_check(env["folder"], {})
    kinds = {f["kind"] for f in check["findings"]}
    assert "empty_days" in kinds and "dropped" in kinds and check["entities"] >= 3
    table = dd.cumulative_table(env["folder"], {})
    assert table["columns"] and table["rows"][-1][0] == check["end"]
    assert all(a <= b for a, b in zip([r[1] for r in table["rows"]], [r[1] for r in table["rows"]][1:]))   # מצטבר לא יורד
    pace = dd.pacing(env["folder"], {})
    assert pace["points"] and pace["total_frames"] > 0 and pace["events"] and pace["peaks"][0]["date"] == "2023-10-07"
    assert pace["step_limited_days"] >= 1


def test_spread_of_an_annual_total(env):
    spread = dd.spread_preview(env["folder"], {}, 0)
    assert spread["period"] == "year" and abs(sum(p["value"] for p in spread["points"]) - spread["total"]) < 1e-6
    assert dd.spread_preview(env["folder"], {}, 1)["points"] == []   # מקור יומי


def test_excel_and_json_become_csv():
    df = pd.DataFrame({"date": ["2020-01-01", "2020-01-02"], "city": ["A", "B"], "n": [1, 2]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    excel = dd.table_to_csv("t.xlsx", base64.b64encode(buf.getvalue()).decode())
    assert excel["columns"] == ["date", "city", "n"] and excel["rows"] == 2
    js = dd.table_to_csv("t.json", base64.b64encode(json.dumps({"records": df.to_dict("records")}).encode()).decode())
    assert js["columns"] == ["date", "city", "n"]
    for name, payload in (("t.pdf", b"x"), ("t.csv", b""), ("t.json", b"[1]")):
        with pytest.raises(de.EpisodeError):
            dd.table_to_csv(name, base64.b64encode(payload).decode())


def test_update_data_compares_then_saves_a_new_file(env):
    before = _tree(env["folder"])
    csv = "time,origin\n" + "".join(f"2021-0{m}-01 10:00:00,South\n" for m in range(1, 10))
    preview = dd.update_data(env["data"], "tiny", 1, csv, confirm=False)
    assert not preview["saved"] and preview["total_after"] != preview["total_before"]
    assert de.load_overrides_for_path(env["folder"]) == {}
    saved = dd.update_data(env["data"], "tiny", 1, csv, confirm=True)
    assert saved["saved"] and saved["file"].startswith("alarms_")
    overrides = de.load_overrides_for_path(env["folder"])
    assert os.path.isfile(overrides["sources"][1]["path"]) and overrides["sources"][0]["path"] == "annual.csv"
    assert _tree(env["folder"]) == before   # תיקיית הפרק לא השתנתה
    with pytest.raises(de.EpisodeError):
        dd.update_data(env["data"], "tiny", 1, "a,b\n1,2\n", confirm=True)   # לא מתאים למיפוי
    with pytest.raises(de.EpisodeError):
        dd.update_data(env["data"], "tiny", 0, csv, confirm=False)   # עמודות אחרות


def _write_wav(path, seconds=1.0, rate=8000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(10000 * (i % 100) / 100)) for i in range(int(rate * seconds))))


def test_music_files_waveform_and_choice(env):
    _write_wav(os.path.join(env["folder"], "song.wav"))
    info = dd.music_info(env["folder"], {})
    assert info["files"] == ["song.wav"] and info["current"] == "" and info["video_seconds"] > 0
    wave_data = dd.waveform(env["folder"], "song.wav")
    assert len(wave_data["peaks"]) == dd.WAVE_POINTS and max(wave_data["peaks"]) == 1.0 and abs(wave_data["duration"] - 1.0) < 0.01
    with pytest.raises(de.EpisodeError):
        dd.waveform(env["folder"], "../x.wav")
    de.update_override_fields(env["data"], "tiny", {"audio.path": "song.wav", "audio.start": 0.5}, [])
    assert dd.music_info(env["folder"], de.load_overrides_for_path(env["folder"]))["current"] == "song.wav"
    with pytest.raises(de.EpisodeError):
        de.update_override_fields(env["data"], "tiny", {"audio.path": "../song.wav"}, [])


def test_routes(env):
    for part in ("sources", "check", "cumulative", "pacing", "spread", "music"):
        resp = client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": part})
        assert resp.status_code == 200 and resp.json()["part"] == part, part
    assert client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": "nope"}).status_code == 400
    csv = base64.b64encode(b"a,b\n1,2\n").decode()
    assert client.post("/api/dataviz/convert_table", json={"filename": "x.csv", "data_base64": csv}).json()["columns"] == ["a", "b"]
    resp = client.post("/api/dataviz/episodes/update_data", json={"episode": "tiny", "source": 1, "csv_text": "time,origin\n2021-01-01,South\n"})
    assert resp.status_code == 200 and resp.json()["saved"] is False


# ---------- 18.10.2026: קובץ נתונים נוסף לפרק קיים - מקור חדש לצד המקורות שכבר יש ----------
EXTRA_CSV = "year,region,total\n2019,C,365\n2020,C,366\n"
MAPPING = {"time_column": "year", "period": "year", "value_column": "total", "group_column": "region", "legend": "נוסף"}


def _overrides_dir(env):
    return os.path.join(env["data"], de.OVERRIDES_DIRNAME, "tiny")


def test_add_source_compares_then_adds_a_new_source_next_to_the_existing(env):
    before = _tree(env["folder"])
    preview = dd.add_source(env["data"], "tiny", "extra data.csv", EXTRA_CSV, MAPPING, confirm=False)
    assert not preview["saved"] and preview["new"] == ["C"] and preview["gone"] == []
    assert preview["total_after"] == pytest.approx(preview["total_before"] + 731)
    assert de.load_overrides_for_path(env["folder"]) == {} and os.listdir(_overrides_dir(env)) == []   # רק בדיקה - לא נשמר כלום

    saved = dd.add_source(env["data"], "tiny", "extra data.csv", EXTRA_CSV, MAPPING, confirm=True)
    assert saved["saved"] and saved["sources"] == 3 and saved["file"].startswith("extra_data_")
    sources = de.load_overrides_for_path(env["folder"])["sources"]
    assert [s["path"] for s in sources[:2]] == ["annual.csv", "alarms.csv"]   # המקורות הקיימים לא השתנו
    assert sources[2] == {"path": os.path.join(os.path.abspath(_overrides_dir(env)), saved["file"]), "time": {"column": "year", "period": "year"},
                          "value": {"column": "total"}, "entity": {"column": "region"}, "legend": "נוסף"}
    with open(sources[2]["path"], encoding="utf-8") as f:
        assert f.read() == EXTRA_CSV
    totals = dd._totals(env["folder"], de.load_overrides_for_path(env["folder"]))
    assert totals["C"] == pytest.approx(731) and "2023" in totals   # הסרטון כולל את הנתונים של שני הקבצים
    assert _tree(env["folder"]) == before   # תיקיית הפרק (ו-config.yaml) לא השתנתה


@pytest.mark.parametrize("csv, mapping, fragment", [
    (EXTRA_CSV, {**MAPPING, "time_column": "nope"}, "nope"), (EXTRA_CSV, {**MAPPING, "group_column": "nope"}, "nope"),
    (EXTRA_CSV, {**MAPPING, "time_column": ""}, "עמודת התאריך"), (EXTRA_CSV, {**MAPPING, "period": "hour"}, "תקופת"),
    ("", MAPPING, "CSV"), ("year,region,total\nabc,C,1\n", MAPPING, "לא נטען"),
])
def test_add_source_rejects_a_bad_file_and_writes_nothing(env, csv, mapping, fragment):
    before = _tree(env["folder"])
    with pytest.raises(de.EpisodeError, match=fragment):
        dd.add_source(env["data"], "tiny", "x.csv", csv, mapping, confirm=True)
    assert de.load_overrides_for_path(env["folder"]) == {}
    assert not os.path.isdir(_overrides_dir(env)) or os.listdir(_overrides_dir(env)) == []
    assert _tree(env["folder"]) == before
    with pytest.raises(de.EpisodeError) as missing:
        dd.add_source(env["data"], "nope", "x.csv", EXTRA_CSV, MAPPING, confirm=False)
    assert missing.value.status == 404


def test_add_source_route(env, monkeypatch):
    audit = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append((a, k)))
    body = {"episode": "tiny", "filename": "extra.csv", "csv_text": EXTRA_CSV, **MAPPING}
    preview = client.post("/api/dataviz/episodes/add_source", json=body)
    assert preview.status_code == 200 and preview.json()["saved"] is False and not audit
    saved = client.post("/api/dataviz/episodes/add_source", json={**body, "confirm": True})
    assert saved.status_code == 200 and saved.json()["saved"] and saved.json()["sources"] == 3
    assert any(a[1] == "dataviz_add_source" for a, _k in audit)
    sources = client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": "sources"}).json()["data"]
    assert len(sources) == 3 and sources[2]["entity"] == "region"
    assert client.post("/api/dataviz/episodes/add_source", json={**body, "episode": "nope"}).status_code == 404
    assert client.post("/api/dataviz/episodes/add_source", json={**body, "time_column": "nope"}).status_code == 400
    assert client.post("/api/dataviz/episodes/add_source", json="x").status_code == 400
    foreign = client.post("/api/dataviz/episodes/add_source", json=body, headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"})
    assert foreign.status_code == 403


def _fake_bin(trashed):
    # סל מיחזור מזויף שבאמת מעביר את הקובץ "החוצה" - ככה הטסט תופס גם קוד שמעביר את הקובץ לסל
    def send(path):
        trashed.append(path)
        os.remove(path)   # safe: קובץ זמני של הטסט ב-tmp_path
    return send


def test_remove_source_unlists_only_an_added_source_and_keeps_its_file_on_disk(env, monkeypatch):
    # 18.10.2026: רק מקור שנוסף מהדפדפן מוסר, ורק מה-override - הקובץ שלו נשאר בדיסק בלי שינוי (החלטת המשתמש)
    trashed = []
    monkeypatch.setattr("send2trash.send2trash", _fake_bin(trashed))
    assert [s["removable"] for s in dd.sources_overview(env["folder"], {})] == [False, False]
    before = _tree(env["folder"])
    saved = dd.add_source(env["data"], "tiny", "extra.csv", EXTRA_CSV, MAPPING, confirm=True)
    added = os.path.join(_overrides_dir(env), saved["file"])
    content = open(added, "rb").read()
    overrides = de.load_overrides_for_path(env["folder"])
    assert [s["removable"] for s in dd.sources_overview(env["folder"], overrides)] == [False, False, True]
    for index in (0, 1, 3, -1):
        with pytest.raises(de.EpisodeError, match="המקורות המקוריים"):
            dd.remove_source(env["data"], "tiny", index)
    assert len(de.load_overrides_for_path(env["folder"])["sources"]) == 3
    result = dd.remove_source(env["data"], "tiny", 2)
    assert result == {"ok": True, "sources": 2, "kept": saved["file"]}
    assert not trashed and open(added, "rb").read() == content   # הקובץ נשאר במקום, אותם בייטים
    assert [s["path"] for s in de.load_overrides_for_path(env["folder"])["sources"]] == ["annual.csv", "alarms.csv"]
    assert _tree(env["folder"]) == before
    with pytest.raises(de.EpisodeError) as missing:
        dd.remove_source(env["data"], "nope", 2)
    assert missing.value.status == 404


def test_a_data_file_over_5mb_can_be_added_and_converted(env):
    # 18.10.2026: המגבלה לקובץ עלתה מ-5MB ל-25MB (קובץ נוסף, המרה מ-Excel/JSON/CSV)
    csv = "year,region,total\n" + "".join(f"{2019 + i % 2},C{i % 50},1\n" for i in range(650_000))
    assert len(csv.encode("utf-8")) > 6 * 1024 * 1024
    preview = dd.add_source(env["data"], "tiny", "big.csv", csv, MAPPING, confirm=False)
    assert not preview["saved"] and preview["total_after"] == pytest.approx(preview["total_before"] + 650_000)
    assert dd.table_to_csv("big.csv", base64.b64encode(csv.encode()).decode())["rows"] == 650_000
    with pytest.raises(de.EpisodeError, match="25MB"):
        dd.add_source(env["data"], "tiny", "huge.csv", "a" * (25 * 1024 * 1024 + 1), MAPPING, confirm=False)


def test_remove_source_route(env, monkeypatch):
    audit, trashed = [], []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append((a, k)))
    monkeypatch.setattr("send2trash.send2trash", _fake_bin(trashed))
    saved = dd.add_source(env["data"], "tiny", "extra.csv", EXTRA_CSV, MAPPING, confirm=True)
    added = os.path.join(_overrides_dir(env), saved["file"])
    content = open(added, "rb").read()
    assert client.post("/api/dataviz/episodes/remove_source", json={"episode": "tiny", "source": 0}).status_code == 400
    assert client.post("/api/dataviz/episodes/remove_source", json={"episode": "tiny", "source": "x"}).status_code == 400
    assert client.post("/api/dataviz/episodes/remove_source", json={"episode": "nope", "source": 2}).status_code == 404
    foreign = client.post("/api/dataviz/episodes/remove_source", json={"episode": "tiny", "source": 2},
                          headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"})
    assert foreign.status_code == 403
    ok = client.post("/api/dataviz/episodes/remove_source", json={"episode": "tiny", "source": 2})
    assert ok.status_code == 200 and ok.json()["sources"] == 2 and ok.json()["kept"] == saved["file"]
    assert not trashed and open(added, "rb").read() == content
    assert any(a[1] == "dataviz_remove_source" for a, _k in audit)


# ---------- 18.10.2026: קובץ משקלות (spread.weights) מהדפדפן - קובץ חדש תחת dataviz_overrides, הסרה רק מה-override ----------
WEIGHTS_CSV = "שנה,חודש,משקל\n2019,1,1\n2019,7,3\n2020,6,5\n"
WEIGHTS_MAP = {"period_column": "שנה", "month_column": "חודש", "value": "משקל"}


def test_set_weights_saves_a_new_file_and_the_override_points_to_it(env):
    before = _tree(env["folder"])
    saved = dd.set_weights(env["data"], "tiny", 0, "my weights.csv", WEIGHTS_CSV, WEIGHTS_MAP)
    assert saved["saved"] and saved["file"].startswith("my_weights_") and saved["matched"] == 2 and saved["periods"] == 2
    path = os.path.join(_overrides_dir(env), saved["file"])
    assert open(path, "rb").read() == WEIGHTS_CSV.encode("utf-8") and os.listdir(_overrides_dir(env)) == [saved["file"]]
    sources = de.load_overrides_for_path(env["folder"])["sources"]
    assert sources[0]["spread"] == {"per": "day", "weights": {"path": os.path.abspath(path), **WEIGHTS_MAP}}
    assert [s["path"] for s in sources] == ["annual.csv", "alarms.csv"]   # המקורות עצמם לא השתנו
    overrides = de.load_overrides_for_path(env["folder"])
    points = {p["date"]: p["value"] for p in dd.spread_preview(env["folder"], overrides, 0)["points"]}
    assert points["2019-07-15"] == pytest.approx(3 * points["2019-01-15"], rel=1e-3) and points["2019-03-15"] == 0   # הפיזור לפי הקובץ החדש
    assert sum(points.values()) == pytest.approx(365, rel=1e-3)   # הסכום השנתי לא השתנה
    overview = dd.sources_overview(env["folder"], overrides)
    assert [(s["weights"], s["weights_removable"]) for s in overview] == [(saved["file"], True), ("", False)]
    assert _tree(env["folder"]) == before


def test_set_weights_rejects_bad_files_without_writing(env):
    for index, csv, mapping, error in (
            (1, WEIGHTS_CSV, WEIGHTS_MAP, "יומי"),
            (0, WEIGHTS_CSV, dict(WEIGHTS_MAP, value="אין"), "לא קיימת"),
            (0, "שנה,חודש,משקל\n1990,1,1\n", WEIGHTS_MAP, "אף שורה"),
            (0, "שנה,חודש,משקל\n2019,1,x\n", WEIGHTS_MAP, "מספרים"),
            (5, WEIGHTS_CSV, WEIGHTS_MAP, "אין מקור"),
            (0, "a" * (25 * 1024 * 1024 + 1), WEIGHTS_MAP, "25MB")):
        with pytest.raises(de.EpisodeError, match=error):
            dd.set_weights(env["data"], "tiny", index, "w.csv", csv, mapping)
    assert de.load_overrides_for_path(env["folder"]) == {}
    assert not os.path.isdir(_overrides_dir(env)) or os.listdir(_overrides_dir(env)) == []
    with pytest.raises(de.EpisodeError) as missing:
        dd.set_weights(env["data"], "nope", 0, "w.csv", WEIGHTS_CSV, WEIGHTS_MAP)
    assert missing.value.status == 404


def test_remove_weights_only_from_the_override_and_the_file_stays_on_disk(env):
    saved = dd.set_weights(env["data"], "tiny", 0, "w.csv", WEIGHTS_CSV, WEIGHTS_MAP)
    path = os.path.join(_overrides_dir(env), saved["file"])
    assert dd.remove_weights(env["data"], "tiny", 0) == {"ok": True, "kept": saved["file"]}
    assert open(path, "rb").read() == WEIGHTS_CSV.encode("utf-8")   # הקובץ נשאר במקום, אותם בייטים
    overrides = de.load_overrides_for_path(env["folder"])
    assert overrides["sources"][0]["spread"] == {"per": "day", "weights": {"path": "monthly.csv"}}   # חזרה למשקלות של config.yaml
    assert [(s["weights"], s["weights_removable"]) for s in dd.sources_overview(env["folder"], overrides)] == [("monthly.csv", False), ("", False)]
    for index in (0, 1, 7):
        with pytest.raises(de.EpisodeError, match="שנוסף מהדפדפן"):
            dd.remove_weights(env["data"], "tiny", index)
    # מקור שנוסף מהדפדפן (בלי משקלות ב-config.yaml) - ההסרה מורידה את המשקלות לגמרי
    dd.add_source(env["data"], "tiny", "extra.csv", EXTRA_CSV, MAPPING, confirm=True)
    second = dd.set_weights(env["data"], "tiny", 2, "w2.csv", WEIGHTS_CSV, WEIGHTS_MAP)
    assert dd.remove_weights(env["data"], "tiny", 2)["kept"] == second["file"]
    assert "weights" not in (de.load_overrides_for_path(env["folder"])["sources"][2].get("spread") or {})
    assert os.path.isfile(os.path.join(_overrides_dir(env), second["file"]))


def test_weights_routes(env, monkeypatch):
    audit = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append((a, k)))
    body = {"episode": "tiny", "source": 0, "filename": "w.csv", "csv_text": WEIGHTS_CSV, **WEIGHTS_MAP}
    assert client.post("/api/dataviz/episodes/set_weights", json=dict(body, source="x")).status_code == 400
    assert client.post("/api/dataviz/episodes/set_weights", json=dict(body, source=1)).status_code == 400
    assert client.post("/api/dataviz/episodes/set_weights", json=dict(body, episode="nope")).status_code == 404
    assert client.post("/api/dataviz/episodes/set_weights", json="x").status_code == 400
    foreign = {"Origin": "http://evil.example", "Host": "127.0.0.1:8878"}
    assert client.post("/api/dataviz/episodes/set_weights", json=body, headers=foreign).status_code == 403
    assert de.load_overrides_for_path(env["folder"]) == {}
    ok = client.post("/api/dataviz/episodes/set_weights", json=body)
    assert ok.status_code == 200 and ok.json()["saved"] and ok.json()["matched"] == 2
    path = os.path.join(_overrides_dir(env), ok.json()["file"])
    assert client.post("/api/dataviz/episodes/remove_weights", json={"episode": "tiny", "source": 1}).status_code == 400
    assert client.post("/api/dataviz/episodes/remove_weights", json={"episode": "tiny", "source": 0}, headers=foreign).status_code == 403
    removed = client.post("/api/dataviz/episodes/remove_weights", json={"episode": "tiny", "source": 0})
    assert removed.status_code == 200 and removed.json()["kept"] == ok.json()["file"] and os.path.isfile(path)
    assert {a[1] for a, _k in audit} >= {"dataviz_set_weights", "dataviz_remove_weights"}


def test_two_saves_in_the_same_second_get_different_files(env, monkeypatch):
    # 19.10.2026: השם היה לפי השנייה + os.replace - שמירה שנייה באותה שנייה דרסה את הקובץ של הראשונה
    monkeypatch.setattr(dd, "_stamp", lambda: "20261019_120000")
    first = dd.add_source(env["data"], "tiny", "extra.csv", EXTRA_CSV, MAPPING, confirm=True)
    second = dd.add_source(env["data"], "tiny", "extra.csv", EXTRA_CSV.replace("365", "300"), MAPPING, confirm=True)
    assert first["file"] == "extra_20261019_120000.csv" and second["file"] == "extra_20261019_120000_2.csv"
    paths = [s["path"] for s in de.load_overrides_for_path(env["folder"])["sources"][2:]]
    assert [os.path.basename(p) for p in paths] == [first["file"], second["file"]]
    with open(paths[0], encoding="utf-8") as f:
        assert f.read() == EXTRA_CSV                                   # הראשון לא נדרס
    csv = "time,origin\n2021-01-01 10:00:00,South\n"
    a = dd.update_data(env["data"], "tiny", 1, csv, confirm=True)["file"]
    b = dd.update_data(env["data"], "tiny", 1, csv + "2021-02-01 10:00:00,South\n", confirm=True)["file"]
    assert a != b and sorted(os.listdir(_overrides_dir(env))) == sorted([first["file"], second["file"], a, b])   # בלי קובצי בדיקה שנשארו
