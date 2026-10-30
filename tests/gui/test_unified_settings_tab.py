# tests/gui/test_unified_settings_tab.py
#
# בודק את מנגנון בורר תת-המדורים (עיצוב/כללי/Rocket Shorts) של טאב "⚙️ הגדרות"
# המאוחד - .winfo_manager() (לא .winfo_ismapped()) כי הטסט רץ מול shared_tk_root
# מוסתר (withdraw) ומיפוי אמיתי-על-מסך לא אמין בתרחיש כזה; winfo_manager()
# משקף במדויק את מה ש-_show_section עצמו קובע (pack מול pack_forget).


import pytest

from utils.shared.state import DEFAULT_UI_SETTINGS
from ui.unified_settings_tab import UnifiedSettingsTabComponent
import ui.rocket_settings_tab as rocket_settings_tab


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    # drop_target_register() דורש ש-TkinterDnD._require() ירוץ קודם על ה-root
    # הספציפי (LauncherApp.__init__ עושה את זה בפועל) - shared_tk_root של הטסטים
    # הוא ctk.CTk() רגיל בלי זה, אז ההרשמה הייתה נכשלת ב-TclError. זה בדיוק
    # אותו מסלול-קוד נתמך שכבר קיים כש-tkinterdnd2 לא מותקן בכלל (see: except
    # ImportError ב-ui/rocket_settings_tab.py) - לא נוגע בקוד המוצר עצמו.
    monkeypatch.setattr(rocket_settings_tab, "_DND_AVAILABLE", False)


class _FakeApp:
    def __init__(self):
        self.ui_settings = dict(DEFAULT_UI_SETTINGS)

    def play_ui_sound(self):
        pass

    def log_message(self, *args, **kwargs):
        pass


def test_unified_settings_tab_starts_on_style_section(shared_tk_root):
    comp = UnifiedSettingsTabComponent(shared_tk_root, _FakeApp())
    try:
        assert comp.style_comp.winfo_manager() == "pack"
        assert comp.global_comp.winfo_manager() == ""
        assert comp.rocket_comp.winfo_manager() == ""
    finally:
        comp.destroy()


def test_unified_settings_tab_switches_sections(shared_tk_root):
    comp = UnifiedSettingsTabComponent(shared_tk_root, _FakeApp())
    try:
        comp._show_section("rocket")
        assert comp.rocket_comp.winfo_manager() == "pack"
        assert comp.style_comp.winfo_manager() == ""

        comp._show_section("global")
        assert comp.global_comp.winfo_manager() == "pack"
        assert comp.rocket_comp.winfo_manager() == ""
    finally:
        comp.destroy()


def test_on_section_selected_maps_display_label_to_key(shared_tk_root):
    comp = UnifiedSettingsTabComponent(shared_tk_root, _FakeApp())
    try:
        rocket_label = next(label for label, key in comp._section_labels.items() if key == "rocket")
        comp._on_section_selected(rocket_label)
        assert comp.rocket_comp.winfo_manager() == "pack"
    finally:
        comp.destroy()


def test_get_active_section_key_reflects_current_switcher_value(shared_tk_root):
    # gui_manager.pyw's on_global_file_dropped() משתמש בזה כדי לדעת אם לנתב
    # גרירת תיקייה לתת-המדור "rocket" - חייב לשקף בדיוק מה שמוצג כרגע. switcher.set()
    # (לא _on_section_selected, שרק מגיב ללחיצה אמיתית ולא מזיז את ה-switcher
    # עצמו) הוא מה שבאמת קובע את מה ש-.get() יחזיר - בדיוק מה ש-get_active_section_key() קורא.
    comp = UnifiedSettingsTabComponent(shared_tk_root, _FakeApp())
    try:
        assert comp.get_active_section_key() == "style"  # ברירת מחדל בבנייה

        rocket_label = next(label for label, key in comp._section_labels.items() if key == "rocket")
        comp.switcher.set(rocket_label)
        assert comp.get_active_section_key() == "rocket"

        global_label = next(label for label, key in comp._section_labels.items() if key == "global")
        comp.switcher.set(global_label)
        assert comp.get_active_section_key() == "global"
    finally:
        comp.destroy()
