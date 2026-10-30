# ui/unified_settings_tab.py
#
# מאחד 3 טאבים נפרדים שהיו קיימים קודם ("🎨 עיצוב וממשק", "🌐 הגדרות גלובליות",
# וחלק מ-"⚙️ הגדרות") לטאב "⚙️ הגדרות" אחד עם בורר תת-מדורים - היו למעשה 3
# מקומות שונים בשם "הגדרות" עם קריטריון חלוקה לא ברור למשתמש.

import customtkinter as ctk

from utils.shared.i18n import t
from utils.shared.state import state
from ui.style_settings_tab import StyleSettingsTabComponent
from ui.global_settings_tab import GlobalSettingsTabComponent
from ui.rocket_settings_tab import RocketSettingsTabComponent


class UnifiedSettingsTabComponent(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build_component()

    def _build_component(self):
        self._section_labels = {
            t("🎨 עיצוב"): "style",
            t("🌐 כללי"): "global",
            t("🎬 Rocket Shorts"): "rocket",
        }
        first_label = next(iter(self._section_labels))

        # selected_color/selected_hover_color - בלי זה הבורר משתמש בכחול ברירת
        # המחדל של CTkSegmentedButton, בלי שום קשר לערכת הנושא הנבחרת (Pink/
        # Cyberpunk/וכו') - היחיד ברכיבי ה-accent שלא הגיב לשינוי ערכת נושא בכלל.
        accent = state.current_theme["accent"]
        self.switcher = ctk.CTkSegmentedButton(
            self, values=list(self._section_labels.keys()), command=self._on_section_selected,
            selected_color=accent, selected_hover_color=state.current_theme["accent_hover"]
        )
        self.switcher.pack(pady=(15, 5), padx=15, fill="x")
        self.switcher.set(first_label)

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        self.style_comp = StyleSettingsTabComponent(self.content_frame, self.app)
        self.global_comp = GlobalSettingsTabComponent(self.content_frame, self.app)
        self.rocket_comp = RocketSettingsTabComponent(self.content_frame, self.app)
        self._sections = {"style": self.style_comp, "global": self.global_comp, "rocket": self.rocket_comp}

        self._show_section(self._section_labels[first_label])

    def _on_section_selected(self, label):
        self._show_section(self._section_labels[label])

    def get_active_section_key(self):
        """"style"/"global"/"rocket" - איזה תת-מדור מוצג כרגע. משמש את
        gui_manager.pyw's on_global_file_dropped() כדי לנתב גרירה על החלון
        לתת-המדור הנכון (רק "rocket" כולל שדה תיקייה), בלי לגשת ל-_section_labels
        הפרטי מבחוץ."""
        return self._section_labels[self.switcher.get()]

    def _show_section(self, key):
        for name, comp in self._sections.items():
            if name == key:
                comp.pack(fill="both", expand=True)
            else:
                comp.pack_forget()

    def update_accent(self, color, hover_color):
        """נקרא מ-apply_theme_change (gui_manager.pyw) - בלי זה בורר תת-המדורים
        היה נשאר בצבע הישן (או בכחול ברירת המחדל) אחרי החלפת ערכת נושא חיה,
        בזמן שכל שאר רכיבי ה-accent (סיידבר, כפתור הרצה, טבעות) כן מתעדכנים."""
        self.switcher.configure(selected_color=color, selected_hover_color=hover_color)
