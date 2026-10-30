# tests/dataviz/test_web_app_dataviz_script_draft_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "🎙 תסריט קריינות" בלשונית הסיפור - "✨ טיוטה מהנתונים" ממלא שורות בטיוטה (כאן בלי
# Gemini: הקריאה נכשלת והטיוטה מקומית), ו"שמור" כותב story.script לקובץ השינויים.
# xdist-group: workspace
import json

import pytest

from dataviz.web import narration_draft

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "תסריט", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))

    def no_gemini(prompt):   # אף פעם לא Gemini אמיתי מטסט
        raise RuntimeError("no gemini in tests")
    monkeypatch.setattr(narration_draft, "_gemini", no_gemini)
    return data


def test_the_draft_button_fills_the_script_and_save_writes_it(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorTabs button[data-tab='story']")
    page.click("#dvzEditorTabs button[data-tab='story']")
    page.click("#dvzScriptDraftBtn")
    page.wait_for_function("() => (dvzEd.draft['story.script'] || []).length > 1")
    assert "טיוטה מקומית" in page.inner_text("#dvzEditorStatus")
    rows = page.locator("section[data-list='script'] tbody tr")
    assert rows.count() == len(page.evaluate("() => dvzEd.draft['story.script']"))
    assert not (screen / "dataviz_overrides" / "alarms.json").exists()            # רק טיוטה עד "שמור"
    page.evaluate("() => dvzSaveDraft()")
    page.wait_for_function("() => !Object.keys(dvzEd.draft).length")
    saved = json.loads((screen / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert any(line["text"].startswith("בסוף:") for line in saved["story"]["script"])
