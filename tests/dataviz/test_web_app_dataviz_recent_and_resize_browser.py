# tests/dataviz/test_web_app_dataviz_recent_and_resize_browser.py
#
# 23.10.2026 (המלצות 6-7): עורך הגרפים מחובר לרכיבי המסגרת המשותפים (#58).
# - "נפתחו לאחרונה" (uiRecent): פרק שבוחרים נרשם, והפרק שנבחר לבד כשנכנסים למסך לא נרשם. הסוג רשום בדף הראשי, כך שהפרקים
#   מופיעים גם לפני שהמסך נטען, ולחיצה על פרק פותחת את המסך עליו.
# - גבולות נגררים (uiSplitter) בין רשימת הפרקים, התצוגה החיה וההגדרות: מהמקלדת ובגרירה, עם שמירה, ומוסתרים בפריסת "צפייה".
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VISIBLE_SPLITTERS = "() => [...document.querySelectorAll('.dvz-splitter')].filter(h => h.offsetParent).map(h => h.dataset.when)"


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אלפא"}, name="alpha")
    write_episode(data / "dataviz_episodes", overrides={"title": "בטא"}, name="beta")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))


def _open(page, clear):
    page.evaluate(f"() => {{ for (const k of {clear}) localStorage.removeItem(k); localStorage.setItem('dvzMode', 'regular'); "
                  "closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card[data-episode='beta']")
    page.wait_for_function("() => dvzState.selected === 'alpha'")


def test_an_opened_episode_is_listed_under_recently_opened_and_reopens(editor_page, screen):
    page = editor_page
    _open(page, ["uiRecent"])
    assert page.evaluate("() => uiRecent.list().filter(i => i.kind === 'dataviz')") == []   # הראשון נבחר לבד - לא נרשם
    page.click("#dvzEpisodes .dvz-card[data-episode='beta']")
    page.wait_for_function("() => uiRecent.list().some(i => i.kind === 'dataviz' && i.id === 'beta' && i.label === 'בטא')")   # קודם: כלום

    page.reload()   # דף חדש: עורך הגרפים עוד לא נטען, והפרק כבר ברשימה
    page.wait_for_function("() => typeof uiRecent !== 'undefined' && typeof closeVeEditor === 'function'")
    page.evaluate("() => closeVeEditor()")
    assert page.evaluate("() => uiRecent.list().filter(i => i.kind === 'dataviz').map(i => i.icon + ' ' + i.label)") == ["📊 בטא"]
    page.click("#recentBtn")
    page.click("#recentMenu button:has-text('בטא')")
    page.wait_for_function("() => typeof dvzState !== 'undefined' && dvzState.selected === 'beta'")
    assert page.inner_text("#dvzTopbarEpisode").endswith("בטא")


def test_the_columns_have_draggable_borders_that_remember(editor_page, screen):
    page = editor_page
    _open(page, ["dvzEpisodesW", "dvzSettingsW", "dvzEditorW", "dvzLayout"])
    page.wait_for_function(f"() => ({VISIBLE_SPLITTERS})().join() === 'any,normal'")    # קודם: אין מפרידים
    episodes = page.locator(".dvz-splitter[data-when=any]")
    assert episodes.get_attribute("role") == "separator" and episodes.get_attribute("aria-label") == "רוחב רשימת הפרקים"

    before = page.evaluate("() => document.querySelector('.dvz-episodes-pane').getBoundingClientRect().width")
    episodes.focus()
    page.keyboard.press("ArrowLeft")    # בעברית הרשימה צמודה לימין: המפריד זז שמאלה והרשימה גדלה
    page.wait_for_function("(w) => Math.round(document.querySelector('.dvz-episodes-pane').getBoundingClientRect().width) === w",
                           arg=round(before) + 16)
    assert page.evaluate("() => JSON.parse(localStorage.getItem('dvzEpisodesW'))") == round(before) + 16

    settings = page.locator(".dvz-splitter[data-when=normal]")
    pane_width = "() => document.querySelector('.dvz-settings-pane').getBoundingClientRect().width"
    start = page.evaluate(pane_width)
    box = settings.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + 40
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 30, y)
    page.mouse.move(x + 60, y)
    page.mouse.up()     # ההגדרות בצד שמאל: גרירה ימינה מרחיבה אותן
    # עד 8: uiSplitter מודד מהעכבר עצמו, והמפריד באמצע הרווח (6px מהגבול) - התפיסה מוסיפה עד חצי רווח
    page.wait_for_function(f"() => Math.abs(({pane_width})() - {start + 60}) <= 8")
    saved = page.evaluate("() => JSON.parse(localStorage.getItem('dvzSettingsW'))")
    assert abs(saved - (start + 60)) <= 8
    # המפריד זז עם הגבול - באמצע הרווח שבין התצוגה החיה להגדרות
    page.wait_for_function("""() => { const h = document.querySelector('.dvz-splitter[data-when=normal]').getBoundingClientRect();
      const s = document.querySelector('.dvz-settings-pane').getBoundingClientRect(); return Math.abs(h.left + h.width / 2 - s.right) <= 12; }""")

    page.evaluate("() => dvzSetLayout('view')")
    page.wait_for_function(f"() => ({VISIBLE_SPLITTERS})().length === 0")             # בצפייה יש עמודה אחת
    page.evaluate("() => dvzSetLayout('view')")                                         # לחיצה שנייה - חזרה לפריסה הרגילה
    page.reload()
    page.wait_for_function("() => typeof closeVeEditor === 'function'")
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_function(f"() => ({VISIBLE_SPLITTERS})().join() === 'any,normal'")
    assert abs(page.evaluate(pane_width) - saved) <= 2                                    # הרוחב נשמר
