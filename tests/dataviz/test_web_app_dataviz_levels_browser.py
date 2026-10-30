# tests/test_web_app_dataviz_levels_browser.py
#
# עורך הגרפים בדפדפן (19.10.2026): שלוש רמות כמו בסטודיו. "פשוט" (ברירת המחדל) מציג רק בסיסי, טקסטים, וידאו ומוזיקה;
# "רגיל" - בלי הקבוצות הנדירות; "מומחה" - הכל. קבוצה עם הגדרה ששונתה מוצגת תמיד, חיפוש מוצא גם בקבוצה מוסתרת,
# והבחירה נשמרת בדפדפן (גם אחרי רענון).
# xdist-group: workspace


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
SIMPLE = ["basic", "texts", "video", "audio"]
RARE = {"series", "brand", "captions", "map", "share", "data"}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return data


def _open_editor(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")


def _visible_groups(page):
    return page.evaluate("() => [...document.querySelectorAll('#dvzEditorBody .dvz-group')]"
                         ".filter(g => g.offsetParent !== null).map(g => g.dataset.group)")


def test_simple_is_the_default_and_shows_only_the_main_groups(editor_page, screen):
    page = editor_page
    page.evaluate("() => localStorage.removeItem('dvzMode')")   # ברירת המחדל (tests/dataviz/conftest.py מתחיל ב"רגיל")
    _open_editor(page)
    assert _visible_groups(page) == SIMPLE
    assert page.get_attribute("#dvzModeSimpleBtn", "aria-pressed") == "true"
    chip = page.inner_text("#dvzRareChip")
    hidden = page.evaluate("() => [...document.querySelectorAll('#dvzEditorBody .dvz-group.dvz-rare .dvz-field')].length")
    assert hidden > 50 and f"עוד {hidden} הגדרות במצב מומחה" in chip
    # חיפוש מוצא גם הגדרה בקבוצה מוסתרת
    page.fill("#dvzFieldSearch", "log_scale")
    assert page.is_visible("#dvzF-ranking-log_scale")
    page.fill("#dvzFieldSearch", "")
    assert page.is_hidden("#dvzF-ranking-log_scale")
    # הצ'יפ עובר למומחה
    page.click("#dvzRareChip")
    assert page.get_attribute("#dvzModeAdvancedBtn", "aria-pressed") == "true"
    assert page.is_hidden("#dvzRareChip")


def test_regular_hides_only_the_rare_groups_and_the_choice_survives_a_reload(editor_page, screen):
    page = editor_page
    _open_editor(page)
    page.click("#dvzModeRegularBtn")
    groups = _visible_groups(page)
    all_groups = page.evaluate("() => [...document.querySelectorAll('#dvzEditorBody .dvz-group')].map(g => g.dataset.group)")
    assert len(all_groups) == 19 and set(groups) == set(all_groups) - RARE
    page.click("#dvzModeAdvancedBtn")
    assert _visible_groups(page) == all_groups
    page.click("#dvzModeRegularBtn")
    page.reload()
    page.wait_for_function("() => typeof switchTab === 'function'")
    _open_editor(page)
    assert page.get_attribute("#dvzModeRegularBtn", "aria-pressed") == "true"
    assert set(_visible_groups(page)) == set(all_groups) - RARE


def test_a_group_with_a_changed_setting_stays_visible_in_simple(editor_page, screen):
    page = editor_page
    page.evaluate("() => localStorage.removeItem('dvzMode')")
    _open_editor(page)
    assert "ranking" not in _visible_groups(page)
    page.evaluate("() => { _dvzStage('ranking.log_scale', true); _dvzRenderEditor(); }")
    assert "ranking" in _visible_groups(page)


def test_simple_hides_the_rest_of_the_screen_until_asked(editor_page, screen):
    # 21.10.2026 (סבב הפישוט): "פשוט" לכל המסך - שינויים להרצה, חלון הנתונים, ההשוואות, פעולות הסדרה ולשוניות העורך
    # מלבד ההגדרות מוסתרים; "רגיל" מחזיר את הכל (הגישה של לפני הסבב). הבורר בסרגל העליון
    page = editor_page
    page.evaluate("() => localStorage.removeItem('dvzMode')")
    _open_editor(page)
    hidden = ["#dvzRunOverrides", "#dvzData", "#dvzPreviewPane .dvz-adv", "#dvzEditorTabs [data-tab='events']"]
    assert all(page.is_hidden(sel) for sel in hidden) and page.is_visible("#dvzEditorTabs [data-tab='fields']")
    assert page.is_visible(".dvz-topbar #dvzModeSimpleBtn") and page.is_visible("#dvzDataBadge") and page.is_visible("#dvzToolsBtn")
    page.click("#dvzModeRegularBtn")
    assert all(page.is_visible(sel) for sel in hidden)
    page.click("#dvzModeSimpleBtn")
    assert page.is_hidden("#dvzData")
