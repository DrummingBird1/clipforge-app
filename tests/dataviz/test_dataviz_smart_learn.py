# tests/dataviz/test_dataviz_smart_learn.py
#
# 20.10.2026: עורך הגרפים החכם, פריטים 15-17 - תיקייה במעקב (רק תיקיות חדשות -> טיוטה + דוח תמונות + התראה למקבל מזויף,
# בלי רינדור מלא), העדפות שנלמדות כשבחירה אוטומטית מוחלפת ביד (לכל ערכת ערוץ), וסדרה: תיקייה שדומה לפרק קיים מקבלת את
# המראה והמבנה שלו ואת המספר הבא בסדרה.
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.smart import create, learn, watch
from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web_app import app

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _medals(folder, source_line="Olympedia, medal tables", shift=0, header="year,country,total_medals"):
    os.makedirs(folder, exist_ok=True)
    lines = [header]
    for year in range(1980, 1996):
        lines += [f"{year},צרפת,20", f"{year},יפן,{5 + shift + (60 if year >= 1988 else 0)}", f"{year},איטליה,8", f"{year},קנדה,3"]
    with open(os.path.join(folder, "medals_per_games.csv"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(folder, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write(f"# SOURCES\n- **Source:** {source_line}.\n")
    return str(folder)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return {"data": str(data), "workspace": str(workspace), "tmp": tmp_path}


def test_an_overridden_choice_becomes_a_preference_for_the_next_draft(env):
    create.create_from_folder(env["data"], _medals(env["tmp"] / "a"), "a", thumbnail=False)
    assert de.load_overrides_for_path(de.episode_folder(env["data"], "a"))["chart"] == "bar_race"
    de.update_override_fields(env["data"], "a", {"chart": "line_race", "theme": "dark"}, [])     # המשתמש מחליף
    assert learn.load_prefs(env["data"])["default"] == {"chart": {"bar_race": "line_race"}, "theme": "dark"}
    record = create.create_from_folder(env["data"], _medals(env["tmp"] / "b", source_line="another source", header="year,nation,medal_count"),
                                       "b", thumbnail=False)   # לא סדרה של a - עמודות ומקור אחרים
    overrides = de.load_overrides_for_path(de.episode_folder(env["data"], "b"))
    assert overrides["chart"] == "line_race" and overrides["theme"] == "dark"
    chart = next(c for c in record["choices"] if c["path"] == "chart")
    assert "העדפה שלך" in chart["reason"] and "bar_race" in chart["reason"]
    settings = client.get("/api/dataviz/smart/settings").json()
    assert settings["prefs"]["default"]["theme"] == "dark"
    assert client.post("/api/dataviz/smart/prefs_reset", json={}).json()["prefs"] == {}


def test_preferences_are_per_channel_kit(env):
    from dataviz.web.kits import save_kit
    save_kit(env["data"], "ערוץ", {"theme": "light"})
    create.create_from_folder(env["data"], _medals(env["tmp"] / "a"), "a", thumbnail=False, kit="ערוץ")
    de.update_override_fields(env["data"], "a", {"ranking.top_n": 3}, [])
    assert learn.load_prefs(env["data"]) == {"ערוץ": {"ranking.top_n": 3}}
    other = create.create_from_folder(env["data"], _medals(env["tmp"] / "b", source_line="x", header="year,nation,medal_count"),
                                      "b", thumbnail=False)   # בלי ערכה
    assert next(c for c in other["choices"] if c["path"] == "ranking.top_n")["value"] == 4


def test_a_similar_folder_continues_the_series(env):
    create.create_from_folder(env["data"], _medals(env["tmp"] / "first"), "first", thumbnail=False)
    de.update_override_fields(env["data"], "first", {"theme": "dark", "theme_overrides.accent": "#ff0000",
                                                     "series.name": "מדליות", "series.number": 1}, [])
    learn.reset_prefs(env["data"])                                        # רק הסדרה, בלי העדפות
    record = create.create_from_folder(env["data"], _medals(env["tmp"] / "second", shift=2), "second", thumbnail=False)
    assert record["series"]["episode"] == "first" and "אותו מקור" in record["series"]["why"]
    overrides = de.load_overrides_for_path(de.episode_folder(env["data"], "second"))
    assert overrides["theme"] == "dark" and overrides["theme_overrides"]["accent"] == "#ff0000"
    assert overrides["series"] == {"name": "מדליות", "number": 2}
    assert any("דומה לפרק 'first'" in c["reason"] for c in record["choices"])
    unrelated = env["tmp"] / "unrelated"
    unrelated.mkdir()
    (unrelated / "temps.csv").write_text("year,entity,level_value\n2000,טמפרטורה (°C),18\n2001,טמפרטורה (°C),19\n2002,טמפרטורה (°C),18.5\n", encoding="utf-8")
    assert learn.find_series(env["data"], str(unrelated)) is None


def test_the_watched_folder_takes_only_new_folders(env):
    root = env["tmp"] / "graphs"
    _medals(root / "old")
    assert client.post("/api/dataviz/smart/watch", json={"enabled": True, "root": str(root / "nope")}).status_code == 404
    status = client.post("/api/dataviz/smart/watch", json={"enabled": True, "root": str(root), "interval_minutes": 15}).json()
    assert status["enabled"] and status["seen"] == 1 and status["pending"] == []
    _medals(root / "new_one", source_line="y")
    assert client.get("/api/dataviz/smart/settings").json()["watch"]["pending"] == ["new_one"]
    sent = []
    done = watch.check(env["data"], env["workspace"], send=lambda text: sent.append(text) or True)
    assert [d["episode"] for d in done] == ["new_one"] and done[0]["ok"] and done[0]["notified"]
    assert "new_one" in sent[0] and de.episode_folder(env["data"], "old") is None          # רק החדשה
    assert os.path.isfile(os.path.join(env["workspace"], "dataviz", "batch", done[0]["report"], "index.html"))
    assert watch.check(env["data"], env["workspace"], send=lambda text: sent.append(text) or True) == []
    assert watch.status(env["data"])["log"][0]["episode"] == "new_one"
    client.post("/api/dataviz/smart/watch", json={"enabled": False, "root": str(root)})
    _medals(root / "after_off", source_line="z")
    assert watch.check(env["data"], env["workspace"], send=lambda text: True) == []          # כבוי - כלום
