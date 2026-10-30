# tests/studio/test_web_app_studio_tour_fixes_browser.py
#
# 24.10.2026: מנה 1 מסיור השימושיות בסטודיו (23.10, ‏studio-usability-tour-2026-10-23.md), הממצאים שלא דורשים החלטה:
# 5 - השורה של "🎬 קטע" נשארה מהתיקייה הקודמת; 4 - פס הסטטוס אמר "אופקי 16:9" כשהיעד Shorts; 14 - התווית של אזור הכפתורים
# בצד נשברה למילה בכל שורה; 13 - חלונית האזהרות נשארה פתוחה מעל ההגדרות; 10 - ⋯ עם כפולים, והתצוגה מעורבבת בפעולות.
import pytest

from tests.web.test_web_app_wave27_browser import _settle, _studio

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

SUMMARY = "() => document.getElementById('veSummaryText').textContent"


def test_the_clip_status_line_clears_when_the_folder_changes(editor_page):
    page = editor_page
    page.evaluate("""() => { document.getElementById('vePreviewStatus').textContent = '✓ round_1.mp4 · 🎬 0:00–0:05 בפלט';
      document.getElementById('vePreviewNotes').innerHTML = '<li>הערה</li>'; uiBus.emit('ve:folder-changed', 'C:\\\\other'); }""")
    assert page.evaluate("() => document.getElementById('vePreviewStatus').textContent") == ""   # קודם: round_1 מהתיקייה הקודמת
    assert page.evaluate("() => document.getElementById('vePreviewNotes').children.length") == 0


def test_the_status_bar_follows_the_target_shape(editor_page):
    page = editor_page
    page.wait_for_selector("#veTargetChips button[data-target=shorts]")
    page.evaluate("() => _applyVideoEditorFields({vertical: false, targets: []})")
    page.wait_for_function(f"() => ({SUMMARY})().includes('אופקי 16:9')")
    page.click("#veTargetChips button[data-target=shorts]")
    page.wait_for_function(f"() => ({SUMMARY})().includes('אנכי 9:16')")              # קודם: "אופקי 16:9" - ההגדרה הכללית
    assert "אופקי" not in page.evaluate(SUMMARY)
    page.click("#veTargetChips button[data-target=youtube]")
    page.wait_for_function(f"() => ({SUMMARY})().includes('2 יעדים')")                # שני יעדים - כל אחד בצורה שלו
    page.evaluate("() => _applyVideoEditorFields({targets: []})")


def test_a_tall_safe_zone_label_reads_on_one_line(editor_page):
    page = editor_page
    page.evaluate("() => { document.getElementById('veSafeZones').value = 'shorts'; applyVeSafeZones(); }")
    labels = page.evaluate("""() => [...document.querySelectorAll('#veSafeZonesOverlay span')].map(s => ({text: s.textContent,
      mode: getComputedStyle(s).writingMode, wrap: getComputedStyle(s).whiteSpace}))""")
    side = next(label for label in labels if label["text"] == "לייק / תגובה / שיתוף")
    assert side["mode"] == "vertical-rl"                                                 # קודם: אופקית, נשברה למילה בשורה
    assert all(label["wrap"] == "nowrap" for label in labels)
    page.evaluate("() => { document.getElementById('veSafeZones').value = ''; applyVeSafeZones(); }")


def test_the_warnings_popover_closes_like_a_menu(editor_page):
    page = editor_page
    _studio(page)
    page.evaluate("() => _applyVideoEditorFields({keep_audio: false, loudnorm: true})")   # אזהרה אמיתית: נרמול בלי שמע
    page.wait_for_selector("#veWarningsToggle:not([hidden])")
    hidden = "() => document.getElementById('veWarningsBox').hidden"
    page.click("#veWarningsToggle")
    page.wait_for_function(f"() => !({hidden})()")
    page.click("#veSummaryText")                                                         # לחיצה מחוץ לחלונית
    page.wait_for_function(hidden)                                                       # קודם: נשארה פתוחה
    page.click("#veWarningsToggle")
    page.wait_for_function(f"() => !({hidden})()")
    page.keyboard.press("Escape")
    page.wait_for_function(hidden)
    assert page.evaluate("() => document.body.classList.contains('ve-focus')")          # Escape סגר רק את החלונית
    page.evaluate("() => _applyVideoEditorFields({loudnorm: false})")


def test_the_more_menu_has_no_duplicates_and_folds_the_view_options(editor_page):
    page = editor_page
    _studio(page)
    _settle(page)
    page.click("#veViewMenuBtn")
    items = page.evaluate("() => [...document.querySelectorAll('#veViewMenu button, #veViewMenu label')].map(e => e.textContent.trim())")
    for duplicate in ("תוצאות הריצה האחרונה", "ספרייה", "רק מה ששיניתי"):                 # כבר במסך: מרכז הריצות, ליד החיפוש
        assert not any(duplicate in item for item in items), duplicate
    assert not page.is_visible("#veViewMenu >> text=מצב צפוף")                          # מקופל בתת-תפריט
    page.click("#veViewMenu summary")
    assert page.is_visible("#veViewMenu >> text=מצב צפוף")
    assert page.is_visible("#veViewMenu >> text=היסטוריית שינויים")                     # פעולות הפרויקט נשארו בחוץ
    page.evaluate("() => closeVeMenus()")
