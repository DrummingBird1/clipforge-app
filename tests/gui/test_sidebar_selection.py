# tests/gui/test_sidebar_selection.py
#
# רגרסיה: בחירת סקריפט בסיידבר הייתה קוראת ל-_render_buttons (הורס+בונה מחדש
# את כל רשימת הכפתורים) בכל לחיצה, כדי שהדגשת "הסקריפט הנבחר" תתעדכן - עם
# הרבה סקריפטים/קטגוריות זה הורגש כ"קיפאון" רגעי של כל הסיידבר בכל החלפה.
# הבדיקות כאן מוודאות שההדגשה מתעדכנת בלי לקרוא ל-_render_buttons שוב, ושהיא
# מסונכרנת גם כשהבחירה קרתה דרך נתיב אחר (Command Palette/"הרץ שוב") ולא
# דרך לחיצה על כפתור בסיידבר עצמו.


from utils.shared.state import state, PALETTE
from ui.sidebar import SidebarComponent


def _make_sidebar(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "selected_script", None)
    monkeypatch.setattr(state, "favorite_scripts_csv", "")
    comp = SidebarComponent(shared_tk_root, on_script_select=lambda path: setattr(state, "selected_script", path))
    return comp


def test_selecting_script_highlights_it_without_full_rerender(shared_tk_root, monkeypatch):
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        assert len(comp.all_scripts) >= 2, "בדיקה זו דורשת לפחות 2 סקריפטים אמיתיים תחת my_scripts/"
        first, second = comp.all_scripts[0], comp.all_scripts[1]

        rerender_calls = []
        original_render = comp._render_buttons
        monkeypatch.setattr(comp, "_render_buttons", lambda *a, **kw: (rerender_calls.append(1), original_render(*a, **kw))[1])

        comp._select_script(first)
        assert state.selected_script == first
        assert comp._script_buttons[first][0].cget("fg_color") == state.current_theme["accent"]

        comp._select_script(second)
        assert state.selected_script == second
        assert comp._script_buttons[second][0].cget("fg_color") == state.current_theme["accent"]
        # הכפתור הקודם חוזר לצבע הרגיל, לא נשאר "תקוע" מודגש
        assert comp._script_buttons[first][0].cget("fg_color") == PALETTE["border_dim2"]

        assert rerender_calls == [], "בחירת סקריפט לא אמורה לקרוא ל-_render_buttons בכלל"
    finally:
        comp.destroy()


def test_refresh_selection_highlight_syncs_when_selection_changed_externally(shared_tk_root, monkeypatch):
    # מדמה בחירה שקרתה דרך Command Palette/"הרץ שוב" - state.selected_script
    # משתנה ישירות, בלי לעבור דרך comp._select_script בכלל.
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        first, second = comp.all_scripts[0], comp.all_scripts[1]

        comp._select_script(first)
        state.selected_script = second  # שינוי "חיצוני", לא דרך הסיידבר
        comp.refresh_selection_highlight()

        assert comp._script_buttons[second][0].cget("fg_color") == state.current_theme["accent"]
        assert comp._script_buttons[first][0].cget("fg_color") == PALETTE["border_dim2"]
    finally:
        comp.destroy()


def test_refresh_selection_highlight_is_noop_when_unchanged(shared_tk_root, monkeypatch):
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        first = comp.all_scripts[0]
        comp._select_script(first)

        calls = []
        monkeypatch.setattr(comp, "_update_button_highlight", lambda path: calls.append(path))
        comp.refresh_selection_highlight()  # שום שינוי ב-state.selected_script מאז
        assert calls == []
    finally:
        comp.destroy()


def test_script_row_favorite_star_sits_on_the_right_in_rtl_order(shared_tk_root, monkeypatch):
    # רגרסיה: כוכב המועדפים היה ארוז עם side="left" בזמן שכפתור הסקריפט עצמו
    # ארוז עם side="right" - בקריאה מימין-לשמאל סמן מוביל כמו כוכב אמור לשבת
    # בקצה הימני (איפה שקריאה עברית מתחילה), לא בקצה השמאלי.
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        first = comp.all_scripts[0]
        script_button = comp._script_buttons[first][0]
        row = script_button.master
        siblings = [w for w in row.winfo_children() if w is not script_button]
        assert len(siblings) == 1, "אמור להיות בדיוק עוד widget אחד בשורה - כפתור הכוכב"
        star_button = siblings[0]

        assert script_button.pack_info()["side"] == "left"
        assert star_button.pack_info()["side"] == "right"
    finally:
        comp.destroy()
