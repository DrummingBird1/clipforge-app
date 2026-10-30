# ui/settings_tab.py
import os
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
from ui.widgets import FONT_HEBREW_TEXT, Tooltip
from utils.shared.state import state, PALETTE
from utils.shared.i18n import t, fix_hebrew_word_order
from utils.video.video_editor import VIDEO_EDITOR_PRESETS, compute_watermark_geometry, parse_fps_value, resolve_output_dimensions
from utils.video.video_editor_field_help import FIELD_HELP
from utils.video.video_editor_profiles import PROFILE_FIELDS, delete_profile, load_profiles, rename_profile, save_profile
from utils.video.video_editor_counter import save_number as save_video_editor_counter

# תואם בכוונה לגודל תיבת התצוגה המקדימה בווב (web_app.py's #wmPreviewBox) -
# אותה חוויה בדיוק בין דסקטופ לדפדפן. אופקי 16:9, אנכי 9:16.
_WM_PREVIEW_BOX_SIZES = {False: (213, 120), True: (120, 213)}

# צבע הבחנה קבוע לכל קטגוריה בעורך-העל (item: קידוד-צבע לקטגוריות) - גוון
# גבול לכרטיס הקטגוריה, כדי לסרוק ויזואלית מהר יותר בין 11 קטגוריות פתוחות
# בו-זמנית. קבוע (לא תלוי בערכת-הנושא/accent הניתנת-להתאמה של המשתמש) בכוונה -
# ההבחנה בין קטגוריות אמורה להישאר יציבה גם כשהמשתמש מחליף ערכת-נושא.
_CATEGORY_COLORS = {
    "favorites": "#fbbf24", "profiles": "#a78bfa", "watermark": "#f472b6",
    "format": "#38bdf8", "trim": "#34d399", "audio": "#fb7185",
    "color": "#f59e0b", "motion": "#2dd4bf", "captions": "#818cf8",
    "export": "#60a5fa", "resources": "#94a3b8",
}

try:
    from tkinterdnd2 import DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    _DND_AVAILABLE = False


def _collect_widgets(widget):
    """כל ה-widgets מתחת ל-widget, כולל הוא עצמו - שימושי לסריקה גנרית (item:
    תקציר-מצב לקטגוריה) בלי לתחזק רשימה נפרדת של אילו Var-ים שייכים לאיזו
    קטגוריה."""
    result = [widget]
    for child in widget.winfo_children():
        result.extend(_collect_widgets(child))
    return result


class SettingsTabComponent(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build_tab()

    def _build_tab(self):
        self.lbl_title = ctk.CTkLabel(self, text=t("⚙️ הגדרות עבור הסקריפט הנבחר"), font=("Segoe UI", 13, "bold"))
        self.lbl_title.pack(pady=10)

        # תיאור הסקריפט הנבחר (נקרא מ-"# Description:" בראש קובץ הסקריפט עצמו -
        # ראו utils/shared/script_metadata.py). anchor="e" + justify="right" כדי שטקסט
        # ארוך שעובר שורה יתיישר לימין כמו שאר הממשק, לא ישמאל כברירת המחדל.
        self.description_label = ctk.CTkLabel(
            self, text="", text_color=PALETTE["text_muted"], anchor="e", justify="right",
            wraplength=280, font=("Segoe UI", 11)
        )
        self.description_label.pack(pady=(0, 10), padx=15, fill="x")

        # שדה תיקייה/קובץ - עריכה ישירה (הקלדה/הדבקה) בנוסף לכפתור עיון ולגרירה
        # (Drag&Drop) של תיקייה או קובץ וידאו ישירות לתוך השדה. היה קודם רק
        # תווית קריאה-בלבד + כפתור "בחר תיקייה" - אי אפשר היה להקליד נתיב ישירות
        # ולא הייתה תמיכה בגרירה בכלל (בניגוד לפאנל Rocket Shorts שכבר תמך בזה).
        row_folder = ctk.CTkFrame(self, fg_color="transparent")
        row_folder.pack(pady=15, padx=20, fill="x")

        self.folder_path_var = ctk.StringVar(value=state.selected_gameplay_folder)
        self.folder_entry = ctk.CTkEntry(
            row_folder, textvariable=self.folder_path_var, font=("Segoe UI", 11),
            placeholder_text=t("גרור תיקייה/קובץ וידאו לכאן, או הקלד נתיב...") if _DND_AVAILABLE else t("הקלד נתיב תיקייה...")
        )
        self.folder_entry.pack(side="right", fill="x", expand=True, padx=(5, 0))
        self.folder_entry.bind("<Return>", self._on_folder_entry_changed)
        self.folder_entry.bind("<FocusOut>", self._on_folder_entry_changed)

        if _DND_AVAILABLE:
            self.folder_entry.drop_target_register(DND_FILES)
            self.folder_entry.dnd_bind("<<Drop>>", self.on_folder_dropped)

        btn_browse_folder = ctk.CTkButton(row_folder, text=t("📂 עיון..."), width=90, command=self.choose_gameplay_folder)
        btn_browse_folder.pack(side="right", padx=(5, 0))

        # פאנל שופט ה-AI - מוצג רק כשהסקריפט הנבחר הוא story_cutter.py (ראו
        # _AI_PROVIDER_LABELS למטה); לא נעשה .pack() כאן, update_script_context
        # הוא זה שקובע אם הפאנל מוצג בכלל.
        self._ai_provider_display_to_value = {
            t("☁️ Gemini (מדויק יותר, בתשלום/מכסה)"): "gemini",
            t("💻 מקומי - Ollama (חינמי, פחות מדויק)"): "local",
        }
        self._ai_provider_value_to_display = {v: k for k, v in self._ai_provider_display_to_value.items()}

        self.ai_provider_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.ai_provider_label = ctk.CTkLabel(self.ai_provider_frame, text=t("שיפוט קליפים באמצעות:"), anchor="e", justify="right")
        self.ai_provider_label.pack(fill="x", padx=5)
        self.ai_provider_menu = ctk.CTkOptionMenu(
            self.ai_provider_frame,
            values=list(self._ai_provider_display_to_value.keys()),
            command=self._on_ai_provider_selected,
        )
        self.ai_provider_menu.pack(pady=(5, 0), padx=5, fill="x")

        # פאנל video_editor.py - מוצג רק כשהסקריפט הנבחר הוא הסקריפט הזה (ראו
        # update_script_context למטה, אותו דפוס בדיוק כמו ai_provider_frame).
        self._wm_position_display_to_value = {
            t("⬆️⬅️ שמאל-עליון"): "top-left",
            t("⬆️ מרכז-עליון"): "top-center",
            t("⬆️➡️ ימין-עליון"): "top-right",
            t("⬇️⬅️ שמאל-תחתון"): "bottom-left",
            t("⬇️ מרכז-תחתון"): "bottom-center",
            t("⬇️➡️ ימין-תחתון"): "bottom-right",
            t("⏺️ מרכז"): "center",
        }
        self._wm_position_value_to_display = {v: k for k, v in self._wm_position_display_to_value.items()}

        # אותם תוויות מיקום בדיוק (עקביות), פלוס פלייסהולדר "ללא" - בניגוד למיקום
        # ה-watermark החדש (שתמיד יש לו ערך תקין), מחיקת watermark ישן היא
        # אופציונלית לגמרי (ראו --remove_watermark_position ב-video_editor.py).
        self._remove_wm_placeholder = t("ללא מחיקה")
        self._remove_wm_position_display_to_value = {self._remove_wm_placeholder: "", **self._wm_position_display_to_value}
        self._remove_wm_position_value_to_display = {v: k for k, v in self._remove_wm_position_display_to_value.items()}

        self._codec_display_to_value = {
            t("H.264 (CPU, תאימות מקסימלית)"): "h264",
            t("H.265 / HEVC (GPU NVENC)"): "hevc",
            t("AV1 (GPU NVENC, הדור הבא)"): "av1",
        }
        self._codec_value_to_display = {v: k for k, v in self._codec_display_to_value.items()}

        # CTkScrollableFrame עם גובה קבוע (לא CTkFrame רגיל שגדל בלי גבול) - אחרי
        # פיצול כל הגדרה לשורה משלה (במקום כמה מתגים/שדות דחוסים יחד) הפאנל
        # גבוה מכדי להיכנס בפאנל שמעליו dashboard_comp (כפתור הרצה/קונסולה,
        # שתופס fill="both", expand=True) - נמדד בפועל: ~1200px רק ל-video_editor_frame
        # מול חלון ברירת-מחדל של 980px גובה כולל. גלילה פנימית שומרת את שתי
        # הדרישות: כל הגדרה בשורה קריאה משלה, וגם שהריצה/קונסולה נשארות גלויות.
        self.video_editor_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", height=480)

        # item: פס פעולות צף - נשאר גלוי בלי קשר לגלילה בתוך video_editor_frame
        # (אח שלו, לא בתוכו) - שמירה/עדכון פרופיל היו נגישים רק דרך קטגוריית
        # "פרופילים" למעלה, שדורשת גלילה חזרה מעלה מכל קטגוריה אחרת.
        # unsaved_indicator_var נוצר כאן (לא בשורת ה-preset למטה, שנבנית אחרי
        # הפס הצף הזה) כדי ששני המקומות שמציגים אותו יחלקו את אותו Var.
        self.unsaved_indicator_var = ctk.StringVar(value="")
        self.video_editor_sticky_bar = ctk.CTkFrame(self, fg_color=PALETTE["surface_alt"], corner_radius=8)
        ctk.CTkButton(self.video_editor_sticky_bar, text=t("💾 שמור פרופיל"), width=110, command=self._save_video_editor_profile).pack(side="right", padx=5, pady=6)
        ctk.CTkButton(self.video_editor_sticky_bar, text=t("🔄 עדכן"), width=70, command=self._update_video_editor_profile).pack(side="right", padx=5, pady=6)
        ctk.CTkLabel(
            self.video_editor_sticky_bar, textvariable=self.unsaved_indicator_var,
            text_color=PALETTE["danger"], font=("Segoe UI", 10, "bold"),
        ).pack(side="right", padx=5)

        # item: טור הכרות ראשוני - באנר-הודעה עם "הבנתי" (לא spotlight רב-שלבי -
        # ל-Tkinter/CTk אין מסגרת-overlay מובנית לזה, ובאנר-כניסה חד-פעמי
        # מכסה את אותה מטרה: להפנות תשומת לב למועדפים/מקראה/גרירה) - מוצג
        # רק אם video_editor_onboarding_seen עדיין False, נעלם לצמיתות בלחיצה.
        self.video_editor_onboarding_banner = ctk.CTkFrame(self, fg_color=PALETTE["surface_purple"], corner_radius=8)
        ctk.CTkLabel(
            self.video_editor_onboarding_banner, anchor="e", justify="right", wraplength=520,
            text=t("👋 טיפ: אפשר לסמן הגדרות כ⭐מועדפות (בקטגוריית \"פרופילים\"), לגרור watermark ישירות על התצוגה המקדימה, וללחוץ \"📖 מקראה\" לכל ההסברים במקום אחד."),
        ).pack(side="right", padx=10, pady=8, fill="x", expand=True)
        ctk.CTkButton(self.video_editor_onboarding_banner, text=t("הבנתי"), width=70, command=self._dismiss_video_editor_onboarding).pack(side="left", padx=10, pady=8)

        # קטגוריות מסודרות (item) - כל הגדרות עורך-העל מפוצלות ל-10 סקציות
        # ניתנות-לקיפול (ראו _build_collapsible_category), פתוחות כברירת מחדל.
        # נבנות כאן מראש - כל שורת-הגדרה בהמשך נכנסת לתוך אחת מהן (cat_X)
        # במקום ישירות ל-self.video_editor_frame כמו קודם.
        # item: תיבת העדפות לכל פרופיל - קטגוריה ראשונה (לא ניתנת-לקיפול-החוצה
        # באמת אבל ממוקמת ראשונה כדי שתהיה הכי נגישה), מתמלאת דינמית ב-
        # _rebuild_favorites_box() (לא כאן - עדיין אין ל-Var/menu-ים של שאר
        # השדות ערך בזמן הזה בבנייה). self.cat_favorites נשמר כדי שאפשר יהיה
        # לפרק ולבנות מחדש את התוכן שלה כל פעם שסט המועדפים משתנה.
        self._category_content_by_key = {}
        self._category_summary_vars = {}
        self.cat_favorites = self._build_collapsible_category(self.video_editor_frame, t("⭐ מועדפים"), "favorites")
        self._favorite_mirrors = {}
        cat_profiles = self._build_collapsible_category(self.video_editor_frame, t("👤 פרופילים"), "profiles")
        cat_watermark = self._build_collapsible_category(self.video_editor_frame, t("🖼️ Watermark"), "watermark")
        cat_format = self._build_collapsible_category(self.video_editor_frame, t("📐 פורמט וקרופ"), "format")
        cat_trim = self._build_collapsible_category(self.video_editor_frame, t("✂️ חיתוך וזמנים"), "trim")
        cat_audio = self._build_collapsible_category(self.video_editor_frame, t("🔊 אודיו"), "audio")
        cat_color = self._build_collapsible_category(self.video_editor_frame, t("🎨 צבע ופילטרים ויזואליים"), "color")
        cat_motion = self._build_collapsible_category(self.video_editor_frame, t("🎞️ תנועה ו-FPS"), "motion")
        cat_captions = self._build_collapsible_category(self.video_editor_frame, t("💬 כתוביות"), "captions")
        cat_export = self._build_collapsible_category(self.video_editor_frame, t("📦 קידוד ויצוא"), "export")
        cat_resources = self._build_collapsible_category(self.video_editor_frame, t("⚙️ משאבי-מחשב ותשתית"), "resources")

        # פרופיל מוכן (זהה בעיקרון ל-PRESETS ב-ui/rocket_settings_tab.py) -
        # מציבים ערך "לבחור פרופיל..." ראשון כדי שבחירת סקריפט לא "תדרוס"
        # בטעות הגדרות קיימות; רק בחירה מפורשת של פרופיל אמיתי משנה משהו.
        # אחריהם (item: פרופיל משלי) - פרופילים אישיים שהמשתמש שומר בעצמו
        # (utils/video/video_editor_profiles.py) - snapshot מלא כולל נתיבים/סליידרים,
        # לא רק "סוג עריכה" כללי כמו ה-presets הקבועים. CTkOptionMenu לא תומך
        # בקבוצות (optgroup, בניגוד ל-<select> בווב) - מסומנים ב-"👤 " בתצוגה
        # במקום זה, ומופרדים חזרה למפתח האמיתי דרך self._profile_display_to_name.
        self._custom_profile_display_prefix = "👤 "
        self._profile_display_to_name: dict = {}
        row_preset = ctk.CTkFrame(cat_profiles, fg_color="transparent")
        row_preset.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(row_preset, text=t("פרופיל מוכן:"), anchor="e", justify="right").pack(side="right", padx=(5, 0))
        self._preset_placeholder = t("בחר פרופיל...")
        self.preset_menu = ctk.CTkOptionMenu(row_preset, values=[self._preset_placeholder], command=self._on_video_editor_preset_selected)
        self.preset_menu.set(self._preset_placeholder)
        self.preset_menu.pack(side="right", padx=5, fill="x", expand=True)
        self._preset_menu_previous_display = self._preset_placeholder
        self._profile_baseline_snapshot = None
        self.delete_profile_btn = ctk.CTkButton(
            row_preset, text=t("🗑️ מחק"), width=70, fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"],
            command=self._delete_video_editor_profile,
        )
        # item: אפשרות לעדכן פרופיל קיים - שומר מחדש את ההגדרות הנוכחיות תחת
        # אותו שם, בלי לצטרך להקליד את השם שוב (בניגוד ל-"שמור פרופיל" למטה,
        # שדורש הקלדת שם - כתיבה מקרית של שם קיים כבר הייתה עובדת כעדכון גם
        # קודם, אבל בלי כפתור ייעודי זה לא היה נגיש/מובן כתכונה).
        self.update_profile_btn = ctk.CTkButton(
            row_preset, text=t("🔄 עדכן"), width=70, command=self._update_video_editor_profile,
        )
        # item: שינוי שם לפרופיל
        self.rename_profile_btn = ctk.CTkButton(
            row_preset, text=t("✏️ שנה שם"), width=90, command=self._rename_video_editor_profile,
        )
        self._refresh_video_editor_profile_menu()

        # item: אינדיקציית שינויים לא-שמורים - מתעדכנת ממעגל-הרענון התקופתי
        # (_start_periodic_ui_refresh), לא כאן.
        row_unsaved = ctk.CTkFrame(cat_profiles, fg_color="transparent")
        row_unsaved.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            row_unsaved, textvariable=self.unsaved_indicator_var, anchor="e", justify="right",
            text_color=PALETTE["danger"], font=("Segoe UI", 11, "bold"),
        ).pack(side="right", padx=5)
        # item: מקראה - כפתור שפותח את דיאלוג-ההסברים המלא לכל ההגדרות.
        ctk.CTkButton(row_unsaved, text=t("📖 מקראה"), width=90, command=self._open_glossary_dialog).pack(side="left", padx=5)
        # item: איפוס לברירת מחדל - מאפס את כל הגדרות עורך-העל (לא רק פרופיל
        # אחד) לברירות המחדל של video_editor.py, בלי לגעת בפרופילים השמורים
        # עצמם על הדיסק. גרנולריות "כל הפאנל" ולא per-field/per-category -
        # מסובך יותר בלי תועלת ברורה מספיק (כל שדה היה דורש מיפוי-ברירת-מחדל
        # ורענון-widget נפרד), בעוד ש-_apply_video_editor_profile_fields({})
        # כבר קיים, בדוק, ומכסה את כל השדות בבת אחת.
        ctk.CTkButton(row_unsaved, text=t("↺ אפס לברירת מחדל"), width=130, command=self._reset_video_editor_to_defaults).pack(side="left", padx=5)

        row_save_profile = ctk.CTkFrame(cat_profiles, fg_color="transparent")
        row_save_profile.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(row_save_profile, text=t("שמור את ההגדרות הנוכחיות כפרופיל שלי:"), anchor="e", justify="right").pack(side="right", padx=(5, 0))
        self.profile_name_var = ctk.StringVar(value="")
        self.profile_name_entry = ctk.CTkEntry(row_save_profile, textvariable=self.profile_name_var, placeholder_text=t("למשל: קליפים של משחקים"))
        self.profile_name_entry.pack(side="right", fill="x", expand=True, padx=5)
        ctk.CTkButton(row_save_profile, text=t("💾 שמור פרופיל"), width=110, command=self._save_video_editor_profile).pack(side="right")

        # item: תיבת העדפות לכל פרופיל - כפתור ייעודי (לא ⭐ בכל שורה בנפרד -
        # 40+ שורות ברוב הקטגוריות, כפתור אחד עם דיאלוג צ'קליסט הרבה יותר קל
        # לתחזוקה ולסקירה מאשר לגעת בכל שורה קיימת בנפרד) שפותח דיאלוג לבחירת
        # אילו הגדרות (מכל הקטגוריות) יופיעו גם בקטגוריית "⭐ מועדפים" הראשונה.
        row_favorites_config = ctk.CTkFrame(cat_profiles, fg_color="transparent")
        row_favorites_config.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(row_favorites_config, text=t("⭐ הגדר מועדפים..."), command=self._open_favorites_dialog).pack(side="right")

        row_wm = ctk.CTkFrame(cat_watermark, fg_color="transparent")
        row_wm.pack(fill="x", pady=(0, 4))
        self.watermark_path_var = ctk.StringVar(value=state.video_editor_watermark_path)
        self.watermark_entry = ctk.CTkEntry(
            row_wm, textvariable=self.watermark_path_var, font=("Segoe UI", 11),
            placeholder_text=t("גרור תמונת watermark לכאן, או הקלד נתיב...") if _DND_AVAILABLE else t("הקלד נתיב לתמונת watermark...")
        )
        self.watermark_entry.pack(side="right", fill="x", expand=True, padx=(5, 0))
        self.watermark_entry.bind("<Return>", self._on_watermark_entry_changed)
        self.watermark_entry.bind("<FocusOut>", self._on_watermark_entry_changed)
        if _DND_AVAILABLE:
            self.watermark_entry.drop_target_register(DND_FILES)
            self.watermark_entry.dnd_bind("<<Drop>>", self.on_watermark_dropped)
        btn_browse_watermark = ctk.CTkButton(row_wm, text=t("🖼️ עיון..."), width=90, command=self.choose_watermark_file)
        btn_browse_watermark.pack(side="right", padx=(5, 0))

        row_wm_position = ctk.CTkFrame(cat_watermark, fg_color="transparent")
        row_wm_position.pack(fill="x", pady=4)
        self._field_label(row_wm_position, "watermark_position").pack(side="right", padx=(5, 0))
        self.wm_position_menu = ctk.CTkOptionMenu(
            row_wm_position, values=list(self._wm_position_display_to_value.keys()), command=self._on_watermark_position_selected
        )
        self.wm_position_menu.pack(side="right", padx=5, fill="x", expand=True)

        row_wm_opacity = ctk.CTkFrame(cat_watermark, fg_color="transparent")
        row_wm_opacity.pack(fill="x", pady=4)
        self._field_label(row_wm_opacity, "watermark_opacity").pack(side="right", padx=(5, 0))
        self.watermark_opacity_var = ctk.StringVar(value=state.video_editor_watermark_opacity)
        entry_watermark_opacity = ctk.CTkEntry(row_wm_opacity, textvariable=self.watermark_opacity_var, width=55, justify="center")
        entry_watermark_opacity.pack(side="right", padx=5)
        entry_watermark_opacity.bind("<Return>", self._on_watermark_opacity_changed)
        entry_watermark_opacity.bind("<FocusOut>", self._on_watermark_opacity_changed)
        # סליידר לשינוי מהיר/ויזואלי - בנוסף לשדה המספרי (לא במקומו, כדי לשמור
        # על קלט מדויק), מסונכרן דו-כיווני איתו דרך אותו state.video_editor_watermark_opacity.
        self.watermark_opacity_slider_var = ctk.DoubleVar(value=self._parse_opacity(state.video_editor_watermark_opacity))
        slider_watermark_opacity = ctk.CTkSlider(
            row_wm_opacity, from_=0.0, to=1.0, number_of_steps=20,
            variable=self.watermark_opacity_slider_var, command=self._on_watermark_opacity_slider_changed
        )
        slider_watermark_opacity.pack(side="right", padx=5, fill="x", expand=True)

        row_wm_scale = ctk.CTkFrame(cat_watermark, fg_color="transparent")
        row_wm_scale.pack(fill="x", pady=4)
        self._field_label(row_wm_scale, "watermark_scale").pack(side="right", padx=(5, 0))
        self.watermark_scale_var = ctk.StringVar(value=self._scale_to_percent_str(state.video_editor_watermark_scale))
        entry_watermark_scale = ctk.CTkEntry(row_wm_scale, textvariable=self.watermark_scale_var, width=55, justify="center")
        entry_watermark_scale.pack(side="right", padx=5)
        entry_watermark_scale.bind("<Return>", self._on_watermark_scale_changed)
        entry_watermark_scale.bind("<FocusOut>", self._on_watermark_scale_changed)
        self.watermark_scale_slider_var = ctk.DoubleVar(value=self._parse_scale_percent(state.video_editor_watermark_scale))
        slider_watermark_scale = ctk.CTkSlider(
            row_wm_scale, from_=5, to=50, number_of_steps=45,
            variable=self.watermark_scale_slider_var, command=self._on_watermark_scale_slider_changed
        )
        slider_watermark_scale.pack(side="right", padx=5, fill="x", expand=True)

        row_remove_wm = ctk.CTkFrame(cat_watermark, fg_color="transparent")
        row_remove_wm.pack(fill="x", pady=4)
        self._field_label(row_remove_wm, "remove_watermark_position").pack(side="right", padx=(5, 0))
        self.remove_wm_position_menu = ctk.CTkOptionMenu(
            row_remove_wm, values=list(self._remove_wm_position_display_to_value.keys()), command=self._on_remove_watermark_position_selected
        )
        self.remove_wm_position_menu.pack(side="right", padx=5, fill="x", expand=True)

        # תצוגה מקדימה של מיקום/גודל ה-watermark (item: watermark preview) - זהה
        # בעיקרון ל-web_app.py's updateWatermarkPreview() (אותם compute_watermark_geometry/
        # resolve_output_dimensions בדיוק, אותם ממדי תיבה) - קודם קיים רק בווב.
        # מציג את התמונה האמיתית מוקטנת, לא placeholder - כמו בווב.
        self.wm_preview_box = ctk.CTkFrame(cat_watermark, fg_color=PALETTE["surface_deep"], width=213, height=120)
        self.wm_preview_box.pack(pady=(2, 6))
        self.wm_preview_box.pack_propagate(False)
        self.wm_preview_label = ctk.CTkLabel(self.wm_preview_box, text="")
        self.wm_preview_label.place(x=0, y=0)
        self._wm_preview_ctk_image = None  # שומר רפרנס - בלי זה tkinter זורק את התמונה מהזיכרון (garbage collected) ומציג ריק

        # item: גרירת watermark חופשית - גרירה חופשית של ה-thumbnail בתוך
        # התצוגה המקדימה עצמה קובעת מיקום מדויק (לא רק פינה/מרכז קבועים),
        # מסונכרן עם compute_watermark_geometry's custom_center_fraction דרך
        # state.video_editor_watermark_x/_y (מרכז ה-watermark, לא הפינה
        # השמאלית-עליונה שלו - כדי שגודל שמשתנה לא "יזיז" את הנקודה שנגררה).
        self.wm_preview_hint = ctk.CTkLabel(
            cat_watermark, text=t("💡 אפשר לגרור את ה-watermark למעלה למיקום מדויק"),
            font=("Segoe UI", 10), text_color=PALETTE["text_muted"],
        )
        self.wm_preview_hint.pack(pady=(0, 2))
        # item: מספרים מדויקים ליד גרירת ה-watermark - x%/y% חיים, מתעדכנים
        # ב-_on_watermark_drag_motion וב-_update_watermark_preview (טעינה
        # ראשונית/מעבר בין פרופילים, לא רק תוך כדי גרירה).
        self.wm_drag_coords_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            cat_watermark, textvariable=self.wm_drag_coords_var, font=("Segoe UI", 10, "bold"), text_color=PALETTE["text_dim"],
        ).pack(pady=(0, 2))
        self.wm_clear_custom_position_btn = ctk.CTkButton(
            cat_watermark, text=t("↩️ בטל מיקום מותאם (חזרה לרשימה)"), width=180, height=24,
            font=("Segoe UI", 10), command=self._clear_watermark_custom_position,
        )
        self.wm_clear_custom_position_btn.pack(pady=(0, 6))
        self.wm_preview_label.bind("<ButtonPress-1>", self._on_watermark_drag_start)
        self.wm_preview_label.bind("<B1-Motion>", self._on_watermark_drag_motion)
        self.wm_preview_label.bind("<ButtonRelease-1>", self._on_watermark_drag_end)
        self._wm_drag_start = None

        # כל הגדרה בשורה משלה מכאן ואילך (לא כמה מתגים/שדות דחוסים יחד באותה
        # שורה) - פאנל דחוס מדי היה בפועל לא נוח לקריאה/שימוש.
        row_vertical = ctk.CTkFrame(cat_format, fg_color="transparent")
        row_vertical.pack(fill="x", pady=4)
        self.vertical_var = ctk.BooleanVar(value=state.video_editor_vertical)
        chk_vertical = ctk.CTkSwitch(
            row_vertical, text=t(FIELD_HELP["vertical"].term), variable=self.vertical_var,
            onvalue=True, offvalue=False, command=self._on_vertical_toggled
        )
        chk_vertical.pack(side="right", padx=5)
        self._attach_tooltip(chk_vertical, "vertical")

        # smart_crop רלוונטי רק עם vertical, blur_background רק בלעדיו.
        row_smart_crop = ctk.CTkFrame(cat_format, fg_color="transparent")
        row_smart_crop.pack(fill="x", pady=4)
        self.smart_crop_var = ctk.BooleanVar(value=state.video_editor_smart_crop)
        chk_smart_crop = ctk.CTkSwitch(
            row_smart_crop, text=t(FIELD_HELP["smart_crop"].term), variable=self.smart_crop_var,
            onvalue=True, offvalue=False, command=self._on_smart_crop_toggled
        )
        chk_smart_crop.pack(side="right", padx=5)
        self._attach_tooltip(chk_smart_crop, "smart_crop")

        row_blur_background = ctk.CTkFrame(cat_format, fg_color="transparent")
        row_blur_background.pack(fill="x", pady=4)
        self.blur_background_var = ctk.BooleanVar(value=state.video_editor_blur_background)
        chk_blur_background = ctk.CTkSwitch(
            row_blur_background, text=t(FIELD_HELP["blur_background"].term), variable=self.blur_background_var,
            onvalue=True, offvalue=False, command=self._on_blur_background_toggled
        )
        chk_blur_background.pack(side="right", padx=5)
        self._attach_tooltip(chk_blur_background, "blur_background")

        row_trim_start = ctk.CTkFrame(cat_trim, fg_color="transparent")
        row_trim_start.pack(fill="x", pady=4)
        self._field_label(row_trim_start, "trim_start").pack(side="right", padx=(5, 0))
        self.trim_start_var = ctk.StringVar(value=state.video_editor_trim_start)
        entry_trim_start = ctk.CTkEntry(row_trim_start, textvariable=self.trim_start_var, width=70, justify="center")
        entry_trim_start.pack(side="right", padx=5)
        entry_trim_start.bind("<Return>", self._on_trim_start_changed)
        entry_trim_start.bind("<FocusOut>", self._on_trim_start_changed)

        row_trim_duration = ctk.CTkFrame(cat_trim, fg_color="transparent")
        row_trim_duration.pack(fill="x", pady=4)
        self._field_label(row_trim_duration, "trim_duration").pack(side="right", padx=(5, 0))
        self.trim_duration_var = ctk.StringVar(value=state.video_editor_trim_duration)
        entry_trim_duration = ctk.CTkEntry(row_trim_duration, textvariable=self.trim_duration_var, width=70, justify="center", placeholder_text=t("עד הסוף"))
        entry_trim_duration.pack(side="right", padx=5)
        entry_trim_duration.bind("<Return>", self._on_trim_duration_changed)
        entry_trim_duration.bind("<FocusOut>", self._on_trim_duration_changed)

        row_trim_silence = ctk.CTkFrame(cat_trim, fg_color="transparent")
        row_trim_silence.pack(fill="x", pady=4)
        self.trim_silence_var = ctk.BooleanVar(value=state.video_editor_trim_silence)
        chk_trim_silence = ctk.CTkSwitch(
            row_trim_silence, text=t(FIELD_HELP["trim_silence"].term), variable=self.trim_silence_var,
            onvalue=True, offvalue=False, command=self._on_trim_silence_toggled
        )
        chk_trim_silence.pack(side="right", padx=5)
        self._attach_tooltip(chk_trim_silence, "trim_silence")

        row_timelapse = ctk.CTkFrame(cat_trim, fg_color="transparent")
        row_timelapse.pack(fill="x", pady=4)
        self._field_label(row_timelapse, "target_seconds").pack(side="right", padx=(5, 0))
        self.target_seconds_var = ctk.StringVar(value=state.video_editor_target_seconds)
        entry_target_seconds = ctk.CTkEntry(row_timelapse, textvariable=self.target_seconds_var, width=70, justify="center")
        entry_target_seconds.pack(side="right", padx=5)
        entry_target_seconds.bind("<Return>", self._on_target_seconds_changed)
        entry_target_seconds.bind("<FocusOut>", self._on_target_seconds_changed)

        row_keep_audio = ctk.CTkFrame(cat_audio, fg_color="transparent")
        row_keep_audio.pack(fill="x", pady=4)
        self.keep_audio_var = ctk.BooleanVar(value=state.video_editor_keep_audio)
        chk_keep_audio = ctk.CTkSwitch(
            row_keep_audio, text=t(FIELD_HELP["keep_audio"].term), variable=self.keep_audio_var,
            onvalue=True, offvalue=False, command=self._on_keep_audio_toggled
        )
        chk_keep_audio.pack(side="right", padx=5)
        self._attach_tooltip(chk_keep_audio, "keep_audio")

        row_loudnorm = ctk.CTkFrame(cat_audio, fg_color="transparent")
        row_loudnorm.pack(fill="x", pady=4)
        self.loudnorm_var = ctk.BooleanVar(value=state.video_editor_loudnorm)
        chk_loudnorm = ctk.CTkSwitch(
            row_loudnorm, text=t(FIELD_HELP["loudnorm"].term), variable=self.loudnorm_var,
            onvalue=True, offvalue=False, command=self._on_loudnorm_toggled
        )
        chk_loudnorm.pack(side="right", padx=5)
        self._attach_tooltip(chk_loudnorm, "loudnorm")

        row_thumbnail = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_thumbnail.pack(fill="x", pady=4)
        self.thumbnail_var = ctk.BooleanVar(value=state.video_editor_thumbnail)
        chk_thumbnail = ctk.CTkSwitch(
            row_thumbnail, text=t(FIELD_HELP["thumbnail"].term), variable=self.thumbnail_var,
            onvalue=True, offvalue=False, command=self._on_thumbnail_toggled
        )
        chk_thumbnail.pack(side="right", padx=5)
        self._attach_tooltip(chk_thumbnail, "thumbnail")

        # captions דורש --keep-audio (ראו video_editor.py).
        row_captions = ctk.CTkFrame(cat_captions, fg_color="transparent")
        row_captions.pack(fill="x", pady=4)
        self.captions_var = ctk.BooleanVar(value=state.video_editor_captions)
        chk_captions = ctk.CTkSwitch(
            row_captions, text=t(FIELD_HELP["captions"].term), variable=self.captions_var,
            onvalue=True, offvalue=False, command=self._on_captions_toggled
        )
        chk_captions.pack(side="right", padx=5)
        self._attach_tooltip(chk_captions, "captions")

        # תרגום כתוביות לאנגלית (item) - task="translate" המובנה של Whisper
        # עצמו, רלוונטי רק כש-captions פעיל בפועל.
        row_captions_translate = ctk.CTkFrame(cat_captions, fg_color="transparent")
        row_captions_translate.pack(fill="x", pady=4)
        self.captions_translate_var = ctk.BooleanVar(value=state.video_editor_captions_translate)
        chk_captions_translate = ctk.CTkSwitch(
            row_captions_translate, text=t(FIELD_HELP["captions_translate"].term), variable=self.captions_translate_var,
            onvalue=True, offvalue=False, command=self._on_captions_translate_toggled
        )
        chk_captions_translate.pack(side="right", padx=5)
        self._attach_tooltip(chk_captions_translate, "captions_translate")

        row_audio_filters = ctk.CTkFrame(cat_audio, fg_color="transparent")
        row_audio_filters.pack(fill="x", pady=4)
        self._field_label(row_audio_filters, "loudnorm_target").pack(side="right", padx=(5, 0))
        self.loudnorm_target_var = ctk.StringVar(value=state.video_editor_loudnorm_target)
        entry_loudnorm_target = ctk.CTkEntry(row_audio_filters, textvariable=self.loudnorm_target_var, width=70, justify="center")
        entry_loudnorm_target.pack(side="right", padx=5)
        entry_loudnorm_target.bind("<Return>", self._on_loudnorm_target_changed)
        entry_loudnorm_target.bind("<FocusOut>", self._on_loudnorm_target_changed)

        row_denoise = ctk.CTkFrame(cat_color, fg_color="transparent")
        row_denoise.pack(fill="x", pady=4)
        self.denoise_var = ctk.BooleanVar(value=state.video_editor_denoise)
        chk_denoise = ctk.CTkSwitch(
            row_denoise, text=t(FIELD_HELP["denoise"].term), variable=self.denoise_var,
            onvalue=True, offvalue=False, command=self._on_denoise_toggled
        )
        chk_denoise.pack(side="right", padx=5)
        self._attach_tooltip(chk_denoise, "denoise")

        row_sharpen = ctk.CTkFrame(cat_color, fg_color="transparent")
        row_sharpen.pack(fill="x", pady=4)
        self.sharpen_var = ctk.BooleanVar(value=state.video_editor_sharpen)
        chk_sharpen = ctk.CTkSwitch(
            row_sharpen, text=t(FIELD_HELP["sharpen"].term), variable=self.sharpen_var,
            onvalue=True, offvalue=False, command=self._on_sharpen_toggled
        )
        chk_sharpen.pack(side="right", padx=5)
        self._attach_tooltip(chk_sharpen, "sharpen")

        # קצב פריימים (item: שימור FPS מקורי) - ריק (ברירת מחדל) שומר את הקצב
        # המקורי של כל קובץ בנפרד; דריסה ידנית (מספר או שבר כמו 30000/1001)
        # חלה על כל הקבצים בריצה. HDR (item: שימור הגדרות HDR) אין לו שדה
        # בכוונה - הוא אוטומטי לגמרי (מזוהה מהקובץ עצמו, תלוי ב---codec שכבר
        # קיים), אין דגל/מצב לבחור בו כלל.
        row_fps = ctk.CTkFrame(cat_motion, fg_color="transparent")
        row_fps.pack(fill="x", pady=4)
        self._field_label(row_fps, "fps").pack(side="right", padx=(5, 0))
        self.fps_var = ctk.StringVar(value=state.video_editor_fps)
        entry_fps = ctk.CTkEntry(row_fps, textvariable=self.fps_var, width=90, justify="center", placeholder_text=t("למשל 30 או 30000/1001"))
        entry_fps.pack(side="right", padx=5)
        entry_fps.bind("<Return>", self._on_fps_changed)
        entry_fps.bind("<FocusOut>", self._on_fps_changed)

        # --- "שדרוג ענקי" - צבע/HDR, תנועה, אודיו, פילטרים ויזואליים, כתוביות
        # (item) - לא כולל smooth_fps/chromakey-similarity/blend, אותו עיקרון
        # "לא כל דגל צריך שדה" כמו watermark_scale.
        row_lut = ctk.CTkFrame(cat_color, fg_color="transparent")
        row_lut.pack(fill="x", pady=4)
        self._field_label(row_lut, "lut_path").pack(side="right", padx=(5, 0))
        self.lut_path_var = ctk.StringVar(value=state.video_editor_lut_path)
        entry_lut_path = ctk.CTkEntry(row_lut, textvariable=self.lut_path_var, placeholder_text=t("C:\\...\\look.cube"))
        entry_lut_path.pack(side="right", padx=5, fill="x", expand=True)
        entry_lut_path.bind("<Return>", self._on_lut_path_changed)
        entry_lut_path.bind("<FocusOut>", self._on_lut_path_changed)

        row_auto_levels = ctk.CTkFrame(cat_color, fg_color="transparent")
        row_auto_levels.pack(fill="x", pady=4)
        self.auto_levels_var = ctk.BooleanVar(value=state.video_editor_auto_levels)
        chk_auto_levels = ctk.CTkSwitch(
            row_auto_levels, text=t(FIELD_HELP["auto_levels"].term), variable=self.auto_levels_var,
            onvalue=True, offvalue=False, command=self._on_auto_levels_toggled
        )
        chk_auto_levels.pack(side="right", padx=5)
        self._attach_tooltip(chk_auto_levels, "auto_levels")

        row_noise_gate = ctk.CTkFrame(cat_audio, fg_color="transparent")
        row_noise_gate.pack(fill="x", pady=4)
        self.noise_gate_var = ctk.BooleanVar(value=state.video_editor_noise_gate)
        chk_noise_gate = ctk.CTkSwitch(
            row_noise_gate, text=t(FIELD_HELP["noise_gate"].term), variable=self.noise_gate_var,
            onvalue=True, offvalue=False, command=self._on_noise_gate_toggled
        )
        chk_noise_gate.pack(side="right", padx=5)
        self._attach_tooltip(chk_noise_gate, "noise_gate")

        row_remove_mid_silence = ctk.CTkFrame(cat_audio, fg_color="transparent")
        row_remove_mid_silence.pack(fill="x", pady=4)
        self.remove_mid_silence_var = ctk.BooleanVar(value=state.video_editor_remove_mid_silence)
        chk_remove_mid_silence = ctk.CTkSwitch(
            row_remove_mid_silence, text=t(FIELD_HELP["remove_mid_silence"].term), variable=self.remove_mid_silence_var,
            onvalue=True, offvalue=False, command=self._on_remove_mid_silence_toggled
        )
        chk_remove_mid_silence.pack(side="right", padx=5)
        self._attach_tooltip(chk_remove_mid_silence, "remove_mid_silence")

        row_stabilize = ctk.CTkFrame(cat_motion, fg_color="transparent")
        row_stabilize.pack(fill="x", pady=4)
        self.stabilize_var = ctk.BooleanVar(value=state.video_editor_stabilize)
        chk_stabilize = ctk.CTkSwitch(
            row_stabilize, text=t(FIELD_HELP["stabilize"].term), variable=self.stabilize_var,
            onvalue=True, offvalue=False, command=self._on_stabilize_toggled
        )
        chk_stabilize.pack(side="right", padx=5)
        self._attach_tooltip(chk_stabilize, "stabilize")

        row_chromakey = ctk.CTkFrame(cat_color, fg_color="transparent")
        row_chromakey.pack(fill="x", pady=4)
        self.chromakey_var = ctk.BooleanVar(value=state.video_editor_chromakey)
        chk_chromakey = ctk.CTkSwitch(
            row_chromakey, text=t(FIELD_HELP["chromakey"].term), variable=self.chromakey_var,
            onvalue=True, offvalue=False, command=self._on_chromakey_toggled
        )
        chk_chromakey.pack(side="right", padx=5)
        self._attach_tooltip(chk_chromakey, "chromakey")

        row_chromakey_colors = ctk.CTkFrame(cat_color, fg_color="transparent")
        row_chromakey_colors.pack(fill="x", pady=4)
        self._field_label(row_chromakey_colors, "chromakey_color").pack(side="right", padx=(5, 0))
        self.chromakey_color_var = ctk.StringVar(value=state.video_editor_chromakey_color)
        entry_chromakey_color = ctk.CTkEntry(row_chromakey_colors, textvariable=self.chromakey_color_var, width=90, justify="center")
        entry_chromakey_color.pack(side="right", padx=5)
        entry_chromakey_color.bind("<Return>", self._on_chromakey_color_changed)
        entry_chromakey_color.bind("<FocusOut>", self._on_chromakey_color_changed)
        self._attach_tooltip(entry_chromakey_color, "chromakey_color")
        self.chromakey_bg_color_var = ctk.StringVar(value=state.video_editor_chromakey_bg_color)
        entry_chromakey_bg_color = ctk.CTkEntry(row_chromakey_colors, textvariable=self.chromakey_bg_color_var, width=90, justify="center")
        entry_chromakey_bg_color.pack(side="right", padx=5)
        self._attach_tooltip(entry_chromakey_bg_color, "chromakey_bg_color")
        entry_chromakey_bg_color.bind("<Return>", self._on_chromakey_bg_color_changed)
        entry_chromakey_bg_color.bind("<FocusOut>", self._on_chromakey_bg_color_changed)

        row_caption_style = ctk.CTkFrame(cat_captions, fg_color="transparent")
        row_caption_style.pack(fill="x", pady=4)
        self._field_label(row_caption_style, "caption_font").pack(side="right", padx=(5, 0))
        self.caption_font_var = ctk.StringVar(value=state.video_editor_caption_font)
        entry_caption_font = ctk.CTkEntry(row_caption_style, textvariable=self.caption_font_var, width=90, justify="center")
        entry_caption_font.pack(side="right", padx=5)
        entry_caption_font.bind("<Return>", self._on_caption_font_changed)
        entry_caption_font.bind("<FocusOut>", self._on_caption_font_changed)
        self._field_label(row_caption_style, "caption_font_size").pack(side="right", padx=(5, 0))
        self.caption_font_size_var = ctk.StringVar(value=state.video_editor_caption_font_size)
        entry_caption_font_size = ctk.CTkEntry(row_caption_style, textvariable=self.caption_font_size_var, width=50, justify="center")
        entry_caption_font_size.pack(side="right", padx=5)
        entry_caption_font_size.bind("<Return>", self._on_caption_font_size_changed)
        entry_caption_font_size.bind("<FocusOut>", self._on_caption_font_size_changed)

        row_caption_style2 = ctk.CTkFrame(cat_captions, fg_color="transparent")
        row_caption_style2.pack(fill="x", pady=4)
        self._field_label(row_caption_style2, "caption_color").pack(side="right", padx=(5, 0))
        self.caption_color_var = ctk.StringVar(value=state.video_editor_caption_color)
        entry_caption_color = ctk.CTkEntry(row_caption_style2, textvariable=self.caption_color_var, width=90, justify="center")
        entry_caption_color.pack(side="right", padx=5)
        entry_caption_color.bind("<Return>", self._on_caption_color_changed)
        entry_caption_color.bind("<FocusOut>", self._on_caption_color_changed)
        self._caption_position_display_to_value = {
            t("תחתון"): "bottom", t("עליון"): "top", t("מרכז"): "center",
        }
        self._caption_position_value_to_display = {v: k for k, v in self._caption_position_display_to_value.items()}
        self._field_label(row_caption_style2, "caption_position").pack(side="right", padx=(5, 0))
        self.caption_position_menu = ctk.CTkOptionMenu(
            row_caption_style2, values=list(self._caption_position_display_to_value.keys()), command=self._on_caption_position_selected, width=90
        )
        self.caption_position_menu.pack(side="right", padx=5)

        row_codec = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_codec.pack(fill="x", pady=(4, 0))
        self._field_label(row_codec, "codec").pack(side="right", padx=(5, 0))
        self.codec_menu = ctk.CTkOptionMenu(
            row_codec, values=list(self._codec_display_to_value.keys()), command=self._on_codec_selected
        )
        self.codec_menu.pack(side="right", padx=5, fill="x", expand=True)

        # שימור רזולוציית מקור / ביטול סיומת שם קובץ / קידוד מקביל ודרגת מאמץ
        # (items: לא להקטין ל-1080p, ביטול _edited_horizontal/_edited_vertical,
        # מספר סרטונים בו-זמנית + חוגת משאבי-מחשב).
        row_preserve_resolution = ctk.CTkFrame(cat_format, fg_color="transparent")
        row_preserve_resolution.pack(fill="x", pady=4)
        self.preserve_resolution_var = ctk.BooleanVar(value=state.video_editor_preserve_resolution)
        chk_preserve_resolution = ctk.CTkSwitch(
            row_preserve_resolution, text=t(FIELD_HELP["preserve_resolution"].term), variable=self.preserve_resolution_var,
            onvalue=True, offvalue=False, command=self._on_preserve_resolution_toggled
        )
        chk_preserve_resolution.pack(side="right", padx=5)
        self._attach_tooltip(chk_preserve_resolution, "preserve_resolution")

        row_no_suffix = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_no_suffix.pack(fill="x", pady=4)
        self.no_suffix_var = ctk.BooleanVar(value=state.video_editor_no_suffix)
        chk_no_suffix = ctk.CTkSwitch(
            row_no_suffix, text=t(FIELD_HELP["no_suffix"].term), variable=self.no_suffix_var,
            onvalue=True, offvalue=False, command=self._on_no_suffix_toggled
        )
        chk_no_suffix.pack(side="right", padx=5)
        self._attach_tooltip(chk_no_suffix, "no_suffix")

        # מספור סרטונים ברצף (item: אופציית מספור זהה ל-rocket_shorts_publisher.py) -
        # counter נפרד ומתמשך (data/video_editor_counter.txt), ראו utils/video/video_editor_counter.py.
        row_number_videos = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_number_videos.pack(fill="x", pady=4)
        self.number_videos_var = ctk.BooleanVar(value=state.video_editor_number_videos)
        chk_number_videos = ctk.CTkSwitch(
            row_number_videos, text=t(FIELD_HELP["number_videos"].term), variable=self.number_videos_var,
            onvalue=True, offvalue=False, command=self._on_number_videos_toggled
        )
        chk_number_videos.pack(side="right", padx=5)
        self._attach_tooltip(chk_number_videos, "number_videos")

        row_number_settings = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_number_settings.pack(fill="x", pady=4)
        self._field_label(row_number_settings, "number_prefix").pack(side="right", padx=(5, 0))
        self.number_prefix_var = ctk.StringVar(value=state.video_editor_number_prefix)
        entry_number_prefix = ctk.CTkEntry(row_number_settings, textvariable=self.number_prefix_var, width=100)
        entry_number_prefix.pack(side="right", padx=5)
        entry_number_prefix.bind("<Return>", self._on_number_prefix_changed)
        entry_number_prefix.bind("<FocusOut>", self._on_number_prefix_changed)
        self._field_label(row_number_settings, "number_start").pack(side="right", padx=(5, 0))
        self.number_start_var = ctk.StringVar(value=state.video_editor_number_start)
        entry_number_start = ctk.CTkEntry(row_number_settings, textvariable=self.number_start_var, width=70, justify="center")
        entry_number_start.pack(side="right", padx=5)
        entry_number_start.bind("<Return>", self._on_number_start_changed)
        entry_number_start.bind("<FocusOut>", self._on_number_start_changed)

        row_parallel_effort = ctk.CTkFrame(cat_resources, fg_color="transparent")
        row_parallel_effort.pack(fill="x", pady=4)
        self._field_label(row_parallel_effort, "parallel").pack(side="right", padx=(5, 0))
        self.parallel_var = ctk.StringVar(value=state.video_editor_parallel)
        entry_parallel = ctk.CTkEntry(row_parallel_effort, textvariable=self.parallel_var, width=50, justify="center")
        entry_parallel.pack(side="right", padx=5)
        entry_parallel.bind("<Return>", self._on_parallel_changed)
        entry_parallel.bind("<FocusOut>", self._on_parallel_changed)
        self._field_label(row_parallel_effort, "effort").pack(side="right", padx=(5, 0))
        self._effort_display_to_value = {
            t("גבוה (ברירת מחדל)"): "high", t("בינוני"): "medium", t("נמוך"): "low", t("אוטומטי (לפי עומס)"): "auto",
        }
        self._effort_value_to_display = {v: k for k, v in self._effort_display_to_value.items()}
        self.effort_menu = ctk.CTkOptionMenu(
            row_parallel_effort, values=list(self._effort_display_to_value.keys()), command=self._on_effort_selected, width=130
        )
        self.effort_menu.pack(side="right", padx=5)

        # מגבלת-מקביליות אמיתית ל-NVENC (item) - ריק=אוטומטי (נבדק בפועל בתחילת
        # הריצה, ראו --max-concurrent-nvenc ב-video_editor.py); רלוונטי רק כש-
        # --parallel>1 וקודק hevc/av1, אבל השדה עצמו תמיד מוצג (בלי לוגיקת
        # הצגה-מותנית מורכבת) - הסקריפט עצמו כבר מתעלם ממנו בשקט כשלא רלוונטי.
        row_nvenc_concurrency = ctk.CTkFrame(cat_resources, fg_color="transparent")
        row_nvenc_concurrency.pack(fill="x", pady=4)
        self._field_label(row_nvenc_concurrency, "max_concurrent_nvenc").pack(side="right", padx=(5, 0))
        self.max_concurrent_nvenc_var = ctk.StringVar(value=state.video_editor_max_concurrent_nvenc)
        entry_max_concurrent_nvenc = ctk.CTkEntry(row_nvenc_concurrency, textvariable=self.max_concurrent_nvenc_var, width=50, justify="center")
        entry_max_concurrent_nvenc.pack(side="right", padx=5)
        entry_max_concurrent_nvenc.bind("<Return>", self._on_max_concurrent_nvenc_changed)
        entry_max_concurrent_nvenc.bind("<FocusOut>", self._on_max_concurrent_nvenc_changed)

        row_container = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_container.pack(fill="x", pady=4)
        self._field_label(row_container, "container").pack(side="right", padx=(5, 0))
        self._container_display_to_value = {"MP4": "mp4", "MKV": "mkv"}
        self._container_value_to_display = {v: k for k, v in self._container_display_to_value.items()}
        self.container_menu = ctk.CTkOptionMenu(
            row_container, values=list(self._container_display_to_value.keys()), command=self._on_container_selected, width=90
        )
        self.container_menu.pack(side="right", padx=5)

        row_output_template = ctk.CTkFrame(cat_export, fg_color="transparent")
        row_output_template.pack(fill="x", pady=4)
        self._field_label(row_output_template, "output_template").pack(side="right", padx=(5, 0))
        self.output_template_var = ctk.StringVar(value=state.video_editor_output_template)
        entry_output_template = ctk.CTkEntry(row_output_template, textvariable=self.output_template_var, placeholder_text=t("{date}_{name}_{codec}"))
        entry_output_template.pack(side="right", padx=5, fill="x", expand=True)
        entry_output_template.bind("<Return>", self._on_output_template_changed)
        entry_output_template.bind("<FocusOut>", self._on_output_template_changed)

        row_validate_notify = ctk.CTkFrame(cat_resources, fg_color="transparent")
        row_validate_notify.pack(fill="x", pady=4)
        self.validate_only_var = ctk.BooleanVar(value=state.video_editor_validate_only)
        chk_validate_only = ctk.CTkSwitch(
            row_validate_notify, text=t(FIELD_HELP["validate_only"].term), variable=self.validate_only_var,
            onvalue=True, offvalue=False, command=self._on_validate_only_toggled
        )
        chk_validate_only.pack(side="right", padx=5)
        self._attach_tooltip(chk_validate_only, "validate_only")
        self.notify_per_file_var = ctk.BooleanVar(value=state.video_editor_notify_per_file)
        chk_notify_per_file = ctk.CTkSwitch(
            row_validate_notify, text=t(FIELD_HELP["notify_per_file"].term), variable=self.notify_per_file_var,
            onvalue=True, offvalue=False, command=self._on_notify_per_file_toggled
        )
        chk_notify_per_file.pack(side="right", padx=5)
        self._attach_tooltip(chk_notify_per_file, "notify_per_file")

        row_export_report = ctk.CTkFrame(cat_resources, fg_color="transparent")
        row_export_report.pack(fill="x", pady=4)
        self._field_label(row_export_report, "export_report").pack(side="right", padx=(5, 0))
        self._export_report_display_to_value = {
            t("כבוי (ברירת מחדל)"): "", t("CSV"): "csv", t("Excel"): "xlsx", t("שניהם"): "both",
        }
        self._export_report_value_to_display = {v: k for k, v in self._export_report_display_to_value.items()}
        self.export_report_menu = ctk.CTkOptionMenu(
            row_export_report, values=list(self._export_report_display_to_value.keys()), command=self._on_export_report_selected, width=140
        )
        self.export_report_menu.pack(side="right", padx=5)

        # פאנל timelapse_maker.py - מוצג רק כשהסקריפט הנבחר הוא הסקריפט הזה
        # (אותו דפוס בדיוק כמו video_editor_frame). לפני הפאנל הזה, --keep-audio
        # של הסקריפט (שכבוי כברירת מחדל ב-CLI) לא היה נגיש בכלל מה-GUI - כל
        # טיימלאפס שהופק מהממשק יצא שקט לגמרי, בלי שום דרך לשנות את זה.
        self.timelapse_frame = ctk.CTkFrame(self, fg_color="transparent")
        row_timelapse_target = ctk.CTkFrame(self.timelapse_frame, fg_color="transparent")
        row_timelapse_target.pack(fill="x", pady=4)
        ctk.CTkLabel(row_timelapse_target, text=t("אורך יעד לטיימלאפס (שניות):"), anchor="e", justify="right").pack(side="right", padx=(5, 0))
        self.timelapse_target_seconds_var = ctk.StringVar(value=state.timelapse_target_seconds)
        entry_timelapse_target = ctk.CTkEntry(row_timelapse_target, textvariable=self.timelapse_target_seconds_var, width=70, justify="center")
        entry_timelapse_target.pack(side="right", padx=5)
        entry_timelapse_target.bind("<Return>", self._on_timelapse_target_seconds_changed)
        entry_timelapse_target.bind("<FocusOut>", self._on_timelapse_target_seconds_changed)

        self.timelapse_keep_audio_var = ctk.BooleanVar(value=state.timelapse_keep_audio)
        chk_timelapse_keep_audio = ctk.CTkSwitch(
            row_timelapse_target, text=t("שמור אודיו"), variable=self.timelapse_keep_audio_var,
            onvalue=True, offvalue=False, command=self._on_timelapse_keep_audio_toggled
        )
        chk_timelapse_keep_audio.pack(side="right", padx=5)

        self._rebuild_favorites_box()
        self._start_periodic_ui_refresh()

    def _build_collapsible_category(self, parent, title, category_key=None):
        """סקציה ניתנת-לקיפול/פתיחה (item: קטגוריות מסודרות בעורך-העל) - כרטיס
        עם כותרת לחיצה (שברון ▾/▸ + שם) שמחליפה בין פתוח/סגור; פתוחה כברירת
        מחדל (item: פתוחות כברירת מחדל, ניתן לסגור/לפתוח). מחזירה את content
        (CTkFrame) - כל שורות ההגדרה של הקטגוריה נכנסות פנימה, לא ישירות
        ל-parent, כדי שקיפול הכותרת יקפל את כולן כיחידה אחת. זהה בעיקרון
        ל-<details>/<summary> הקיים בווב (web_app.py) - שם זה חינם מה-דפדפן,
        כאן צריך לבנות את זה ידנית כי ל-CTk/Tkinter אין רכיב accordion מובנה.

        category_key (item: קידוד-צבע + תקציר-מצב לקטגוריה) - כשסופק, גבול
        הכרטיס צובע לפי _CATEGORY_COLORS[category_key], ומתווסף תווית-תקציר
        דהויה מתחת לכותרת (למשל "3 מתגים פעילים") שמתעדכנת מ-_update_category_summaries
        (נקראת ממעגל-הרענון התקופתי, לא מכל handler בנפרד - ראו _start_periodic_ui_refresh)."""
        color = _CATEGORY_COLORS.get(category_key)
        section = ctk.CTkFrame(
            parent, fg_color=PALETTE["surface_deep"], corner_radius=8,
            border_width=2 if color else 0, border_color=color or PALETTE["border"],
        )
        section.pack(fill="x", pady=(0, 8))
        header = ctk.CTkFrame(section, fg_color="transparent", cursor="hand2")
        header.pack(fill="x", padx=4, pady=4)
        chevron_var = ctk.StringVar(value="▾")
        chevron_label = ctk.CTkLabel(header, textvariable=chevron_var, width=18, anchor="w")
        chevron_label.pack(side="left", padx=(6, 0))
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(side="right", padx=(0, 6), fill="x", expand=True)
        title_label = ctk.CTkLabel(title_row, text=title, anchor="e", justify="right", font=("Segoe UI", 13, "bold"))
        title_label.pack(anchor="e", fill="x")
        summary_var = ctk.StringVar(value="")
        summary_label = ctk.CTkLabel(
            title_row, textvariable=summary_var, anchor="e", justify="right",
            font=("Segoe UI", 10), text_color=PALETTE["text_muted"],
        )
        summary_label.pack(anchor="e", fill="x")
        content = ctk.CTkFrame(section, fg_color="transparent")
        content.pack(fill="x", padx=10, pady=(0, 10))
        if category_key:
            self._category_content_by_key[category_key] = content
            self._category_summary_vars[category_key] = summary_var

        is_open = {"value": True}

        def _toggle(_event=None):
            if is_open["value"]:
                content.pack_forget()
                chevron_var.set("▸")
            else:
                content.pack(fill="x", padx=10, pady=(0, 10))
                chevron_var.set("▾")
            is_open["value"] = not is_open["value"]

        header.bind("<Button-1>", _toggle)
        chevron_label.bind("<Button-1>", _toggle)
        title_row.bind("<Button-1>", _toggle)
        title_label.bind("<Button-1>", _toggle)
        return content

    def _field_label(self, parent, field_key, **extra_kwargs):
        """CTkLabel עם מונח קצר מ-FIELD_HELP (item: מונח קצר במקום רצף-מילים)
        + טולטיפ-הובר עם ההסבר המלא (item: הסבר-בהובר) - התחליף לתווית שהייתה
        קודם מכילה משפט-הסבר שלם. משמש לכל שדה "תווית + control" בעורך-העל."""
        help_ = FIELD_HELP[field_key]
        label = ctk.CTkLabel(parent, text=t(help_.term), anchor="e", justify="right", **extra_kwargs)
        Tooltip(label, help_.tooltip)
        return label

    def _attach_tooltip(self, widget, field_key):
        """מצרף טולטיפ-הובר לפי FIELD_HELP בלי לשנות טקסט קיים - לשימוש
        ב-switch-ים, שכבר מציגים את המונח הקצר בתור ה-text שלהם."""
        Tooltip(widget, FIELD_HELP[field_key].tooltip)
        return widget

    def _open_glossary_dialog(self):
        """מקראה (item: הסבר בתוך מקראה שנפתחת בלחיצה) - דיאלוג עם כל המונחים
        וההסברים מ-FIELD_HELP במקום אחד, עם חיפוש טקסט חי - להבדיל מהטולטיפים
        (per-field, דורשים לרחף בדיוק מעל השדה) זו רשימה מלאה ניתנת-לסריקה/
        חיפוש, לשימוש כשלא בטוחים באיזה שדה בכלל לחפש."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(t("📖 מקראה - כל ההגדרות בעורך-העל"))
        dialog.geometry("440x560")
        dialog.transient(self.winfo_toplevel())

        search_var = ctk.StringVar(value="")
        search_entry = ctk.CTkEntry(dialog, textvariable=search_var, placeholder_text=t("חפש מונח..."), justify="right")
        search_entry.pack(fill="x", padx=10, pady=(10, 5))

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        entries = sorted(FIELD_HELP.items(), key=lambda kv: kv[1].term)

        def _rebuild(_event=None):
            for child in scroll.winfo_children():
                child.destroy()
            query = search_var.get().strip().lower()
            for _key, help_ in entries:
                if query and query not in help_.term.lower() and query not in help_.tooltip.lower():
                    continue
                row = ctk.CTkFrame(scroll, fg_color=PALETTE["surface_deep"], corner_radius=6)
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text=t(help_.term), anchor="e", justify="right", font=("Segoe UI", 12, "bold")).pack(fill="x", padx=8, pady=(6, 0))
                ctk.CTkLabel(row, text=t(help_.tooltip), anchor="e", justify="right", wraplength=380, text_color=PALETTE["text_muted"], font=FONT_HEBREW_TEXT).pack(fill="x", padx=8, pady=(0, 6))

        search_entry.bind("<KeyRelease>", _rebuild)
        _rebuild()
        ctk.CTkButton(dialog, text=t("סגור"), command=dialog.destroy).pack(pady=(0, 10))
        dialog.search_var = search_var  # נגיש לטסטים - עדכון ה-Var + קריאה ל-rebuild ישירה, בלי להסתמך על סימולציית אירועי-מקלדת שלא תמיד אמינה בחלון לא-מצויר
        dialog.rebuild = _rebuild
        return dialog

    def _update_category_summaries(self):
        """תקציר-מצב בכותרת קטגוריה מקופלת (item) - סופר switch-ים פעילים
        ו-entry-ים לא-ריקים בכל קטגוריה, כדי שאפשר יהיה לדעת מה מוגדר בלי
        לפתוח כל קטגוריה בנפרד. נקרא ממעגל-הרענון התקופתי (לא מכל handler
        בנפרד - 40+ handlers, זול משמעותית לרענן הכל ביחד כל שנייה-שתיים)."""
        for key, content in self._category_content_by_key.items():
            summary_var = self._category_summary_vars.get(key)
            if summary_var is None or not content.winfo_exists():
                continue
            active_switches = 0
            filled_entries = 0
            for widget in _collect_widgets(content):
                if isinstance(widget, ctk.CTkSwitch):
                    if widget.get():
                        active_switches += 1
                elif isinstance(widget, ctk.CTkEntry):
                    if widget.get().strip():
                        filled_entries += 1
            parts = []
            if active_switches:
                parts.append(t("{n} מתגים פעילים", n=active_switches))
            if filled_entries:
                parts.append(t("{n} שדות מלאים", n=filled_entries))
            summary_var.set(" · ".join(parts) if parts else t("ללא הגדרות מיוחדות"))

    def _is_personal_profile_selected(self):
        return self._profile_display_to_name.get(self.preset_menu.get()) is not None

    def _update_unsaved_indicator(self):
        """נקודת "שינויים לא-שמורים" (item) - משווה את הסנאפשוט החי הנוכחי
        (state.video_editor_*) מול _profile_baseline_snapshot שנלכד בפעם
        האחרונה שפרופיל אישי נטען/נשמר. רלוונטי רק כשפרופיל אישי אמיתי נבחר
        כרגע - ל-presets קבועים ("בחר פרופיל...") אין מושג "לא-שמור" (אין שם
        שאליו לשמור)."""
        if not self._is_personal_profile_selected() or self._profile_baseline_snapshot is None:
            self.unsaved_indicator_var.set("")
            return
        is_dirty = self._collect_video_editor_profile_settings() != self._profile_baseline_snapshot
        self.unsaved_indicator_var.set(t("● שינויים לא-שמורים") if is_dirty else "")

    def _capture_profile_baseline(self):
        self._profile_baseline_snapshot = self._collect_video_editor_profile_settings()
        self._update_unsaved_indicator()

    def _start_periodic_ui_refresh(self):
        """מעגל-רענון תקופתי משותף (item: תקציר-קטגוריה + שינויים לא-שמורים) -
        polling קל (אחת לשנייה) במקום לחבר trace ל-48+ Var-ים בנפרד; שני
        העדכונים זולים (רק winfo/get() על widgets קיימים, בלי I/O), אז רענון
        משותף אחד עדיף על תחזוקת חיבורי-trace נפרדים לכל שדה."""
        if not self.winfo_exists():
            return
        self._update_category_summaries()
        self._update_unsaved_indicator()
        self.after(1200, self._start_periodic_ui_refresh)

    def _dismiss_video_editor_onboarding(self):
        state.video_editor_onboarding_seen = True
        state.save_config()
        self.video_editor_onboarding_banner.pack_forget()

    def _reset_video_editor_to_defaults(self):
        """item: איפוס לברירת מחדל - מאשר (פעולה הרסנית לכל שינוי לא-שמור),
        ואז משתמש ב-_apply_video_editor_profile_fields({}) הקיים (כבר בדוק -
        כל שדה נופל לברירת המחדל שלו כשהמפתח חסר) ומרענן את כל ה-widgets
        מ-state דרך update_script_context - לא נוגע בפרופילים שמורים על הדיסק."""
        if not messagebox.askyesno(t("איפוס לברירת מחדל"), t("לאפס את כל הגדרות עורך-העל לברירת המחדל? פרופילים שמורים לא יימחקו.")):
            return
        self._apply_video_editor_profile_fields({})
        self.preset_menu.set(self._preset_placeholder)
        self._preset_menu_previous_display = self._preset_placeholder
        self.update_profile_btn.pack_forget()
        self.rename_profile_btn.pack_forget()
        self.delete_profile_btn.pack_forget()
        self._profile_baseline_snapshot = None
        if hasattr(self, "_last_script_context"):
            self.update_script_context(*self._last_script_context)

    def _confirm_discard_unsaved_if_needed(self):
        """אישור לפני מעבר/סגירה עם שינויים לא-שמורים (item) - נקרא לפני
        בחירת פרופיל/preset אחר מהתפריט. מחזיר True אם מותר להמשיך (אין
        שינויים לא-שמורים, או שהמשתמש אישר לוותר עליהם)."""
        if not self._is_personal_profile_selected() or self._profile_baseline_snapshot is None:
            return True
        if self._collect_video_editor_profile_settings() == self._profile_baseline_snapshot:
            return True
        return messagebox.askyesno(
            t("שינויים לא-שמורים"),
            t("יש שינויים לא-שמורים בפרופיל הנוכחי. לעבור בכל זאת ולוותר עליהם?"),
        )

    def _on_ai_provider_selected(self, display_value):
        state.story_cutter_ai_provider = self._ai_provider_display_to_value.get(display_value, "gemini")
        state.save_config()

    def _set_watermark_path(self, path):
        state.video_editor_watermark_path = path
        self.watermark_path_var.set(path)
        state.save_config()
        self._update_watermark_preview()

    def _on_watermark_entry_changed(self, event=None):
        state.video_editor_watermark_path = self.watermark_path_var.get().strip()
        state.save_config()
        self._update_watermark_preview()

    def _parse_watermark_scale_fraction(self, raw):
        """0.05-0.5 (5%-50% מרוחב הפלט) - טווח סביר, מספיק רחב לכל שימוש אמיתי
        (מתחת ל-5% בלתי-קריא, מעל 50% כובש את הפריים) - קלט לא תקין נופל
        בחזרה ל-15% (ברירת המחדל הקיימת של --watermark_scale)."""
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.15
        return max(0.05, min(0.5, value))

    def _scale_to_percent_str(self, raw):
        return str(round(self._parse_watermark_scale_fraction(raw) * 100))

    def _parse_scale_percent(self, raw_percent):
        try:
            value = float(raw_percent)
        except (TypeError, ValueError):
            return 15.0
        return max(5.0, min(50.0, value))

    def _parse_watermark_custom_center(self):
        """(x_fraction, y_fraction) של מרכז ה-watermark אם שניהם הוגדרו
        (item: גרירת watermark חופשית) - None (חוזר למיקום-פינה/מרכז קבוע)
        אם אחד מהם חסר/לא תקין, אותו עיקרון בדיוק כמו --watermark_x/--watermark_y
        ב-video_editor.py (שניהם ביחד, לא חלקי)."""
        try:
            return (float(state.video_editor_watermark_x), float(state.video_editor_watermark_y))
        except (TypeError, ValueError):
            return None

    def _on_watermark_scale_changed(self, event=None):
        percent = round(self._parse_scale_percent(self.watermark_scale_var.get().strip()))
        state.video_editor_watermark_scale = str(round(percent / 100, 4))
        self.watermark_scale_var.set(str(percent))
        self.watermark_scale_slider_var.set(percent)
        state.save_config()
        self._update_watermark_preview()

    def _on_watermark_scale_slider_changed(self, value):
        percent = round(self._parse_scale_percent(value))
        state.video_editor_watermark_scale = str(round(percent / 100, 4))
        self.watermark_scale_var.set(str(percent))
        state.save_config()
        self._update_watermark_preview()

    def _clear_watermark_custom_position(self):
        state.video_editor_watermark_x = ""
        state.video_editor_watermark_y = ""
        state.save_config()
        self.wm_drag_coords_var.set("")
        self._update_watermark_preview()

    def _on_watermark_drag_start(self, event):
        if self._wm_preview_ctk_image is None:
            return
        self._wm_drag_start = (event.x, event.y)

    def _on_watermark_drag_motion(self, event):
        # item: גרירת watermark חופשית - dx/dy מהמרחק שהעכבר זז *מנקודת התפיסה
        # המקורית על ה-widget עצמו* (לא מהפינה שלו) - event.x/y תמיד יחסיים
        # למיקום הנוכחי של ה-widget הנגרר, אז זה נכון גם אחרי כמה .place() רצופים
        # (הדפוס הסטנדרטי לגרירת widget ב-Tkinter).
        if self._wm_preview_ctk_image is None or self._wm_drag_start is None:
            return
        dx = event.x - self._wm_drag_start[0]
        dy = event.y - self._wm_drag_start[1]
        vertical = self.vertical_var.get()
        box_w, box_h = _WM_PREVIEW_BOX_SIZES[vertical]
        label_w = self.wm_preview_label.winfo_width()
        label_h = self.wm_preview_label.winfo_height()
        new_x = max(0, min(self.wm_preview_label.winfo_x() + dx, max(0, box_w - label_w)))
        new_y = max(0, min(self.wm_preview_label.winfo_y() + dy, max(0, box_h - label_h)))
        self.wm_preview_label.place(x=new_x, y=new_y)
        # מרכז ה-watermark (לא הפינה השמאלית-עליונה) - תואם ל-compute_watermark_geometry's
        # custom_center_fraction, כדי שגודל שמשתנה אח"כ לא "יזיז" את הנקודה שנגררה.
        center_x_fraction = max(0.0, min(1.0, (new_x + label_w / 2) / box_w))
        center_y_fraction = max(0.0, min(1.0, (new_y + label_h / 2) / box_h))
        state.video_editor_watermark_x = str(round(center_x_fraction, 4))
        state.video_editor_watermark_y = str(round(center_y_fraction, 4))
        # item: מספרים מדויקים ליד גרירת ה-watermark - עדכון חי בזמן הגרירה
        # עצמה, לכיוונון עדין גם למי שרוצה דיוק ולא רק מיקום ויזואלי-חופשי.
        self.wm_drag_coords_var.set(f"x={center_x_fraction * 100:.0f}%  y={center_y_fraction * 100:.0f}%")

    def _on_watermark_drag_end(self, event):
        # לא נכתב לדיסק בכל אירוע B1-Motion (הרבה עשרות בשנייה) - רק פעם אחת
        # כשהגרירה בפועל מסתיימת.
        if self._wm_drag_start is None:
            return
        self._wm_drag_start = None
        state.save_config()

    def _update_watermark_preview(self):
        """מציג את ה-watermark מוקטן במיקום/גודל היחסי הנכון בתוך wm_preview_box -
        אותו חישוב גיאומטריה בדיוק (compute_watermark_geometry/resolve_output_dimensions)
        ששרשרת ה-ffmpeg האמיתית משתמשת בו, כדי שהתצוגה תשקף בדיוק מה שיתקבל
        בפלט. מציג תיבה ריקה (בלי image) בכל מצב שלא ניתן לחשב תצוגה תקינה -
        אין נתיב, קובץ לא נמצא/לא תמונה תקינה - בלי לזרוק שגיאה למשתמש, זו
        רק תצוגה מקדימה אופציונלית."""
        path = self.watermark_path_var.get().strip()
        if not path or not os.path.isfile(path):
            self.wm_preview_label.configure(image=None)
            self._wm_preview_ctk_image = None
            return
        try:
            with Image.open(path) as img:
                wm_width, wm_height = img.size
                img_copy = img.convert("RGBA")
        except Exception:
            self.wm_preview_label.configure(image=None)
            self._wm_preview_ctk_image = None
            return

        vertical = self.vertical_var.get()
        output_width, output_height = resolve_output_dimensions(vertical)
        position = state.video_editor_watermark_position
        scale_fraction = self._parse_watermark_scale_fraction(state.video_editor_watermark_scale)
        custom_center_fraction = self._parse_watermark_custom_center()
        try:
            target_w, target_h, x, y = compute_watermark_geometry(
                output_width, output_height, wm_width, wm_height, position,
                scale_fraction=scale_fraction, custom_center_fraction=custom_center_fraction,
            )
        except ValueError:
            self.wm_preview_label.configure(image=None)
            self._wm_preview_ctk_image = None
            return

        box_w, box_h = _WM_PREVIEW_BOX_SIZES[vertical]
        self.wm_preview_box.configure(width=box_w, height=box_h)
        preview_scale = box_w / output_width
        scaled_w = max(1, round(target_w * preview_scale))
        scaled_h = max(1, round(target_h * preview_scale))
        scaled_x = round(x * preview_scale)
        scaled_y = round(y * preview_scale)

        resized = img_copy.resize((scaled_w, scaled_h))
        # שקיפות (item: watermark opacity) - כופל את ערוץ האלפא הקיים (לא דורס
        # אותו), זהה בדיוק לאופן שבו colorchannelmixer=aa=X פועל ב-ffmpeg עצמו.
        try:
            opacity = max(0.0, min(1.0, float(state.video_editor_watermark_opacity)))
        except ValueError:
            opacity = 1.0
        if opacity < 1.0:
            alpha = resized.split()[3].point(lambda p, o=opacity: int(p * o))
            resized.putalpha(alpha)
        self._wm_preview_ctk_image = ctk.CTkImage(light_image=resized, dark_image=resized, size=(scaled_w, scaled_h))
        self.wm_preview_label.configure(image=self._wm_preview_ctk_image, text="")
        self.wm_preview_label.place(x=scaled_x, y=scaled_y)
        if custom_center_fraction is not None:
            self.wm_drag_coords_var.set(f"x={custom_center_fraction[0] * 100:.0f}%  y={custom_center_fraction[1] * 100:.0f}%")
        else:
            self.wm_drag_coords_var.set("")

    def choose_watermark_file(self):
        current = self.watermark_path_var.get()
        initial_dir = os.path.dirname(current) if current and os.path.isfile(current) else None
        f = filedialog.askopenfilename(
            initialdir=initial_dir,
            filetypes=[("קובצי תמונה", "*.png;*.jpg;*.jpeg;*.webp"), ("כל הקבצים", "*.*")]
        )
        if f:
            self._set_watermark_path(os.path.normpath(f))

    def on_watermark_dropped(self, event):
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = raw.split("} {")[0] if "} {" in raw else raw
        if os.path.isfile(path):
            self._set_watermark_path(os.path.normpath(path))

    def _on_watermark_position_selected(self, display_value):
        state.video_editor_watermark_position = self._wm_position_display_to_value.get(display_value, "bottom-right")
        # בחירת preset מהרשימה גוברת על מיקום מותאם-אישית קודם (גרירה) - אחרת
        # ה-preset הנבחר לא היה משפיע כלל בפועל (custom_center_fraction עדיין גובר).
        state.video_editor_watermark_x = ""
        state.video_editor_watermark_y = ""
        state.save_config()
        self.wm_position_menu.set(display_value)
        self._sync_favorite_mirror("watermark_position", display_value)
        self._update_watermark_preview()

    def _parse_opacity(self, raw):
        try:
            return max(0.0, min(1.0, float(raw)))
        except (TypeError, ValueError):
            return 1.0

    def _on_watermark_opacity_changed(self, event=None):
        value = self._parse_opacity(self.watermark_opacity_var.get().strip())
        state.video_editor_watermark_opacity = str(value)
        self.watermark_opacity_var.set(str(value))
        self.watermark_opacity_slider_var.set(value)
        state.save_config()
        self._update_watermark_preview()

    def _on_watermark_opacity_slider_changed(self, value):
        value = round(self._parse_opacity(value), 2)
        state.video_editor_watermark_opacity = str(value)
        self.watermark_opacity_var.set(str(value))
        state.save_config()
        self._update_watermark_preview()

    def _on_remove_watermark_position_selected(self, display_value):
        state.video_editor_remove_watermark_position = self._remove_wm_position_display_to_value.get(display_value, "")
        state.save_config()
        self.remove_wm_position_menu.set(display_value)
        self._sync_favorite_mirror("remove_watermark_position", display_value)

    def _on_vertical_toggled(self):
        state.video_editor_vertical = self.vertical_var.get()
        state.save_config()
        self._update_watermark_preview()

    def _on_smart_crop_toggled(self):
        state.video_editor_smart_crop = self.smart_crop_var.get()
        state.save_config()

    def _on_blur_background_toggled(self):
        state.video_editor_blur_background = self.blur_background_var.get()
        state.save_config()

    def _on_trim_start_changed(self, event=None):
        typed = self.trim_start_var.get().strip()
        try:
            value = max(0.0, float(typed))
        except ValueError:
            value = 0.0
        state.video_editor_trim_start = str(value)
        self.trim_start_var.set(str(value))
        state.save_config()

    def _on_trim_duration_changed(self, event=None):
        typed = self.trim_duration_var.get().strip()
        if not typed:
            state.video_editor_trim_duration = ""
            self.trim_duration_var.set("")
            state.save_config()
            return
        try:
            value = max(0.0, float(typed))
            state.video_editor_trim_duration = str(value)
            self.trim_duration_var.set(str(value))
        except ValueError:
            state.video_editor_trim_duration = ""
            self.trim_duration_var.set("")
        state.save_config()

    def _on_trim_silence_toggled(self):
        state.video_editor_trim_silence = self.trim_silence_var.get()
        state.save_config()

    def _on_target_seconds_changed(self, event=None):
        typed = self.target_seconds_var.get().strip()
        try:
            value = max(0, int(typed))
        except ValueError:
            value = 0
        state.video_editor_target_seconds = str(value)
        self.target_seconds_var.set(str(value))
        state.save_config()

    def _on_keep_audio_toggled(self):
        state.video_editor_keep_audio = self.keep_audio_var.get()
        state.save_config()

    def _on_loudnorm_toggled(self):
        state.video_editor_loudnorm = self.loudnorm_var.get()
        state.save_config()

    def _on_thumbnail_toggled(self):
        state.video_editor_thumbnail = self.thumbnail_var.get()
        state.save_config()

    def _on_captions_toggled(self):
        state.video_editor_captions = self.captions_var.get()
        state.save_config()

    def _on_captions_translate_toggled(self):
        state.video_editor_captions_translate = self.captions_translate_var.get()
        state.save_config()

    def _on_loudnorm_target_changed(self, event=None):
        typed = self.loudnorm_target_var.get().strip()
        if not typed:
            state.video_editor_loudnorm_target = ""
            self.loudnorm_target_var.set("")
            state.save_config()
            return
        try:
            value = float(typed)
            state.video_editor_loudnorm_target = str(value)
            self.loudnorm_target_var.set(str(value))
        except ValueError:
            state.video_editor_loudnorm_target = ""
            self.loudnorm_target_var.set("")
        state.save_config()

    def _on_denoise_toggled(self):
        state.video_editor_denoise = self.denoise_var.get()
        state.save_config()

    def _on_sharpen_toggled(self):
        state.video_editor_sharpen = self.sharpen_var.get()
        state.save_config()

    def _on_fps_changed(self, event=None):
        typed = self.fps_var.get().strip()
        if typed:
            try:
                parse_fps_value(typed)
            except ValueError:
                typed = ""  # קלט לא תקין - חוזר ל"שמירת קצב מקורי" (ריק), לא ערך שגוי שיישלח ל-CLI
        state.video_editor_fps = typed
        self.fps_var.set(typed)
        state.save_config()

    def _on_lut_path_changed(self, event=None):
        state.video_editor_lut_path = self.lut_path_var.get().strip()
        self.lut_path_var.set(state.video_editor_lut_path)
        state.save_config()

    def _on_auto_levels_toggled(self):
        state.video_editor_auto_levels = self.auto_levels_var.get()
        state.save_config()

    def _on_noise_gate_toggled(self):
        state.video_editor_noise_gate = self.noise_gate_var.get()
        state.save_config()

    def _on_remove_mid_silence_toggled(self):
        state.video_editor_remove_mid_silence = self.remove_mid_silence_var.get()
        state.save_config()

    def _on_stabilize_toggled(self):
        state.video_editor_stabilize = self.stabilize_var.get()
        state.save_config()

    def _on_chromakey_toggled(self):
        state.video_editor_chromakey = self.chromakey_var.get()
        state.save_config()

    def _on_chromakey_color_changed(self, event=None):
        typed = self.chromakey_color_var.get().strip()
        state.video_editor_chromakey_color = typed or "0x00FF00"
        self.chromakey_color_var.set(state.video_editor_chromakey_color)
        state.save_config()

    def _on_chromakey_bg_color_changed(self, event=None):
        typed = self.chromakey_bg_color_var.get().strip()
        state.video_editor_chromakey_bg_color = typed or "0x000000"
        self.chromakey_bg_color_var.set(state.video_editor_chromakey_bg_color)
        state.save_config()

    def _on_caption_font_changed(self, event=None):
        typed = self.caption_font_var.get().strip()
        state.video_editor_caption_font = typed or "Arial"
        self.caption_font_var.set(state.video_editor_caption_font)
        state.save_config()

    def _on_caption_font_size_changed(self, event=None):
        typed = self.caption_font_size_var.get().strip()
        try:
            value = max(1, int(typed))
        except ValueError:
            value = 16
        state.video_editor_caption_font_size = str(value)
        self.caption_font_size_var.set(str(value))
        state.save_config()

    def _on_caption_color_changed(self, event=None):
        typed = self.caption_color_var.get().strip()
        state.video_editor_caption_color = typed or "#FFFFFF"
        self.caption_color_var.set(state.video_editor_caption_color)
        state.save_config()

    def _on_caption_position_selected(self, display_value):
        state.video_editor_caption_position = self._caption_position_display_to_value.get(display_value, "bottom")
        state.save_config()
        self.caption_position_menu.set(display_value)
        self._sync_favorite_mirror("caption_position", display_value)

    def _on_codec_selected(self, display_value):
        state.video_editor_codec = self._codec_display_to_value.get(display_value, "h264")
        state.save_config()
        self.codec_menu.set(display_value)
        self._sync_favorite_mirror("codec", display_value)

    def _on_preserve_resolution_toggled(self):
        state.video_editor_preserve_resolution = self.preserve_resolution_var.get()
        state.save_config()

    def _on_no_suffix_toggled(self):
        state.video_editor_no_suffix = self.no_suffix_var.get()
        state.save_config()

    def _on_number_videos_toggled(self):
        state.video_editor_number_videos = self.number_videos_var.get()
        state.save_config()

    def _on_number_prefix_changed(self, event=None):
        typed = self.number_prefix_var.get().strip() or "Clip"
        state.video_editor_number_prefix = typed
        self.number_prefix_var.set(typed)
        state.save_config()

    def _on_number_start_changed(self, event=None):
        previous = state.video_editor_number_start
        typed = self.number_start_var.get().strip()
        if typed:
            try:
                typed = str(max(1, int(typed)))
            except ValueError:
                typed = ""
        state.video_editor_number_start = typed
        self.number_start_var.set(typed)
        state.save_config()
        # item: מספור סרטונים - עדכון בפועל של השדה (לא רק פוקוס-יציאה בלי
        # שינוי, שגם הוא מפעיל את ה-handler הזה) הוא "שינוי ידני" מפורש -
        # מאפס את המונה על הדיסק *עכשיו*, לא רק שולח --number-start לריצה
        # הבאה (שם זה מתעלם כליל אם קובץ המונה כבר קיים, ראו
        # utils/video/video_editor_counter.py). ה-previous != typed מונע איפוס
        # בטעות בכל פוקוס-יציאה שלא שינה בפועל שום דבר.
        if typed and typed != previous:
            save_video_editor_counter(int(typed))

    def _on_parallel_changed(self, event=None):
        typed = self.parallel_var.get().strip()
        try:
            value = max(1, int(typed))
        except ValueError:
            value = 1
        state.video_editor_parallel = str(value)
        self.parallel_var.set(str(value))
        state.save_config()

    def _on_max_concurrent_nvenc_changed(self, event=None):
        typed = self.max_concurrent_nvenc_var.get().strip()
        if typed:
            try:
                typed = str(max(1, int(typed)))
            except ValueError:
                typed = ""
        state.video_editor_max_concurrent_nvenc = typed
        self.max_concurrent_nvenc_var.set(typed)
        state.save_config()

    def _on_effort_selected(self, display_value):
        state.video_editor_effort = self._effort_display_to_value.get(display_value, "high")
        state.save_config()
        self.effort_menu.set(display_value)
        self._sync_favorite_mirror("effort", display_value)

    def _on_container_selected(self, display_value):
        state.video_editor_container = self._container_display_to_value.get(display_value, "mp4")
        state.save_config()
        self.container_menu.set(display_value)
        self._sync_favorite_mirror("container", display_value)

    def _on_output_template_changed(self, event=None):
        state.video_editor_output_template = self.output_template_var.get().strip()
        state.save_config()

    def _on_validate_only_toggled(self):
        state.video_editor_validate_only = self.validate_only_var.get()
        state.save_config()

    def _on_notify_per_file_toggled(self):
        state.video_editor_notify_per_file = self.notify_per_file_var.get()
        state.save_config()

    def _on_export_report_selected(self, display_value):
        state.video_editor_export_report = self._export_report_display_to_value.get(display_value, "")
        state.save_config()
        self.export_report_menu.set(display_value)
        self._sync_favorite_mirror("export_report", display_value)

    def _on_timelapse_target_seconds_changed(self, event=None):
        typed = self.timelapse_target_seconds_var.get().strip()
        try:
            value = max(1, int(typed))
        except ValueError:
            value = 60
        state.timelapse_target_seconds = str(value)
        self.timelapse_target_seconds_var.set(str(value))
        state.save_config()

    def _on_timelapse_keep_audio_toggled(self):
        state.timelapse_keep_audio = self.timelapse_keep_audio_var.get()
        state.save_config()

    def _on_video_editor_preset_selected(self, display_name):
        # item: אישור לפני מעבר עם שינויים לא-שמורים - נבדק לפני שמשנים משהו
        # בפועל; אם המשתמש מבטל, מחזירים את התפריט לבחירה הקודמת (הפרופיל
        # שעדיין בפועל טעון) במקום להשאיר אותו על בחירה שלא באמת קרתה.
        previous_display = self._preset_menu_previous_display
        self._preset_menu_previous_display = display_name
        if not self._confirm_discard_unsaved_if_needed():
            self.preset_menu.set(previous_display)
            self._preset_menu_previous_display = previous_display
            return

        # פרופיל אישי (item: פרופיל משלי) - נבדק לפני ה-presets הקבועים, כי
        # שני המקורות חולקים את אותו preset_menu (ראו _refresh_video_editor_profile_menu).
        profile_name = self._profile_display_to_name.get(display_name)
        if profile_name is not None:
            self.update_profile_btn.pack(side="right", padx=(0, 5))
            self.rename_profile_btn.pack(side="right", padx=(0, 5))
            self.delete_profile_btn.pack(side="right", padx=(0, 5))
            profile = load_profiles().get(profile_name)
            if profile:
                self._apply_video_editor_profile_fields(profile)
            self._capture_profile_baseline()
            return
        self.update_profile_btn.pack_forget()
        self.rename_profile_btn.pack_forget()
        self.delete_profile_btn.pack_forget()
        self._profile_baseline_snapshot = None
        self._update_unsaved_indicator()

        preset = VIDEO_EDITOR_PRESETS.get(display_name)
        if not preset:
            return  # "בחר פרופיל..." הפלייסהולדר עצמו, לא preset/פרופיל אמיתי

        state.video_editor_vertical = preset["vertical"]
        state.video_editor_target_seconds = str(preset["target_seconds"])
        state.video_editor_keep_audio = preset["keep_audio"]
        state.video_editor_loudnorm = preset["loudnorm"]
        state.video_editor_codec = preset["codec"]
        state.save_config()

        self.vertical_var.set(preset["vertical"])
        self.target_seconds_var.set(str(preset["target_seconds"]))
        self.keep_audio_var.set(preset["keep_audio"])
        self.loudnorm_var.set(preset["loudnorm"])
        codec_display = self._codec_value_to_display.get(preset["codec"])
        if codec_display:
            self.codec_menu.set(codec_display)

    def _favorite_field_registry(self):
        """מיפוי field_key (תת-קבוצה של PROFILE_FIELDS - שדות שיש להם שווה-ערך
        עורך אחד וברור, לא watermark_path/x/y או "folder" שיש להם UI מיוחד
        משלהם) -> (label, kind, extra) לבניית ה-widget ה'משתף' בתיבת המועדפים
        (item: תיבת העדפות לכל פרופיל). kind="entry"/"switch": extra הוא שם
        attribute של Var קיים - Entry/Switch חדש שמצביע על אותו Var מסתנכרן
        אוטומטית עם המקור (Tkinter, לא קוד שלנו). kind="option": extra הוא
        (display_to_value_attr, value_to_display_attr, handler_method_name,
        state_attr, menu_widget_attr) - CTkOptionMenu לא נתמך ע"י Variable
        binding, אז השני-הכיוונים מתבצע ידנית (ראו _sync_favorite_mirror
        וההנדלרים המתאימים, שכולם גם מעדכנים את ה-menu המקורי בפועל)."""
        # item: מונח קצר במקום רצף-מילים - התוויות כאן נשלפות מ-FIELD_HELP
        # (אותו מקור בדיוק כמו הטולטיפים/המקראה), לא משוכפלות כאן שוב עם
        # ניסוח אחר - כך שהמונח של שדה זהה תמיד, בין אם רואים אותו בקטגוריה
        # המקורית שלו או בתיבת ה"⭐ מועדפים"/דיאלוג-הבחירה.
        def entry(field_key, var_attr):
            return (t(FIELD_HELP[field_key].term), "entry", var_attr)

        def switch(field_key, var_attr):
            return (t(FIELD_HELP[field_key].term), "switch", var_attr)

        def option(field_key, d2v_attr, v2d_attr, handler_name, state_attr, menu_attr):
            return (t(FIELD_HELP[field_key].term), "option", (d2v_attr, v2d_attr, handler_name, state_attr, menu_attr))

        return {
            "watermark_opacity": entry("watermark_opacity", "watermark_opacity_var"),
            "watermark_scale": entry("watermark_scale", "watermark_scale_var"),
            "watermark_position": option("watermark_position", "_wm_position_display_to_value", "_wm_position_value_to_display", "_on_watermark_position_selected", "video_editor_watermark_position", "wm_position_menu"),
            "remove_watermark_position": option("remove_watermark_position", "_remove_wm_position_display_to_value", "_remove_wm_position_value_to_display", "_on_remove_watermark_position_selected", "video_editor_remove_watermark_position", "remove_wm_position_menu"),
            "vertical": switch("vertical", "vertical_var"),
            "smart_crop": switch("smart_crop", "smart_crop_var"),
            "blur_background": switch("blur_background", "blur_background_var"),
            "trim_start": entry("trim_start", "trim_start_var"),
            "trim_duration": entry("trim_duration", "trim_duration_var"),
            "trim_silence": switch("trim_silence", "trim_silence_var"),
            "target_seconds": entry("target_seconds", "target_seconds_var"),
            "keep_audio": switch("keep_audio", "keep_audio_var"),
            "captions": switch("captions", "captions_var"),
            "captions_translate": switch("captions_translate", "captions_translate_var"),
            "loudnorm": switch("loudnorm", "loudnorm_var"),
            "loudnorm_target": entry("loudnorm_target", "loudnorm_target_var"),
            "denoise": switch("denoise", "denoise_var"),
            "sharpen": switch("sharpen", "sharpen_var"),
            "thumbnail": switch("thumbnail", "thumbnail_var"),
            "codec": option("codec", "_codec_display_to_value", "_codec_value_to_display", "_on_codec_selected", "video_editor_codec", "codec_menu"),
            "fps": entry("fps", "fps_var"),
            "lut_path": entry("lut_path", "lut_path_var"),
            "auto_levels": switch("auto_levels", "auto_levels_var"),
            "noise_gate": switch("noise_gate", "noise_gate_var"),
            "remove_mid_silence": switch("remove_mid_silence", "remove_mid_silence_var"),
            "stabilize": switch("stabilize", "stabilize_var"),
            "chromakey": switch("chromakey", "chromakey_var"),
            "chromakey_color": entry("chromakey_color", "chromakey_color_var"),
            "chromakey_bg_color": entry("chromakey_bg_color", "chromakey_bg_color_var"),
            "caption_font": entry("caption_font", "caption_font_var"),
            "caption_font_size": entry("caption_font_size", "caption_font_size_var"),
            "caption_color": entry("caption_color", "caption_color_var"),
            "caption_position": option("caption_position", "_caption_position_display_to_value", "_caption_position_value_to_display", "_on_caption_position_selected", "video_editor_caption_position", "caption_position_menu"),
            "preserve_resolution": switch("preserve_resolution", "preserve_resolution_var"),
            "no_suffix": switch("no_suffix", "no_suffix_var"),
            "parallel": entry("parallel", "parallel_var"),
            "max_concurrent_nvenc": entry("max_concurrent_nvenc", "max_concurrent_nvenc_var"),
            "effort": option("effort", "_effort_display_to_value", "_effort_value_to_display", "_on_effort_selected", "video_editor_effort", "effort_menu"),
            "container": option("container", "_container_display_to_value", "_container_value_to_display", "_on_container_selected", "video_editor_container", "container_menu"),
            "output_template": entry("output_template", "output_template_var"),
            "validate_only": switch("validate_only", "validate_only_var"),
            "notify_per_file": switch("notify_per_file", "notify_per_file_var"),
            "export_report": option("export_report", "_export_report_display_to_value", "_export_report_value_to_display", "_on_export_report_selected", "video_editor_export_report", "export_report_menu"),
            "number_videos": switch("number_videos", "number_videos_var"),
            "number_prefix": entry("number_prefix", "number_prefix_var"),
            "number_start": entry("number_start", "number_start_var"),
        }

    def _sync_favorite_mirror(self, field_key, display_value):
        """מעדכן את ה-widget ב'מועדפים' עבור field_key (אם קיים כרגע) לאחר
        שההנדלר האמיתי של השדה (option-menu) עודכן - ראו _favorite_field_registry.
        no-op בשקט אם השדה הזה לא מועדף כרגע (אין mirror) - זה המקרה הנפוץ."""
        mirror = self._favorite_mirrors.get(field_key)
        if mirror is not None:
            mirror.set(display_value)

    def _rebuild_favorites_box(self):
        """בונה מחדש את כל התוכן של קטגוריית "⭐ מועדפים" לפי
        state.video_editor_favorite_fields הנוכחי (CSV של field_key-ים) -
        נקרא אחרי טעינת פרופיל ואחרי סגירת דיאלוג הבחירה (_open_favorites_dialog).
        פשוט הורס ובונה מחדש (לא מנסה לעדכן חלקית) - הכמות קטנה (כמה עשרות
        widgets לכל היותר) כך שאין עלות ביצועים אמיתית, והרבה יותר קל לוודא
        נכונות מאשר עדכון-הדרגתי."""
        for widget in self.cat_favorites.winfo_children():
            widget.destroy()
        self._favorite_mirrors = {}

        field_keys = [f.strip() for f in state.video_editor_favorite_fields.split(",") if f.strip()]
        if not field_keys:
            ctk.CTkLabel(
                self.cat_favorites,
                text=t('אין מועדפים עדיין - לחץ "⭐ הגדר מועדפים..." בקטגוריית "פרופילים" כדי לבחור.'),
                text_color=PALETTE["text_muted"], anchor="e", justify="right", wraplength=280,
            ).pack(fill="x", pady=4)
            return

        registry = self._favorite_field_registry()
        for index, field_key in enumerate(field_keys):
            field_def = registry.get(field_key)
            if field_def is None:
                continue  # שדה שהוסר/שונה שם מאז שנשמר כמועדף - מדולג בשקט, לא שגיאה
            label, kind, extra = field_def
            row = ctk.CTkFrame(self.cat_favorites, fg_color="transparent")
            row.pack(fill="x", pady=4)
            # item: סידור-ידני של רשימת המועדפים - ▲/▼ במקום גרירה אמיתית
            # (Tkinter לא תומך בגרירת-widgets בין שורות מובנה) - מזיזים את
            # field_key צעד אחד ב-CSV הנשמר ובונים מחדש.
            reorder_box = ctk.CTkFrame(row, fg_color="transparent")
            reorder_box.pack(side="left", padx=(0, 5))
            btn_up = ctk.CTkButton(reorder_box, text="▲", width=22, height=20, font=("Segoe UI", 9), command=lambda k=field_key: self._move_favorite(k, -1))
            btn_up.pack(side="top")
            if index == 0:
                btn_up.configure(state="disabled")
            btn_down = ctk.CTkButton(reorder_box, text="▼", width=22, height=20, font=("Segoe UI", 9), command=lambda k=field_key: self._move_favorite(k, 1))
            btn_down.pack(side="top")
            if index == len(field_keys) - 1:
                btn_down.configure(state="disabled")
            if kind == "switch":
                switch = ctk.CTkSwitch(
                    row, text=label, variable=getattr(self, extra), onvalue=True, offvalue=False,
                )
                switch.pack(side="right", padx=5)
                self._attach_tooltip(switch, field_key)
            elif kind == "entry":
                self._field_label(row, field_key).pack(side="right", padx=(5, 0))
                ctk.CTkEntry(row, textvariable=getattr(self, extra), width=120).pack(side="right", padx=5)
            elif kind == "option":
                d2v_attr, v2d_attr, handler_name, state_attr, _menu_attr = extra
                self._field_label(row, field_key).pack(side="right", padx=(5, 0))
                display_to_value = getattr(self, d2v_attr)
                value_to_display = getattr(self, v2d_attr)
                mirror = ctk.CTkOptionMenu(row, values=list(display_to_value.keys()), command=getattr(self, handler_name), width=130)
                mirror.pack(side="right", padx=5)
                current_display = value_to_display.get(getattr(state, state_attr))
                if current_display:
                    mirror.set(current_display)
                self._favorite_mirrors[field_key] = mirror

    def _move_favorite(self, field_key, direction):
        field_keys = [f.strip() for f in state.video_editor_favorite_fields.split(",") if f.strip()]
        if field_key not in field_keys:
            return
        i = field_keys.index(field_key)
        j = i + direction
        if not (0 <= j < len(field_keys)):
            return
        field_keys[i], field_keys[j] = field_keys[j], field_keys[i]
        state.video_editor_favorite_fields = ",".join(field_keys)
        state.save_config()
        self._rebuild_favorites_box()

    def _open_favorites_dialog(self):
        """דיאלוג צ'קליסט (item: תיבת העדפות לכל פרופיל) - כל השדות מ-
        _favorite_field_registry, קבוצה לפי סדר-ההופעה ברשימה (לא מקובצים
        לפי קטגוריה במכוון - זו רשימה שטוחה קטנה מדי כדי להצדיק עוד שכבת
        UI). שינויים נכנסים לתוקף רק בסגירה (❌/"סגור"), לא per-checkbox -
        כדי שסגירה-בטעות-לפני-סיום לא תשמור מצב-ביניים מקרי."""
        registry = self._favorite_field_registry()
        current = {f.strip() for f in state.video_editor_favorite_fields.split(",") if f.strip()}

        dialog = ctk.CTkToplevel(self)
        dialog.title(t("⭐ הגדר מועדפים"))
        dialog.geometry("380x520")
        dialog.transient(self.winfo_toplevel())

        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        check_vars = {}
        for field_key, (label, _kind, _extra) in registry.items():
            var = ctk.BooleanVar(value=field_key in current)
            check_vars[field_key] = var
            ctk.CTkCheckBox(scroll, text=label, variable=var, onvalue=True, offvalue=False).pack(anchor="e", pady=2, padx=5, fill="x")

        def _apply_and_close():
            selected = [key for key, var in check_vars.items() if var.get()]
            state.video_editor_favorite_fields = ",".join(selected)
            state.save_config()
            self._rebuild_favorites_box()
            dialog.destroy()

        ctk.CTkButton(dialog, text=t("✅ סגור ושמור"), command=_apply_and_close).pack(pady=(0, 10))

    def _refresh_video_editor_profile_menu(self):
        """טוען פרופילים אישיים מהדיסק (utils/video/video_editor_profiles.py) ובונה
        מחדש את רשימת preset_menu - נקרא באתחול וגם אחרי כל שמירה/מחיקה, וגם
        בכל כניסה לפאנל (update_script_context), כדי שהתפריט תמיד ישקף את מה
        שקיים בפועל (כולל פרופיל שנשמר מהווב, בלי הפעלה מחדש)."""
        profiles = load_profiles()
        self._profile_display_to_name = {
            f"{self._custom_profile_display_prefix}{name}": name for name in profiles
        }
        values = [self._preset_placeholder, *VIDEO_EDITOR_PRESETS.keys(), *self._profile_display_to_name.keys()]
        self.preset_menu.configure(values=values)

    def _collect_video_editor_profile_settings(self):
        """snapshot מלא לשמירה כפרופיל - PROFILE_FIELDS מלבד "folder" (item:
        תיקיית קלט בפרופיל) נאספים גנרית מ-state.video_editor_<field>;
        "folder" חורג מהמוסכמה הזו (state.selected_gameplay_folder, בלי
        prefix - זו תיקיית הקלט המשותפת לכל הסקריפטים, לא הגדרה ספציפית
        לעורך-העל) ונאסף בנפרד.

        getattr עם ברירת-מחדל None (לא גישה ישירה) - מעכשיו הדסקטופ קפוא
        ושדות PROFILE_FIELDS חדשים (ראו utils/video/video_editor_profiles.py)
        נוספים web-בלבד, בלי state.video_editor_<field> תואם ובלי widget
        בכלל כאן - גישה ישירה הייתה מפילה כל טעינת/שמירת פרופיל בדסקטופ
        עם AttributeError ברגע שהשדה הראשון כזה נוסף. שדה שהדסקטופ לא מכיר
        פשוט נשמר כ-None (יתפרש כברירת המחדל שלו כשהפרופיל ייטען בווב)."""
        settings = {field: getattr(state, f"video_editor_{field}", None) for field in PROFILE_FIELDS if field != "folder"}
        settings["folder"] = state.selected_gameplay_folder
        return settings

    def _save_video_editor_profile(self):
        name = self.profile_name_var.get().strip()
        if not name:
            return
        save_profile(name, self._collect_video_editor_profile_settings())
        self.profile_name_var.set("")
        self._refresh_video_editor_profile_menu()
        self.preset_menu.set(f"{self._custom_profile_display_prefix}{name}")
        self._preset_menu_previous_display = f"{self._custom_profile_display_prefix}{name}"
        self.update_profile_btn.pack(side="right", padx=(0, 5))
        self.rename_profile_btn.pack(side="right", padx=(0, 5))
        self.delete_profile_btn.pack(side="right", padx=(0, 5))
        self._capture_profile_baseline()
        # item: הודעת אישור שמירת/עדכון פרופיל - בלי זה, לחיצה על "שמור פרופיל"
        # לא נתנה שום משוב גלוי (רק הופעת התפריט/כפתורים, קל לפספס), אז לא היה
        # ברור אם השמירה באמת הצליחה.
        messagebox.showinfo(t("פרופיל נשמר"), t(f'הפרופיל "{name}" נשמר בהצלחה.'))

    def _update_video_editor_profile(self):
        """item: אפשרות לעדכן פרופיל קיים - שומר מחדש (דורס) את הפרופיל האישי
        שנבחר כרגע ב-preset_menu עם ההגדרות הנוכחיות של הטופס, בלי לדרוש
        הקלדת השם שוב. no-op בשקט אם לא נבחר כרגע פרופיל אישי אמיתי (preset
        קבוע/הפלייסהולדר) - אין שם לעדכן."""
        name = self._profile_display_to_name.get(self.preset_menu.get())
        if not name:
            return
        save_profile(name, self._collect_video_editor_profile_settings())
        self._capture_profile_baseline()
        messagebox.showinfo(t("פרופיל עודכן"), t(f'הפרופיל "{name}" עודכן בהצלחה.'))

    def _rename_video_editor_profile(self):
        """item: שינוי שם לפרופיל - ctk.CTkInputDialog (מובנה ב-customtkinter,
        לא PassphraseDialog המסויג - זה לא סיסמה, אין צורך במיסוך) בלי ערך
        התחלתי (המובנה לא תומך בזה) - המשתמש מקליד את השם החדש מהתחלה.
        no-op אם לא נבחר פרופיל אישי, בוטל, או הוקלד ריק/זהה לשם הקיים."""
        old_name = self._profile_display_to_name.get(self.preset_menu.get())
        if not old_name:
            return
        dialog = ctk.CTkInputDialog(text=t(f"שם חדש לפרופיל \"{old_name}\":"), title=t("שינוי שם פרופיל"))
        new_name = dialog.get_input()
        if not new_name or not new_name.strip() or new_name.strip() == old_name:
            return
        try:
            rename_profile(old_name, new_name.strip())
        except ValueError as e:
            # item: בדיקת באגים מקיפה - print() בלבד היה בלתי-נראה למשתמש GUI
            # רגיל (אין לו טרמינל פתוח); הדיאלוג הזה גלוי בפועל, כמו שגיאות
            # אחרות בטאב ההגדרות (ראו global_settings_tab.py).
            messagebox.showerror(t("שגיאה"), str(e))
            return
        self._refresh_video_editor_profile_menu()
        self.preset_menu.set(f"{self._custom_profile_display_prefix}{new_name.strip()}")

    def _delete_video_editor_profile(self):
        name = self._profile_display_to_name.get(self.preset_menu.get())
        if not name:
            return  # שום פרופיל אישי נבחר כרגע - לא preset מובנה/פלייסהולדר
        delete_profile(name)
        self._refresh_video_editor_profile_menu()
        self.preset_menu.set(self._preset_placeholder)
        self._preset_menu_previous_display = self._preset_placeholder
        self._profile_baseline_snapshot = None
        self._update_unsaved_indicator()
        self.update_profile_btn.pack_forget()
        self.rename_profile_btn.pack_forget()
        self.delete_profile_btn.pack_forget()

    def _apply_video_editor_profile_fields(self, profile):
        """מחיל snapshot מלא של פרופיל אישי (item: פרופיל משלי) - כולל נתיבים/
        סליידרים, לא רק "סוג עריכה" כללי כמו VIDEO_EDITOR_PRESETS הקבועים
        (_on_video_editor_preset_selected למעלה). שדה חסר/None נופל לברירת
        המחדל הרגילה של השדה עצמו."""
        def _str(value, default=""):
            return default if value is None else str(value)

        state.video_editor_watermark_path = profile.get("watermark_path") or ""
        state.video_editor_watermark_position = profile.get("watermark_position") or "bottom-right"
        state.video_editor_watermark_opacity = _str(profile.get("watermark_opacity"), "1.0")
        state.video_editor_watermark_scale = _str(profile.get("watermark_scale"), "0.15")
        state.video_editor_watermark_x = _str(profile.get("watermark_x"), "")
        state.video_editor_watermark_y = _str(profile.get("watermark_y"), "")
        state.video_editor_remove_watermark_position = profile.get("remove_watermark_position") or ""
        state.video_editor_vertical = bool(profile.get("vertical"))
        state.video_editor_smart_crop = bool(profile.get("smart_crop"))
        state.video_editor_blur_background = bool(profile.get("blur_background"))
        state.video_editor_trim_start = _str(profile.get("trim_start"), "0")
        state.video_editor_trim_duration = _str(profile.get("trim_duration"), "")
        state.video_editor_trim_silence = bool(profile.get("trim_silence"))
        state.video_editor_target_seconds = _str(profile.get("target_seconds"), "0")
        state.video_editor_keep_audio = bool(profile.get("keep_audio"))
        state.video_editor_loudnorm = bool(profile.get("loudnorm"))
        state.video_editor_loudnorm_target = _str(profile.get("loudnorm_target"), "")
        state.video_editor_denoise = bool(profile.get("denoise"))
        state.video_editor_sharpen = bool(profile.get("sharpen"))
        state.video_editor_thumbnail = bool(profile.get("thumbnail"))
        state.video_editor_captions = bool(profile.get("captions"))
        state.video_editor_captions_translate = bool(profile.get("captions_translate"))
        state.video_editor_codec = profile.get("codec") or "h264"
        state.video_editor_fps = profile.get("fps") or ""
        state.video_editor_lut_path = profile.get("lut_path") or ""
        state.video_editor_auto_levels = bool(profile.get("auto_levels"))
        state.video_editor_noise_gate = bool(profile.get("noise_gate"))
        state.video_editor_remove_mid_silence = bool(profile.get("remove_mid_silence"))
        state.video_editor_stabilize = bool(profile.get("stabilize"))
        state.video_editor_chromakey = bool(profile.get("chromakey"))
        state.video_editor_chromakey_color = profile.get("chromakey_color") or "0x00FF00"
        state.video_editor_chromakey_bg_color = profile.get("chromakey_bg_color") or "0x000000"
        state.video_editor_caption_font = profile.get("caption_font") or "Arial"
        state.video_editor_caption_font_size = _str(profile.get("caption_font_size"), "16")
        state.video_editor_caption_color = profile.get("caption_color") or "#FFFFFF"
        state.video_editor_caption_position = profile.get("caption_position") or "bottom"
        state.video_editor_preserve_resolution = bool(profile.get("preserve_resolution"))
        state.video_editor_no_suffix = bool(profile.get("no_suffix"))
        state.video_editor_number_videos = bool(profile.get("number_videos"))
        state.video_editor_number_prefix = profile.get("number_prefix") or "Clip"
        state.video_editor_number_start = _str(profile.get("number_start"), "")
        state.video_editor_parallel = _str(profile.get("parallel"), "1")
        state.video_editor_max_concurrent_nvenc = _str(profile.get("max_concurrent_nvenc"), "")
        state.video_editor_effort = profile.get("effort") or "high"
        state.video_editor_container = profile.get("container") or "mp4"
        state.video_editor_output_template = profile.get("output_template") or ""
        state.video_editor_validate_only = bool(profile.get("validate_only"))
        state.video_editor_notify_per_file = bool(profile.get("notify_per_file"))
        state.video_editor_export_report = profile.get("export_report") or ""
        # item: תיבת העדפות לכל פרופיל - "" (ברירת מחדל) אם הפרופיל נשמר לפני
        # התכונה הזו - תיבת המועדפים נשארת ריקה, לא שגיאה.
        state.video_editor_favorite_fields = profile.get("favorite_fields") or ""
        # item: תיקיית קלט בפרופיל - רק אם הפרופיל בכלל שומר תיקייה (profile.get
        # לא None/ריק) - פרופילים ישנים משלב לפני התכונה הזו לא ידרסו בטעות
        # את התיקייה הנוכחית בריק כשנטענים.
        profile_folder = profile.get("folder")
        if profile_folder:
            state.selected_gameplay_folder = profile_folder
        state.save_config()

        self.watermark_path_var.set(state.video_editor_watermark_path)
        wm_position_display = self._wm_position_value_to_display.get(state.video_editor_watermark_position)
        if wm_position_display:
            self.wm_position_menu.set(wm_position_display)
        self.watermark_opacity_var.set(state.video_editor_watermark_opacity)
        self.watermark_opacity_slider_var.set(self._parse_opacity(state.video_editor_watermark_opacity))
        self.watermark_scale_var.set(self._scale_to_percent_str(state.video_editor_watermark_scale))
        self.watermark_scale_slider_var.set(self._parse_scale_percent(self._scale_to_percent_str(state.video_editor_watermark_scale)))
        remove_wm_display = self._remove_wm_position_value_to_display.get(state.video_editor_remove_watermark_position, self._remove_wm_placeholder)
        self.remove_wm_position_menu.set(remove_wm_display)
        self.vertical_var.set(state.video_editor_vertical)
        self.smart_crop_var.set(state.video_editor_smart_crop)
        self.blur_background_var.set(state.video_editor_blur_background)
        self.trim_start_var.set(state.video_editor_trim_start)
        self.trim_duration_var.set(state.video_editor_trim_duration)
        self.trim_silence_var.set(state.video_editor_trim_silence)
        self.target_seconds_var.set(state.video_editor_target_seconds)
        self.keep_audio_var.set(state.video_editor_keep_audio)
        self.loudnorm_var.set(state.video_editor_loudnorm)
        self.loudnorm_target_var.set(state.video_editor_loudnorm_target)
        self.denoise_var.set(state.video_editor_denoise)
        self.sharpen_var.set(state.video_editor_sharpen)
        self.thumbnail_var.set(state.video_editor_thumbnail)
        self.captions_var.set(state.video_editor_captions)
        self.captions_translate_var.set(state.video_editor_captions_translate)
        codec_display = self._codec_value_to_display.get(state.video_editor_codec)
        if codec_display:
            self.codec_menu.set(codec_display)
        self.fps_var.set(state.video_editor_fps)
        self.lut_path_var.set(state.video_editor_lut_path)
        self.auto_levels_var.set(state.video_editor_auto_levels)
        self.noise_gate_var.set(state.video_editor_noise_gate)
        self.remove_mid_silence_var.set(state.video_editor_remove_mid_silence)
        self.stabilize_var.set(state.video_editor_stabilize)
        self.chromakey_var.set(state.video_editor_chromakey)
        self.chromakey_color_var.set(state.video_editor_chromakey_color)
        self.chromakey_bg_color_var.set(state.video_editor_chromakey_bg_color)
        self.caption_font_var.set(state.video_editor_caption_font)
        self.caption_font_size_var.set(state.video_editor_caption_font_size)
        self.caption_color_var.set(state.video_editor_caption_color)
        caption_position_display = self._caption_position_value_to_display.get(state.video_editor_caption_position)
        if caption_position_display:
            self.caption_position_menu.set(caption_position_display)
        self.preserve_resolution_var.set(state.video_editor_preserve_resolution)
        self.no_suffix_var.set(state.video_editor_no_suffix)
        self.number_videos_var.set(state.video_editor_number_videos)
        self.number_prefix_var.set(state.video_editor_number_prefix)
        self.number_start_var.set(state.video_editor_number_start)
        self.parallel_var.set(state.video_editor_parallel)
        self.max_concurrent_nvenc_var.set(state.video_editor_max_concurrent_nvenc)
        effort_display = self._effort_value_to_display.get(state.video_editor_effort)
        if effort_display:
            self.effort_menu.set(effort_display)
        container_display = self._container_value_to_display.get(state.video_editor_container)
        if container_display:
            self.container_menu.set(container_display)
        self.output_template_var.set(state.video_editor_output_template)
        self.validate_only_var.set(state.video_editor_validate_only)
        self.notify_per_file_var.set(state.video_editor_notify_per_file)
        export_report_display = self._export_report_value_to_display.get(state.video_editor_export_report)
        if export_report_display:
            self.export_report_menu.set(export_report_display)
        self.folder_path_var.set(state.selected_gameplay_folder)
        self._update_watermark_preview()
        self._rebuild_favorites_box()

    def _set_folder(self, folder):
        state.selected_gameplay_folder = folder
        self.folder_path_var.set(folder)
        state.save_config()

    def _on_folder_entry_changed(self, event=None):
        typed = self.folder_path_var.get().strip()
        if typed and os.path.isdir(typed):
            self._set_folder(os.path.normpath(typed))
        elif typed and os.path.isfile(typed):
            self._set_folder(os.path.normpath(os.path.dirname(typed)))
        # נתיב שאינו תיקייה/קובץ קיים - לא שומרים כדי לא לדרוס הגדרה תקינה
        # בטעות הקלדה, אבל גם לא מוחקים את מה שהמשתמש הקליד (אולי עדיין מקליד).

    def choose_gameplay_folder(self):
        current = self.folder_path_var.get()
        initial = current if os.path.isdir(current) else None
        f = filedialog.askdirectory(initialdir=initial) if initial else filedialog.askdirectory()
        if f:
            self._set_folder(os.path.normpath(f))

    def on_folder_dropped(self, event):
        """מטפל בגרירת תיקייה או קובץ (כולל קובץ וידאו ספציפי - נלקחת אז תיקיית
        האב שלו, כי כל הסקריפטים סורקים תיקייה שלמה עם --input_dir, לא קובץ בודד)."""
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = raw.split("} {")[0] if "} {" in raw else raw

        if os.path.isdir(path):
            target_dir = path
        elif os.path.isfile(path):
            target_dir = os.path.dirname(path)
        else:
            return

        self._set_folder(os.path.normpath(target_dir))

    def update_script_context(self, script_name, description="", filename=""):
        # item: איפוס עורך-העל לברירת מחדל - נשמר כדי ש-_reset_video_editor_to_defaults
        # יוכל לקרוא שוב ל-update_script_context (מרענן את כל ה-widgets מ-state
        # מחדש, אותה לוגיקה בדיוק כמו כניסה טרייה לפאנל) בלי לדרוש מהקורא
        # להעביר שוב script_name/description/filename.
        self._last_script_context = (script_name, description, filename)
        if not filename and state.selected_script:
            filename = os.path.basename(state.selected_script)
        self.lbl_title.configure(text=t("⚙️ הגדרות עבור {name} ({filename})", name=script_name, filename=filename))
        # fix_hebrew_word_order כאן כי התיאור מוצג לבד (לא כחלק ממחרוזת t()
        # גדולה יותר) - ראו utils/shared/script_metadata.py למה זה כבר לא קורה שם.
        self.description_label.configure(text=fix_hebrew_word_order(description) if description else t("אין תיאור זמין לסקריפט זה."))
        self.folder_path_var.set(state.selected_gameplay_folder)

        # רק story_cutter.py מכיר את --ai-provider (ראו worker.add_script_task) -
        # לכל סקריפט אחר הפאנל הזה פשוט לא מוצג בכלל.
        is_story_cutter = bool(state.selected_script) and os.path.basename(state.selected_script) == "story_cutter.py"
        if is_story_cutter:
            current_display = self._ai_provider_value_to_display.get(state.story_cutter_ai_provider)
            if current_display:
                self.ai_provider_menu.set(current_display)
            self.ai_provider_frame.pack(pady=(0, 10), padx=15, fill="x")
        else:
            self.ai_provider_frame.pack_forget()

        # רק video_editor.py מכיר את הדגלים האלה (ראו ui/dashboard.py) - לכל
        # סקריפט אחר הפאנל הזה לא מוצג בכלל, אותו דפוס בדיוק כמו is_story_cutter.
        is_video_editor = bool(state.selected_script) and os.path.basename(state.selected_script) == "video_editor.py"
        if is_video_editor:
            # מרענן את רשימת הפרופילים האישיים בכל כניסה לפאנל (item: פרופיל
            # משלי) - כך שפרופיל שנשמר מהווב (או מסבב הפעלה קודם) יופיע גם כאן,
            # בלי צורך בהפעלה מחדש של ה-GUI.
            self._refresh_video_editor_profile_menu()
            self.preset_menu.set(self._preset_placeholder)
            self.update_profile_btn.pack_forget()
            self.rename_profile_btn.pack_forget()
            self.delete_profile_btn.pack_forget()
            self.watermark_path_var.set(state.video_editor_watermark_path)
            wm_position_display = self._wm_position_value_to_display.get(state.video_editor_watermark_position)
            if wm_position_display:
                self.wm_position_menu.set(wm_position_display)
            remove_wm_display = self._remove_wm_position_value_to_display.get(state.video_editor_remove_watermark_position, self._remove_wm_placeholder)
            self.remove_wm_position_menu.set(remove_wm_display)
            self.watermark_opacity_var.set(state.video_editor_watermark_opacity)
            self.watermark_opacity_slider_var.set(self._parse_opacity(state.video_editor_watermark_opacity))
            self.watermark_scale_var.set(self._scale_to_percent_str(state.video_editor_watermark_scale))
            self.watermark_scale_slider_var.set(self._parse_scale_percent(self._scale_to_percent_str(state.video_editor_watermark_scale)))
            self.vertical_var.set(state.video_editor_vertical)
            self.smart_crop_var.set(state.video_editor_smart_crop)
            self.blur_background_var.set(state.video_editor_blur_background)
            self.trim_start_var.set(state.video_editor_trim_start)
            self.trim_duration_var.set(state.video_editor_trim_duration)
            self.trim_silence_var.set(state.video_editor_trim_silence)
            self.target_seconds_var.set(state.video_editor_target_seconds)
            self.keep_audio_var.set(state.video_editor_keep_audio)
            self.loudnorm_var.set(state.video_editor_loudnorm)
            self.thumbnail_var.set(state.video_editor_thumbnail)
            self.captions_var.set(state.video_editor_captions)
            self.captions_translate_var.set(state.video_editor_captions_translate)
            self.loudnorm_target_var.set(state.video_editor_loudnorm_target)
            self.denoise_var.set(state.video_editor_denoise)
            self.sharpen_var.set(state.video_editor_sharpen)
            codec_display = self._codec_value_to_display.get(state.video_editor_codec)
            if codec_display:
                self.codec_menu.set(codec_display)
            self.fps_var.set(state.video_editor_fps)
            self.lut_path_var.set(state.video_editor_lut_path)
            self.auto_levels_var.set(state.video_editor_auto_levels)
            self.noise_gate_var.set(state.video_editor_noise_gate)
            self.remove_mid_silence_var.set(state.video_editor_remove_mid_silence)
            self.stabilize_var.set(state.video_editor_stabilize)
            self.chromakey_var.set(state.video_editor_chromakey)
            self.chromakey_color_var.set(state.video_editor_chromakey_color)
            self.chromakey_bg_color_var.set(state.video_editor_chromakey_bg_color)
            self.caption_font_var.set(state.video_editor_caption_font)
            self.caption_font_size_var.set(state.video_editor_caption_font_size)
            self.caption_color_var.set(state.video_editor_caption_color)
            caption_position_display = self._caption_position_value_to_display.get(state.video_editor_caption_position)
            if caption_position_display:
                self.caption_position_menu.set(caption_position_display)
            self.preserve_resolution_var.set(state.video_editor_preserve_resolution)
            self.no_suffix_var.set(state.video_editor_no_suffix)
            self.number_videos_var.set(state.video_editor_number_videos)
            self.number_prefix_var.set(state.video_editor_number_prefix)
            self.number_start_var.set(state.video_editor_number_start)
            self.parallel_var.set(state.video_editor_parallel)
            self.max_concurrent_nvenc_var.set(state.video_editor_max_concurrent_nvenc)
            effort_display = self._effort_value_to_display.get(state.video_editor_effort)
            if effort_display:
                self.effort_menu.set(effort_display)
            container_display = self._container_value_to_display.get(state.video_editor_container)
            if container_display:
                self.container_menu.set(container_display)
            self.output_template_var.set(state.video_editor_output_template)
            self.validate_only_var.set(state.video_editor_validate_only)
            self.notify_per_file_var.set(state.video_editor_notify_per_file)
            export_report_display = self._export_report_value_to_display.get(state.video_editor_export_report)
            if export_report_display:
                self.export_report_menu.set(export_report_display)
            if not state.video_editor_onboarding_seen:
                self.video_editor_onboarding_banner.pack(pady=(0, 6), padx=15, fill="x")
            else:
                self.video_editor_onboarding_banner.pack_forget()
            self.video_editor_sticky_bar.pack(pady=(0, 4), padx=15, fill="x")
            self.video_editor_frame.pack(pady=(0, 10), padx=15, fill="x")
            self._update_watermark_preview()
            self._update_category_summaries()
        else:
            self.video_editor_onboarding_banner.pack_forget()
            self.video_editor_sticky_bar.pack_forget()
            self.video_editor_frame.pack_forget()

        # רק timelapse_maker.py מכיר את --target-seconds/--keep-audio (ראו
        # ui/dashboard.py) - אותו דפוס בדיוק כמו is_video_editor.
        is_timelapse_maker = bool(state.selected_script) and os.path.basename(state.selected_script) == "timelapse_maker.py"
        if is_timelapse_maker:
            self.timelapse_target_seconds_var.set(state.timelapse_target_seconds)
            self.timelapse_keep_audio_var.set(state.timelapse_keep_audio)
            self.timelapse_frame.pack(pady=(0, 10), padx=15, fill="x")
        else:
            self.timelapse_frame.pack_forget()
