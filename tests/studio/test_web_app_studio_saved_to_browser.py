# tests/studio/test_web_app_studio_saved_to_browser.py
#
# 24.10.2026, מנה 3 מסיור השימושיות בסטודיו (ממצא 7): הגיליון "לפני הרצה" הראה רק את תיקיית הקלט, ובתוצאות היה רק 📂 בלי
# נתיב - ומאז תיקיית הייצוא הסרטונים יכולים להיות בכונן אחר. עכשיו "💾 נשמר ב-..." בשניהם (89-studio-more.js), כמו בעורך
# הגרפים, ואזהרה כשתיקיית הייצוא לא זמינה. ההגדרה בקובץ זמני של הטסט (השרת של הטסטים רץ באותו תהליך).
import pytest

from utils.shared import export_dir

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
SHEET_LINE = "() => (document.getElementById('veRunSheetSavedTo') || {textContent: ''}).textContent"


@pytest.fixture
def exports(tmp_path, monkeypatch):
    folder = tmp_path / "exports"
    folder.mkdir()
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.setenv(export_dir.ENV_VAR, str(folder))
    return folder


def test_the_run_sheet_says_where_the_videos_go(editor_page, exports, tmp_path, monkeypatch):
    page = editor_page
    page.evaluate("() => setVeFocus(true)")
    page.wait_for_function(LOADED)
    page.evaluate("() => openVeRunSheet()")
    page.wait_for_function(f"(p) => ({SHEET_LINE})() === '💾 נשמר ב-' + p", arg=str(exports / "studio"))   # קודם: אין
    page.evaluate("() => closeVeRunSheet()")

    monkeypatch.setenv(export_dir.ENV_VAR, str(tmp_path / "unplugged"))
    page.evaluate("() => openVeRunSheet()")
    page.wait_for_function(f"() => ({SHEET_LINE})().includes('תיקיית הייצוא לא זמינה עכשיו')")
    assert "workspace" in page.evaluate(SHEET_LINE)
    page.evaluate("() => closeVeRunSheet()")


def test_the_results_say_where_the_videos_were_saved(editor_page):
    page = editor_page
    page.evaluate("() => setVeFocus(true)")
    page.wait_for_function(LOADED)
    page.evaluate("() => _veShowResults({counts: {files_created: 1}, files: [], output_dir: 'D:\\\\Exports\\\\studio\\\\vertical'})")
    assert page.evaluate("() => document.getElementById('veResultsSavedTo').textContent") == "💾 נשמר ב-D:\\Exports\\studio\\vertical"
