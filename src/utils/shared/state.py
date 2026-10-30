# utils/shared/state.py
import json
import os

from utils.shared.atomic_write import atomic_write_json
from utils.shared.file_lock import file_lock
from utils.shared import data_paths, install_profile

CONFIG_FILE = data_paths.path(data_paths.CONFIG)
# מנעול חוצה-תהליכים סביב כל קריאה-שינוי-כתיבה של config.json - גם הדסקטופ
# (save_config למטה) וגם ה-web app (web_app.py's _save_raw_config) כותבים
# לקובץ הזה, בלי זה שני כותבים בו-זמנים יכולים לדרוס בשקט אחד את השני
# (item: בדיקת באגים מקיפה).
CONFIG_LOCK_FILE = CONFIG_FILE + ".lock"

# הגדרת ה-Themes המרכזית עברה לכאן כדי שכל רכיב UI יוכל למשוך צבעים בבטחה
THEMES = {
    "Green": {"accent": "#00e676", "accent_hover": "#00c853", "led_on": "#00e676", "led_dim": "#004d1a", "border": "#00e676"},
    "Pink": {"accent": "#ff007f", "accent_hover": "#d9006c", "led_on": "#ff007f", "led_dim": "#4d0026", "border": "#ff007f"},
    "Blue": {"accent": "#00e5ff", "accent_hover": "#00b3cc", "led_on": "#00e5ff", "led_dim": "#004c53", "border": "#00e5ff"},
    "Cyberpunk": {"accent": "#f3e500", "accent_hover": "#bfa500", "led_on": "#f3e500", "led_dim": "#4a3e00", "border": "#f3e500"},
    "Rocket League": {"accent": "#ff4500", "accent_hover": "#cc3700", "led_on": "#0088ff", "led_dim": "#003366", "border": "#ff4500"}
}

DEFAULT_CUSTOM_ACCENT = "#00e676"


def derive_theme_from_accent(hex_color):
    """בונה dict תאום ל-THEMES מצבע accent בודד (מה-color picker) - hover
    ו-led_dim מחושבים כגרסאות מוכהות של אותו צבע, כדי לא לדרוש מהמשתמש לבחור
    5 גוונים בנפרד עבור ערכת נושא "Custom" אחת."""
    hex_color = hex_color.lstrip("#")
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 0, 230, 118  # נופל חזרה לירוק (Green) אם הקלט לא hex תקין

    def _scale(factor):
        return "#{:02x}{:02x}{:02x}".format(
            max(0, min(255, int(r * factor))),
            max(0, min(255, int(g * factor))),
            max(0, min(255, int(b * factor))),
        )

    accent = f"#{r:02x}{g:02x}{b:02x}"
    return {"accent": accent, "accent_hover": _scale(0.8), "led_on": accent, "led_dim": _scale(0.25), "border": accent}


THEMES["Custom"] = derive_theme_from_accent(DEFAULT_CUSTOM_ACCENT)

# צבעי ניטרלי חוזרים (רקעים/מסגרות/טקסט) שהיו כתובים כ-hex מקובע בעשרות מקומות
# ב-gui_manager.pyw וב-ui/*.py. ריכוז כאן מאפשר להחליף ערכת נושא במקום אחד.
#
# הערה טכנית: כל הרכיבים בונים את ה-widgets פעם אחת בעליית האפליקציה עם הערך
# הנוכחי של PALETTE["..."] "צרוב" בתוכם - אין רענון חי של צבעים בלי לבנות מחדש
# את כל העצים. לכן מעבר Dark/Light הוא "restart to apply", לא מיתוג חי.
DARK_PALETTE = {
    "bg_root": "#0c0c0e",
    "surface": "#141418",
    "surface_alt": "#101014",
    "surface_deep": "#070709",
    "surface_console": "#050505",
    "surface_purple": "#181822",
    "surface_stats": "#1a1a26",
    "border": "#22222b",
    "border_dim": "#1d1d26",
    "border_dim2": "#1d1d24",
    "border_search": "#292932",
    "border_sidebar": "#222228",
    "border_console": "#113311",
    # שלב בהירות ברור מעל border_dim2 - למשוב hover נראה על כרטיסי סקריפט
    # בסיידבר (ראו ui/sidebar.py), ולא רק ההצללה האוטומטית הכהה-כמעט-זהה
    # שבררת המחדל של CTkButton הייתה נותנת.
    "script_btn_hover": "#2a2a35",
    "text_muted": "#8e8e9a",
    "text_dim": "#a9a9b3",
    "text_faint": "#555566",
    "text_category": "#6f7280",
    "led_off": "#555555",
    "danger": "#e55353",
    "danger_hover": "#b83c3c",
    "success_btn": "#2eb85c",
    "success_btn_hover": "#1b853e",
    "console_text": "#00ff66",
    "alert_banner": "#ff3355",
    "stop_btn": "#ff1744",
    "pink_accent": "#ff007f",
    "queued": "#f5a623",
    "disk_bar": "#ffea00",
    "white": "#ffffff",
    "cpu_ring": "#00e5ff",
    "gpu_ring": "#7c4dff",
}

LIGHT_PALETTE = {
    "bg_root": "#f2f2f5",
    "surface": "#ffffff",
    "surface_alt": "#eceef2",
    "surface_deep": "#e4e6eb",
    "surface_console": "#fbfbfc",
    "surface_purple": "#eeeaf7",
    "surface_stats": "#eef0f7",
    "border": "#d7d9e0",
    "border_dim": "#e0e2e8",
    "border_dim2": "#dcdee5",
    "border_search": "#c9cbd4",
    "border_sidebar": "#d7d9e0",
    "script_btn_hover": "#c8cad4",
    "border_console": "#c5e3c8",
    "text_muted": "#5a5d6b",
    "text_dim": "#3d3f4a",
    "text_faint": "#8a8d99",
    "text_category": "#6f7280",
    "led_off": "#aeb1bc",
    "danger": "#d9363e",
    "danger_hover": "#b8262d",
    "success_btn": "#1f9d4d",
    "success_btn_hover": "#187e3d",
    "console_text": "#0a8a2e",
    "alert_banner": "#ff3355",
    "stop_btn": "#e0143c",
    "pink_accent": "#d6006a",
    "queued": "#c47c00",
    "disk_bar": "#c99700",
    "white": "#14161c",
    "cpu_ring": "#0090a8",
    "gpu_ring": "#6a3fd1",
}


# מצב נגישות - ניגודיות מקסימלית (שחור/לבן טהורים, בלי גוני ביניים עדינים
# שקשה להבחין ביניהם) - לא רק "Dark אבל יותר כהה", אלא פלטה נפרדת שנבנתה
# סביב הכלל "כל טקסט/מסגרת רלוונטי צריך יחס ניגודיות גבוה משמעותית מהרקע".
HIGH_CONTRAST_PALETTE = {
    "bg_root": "#000000",
    "surface": "#000000",
    "surface_alt": "#0a0a0a",
    "surface_deep": "#000000",
    "surface_console": "#000000",
    "surface_purple": "#0a0a0a",
    "surface_stats": "#0a0a0a",
    "border": "#ffffff",
    "border_dim": "#ffffff",
    "border_dim2": "#ffffff",
    "border_search": "#ffffff",
    "border_sidebar": "#ffffff",
    "border_console": "#ffffff",
    "script_btn_hover": "#333333",
    "text_muted": "#ffffff",
    "text_dim": "#ffffff",
    "text_faint": "#cccccc",
    "text_category": "#ffffff",
    "led_off": "#666666",
    "danger": "#ff5555",
    "danger_hover": "#ff8888",
    "success_btn": "#55ff55",
    "success_btn_hover": "#88ff88",
    "console_text": "#00ff00",
    "alert_banner": "#ff0000",
    "stop_btn": "#ff0000",
    "pink_accent": "#ff55ff",
    "queued": "#ffff00",
    "disk_bar": "#ffff00",
    "white": "#ffffff",
    "cpu_ring": "#00ffff",
    "gpu_ring": "#ff55ff",
}

THEME_MODES = ("dark", "light", "high_contrast")
_PALETTE_BY_MODE = {"dark": DARK_PALETTE, "light": LIGHT_PALETTE, "high_contrast": HIGH_CONTRAST_PALETTE}


def _load_saved_theme_mode():
    """נקרא לפני בניית ה-UI כדי לדעת איזה PALETTE להשתמש בו - לא ניתן להמתין
    לבניית AppState כי PALETTE נטען בזמן import, לפני שהמחלקה בכלל קיימת."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                mode = json.load(f).get("theme_mode", "dark")
                return mode if mode in THEME_MODES else "dark"
        except Exception:
            pass
    return "dark"


PALETTE = _PALETTE_BY_MODE[_load_saved_theme_mode()]

# ברירות מחדל לרכיבי הממשק שניתנים להדלקה/כיבוי מטאב "עיצוב וממשק"
DEFAULT_UI_SETTINGS = {
    "rings": True,
    "drawer": True,
    "palette": True,
    "transparency": True,
    "always_on_top": False,
    "sound_fx": True,
    "syntax_highlight": True,
    "cpu_alerts": True,
    "shortcut_bar": True
}

# מקור אמת יחיד לשם/סוג/ברירת מחדל של כל שדה ב-config.json - load_config() היה
# עושה d.get(key, default) פזור בלי לבדוק טיפוס בכלל, כך ש-config.json פגום
# (למשל ערך מספרי איפה שאמור להיות bool) היה זולג בשקט עמוק לתוך קוד ה-GUI
# ורק שם מתגלה (או לא מתגלה) - במקום כישלון גלוי וברור כבר בשלב הטעינה.
CONFIG_SCHEMA = {
    "folder": ("selected_gameplay_folder", str, ""),
    "nas_folder": ("backup_folder_path", str, ""),
    "theme": ("current_theme_name", str, "Green"),
    "turbo_active": ("turbo_mode_active", bool, False),
    "night_active": ("night_mode_active", bool, False),
    "webhook": ("discord_webhook_url", str, ""),
    "auto_backup_active": ("auto_backup_active", bool, False),
    "theme_mode": ("theme_mode", str, "dark"),
    "language": ("language", str, "he"),
    "custom_accent_hex": ("custom_accent_hex", str, DEFAULT_CUSTOM_ACCENT),
    "onboarding_dismissed": ("onboarding_dismissed", bool, False),
    "last_digest_sent_at": ("last_digest_sent_at", str, ""),
    "story_cutter_ai_provider": ("story_cutter_ai_provider", str, "gemini"),
    # 30.10.2026: הקונטיינר שהמתג "שרת Docker" מפעיל; ריק = בלי מתג ובלי כרטיס (utils/shared/install_profile)
    "docker_container": ("docker_container", str, ""),
    # מאוחסן כ-CSV של שמות-קבצים (לא list) בכוונה - כל ערכי CONFIG_SCHEMA האחרים
    # הם str/bool פשוטים; default=[] משותף היה מסתכן בבאג של אובייקט list אחד
    # ששותף בין כל טעינה/איפוס (כל שינוי היה "דולף" בין הריצות).
    "favorite_scripts": ("favorite_scripts_csv", str, ""),
    # item: תיבת העדפות לכל פרופיל - CSV של שמות-שדות (מפתחות PROFILE_FIELDS),
    # אותו עיקרון בדיוק כמו favorite_scripts_csv למעלה (לא list, מסיבה זהה).
    # נשמר/נטען גם כחלק מ-snapshot של פרופיל (video_editor_profiles.py's
    # PROFILE_FIELDS) - כך שלכל פרופיל אישי יכול להיות סט מועדפים שונה.
    "video_editor_favorite_fields": ("video_editor_favorite_fields", str, ""),
    # item: טור הכרות ראשוני לעורך-העל - נשאר True לצמיתות אחרי שנדחה פעם
    # אחת, כדי שלא יופיע שוב בכל הפעלה (לא state של הסשן הנוכחי בלבד).
    "video_editor_onboarding_seen": ("video_editor_onboarding_seen", bool, False),
    "video_editor_watermark_path": ("video_editor_watermark_path", str, ""),
    "video_editor_watermark_position": ("video_editor_watermark_position", str, "bottom-right"),
    "video_editor_watermark_scale": ("video_editor_watermark_scale", str, "0.15"),
    # "" = בלי מיקום מותאם-אישית (גרירה) - נופל בחזרה ל-video_editor_watermark_position.
    # שני השדות נדרשים ביחד, אותו עיקרון בדיוק כמו --watermark_x/--watermark_y ב-video_editor.py.
    "video_editor_watermark_x": ("video_editor_watermark_x", str, ""),
    "video_editor_watermark_y": ("video_editor_watermark_y", str, ""),
    "video_editor_vertical": ("video_editor_vertical", bool, False),
    "video_editor_target_seconds": ("video_editor_target_seconds", str, "0"),
    "video_editor_keep_audio": ("video_editor_keep_audio", bool, False),
    "video_editor_loudnorm": ("video_editor_loudnorm", bool, False),
    "video_editor_thumbnail": ("video_editor_thumbnail", bool, False),
    "video_editor_codec": ("video_editor_codec", str, "h264"),
    # ריק = כבוי (בלי מחיקת watermark ישן) - ראו my_scripts/video/video_editor.py's
    # --remove_watermark_position. width_fraction/height_fraction נשארים בברירת
    # המחדל של הסקריפט (לא חשופים ב-GUI), אותו עיקרון בדיוק כמו watermark_scale
    # של הוספת watermark - לא כל דגל צריך שדה משלו בממשק.
    "video_editor_remove_watermark_position": ("video_editor_remove_watermark_position", str, ""),
    # 10 האפשרויות שנוספו ל-video_editor.py (item: video editor upgrades) -
    # שדות מספריים כ-str, אותו עיקרון בדיוק כמו video_editor_target_seconds
    # (CTkEntry/StringVar דורשים str, ההמרה לפייתון-מספרי קורית ב-handler
    # ולא כאן) - "" (ריק) משמש "לא הוגדר" עבור trim_duration/loudnorm_target,
    # שני הדגלים היחידים כאן שהם Optional באמת ב-CLI (0 הוא ערך תקף בפני
    # עצמו ל-trim_start, אז לא יכול לשמש גם כ"כבוי").
    "video_editor_watermark_opacity": ("video_editor_watermark_opacity", str, "1.0"),
    "video_editor_smart_crop": ("video_editor_smart_crop", bool, False),
    "video_editor_captions": ("video_editor_captions", bool, False),
    "video_editor_captions_translate": ("video_editor_captions_translate", bool, False),
    "video_editor_blur_background": ("video_editor_blur_background", bool, False),
    "video_editor_trim_start": ("video_editor_trim_start", str, "0"),
    "video_editor_trim_duration": ("video_editor_trim_duration", str, ""),
    "video_editor_trim_silence": ("video_editor_trim_silence", bool, False),
    "video_editor_denoise": ("video_editor_denoise", bool, False),
    "video_editor_sharpen": ("video_editor_sharpen", bool, False),
    "video_editor_loudnorm_target": ("video_editor_loudnorm_target", str, ""),
    # השדות שנוספו ב"שדרוג הענקי" (צבע/HDR, תנועה, אודיו, פילטרים ויזואליים,
    # עיצוב כתוביות) - לא כולל smooth_fps (דורש --fps מפורש, ששום שדה לא
    # חושף בכלל ב-GUI) ולא chromakey-similarity/blend (כיוונון עדין, אותו
    # עיקרון "לא כל דגל צריך שדה" כמו watermark_scale/remove_watermark_width_fraction).
    # ריק = שמירת קצב הפריימים המקורי של כל קובץ (item: שימור FPS מקורי כברירת
    # מחדל) - לא נשמר ב-video_editor_lut_path/וכו' למעלה כי זה קדם להם
    # (שדרוג ה-FPS/HDR המקורי), נוסף כאן בנפרד רק כש-UI parity התבקש בשבילו.
    "video_editor_fps": ("video_editor_fps", str, ""),
    "video_editor_lut_path": ("video_editor_lut_path", str, ""),
    "video_editor_auto_levels": ("video_editor_auto_levels", bool, False),
    "video_editor_noise_gate": ("video_editor_noise_gate", bool, False),
    "video_editor_remove_mid_silence": ("video_editor_remove_mid_silence", bool, False),
    "video_editor_stabilize": ("video_editor_stabilize", bool, False),
    "video_editor_chromakey": ("video_editor_chromakey", bool, False),
    "video_editor_chromakey_color": ("video_editor_chromakey_color", str, "0x00FF00"),
    "video_editor_chromakey_bg_color": ("video_editor_chromakey_bg_color", str, "0x000000"),
    "video_editor_caption_font": ("video_editor_caption_font", str, "Arial"),
    "video_editor_caption_font_size": ("video_editor_caption_font_size", str, "16"),
    "video_editor_caption_color": ("video_editor_caption_color", str, "#FFFFFF"),
    "video_editor_caption_position": ("video_editor_caption_position", str, "bottom"),
    "video_editor_preserve_resolution": ("video_editor_preserve_resolution", bool, False),
    "video_editor_no_suffix": ("video_editor_no_suffix", bool, False),
    "video_editor_number_videos": ("video_editor_number_videos", bool, False),
    "video_editor_number_prefix": ("video_editor_number_prefix", str, "Clip"),
    # "" = "לא הוגדר" (ממשיך מהמספר האחרון שנשמר ב-data/video_editor_counter.txt),
    # אותו עיקרון בדיוק כמו video_editor_trim_duration/video_editor_loudnorm_target.
    "video_editor_number_start": ("video_editor_number_start", str, ""),
    "video_editor_parallel": ("video_editor_parallel", str, "1"),
    # "" = אוטומטי (נבדק בפועל בתחילת הריצה, ראו --max-concurrent-nvenc), אותו
    # עיקרון בדיוק כמו video_editor_number_start.
    "video_editor_max_concurrent_nvenc": ("video_editor_max_concurrent_nvenc", str, ""),
    "video_editor_effort": ("video_editor_effort", str, "high"),
    "video_editor_container": ("video_editor_container", str, "mp4"),
    "video_editor_output_template": ("video_editor_output_template", str, ""),
    "video_editor_validate_only": ("video_editor_validate_only", bool, False),
    "video_editor_notify_per_file": ("video_editor_notify_per_file", bool, False),
    "video_editor_export_report": ("video_editor_export_report", str, ""),
    "timelapse_target_seconds": ("timelapse_target_seconds", str, "60"),
    # ברירת מחדל True (בניגוד ל---keep-audio של timelapse_maker.py עצמו, שכבוי
    # כברירת מחדל בשורת הפקודה) - כי בלי אינדיקציה כלשהי ב-GUI, משתמש שמריץ
    # את הסקריפט הזה מקבל תוצר שקט לגמרי בלי שום רמז למה, ובלי דרך לשנות את
    # זה מהממשק (הדגל היה קיים רק ב-CLI). ה-GUI הוא הדרך היחידה שרוב המשתמשים
    # בפרויקט הזה בפועל מריצים סקריפטים, אז ברירת המחדל שלו צריכה לשקף את
    # הציפייה הסבירה (יש סאונד), עם אפשרות כיבוי למי שמעדיף שקט.
    "timelapse_keep_audio": ("timelapse_keep_audio", bool, True),
    # item: פריסת ווידג'טים ניתנת לסידור אישי - סדר 5 כרטיסי הסטטיסטיקות
    # (CPU/RAM/GPU/Uptime/Docker) בראש הדשבורד. CSV (לא list), אותו עיקרון
    # בדיוק כמו favorite_scripts - str פשוט תואם ל-CONFIG_SCHEMA האחיד.
    "dashboard_widget_order": ("dashboard_widget_order_csv", str, "cpu,ram,gpu,uptime,docker"),
}

# חמשת ה-widgets הקבועים בשורת הסטטיסטיקות - סדר הופעה כאן הוא רק ברירת
# המחדל/סט האמת של המזהים התקינים, לא סדר תצוגה (זה מגיע מ-get_dashboard_widget_order).
DASHBOARD_WIDGET_IDS = ("cpu", "ram", "gpu", "uptime", "docker")

class AppState:
    """מנוע Singleton מרכזי לניהול מצב האפליקציה והגדרותיה"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppState, cls).__new__(cls)
            cls._instance._init_state()
        return cls._instance

    def _init_state(self):
        self.selected_script = None
        self.selected_gameplay_folder = ""
        self.backup_folder_path = ""
        self.discord_webhook_url = ""
        self.last_selected_clip_path = ""
        self.current_theme_name = "Green"
        self.turbo_mode_active = False
        self.night_mode_active = False
        self.auto_backup_active = False
        self.theme_mode = "dark"
        self.language = "he"
        self.custom_accent_hex = DEFAULT_CUSTOM_ACCENT
        self.onboarding_dismissed = False
        self.last_digest_sent_at = ""
        self.story_cutter_ai_provider = "gemini"
        self.docker_container = ""
        self.favorite_scripts_csv = ""
        self.video_editor_favorite_fields = ""
        self.video_editor_onboarding_seen = False
        self.video_editor_watermark_path = ""
        self.video_editor_watermark_position = "bottom-right"
        self.video_editor_watermark_scale = "0.15"
        self.video_editor_watermark_x = ""
        self.video_editor_watermark_y = ""
        self.video_editor_vertical = False
        self.video_editor_target_seconds = "0"
        self.video_editor_keep_audio = False
        self.video_editor_loudnorm = False
        self.video_editor_thumbnail = False
        self.video_editor_codec = "h264"
        self.video_editor_remove_watermark_position = ""
        self.video_editor_watermark_opacity = "1.0"
        self.video_editor_smart_crop = False
        self.video_editor_captions = False
        self.video_editor_captions_translate = False
        self.video_editor_blur_background = False
        self.video_editor_trim_start = "0"
        self.video_editor_trim_duration = ""
        self.video_editor_trim_silence = False
        self.video_editor_denoise = False
        self.video_editor_sharpen = False
        self.video_editor_loudnorm_target = ""
        self.video_editor_fps = ""
        self.video_editor_lut_path = ""
        self.video_editor_auto_levels = False
        self.video_editor_noise_gate = False
        self.video_editor_remove_mid_silence = False
        self.video_editor_stabilize = False
        self.video_editor_chromakey = False
        self.video_editor_chromakey_color = "0x00FF00"
        self.video_editor_chromakey_bg_color = "0x000000"
        self.video_editor_caption_font = "Arial"
        self.video_editor_caption_font_size = "16"
        self.video_editor_caption_color = "#FFFFFF"
        self.video_editor_caption_position = "bottom"
        self.video_editor_preserve_resolution = False
        self.video_editor_no_suffix = False
        self.video_editor_number_videos = False
        self.video_editor_number_prefix = "Clip"
        self.video_editor_number_start = ""
        self.video_editor_parallel = "1"
        self.video_editor_max_concurrent_nvenc = ""
        self.video_editor_effort = "high"
        self.video_editor_container = "mp4"
        self.video_editor_output_template = ""
        self.video_editor_validate_only = False
        self.video_editor_notify_per_file = False
        self.video_editor_export_report = ""
        self.timelapse_target_seconds = "60"
        self.timelapse_keep_audio = True
        self.dashboard_widget_order_csv = "cpu,ram,gpu,uptime,docker"
        self.ui_settings = dict(DEFAULT_UI_SETTINGS)
        self.load_config()

    def set_custom_accent(self, hex_color):
        """מעדכן את ערכת הנושא "Custom" (THEMES["Custom"], ראו derive_theme_from_accent)
        מצבע accent בודד ובוחר אותה כערכה הפעילה. לא שומר config - קריאה
        מפורשת ל-save_config() היא באחריות הקורא, כמו בשאר ה-setters."""
        self.custom_accent_hex = hex_color
        THEMES["Custom"] = derive_theme_from_accent(hex_color)
        self.current_theme_name = "Custom"

    def get_favorite_scripts(self):
        """מחזיר set של שמות-קבצים (basename, לא נתיב מלא) שסומנו כמועדפים."""
        return {name for name in self.favorite_scripts_csv.split(",") if name}

    def toggle_favorite_script(self, script_basename):
        """מוסיף/מסיר שם קובץ מהמועדפים ושומר config מיד - אחריות הקורא (לא
        שדה נפרד) כי אין הקשר GUI-loop שקורא לזה שוב ושוב, בניגוד ל-set_custom_accent."""
        favorites = self.get_favorite_scripts()
        if script_basename in favorites:
            favorites.discard(script_basename)
        else:
            favorites.add(script_basename)
        self.favorite_scripts_csv = ",".join(sorted(favorites))
        self.save_config()

    def get_dashboard_widget_order(self):
        """מחזיר רשימת widget IDs לפי הסדר האישי שנשמר (item: reorderable
        dashboard widgets) - מוודא שכל 5 ה-widgets הקבועים מופיעים בדיוק פעם
        אחת, גם אם ה-CSV ב-config.json פגום/חלקי (למשל נערך ידנית או מגרסה
        ישנה בלי השדה) - נופל בחזרה לסדר ברירת המחדל המלא כשהוא לא."""
        order = [w for w in self.dashboard_widget_order_csv.split(",") if w in DASHBOARD_WIDGET_IDS]
        if sorted(order) != sorted(DASHBOARD_WIDGET_IDS):
            return list(DASHBOARD_WIDGET_IDS)
        return order

    @property
    def current_theme(self):
        """מחזיר דינמית את מילון הצבעים המלא לפי השם הנבחר"""
        return THEMES.get(self.current_theme_name, THEMES["Green"])

    def save_config(self):
        try:
            with file_lock(CONFIG_LOCK_FILE):
                atomic_write_json(CONFIG_FILE, {
                    "folder": self.selected_gameplay_folder,
                    "theme": self.current_theme_name,
                    "nas_folder": self.backup_folder_path,
                    "turbo_active": self.turbo_mode_active,
                    "night_active": self.night_mode_active,
                    "webhook": self.discord_webhook_url,
                    "auto_backup_active": self.auto_backup_active,
                    "theme_mode": self.theme_mode,
                    "language": self.language,
                    "custom_accent_hex": self.custom_accent_hex,
                    "onboarding_dismissed": self.onboarding_dismissed,
                    "last_digest_sent_at": self.last_digest_sent_at,
                    "story_cutter_ai_provider": self.story_cutter_ai_provider,
                    "docker_container": self.docker_container,
                    "favorite_scripts": self.favorite_scripts_csv,
                    "video_editor_favorite_fields": self.video_editor_favorite_fields,
                    "video_editor_onboarding_seen": self.video_editor_onboarding_seen,
                    "video_editor_watermark_path": self.video_editor_watermark_path,
                    "video_editor_watermark_position": self.video_editor_watermark_position,
                    "video_editor_watermark_scale": self.video_editor_watermark_scale,
                    "video_editor_watermark_x": self.video_editor_watermark_x,
                    "video_editor_watermark_y": self.video_editor_watermark_y,
                    "video_editor_vertical": self.video_editor_vertical,
                    "video_editor_target_seconds": self.video_editor_target_seconds,
                    "video_editor_keep_audio": self.video_editor_keep_audio,
                    "video_editor_loudnorm": self.video_editor_loudnorm,
                    "video_editor_thumbnail": self.video_editor_thumbnail,
                    "video_editor_codec": self.video_editor_codec,
                    "video_editor_remove_watermark_position": self.video_editor_remove_watermark_position,
                    "video_editor_watermark_opacity": self.video_editor_watermark_opacity,
                    "video_editor_smart_crop": self.video_editor_smart_crop,
                    "video_editor_captions": self.video_editor_captions,
                    "video_editor_captions_translate": self.video_editor_captions_translate,
                    "video_editor_blur_background": self.video_editor_blur_background,
                    "video_editor_trim_start": self.video_editor_trim_start,
                    "video_editor_trim_duration": self.video_editor_trim_duration,
                    "video_editor_trim_silence": self.video_editor_trim_silence,
                    "video_editor_denoise": self.video_editor_denoise,
                    "video_editor_sharpen": self.video_editor_sharpen,
                    "video_editor_loudnorm_target": self.video_editor_loudnorm_target,
                    "video_editor_fps": self.video_editor_fps,
                    "video_editor_lut_path": self.video_editor_lut_path,
                    "video_editor_auto_levels": self.video_editor_auto_levels,
                    "video_editor_noise_gate": self.video_editor_noise_gate,
                    "video_editor_remove_mid_silence": self.video_editor_remove_mid_silence,
                    "video_editor_stabilize": self.video_editor_stabilize,
                    "video_editor_chromakey": self.video_editor_chromakey,
                    "video_editor_chromakey_color": self.video_editor_chromakey_color,
                    "video_editor_chromakey_bg_color": self.video_editor_chromakey_bg_color,
                    "video_editor_caption_font": self.video_editor_caption_font,
                    "video_editor_caption_font_size": self.video_editor_caption_font_size,
                    "video_editor_caption_color": self.video_editor_caption_color,
                    "video_editor_caption_position": self.video_editor_caption_position,
                    "video_editor_preserve_resolution": self.video_editor_preserve_resolution,
                    "video_editor_no_suffix": self.video_editor_no_suffix,
                    "video_editor_number_videos": self.video_editor_number_videos,
                    "video_editor_number_prefix": self.video_editor_number_prefix,
                    "video_editor_number_start": self.video_editor_number_start,
                    "video_editor_parallel": self.video_editor_parallel,
                    "video_editor_max_concurrent_nvenc": self.video_editor_max_concurrent_nvenc,
                    "video_editor_effort": self.video_editor_effort,
                    "video_editor_container": self.video_editor_container,
                    "video_editor_output_template": self.video_editor_output_template,
                    "video_editor_validate_only": self.video_editor_validate_only,
                    "video_editor_notify_per_file": self.video_editor_notify_per_file,
                    "video_editor_export_report": self.video_editor_export_report,
                    "timelapse_target_seconds": self.timelapse_target_seconds,
                    "timelapse_keep_audio": self.timelapse_keep_audio,
                    "dashboard_widget_order": self.dashboard_widget_order_csv,
                    "ui_settings": self.ui_settings,
                    # המפתחות שהשרת והבוט כתבו (סינון RSS, אזור Steam) - הקובץ נכתב מחדש כולו, אז שומרים עליהם
                    **{k: v for k, v in install_profile.read(CONFIG_FILE).items() if k in install_profile.NEW_INSTALL
                       and k != "docker_container"},
                }, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[state] שגיאה בשמירת config.json: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)

                for json_key, (attr_name, expected_type, default) in CONFIG_SCHEMA.items():
                    value = d.get(json_key, default)
                    # isinstance(True, int) הוא True ב-פייתון (bool הוא תת-מחלקה של
                    # int) - בלי הבדיקה המפורשת הזו, ערך bool תקין היה "עובר" גם
                    # אם expected_type הוא str ולהיפך, במקרים מסוימים.
                    valid = isinstance(value, expected_type) and not (expected_type is str and isinstance(value, bool))
                    if not valid:
                        print(f"[state] '{json_key}' ב-config.json הוא {type(value).__name__}, ציפינו {expected_type.__name__} - חוזר לברירת מחדל ({default!r}).")
                        value = default
                    setattr(self, attr_name, value)

                if self.theme_mode not in THEME_MODES:
                    print(f"[state] 'theme_mode' לא מוכר ({self.theme_mode!r}) - חוזר ל-'dark'.")
                    self.theme_mode = "dark"
                if self.language not in ("he", "en"):
                    print(f"[state] 'language' לא מוכר ({self.language!r}) - חוזר ל-'he'.")
                    self.language = "he"
                if self.story_cutter_ai_provider not in ("gemini", "local"):
                    print(f"[state] 'story_cutter_ai_provider' לא מוכר ({self.story_cutter_ai_provider!r}) - חוזר ל-'gemini'.")
                    self.story_cutter_ai_provider = "gemini"
                if self.video_editor_watermark_position not in ("top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right", "center"):
                    print(f"[state] 'video_editor_watermark_position' לא מוכר ({self.video_editor_watermark_position!r}) - חוזר ל-'bottom-right'.")
                    self.video_editor_watermark_position = "bottom-right"
                if self.video_editor_codec not in ("h264", "hevc", "av1"):
                    print(f"[state] 'video_editor_codec' לא מוכר ({self.video_editor_codec!r}) - חוזר ל-'h264'.")
                    self.video_editor_codec = "h264"
                if self.video_editor_caption_position not in ("bottom", "top", "center"):
                    print(f"[state] 'video_editor_caption_position' לא מוכר ({self.video_editor_caption_position!r}) - חוזר ל-'bottom'.")
                    self.video_editor_caption_position = "bottom"
                if self.video_editor_effort not in ("low", "medium", "high", "auto"):
                    print(f"[state] 'video_editor_effort' לא מוכר ({self.video_editor_effort!r}) - חוזר ל-'high'.")
                    self.video_editor_effort = "high"
                if self.video_editor_container not in ("mp4", "mkv"):
                    print(f"[state] 'video_editor_container' לא מוכר ({self.video_editor_container!r}) - חוזר ל-'mp4'.")
                    self.video_editor_container = "mp4"
                if self.video_editor_export_report not in ("", "csv", "xlsx", "both"):
                    print(f"[state] 'video_editor_export_report' לא מוכר ({self.video_editor_export_report!r}) - חוזר לכבוי.")
                    self.video_editor_export_report = ""

                # מרענן את THEMES["Custom"] מה-hex שנשמר - אחרת, אם current_theme_name
                # הוא "Custom" מריצה קודמת, הוא היה מצביע על צבע ברירת המחדל
                # (הירוק) עד שהמשתמש בוחר צבע חדש דרך ה-color picker.
                THEMES["Custom"] = derive_theme_from_accent(self.custom_accent_hex)

                saved_ui_settings = d.get("ui_settings", {})
                if not isinstance(saved_ui_settings, dict):
                    saved_ui_settings = {}
                self.ui_settings = {**DEFAULT_UI_SETTINGS, **saved_ui_settings}
            except Exception as e:
                print(f"[state] שגיאה בטעינת config.json: {e}")

    def reset_to_defaults(self):
        """מאפס את כל ההגדרות לברירת מחדל - לא נוגע בקובץ config.json הישן
        (הקריאה הבאה ל-save_config() תדרוס אותו); הקריאה מה-GUI אחראית לגבות
        אותו לפני קריאה לזה, אם רוצים אפשרות שחזור."""
        for _json_key, (attr_name, _expected_type, default) in CONFIG_SCHEMA.items():
            setattr(self, attr_name, default)
        self.ui_settings = dict(DEFAULT_UI_SETTINGS)
        THEMES["Custom"] = derive_theme_from_accent(self.custom_accent_hex)

state = AppState()