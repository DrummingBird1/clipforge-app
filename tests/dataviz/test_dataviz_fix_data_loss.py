# tests/dataviz/test_dataviz_fix_data_loss.py
#
# 23.10.2026, סריקת הבאגים - מנה 1 (אובדן נתונים). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ק6 מחיקה כשקובץ של הפרק פתוח מחקה חצי פרק; ק8 "אפס הכל" אחרי הטופס הבסיסי בלי היסטוריה, ו-payload שמתנקה לריק
# מחק גם את העורך המלא; ג4 ריצה מתוזמנת לא נחשבה "רצה" ופרק נמחק באמצע רינדור; ב2 "EP1" / "ep1." פתחו את "ep1";
# ג16 שם גרסה שדורס קבצים של הפרק או של פרק אחר; ב1 שכפול שנשבר כשהמקור נמחק; ב3 מקור מכתובת שנכשל שינה את ההגדרות.
import os
import subprocess
import sys

import psutil
import pytest
from fastapi.testclient import TestClient

from dataviz.web import data as dd
from dataviz.web import episodes as de
from dataviz.web import history, remote, trash, variants
from entrypoints import web_app
from entrypoints.web.routes import dataviz as routes
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _files(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _dirs, files in os.walk(root) for f in files)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setattr(web_app.worker, "is_running", False)
    routes._RUN_EPISODES.clear()
    write_episode(data / "dataviz_episodes", name="ep1")
    return data


# ---------- ק6: מחיקה כשקובץ פתוח ----------
@pytest.mark.skipif(sys.platform != "win32", reason="ב-Windows קובץ פתוח חוסם שינוי שם של התיקייה")
def test_deleting_while_a_file_is_open_moves_nothing(env):
    folder = env / "dataviz_episodes" / "ep1"
    before = _files(folder)
    with open(folder / "monthly.csv", "rb"):
        with pytest.raises(de.EpisodeError) as err:
            trash.delete_episode(str(env), "ep1")
    assert err.value.status == 409
    assert _files(folder) == before and de.episode_folder(str(env), "ep1") is not None   # קודם: נשאר רק monthly.csv
    assert trash.list_trash(str(env)) == []


def test_a_move_that_fails_midway_is_rolled_back(env, monkeypatch):
    de.update_override_fields(str(env), "ep1", {"labels.total": "סך"}, [])   # עוד חלק לסל: קובץ השינויים
    real_rename, calls = os.rename, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) == 2:
            raise PermissionError("locked")
        return real_rename(src, dst)
    monkeypatch.setattr(trash.os, "rename", flaky)
    with pytest.raises(de.EpisodeError) as err:
        trash.delete_episode(str(env), "ep1")
    monkeypatch.setattr(trash.os, "rename", real_rename)
    assert err.value.status == 409 and de.episode_folder(str(env), "ep1") is not None
    assert de.load_overrides_for_path(str(env / "dataviz_episodes" / "ep1")) == {"labels": {"total": "סך"}}
    assert trash.list_trash(str(env)) == []


# ---------- ק8: הטופס הבסיסי ו"אפס הכל" ----------
def test_reset_all_after_the_basic_form_can_be_undone_from_history(env):
    de.set_overrides(str(env), "ep1", {"title": "כותרת מהטופס"})
    de.set_overrides(str(env), "ep1", None)                                      # "↩️ אפס הכל"
    assert de.load_overrides_for_path(str(env / "dataviz_episodes" / "ep1")) == {}
    versions = history.versions(str(env), "ep1")["versions"]
    saved = [v["id"] for v in versions if history._load(str(env), "ep1", v["id"])["overrides"].get("title") == "כותרת מהטופס"]
    assert saved                                                                 # קודם: 0 גרסאות
    history.restore(str(env), "ep1", saved[0])
    assert de.load_overrides_for_path(str(env / "dataviz_episodes" / "ep1"))["title"] == "כותרת מהטופס"


def test_a_basic_form_save_that_cleans_to_nothing_keeps_the_full_editor_edits(env):
    de.update_override_fields(str(env), "ep1", {"labels.total": "סך", "subtitle": "ישן"}, [])
    de.set_overrides(str(env), "ep1", {"publish": {}})
    assert de.load_overrides_for_path(str(env / "dataviz_episodes" / "ep1")) == {"labels": {"total": "סך"}}   # קודם: {}


# ---------- ג4: ריצה שלא התחילה מהמסך ----------
def test_an_episode_rendered_by_a_scheduled_run_is_not_deleted(env, monkeypatch):
    monkeypatch.setattr(web_app.worker, "is_running", True)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "dataviz_maker.py", "--episode", "ep1"])
    try:
        psutil.Process(proc.pid).cmdline()
        resp = client.post("/api/dataviz/episodes/delete", json={"episode": "ep1"})
        assert resp.status_code == 409, resp.text                               # קודם: 200 ונמחק באמצע הרינדור
        assert de.episode_folder(str(env), "ep1") is not None
    finally:
        for child in psutil.Process(proc.pid).children(recursive=True):
            child.kill()
        proc.kill()
        proc.wait()


# ---------- ב2: שמות כפולים ב-Windows ----------
def test_only_the_exact_folder_name_opens_an_episode(env):
    for alias in ("EP1", "ep1.", "ep1 ", "Ep1"):
        assert de.episode_folder(str(env), alias) is None, alias
        assert client.post("/api/dataviz/episodes/delete", json={"episode": alias}).status_code == 404
    assert de.episode_folder(str(env), "ep1") is not None and trash.list_trash(str(env)) == []


# ---------- ג16: שם גרסה שדורס קבצים ----------
def test_a_variant_name_that_would_overwrite_other_outputs_is_refused(env):
    for name in ("shorts", "test", "en", "Preview", "shorts_2"):
        with pytest.raises(de.EpisodeError):
            variants.save(str(env), "ep1", name, set_values={})
    write_episode(env / "dataviz_episodes", name="ep1_israel")
    with pytest.raises(de.EpisodeError) as err:
        variants.save(str(env), "ep1", "israel", set_values={})                 # ep1_israel.mp4 של הפרק האחר
    assert err.value.status == 409
    assert variants.save(str(env), "ep1", "short_cut", set_values={})


# ---------- ב1: שכפול עצמאי ----------
def test_a_duplicate_keeps_working_after_the_original_is_deleted(env):
    mapping = {"time_column": "date", "period": "day", "value_column": "value", "group_column": "entity", "kind": "amount", "legend": ""}
    dd.add_source(str(env), "ep1", "extra.csv", "date,entity,value\n2021-02-01,X,5\n2021-03-01,X,7\n", mapping, confirm=True)
    de.duplicate_episode(str(env), "ep1", "copy1")
    trash.delete_episode(str(env), "ep1")
    summary = de._summary("copy1", str(env / "dataviz_episodes" / "copy1"))
    assert summary["valid"], summary.get("errors")                              # קודם: המקור הנוסף הצביע לתיקייה של ep1
    sources = de.load_overrides_for_path(str(env / "dataviz_episodes" / "copy1"))["sources"]
    assert any(os.sep + os.path.join("dataviz_overrides", "copy1") + os.sep in str(s.get("path")) for s in sources)


# ---------- ב3: מקור מכתובת שנכשל ----------
def test_a_failed_url_source_leaves_the_overrides_as_they_were(env):
    def opener(url):
        raise OSError("offline")
    with pytest.raises(de.EpisodeError):
        remote.add_url_source(str(env), "ep1", {"url": "https://example.com/data.csv", "time_column": "date"}, opener=opener)
    assert de.load_overrides_for_path(str(env / "dataviz_episodes" / "ep1")) == {}   # קודם: sources + data.cache_dir
