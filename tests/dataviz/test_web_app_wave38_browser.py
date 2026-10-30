# tests/dataviz/test_web_app_wave38_browser.py
#
# גל 38 בדפדפן: עורך הגרפים בשלושה אזורים - כרטיסים עם תמונה ותגיות, חיפוש/מיון/סינון, תצוגה חיה עם
# סליידר, רצועת פריימים, השוואת סוגי תרשים ובהיר מול כהה, ואומדן אורך/זמן. הקוד של המסך נטען
# לפי דרישה (uiLoadLazy) - לא ב-bundle הראשי. פריימים בודדים בלבד (matplotlib), בלי ffmpeg.
# xdist-group: workspace


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    small = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **small}, name="alarms")
    write_episode(data / "dataviz_episodes", overrides={"title": "מכוניות", "chart": "line_race", **small}, name="cars")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return {"data": data, "workspace": workspace}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_the_screen_loads_on_demand_in_three_areas(editor_page, screen):
    page = editor_page
    assert page.evaluate("() => typeof loadDataviz") == "undefined"   # לא ב-bundle הראשי
    _open(page)
    assert page.evaluate("() => window.__uiLazyLoaded && window.__uiLazyLoaded.dataviz") is True
    panes = page.eval_on_selector_all(".dvz-studio > .dvz-pane", "els => els.map(e => e.className.split(' ').pop())")
    assert panes == ["dvz-episodes-pane", "dvz-preview-pane", "dvz-settings-pane"]
    assert page.is_visible("#dvzPreviewPane") and page.is_visible("#dvzControls")


def test_cards_have_a_picture_and_badges_and_the_list_filters(editor_page, screen):
    page = editor_page
    _open(page)
    page.wait_for_function("() => document.querySelectorAll('.dvz-card .dvz-card-thumb').length === 2")
    assert "עוד לא הורץ" in page.locator('.dvz-card[data-episode="alarms"] .dvz-card-badges').inner_text()
    page.fill("#dvzSearch", "מכוניות")
    assert page.eval_on_selector_all(".dvz-card", "els => els.map(e => e.dataset.episode)") == ["cars"]
    page.fill("#dvzSearch", "")
    page.select_option("#dvzChartFilter", "bar_race")
    assert page.eval_on_selector_all(".dvz-card", "els => els.map(e => e.dataset.episode)") == ["alarms"]
    page.select_option("#dvzChartFilter", "")
    page.select_option("#dvzSort", "name")
    assert page.eval_on_selector_all(".dvz-card", "els => els.map(e => e.dataset.episode)") == ["alarms", "cars"]


def test_live_preview_follows_the_slider_and_the_strip(editor_page, screen):
    page = editor_page
    _open(page)
    # גל 59: התאריך והזמן בסרטון בטקסט, מספר הפריים בריחוף (title)
    page.wait_for_function("() => document.getElementById('dvzPreviewInfo').title.startsWith('פריים')", timeout=30000)
    first = page.evaluate("() => document.getElementById('dvzPreviewInfo').title")
    page.evaluate("() => { const s = document.getElementById('dvzPreviewPos'); s.value = '0'; s.dispatchEvent(new Event('input')); }")
    page.wait_for_function("(t) => document.getElementById('dvzPreviewInfo').title !== t", arg=first, timeout=30000)
    assert page.evaluate("() => document.getElementById('dvzPreviewInfo').title").startswith("פריים 1 ")
    assert "⏱ 0:00 / " in page.evaluate("() => document.getElementById('dvzPreviewInfo').textContent")
    assert page.evaluate("() => document.querySelectorAll('#dvzStrip button').length") == 10
    page.click("#dvzStrip button:last-child")
    page.wait_for_function("() => document.querySelector('#dvzStrip button:last-child').getAttribute('aria-current') === 'true'")
    assert page.evaluate("() => document.getElementById('dvzPreviewPos').value") == "980"


def test_compare_chart_types_and_themes(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => dvzCompare('charts')")
    assert page.evaluate("() => document.querySelectorAll('#dvzCompareBox figure').length") == 8   # גל 51: גם עוגה; 20.10.2026: גרפים קטנים
    page.evaluate("() => document.querySelectorAll('#dvzCompareBox figure button')[1].click()")   # מרוץ קווים
    assert page.input_value("#dvzChart") == "line_race"
    page.evaluate("() => dvzCompare('themes')")
    assert page.evaluate("() => document.querySelectorAll('#dvzCompareBox figure').length") == 2
    page.evaluate("() => document.querySelectorAll('#dvzCompareBox figure button')[1].click()")   # כהה
    page.wait_for_function("() => typeof dvzEd !== 'undefined' && dvzEd.draft.theme === 'dark'")    # גל 59: טיוטה בעורך המלא
    assert page.evaluate("() => document.getElementById('dvzEditor').open")


def test_estimate_shows_length_and_render_time(editor_page, screen):
    page = editor_page
    _open(page)
    page.select_option("#dvzMode", "full")
    page.wait_for_function("() => document.getElementById('dvzEstimate').textContent.includes('רינדור משוער')", timeout=30000)
    page.select_option("#dvzMode", "preview")
    assert "פריימים" in page.inner_text("#dvzEstimate")
