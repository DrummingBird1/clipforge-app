# tests/gui/test_rtl_tab_order.py
#
# רגרסיה ל-gui_manager.pyw: CTkTabview מסדר כרטיסיות משמאל לימין לפי סדר
# .add() בלי שום מודעות ל-RTL, אז הכרטיסייה ה"ראשונה" (Dashboard) הייתה
# תמיד יושבת הכי משמאל גם בעברית. תוקן עם .move() אחרי בנייה, ראו
# gui_manager.pyw. בודק את אותו דפוס בבידוד (בלי לבנות את כל ה-GUI האמיתי).


import customtkinter as ctk

from utils.shared.state import state
from utils.shared.i18n import t

TAB_LABELS = ["🎮 לוח בקרה", "🤖 ניהול דיסקורד",
              "⚙️ הגדרות", "🔊 סאונדבורד", "📊 סטטיסטיקות", "⏰ תזמון"]


def _build_and_reorder(language, monkeypatch, root):
    # monkeypatch (לא הקצאה ישירה) כדי ש-state.language יתאפס אוטומטית אחרי
    # הטסט הזה - state הוא singleton משותף לכל קובצי הטסטים בתהליך.
    monkeypatch.setattr(state, "language", language)
    tabview = ctk.CTkTabview(root)
    tabview.pack()
    try:
        names = [t(label) for label in TAB_LABELS]
        for name in names:
            tabview.add(name)

        # אותו דפוס בדיוק כמו ב-build_skeleton() ב-gui_manager.pyw
        if state.language != "en":
            for i, name in enumerate(reversed(names)):
                tabview.move(i, name)

        return list(tabview._segmented_button._value_list), tabview.get(), names[0]
    finally:
        tabview.destroy()


def test_hebrew_moves_dashboard_to_rightmost_but_keeps_it_selected(monkeypatch, shared_tk_root):
    visual_order, selected, dashboard_name = _build_and_reorder("he", monkeypatch, shared_tk_root)
    assert visual_order[-1] == dashboard_name  # index 0 = leftmost, אז rightmost = האחרון ברשימה
    assert selected == dashboard_name


def test_english_keeps_original_order_with_dashboard_leftmost(monkeypatch, shared_tk_root):
    visual_order, selected, dashboard_name = _build_and_reorder("en", monkeypatch, shared_tk_root)
    assert visual_order[0] == dashboard_name
    assert selected == dashboard_name
