# ui/rocket_settings_tab.py
#
# הועבר מ-gui_manager.pyw (היה מתפרש ישירות בתוך "⚙️ הגדרות" ביחד עם
# SettingsTabComponent הגנרי, בלי שום קשר לוגי בין השניים) לתוך טאב "⚙️ הגדרות"
# המאוחד (ui/unified_settings_tab.py), תחת תת-הבחירה "🎬 Rocket Shorts".
#
# מקבל app (מופע LauncherApp) כי כמה פעולות (play_ui_sound, log_message,
# _main_dispatcher לחלון תצוגת גל הקול) הן פונקציונליות ברמת האפליקציה כולה,
# לא ספציפיות לטאב הזה - זה תואם את הדפוס הקיים כבר בקוד (למשל
# DashboardTabComponent מקבל set_led_callback מ-LauncherApp).

import json
import os
import subprocess
import sys
import threading
from tkinter import filedialog

import customtkinter as ctk

try:
    from tkinterdnd2 import DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    _DND_AVAILABLE = False

from utils.shared.state import state, PALETTE
from utils.shared.i18n import t
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.media.nvenc_probe import probe_max_concurrent_nvenc_sessions
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared import data_paths
from ui.widgets import FONT_HEBREW_TEXT, FONT_BADGE, Spinner

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTINGS_FILE_PATH = data_paths.path(data_paths.ROCKET_SETTINGS)
COUNTER_FILE_PATH = data_paths.path(data_paths.ROCKET_COUNTER)

# פרופילי איכות מוגדרים מראש (Preset Manager). כותב את המפתחות ש-
# rocket_shorts_publisher.py אכן קורא (encoder/ffmpeg_preset/quality_cq).
PRESETS = {
    "🚀 Max Quality (HEVC NVENC, P7)": {"encoder": "hevc_nvenc", "ffmpeg_preset": "p7", "quality_cq": 17},
    "📱 Balanced (HEVC NVENC, P5)": {"encoder": "hevc_nvenc", "ffmpeg_preset": "p5", "quality_cq": 19},
    "⚡ Fast Render (HEVC NVENC, P1)": {"encoder": "hevc_nvenc", "ffmpeg_preset": "p1", "quality_cq": 23},
    "🧪 AV1 Next-Gen (NVENC, P5)": {"encoder": "av1_nvenc", "ffmpeg_preset": "p5", "quality_cq": 24},
    "💻 CPU Fallback (H.264, Medium)": {"encoder": "libx264", "ffmpeg_preset": "medium", "quality_cq": 22},
}

# תואם ל-date.weekday() של פייתון (שני=0 ... ראשון=6).
RECAP_DAYS = [t("שני"), t("שלישי"), t("רביעי"), t("חמישי"), t("שישי"), t("שבת"), t("ראשון")]

# תקופת ריקאפ (item: ריקאפ חודשי/שנתי) - חודשי/שנתי רצים בתאריך קבוע (1
# לחודש/1 בינואר, ראו utils/media/compilation.py) ולא תלויים בבחירת יום-בשבוע.
RECAP_PERIOD_DISPLAY_TO_VALUE = {t("שבועי"): "week", t("חודשי"): "month", t("שנתי"): "year"}
RECAP_PERIOD_VALUE_TO_DISPLAY = {v: k for k, v in RECAP_PERIOD_DISPLAY_TO_VALUE.items()}


class RocketSettingsTabComponent(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build_component()

    def _build_component(self):
        accent_color = state.current_theme["accent"]
        card = ctk.CTkFrame(self, fg_color=PALETTE["bg_root"], corner_radius=10, border_width=1, border_color=PALETTE["border"])
        card.pack(fill="x", padx=15, pady=15)

        saved_settings = self.get_rocket_settings()
        self.input_dir_var = ctk.StringVar(value=saved_settings.get("input_dir", BASE_DIR))
        self.output_dir_var = ctk.StringVar(value=saved_settings.get("output_dir", saved_settings.get("input_dir", BASE_DIR)))
        # ריק כשעוד לא נבחר לוגו - assets/overlay.png כבר לא בריפו (כמו rocket_shorts_publisher.py ו-/api/rocket_settings)
        self.overlay_path_var = ctk.StringVar(value=saved_settings.get("watermark_image_path", ""))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=4)
        lbl_input = ctk.CTkLabel(row1, text=t("תיקיית קליפים (Import):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_input.pack(side="right", padx=(5, 0))
        entry_input = ctk.CTkEntry(row1, textvariable=self.input_dir_var, font=FONT_HEBREW_TEXT, width=330,
                                    placeholder_text=t("גרור לכאן תיקייה...") if _DND_AVAILABLE else None)
        entry_input.pack(side="right", padx=5)
        btn_browse_input = ctk.CTkButton(row1, text=t("עיון..."), font=FONT_BADGE, width=70, command=self.browse_video_dir)
        btn_browse_input.pack(side="right", padx=5)

        if _DND_AVAILABLE:
            entry_input.drop_target_register(DND_FILES)
            entry_input.dnd_bind("<<Drop>>", self.on_folder_dropped)

        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=4)
        lbl_output = ctk.CTkLabel(row2, text=t("תיקיית ייצוא (Export):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_output.pack(side="right", padx=(5, 0))
        entry_output = ctk.CTkEntry(row2, textvariable=self.output_dir_var, font=FONT_HEBREW_TEXT, width=330)
        entry_output.pack(side="right", padx=5)
        btn_browse_output = ctk.CTkButton(row2, text=t("עיון..."), font=FONT_BADGE, width=70, command=self.browse_output_dir)
        btn_browse_output.pack(side="right", padx=5)

        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=15, pady=4)
        lbl_overlay = ctk.CTkLabel(row3, text=t("תמונת Overlay:"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_overlay.pack(side="right", padx=(5, 0))
        entry_overlay = ctk.CTkEntry(row3, textvariable=self.overlay_path_var, font=FONT_HEBREW_TEXT, width=330)
        entry_overlay.pack(side="right", padx=5)
        btn_browse_overlay = ctk.CTkButton(row3, text=t("עיון..."), font=FONT_BADGE, width=70, command=self.browse_overlay_file)
        btn_browse_overlay.pack(side="right", padx=5)

        row_counter = ctk.CTkFrame(card, fg_color="transparent")
        row_counter.pack(fill="x", padx=15, pady=6)
        lbl_cnt = ctk.CTkLabel(row_counter, text=t("מספר מונה קליפ נוכחי (#):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_cnt.pack(side="right", padx=(5, 0))
        self.counter_var = ctk.StringVar(value=str(self.get_current_counter()))
        entry_cnt = ctk.CTkEntry(row_counter, textvariable=self.counter_var, font=FONT_HEBREW_TEXT, width=80, justify="center")
        entry_cnt.pack(side="right", padx=5)
        btn_dec = ctk.CTkButton(row_counter, text="-1", font=FONT_BADGE, width=35, command=lambda: self.adjust_counter(-1))
        btn_dec.pack(side="right", padx=2)
        btn_inc = ctk.CTkButton(row_counter, text="+1", font=FONT_BADGE, width=35, command=lambda: self.adjust_counter(1))
        btn_inc.pack(side="right", padx=2)

        row_preset = ctk.CTkFrame(card, fg_color="transparent")
        row_preset.pack(fill="x", padx=15, pady=6)
        lbl_prst = ctk.CTkLabel(row_preset, text=t("פרופיל איכות ואיכות וידאו:"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_prst.pack(side="right", padx=(5, 0))
        self.preset_combo = ctk.CTkOptionMenu(
            row_preset, values=list(PRESETS.keys()), font=FONT_HEBREW_TEXT, dropdown_font=FONT_HEBREW_TEXT,
            width=250, command=self.apply_preset_selection
        )
        current_match = next(
            (name for name, p in PRESETS.items()
             if p["encoder"] == saved_settings.get("encoder") and p["ffmpeg_preset"] == saved_settings.get("ffmpeg_preset")
             and p["quality_cq"] == saved_settings.get("quality_cq")),
            None
        )
        if current_match:
            self.preset_combo.set(current_match)
        self.preset_combo.pack(side="right", padx=5)

        # רינדורים מקבילים (item: מודעות למגבלת סשנים אמיתית של NVENC) - עד
        # היום rocket_shorts_publisher.py כבר קרא max_concurrent_renders
        # מ-rocket_settings.json, אבל שום ממשק (לא כאן, לא בווב) לא חשף שדה
        # בשבילו בכלל - היחיד לשנות אותו היה לערוך את קובץ ה-JSON ידנית.
        # "🎮 גלה מגבלה בפועל" מריץ בדיקה אמיתית (utils/media/nvenc_probe.py, כמה
        # קידודי NVENC זעירים מצליחים בו-זמנית) במקום להשאיר את המשתמש לנחש.
        row_concurrency = ctk.CTkFrame(card, fg_color="transparent")
        row_concurrency.pack(fill="x", padx=15, pady=6)
        lbl_concurrency = ctk.CTkLabel(row_concurrency, text=t("רינדורים מקבילים (NVENC):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_concurrency.pack(side="right", padx=(5, 0))
        self.max_concurrent_renders_var = ctk.StringVar(value=str(saved_settings.get("max_concurrent_renders", 1)))
        entry_concurrency = ctk.CTkEntry(row_concurrency, textvariable=self.max_concurrent_renders_var, font=FONT_HEBREW_TEXT, width=50, justify="center")
        entry_concurrency.pack(side="right", padx=5)
        btn_probe_nvenc = ctk.CTkButton(row_concurrency, text=t("🎮 גלה מגבלה בפועל"), font=FONT_BADGE, width=140, command=self.probe_nvenc_limit)
        btn_probe_nvenc.pack(side="right", padx=5)
        self.nvenc_probe_status_label = ctk.CTkLabel(card, text="", font=("Segoe UI", 9), text_color=PALETTE["text_muted"], wraplength=480, anchor="e", justify="right")
        self.nvenc_probe_status_label.pack(fill="x", padx=15, pady=(0, 4))

        row_recap = ctk.CTkFrame(card, fg_color="transparent")
        row_recap.pack(fill="x", padx=15, pady=6)
        lbl_recap = ctk.CTkLabel(row_recap, text=t("ריקאפ אוטומטי (דרך הבוט):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_recap.pack(side="right", padx=(5, 0))
        self.recap_enabled_var = ctk.BooleanVar(value=bool(saved_settings.get("enable_weekly_recap", False)))
        chk_recap = ctk.CTkSwitch(row_recap, text=t("הפעל"), font=FONT_HEBREW_TEXT, variable=self.recap_enabled_var, onvalue=True, offvalue=False)
        chk_recap.pack(side="right", padx=5)
        # תקופה (שבועי/חודשי/שנתי) - יום-בשבוע למטה רלוונטי רק כש"שבועי" נבחר
        # (חודשי/שנתי רצים בתאריך קבוע, ראו utils/media/compilation.py).
        self.recap_period_var = ctk.StringVar(
            value=RECAP_PERIOD_VALUE_TO_DISPLAY.get(saved_settings.get("weekly_recap_period", "week"), RECAP_PERIOD_VALUE_TO_DISPLAY["week"])
        )
        recap_period_combo = ctk.CTkOptionMenu(row_recap, values=list(RECAP_PERIOD_DISPLAY_TO_VALUE.keys()), variable=self.recap_period_var, font=FONT_HEBREW_TEXT, dropdown_font=FONT_HEBREW_TEXT, width=90)
        recap_period_combo.pack(side="right", padx=5)
        self.recap_day_var = ctk.StringVar(value=RECAP_DAYS[min(max(int(saved_settings.get("weekly_recap_day", 6)), 0), 6)])
        recap_day_combo = ctk.CTkOptionMenu(row_recap, values=RECAP_DAYS, variable=self.recap_day_var, font=FONT_HEBREW_TEXT, dropdown_font=FONT_HEBREW_TEXT, width=100)
        recap_day_combo.pack(side="right", padx=5)

        # enable_captions כבר נקרא ע"י rocket_shorts_publisher.py (utils/media/captions.py,
        # faster-whisper) אבל לא הייתה שום דרך להפעיל אותו חוץ מעריכת rocket_settings.json
        # ידנית - הדגל היה קיים בקוד בלי אף כפתור בממשק.
        row_captions = ctk.CTkFrame(card, fg_color="transparent")
        row_captions.pack(fill="x", padx=15, pady=6)
        lbl_captions = ctk.CTkLabel(row_captions, text=t("כתוביות אוטומטיות (תמלול Whisper):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_captions.pack(side="right", padx=(5, 0))
        self.captions_enabled_var = ctk.BooleanVar(value=bool(saved_settings.get("enable_captions", False)))
        chk_captions = ctk.CTkSwitch(row_captions, text=t("הפעל"), font=FONT_HEBREW_TEXT, variable=self.captions_enabled_var, onvalue=True, offvalue=False)
        chk_captions.pack(side="right", padx=5)
        # תרגום כתוביות לאנגלית (item) - task="translate" המובנה של Whisper
        # עצמו, רלוונטי רק כש-enable_captions פעיל בפועל.
        self.captions_translate_enabled_var = ctk.BooleanVar(value=bool(saved_settings.get("enable_captions_translate", False)))
        chk_captions_translate = ctk.CTkSwitch(row_captions, text=t("תרגם לאנגלית"), font=FONT_HEBREW_TEXT, variable=self.captions_translate_enabled_var, onvalue=True, offvalue=False)
        chk_captions_translate.pack(side="right", padx=5)

        # קיצור "Clip That!" (item) - נקרא ע"י my_scripts/stream/obs_replay_watcher.py
        # (ריק=כבוי). לא נאכף/מאומת כאן (למשל שהתחביר תקין ל-keyboard.add_hotkey) -
        # הסקריפט עצמו כבר מטפל בכשל רישום בעדינות (ראו שם).
        row_clip_hotkey = ctk.CTkFrame(card, fg_color="transparent")
        row_clip_hotkey.pack(fill="x", padx=15, pady=6)
        lbl_clip_hotkey = ctk.CTkLabel(row_clip_hotkey, text=t("קיצור מקלדת ל-Clip That! (OBS, ריק=כבוי):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_clip_hotkey.pack(side="right", padx=(5, 0))
        self.clip_hotkey_var = ctk.StringVar(value=str(saved_settings.get("clip_hotkey", "")))
        entry_clip_hotkey = ctk.CTkEntry(row_clip_hotkey, textvariable=self.clip_hotkey_var, font=FONT_HEBREW_TEXT, placeholder_text="ctrl+alt+c")
        entry_clip_hotkey.pack(side="right", padx=5, fill="x", expand=True)

        # ערוץ קול לזיהוי חברים (item: friend detection via Discord voice
        # channel presence) - cogs/voice_presence_cog.py דוגם מי בערוץ הזה
        # תקופתית; cogs/approval_cog.py מתאם מול mtime הקליפ בזמן סריקה.
        # ריק=כבוי, אותה מוסכמה בדיוק כמו clip_hotkey.
        row_voice_channel = ctk.CTkFrame(card, fg_color="transparent")
        row_voice_channel.pack(fill="x", padx=15, pady=6)
        lbl_voice_channel = ctk.CTkLabel(row_voice_channel, text=t("ערוץ קול לזיהוי חברים (ריק=כבוי):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_voice_channel.pack(side="right", padx=(5, 0))
        self.capture_voice_channel_id_var = ctk.StringVar(value=str(saved_settings.get("capture_voice_channel_id", "")))
        entry_voice_channel = ctk.CTkEntry(row_voice_channel, textvariable=self.capture_voice_channel_id_var, font=FONT_HEBREW_TEXT, placeholder_text=t("מזהה ערוץ קול"))
        entry_voice_channel.pack(side="right", padx=5, fill="x", expand=True)

        # תיקיית מעקב לתוכנת לכידה נוספת (item: אינטגרציה עם תוכנת לכידה
        # נוספת - Streamlabs/ShadowPlay/כל כלי אחר) - my_scripts/stream/
        # capture_folder_watcher.py קורא את זה, ריק=כבוי אותה מוסכמה בדיוק.
        row_capture_watch = ctk.CTkFrame(card, fg_color="transparent")
        row_capture_watch.pack(fill="x", padx=15, pady=6)
        lbl_capture_watch = ctk.CTkLabel(row_capture_watch, text=t("תיקיית מעקב (Streamlabs/ShadowPlay, ריק=כבוי):"), font=FONT_HEBREW_TEXT, width=160, anchor="e")
        lbl_capture_watch.pack(side="right", padx=(5, 0))
        self.capture_watch_dir_var = ctk.StringVar(value=str(saved_settings.get("capture_watch_dir", "")))
        entry_capture_watch = ctk.CTkEntry(row_capture_watch, textvariable=self.capture_watch_dir_var, font=FONT_HEBREW_TEXT, placeholder_text=t("תיקיית הפלט של תוכנת הלכידה"))
        entry_capture_watch.pack(side="right", padx=5, fill="x", expand=True)
        btn_browse_capture_watch = ctk.CTkButton(row_capture_watch, text=t("עיון..."), font=FONT_BADGE, width=70, command=self.browse_capture_watch_dir)
        btn_browse_capture_watch.pack(side="right", padx=5)

        row_save = ctk.CTkFrame(card, fg_color="transparent")
        row_save.pack(fill="x", padx=15, pady=(8, 10))
        btn_save = ctk.CTkButton(row_save, text=t("💾 שמור הגדרות Rocket"), font=FONT_BADGE, width=140, fg_color=accent_color, command=self.save_rocket_settings)
        btn_save.pack(side="left", padx=5)
        btn_waveform = ctk.CTkButton(row_save, text=t("🌊 תצוגת גל קול"), font=FONT_BADGE, width=130, fg_color=PALETTE["border"], command=self.show_waveform_dialog)
        btn_waveform.pack(side="left", padx=5)

    def get_current_counter(self):
        if os.path.exists(COUNTER_FILE_PATH):
            try:
                with open(COUNTER_FILE_PATH, "r", encoding="utf-8") as f:
                    return int(f.read().strip())
            except Exception:
                pass
        return 1

    def adjust_counter(self, amount):
        self.app.play_ui_sound()
        try:
            val = int(self.counter_var.get()) + amount
            val = max(1, val)
            self.counter_var.set(str(val))
            with open(COUNTER_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(str(val))
            self.app.log_message("SYSTEM", t("המונה עודכן ידנית ל: #{val}", val=val), "🔢")
        except Exception:
            pass

    def apply_preset_selection(self, choice):
        self.app.play_ui_sound()
        if choice in PRESETS:
            p_data = PRESETS[choice]
            data = self.get_rocket_settings()
            data["encoder"] = p_data["encoder"]
            data["ffmpeg_preset"] = p_data["ffmpeg_preset"]
            data["quality_cq"] = p_data["quality_cq"]
            try:
                with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                self.app.log_message("SETTINGS", t("פרופיל איכות הוחל: {name}", name=choice), "⚙️")
            except Exception as e:
                self.app.log_message("ERROR", t("שגיאה בהחלת פרופיל: {error}", error=e), "❌")

    def probe_nvenc_limit(self):
        """מריץ בדיקה אמיתית (item: מודעות למגבלת סשנים אמיתית של NVENC) -
        לא אוטומטי בפתיחת הטאב (כמו בדיקת תוקף credentials): לוקח כמה שניות
        ומעמיס זמנית על ה-GPU, אז רק על-פי-בקשה מפורשת."""
        self.app.play_ui_sound()
        self.nvenc_probe_status_label.configure(text=t("בודק... (מריץ כמה קידודי NVENC זעירים בו-זמנית, עד כמה שניות)"))

        def _run():
            detected = probe_max_concurrent_nvenc_sessions(get_ffmpeg_exe(), creationflags=NO_WINDOW_FLAGS)

            def _show():
                if detected <= 0:
                    self.nvenc_probe_status_label.configure(
                        text=t("לא זוהה NVENC פעיל (אין GPU של NVIDIA, או שהוא לא נתמך) - ההגדרה הידנית נשארת ללא שינוי.")
                    )
                    return
                self.max_concurrent_renders_var.set(str(detected))
                self.nvenc_probe_status_label.configure(
                    text=t("✅ הכרטיס תומך ב-{n} רינדורים מקבילים בפועל - הוחל אוטומטית (זכור/י ללחוץ 'שמור הגדרות').", n=detected)
                )

            self.app._main_dispatcher.call_soon(_show)

        threading.Thread(target=_run, daemon=True).start()

    def get_rocket_settings(self):
        if os.path.exists(SETTINGS_FILE_PATH):
            try:
                with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def browse_video_dir(self):
        self.app.play_ui_sound()
        current_val = self.input_dir_var.get()
        initial = current_val if os.path.exists(current_val) else BASE_DIR
        selected = filedialog.askdirectory(title=t("בחר תיקייה לחיפוש סרטונים לעריכה (Import)"), initialdir=initial)
        if selected:
            self.input_dir_var.set(os.path.normpath(selected))

    def on_folder_dropped(self, event):
        """מטפל בגרירת תיקייה (או קובץ - נלקחת אז תיקיית האב שלו) לשדה תיקיית הקליפים."""
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

        self.input_dir_var.set(os.path.normpath(target_dir))
        self.app.play_ui_sound()
        self.app.log_message("SYSTEM", t("תיקיית קליפים עודכנה מגרירה: {dir}", dir=target_dir), "📂")

    def browse_output_dir(self):
        self.app.play_ui_sound()
        current_val = self.output_dir_var.get()
        initial = current_val if os.path.exists(current_val) else self.input_dir_var.get()
        selected = filedialog.askdirectory(title=t("בחר תיקייה לשמירת התוצרים המרונדרים (Export)"), initialdir=initial)
        if selected:
            self.output_dir_var.set(os.path.normpath(selected))

    def browse_capture_watch_dir(self):
        self.app.play_ui_sound()
        current_val = self.capture_watch_dir_var.get()
        initial = current_val if os.path.isdir(current_val) else BASE_DIR
        selected = filedialog.askdirectory(title=t("בחר את תיקיית הפלט של תוכנת הלכידה"), initialdir=initial)
        if selected:
            self.capture_watch_dir_var.set(os.path.normpath(selected))

    def browse_overlay_file(self):
        self.app.play_ui_sound()
        current_val = self.overlay_path_var.get()
        initial_dir = os.path.dirname(current_val) if os.path.exists(current_val) else BASE_DIR
        selected = filedialog.askopenfilename(
            title=t("בחר קובץ תמונת Overlay / לוגו"),
            initialdir=initial_dir,
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.webp"), ("All Files", "*.*")]
        )
        if selected:
            self.overlay_path_var.set(os.path.normpath(selected))

    def save_rocket_settings(self):
        self.app.play_ui_sound()
        new_dir = self.input_dir_var.get().strip()
        new_output = self.output_dir_var.get().strip()
        new_overlay = self.overlay_path_var.get().strip()

        data = self.get_rocket_settings()
        data["input_dir"] = new_dir
        data["rocket_videos_directory"] = new_dir
        data["output_dir"] = new_output if new_output else new_dir
        data["watermark_image_path"] = new_overlay
        data["enable_weekly_recap"] = self.recap_enabled_var.get()
        data["weekly_recap_period"] = RECAP_PERIOD_DISPLAY_TO_VALUE.get(self.recap_period_var.get(), "week")
        data["weekly_recap_day"] = RECAP_DAYS.index(self.recap_day_var.get())
        data["enable_captions"] = self.captions_enabled_var.get()
        data["enable_captions_translate"] = self.captions_translate_enabled_var.get()
        data["clip_hotkey"] = self.clip_hotkey_var.get().strip()
        data["capture_voice_channel_id"] = self.capture_voice_channel_id_var.get().strip()
        data["capture_watch_dir"] = self.capture_watch_dir_var.get().strip()
        try:
            data["max_concurrent_renders"] = max(1, int(self.max_concurrent_renders_var.get()))
        except ValueError:
            data["max_concurrent_renders"] = 1
        self.max_concurrent_renders_var.set(str(data["max_concurrent_renders"]))

        try:
            cnt_val = int(self.counter_var.get())
            with open(COUNTER_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(str(cnt_val))
        except Exception:
            pass

        try:
            with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            self.app.log_message("SETTINGS", t("הגדרות נשמרו! Import: {input} | Export: {output}", input=new_dir, output=data['output_dir']), "🎬")
        except Exception as e:
            self.app.log_message("ERROR", t("שגיאה בשמירת הגדרות Rocket: {error}", error=e), "❌")

    def open_export_directory(self):
        self.app.play_ui_sound()
        settings = self.get_rocket_settings()
        export_path = settings.get("output_dir", BASE_DIR)
        if os.path.exists(export_path):
            if sys.platform == "win32":
                os.startfile(export_path)
            else:
                subprocess.Popen(["xdg-open", export_path])
            self.app.log_message("SYSTEM", t("תיקיית התוצרים נפתחה: {path}", path=export_path), "📂")
        else:
            self.app.log_message("ERROR", t("תיקיית התוצרים אינה קיימת עדיין."), "⚠️")

    def show_waveform_dialog(self):
        """תצוגת גל קול - עוזר לכוון את סף הרעש של story_cutter לפני הרצה."""
        self.app.play_ui_sound()
        video_path = filedialog.askopenfilename(
            title=t("בחר סרטון להצגת גל קול"),
            filetypes=[("Video Files", "*.mp4;*.mkv;*.mov;*.avi"), ("All Files", "*.*")]
        )
        if not video_path:
            return

        dialog = ctk.CTkToplevel(self.app)
        dialog.title(t("🌊 תצוגת גל קול"))
        dialog.geometry("760x260")
        lbl_status = ctk.CTkLabel(dialog, text="", font=FONT_HEBREW_TEXT)
        lbl_status.pack(pady=10)
        # טעינת/ניתוח קובץ השמע לוקחים כמה שניות בלי שום אחוז התקדמות אמיתי -
        # ספינר (ui/widgets.py) במקום טקסט "טוען..." קבוע.
        loading_spinner = Spinner(lbl_status, t("טוען נתוני שמע..."))
        loading_spinner.start()
        canvas = ctk.CTkCanvas(dialog, width=720, height=180, bg=PALETTE["bg_root"], highlightthickness=0)
        canvas.pack(padx=15, pady=10)

        def _load():
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(video_path).set_channels(1)
                samples = audio.get_array_of_samples()
                chunk_size = max(1, len(samples) // 700)
                peaks = [max(abs(s) for s in samples[i:i + chunk_size]) for i in range(0, len(samples) - chunk_size, chunk_size)]
                max_peak = max(peaks) if peaks else 1

                def _draw():
                    loading_spinner.stop()
                    canvas.delete("all")
                    mid_y = 90
                    accent = state.current_theme["accent"]
                    for x, peak in enumerate(peaks[:720]):
                        h = (peak / max_peak) * 85 if max_peak else 0
                        canvas.create_line(x, mid_y - h, x, mid_y + h, fill=accent)
                    lbl_status.configure(text=f"📁 {os.path.basename(video_path)}")

                self.app._main_dispatcher.call_soon(_draw)
            except Exception as e:
                # פייתון מוחק את משתנה ה-except (e) ביציאה מהבלוק - הריצה בפועל
                # דוחה את ה-lambda, אז צריך ללכוד את ההודעה עכשיו ולא לסמוך על e
                # להישאר בחיים (בדיוק אותו באג שכבר תוקן ב-ui/stats_tab.py). וגם
                # דרך _main_dispatcher, לא self.after ישיר - ראו utils/shared/gui_thread.py.
                error_msg = str(e)

                def _show_error():
                    loading_spinner.stop()
                    lbl_status.configure(text=t("שגיאה בטעינת השמע: {error}", error=error_msg))

                self.app._main_dispatcher.call_soon(_show_error)

        threading.Thread(target=_load, daemon=True).start()
