# tests/dataviz/test_web_app_dataviz_edit_view_layout_browser.py
#
# 23.10.2026, המלצה 8: "✏️ עריכה" (עורך רחב - רשימת הפרקים מתקפלת, ההגדרות רחבות מהתצוגה והעורך נפתח) ו-"👁 צפייה" (רק
# התצוגה החיה, ברוחב מלא) בלחיצה אחת בסרגל העליון; לחיצה נוספת - חזרה לפריסה הרגילה. הבחירה נשמרת לטעינה הבאה.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

_WIDTHS = """() => Object.fromEntries([['episodes', '.dvz-episodes-pane'], ['preview', '#dvzPreviewPane'], ['settings', '#dvzControls']]
    .map(([k, sel]) => [k, Math.round(document.querySelector(sel).getBoundingClientRect().width)]))"""


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", name="alpha")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def _open(page):
    page.set_viewport_size({"width": 1600, "height": 900})
    page.evaluate("() => { localStorage.setItem('dvzMode', 'regular'); localStorage.removeItem('dvzLayout'); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.wait_for_function("() => dvzState.selected === 'alpha' && !document.getElementById('dvzControls').hidden")


def test_edit_and_view_layouts_in_one_click_and_back(editor_page, screen):
    page = editor_page
    _open(page)
    page.click("#dvzLayoutEditBtn")                                             # קודם: אין כפתור כזה
    page.wait_for_function("() => document.getElementById('dvzEditor').open && dvzEd.data")
    edit = page.evaluate(_WIDTHS)
    assert edit["episodes"] == 0 and edit["settings"] > edit["preview"] * 1.3, edit   # עורך רחב
    assert page.get_attribute("#dvzLayoutEditBtn", "aria-pressed") == "true"
    page.click("#dvzLayoutViewBtn")
    view = page.evaluate(_WIDTHS)
    studio = page.evaluate("() => Math.round(document.querySelector('.dvz-studio').getBoundingClientRect().width)")
    assert view["episodes"] == 0 and view["settings"] == 0 and view["preview"] >= studio - 2, (view, studio)   # רק התצוגה
    page.click("#dvzLayoutViewBtn")                                             # לחיצה נוספת - חזרה
    assert page.evaluate("() => document.querySelector('.dvz-studio').dataset.layout") is None
    assert page.evaluate(_WIDTHS)["settings"] > 0


def test_the_layout_is_kept_for_the_next_load(editor_page, screen):
    page = editor_page
    _open(page)
    page.click("#dvzLayoutViewBtn")
    page.reload()
    page.wait_for_function("() => typeof switchTab === 'function'")
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_function("() => document.querySelector('.dvz-studio') && document.querySelector('.dvz-studio').dataset.layout === 'view'")
    assert page.get_attribute("#dvzLayoutViewBtn", "aria-pressed") == "true"
