# tests/studio/test_web_app_studio_nav_browser.py
#
# באג: פתיחת הסטודיו (מצב מיקוד, בלי סרגל ניווט) ואז מעבר למסך אחר דרך Ctrl+K השאיר את הדף בלי סרגל ניווט
# ובלי כותרת - אי אפשר היה לחזור. עכשיו: (1) מעבר מסך מחזיר את הניווט; (2) כפתור ☰ בסטודיו פותח/סוגר את הסרגל
# בלי לצאת מהסטודיו; (3) בחירה בסרגל הפתוח סוגרת אותו.
import os


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

STATE = """() => ({focus: document.body.classList.contains('ve-focus'), open: document.body.classList.contains('ve-nav-open'),
  rail: getComputedStyle(document.querySelector('.nav-rail')).display, top: getComputedStyle(document.querySelector('header.topbar')).display})"""


@pytest.fixture
def home_page(editor_server, edge_browser):
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL")
    page = context.new_page()
    try:
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    except Exception:
        context.close()
        raise
    yield page
    context.close()


def _studio(page):
    page.evaluate("() => { closeVeEditor(); }")
    page.locator(".rail-studio").click()
    page.wait_for_function("() => document.body.classList.contains('ve-focus')")


def test_leaving_the_studio_through_the_palette_brings_the_navigation_back(home_page, tmp_path):
    page = home_page
    _studio(page)
    assert page.evaluate(STATE)["rail"] == "none"
    page.keyboard.press("Control+k")
    page.fill("#paletteInput", "גלריה")
    page.wait_for_selector("#paletteList .ve-palette-active")
    page.keyboard.press("Enter")
    page.wait_for_function("() => !document.querySelector('[data-tab-panel=\"gallery\"]').hidden")
    state = page.evaluate(STATE)
    assert state == {"focus": False, "open": False, "rail": "flex", "top": "flex"}
    page.screenshot(path=str(tmp_path / "after_palette.png"))
    page.locator(".rail-studio").click()                      # וחוזרים לסטודיו מהסרגל
    page.wait_for_function("() => document.body.classList.contains('ve-focus')")


def test_studio_nav_button_opens_and_closes_the_rail_without_leaving_the_studio(home_page, tmp_path):
    page = home_page
    _studio(page)
    button = page.locator("#veNavBtn")
    assert button.is_visible() and button.get_attribute("aria-expanded") == "false"

    button.click()
    state = page.evaluate(STATE)
    assert state["focus"] and state["open"] and state["rail"] == "flex"
    assert page.locator("#veNavBtn").get_attribute("aria-expanded") == "true"
    assert page.locator('.nav-rail .tab-btn[data-tab="gallery"]').is_visible()
    page.screenshot(path=str(tmp_path / "nav_open.png"))

    button.click()
    assert page.evaluate(STATE)["rail"] == "none" and page.evaluate("() => document.body.classList.contains('ve-focus')")

    button.click()
    page.locator('.nav-rail .tab-btn[data-tab="gallery"]').click()           # בחירה בסרגל הפתוח
    page.wait_for_function("() => !document.querySelector('[data-tab-panel=\"gallery\"]').hidden")
    assert page.evaluate(STATE) == {"focus": False, "open": False, "rail": "flex", "top": "flex"}


def test_nav_button_is_keyboard_reachable_and_does_nothing_outside_the_studio(home_page):
    page = home_page
    page.evaluate("() => toggleStudioNav()")
    assert page.evaluate(STATE)["open"] is False
    _studio(page)
    page.locator("#veNavBtn").focus()
    page.keyboard.press("Enter")
    assert page.evaluate(STATE)["rail"] == "flex"

def test_background_polling_pauses_while_the_tab_is_hidden_and_refreshes_on_return(home_page):
    result = home_page.evaluate("""async () => {
      let hidden = true;
      Object.defineProperty(document, 'hidden', {configurable: true, get: () => hidden});
      let calls = 0;
      pollWhenVisible(() => { calls += 1; }, 40);
      await new Promise(r => setTimeout(r, 300));
      const whileHidden = calls;
      hidden = false;
      document.dispatchEvent(new Event('visibilitychange'));
      const onReturn = calls;
      await new Promise(r => setTimeout(r, 300));
      return {whileHidden, onReturn, later: calls};
    }""")
    assert result["whileHidden"] == 0
    assert result["onReturn"] == 1
    assert result["later"] >= 4

def _shots(tmp_path):
    folder = os.environ.get("SHOT_DIR")
    if folder:
        os.makedirs(folder, exist_ok=True)
    return folder or str(tmp_path)


def test_scripts_button_from_the_studio_shows_the_scripts_list_repeatedly(home_page, tmp_path):
    """באג: סטודיו -> ☰ -> "סקריפטים" רק סגר את התפריט והשאיר את הסטודיו; צריך להציג את רשימת הסקריפטים. גם סטודיו -> סקריפטים -> סטודיו -> סקריפטים."""
    page = home_page
    shots = _shots(tmp_path)
    scripts_btn = '.nav-rail .tab-btn[data-tab="scripts"]'
    for round_no in (1, 2):
        _studio(page)
        page.locator("#veNavBtn").click()                                   # פותח את הסרגל מתוך הסטודיו
        assert page.evaluate(STATE)["rail"] == "flex"
        if round_no == 1:
            page.screenshot(path=os.path.join(shots, "1_studio_rail_open.png"))
        page.locator(scripts_btn).click()
        page.wait_for_function("() => !document.body.classList.contains('ve-focus')")
        if round_no == 1:
            page.screenshot(path=os.path.join(shots, "2_after_scripts_click.png"))
        assert page.evaluate(STATE) == {"focus": False, "open": False, "rail": "flex", "top": "flex"}, f"round {round_no}"
        assert page.evaluate("() => state.selectedId") is None
        assert page.locator("#scriptList").is_visible() and page.locator("#scriptList .script-item, #scriptList [data-script-id], #scriptList > *").count() > 0
        assert page.locator("#videoEditorOptions").is_hidden()
        assert page.locator(scripts_btn).evaluate("e => e.classList.contains('active')")


def test_scripts_button_outside_the_studio_still_just_opens_the_scripts_screen(home_page):
    page = home_page
    page.evaluate("() => { closeVeEditor(); switchTab('gallery'); }")
    page.locator('.nav-rail .tab-btn[data-tab="scripts"]').click()
    page.wait_for_function("() => !document.querySelector('.layout[data-tab-panel=\"scripts\"]').hidden")
    assert page.evaluate(STATE)["rail"] == "flex"