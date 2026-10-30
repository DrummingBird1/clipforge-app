# tests/dataviz/test_web_app_dataviz_focus_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "בפוקוס" בלשונית הישויות מכניס ישות ל-focus.entities בטיוטה, ו"🔦 החלפת פוקוס"
# בלשונית הסיפור מוסיף החלפה בתאריך.
# xdist-group: workspace
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
    write_episode(data / "dataviz_episodes", overrides={"title": "פוקוס", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def test_focus_from_the_entities_tab_and_a_switch_from_the_story_tab(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorTabs button[data-tab='entities']")
    page.click("#dvzEditorTabs button[data-tab='entities']")
    page.check("input[aria-label='2023 בפוקוס']")
    assert page.evaluate("() => dvzEd.draft['focus.entities']") == ["2023"]
    page.click("#dvzEditorTabs button[data-tab='story']")
    page.click("section[data-list='focus'] >> text=➕")
    page.wait_for_function("() => (dvzEd.draft['story.focus'] || []).length === 1")
