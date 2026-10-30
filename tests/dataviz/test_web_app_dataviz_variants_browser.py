# tests/dataviz/test_web_app_dataviz_variants_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "🧬 גרסאות של הפרק" מתפריט ⋯ - שינוי בטיוטה, "💾 שמור כגרסה" (עם יעד), הטיוטה
# מתרוקנת והבסיס לא משתנה; הגרסה ברשימה.
# xdist-group: workspace
import json

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
    write_episode(data / "dataviz_episodes", overrides={"title": "בסיס", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return data


def test_save_the_draft_as_a_variant(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolVariants")
    page.wait_for_selector("#dvzVarList p")
    page.evaluate("() => _dvzStage('title', 'גרסה קצרה')")
    page.fill("#dvzVarName", "short")
    page.fill("#dvzVarLabel", "קצרה")
    page.select_option("#dvzVarTarget", "shorts")
    page.click("#dvzVarSaveBtn")
    page.wait_for_selector("#dvzVarList tr[data-variant='short']")
    assert "Shorts" in page.inner_text("#dvzVarList tr[data-variant='short']")
    assert page.evaluate("() => Object.keys(dvzEd.draft).length") == 0                       # הטיוטה עברה לגרסה
    saved = json.loads((screen / "dataviz_variants" / "alarms" / "short.json").read_text(encoding="utf-8"))
    assert saved["set"] == {"title": "גרסה קצרה"} and saved["target"] == "shorts"
    assert not (screen / "dataviz_overrides" / "alarms.json").exists()                     # הבסיס לא השתנה
