# tests/web/test_web_app_wave60_browser.py
#
# גל 60 בדפדפן - מה שמשותף לסטודיו ולעורך הגרפים: 🔍 שפותח את החיפוש הכללי (Ctrl+K) בסרגל של שניהם, "✕ סגור" גלוי בסוף
# הסרגל בשניהם, ושבב שמראה ריצה של הכלי השני (התור משותף) ועובר אליו בלחיצה.
# xdist-group: workspace


import pytest

from tests.dataviz_helpers import write_episode
from tests.web.test_web_app_wave27_browser import _studio

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def _progress(page, pct):
    page.evaluate("(p) => document.dispatchEvent(new CustomEvent('cf-progress', {detail: {pct: p}}))", pct)


def test_search_and_close_sit_in_the_same_place_in_both(editor_page, screen):
    page = editor_page
    _studio(page)
    last = page.evaluate("() => [...document.querySelectorAll('#veStickyBar .ve-topbar-row > *')].filter(e => e.offsetParent).pop().id")
    assert last == "veFocusBtn"                                        # "סגור" בסוף הסרגל, כמו בעורך הגרפים
    page.evaluate("() => openCommandPalette = (orig => () => { window.__paletteOpened = true; })(openCommandPalette)")
    page.click("#veSearchAllBtn")
    assert page.evaluate("() => window.__paletteOpened") is True
    page.click("#veFocusBtn")
    page.wait_for_function("() => !document.body.classList.contains('ve-focus')")
    page.evaluate("() => { window.__paletteOpened = false; switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzSearchAllBtn")
    assert page.evaluate("() => window.__paletteOpened") is True


def test_a_run_of_one_tool_shows_in_the_other(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    # ריצה של עורך הגרפים: לא בסרגל שלו, כן בסטודיו
    page.evaluate("() => uiMarkRunOwner('dataviz', '📊 עורך הגרפים')")
    _progress(page, 42)
    assert page.is_hidden("#dvzOtherRunChip")
    page.evaluate("() => openStudio()")
    page.wait_for_function("() => document.body.classList.contains('ve-focus')")
    assert page.is_visible("#veOtherRunChip") and "42%" in page.inner_text("#veOtherRunChip")
    page.click("#veOtherRunChip")                                      # לחיצה עוברת לכלי שמריץ
    page.wait_for_function("() => document.body.classList.contains('dvz-focus')")
    page.evaluate("() => document.dispatchEvent(new CustomEvent('cf-finished', {detail: {success: true}}))")
    page.evaluate("() => openStudio()")
    assert page.is_hidden("#veOtherRunChip")
    # ריצה של הסטודיו: מופיעה בעורך הגרפים
    page.evaluate("() => uiMarkRunOwner('studio', '🎬 סטודיו')")
    _progress(page, 7)
    assert page.is_hidden("#veOtherRunChip")
    page.evaluate("() => switchTab('dataviz')")
    assert page.is_visible("#dvzOtherRunChip") and "7%" in page.inner_text("#dvzOtherRunChip")
    page.evaluate("() => document.dispatchEvent(new CustomEvent('cf-finished', {detail: {success: true}}))")
    assert page.is_hidden("#dvzOtherRunChip")
