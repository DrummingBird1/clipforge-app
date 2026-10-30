# tests/dataviz/test_web_app_wave50_browser.py
#
# גל 50 בדפדפן: לשונית "📖 סיפור" בעורך המלא (ב-bundle השני של המסך) - הוספת פרק ותקופה, הטיוטה מוצגת בתצוגה
# החיה, ו"שמור" כותב לקובץ השינויים. config.yaml של הפרק לא משתנה.
# xdist-group: workspace
import hashlib
import json


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", "video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"data": data, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def test_the_story_tab_adds_a_chapter_and_a_period_and_saves(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    assert page.evaluate("() => window.__uiLazyLoaded.dataviz_pro && window.__uiLazyLoaded.dataviz_tools") is True   # שלושת ה-bundles נטענים עם המסך (20.10)
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.click("#dvzEditorTabs button[data-tab=story]")
    page.wait_for_selector(".dvz-story-list[data-list=chapters]")
    page.click(".dvz-story-list[data-list=chapters] >> text=הוסף")
    title = page.locator(".dvz-story-list[data-list=chapters] input[aria-label='כותרת']")
    title.fill("החלק השני")
    page.click(".dvz-story-list[data-list=periods] >> text=הוסף")
    page.locator(".dvz-story-list[data-list=periods] input[aria-label='שם']").fill("מלחמה")
    draft = page.evaluate("() => dvzEd.draft")
    assert draft["story.chapters"][0]["title"] == "החלק השני" and draft["story.periods"][0]["label"] == "מלחמה"
    assert "story.chapters" in page.evaluate("() => _dvzDraftParam()")       # הטיוטה נשלחת לתצוגה החיה
    page.click("#dvzDraftSave")
    page.wait_for_function("() => !Object.keys(dvzEd.draft).length && dvzEd.data && dvzEd.data.story.chapters.length === 1")
    over = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert over["story"]["chapters"][0]["title"] == "החלק השני" and over["story"]["periods"][0]["label"] == "מלחמה"
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
