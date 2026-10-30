# tests/web/test_web_app_settings_lazy_browser.py
#
# 23.10.2026: פתיחת "🌐 הגדרות כלליות" טוענת את ה-bundle העצל של ההגדרות, ומה שבו עובד: ערכות הנושא, תיקיית הייצוא.
import pytest

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]


def test_opening_general_settings_loads_its_bundle(editor_page):
    page = editor_page
    assert not page.evaluate("() => !!(window.__uiLazyLoaded || {}).settings")
    page.evaluate("() => { closeVeEditor(); switchTab('globalsettings'); }")
    page.wait_for_function("() => !!(window.__uiLazyLoaded || {}).settings")
    page.wait_for_function("() => document.getElementById('themeSwatches').children.length > 0")
    page.wait_for_function("() => document.getElementById('gsExportInfo').innerText.length > 0")
