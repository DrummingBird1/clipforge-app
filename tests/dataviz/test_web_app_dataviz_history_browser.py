# tests/dataviz/test_web_app_dataviz_history_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "🕘 היסטוריית גרסאות" מתפריט ⋯ - רשימת הגרסאות, "השוואה" (עכשיו מול הגרסה) ו"↺ שחזר".
# xdist-group: workspace
import json

import pytest

from dataviz.web import episodes as de
from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "היסטוריה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    de.update_override_fields(str(data), "alarms", {"subtitle": "ראשונה"}, [])
    de.update_override_fields(str(data), "alarms", {"subtitle": "שנייה"}, [])
    return data


def test_compare_and_restore_a_version(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolHistory")
    page.wait_for_selector("#dvzHistList tbody tr")
    assert page.locator("#dvzHistList tbody tr").count() == 3
    row = page.locator("#dvzHistList tbody tr").nth(1)
    row.locator("text=השוואה").click()
    page.wait_for_selector("#dvzHistDiff table")
    assert "ראשונה" in page.inner_text("#dvzHistDiff") and "שנייה" in page.inner_text("#dvzHistDiff")
    row.locator("text=שחזר").click()
    page.wait_for_selector("#veConfirmModalBg.show")                                    # האישור - מעל ה-dialog
    assert not (screen / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8").count("ראשונה")   # עוד לא
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.querySelectorAll('#dvzHistList tbody tr').length === 4")
    saved = json.loads((screen / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert saved == {"subtitle": "ראשונה"}
