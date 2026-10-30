# tests/test_dataviz_import_folder.py
#
# 19.10.2026: "📂 ייבא תיקיית פרק" - תיקיית פרק מוכנה (ColdData/Graphs, workspace/dataviz_israel_staging) מועתקת ל-
# data/dataviz_episodes/<שם> עם ה-config.yaml שלה, קובצי הנתונים, האירועים ו-SOURCES.md. המקור רק נקרא, שם קיים = 409,
# והעותק נבדק בתיקייה זמנית לפני שהוא מקבל את השם הסופי (ייבוא שנכשל לא משאיר כלום).
import hashlib
import os


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _tree(root):
    return sorted((os.path.relpath(os.path.join(d, f), root), hashlib.md5(open(os.path.join(d, f), "rb").read()).hexdigest())
                  for d, _dirs, files in os.walk(root) for f in files)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    graphs = tmp_path / "Graphs"
    folder = write_episode(graphs, overrides={"title": "מוכן", "events": "events.csv", "notes": ["מקור: בדיקה"]}, name="climate_ready")
    with open(os.path.join(folder, "events.csv"), "w", encoding="utf-8") as f:
        f.write("date,label\n2021-06-01,אירוע\n")
    with open(os.path.join(folder, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("# מקורות\n")
    return {"data": data, "episodes": data / "dataviz_episodes", "source": folder}


def test_a_ready_folder_is_copied_whole_and_the_source_is_untouched(env):
    before = _tree(env["source"])
    resp = client.post("/api/dataviz/episodes/import_folder", json={"path": env["source"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "climate_ready" and body["title"] == "מוכן" and body["files"] == len(before)
    dest = env["episodes"] / "climate_ready"
    assert _tree(dest) == before                                      # config.yaml, הנתונים, events.csv, SOURCES.md - כמו שהם
    assert _tree(env["source"]) == before                             # המקור לא השתנה
    assert [n for n in os.listdir(env["episodes"]) if n.startswith(".import_")] == []
    names = [e["name"] for e in client.get("/api/dataviz/episodes").json()["episodes"]]
    assert "climate_ready" in names


def test_an_existing_name_is_refused_and_another_name_can_be_given(env):
    assert client.post("/api/dataviz/episodes/import_folder", json={"path": env["source"]}).status_code == 200
    config = env["episodes"] / "climate_ready" / "config.yaml"
    md5 = hashlib.md5(config.read_bytes()).hexdigest()
    again = client.post("/api/dataviz/episodes/import_folder", json={"path": env["source"]})
    assert again.status_code == 409 and hashlib.md5(config.read_bytes()).hexdigest() == md5
    other = client.post("/api/dataviz/episodes/import_folder", json={"path": env["source"], "name": "climate_copy"})
    assert other.status_code == 200 and (env["episodes"] / "climate_copy" / "SOURCES.md").is_file()


@pytest.mark.parametrize("case", ["missing", "no_config", "bad_data", "bad_name", "inside"])
def test_a_bad_import_writes_nothing(env, tmp_path, case):
    path, name = str(env["source"]), ""
    if case == "missing":
        path = str(tmp_path / "nope")
    elif case == "no_config":
        os.makedirs(tmp_path / "empty")
        path = str(tmp_path / "empty")
    elif case == "bad_data":
        with open(os.path.join(env["source"], "alarms.csv"), "w", encoding="utf-8") as f:
            f.write("nothing,here\n1,2\n")
    elif case == "bad_name":
        name = "שם עם רווח"
    elif case == "inside":
        write_episode(env["episodes"], name="already")
        path = str(env["episodes"] / "already")
    before = sorted(os.listdir(env["episodes"]))
    resp = client.post("/api/dataviz/episodes/import_folder", json={"path": path, "name": name})
    assert resp.status_code in (400, 404) and resp.json()["error"]
    assert sorted(os.listdir(env["episodes"])) == before            # לא נוצר פרק ולא נשארה תיקייה זמנית


def test_ready_folders_come_from_the_new_staging_folder_or_the_old_one(env, tmp_path, monkeypatch):
    # 19.10.2026: workspace/dataviz/staging (תוצרים לפי כלי); לפני ההעברה - workspace/dataviz_israel_staging. רק קריאה
    from dataviz.web import episodes as de
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    assert client.get("/api/dataviz/episodes/import_suggestions").json() == {"folder": "", "episodes": []}
    old = workspace / "dataviz_israel_staging"
    write_episode(old, overrides={"title": "מהישנה"}, name="climate_ready")
    (old / "notes_only").mkdir()                                     # בלי config.yaml - לא פרק
    body = client.get("/api/dataviz/episodes/import_suggestions").json()
    assert body["folder"] == str(old) and [(e["name"], e["title"], e["imported"]) for e in body["episodes"]] == [("climate_ready", "מהישנה", False)]
    new = workspace / "dataviz" / "staging"
    write_episode(new, overrides={"title": "מהחדשה"}, name="climate_ready")
    assert client.post("/api/dataviz/episodes/import_folder", json={"path": str(new / "climate_ready")}).status_code == 200
    body = client.get("/api/dataviz/episodes/import_suggestions").json()
    assert body["folder"] == str(new) == de.staging_folder(str(workspace))
    assert [(e["title"], e["imported"]) for e in body["episodes"]] == [("מהחדשה", True)]
