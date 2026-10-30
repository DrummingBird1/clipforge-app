# tests/studio/test_web_app_wave34_browser.py
#
# גל 34 בדפדפן: שלוש רמות (פשוט / רגיל / מומחה), סדר הלשוניות והלשונית האחרונה לכל פרויקט,
# הספרייה, A/B לצבע, מעבר בין אזורים במקלדת, קיצור ששונה, סיור ו"מה חדש".


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

IDLE = "() => typeof uiPendingWork === 'function' && uiPendingWork() === 0"


def _set(page, element_id, value):
    page.evaluate("([id, v]) => { const el = document.getElementById(id); if (el.type === 'checkbox') el.checked = v; else el.value = v;"
                  " el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }",
                  [element_id, value])
    page.wait_for_function(IDLE)


def _row_shown(page, element_id):
    return page.evaluate("(id) => getComputedStyle(document.getElementById(id).closest('.ve-row')).display !== 'none'", element_id)


def test_regular_hides_rare_settings_until_changed_or_expert(editor_page):
    page = editor_page
    page.evaluate("() => setVeMode('regular')")
    page.wait_for_function(IDLE)
    assert page.evaluate("() => document.getElementById('videoEditorOptions').classList.contains('ve-regular')")
    assert page.get_attribute("#veModeRegularBtn", "aria-pressed") == "true"
    assert page.evaluate("() => document.getElementById('veEqGamma').closest('.ve-row').classList.contains('ve-rare')")
    assert not _row_shown(page, "veEqGamma")
    assert _row_shown(page, "veEqSaturation")   # הגדרה נפוצה נשארת
    assert page.is_visible("#veRareChip") and "מומחה" in page.inner_text("#veRareChip")
    # הגדרה נדירה ששונתה (למשל מפרויקט) תמיד מוצגת
    _set(page, "veEqGamma", "1.2")
    page.wait_for_function("() => getComputedStyle(document.getElementById('veEqGamma').closest('.ve-row')).display !== 'none'")
    # קפיצה לשדה נדיר עוברת למומחה
    _set(page, "veEqGamma", "1")
    page.evaluate("() => _veRevealElement(document.getElementById('veLutIntensity'))")
    assert page.evaluate("() => _veCurrentMode()") == "advanced"
    assert _row_shown(page, "veLutIntensity")


def test_tabs_follow_the_workflow_and_remember_each_project(editor_page, tmp_path):
    page = editor_page
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    set_folder = "(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }"
    # הלשונית נשמרת לפרויקט ב-setTimeout אחרי הלחיצה (78-editor-modes.js): בלי לחכות לה, החלפת התיקייה הבאה
    # קודמת לשמירה, והלשונית נרשמת לפרויקט הלא נכון (2 מתוך 3 נכשלו במחשב עמוס)
    saved_for = "([f, tab]) => _veLoadPref('veTabByProject', {})[f] === tab"
    page.evaluate("() => setVeLayout('tabs')")
    tabs = page.evaluate("() => [...document.querySelectorAll('#veCatTabs button')].map(b => b.dataset.cat)")
    assert tabs[:6] == ["time", "look", "effects", "layers", "sound", "output"]
    page.evaluate(set_folder, str(first))
    page.click("#veCatTabs button[data-cat=sound]")
    page.wait_for_function(saved_for, arg=[str(first), "sound"])
    page.evaluate(set_folder, str(second))
    page.click("#veCatTabs button[data-cat=look]")
    page.wait_for_function(saved_for, arg=[str(second), "look"])
    page.evaluate(set_folder, str(first))
    page.wait_for_function("() => _veLoadPref('veActiveTab', '') === 'sound'")
    page.evaluate(set_folder, str(second))
    page.wait_for_function("() => _veLoadPref('veActiveTab', '') === 'look'")


def test_library_lists_targets_and_toggles_them(editor_page):
    page = editor_page
    page.click("#veLibraryBtn")
    assert page.is_visible("#veLibraryModalBg")
    tabs = page.eval_on_selector_all("#veLibraryTabs button", "els => els.map(b => b.textContent)")
    assert [t.split(" ", 1)[0] for t in tabs] == ["🗂️", "🏷️", "🎯", "📑"]
    page.click("#veLibraryTabs button:nth-child(3)")
    page.wait_for_function("() => document.querySelectorAll('#veLibraryList .ve-library-item').length >= 2")
    page.click("#veLibraryList .ve-library-item:first-child button")
    page.wait_for_function("() => _veTargets().length === 1")
    assert page.evaluate("() => document.querySelector('#veLibraryList .ve-library-item').classList.contains('active')")
    page.click("#veLibraryTabs button:nth-child(4)")   # שכבות מוכנות - רשימה, או הסבר כשאין (אף פעם לא ריק)
    page.wait_for_function("() => document.getElementById('veLibraryList').children.length > 0")
    page.evaluate("() => closeVeLibrary()")
    assert not page.is_visible("#veLibraryModalBg")


def test_look_ab_switches_between_two_versions(editor_page):
    page = editor_page
    _set(page, "veEqSaturation", "1.4")
    page.evaluate("() => toggleVeLookAB()")              # A = 1.4
    _set(page, "veEqSaturation", "0.6")                  # B = 0.6
    page.evaluate("() => toggleVeLookAB()")
    assert page.input_value("#veEqSaturation") == "1.4"
    assert page.evaluate("() => document.getElementById('veLookAbBtn').textContent") == "A/B: A"
    page.evaluate("() => toggleVeLookAB()")
    assert page.input_value("#veEqSaturation") == "0.6"
    page.evaluate("() => clearVeLookAB()")
    assert page.evaluate("() => document.getElementById('veLookAbClearBtn').hidden")


def test_keyboard_moves_between_areas(editor_page):
    page = editor_page
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Alt+3")
    assert page.evaluate("() => document.getElementById('veInspectorTools').parentElement.contains(document.activeElement)")
    page.keyboard.press("Alt+2")
    assert page.evaluate("() => document.getElementById('veViewer').contains(document.activeElement)")


def test_a_changed_shortcut_runs_the_same_action(editor_page):
    page = editor_page
    page.evaluate("() => _veSavePref('veShortcutMap', {search: 'Alt+S'})")
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.keyboard.press("Alt+S")
    assert page.evaluate("() => document.activeElement.id") == "veSearchInput"
    page.evaluate("() => document.activeElement.blur()")
    page.keyboard.press("/")   # הצירוף הישן כבר לא מחפש
    assert page.evaluate("() => document.activeElement.id") != "veSearchInput"
    page.evaluate("() => openVeShortcutsDialog()")
    assert page.evaluate("() => !!document.querySelector('#veShortcutsList tr.ve-shortcut-custom')")
    page.evaluate("() => resetVeShortcuts()")
    assert page.evaluate("() => !document.querySelector('#veShortcutsList tr.ve-shortcut-custom')")


def test_tour_and_whats_new(editor_page):
    page = editor_page
    assert page.evaluate("() => document.getElementById('veHelpMenuBtn').classList.contains('ve-has-news')")   # גל 58: בתפריט העזרה
    page.evaluate("() => openVeWhatsNew()")
    assert "34" in page.inner_text("#veWhatsNewList")
    assert not page.evaluate("() => document.getElementById('veHelpMenuBtn').classList.contains('ve-has-news')")
    page.evaluate("() => { closeVeWhatsNew(); startVeTour(); }")
    assert page.is_visible("#veTour")
    assert page.evaluate("() => document.querySelectorAll('.ve-tour-target').length") == 1
    page.click("#veTourNext")
    assert "2/" in page.inner_text("#veTourTitle")
    page.evaluate("() => endVeTour()")
    assert not page.is_visible("#veTour") and page.evaluate("() => !document.querySelector('.ve-tour-target')")
