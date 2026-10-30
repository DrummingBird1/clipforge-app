# tests/dataviz/test_web_app_wave52_browser.py
#
# גל 52 בדפדפן: לשונית "ניקוי" בחלון הנתונים (מיזוג שמות דומים בלחיצה, פיזור של קפיצה חשודה) ולשונית "מכתובת
# ותזמון" (משימה מתוזמנת לפרק). בלי רשת. קבצי הפרק ו-config.yaml לא משתנים.
# xdist-group: workspace
import hashlib
import json


import pytest
import yaml

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

ROWS = ([("2024-01-%02d" % d, "תל אביב", 10) for d in range(1, 31)] + [("2024-01-%02d" % d, "תל-אביב", 1) for d in range(1, 31)]
        + [("2024-01-%02d" % d, "חיפה", 4) for d in range(1, 31)] + [("2024-01-20", "חיפה", 900)])


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    folder = data / "dataviz_episodes" / "cities"
    folder.mkdir(parents=True)
    workspace.mkdir()
    (folder / "data.csv").write_text("date,city,value\n" + "".join(f"{d},{c},{v}\n" for d, c, v in ROWS), encoding="utf-8")
    config = {"title": "ערים", "video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}, "ranking": {"top_n": 3, "axis_min": 1},
              "sources": [{"path": "data.csv", "time": {"column": "date"}, "value": {"column": "value"}, "entity": {"column": "city"}}]}
    (folder / "config.yaml").write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    from utils.bot import scheduler_store
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "tasks.json"))
    md5 = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    return {"data": data, "folder": folder, "md5": md5}


def _data_tab(page, tab):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("(t) => { dvzData.tab = t; const d = document.getElementById('dvzData'); d.open = true; dvzLoadData(); }", tab)


def _unchanged(screen):
    return {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in screen["folder"].iterdir()} == screen["md5"]


def test_the_cleaning_tab_merges_names_and_spreads_a_jump(editor_page, screen):
    page = editor_page
    _data_tab(page, "clean")
    page.wait_for_selector("#dvzDataBody .dvz-clean-row")
    assert page.get_attribute("#dvzDataBody .dvz-clean-row", "data-names") == "תל אביב|תל-אביב"
    page.click("#dvzDataBody .dvz-clean-row >> text=מזג")
    page.wait_for_function("() => !document.querySelector('#dvzDataBody .dvz-clean-row')")
    over = json.loads((screen["data"] / "dataviz_overrides" / "cities.json").read_text(encoding="utf-8"))
    assert over["entities"]["aliases"] == {"תל-אביב": "תל אביב"}
    page.wait_for_selector("#dvzDataBody .dvz-outliers button[data-action=spread]")
    page.click("#dvzDataBody .dvz-outliers button[data-action=spread]")
    page.wait_for_selector("#dvzDataBody .dvz-fixes li")
    over = json.loads((screen["data"] / "dataviz_overrides" / "cities.json").read_text(encoding="utf-8"))
    assert over["data"]["fixes"] == [{"entity": "חיפה", "date": "2024-01-20", "action": "spread", "days": 30}]
    page.select_option("#dvzMissingSelect", "previous")
    page.wait_for_function("() => document.getElementById('dvzDataStatus').textContent.includes('נשמר')")
    assert json.loads((screen["data"] / "dataviz_overrides" / "cities.json").read_text(encoding="utf-8"))["data"]["missing"] == "previous"
    assert _unchanged(screen)


def test_the_remote_tab_schedules_a_night_render(editor_page, screen):
    page = editor_page
    _data_tab(page, "remote")
    page.wait_for_selector("#dvzDataBody .dvz-schedule-form")
    assert "אין מקור מכתובת" in page.inner_text("#dvzDataBody .dvz-remote")
    page.click("#dvzDataBody .dvz-schedule-form >> text=תזמן")
    page.wait_for_selector("#dvzDataBody .dvz-schedule-task")
    from utils.bot import scheduler_store
    task, = scheduler_store.load_tasks()
    assert task["extra_args"] == ["--episode", "cities", "--mode", "full"] and task["time"] == "03:00"
    assert _unchanged(screen)
