# tests/studio/test_web_app_wave58_browser.py
#
# גל 58 בדפדפן - סידור הסטודיו: מקום אחד לבחירת סגנון (בלי שבבי "מהירים" בשורת הסטטוס ובלי שבבים בצעד 3 - "⚡ הכי בשימוש"
# בראש הבורר), העזרה בתפריט 🛟 משלה ו-⋯ בשני חלקים עם כותרות, הודעת השחזור כהודעה קופצת כשאין מה להחליט, מסלול הניווט
# מוסתר במצב הפשוט, ו-4 יעדים נפוצים עם "➕ עוד יעדים".


import pytest

from tests.web.test_web_app_wave27_browser import _set_folder, _settle, _studio

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _menu_texts(page, menu_id):
    return page.evaluate(f"() => [...document.querySelectorAll('#{menu_id} button, #{menu_id} label, #{menu_id} .ve-menu-title')].map(e => e.textContent.trim())")


def test_help_has_its_own_menu_and_more_has_two_titled_parts(editor_page):
    page = editor_page
    _studio(page)
    page.click("#veHelpMenuBtn")
    help_items = _menu_texts(page, "veHelpMenu")
    assert any("מקראה" in t for t in help_items) and any("קיצורי מקלדת" in t for t in help_items)
    assert any("סיור" in t for t in help_items) and any("מה חדש" in t for t in help_items)
    page.click("#veViewMenuBtn")
    more = _menu_texts(page, "veViewMenu")
    assert "הפרויקט" in more and "תצוגת ההגדרות" in more
    assert more.index("הפרויקט") < more.index("תצוגת ההגדרות")
    assert not any("מקראה" in t or "סיור" in t for t in more)                 # העזרה לא כפולה
    page.evaluate("() => closeVeMenus()")
    visible = page.evaluate("() => [...document.querySelectorAll('#veStickyBar button')].filter(b => b.offsetParent).length")
    assert visible <= 14, visible   # גל 60: + 🔍 ו-✕


def test_one_place_to_pick_a_style(editor_page):
    page = editor_page
    _studio(page)
    assert page.evaluate("() => !document.getElementById('veProfileChips')")        # אין שבבים בשורת הסטטוס
    page.evaluate("() => setVeMode('simple')")
    _settle(page)
    assert page.evaluate("() => !document.getElementById('veStepStyleChips')")      # צעד 3 - רק המראה
    assert page.is_visible("#vePreset")                                             # הבורר בפס העליון - בכל המצבים


def test_crumbs_hide_in_simple_mode_and_targets_fold(editor_page, tmp_path):
    page = editor_page
    (tmp_path / "a.mp4").write_bytes(b"x")
    _studio(page)
    _set_folder(page, tmp_path)
    page.evaluate("() => { try { localStorage.removeItem('veMoreTargets'); } catch (e) {} _veRenderTargetChips(); }")
    page.wait_for_selector("#veTargetChips .ve-more-targets")
    shown = page.evaluate("() => [...document.querySelectorAll('#veTargetChips button[data-target]')].map(b => b.dataset.target)")
    assert sorted(shown) == ["reels", "shorts", "tiktok", "youtube"], shown
    page.click("#veTargetChips .ve-more-targets")
    assert page.evaluate("() => document.querySelectorAll('#veTargetChips button[data-target]').length") > 4
    page.click("#veTargetChips .ve-more-targets")
    page.evaluate("() => setVeMode('simple')")
    _settle(page)
    assert page.is_hidden("#veCrumbs")
    page.evaluate("() => setVeMode('advanced')")
    _settle(page)
    page.wait_for_function("() => document.querySelectorAll('#veCrumbs .ve-crumb').length > 0")
    assert page.is_visible("#veCrumbs")
