# tests/web/test_web_app_frame_browser.py
#
# 23.10.2026: רכיבי המסגרת המשותפים בדפדפן - המפריד הנגרר של הסטודיו (uiSplitter) גם מהמקלדת, עם שמירה; "נפתחו
# לאחרונה" (uiRecent) - תיקייה שנפתחה בסטודיו נרשמת, החלונית בסרגל העליון פותחת פריט, ו-Ctrl+K מציג אותם.
import pytest

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]

SIDE_WIDTH = "() => getComputedStyle(document.getElementById('videoEditorOptions')).getPropertyValue('--ve-side-w').trim()"


def test_dragging_the_splitter_moves_it_by_the_distance_dragged(editor_page):
    # 24.10.2026: הרוחב חושב לפי מיקום העכבר ולא לפי המרחק שגררו - מי שתפס את המפריד בקצה של אזור הגרירה (12px) קיבל
    # קפיצה של כמה פיקסלים כבר בתזוזה הראשונה. כאן: תופסים בכל אחד משני הקצוות, וזזים פיקסל אחד
    page = editor_page
    page.evaluate("() => { localStorage.removeItem('veSideW'); openStudio(); }")
    page.wait_for_function("() => document.querySelector('.ve-resizer[data-panel=side]')?.getAttribute('role') === 'separator'")
    resizer = page.locator(".ve-resizer[data-panel=side]")
    resizer.scroll_into_view_if_needed()
    for grab_at, step, change in ((1, -1, 1), (-1, 1, -1)):    # בעברית העמודה צמודה לימין: שמאלה = רחבה יותר
        before = round(page.evaluate("() => document.querySelector('.ve-side').getBoundingClientRect().width"))
        box = resizer.bounding_box()
        x = box["x"] + (1 if grab_at > 0 else box["width"] - 1)
        y = box["y"] + 40
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + step, y)
        width = page.evaluate(SIDE_WIDTH)
        page.mouse.up()
        assert width == f"{before + change}px", (grab_at, before, width)


def test_the_studio_splitter_works_from_the_keyboard_and_remembers(editor_page):
    page = editor_page
    page.evaluate("() => { localStorage.removeItem('veSideW'); openStudio(); }")
    page.wait_for_function("() => document.querySelector('.ve-resizer[data-panel=side]')?.getAttribute('role') === 'separator'")
    resizer = page.locator(".ve-resizer[data-panel=side]")
    assert resizer.get_attribute("aria-valuemin") == "200" and resizer.get_attribute("aria-valuemax") == "520"
    assert resizer.get_attribute("tabindex") == "0" and resizer.get_attribute("aria-label") == "רוחב עמודת הקבצים"
    before = page.evaluate("() => document.querySelector('.ve-side').getBoundingClientRect().width")
    resizer.focus()
    page.keyboard.press("ArrowLeft")    # בעברית העמודה צמודה לימין: המפריד זז שמאלה והעמודה גדלה
    assert int(page.evaluate(SIDE_WIDTH)[:-2]) == round(before) + 16
    assert page.evaluate("() => JSON.parse(localStorage.getItem('veSideW'))") == round(before) + 16
    page.keyboard.press("Home")
    assert page.evaluate(SIDE_WIDTH) == "200px"
    page.keyboard.press("Shift+End")
    page.keyboard.press("End")
    assert page.evaluate(SIDE_WIDTH) == "520px"
    resizer.dblclick()
    assert page.evaluate(SIDE_WIDTH) == "" and page.evaluate("() => localStorage.getItem('veSideW')") == "0"


def test_recently_opened_lists_and_reopens(editor_page):
    page = editor_page
    page.evaluate("""() => {
      closeVeEditor();
      localStorage.removeItem('uiRecent');
      window.__opened = [];
      uiRecent.register('test', {icon: '🧪', open: (id) => window.__opened.push(id)});
      uiRecent.remember('test', 'first', 'פריט ראשון');
      uiRecent.remember('gone', 'x', 'מאזור שלא רשום');
      uiBus.emit('ve:folder-changed', 'D:\\\\Videos\\\\Trip');
    }""")
    assert page.evaluate("() => uiRecent.list().map(i => [i.kind, i.label, i.icon])") == [
        ["project", "Trip", "📁"], ["test", "פריט ראשון", "🧪"]]

    page.click("#recentBtn")
    page.wait_for_function("() => document.querySelectorAll('#recentMenu .recent-item').length === 2")
    assert page.get_attribute("#recentBtn", "aria-expanded") == "true"
    assert "Trip" in page.locator("#recentMenu .recent-item").nth(0).inner_text()
    page.locator("#recentMenu .recent-item").nth(1).click()
    page.wait_for_function("() => document.getElementById('recentMenu').hidden")
    assert page.evaluate("() => window.__opened") == ["first"]
    assert page.evaluate("() => uiRecent.list()[0].id") == "first"     # מה שנפתח עולה לראש

    page.click("#recentBtn")
    page.wait_for_function("() => !document.getElementById('recentMenu').hidden")
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('recentMenu').hidden")
    assert page.evaluate("() => document.activeElement.id") == "recentBtn"
    palette = page.evaluate("() => uiPaletteProviders.flatMap(p => p()).filter(e => e.section === '🕘 נפתחו לאחרונה').map(e => e.label)")
    assert palette == ["🧪 פריט ראשון", "📁 Trip"]
