# tests/dataviz/test_web_app_dataviz_screen.py
#
# מסך "סרטוני נתונים" בדפדפן - ה-API (entrypoints/web/routes/dataviz.py + utils/dataviz_episodes.py):
# רשימת פרקים (קריאה בלבד), הרצה דרך אותו נתיב של /api/run, תוצרים והורדה, ויצירת פרק חדש מ-CSV
# שמסרבת לדרוס. data/ ו-workspace/ זמניים (monkeypatch של web_app.DATA_DIR/WORKSPACE_DIR).
import hashlib
import os


import pytest
import yaml
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

CSV = "date,city,n\n" + "".join(f"2020-0{m}-{d:02d},{city},{m * d}\n" for m in (1, 2, 3) for d in (1, 15) for city in ("A", "B"))
FORM = {"name": "my-ep", "title": "כותרת", "subtitle": "תת", "chart": "line_race", "theme": "dark", "time_column": "date",
        "value_column": "n", "group_column": "city", "period": "day", "csv_text": CSV}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    workspace = tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return {"data": data, "episodes": data / "dataviz_episodes", "workspace": workspace}


def _tree(root):
    return sorted((str(p.relative_to(root)), hashlib.md5(p.read_bytes()).hexdigest() if p.is_file() else "")
                  for p in root.rglob("*"))


def _runs(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: calls.append((script, folder, payload)) or {"ok": True})
    return calls


# ---------- פרקים ----------

def test_episodes_listing_shows_key_config_and_never_touches_data(env):
    write_episode(env["episodes"], overrides={"title": "אזעקות", "chart": "line_race", "theme": "dark"}, name="alarms")
    (env["episodes"] / "broken").mkdir()
    (env["episodes"] / "broken" / "config.yaml").write_text("title: [unclosed", encoding="utf-8")
    (env["episodes"] / "not_an_episode").mkdir()
    before = _tree(env["data"])

    body = client.get("/api/dataviz/episodes").json()

    rows = {r["name"]: r for r in body["episodes"]}
    assert set(rows) == {"alarms", "broken"}
    assert rows["alarms"]["valid"] and rows["alarms"]["title"] == "אזעקות"
    assert rows["alarms"]["chart"] == "line_race" and rows["alarms"]["theme"] == "dark"
    assert rows["alarms"]["sources"] == 2 and rows["alarms"]["width"] > 0
    assert rows["broken"]["valid"] is False and rows["broken"]["errors"]
    assert body["charts"] == ["bar_race", "line_race", "stacked_area_race", "scatter_race", "bump_race", "heatmap_race", "map_race", "pie_race", "small_multiples"]
    assert body["modes"] == ["stills", "preview", "test", "full", "share", "shorts"]   # גל 55: Shorts אוטומטיים
    assert _tree(env["data"]) == before


def test_episodes_listing_without_a_folder_is_empty(env):
    os.rmdir(env["episodes"])
    assert client.get("/api/dataviz/episodes").json()["episodes"] == []


# ---------- הרצה ----------

def test_run_goes_through_the_script_run_path_with_validated_args(env, monkeypatch):
    write_episode(env["episodes"], name="alarms")
    calls = _runs(monkeypatch)

    r = client.post("/api/dataviz/run", json={"episode": "alarms", "mode": "preview", "chart": "scatter_race", "publish": "on"})

    assert r.status_code == 200 and r.json()["ok"]
    script, folder, payload = calls[0]
    assert script.endswith(os.path.join("my_scripts", "video", "dataviz_maker.py"))
    assert folder == str(env["episodes"] / "alarms")
    assert web_app._build_extra_args("dataviz_maker.py", payload) == ["--mode", "preview", "--chart", "scatter_race", "--publish"]


def test_build_extra_args_ignores_anything_outside_the_whitelists():
    args = web_app._build_extra_args("dataviz_maker.py", {"dv_mode": "full; rm -rf", "dv_chart": "../../x", "dv_publish": "off"})
    assert args == ["--no-publish"]
    assert web_app._build_extra_args("dataviz_maker.py", {"dv_mode": "stills"}) == ["--mode", "stills"]


@pytest.mark.parametrize("body, status", [
    ({"episode": "nope", "mode": "full"}, 404),
    ({"episode": "../alarms", "mode": "full"}, 404),
    ({"episode": "..\\alarms", "mode": "full"}, 404),
    ({"episode": "", "mode": "full"}, 404),
    ({"episode": "alarms", "mode": "weird"}, 400),
    ({"episode": "alarms", "mode": "full", "chart": "pie"}, 400),
    ({"episode": "alarms", "mode": "full", "publish": "maybe"}, 400),
])
def test_run_rejects_bad_input_before_starting_anything(env, monkeypatch, body, status):
    write_episode(env["episodes"], name="alarms")
    calls = _runs(monkeypatch)
    assert client.post("/api/dataviz/run", json=body).status_code == status
    assert calls == []


def test_run_rejects_non_object_body_foreign_origin_and_busy_worker(env, monkeypatch):
    write_episode(env["episodes"], name="alarms")
    calls = _runs(monkeypatch)
    assert client.post("/api/dataviz/run", json=["x"]).status_code == 400
    foreign = client.post("/api/dataviz/run", json={"episode": "alarms", "mode": "full"},
                          headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"})
    assert foreign.status_code == 403
    monkeypatch.setattr(web_app.worker, "is_running", True)
    assert client.post("/api/dataviz/run", json={"episode": "alarms", "mode": "full"}).status_code == 409
    assert calls == []


def test_run_is_audited_and_queued_on_the_real_worker_path(env, monkeypatch):
    write_episode(env["episodes"], name="alarms")
    tasks, audit = [], []
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda script, folder, *a, **kw: tasks.append((script, folder, kw)))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append((a, k)))

    assert client.post("/api/dataviz/run", json={"episode": "alarms", "mode": "stills", "publish": "off"}).status_code == 200

    script, folder, kw = tasks[0]
    assert os.path.basename(script) == "dataviz_maker.py" and folder == str(env["episodes"] / "alarms")
    assert kw["extra_args"] == ["--mode", "stills", "--no-publish"]
    assert kw["label"].startswith("📊 alarms")
    assert any(a[1] == "run_script" and k.get("details") == "dataviz_maker.py" for a, k in audit)


# ---------- תוצרים ----------

def _outputs(env):
    folder = env["workspace"] / "dataviz" / "outputs" / "horizontal"
    (folder / "alarms_stills").mkdir(parents=True)
    (folder / "alarms_stills" / "frame_01.png").write_bytes(b"\x89PNGfake")
    (folder / "alarms_stills" / "frame_02.png").write_bytes(b"\x89PNGfake2")
    (folder / "alarms_preview.mp4").write_bytes(b"0123456789" * 100)
    (folder / "alarms_test.mp4").write_bytes(b"test")
    (folder / "alarms.mp4").write_bytes(b"full")
    (folder / "alarms.publish.json").write_text("{}", encoding="utf-8")
    (folder / "other.mp4").write_bytes(b"x")
    (folder / ".hidden.mp4").write_bytes(b"x")
    return folder


def test_outputs_list_videos_and_stills_with_modes_and_filter(env):
    _outputs(env)
    rows = client.get("/api/dataviz/outputs").json()["outputs"]
    by_name = {r["name"]: r for r in rows}
    assert set(by_name) == {"alarms_stills", "alarms_preview.mp4", "alarms_test.mp4", "alarms.mp4", "other.mp4"}
    assert by_name["alarms_preview.mp4"]["mode"] == "preview" and by_name["alarms_test.mp4"]["mode"] == "test"
    assert by_name["alarms.mp4"]["mode"] == "full" and by_name["alarms.mp4"]["has_package"] is True
    assert by_name["alarms_stills"]["files"] == ["frame_01.png", "frame_02.png"] and by_name["alarms_stills"]["count"] == 2
    filtered = client.get("/api/dataviz/outputs", params={"episode": "alarms"}).json()
    assert "other.mp4" not in {r["name"] for r in filtered["outputs"]}
    assert filtered["folders"]["horizontal"].endswith(os.path.join("dataviz", "outputs", "horizontal"))


def test_outputs_empty_workspace(env):
    data = client.get("/api/dataviz/outputs").json()
    assert data["outputs"] == [] and data["folders"] == {}
    assert data["save_to"]["problem"] is None   # 23.10.2026: לאן נכתבים תוצרים חדשים (test_dataviz_export_folder.py)


def test_media_serves_video_range_download_and_stills(env):
    _outputs(env)
    r = client.get("/api/dataviz/media/horizontal/alarms_preview.mp4")
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and len(r.content) == 1000
    partial = client.get("/api/dataviz/media/horizontal/alarms_preview.mp4", headers={"Range": "bytes=0-9"})
    assert partial.status_code == 206 and partial.content == b"0123456789"
    dl = client.get("/api/dataviz/media/horizontal/alarms.mp4", params={"download": 1})
    assert "attachment" in dl.headers["content-disposition"] and "alarms.mp4" in dl.headers["content-disposition"]
    still = client.get("/api/dataviz/media/horizontal/alarms_stills/frame_01.png")
    assert still.status_code == 200 and still.headers["content-type"] == "image/png"


@pytest.mark.parametrize("path", [
    "/api/dataviz/media/horizontal/..%2Falarms.mp4",
    "/api/dataviz/media/horizontal/..%5Calarms.mp4",
    "/api/dataviz/media/elsewhere/alarms.mp4",
    "/api/dataviz/media/horizontal/alarms.publish.json",
    "/api/dataviz/media/horizontal/.hidden.mp4",
    "/api/dataviz/media/horizontal/missing.mp4",
    "/api/dataviz/media/horizontal/alarms_stills/..%2F..%2Falarms.mp4",
    "/api/dataviz/media/horizontal/alarms_stills/frame_01.txt",
    "/api/dataviz/media/horizontal/dataviz/frame_01.png",
    "/api/dataviz/media/horizontal/..%2F..%2F..%2Fdata/x.png",
])
def test_media_blocks_traversal_and_other_files(env, path):
    _outputs(env)
    (env["workspace"] / "alarms.mp4").write_bytes(b"outside")
    assert client.get(path).status_code in (404, 422)


# ---------- פרק חדש ----------

def test_create_episode_writes_only_a_new_valid_folder_and_is_audited(env, monkeypatch):
    audit = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append((a, k)))

    r = client.post("/api/dataviz/episodes/create", json=FORM)

    assert r.status_code == 200 and r.json()["name"] == "my-ep" and r.json()["valid"] and r.json()["chart"] == "line_race"
    folder = env["episodes"] / "my-ep"
    assert sorted(os.listdir(folder)) == ["config.yaml", "data.csv"]
    assert (folder / "data.csv").read_text(encoding="utf-8") == CSV
    assert any(a[1] == "dataviz_create_episode" and k.get("details") == "my-ep" for a, k in audit)
    assert [e["name"] for e in client.get("/api/dataviz/episodes").json()["episodes"]] == ["my-ep"]


def test_create_episode_refuses_an_existing_name_and_leaves_it_untouched(env):
    write_episode(env["episodes"], name="my-ep")
    before = _tree(env["data"])
    r = client.post("/api/dataviz/episodes/create", json=FORM)
    assert r.status_code == 409 and "כבר קיים" in r.json()["error"]
    assert _tree(env["data"]) == before


@pytest.mark.parametrize("change, fragment", [
    ({"name": "../evil"}, "שם הפרק"), ({"name": "a/b"}, "שם הפרק"), ({"name": "..\\x"}, "שם הפרק"),
    ({"name": ".hidden"}, "שם הפרק"), ({"name": ""}, "שם הפרק"), ({"name": "x" * 41}, "שם הפרק"),
    ({"title": " "}, "כותרת"), ({"chart": "pie"}, "תרשים"), ({"theme": "red"}, "ערכת"), ({"period": "hour"}, "תקופת"),
    ({"time_column": ""}, "עמודת התאריך"), ({"time_column": "nope"}, "nope"), ({"value_column": "nope"}, "nope"),
    ({"group_column": "nope"}, "nope"), ({"csv_text": ""}, "CSV"), ({"csv_text": "date,n\n2020-01-01,1\n", "group_column": ""}, "ימים"),
    ({"csv_text": "a" * (25 * 1024 * 1024 + 1)}, "25MB"),
])
def test_create_episode_rejects_bad_forms_without_writing_anything(env, change, fragment):
    before = _tree(env["data"])
    r = client.post("/api/dataviz/episodes/create", json={**FORM, **change})
    assert r.status_code == 400 and fragment in r.json()["error"], r.json()
    assert _tree(env["data"]) == before
    assert not (env["data"].parent / "evil").exists()


def test_create_episode_rejects_foreign_origin_and_non_object(env):
    foreign = client.post("/api/dataviz/episodes/create", json=FORM,
                          headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"})
    assert foreign.status_code == 403 and os.listdir(env["episodes"]) == []
    assert client.post("/api/dataviz/episodes/create", json="x").status_code == 400


# 18.10.2026: פרק חדש מכמה קבצים - הראשון data.csv כמו קודם, וכל קובץ נוסף מקור משלו עם המיפוי שלו
EXTRA_CSV = "year,region,total\n2019,C,365\n2020,C,366\n"
EXTRA = {"csv_text": EXTRA_CSV, "time_column": "year", "period": "year", "value_column": "total", "group_column": "region", "legend": "שנתי"}


def test_create_episode_with_one_file_keeps_the_single_source_config(env):
    assert client.post("/api/dataviz/episodes/create", json=FORM).status_code == 200
    config = yaml.safe_load((env["episodes"] / "my-ep" / "config.yaml").read_text(encoding="utf-8"))
    assert config["sources"] == [{"path": "data.csv", "time": {"column": "date"}, "value": {"column": "n"}, "entity": {"column": "city"}}]


def test_create_episode_from_several_files_writes_a_source_per_file(env):
    second = {**EXTRA, "csv_text": "year,region,total\n2020,D,10\n", "legend": ""}
    r = client.post("/api/dataviz/episodes/create", json={**FORM, "extra_sources": [EXTRA, second]})
    assert r.status_code == 200 and r.json()["sources"] == 3, r.json()
    folder = env["episodes"] / "my-ep"
    assert sorted(os.listdir(folder)) == ["config.yaml", "data.csv", "data_2.csv", "data_3.csv"]
    assert (folder / "data.csv").read_text(encoding="utf-8") == CSV
    assert (folder / "data_2.csv").read_text(encoding="utf-8") == EXTRA_CSV
    config = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))
    assert config["sources"][0] == {"path": "data.csv", "time": {"column": "date"}, "value": {"column": "n"}, "entity": {"column": "city"}}
    assert config["sources"][1] == {"path": "data_2.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "total"},
                                    "entity": {"column": "region"}, "legend": "שנתי"}
    assert config["sources"][2]["path"] == "data_3.csv" and "legend" not in config["sources"][2]
    from dataviz.episode import load_episode
    assert set(load_episode(str(folder)).entities) == {"A", "B", "C", "D"}   # הנתונים של כל הקבצים בסרטון אחד


@pytest.mark.parametrize("extras, fragment", [
    ([{**EXTRA, "time_column": "nope"}], "קובץ 2: עמודת התאריך 'nope'"), ([{**EXTRA, "value_column": "nope"}], "קובץ 2"),
    ([{**EXTRA, "time_column": ""}], "קובץ 2: בחר"), ([{**EXTRA, "period": "hour"}], "קובץ 2: תקופת"),
    ([{**EXTRA, "csv_text": ""}], "קובץ 2: לא נבחר"), ([{**EXTRA, "csv_text": "a" * (25 * 1024 * 1024 + 1)}], "25MB"),
    ([EXTRA, "x"], "קובץ 3"), ([EXTRA] * 10, "עד 9"), ("x", "עד 9"),
    ([{**EXTRA, "csv_text": "year,region,total\nabc,C,1\n"}], "הנתונים לא נטענו"),
])
def test_create_episode_rejects_a_bad_extra_file_without_writing_anything(env, extras, fragment):
    before = _tree(env["data"])
    r = client.post("/api/dataviz/episodes/create", json={**FORM, "extra_sources": extras})
    assert r.status_code == 400 and fragment in r.json()["error"], r.json()
    assert _tree(env["data"]) == before


def test_csv_columns_reads_headers_only(env):
    assert client.post("/api/dataviz/episodes/csv_columns", json={"csv_text": CSV}).json() == {"columns": ["date", "city", "n"]}
    assert client.post("/api/dataviz/episodes/csv_columns", json={"csv_text": ""}).status_code == 400
    big = client.post("/api/dataviz/episodes/csv_columns", json={"csv_text": "a" * (25 * 1024 * 1024 + 1)})
    assert big.status_code == 400 and "25MB" in big.json()["error"]
    assert os.listdir(env["episodes"]) == []


def test_a_file_over_5mb_is_accepted_for_a_new_episode(env):
    # 18.10.2026: המגבלה לקובץ עלתה מ-5MB ל-25MB
    rows = "".join(f"2020-01-{1 + i % 28:02d},{'AB'[i % 2]},{i % 7}\n" for i in range(450_000))
    csv = "date,city,n\n" + rows
    assert len(csv.encode("utf-8")) > 6 * 1024 * 1024
    assert client.post("/api/dataviz/episodes/csv_columns", json={"csv_text": csv}).json() == {"columns": ["date", "city", "n"]}
    r = client.post("/api/dataviz/episodes/create", json={**FORM, "csv_text": csv})
    assert r.status_code == 200, r.json()


# ---------- הסתרת פרק מהרשימה ----------

def test_hide_and_unhide_only_writes_the_marker_file_and_never_touches_the_episode(env):
    write_episode(env["episodes"], name="done")
    write_episode(env["episodes"], name="keep")
    episodes_before = _tree(env["episodes"])

    r = client.post("/api/dataviz/episodes/hide", json={"episode": "done", "hidden": True})

    assert r.status_code == 200 and r.json()["hidden"] == ["done"]
    assert _tree(env["episodes"]) == episodes_before
    assert sorted(os.listdir(env["data"])) == ["dataviz_episodes", "dataviz_hidden.json"]
    body = client.get("/api/dataviz/episodes").json()
    assert [e["name"] for e in body["episodes"]] == ["keep"] and body["hidden_count"] == 1
    shown = client.get("/api/dataviz/episodes", params={"show_hidden": 1}).json()["episodes"]
    assert {e["name"]: e["hidden"] for e in shown} == {"done": True, "keep": False}

    assert client.post("/api/dataviz/episodes/hide", json={"episode": "done", "hidden": False}).json()["hidden"] == []
    assert [e["name"] for e in client.get("/api/dataviz/episodes").json()["episodes"]] == ["done", "keep"]
    assert _tree(env["episodes"]) == episodes_before


@pytest.mark.parametrize("body, status", [
    ({"episode": "ghost", "hidden": True}, 404), ({"episode": "../x", "hidden": True}, 404),
    ({"episode": "done", "hidden": "yes"}, 400), ({"episode": "done"}, 400),
])
def test_hide_rejects_bad_input_and_writes_nothing(env, body, status):
    write_episode(env["episodes"], name="done")
    assert client.post("/api/dataviz/episodes/hide", json=body).status_code == status
    assert not os.path.exists(env["data"] / "dataviz_hidden.json")


def test_hide_rejects_foreign_origin_is_audited_and_survives_a_corrupt_marker(env, monkeypatch):
    write_episode(env["episodes"], name="done")
    foreign = client.post("/api/dataviz/episodes/hide", json={"episode": "done", "hidden": True},
                          headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"})
    assert foreign.status_code == 403 and not os.path.exists(env["data"] / "dataviz_hidden.json")
    audit = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append((a, k)))
    assert client.post("/api/dataviz/episodes/hide", json={"episode": "done", "hidden": True}).status_code == 200
    assert any(a[1] == "dataviz_hide_episode" and k.get("details") == "done" for a, k in audit)
    (env["data"] / "dataviz_hidden.json").write_text("{not json", encoding="utf-8")
    assert [e["name"] for e in client.get("/api/dataviz/episodes").json()["episodes"]] == ["done"]


def test_rotate_token_and_csv_columns_reject_foreign_origin(env):
    foreign = {"Origin": "http://evil.example", "Host": "127.0.0.1:8878"}
    assert client.post("/api/rotate_token", headers=foreign).status_code == 403
    assert client.post("/api/dataviz/episodes/csv_columns", json={"csv_text": "a,b\n1,2"}, headers=foreign).status_code == 403
    assert client.post("/api/dataviz/episodes/csv_columns", json={"csv_text": "a,b\n1,2"}).status_code == 200


def test_hidden_marker_drops_deleted_episodes_and_is_capped(env, monkeypatch):
    write_episode(env["episodes"], name="alive")
    write_episode(env["episodes"], name="gone")
    assert client.post("/api/dataviz/episodes/hide", json={"episode": "gone", "hidden": True}).status_code == 200
    import shutil
    shutil.rmtree(env["episodes"] / "gone")
    body = client.post("/api/dataviz/episodes/hide", json={"episode": "alive", "hidden": True}).json()
    assert body["hidden"] == ["alive"]                      # הפרק שנמחק נושר מהקובץ
    from dataviz.web import episodes as dataviz_episodes
    monkeypatch.setattr(dataviz_episodes, "MAX_HIDDEN", 1)
    write_episode(env["episodes"], name="aaa")
    assert len(client.post("/api/dataviz/episodes/hide", json={"episode": "aaa", "hidden": True}).json()["hidden"]) == 1

# ---------- עריכת הגדרות פרק (override נפרד, config.yaml לא משתנה) ----------

def test_saving_settings_writes_only_a_separate_override_file(env):
    folder = write_episode(env["episodes"], overrides={"title": "מקור"}, name="ep")
    before = _tree(env["episodes"])
    cfg_bytes = (env["episodes"] / "ep" / "config.yaml").read_bytes()

    r = client.post("/api/dataviz/episodes/settings", json={"episode": "ep", "settings": {
        "title": "כותרת חדשה", "chart": "line_race", "theme": "dark", "top_n": 5,
        "publish": {"title": "כותרת לפרסום", "hashtags": ["#a", "#b"], "enabled": True}}})

    assert r.status_code == 200 and r.json()["edited"] is True
    assert _tree(env["episodes"]) == before and (env["episodes"] / "ep" / "config.yaml").read_bytes() == cfg_bytes
    # 23.10.2026: גם הטופס הבסיסי נכנס להיסטוריית הגרסאות (data/dataviz_history) - אפשר לחזור אחרי "אפס הכל"
    assert sorted(os.listdir(env["data"])) == ["dataviz_episodes", "dataviz_history", "dataviz_overrides"]
    row = next(e for e in client.get("/api/dataviz/episodes").json()["episodes"] if e["name"] == "ep")
    assert row["title"] == "כותרת חדשה" and row["chart"] == "line_race" and row["theme"] == "dark" and row["edited"] is True
    got = client.get("/api/dataviz/episodes/settings", params={"episode": "ep"}).json()
    assert got["settings"]["top_n"] == 5 and got["settings"]["publish"]["hashtags"] == ["#a", "#b"] and got["edited"]

    from dataviz.config import load_config
    from dataviz.web.episodes import load_overrides_for_path
    effective = load_config(os.path.join(folder, "config.yaml"), load_overrides_for_path(folder))
    assert effective["title"] == "כותרת חדשה" and effective["ranking"]["top_n"] == 5 and effective["publish"]["enabled"] is True

    assert client.post("/api/dataviz/episodes/settings", json={"episode": "ep", "settings": None}).json()["edited"] is False
    assert not os.path.exists(env["data"] / "dataviz_overrides" / "ep.json")
    assert _tree(env["episodes"]) == before
    assert next(e for e in client.get("/api/dataviz/episodes").json()["episodes"] if e["name"] == "ep")["title"] == "מקור"


@pytest.mark.parametrize("settings", [
    {"chart": "pie"}, {"theme": "neon"}, {"top_n": 2}, {"top_n": "7"}, {"top_n": True}, {"title": "x" * 201}, {"title": 5},
    {"publish": {"hashtags": "abc"}}, {"publish": {"enabled": "yes"}}, {"publish": {"hashtags": ["a"] * 16}},
    {"video": {"width": 1}}, {"sources": []}, {"base_dir": "C:/x"},
])
def test_settings_reject_bad_or_unsupported_fields_and_write_nothing(env, settings):
    write_episode(env["episodes"], name="ep")
    r = client.post("/api/dataviz/episodes/settings", json={"episode": "ep", "settings": settings})
    assert r.status_code == 400
    assert not os.path.exists(env["data"] / "dataviz_overrides")


def test_settings_origin_unknown_episode_and_audit(env, monkeypatch):
    write_episode(env["episodes"], name="ep")
    body = {"episode": "ep", "settings": {"title": "t"}}
    assert client.post("/api/dataviz/episodes/settings", json=body, headers={"Origin": "http://evil.example", "Host": "127.0.0.1:8878"}).status_code == 403
    assert client.post("/api/dataviz/episodes/settings", json={"episode": "../x", "settings": {"title": "t"}}).status_code == 404
    assert client.get("/api/dataviz/episodes/settings", params={"episode": "ghost"}).status_code == 404
    audit = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: audit.append(a))
    assert client.post("/api/dataviz/episodes/settings", json=body).status_code == 200
    assert any(a[1] == "dataviz_edit_episode" for a in audit)