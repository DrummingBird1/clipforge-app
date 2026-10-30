# tests/web/test_web_app_no_hebrew_flash_browser.py
#
# 31.10.2026: ה-HTML של הדף בעברית וב-RTL, והאנגלית מוחלת רק אחרי שה-JS נטען והמילון מגיע - בממשק האנגלי (וגם בהתקנה חדשה,
# שעוד לא בחרה) העברית הבהבה בכל טעינה (נראה בסרטון ההדגמה). עכשיו הדף מוסתר (05-reset.css) עד ש-_uiLangReady מסמן
# ui-lang-ready: בעברית כבר כשה-JS רץ, באנגלית אחרי התרגום. ב-DOMContentLoaded (אחרי ה-JS, לפני שהמילון מגיע) נבדק מה רואים.
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

AT_LOAD = """document.addEventListener('DOMContentLoaded', () => { window.__atLoad = [
  document.documentElement.classList.contains('ui-lang-ready'), getComputedStyle(document.body).visibility]; });"""
READY = "() => document.documentElement.classList.contains('ui-lang-ready') && getComputedStyle(document.body).visibility === 'visible'"


def _open(editor_server, edge_browser, lang):
    context = edge_browser.new_context(viewport={"width": 1280, "height": 800})
    context.add_init_script(f"localStorage.setItem('uiLang', '{lang}')")
    context.add_init_script(AT_LOAD)
    page = context.new_page()
    page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
    page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    return context, page


def test_the_english_ui_does_not_flash_hebrew_on_load(editor_server, edge_browser):
    context, page = _open(editor_server, edge_browser, "en")
    try:
        assert page.evaluate("() => window.__atLoad") == [False, "hidden"]                      # קודם: גלוי, בעברית
        page.wait_for_function(READY)
        assert page.evaluate("() => [_uiLang, document.documentElement.dir]") == ["en", "ltr"]  # נחשף רק אחרי התרגום
    finally:
        context.close()


def test_the_hebrew_ui_shows_right_away(editor_server, edge_browser):
    context, page = _open(editor_server, edge_browser, "he")
    try:
        assert page.evaluate("() => window.__atLoad") == [True, "visible"]
    finally:
        context.close()
