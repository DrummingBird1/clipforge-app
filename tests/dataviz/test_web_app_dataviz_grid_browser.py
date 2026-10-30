# tests/dataviz/test_web_app_dataviz_grid_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "✏️ נתונים" על מקור - עריכת תא, מחיקת שורה, שורה חדשה והדבקה מ-Excel (טאבים), "🔍 בדוק"
# (השוואת סכומים) ו"💾 שמור" - קובץ חדש תחת data/dataviz_overrides/<פרק>/. הקובץ המקורי לא משתנה.
# xdist-group: workspace
import json
import os

import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    folder = write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return {"data": data, "folder": folder}


def test_edit_a_source_in_the_grid_and_save_it_as_a_new_file(editor_page, screen):
    page = editor_page
    original = open(os.path.join(screen["folder"], "annual.csv"), "rb").read()
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { dvzData.tab = 'sources'; const d = document.getElementById('dvzData'); d.open = true; dvzLoadData(); }")
    page.wait_for_selector(".dvz-source .dvz-edit-grid")
    page.locator(".dvz-source .dvz-edit-grid").first.click()
    grid = ".dvz-source >> nth=0 >> .dvz-grid"
    page.wait_for_selector(f"{grid} tbody tr")
    assert page.locator(f"{grid} tbody tr").count() == 2
    cell = page.locator(f"{grid} tbody tr >> nth=0 >> td >> nth=1")
    cell.click()
    page.keyboard.press("Control+a")
    page.keyboard.type("400")
    page.locator(f"{grid} tbody tr >> nth=1 >> button").click()                  # מחיקת 2020
    page.click(".dvz-source >> nth=0 >> text=➕ שורה")
    page.locator(f"{grid} tbody tr >> nth=1 >> td >> nth=0").click()
    page.evaluate(r"""() => { const dt = new DataTransfer(); dt.setData('text/plain', '2021\t500\n2022\t600\n');
        document.activeElement.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }""")
    assert page.locator(f"{grid} tbody tr").count() == 3
    save = ".dvz-source >> nth=0 >> text=💾 שמור כקובץ חדש"
    assert page.is_disabled(save)
    page.click(".dvz-source >> nth=0 >> text=🔍 בדוק שינויים")
    page.wait_for_function("() => document.querySelector('.dvz-grid-status').textContent.includes('←')")
    page.click(save)
    page.wait_for_function("() => document.getElementById('dvzDataStatus').textContent.includes('קובץ חדש')", timeout=20000)
    overrides = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    with open(overrides["sources"][0]["path"], encoding="utf-8") as f:
        assert f.read() == "year,total\n2019,400\n2021,500\n2022,600\n"
    assert open(os.path.join(screen["folder"], "annual.csv"), "rb").read() == original
