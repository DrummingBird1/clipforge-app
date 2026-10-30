# tests/web/test_web_app_english_default_browser.py
#
# 30.10.2026 (לפני ההפצה הציבורית): בדפדפן בלי בחירת שפה, הדף שואל את השרת. התקנה חדשה (אין config.json) נפתחת באנגלית
# וב-LTR; התקנה קיימת (config.json עם "he", כמו שרת הבדיקה) - בעברית; ובחירה ששמורה בדפדפן גוברת על שתיהן.
import json

import pytest

from utils.shared import install_profile

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LANG = "() => [_uiLang, document.documentElement.dir, localStorage.getItem('uiLang')]"


def _page(editor_server, edge_browser, saved=None):
    context = edge_browser.new_context(viewport={"width": 1280, "height": 800})
    if saved:
        context.add_init_script(f"localStorage.setItem('uiLang', '{saved}')")
    page = context.new_page()
    page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
    page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    return context, page


def test_a_new_install_opens_in_english(editor_server, edge_browser, tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    monkeypatch.setattr(editor_server["web_app"], "CONFIG_FILE", str(config))
    context, page = _page(editor_server, edge_browser)
    try:
        page.wait_for_function("() => _uiLang === 'en' && document.documentElement.dir === 'ltr'", timeout=10000)   # קודם: עברית
        assert page.evaluate(LANG) == ["en", "ltr", "en"]
        # 30.10.2026: באותה כתיבה גם ההגדרות הניטרליות של התקנה חדשה (utils/shared/install_profile)
        assert json.loads(config.read_text(encoding="utf-8")) == {**install_profile.NEW_INSTALL, "language": "en"}
        page.evaluate("() => uiToast('תיקיית הייצוא נשמרה', 'ok')")
        page.wait_for_function("() => document.getElementById('toastHost').textContent.includes('Export folder saved')")
    finally:
        context.close()


def test_an_existing_install_stays_in_hebrew_and_a_saved_choice_wins(editor_server, edge_browser):
    context, page = _page(editor_server, edge_browser)
    try:
        page.wait_for_function("() => localStorage.getItem('uiLang') === 'he'", timeout=10000)
        assert page.evaluate(LANG) == ["he", "rtl", "he"]
    finally:
        context.close()
    context, page = _page(editor_server, edge_browser, saved="en")
    try:
        page.wait_for_function("() => _uiLang === 'en'", timeout=10000)
    finally:
        context.close()
