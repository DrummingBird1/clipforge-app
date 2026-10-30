# tests/dataviz/test_web_app_dataviz_facts_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): לשונית "🔎 בדיקת עובדות" בחלון הנתונים - תקציר, תיבת הסיום ונקודות המפתח עם שורות המקור,
# ושורה שלא מתאימה מסומנת ❌.
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
    write_episode(data / "dataviz_episodes", overrides={"title": "חתוך", "timeline": {"start": "2020-06-01"}, **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def test_the_fact_check_tab_flags_numbers_that_differ_from_the_files(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    # 21.10.2026: בדיקת העובדות ברשימה "✅ לפני רינדור" (הייתה לשונית בחלון הנתונים); אי-התאמה = ⚠ והפירוט פתוח
    page.wait_for_selector("#dvzDataBadge:not([hidden])")
    page.click("#dvzDataBadge")
    page.wait_for_selector("#dvzPreFacts .dvz-facts-view")
    assert "⚠" in page.inner_text("#dvzPreFacts > .dvz-finding")   # בלי לחכות למקורות - הייבוא של matplotlib במקביל לתצוגה (20.10.2026)
    assert "❌" in page.inner_text(".dvz-facts-view .dvz-finding")
    assert page.locator('.dvz-facts-table tr[data-ok="false"]').count() >= 1
    assert "annual.csv" in page.inner_text(".dvz-facts-view")
