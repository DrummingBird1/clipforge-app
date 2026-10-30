# tests/dataviz/test_web_app_dataviz_readability_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "📏 בדיקת קריאות" מתפריט ⋯ - בודקים ל-Shorts, "🔧" מכניס את התיקון לטיוטה
# (לא נשמר), ובדיקה חוזרת עם הטיוטה בלי האזהרה הזו.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 30}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "קריאות", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return data


def test_check_for_shorts_and_stage_the_fix(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    # 21.10.2026: הקריאות ברשימה "✅ לפני רינדור" (הייתה חלון מתפריט ⋯) - נבדקת מיד, ובחירת יעד בודקת שוב
    page.wait_for_selector("#dvzDataBadge:not([hidden])")
    page.click("#dvzDataBadge")
    page.wait_for_selector("#dvzReadTarget option[value='shorts']", state="attached")
    page.wait_for_function("() => { const t = document.getElementById('dvzReadMsg').textContent; return t && !t.startsWith('⏳'); }", timeout=60000)
    page.select_option("#dvzReadTarget", "shorts")
    page.wait_for_function("() => document.getElementById('dvzReadMsg').textContent.includes('1080x1920')", timeout=60000)
    page.wait_for_selector("#dvzReadResults [data-kind='small'] button")
    page.click("#dvzReadResults [data-kind='small'] button")
    assert page.evaluate("() => dvzEd.draft['video.dpi']") > 30
    assert not (screen / "dataviz_overrides" / "alarms.json").exists()            # רק טיוטה
    page.click("#dvzReadCheckBtn")
    page.wait_for_function("() => document.getElementById('dvzReadMsg').textContent.includes('1080x1920')"
                           " && !document.querySelector(\"#dvzReadResults [data-kind='small']\")", timeout=60000)
