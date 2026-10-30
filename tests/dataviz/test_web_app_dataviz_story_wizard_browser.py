# tests/dataviz/test_web_app_dataviz_story_wizard_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "✨ אשף סיפור" מתפריט ⋯ - שאלה, סוג (השוואה של שניים), "מה ישתנה" (טבלת לפני/אחרי,
# בלי לכתוב) ו"החל" (קובץ השינויים בלבד).
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
    write_episode(data / "dataviz_episodes", overrides={"title": "אשף", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return data


def test_the_wizard_previews_then_applies_a_story_type(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzEpisodeMenuBtn")
    page.click("#dvzStoryWizardBtn")
    page.wait_for_selector("#dvzWizTypes .dvz-wiz-type")
    # 21.10.2026: כלי סיפור אחד - נפתח על ההצעה של העורך החכם (עם הסיבה) ומראה מיד מה ישתנה; אפשר להחליף סוג
    page.wait_for_selector("#dvzWizSuggest:not([hidden])")
    suggested = page.evaluate("() => _dvzWiz.suggest.value")
    assert "🤖" in page.inner_text("#dvzWizSuggest") and page.get_attribute(f"#dvzWizTypes [data-type='{suggested}']", "aria-checked") == "true"
    page.wait_for_function("() => !document.getElementById('dvzWizApplyBtn').disabled || document.querySelector('#dvzWizDiff p')")
    page.fill("#dvzWizQuestion", "מי מול מי?")
    page.click("#dvzWizTypes [data-type='compare']")
    page.wait_for_selector("#dvzWizExtra select[data-pick='1']")
    page.click("#dvzWizPreviewBtn")
    page.wait_for_function("() => document.getElementById('dvzWizDiff').textContent.includes('מי מול מי?')")
    assert "מי מול מי?" in page.inner_text("#dvzWizDiff") and not (screen / "dataviz_overrides" / "alarms.json").exists()
    page.click("#dvzWizApplyBtn")
    page.wait_for_function("() => !document.getElementById('dvzStoryWizard').open")
    saved = json.loads((screen / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert saved["intro"]["question"] == "מי מול מי?" and saved["chart"] == "line_race" and len(saved["focus"]["entities"]) == 2
