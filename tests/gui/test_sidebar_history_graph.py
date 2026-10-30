# tests/gui/test_sidebar_history_graph.py
#
# בודק את גרף "ניצולת לאורך זמן" (item 17) ב-ui/sidebar.py - עד כה היו רק
# מדי-אחוזים רגעיים, בלי שום דרך לראות מגמה (למשל דליפת RAM הדרגתית) בלי
# להריץ כלי ניטור חיצוני.


from utils.shared.state import state
from ui.sidebar import SidebarComponent


def _make_sidebar(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "selected_script", None)
    monkeypatch.setattr(state, "favorite_scripts_csv", "")
    comp = SidebarComponent(shared_tk_root, on_script_select=lambda path: None)
    # shared_tk_root נשאר withdraw()-ed לכל הטסטים (בכוונה - ראו conftest.py) -
    # widget בתוך root שלא נמפה אף פעם למסך לא מקבל winfo_width/height אמיתיים
    # מ-geometry management, גם עם pack()+update_idletasks(). כדי לבדוק את
    # לוגיקת הציור עצמה (לא את Tk's geometry propagation, שלא רלוונטי כאן),
    # ממקמים ישירות מידות קבועות על ה-canvas הספציפי הזה בלבד.
    comp.history_canvas.winfo_width = lambda: 240
    comp.history_canvas.winfo_height = lambda: 60
    return comp


def test_draws_cpu_and_ram_lines_without_gpu(shared_tk_root, monkeypatch):
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        comp._draw_history_graph([10, 20, 30, 40], [50, 60, 70, 80], None)
        # קו לכל סדרה (CTk Canvas.create_line יוצר item בודד לכל קריאה, גם עם
        # smooth=True) - שתי סדרות (CPU+RAM) בלי GPU = בדיוק 2 items.
        assert len(comp.history_canvas.find_all()) == 2
    finally:
        comp.destroy()


def test_draws_gpu_line_too_when_history_provided(shared_tk_root, monkeypatch):
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        comp._draw_history_graph([10, 20, 30, 40], [50, 60, 70, 80], [5, 15, 25, 35])
        assert len(comp.history_canvas.find_all()) == 3
    finally:
        comp.destroy()


def test_redraw_clears_previous_lines(shared_tk_root, monkeypatch):
    # רגרסיה אפשרית: בלי canvas.delete("all") בתחילת _draw_history_graph, כל
    # טיק היה מוסיף עוד קווים על גבי הקודמים במקום להחליף אותם - "מריחה"
    # שהולכת ומצטברת עם הזמן.
    comp = _make_sidebar(shared_tk_root, monkeypatch)
    try:
        comp._draw_history_graph([10, 20], [50, 60], None)
        comp._draw_history_graph([10, 20], [50, 60], None)
        comp._draw_history_graph([10, 20], [50, 60], None)
        assert len(comp.history_canvas.find_all()) == 2
    finally:
        comp.destroy()


def test_does_not_draw_before_canvas_has_real_dimensions(shared_tk_root, monkeypatch):
    # לפני ה-map הראשון (winfo_width/height עדיין 1) - לא אמור לזרוק, פשוט
    # לא מצייר כלום ומחכה לטיק הבא.
    monkeypatch.setattr(state, "selected_script", None)
    monkeypatch.setattr(state, "favorite_scripts_csv", "")
    comp = SidebarComponent(shared_tk_root, on_script_select=lambda path: None)
    try:
        comp.history_canvas.winfo_width = lambda: 1
        comp.history_canvas.winfo_height = lambda: 1
        comp._draw_history_graph([10, 20], [50, 60], None)
        assert len(comp.history_canvas.find_all()) == 0
    finally:
        comp.destroy()
