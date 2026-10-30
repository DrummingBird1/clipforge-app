# tests/studio/test_web_app_studio_folder_picker_browser.py
#
# 24.10.2026, מנה 2 מסיור השימושיות בסטודיו (ממצא 1): בחלון בחירת התיקייה לא היה שדה נתיב ולא היו תיקיות אחרונות, והוא
# נפתח בתיקיית הבית - לתיקייה בעומק 4 צריך היה 4 לחיצות. עכשיו (89-studio-more.js, נטען כשהסטודיו נפתח): שדה נתיב שמקבל
# הדבקה (גם עם המירכאות של "העתק כנתיב") ו-Enter, שורת "🕘" מ-uiRecent, ופתיחה בתיקיית האב של התיקייה האחרונה. נתיב שלא
# קיים - הודעה בחלון, בלי alert. כשה-bundle לא נטען, החלון עובד כמו קודם, וננסה שוב בפתיחה הבאה.
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
AT = "(name) => (state.browsePath || '').split(/[\\\\/]/).filter(Boolean).pop() === name"


def _open_picker(page):
    page.evaluate("() => { closeBrowser(); openBrowser(); }")
    page.wait_for_selector("#modalBg.show")


def test_the_picker_takes_a_pasted_path_and_offers_recent_folders(editor_page, tmp_path):
    clips, other = tmp_path / "videos" / "clips", tmp_path / "videos" / "other"
    clips.mkdir(parents=True)
    other.mkdir()
    page = editor_page
    alerts = []
    page.on("dialog", lambda dialog: (alerts.append(dialog.message), dialog.dismiss()))
    page.evaluate("(f) => { localStorage.removeItem('uiRecent'); uiRecent.remember('project', f, 'clips'); state.folder = ''; setVeFocus(true); }",
                  str(clips))
    page.wait_for_function(LOADED)
    _open_picker(page)
    page.wait_for_function(AT, arg="videos")                                            # קודם: תיקיית הבית
    assert page.input_value("#modalPathInput").rstrip("\\/").endswith("videos")
    assert page.is_visible("#modalRecent button:has-text('clips')")

    page.fill("#modalPathInput", f'"{other}"')                                           # כמו "העתק כנתיב" בסייר
    page.press("#modalPathInput", "Enter")
    page.wait_for_function(AT, arg="other")
    page.fill("#modalPathInput", str(tmp_path / "missing"))
    page.press("#modalPathInput", "Enter")
    page.wait_for_selector("#modalPathNote:not([hidden])")
    assert alerts == [] and page.evaluate(AT, "other")                                   # נשארים במקום, בלי alert

    page.click("#modalRecent button:has-text('clips')")
    page.wait_for_function(AT, arg="clips")
    page.click("#modalChooseFolderBtn")
    page.wait_for_function("(name) => state.folder.split(/[\\\\/]/).filter(Boolean).pop() === name", arg="clips")


def test_without_the_extras_the_picker_works_as_before_and_they_load_next_time(editor_page):
    page = editor_page
    page.evaluate("""() => { closeVeEditor(); window.__realLazy = uiLoadLazy;
      uiLoadLazy = (name) => name === 'studio_more' ? Promise.reject(new Error('offline')) : window.__realLazy(name); }""")
    assert not page.evaluate(LOADED)
    page.evaluate("() => setVeFocus(true)")
    _open_picker(page)
    page.wait_for_function("() => document.querySelectorAll('#modalList div').length > 0")
    assert page.evaluate("() => !document.getElementById('modalPathInput')")             # החלון הרגיל, בלי התוספות
    page.evaluate("() => { closeBrowser(); closeVeEditor(); uiLoadLazy = window.__realLazy; setVeFocus(true); }")
    page.wait_for_function(LOADED)                                                       # בפתיחה הבאה - נטען
    _open_picker(page)
    page.wait_for_selector("#modalPathInput")
    page.evaluate("() => closeBrowser()")
