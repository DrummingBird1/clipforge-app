# ui/style_settings_tab.py
#
# הועבר מ-gui_manager.pyw (build_style_settings_tab + הפונקציות הנלוות) כחלק
# מאיחוד "🎨 עיצוב וממשק" + "🌐 הגדרות גלובליות" + "⚙️ הגדרות" לטאב "⚙️ הגדרות"
# מאוחד אחד (ui/unified_settings_tab.py).
#
# מקבל app (מופע LauncherApp) כי כמה מהפעולות כאן (שקיפות חלון, "תמיד עליון",
# מגירת התראות) הן פעולות ברמת חלון-השורש עצמו (self.attributes(...)) שרכיב
# טאב רגיל (CTkFrame) לא יכול לבצע בכוחות עצמו.

import customtkinter as ctk

from utils.shared.state import state, THEMES, PALETTE, THEME_MODES
from utils.shared.i18n import t
from ui.widgets import FONT_HEBREW_TITLE, FONT_HEBREW_SUB, FONT_HEBREW_TEXT


class StyleSettingsTabComponent(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build_component()

    def _build_component(self):
        frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        lbl_t = ctk.CTkLabel(frame, text=t("🎨 שליטה ברכיבי עיצוב, אפקטים וממשק"), font=FONT_HEBREW_TITLE, text_color=state.current_theme["accent"])
        lbl_t.pack(pady=(5, 15), anchor="ne")

        ui_settings = self.app.ui_settings

        sw_rings = ctk.CTkSwitch(frame, text=t("טבעות ניצולת מעגליות (CPU/RAM)"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("rings", sw_rings.get()))
        if ui_settings["rings"]: sw_rings.select()
        sw_rings.pack(pady=8, anchor="ne")

        sw_drawer = ctk.CTkSwitch(frame, text=t("מגירת התראות נשלפת (🔔)"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("drawer", sw_drawer.get()))
        if ui_settings["drawer"]: sw_drawer.select()
        sw_drawer.pack(pady=8, anchor="ne")

        sw_palette = ctk.CTkSwitch(frame, text=t("חלון פקודות מהיר (Ctrl+K)"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("palette", sw_palette.get()))
        if ui_settings["palette"]: sw_palette.select()
        sw_palette.pack(pady=8, anchor="ne")

        sw_trans = ctk.CTkSwitch(frame, text=t("אפקט שקיפות חלון (Alpha Glass)"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("transparency", sw_trans.get()))
        if ui_settings["transparency"]: sw_trans.select()
        sw_trans.pack(pady=8, anchor="ne")

        sw_sound = ctk.CTkSwitch(frame, text=t("אפקטים קוליים לממשק (UI Sound FX)"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("sound_fx", sw_sound.get()))
        if ui_settings["sound_fx"]: sw_sound.select()
        sw_sound.pack(pady=8, anchor="ne")

        sw_hl = ctk.CTkSwitch(frame, text=t("צביעה אוטומטית של מילות מפתח בלוגים"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("syntax_highlight", sw_hl.get()))
        if ui_settings["syntax_highlight"]: sw_hl.select()
        sw_hl.pack(pady=8, anchor="ne")

        sw_alerts = ctk.CTkSwitch(frame, text=t("באנר אזהרת עומס מערכת (CPU High Alert)"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("cpu_alerts", sw_alerts.get()))
        if ui_settings["cpu_alerts"]: sw_alerts.select()
        sw_alerts.pack(pady=8, anchor="ne")

        sw_hkbar = ctk.CTkSwitch(frame, text=t("סרגל קיצורי מקלדת בתחתית הלוג"), font=FONT_HEBREW_TEXT, command=lambda: self.toggle_ui_feature("shortcut_bar", sw_hkbar.get()))
        if ui_settings["shortcut_bar"]: sw_hkbar.select()
        sw_hkbar.pack(pady=8, anchor="ne")

        # ערכת נושא - שינוי חי (בלי הפעלה מחדש), בניגוד ל-Dark/Light ולשפה למטה.
        # apply_theme_change() (על LauncherApp) כבר מעדכן את כל ה-widgets
        # הרלוונטיים ושומר config, אז אין צורך לבנות מחדש את הטאב אחרי לחיצה.
        ctk.CTkLabel(frame, text=t("🎨 ערכת נושא"), font=FONT_HEBREW_SUB, text_color=state.current_theme["accent"]).pack(pady=(20, 8), anchor="ne")
        theme_row = ctk.CTkFrame(frame, fg_color="transparent")
        theme_row.pack(pady=4, anchor="ne")
        for preset_name in ("Green", "Pink", "Blue", "Cyberpunk", "Rocket League"):
            swatch_color = THEMES[preset_name]["accent"]
            ctk.CTkButton(
                theme_row, text="", width=28, height=28, corner_radius=14,
                fg_color=swatch_color, hover_color=swatch_color,
                command=lambda n=preset_name: self.app.apply_theme_change(n)
            ).pack(side="right", padx=4)
        ctk.CTkButton(
            theme_row, text=t("🎨 מותאם אישית..."), width=100, height=28,
            fg_color=THEMES["Custom"]["accent"],
            command=self.pick_custom_theme_color
        ).pack(side="right", padx=4)

        ctk.CTkLabel(frame, text=t("🌗 מצב עיצוב (נדרשת הפעלה מחדש)"), font=FONT_HEBREW_SUB, text_color=state.current_theme["accent"]).pack(pady=(20, 8), anchor="ne")
        # 3 מצבים (לא switch בינארי) - THEME_MODES ב-utils/shared/state.py הוא מקור
        # האמת היחיד לערכים התקפים, אז TEXT_BY_MODE כאן חייב לכסות בדיוק אותם.
        text_by_mode = {"dark": t("כהה (Dark)"), "light": t("בהיר (Light)"), "high_contrast": t("ניגודיות גבוהה (High-Contrast)")}
        mode_segmented = ctk.CTkSegmentedButton(
            frame, values=[text_by_mode[mode] for mode in THEME_MODES],
            command=lambda label: self.set_theme_mode(next(mode for mode in THEME_MODES if text_by_mode[mode] == label)),
        )
        mode_segmented.set(text_by_mode[state.theme_mode])
        mode_segmented.pack(pady=8, anchor="ne")

        ctk.CTkLabel(frame, text=t("🌐 שפה (נדרשת הפעלה מחדש) / Language (restart required)"), font=FONT_HEBREW_SUB, text_color=state.current_theme["accent"]).pack(pady=(20, 8), anchor="ne")
        sw_lang = ctk.CTkSwitch(frame, text="English", font=FONT_HEBREW_TEXT, command=lambda: self.toggle_language(sw_lang.get()))
        if state.language == "en": sw_lang.select()
        sw_lang.pack(pady=8, anchor="ne")

    def pick_custom_theme_color(self):
        from tkinter import colorchooser
        self.app.play_ui_sound()
        _rgb, hex_color = colorchooser.askcolor(color=state.custom_accent_hex, title=t("בחר צבע accent מותאם אישית"))
        if not hex_color:
            return  # המשתמש ביטל את הדיאלוג
        state.set_custom_accent(hex_color)
        self.app.apply_theme_change("Custom")

    def set_theme_mode(self, mode):
        state.theme_mode = mode
        state.save_config()
        self.app.play_ui_sound()
        self.app.log_message("SYSTEM", t("מצב העיצוב נשמר - סגור ופתח מחדש את האפליקציה כדי שהשינוי ייכנס לתוקף."), "🌗")

    def toggle_language(self, is_english):
        state.language = "en" if is_english else "he"
        state.save_config()
        self.app.play_ui_sound()
        self.app.log_message("SYSTEM", t("השפה נשמרה - סגור ופתח מחדש את האפליקציה כדי שהשינוי ייכנס לתוקף. / Language saved - restart the app to apply."), "🌐")

    def toggle_ui_feature(self, feature_key, state_val):
        self.app.ui_settings[feature_key] = bool(state_val)
        self.app.play_ui_sound()

        if feature_key == "transparency":
            try:
                self.app.attributes("-alpha", 0.98 if state_val else 1.0)
            except Exception:
                pass
        elif feature_key == "drawer":
            if not state_val and self.app.drawer_visible:
                self.app.toggle_notification_drawer()
            self.app.btn_drawer.configure(state="normal" if state_val else "disabled")
        elif feature_key == "shortcut_bar":
            if state_val:
                self.app.hotkey_bar.pack(fill="x", padx=15, pady=(0, 4))
            else:
                self.app.hotkey_bar.pack_forget()

        state.save_config()
        self.app.log_message("SYSTEM", t("הגדרת עיצוב [{key}] שונתה ל: {state}", key=feature_key, state=t("מופעל") if state_val else t("כבוי")), "🎨")

    def toggle_always_on_top(self):
        self.app.ui_settings["always_on_top"] = not self.app.ui_settings["always_on_top"]
        self.app.attributes("-topmost", self.app.ui_settings["always_on_top"])
        self.app.btn_pin.configure(fg_color=state.current_theme["accent"] if self.app.ui_settings["always_on_top"] else PALETTE["border"])
        state.save_config()
        self.app.play_ui_sound()
        self.app.log_message("SYSTEM", t("מצב חלון תמיד עליון: {state}", state=t("מופעל") if self.app.ui_settings['always_on_top'] else t("כבוי")), "📌")
