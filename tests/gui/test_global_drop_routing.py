# tests/gui/test_global_drop_routing.py
#
# רגרסיה ל-gui_manager.pyw's on_global_file_dropped: לפני התיקון תמיד ניתב
# ל-settings_comp (טאב "לוח בקרה") בלי קשר לאיזה טאב היה פתוח בפועל - גרירה
# בזמן שטאב אחר (Rocket Shorts, Bot, Soundboard וכו') פתוח הייתה מעדכנת בשקט
# שדה תיקייה בלתי-נראה במסך. בודק את אותו דפוס ניתוב בבידוד (מדמה LauncherApp
# עם stubs, בלי לבנות שום GUI אמיתי) - אותה גישה בדיוק כמו test_rtl_tab_order.py.


from utils.shared.i18n import t


class _FakeFolderTarget:
    def __init__(self):
        self.dropped_events = []

    def on_folder_dropped(self, event):
        self.dropped_events.append(event)


class _FakeUnifiedSettingsComp:
    def __init__(self, active_section_key):
        self._active_section_key = active_section_key

    def get_active_section_key(self):
        return self._active_section_key


class _FakeApp:
    """מדמה בדיוק את מה ש-on_global_file_dropped ב-gui_manager.pyw נוגע בו -
    self.tabview.get(), self.unified_settings_comp, self.rocket_settings_comp,
    self.settings_comp - בלי לבנות אף CTk widget אמיתי."""

    def __init__(self, active_tab, active_section_key="style", has_settings_comp=True):
        self.tabview = type("FakeTabview", (), {"get": lambda self_: active_tab})()
        self.unified_settings_comp = _FakeUnifiedSettingsComp(active_section_key)
        self.rocket_settings_comp = _FakeFolderTarget()
        if has_settings_comp:
            self.settings_comp = _FakeFolderTarget()

    # עותק מדויק של הגוף ב-gui_manager.pyw (ראו ההערה שם) - זה מה שמאפשר
    # לבדוק את החלטת-הניתוב עצמה בלי לייבא את כל ה-.pyw.
    def on_global_file_dropped(self, event):
        active_tab = self.tabview.get()
        if active_tab == t("⚙️ הגדרות"):
            if self.unified_settings_comp.get_active_section_key() == "rocket":
                self.rocket_settings_comp.on_folder_dropped(event)
            return
        if active_tab == t("🎮 לוח בקרה") and hasattr(self, "settings_comp"):
            self.settings_comp.on_folder_dropped(event)


def test_drop_on_dashboard_tab_routes_to_settings_comp():
    app = _FakeApp(active_tab=t("🎮 לוח בקרה"))
    app.on_global_file_dropped("event1")
    assert app.settings_comp.dropped_events == ["event1"]
    assert app.rocket_settings_comp.dropped_events == []


def test_drop_on_settings_tab_rocket_section_routes_to_rocket_comp():
    app = _FakeApp(active_tab=t("⚙️ הגדרות"), active_section_key="rocket")
    app.on_global_file_dropped("event1")
    assert app.rocket_settings_comp.dropped_events == ["event1"]
    assert app.settings_comp.dropped_events == []


def test_drop_on_settings_tab_style_section_is_ignored():
    # לפני התיקון: זה היה מעדכן בשקט את שדה התיקייה של "לוח בקרה" הבלתי-נראה.
    app = _FakeApp(active_tab=t("⚙️ הגדרות"), active_section_key="style")
    app.on_global_file_dropped("event1")
    assert app.rocket_settings_comp.dropped_events == []
    assert app.settings_comp.dropped_events == []


def test_drop_on_settings_tab_global_section_is_ignored():
    app = _FakeApp(active_tab=t("⚙️ הגדרות"), active_section_key="global")
    app.on_global_file_dropped("event1")
    assert app.rocket_settings_comp.dropped_events == []
    assert app.settings_comp.dropped_events == []


def test_drop_on_unrelated_tabs_is_ignored():
    for unrelated_tab in (t("🤖 ניהול דיסקורד"), t("🔊 סאונדבורד"), t("📊 סטטיסטיקות"), t("⏰ תזמון")):
        app = _FakeApp(active_tab=unrelated_tab)
        app.on_global_file_dropped("event1")
        assert app.settings_comp.dropped_events == [], f"tab {unrelated_tab!r} should not route anywhere"
        assert app.rocket_settings_comp.dropped_events == []


def test_drop_on_dashboard_tab_without_settings_comp_attribute_does_not_raise():
    # settings_comp נבנה רק אחרי build_skeleton() - גרירה שמגיעה (תיאורטית)
    # לפני שהוא קיים לא אמורה לזרוק AttributeError.
    app = _FakeApp(active_tab=t("🎮 לוח בקרה"), has_settings_comp=False)
    app.on_global_file_dropped("event1")  # לא אמור לזרוק
