# gui_manager.pyw
import customtkinter as ctk
import sys
import os
import subprocess
import threading
import time
import re
import webbrowser

# src/entrypoints/ תחת שורש הפרויקט - כל קוד המקור הראשוני (cogs/ui/utils/וכו')
# יושב תחת src/, לא בשורש עצמו, אז זה מה שצריך להיות ב-sys.path כדי ש-"utils.*"/
# "ui.*" למטה ייובאו בהצלחה - לא שורש הפרויקט עצמו.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC_DIR = os.path.join(_REPO_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ייבוא winsound פעם אחת בלבד עבור Windows
if sys.platform == "win32":
    try:
        import winsound
    except ImportError:
        winsound = None
else:
    winsound = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
except ImportError:
    TkinterDnD, DND_FILES = None, None

try:
    import pystray
    from PIL import Image as PILImage, ImageDraw as PILImageDraw
except ImportError:
    pystray = None

try:
    import keyboard as global_keyboard
except ImportError:
    global_keyboard = None

try:
    from winotify import Notification
except ImportError:
    Notification = None

from utils.shared.logging_setup import setup_persistent_logging
setup_persistent_logging("gui")

from utils.shared.state import state, PALETTE
from utils.shared.gui_thread import MainThreadDispatcher
from utils.shared.rtl_layout import rtl_column
from utils.shared.hardware import get_gpu_stats
from utils.media.game_detector import check_active_game, restore_background_processes
from utils.media.game_playtime import record_playtime_tick
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared.script_metadata import get_script_metadata
from utils.shared.i18n import t, fix_hebrew_word_order
from ui.sidebar import SidebarComponent
from ui.dashboard import DashboardTabComponent
from ui.settings_tab import SettingsTabComponent
from ui.soundboard_tab import SoundboardTabComponent
from ui.unified_settings_tab import UnifiedSettingsTabComponent
from ui.stats_tab import StatsTabComponent
from ui.bot_tab import BotTabComponent
from ui.scheduler_tab import SchedulerTabComponent
from ui.approvals_tab import ApprovalsTabComponent
from utils.shared.worker import worker
from utils.bot.scheduler import check_and_run_due_tasks
from utils.bot.weekly_digest import maybe_send_weekly_digest
from utils.shared.update_checker import check_for_update, RELEASES_PAGE_URL
from utils.shared.version import APP_VERSION
from utils.shared.data_dir import DATA_DIR
from ui.widgets import FONT_FAMILY, FONT_HEBREW_TITLE, FONT_HEBREW_SUB, FONT_HEBREW_TEXT, FONT_BADGE, FONT_LOGS, TextRedirector, CommandPalette, NotificationDrawer, Spinner

BASE_DIR = _REPO_ROOT
APP_ICON_ICO = os.path.join(BASE_DIR, "assets", "app_icon.ico")
APP_ICON_PNG = os.path.join(BASE_DIR, "assets", "app_icon.png")
os.makedirs(DATA_DIR, exist_ok=True)

# item: סינון לפי קטגוריה בלוג המאוחד - כל קטגוריה שנעבר לה log_message()
# בפועל בקוד הזה (grep על log_message("...") ברחבי src/) - לא רשימה מנוחשת.
LOG_CATEGORIES = ("SYSTEM", "ERROR", "AUTOMATION", "SETTINGS", "DISCORD", "DOCKER")

# אם tkinterdnd2 מותקן, ה-mixin שלו מוסיף תמיכת גרירה-ושחרור (Drag & Drop) ל-CTk
_APP_BASE_CLASSES = (TkinterDnD.DnDWrapper, ctk.CTk) if TkinterDnD else (ctk.CTk,)

class LauncherApp(*_APP_BASE_CLASSES):
    def __init__(self):
        super().__init__()
        if TkinterDnD:
            self.TkdndVersion = TkinterDnD._require(self)
            # גרירה על כל שטח החלון (לא רק לתוך שדה תיקייה ספציפי) - תיקייה או
            # קובץ וידאו בודד. widget ספציפי (כמו ui/settings_tab.py's
            # folder_entry) שנרשם גם הוא מקבל את ההתראה במקום זה אם גוררים
            # ישירות עליו (Tk/OLE עושה hit-testing לפי מיקום העכבר); זה כאן
            # תופס כל שאר החלון.
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self.on_global_file_dropped)

        self.title("🎬 ClipForge - Control Center")
        self.geometry("1300x980")
        self.configure(fg_color=PALETTE["bg_root"])
        # בלי זה, CustomTkinter מציב אוטומטית את אייקון ה-mascot הגנרי שלה
        # (customtkinter/windows/ctk_tk.py's _windows_set_titlebar_icon) - סמל
        # מותג אמיתי (dev/generate_app_icon.py) נדרש להירשם במפורש.
        # קובץ יכול להיות חסר (למשל אם מישהו מריץ מ-checkout טרי בלי להריץ את
        # מחולל האייקון) - לא אמור להפיל את כל האפליקציה על זה.
        if os.path.exists(APP_ICON_ICO):
            try:
                self.iconbitmap(APP_ICON_ICO)
            except Exception:
                pass
        self.protocol("WM_DELETE_WINDOW", self.on_close_request)

        self.tray_icon = None
        self.last_run_script_path = None
        # ראו utils/shared/gui_thread.py - כל קריאה ל-self.after() מ-thread רקע (בדיקות
        # preflight, מגש המערכת, טעינת waveform, print() מכל thread דרך
        # TextRedirector) עוברת דרך זה במקום, כדי לא להיתקל ב-
        # "main thread is not in main loop" שאומת בפועל בבדיקות של הפרויקט.
        self._main_dispatcher = MainThreadDispatcher()

        self.ui_settings = state.ui_settings

        if self.ui_settings["transparency"]:
            try:
                self.attributes("-alpha", 0.98)
            except Exception:
                pass

        self.start_time = time.time()
        self.auto_scroll_enabled = True
        self.is_compact = False
        self.log_expanded = False
        self.drawer_visible = False
        # item: סינון לפי קטגוריה בלוג - כל השורות שנרשמו אי-פעם (category,
        # שורה מפורמטת, color_tag), כדי שאפשר יהיה לבנות-מחדש את התצוגה
        # הגלויה מסונן בלי לאבד היסטוריה שכבר נכתבה לפני שינוי הסינון.
        self._log_history = []
        self._log_visible_categories = set(LOG_CATEGORIES)
        # item: פריסת ווידג'טים ניתנת לסידור אישי - {widget_id: card frame},
        # ממולא ע"י create_ring_card/create_metric_card, כדי ש-move_dashboard_widget
        # יוכל למקם-מחדש (grid) בלי להרוס/לבנות-מחדש אף widget בעצמו.
        self._dashboard_widget_cards = {}
        self.current_process = None # מעקב אחר תהליך מורץ (Process Control)

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self.build_skeleton()

        self.bind("<Control-k>", lambda e: self.open_command_palette() if self.ui_settings["palette"] else None)
        self.bind("<Control-l>", lambda e: self.clear_log())

        sys.stdout = TextRedirector(self.log_message, "STDOUT", "💻", original_stream=sys.stdout)
        sys.stderr = TextRedirector(self.log_message, "ERROR", "❌", original_stream=sys.stderr)

        self.after(500, self.run_preflight_checks)
        self.after(1000, self.start_loops)
        self.after(1500, self.register_global_hotkey)
        self.after(2000, self.maybe_show_onboarding)
        self.after(3000, self.check_for_updates_async)
        self._drain_main_dispatcher()

    def _drain_main_dispatcher(self):
        self._main_dispatcher.drain()
        if self.winfo_exists():
            self.after(50, self._drain_main_dispatcher)

    def maybe_show_onboarding(self):
        """דיאלוג הכוונה חד-פעמי (עד שנסגר במפורש) - כדי לא לשנות את פריסת ה-
        grid העמוסה של main_container, זה חלון נפרד (CTkToplevel) ולא באנר
        מוטמע, בדיוק כמו דיאלוג גל הקול/אבחון המערכת.

        item: התאמת NVENC/ffmpeg/DB/דיסק לתוך אשף ההגדרה הראשונית עצמו - השלב
        שהיה קודם רק "לחץ על 🩺 בפינה העליונה" (הפניה לדיאלוג אבחון נפרד)
        מריץ עכשיו את run_diagnostics() האמיתי (utils/shared/diagnostics.py) ומציג
        את התוצאות ✅/❌ מיד כאן, בלי לחיצה נוספת - אותו מקור אמת יחיד כמו
        דיאלוג "🩺 אבחון מערכת" עצמו, לא רשימת בדיקות משוכפלת."""
        if state.onboarding_dismissed:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title(t("👋 ברוך הבא ל-Launcher"))
        dialog.geometry("480x480")
        dialog.attributes("-topmost", True)

        ctk.CTkLabel(dialog, text=t("👋 ברוך הבא!"), font=FONT_HEBREW_TITLE, text_color=state.current_theme["accent"]).pack(pady=(20, 10))

        steps_before_diagnostics = [
            t("1️⃣ בטאב 'הגדרות' - בחר תיקיית גיימפליי (רק לסקריפטים שצריכים תיקיית עבודה)."),
        ]
        for step_text in steps_before_diagnostics:
            ctk.CTkLabel(dialog, text=step_text, font=FONT_HEBREW_TEXT, wraplength=420, justify="right", anchor="e").pack(pady=6, padx=20, fill="x")

        ctk.CTkLabel(dialog, text=t("2️⃣ בדיקת תקינות המערכת (ffmpeg, GPU, מסד נתונים, שטח דיסק):"), font=FONT_HEBREW_TEXT, wraplength=420, justify="right", anchor="e").pack(pady=6, padx=20, fill="x")
        onboarding_diag_status = ctk.CTkLabel(dialog, text="", font=FONT_HEBREW_TEXT)
        onboarding_diag_status.pack(pady=(0, 2))
        onboarding_diag_spinner = Spinner(onboarding_diag_status, t("בודק את המערכת..."))
        onboarding_diag_spinner.start()
        onboarding_diag_frame = ctk.CTkScrollableFrame(dialog, height=110)
        onboarding_diag_frame.pack(fill="x", padx=20, pady=(0, 4))

        def _run_onboarding_diagnostics():
            from utils.shared.diagnostics import run_diagnostics
            results = run_diagnostics()

            def _show():
                onboarding_diag_spinner.stop()
                if not dialog.winfo_exists():
                    return
                onboarding_diag_status.configure(text="")
                for name, ok, detail in results:
                    row = ctk.CTkFrame(onboarding_diag_frame, fg_color="transparent")
                    row.pack(fill="x", pady=2)
                    icon = "✅" if ok else "❌"
                    color = state.current_theme["accent"] if ok else PALETTE["danger"]
                    ctk.CTkLabel(row, text=fix_hebrew_word_order(f"{icon} {name}"), font=("Segoe UI", 11), text_color=color, anchor="e", justify="right").pack(fill="x")
                    if not ok:
                        ctk.CTkLabel(row, text=detail, font=("Consolas", 9), text_color=PALETTE["text_muted"], anchor="e", justify="right", wraplength=400).pack(fill="x")

            self._main_dispatcher.call_soon(_show)

        threading.Thread(target=_run_onboarding_diagnostics, daemon=True).start()

        for step_text in [
            t("3️⃣ בחר סקריפט מהסיידבר ולחץ 'הרץ סקריפט' בלשונית 'לוח בקרה'."),
            t("💡 ⚡ ליד סקריפט = רץ מיד, לא מחכה בתור. ⚠️ = מזיז/משנה קבצים קיימים."),
        ]:
            ctk.CTkLabel(dialog, text=step_text, font=FONT_HEBREW_TEXT, wraplength=420, justify="right", anchor="e").pack(pady=6, padx=20, fill="x")

        def dismiss():
            state.onboarding_dismissed = True
            state.save_config()
            self.play_ui_sound()
            dialog.destroy()

        ctk.CTkButton(dialog, text=t("✅ הבנתי, אל תראה שוב"), fg_color=state.current_theme["accent"], command=dismiss).pack(pady=20)

    def check_for_updates_async(self):
        """בודק מול GitHub Releases ברקע (utils/shared/update_checker.py) - קריאת
        רשת לא אמורה לחסום את ה-mainloop של Tk אפילו לרגע. self._main_dispatcher
        (לא self.after ישיר) כי זה נקרא מ-thread רקע - אותו עיקרון בדיוק כמו
        כל שאר הקוד שרץ מ-thread לא-ראשי בקובץ הזה."""
        def _check():
            latest_tag = check_for_update(APP_VERSION)
            if latest_tag:
                self._main_dispatcher.call_soon(self._show_update_available_dialog, latest_tag)
        threading.Thread(target=_check, daemon=True).start()

    def _show_update_available_dialog(self, latest_tag):
        dialog = ctk.CTkToplevel(self)
        dialog.title(t("🔔 עדכון זמין"))
        dialog.geometry("380x320")
        dialog.attributes("-topmost", True)

        ctk.CTkLabel(dialog, text=t("🔔 גרסה חדשה זמינה: {version}", version=latest_tag), font=FONT_HEBREW_TITLE, text_color=state.current_theme["accent"], wraplength=340).pack(pady=(25, 10), padx=15)
        ctk.CTkLabel(dialog, text=t("הגרסה המותקנת: {version}", version=APP_VERSION), font=FONT_HEBREW_TEXT, text_color=PALETTE["text_muted"]).pack(pady=(0, 15))

        # item: true auto-update - git pull --ff-only + uv sync (utils/shared/update_checker.py's
        # apply_update), אותה שיטת עדכון שהמשתמש היה עושה ידנית, רק בלחיצה אחת
        # עם אישור מפורש (askyesno) - לעולם לא רץ אוטומטית.
        update_status_label = ctk.CTkLabel(dialog, text="", font=("Segoe UI", 10), text_color=PALETTE["text_muted"], wraplength=340, justify="right")
        update_status_label.pack(pady=(0, 5), padx=15)

        def _do_apply_update():
            from tkinter import messagebox
            if not messagebox.askyesno(
                t("עדכון אוטומטי"),
                t("זה ירוץ 'git pull' ואז 'uv sync' על תיקיית הפרויקט הזו. ממשיכים?"),
                parent=dialog,
            ):
                return
            btn_update.configure(state="disabled", text=t("מעדכן..."))
            update_status_label.configure(text=t("מריץ git pull + uv sync..."))

            def _run():
                from utils.shared.update_checker import apply_update
                ok, message = apply_update(BASE_DIR)

                def _show():
                    if not dialog.winfo_exists():
                        return
                    btn_update.configure(state="normal", text=t("⬇️ עדכן עכשיו (git pull + uv sync)"))
                    update_status_label.configure(
                        text=("✅ " if ok else "❌ ") + message,
                        text_color=(state.current_theme["accent"] if ok else PALETTE["danger"]),
                    )

                self._main_dispatcher.call_soon(_show)

            threading.Thread(target=_run, daemon=True).start()

        btn_update = ctk.CTkButton(dialog, text=t("⬇️ עדכן עכשיו (git pull + uv sync)"), fg_color=state.current_theme["accent"], command=_do_apply_update)
        btn_update.pack(pady=5, padx=20, fill="x")
        ctk.CTkButton(dialog, text=t("🔗 פתח את עמוד ההורדה"), fg_color=PALETTE["border"], command=lambda: webbrowser.open(RELEASES_PAGE_URL)).pack(pady=5, padx=20, fill="x")
        ctk.CTkButton(dialog, text=t("סגור"), fg_color=PALETTE["border"], command=dialog.destroy).pack(pady=5, padx=20, fill="x")

    def play_ui_sound(self):
        if self.ui_settings["sound_fx"] and winsound is not None:
            try:
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass

    def run_preflight_checks(self):
        self.log_message("SYSTEM", t("מבצע בדיקת תקינות רכיבי מערכת..."), "🔍")
        
        def _check():
            # היה בודק "ffmpeg" גולמי מה-PATH בלבד - מתעלם לגמרי מ-ffmpeg/bin/ המצורף
            # לפרויקט (utils/shared/ffmpeg_locator.py, בו כל שאר הפייפליין כבר משתמש), אז
            # משתמש שסומך רק על ההעתק המצורף היה מקבל כאן אזהרת שווא בכל הפעלה.
            ffmpeg_ok = False
            try:
                res = subprocess.run([get_ffmpeg_exe(), "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
                ffmpeg_ok = res.returncode == 0
            except Exception:
                pass

            if ffmpeg_ok:
                self.log_message("SYSTEM", t("FFmpeg זוהה בהצלחה (מצורף לפרויקט או במערכת)."), "✅")
            else:
                self.log_message("ERROR", t("FFmpeg לא נמצא (לא ב-ffmpeg/bin/ ולא ב-PATH)! חלק מאפשרויות הרינדור לא יעבדו."), "⚠️")

            gpu_ok = False
            try:
                res = subprocess.run(["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=NO_WINDOW_FLAGS)
                gpu_ok = res.returncode == 0
            except Exception:
                pass

            if gpu_ok:
                self.log_message("SYSTEM", t("מאיץ חומרה Nvidia (NVENC) זמין ופעיל."), "🚀")
            else:
                self.log_message("SYSTEM", t("מאיץ Nvidia לא זוהה - הרינדור יפעל במצב תוכנתי/CPU."), "ℹ️")

        threading.Thread(target=_check, daemon=True).start()

    def build_skeleton(self):
        accent_color = state.current_theme["accent"]

        self.sidebar_container = ctk.CTkFrame(self, fg_color="transparent")
        self.sidebar_container.grid(row=0, column=1, sticky="nsew")

        self.sidebar = SidebarComponent(self.sidebar_container, on_script_select=self.on_script_selected)
        self.sidebar.pack(fill="both", expand=True)

        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=25, pady=20)
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(3, weight=1)

        self.alert_banner = ctk.CTkFrame(self.main_container, fg_color=PALETTE["alert_banner"], corner_radius=6, height=25)
        self.lbl_alert = ctk.CTkLabel(self.alert_banner, text=t("⚠️ אזהרה: ניצולת מעבד/זיכרון גבוהה במיוחד!"), font=FONT_BADGE, text_color=PALETTE["white"])
        self.lbl_alert.pack(pady=2)

        self.header_card = ctk.CTkFrame(self.main_container, fg_color=PALETTE["surface"], corner_radius=12, border_width=1, border_color=accent_color)
        self.header_card.grid(row=1, column=0, sticky="ew", pady=(0, 15))

        self.lbl_title = ctk.CTkLabel(self.header_card, text=t("נא לבחור סקריפט מהרשימה"), font=FONT_HEBREW_TITLE, text_color=PALETTE["white"])
        self.lbl_title.pack(side="right", padx=20, pady=12)

        self.lbl_status_text = ctk.CTkLabel(self.header_card, text=t("מערכת בהמתנה"), font=FONT_HEBREW_TEXT, text_color=PALETTE["text_muted"])
        self.lbl_status_text.pack(side="left", padx=(10, 5), pady=12)
        
        self.lbl_led = ctk.CTkLabel(self.header_card, text="●", font=("Segoe UI", 18), text_color=PALETTE["led_off"])
        self.lbl_led.pack(side="left", padx=5, pady=12)

        self.btn_pin = ctk.CTkButton(
            self.header_card, text="📌", font=FONT_HEBREW_TEXT, width=30, height=26,
            fg_color=PALETTE["border"], hover_color=accent_color, command=lambda: self.style_settings_comp.toggle_always_on_top()
        )
        self.btn_pin.pack(side="left", padx=3)

        # "🔧 כלים" - תפריט נפתח קטן במקום שני כפתורים תמיד-גלויים (אבחון מערכת
        # + תצוגת גל קול) - כלים שנוגעים בהם לעיתים רחוקות, פחות רעש בכותרת.
        self.btn_tools = ctk.CTkButton(
            self.header_card, text="🔧", font=FONT_HEBREW_TEXT, width=30, height=26,
            fg_color=PALETTE["border"], hover_color=accent_color, command=self.open_tools_menu
        )
        self.btn_tools.pack(side="left", padx=3)

        self.btn_drawer = ctk.CTkButton(
            self.header_card, text="🔔", font=FONT_HEBREW_TEXT, width=30, height=26,
            fg_color=PALETTE["border"], hover_color=accent_color, command=self.toggle_notification_drawer
        )
        self.btn_drawer.pack(side="left", padx=3)

        self.btn_compact = ctk.CTkButton(
            self.header_card, text=t("📐 מצב מרוכז"), font=FONT_BADGE, width=80, height=26,
            fg_color=PALETTE["border"], hover_color=accent_color, command=self.toggle_compact_mode
        )
        self.btn_compact.pack(side="left", padx=5)

        self.drawer = NotificationDrawer(self, accent_color)

        self.stats_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.stats_panel.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for i in range(5): self.stats_panel.grid_columnconfigure(i, weight=1)

        # rtl_column: בעברית "התור" קורא מימין לשמאל, כמו שאר הממשק - ראו
        # utils/shared/rtl_layout.py. GPU ליד CPU/RAM (לא רק כפס בסיידבר) כי כל
        # הפייפליין של הפרויקט מבוסס רינדור GPU/NVENC - אם ה-GPU בעומס מלא זו
        # בדיוק העובדה שהכי חשוב לראות במבט אחד בכותרת. הסדר הלוגי עצמו (מי
        # מופיע ראשון/אחרון) ניתן לסידור אישי (item: reorderable dashboard
        # widgets) - state.get_dashboard_widget_order() קובע את סדר האינדקסים,
        # לא קבוע ידנית 0/1/2/3/4 כמו קודם.
        # 30.10.2026: בלי קונטיינר Docker מוגדר (state.docker_container) - בלי הכרטיס שלו
        widget_order = [w for w in state.get_dashboard_widget_order() if w != "docker" or state.docker_container]
        total_widgets = len(widget_order)
        widget_builders = {
            "cpu": lambda col: self.create_ring_card(self.stats_panel, "💻 CPU", col, widget_id="cpu"),
            "ram": lambda col: self.create_ring_card(self.stats_panel, "🧠 RAM", col, widget_id="ram"),
            "gpu": lambda col: self.create_ring_card(self.stats_panel, "🎮 GPU", col, widget_id="gpu"),
            "uptime": lambda col: self.create_metric_card(self.stats_panel, "⏱️ Uptime", "00:00:00", col, widget_id="uptime"),
            "docker": lambda col: self.create_metric_card(self.stats_panel, "🐳 Docker", t("לא פעיל"), col, widget_id="docker"),
        }
        built_widgets = {
            widget_id: widget_builders[widget_id](rtl_column(i, total_widgets))
            for i, widget_id in enumerate(widget_order)
        }
        self.ring_cpu_canvas = built_widgets["cpu"]
        self.ring_ram_canvas = built_widgets["ram"]
        self.ring_gpu_canvas = built_widgets["gpu"]
        self.card_uptime = built_widgets["uptime"]
        self.card_docker_st = built_widgets.get("docker")

        self.tabview = ctk.CTkTabview(
            self.main_container, 
            corner_radius=14, 
            fg_color=PALETTE["surface"], 
            border_width=1, 
            border_color=accent_color, 
            segmented_button_selected_color=accent_color
        )
        self.tabview.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        
        tab_dash = self.tabview.add(t("🎮 לוח בקרה"))
        # הגדרות לכל-סקריפט (תיקיית עבודה, תיאור, ואפשרויות ספציפיות כמו בורר
        # ה-AI של story_cutter.py) עברו לכאן - זה היה טאב נפרד ("⚙️ הגדרות"),
        # למרות שהתוכן שלו תלוי-הקשר לגמרי בסקריפט שנבחר בסיידבר, בדיוק כמו
        # כפתור ה-Run שממש לידו. מוצג למעלה (לפני dashboard_comp) כי dashboard_comp
        # תופס עם expand=True את כל השטח שנשאר - הגדרות למעלה, קונסולה/הרצה למטה.
        self.settings_comp = SettingsTabComponent(tab_dash)
        self.settings_comp.pack(fill="x", pady=(0, 10))

        self.dashboard_comp = DashboardTabComponent(tab_dash, set_led_callback=self.update_led_indicator)
        self.dashboard_comp.pack(fill="both", expand=True)

        tab_bot = self.tabview.add(t("🤖 ניהול דיסקורד"))
        self.bot_comp = BotTabComponent(tab_bot)
        self.bot_comp.pack(fill="both", expand=True)

        # טאב "⚙️ הגדרות" מאוחד - היו 3 טאבים נפרדים ("עיצוב וממשק", "הגדרות
        # גלובליות", וחלק מ"הגדרות") בלי חלוקה ברורה למשתמש. עכשיו בורר תת-מדורים
        # אחד בתוך טאב אחד - ראו ui/unified_settings_tab.py.
        tab_settings = self.tabview.add(t("⚙️ הגדרות"))
        self.unified_settings_comp = UnifiedSettingsTabComponent(tab_settings, self)
        self.unified_settings_comp.pack(fill="both", expand=True)
        self.style_settings_comp = self.unified_settings_comp.style_comp
        self.rocket_settings_comp = self.unified_settings_comp.rocket_comp
        self.global_settings_comp = self.unified_settings_comp.global_comp

        tab_sound = self.tabview.add(t("🔊 סאונדבורד"))
        self.soundboard_comp = SoundboardTabComponent(tab_sound)
        self.soundboard_comp.pack(fill="both", expand=True)

        tab_stats = self.tabview.add(t("📊 סטטיסטיקות"))
        self.stats_comp = StatsTabComponent(tab_stats)
        self.stats_comp.pack(fill="both", expand=True)

        tab_scheduler = self.tabview.add(t("⏰ תזמון"))
        self.scheduler_comp = SchedulerTabComponent(tab_scheduler)
        self.scheduler_comp.pack(fill="both", expand=True)

        tab_approvals = self.tabview.add(t("✅ אישור קליפים"))
        self.approvals_comp = ApprovalsTabComponent(tab_approvals)
        self.approvals_comp.pack(fill="both", expand=True)

        # CTkSegmentedButton (מתחת ל-CTkTabview) מסדר כרטיסיות משמאל לימין לפי
        # סדר .add() בלי שום מודעות ל-RTL - אז "לוח בקרה" (הכרטיסייה שנוספה
        # ראשונה, ולכן גם זו שנבחרת כברירת מחדל בפתיחה - .insert() ב-CTkTabview
        # בוחר אוטומטית רק את הכרטיסייה הראשונה שנוספת) הייתה תמיד יושבת הכי
        # משמאל. .move() מזיז את המיקום הוויזואלי בלבד, בלי לגעת באיזו כרטיסייה
        # פעילה - כך ש"לוח בקרה" גם יושב הכי מימין (סדר קריאה טבעי בעברית) וגם
        # נשאר הכרטיסייה שנבחרת כברירת מחדל. באנגלית משאירים את הסדר הרגיל.
        if state.language != "en":
            all_tab_names = [t("🎮 לוח בקרה"), t("🤖 ניהול דיסקורד"),
                              t("⚙️ הגדרות"), t("🔊 סאונדבורד"), t("📊 סטטיסטיקות"), t("⏰ תזמון"),
                              t("✅ אישור קליפים")]
            for i, name in enumerate(reversed(all_tab_names)):
                self.tabview.move(i, name)

        self.bottom_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.bottom_panel.grid(row=4, column=0, sticky="ew")
        self.bottom_panel.grid_columnconfigure(0, weight=1)

        self.log_card = ctk.CTkFrame(self.bottom_panel, fg_color=PALETTE["surface"], corner_radius=12, border_width=1, border_color=PALETTE["border"])
        self.log_card.grid(row=0, column=0, sticky="nsew")
        
        log_tools = ctk.CTkFrame(self.log_card, fg_color="transparent")
        log_tools.pack(fill="x", padx=15, pady=(8, 2))

        lbl_log_title = ctk.CTkLabel(log_tools, text=t("📝 מרכז לוגים מאוחד (זמן אמת)"), font=FONT_HEBREW_SUB)
        lbl_log_title.pack(side="right", padx=5)

        btn_resize_log = ctk.CTkButton(log_tools, text=t("↕️ גודל לוג"), font=FONT_BADGE, width=65, height=22, fg_color=PALETTE["border"], command=self.toggle_log_size)
        btn_resize_log.pack(side="left", padx=2)

        btn_clear = ctk.CTkButton(log_tools, text=t("🧹 ניקוי (Ctrl+L)"), font=FONT_BADGE, width=90, height=22, fg_color=PALETTE["border"], command=self.clear_log)
        btn_clear.pack(side="left", padx=2)

        # --- שיפור 3: כפתור פתיחת תיקיית תוצרים בלחיצה אחת ---
        btn_open_exports = ctk.CTkButton(log_tools, text=t("📂 פתח תיקיית תוצרים"), font=FONT_BADGE, width=130, height=22, fg_color=accent_color, command=lambda: self.rocket_settings_comp.open_export_directory())
        btn_open_exports.pack(side="left", padx=4)

        # --- שיפור 2: כפתור עצירת רינדור / Kill Switch ---
        self.btn_kill_process = ctk.CTkButton(log_tools, text=t("🛑 עצור רינדור"), font=FONT_BADGE, width=90, height=22, fg_color=PALETTE["danger"], command=self.kill_active_process)
        self.btn_kill_process.pack(side="left", padx=2)

        btn_search_log = ctk.CTkButton(log_tools, text=t("🔍 חיפוש"), font=FONT_BADGE, width=70, height=22, fg_color=PALETTE["border"], command=self.toggle_log_search)
        btn_search_log.pack(side="left", padx=2)

        self.progress_bar = ctk.CTkProgressBar(self.log_card, height=8, progress_color=accent_color)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=15, pady=(2, 6))

        # item: סינון לפי קטגוריה בלוג - שורת צ'יפים, כל אחד מפעיל/מכבה קטגוריה
        # אחת (כולם פעילים כברירת מחדל). לצד חיפוש הטקסט הקיים, לא במקומו.
        category_filter_row = ctk.CTkFrame(self.log_card, fg_color="transparent")
        category_filter_row.pack(fill="x", padx=15, pady=(0, 4))
        ctk.CTkLabel(category_filter_row, text=t("סינון:"), font=FONT_BADGE, text_color=PALETTE["text_faint"]).pack(side="right", padx=(5, 2))
        for cat in LOG_CATEGORIES:
            btn = ctk.CTkButton(category_filter_row, text=cat, font=FONT_BADGE, width=0, height=20, fg_color=accent_color, text_color=PALETTE["bg_root"])
            btn.configure(command=lambda c=cat, b=btn: self.toggle_log_category(c, b))
            btn.pack(side="right", padx=2)

        self.search_bar_frame = ctk.CTkFrame(self.log_card, fg_color="transparent")
        self.search_entry = ctk.CTkEntry(self.search_bar_frame, placeholder_text=t("חפש בלוג..."), font=FONT_HEBREW_TEXT, justify="right")
        self.search_entry.pack(side="right", fill="x", expand=True, padx=(0, 5))
        self.search_entry.bind("<KeyRelease>", self.search_log)

        self.unified_log = ctk.CTkTextbox(self.log_card, font=FONT_LOGS, height=120, fg_color=PALETTE["bg_root"], text_color=PALETTE["text_dim"])
        self.unified_log.pack(fill="both", expand=True, padx=15, pady=(0, 6))
        self.unified_log.configure(state="disabled")

        self.hotkey_bar = ctk.CTkFrame(self.log_card, fg_color="transparent")
        if self.ui_settings["shortcut_bar"]:
            self.hotkey_bar.pack(fill="x", padx=15, pady=(0, 4))
            ctk.CTkLabel(self.hotkey_bar, text=t("⌨️ קיצורים: Ctrl+K (חיפוש) | Ctrl+L (ניקוי לוג)"), font=FONT_BADGE, text_color=PALETTE["text_faint"]).pack(anchor="e")

        # "🔌 ניהול שירותי רשת" עבר לטאב "⚙️ הגדרות" (תת-מדור "כללי") - נראה
        # כמו הגדרה יותר מפעולה שוטפת, לא צריך להיות תמיד-גלוי ליד הלוג.
        # ראו ui/global_settings_tab.py.

        self.log_message("SYSTEM", t("מערכת השליטה מוכנה!"), "🟢")

    # --- שיפור 2: ביטול תהליך מורץ (Kill Process) ---
    def kill_active_process(self):
        self.play_ui_sound()
        
        # חיסול תהליכי FFmpeg במידה ורצים ברקע
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/IM", "ffmpeg.exe"], capture_output=True, creationflags=NO_WINDOW_FLAGS)
            else:
                subprocess.run(["pkill", "-f", "ffmpeg"], capture_output=True)
            self.log_message("SYSTEM", t("התקבלה הוראת ביטול: כל תהליכי הרינדור הופסקו בהצלחה!"), "🛑")
            self.progress_bar.set(0.0)
        except Exception as e:
            self.log_message("ERROR", t("שגיאה בביטול התהליך: {error}", error=e), "❌")

    # --- מגש מערכת (System Tray): סגירת החלון ממזערת במקום לסגור, כדי שהעבודה ברקע תמשיך ---
    def on_close_request(self):
        if pystray:
            self.minimize_to_tray()
        else:
            self.destroy()

    def minimize_to_tray(self):
        self.withdraw()
        self.log_message("SYSTEM", t("האפליקציה מוזערה למגש המערכת. לחץ על האייקון כדי לשחזר."), "🗕")
        if self.tray_icon is None:
            # סמל המותג (dev/generate_app_icon.py) - קבוע, לא תלוי
            # בערכת הנושא/accent הנוכחיים, בדיוק כמו אייקון שורת המשימות.
            # fallback לעיגול הישן אם הקובץ חסר מסיבה כלשהי (checkout טרי בלי
            # להריץ את מחולל האייקון) - מגש המערכת לא אמור פשוט לא לעבוד.
            if os.path.exists(APP_ICON_PNG):
                image = PILImage.open(APP_ICON_PNG)
            else:
                image = PILImage.new("RGB", (64, 64), PALETTE["bg_root"])
                draw = PILImageDraw.Draw(image)
                draw.ellipse((10, 10, 54, 54), fill=state.current_theme["accent"])
            # _fix_word_order=False: t() הופך כברירת מחדל את סדר המילים כדי
            # לפצות על באג רינדור ספציפי ל-Tk (ראו utils/shared/i18n.py) - אבל תפריט
            # מגש המערכת של pystray מוצג דרך תפריט הקונטקסט הילידי של Windows,
            # לא Tk, ולא סובל מאותו באג. הפעלת התיקון עליו הפכה את סדר המילים
            # בכיוון ההפוך (הציגה "חלון שחזר" במקום "שחזר חלון").
            menu = pystray.Menu(
                pystray.MenuItem(t("שחזר חלון", _fix_word_order=False), self.restore_from_tray, default=True),
                pystray.MenuItem(t("סגור לגמרי", _fix_word_order=False), self.quit_app_fully)
            )
            self.tray_icon = pystray.Icon("clipforge", image, "ClipForge", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def restore_from_tray(self, icon=None, item=None):
        # pystray מריץ menu items על ה-thread של אייקון המגש עצמו, לא על ה-thread
        # הראשי - ראו utils/shared/gui_thread.py.
        self._main_dispatcher.call_soon(self.deiconify)

    def quit_app_fully(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self._main_dispatcher.call_soon(self.destroy)

    # --- קיצור מקלדת גלובלי (עובד גם כשהחלון לא בפוקוס) - מריץ את הסקריפט האחרון שהורץ ---
    def register_global_hotkey(self):
        if not global_keyboard:
            return
        try:
            global_keyboard.add_hotkey("ctrl+alt+r", self.run_last_used_script)
            self.log_message("SYSTEM", t("קיצור מקלדת גלובלי פעיל: Ctrl+Alt+R מריץ את הסקריפט האחרון."), "⌨️")
        except Exception as e:
            self.log_message("SYSTEM", t("לא ניתן היה לרשום קיצור מקלדת גלובלי (ייתכן שנדרשות הרשאות מנהל): {error}", error=e), "ℹ️")

    def run_last_used_script(self):
        if not self.last_run_script_path:
            return
        self.after(0, lambda: self.on_script_selected(self.last_run_script_path))
        self.after(100, lambda: self.dashboard_comp.run_task() if self.dashboard_comp.run_btn.cget("state") == "normal" else None)

    # --- חיפוש בתוך הלוג המאוחד ---
    def toggle_log_search(self):
        self.play_ui_sound()
        if self.search_bar_frame.winfo_ismapped():
            self.search_bar_frame.pack_forget()
        else:
            self.search_bar_frame.pack(fill="x", padx=15, pady=(0, 4), before=self.unified_log)
            self.search_entry.focus_set()

    def search_log(self, event=None):
        query = self.search_entry.get()
        self.unified_log.tag_remove("search_hit", "1.0", "end")
        if not query:
            return

        self.unified_log.tag_config("search_hit", background=state.current_theme["accent"], foreground=PALETTE["bg_root"])
        start = "1.0"
        first_match = None
        while True:
            idx = self.unified_log.search(query, start, stopindex="end", nocase=True)
            if not idx:
                break
            end_idx = f"{idx}+{len(query)}c"
            self.unified_log.tag_add("search_hit", idx, end_idx)
            if first_match is None:
                first_match = idx
            start = end_idx

        if first_match:
            self.unified_log.see(first_match)

    def open_tools_menu(self):
        """תפריט "🔧 כלים" קטן - מחליף שני כפתורים תמיד-גלויים (אבחון מערכת +
        תצוגת גל קול) בכפתור אחד, כי אלה כלים שנוגעים בהם לעיתים רחוקות."""
        from tkinter import Menu
        self.play_ui_sound()
        menu = Menu(self, tearoff=0)
        menu.add_command(label=t("🩺 אבחון מערכת"), command=self.open_diagnostics_dialog)
        menu.add_command(label=t("🌊 תצוגת גל קול"), command=lambda: self.rocket_settings_comp.show_waveform_dialog())
        try:
            x = self.btn_tools.winfo_rootx()
            y = self.btn_tools.winfo_rooty() + self.btn_tools.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def open_diagnostics_dialog(self):
        """מריץ את כל הבדיקות ב-utils/shared/diagnostics.py ומציג ✅/❌ ברור לכל אחת -
        רוב הבאגים האמיתיים החודש היו כשלים שקטים שהתגלו רק אחרי לחיצה על
        הרץ; זה נועד לתפוס אותם מראש."""
        self.play_ui_sound()
        dialog = ctk.CTkToplevel(self)
        dialog.title(t("🩺 אבחון מערכת"))
        dialog.geometry("560x680")
        dialog.attributes("-topmost", True)

        lbl_status = ctk.CTkLabel(dialog, text="", font=FONT_HEBREW_TEXT)
        lbl_status.pack(pady=10)
        # בדיקת המערכת אורכת כמה שניות בלי שום אחוז התקדמות אמיתי - ספינר קטן
        # (ui/widgets.py) במקום טקסט "בודק..." קבוע, כדי שיהיה ברור שמשהו קורה בפועל.
        status_spinner = Spinner(lbl_status, t("בודק את המערכת..."))
        status_spinner.start()

        results_frame = ctk.CTkScrollableFrame(dialog)
        results_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        def _run():
            from utils.shared.diagnostics import run_diagnostics
            results = run_diagnostics()

            def _show():
                status_spinner.stop()
                if not dialog.winfo_exists():
                    return
                lbl_status.configure(text=t("הבדיקה הושלמה."))
                for name, ok, detail in results:
                    row = ctk.CTkFrame(results_frame, fg_color="transparent")
                    row.pack(fill="x", pady=3)
                    icon = "✅" if ok else "❌"
                    color = state.current_theme["accent"] if ok else PALETTE["danger"]
                    # fix_hebrew_word_order על המחרוזת המורכבת (icon+name) - name
                    # כבר עבר t() בעצמו ב-utils/shared/diagnostics.py (יכול להיות הפוך אם
                    # הוא עברית טהורה); בלי לתקן שוב כאן, הסימן (✅/❌) היה נופל
                    # בקצה הלא-נכון של המחרוזת המשולבת.
                    ctk.CTkLabel(row, text=fix_hebrew_word_order(f"{icon} {name}"), font=FONT_HEBREW_TEXT, text_color=color, anchor="e", justify="right").pack(fill="x")
                    ctk.CTkLabel(row, text=detail, font=("Consolas", 10), text_color=PALETTE["text_muted"], anchor="e", justify="right", wraplength=480).pack(fill="x")

            self._main_dispatcher.call_soon(_show)

        threading.Thread(target=_run, daemon=True).start()

        # "🔑 בדוק תוקף Credentials" (item: credential vault health-check) - כפתור
        # נפרד, לא חלק מ-_run() האוטומטי למעלה: זה שולח בקשות רשת אמיתיות
        # ל-Gemini/Twitch/Discord (utils/shared/credential_health.py's check_validity()),
        # אז חייב להיות על-פי-בקשה מפורשת - לא לרוץ בכל פתיחת הדיאלוג.
        credentials_frame = ctk.CTkScrollableFrame(dialog, height=100)
        credentials_hint = ctk.CTkLabel(
            dialog, text=t("⚡ בודק תוקף אמיתי מול Gemini/Twitch/Discord (שולח בקשות רשת) - לא רץ אוטומטית"),
            font=("Segoe UI", 9), text_color=PALETTE["text_muted"], wraplength=520,
        )

        def _run_credential_check():
            btn_check_credentials.configure(state="disabled", text=t("בודק..."))
            from utils.shared.credential_health import check_validity
            results = check_validity()

            def _show_credentials():
                btn_check_credentials.configure(state="normal", text=t("🔑 בדוק תוקף Credentials"))
                if not dialog.winfo_exists():
                    return
                for w in credentials_frame.winfo_children():
                    w.destroy()
                for name, configured, valid, detail in results:
                    if not configured:
                        icon, color, text = "➖", PALETTE["text_muted"], t("לא מוגדר")
                    else:
                        icon = "✅" if valid else "❌"
                        color = state.current_theme["accent"] if valid else PALETTE["danger"]
                        text = detail
                    row = ctk.CTkFrame(credentials_frame, fg_color="transparent")
                    row.pack(fill="x", pady=2)
                    ctk.CTkLabel(row, text=f"{icon} {name}", font=FONT_HEBREW_TEXT, text_color=color, anchor="e", justify="right").pack(fill="x")
                    ctk.CTkLabel(row, text=text, font=("Consolas", 9), text_color=PALETTE["text_muted"], anchor="e", justify="right", wraplength=480).pack(fill="x")
                credentials_frame.pack(fill="x", padx=15, pady=(0, 4))

            self._main_dispatcher.call_soon(_show_credentials)

        btn_check_credentials = ctk.CTkButton(dialog, text=t("🔑 בדוק תוקף Credentials"), command=lambda: threading.Thread(target=_run_credential_check, daemon=True).start())
        credentials_hint.pack(padx=15, pady=(0, 4))
        btn_check_credentials.pack(padx=15, pady=(0, 8))

        # גיל מפתחות (item: key-age tracking) - utils/shared/credential_rotation.py,
        # בלי שום קריאת רשת (בניגוד לבדיקת התוקף למעלה), אז נטען מיד עם פתיחת
        # הדיאלוג, לא רק על-פי-בקשה. כל שורה כוללת שדה+כפתור לסבב בפועל.
        rotation_hint = ctk.CTkLabel(
            dialog, text=t("🔄 גיל המפתחות (מתי כל credential הוחלף לאחרונה) - בלי קריאת רשת:"),
            font=("Segoe UI", 9), text_color=PALETTE["text_muted"], wraplength=520,
        )
        rotation_frame = ctk.CTkScrollableFrame(dialog, height=160)
        rotation_hint.pack(padx=15, pady=(0, 4))
        rotation_frame.pack(fill="x", padx=15, pady=(0, 8))

        def _rotate_credential(name, entry):
            new_value = entry.get().strip()
            if not new_value:
                return

            def _do_rotate():
                from utils.shared.secrets_vault import is_vault_available, set_secret
                if not is_vault_available():
                    return
                try:
                    set_secret(name, new_value)
                except Exception as e:
                    print(f"[diagnostics] סבב {name} נכשל: {e}")
                self._main_dispatcher.call_soon(_refresh_rotation_status)

            threading.Thread(target=_do_rotate, daemon=True).start()

        def _refresh_rotation_status():
            if not dialog.winfo_exists():
                return
            from utils.shared.credential_health import get_rotation_status
            for w in rotation_frame.winfo_children():
                w.destroy()
            for name, configured, age_days, stale in get_rotation_status():
                if not configured:
                    age_text = t("לא מוגדר")
                elif age_days is None:
                    age_text = t("גיל לא ידוע (הוגדר ידנית ב-.env, לא דרך הכספת)")
                else:
                    age_text = ("⚠️ " if stale else "") + t("{days} ימים מאז הסבב האחרון", days=age_days)

                row = ctk.CTkFrame(rotation_frame, fg_color="transparent")
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(row, text=name, font=FONT_HEBREW_TEXT, anchor="e", justify="right").pack(fill="x")
                ctk.CTkLabel(
                    row, text=age_text, font=("Consolas", 9),
                    text_color=PALETTE["danger"] if stale else PALETTE["text_muted"], anchor="e", justify="right",
                ).pack(fill="x")
                entry_row = ctk.CTkFrame(row, fg_color="transparent")
                entry_row.pack(fill="x", pady=(2, 0))
                entry = ctk.CTkEntry(entry_row, placeholder_text=t("ערך חדש..."), show="•")
                entry.pack(side="right", fill="x", expand=True, padx=(5, 0))
                ctk.CTkButton(entry_row, text=t("🔄 סבב"), width=60, command=lambda n=name, e=entry: _rotate_credential(n, e)).pack(side="right")

        _refresh_rotation_status()

    def create_ring_card(self, parent, title, col, widget_id=None):
        card = ctk.CTkFrame(parent, fg_color=PALETTE["surface"], corner_radius=10, border_width=1, border_color=PALETTE["border"])
        card.grid(row=0, column=col, sticky="ew", padx=4)
        if widget_id:
            self._dashboard_widget_cards[widget_id] = card

        ctk.CTkLabel(card, text=title, font=FONT_BADGE, text_color=PALETTE["text_muted"]).pack(pady=(4, 0))
        canvas = ctk.CTkCanvas(card, width=42, height=42, bg=PALETTE["surface"], highlightthickness=0)
        canvas.pack(pady=4)
        if widget_id:
            self._add_widget_reorder_controls(card, widget_id)
        return canvas

    def _add_widget_reorder_controls(self, card, widget_id):
        """זוג חצים זעירים בתחתית כל widget בשורת הסטטיסטיקות (item:
        reorderable dashboard widgets) - במקום גרירה-ושחרור מלאה: ל-CTk/Tkinter
        אין תמיכה מובנית בגרירה בין תאי grid, וזה היה דורש מימוש drag-visuals+
        drop-zone עצמאי מלא בשביל 5 widgets קבועים בלבד - לא שווה את הסיכון/
        מורכבות ביחס לתועלת כאן. ◀/▶ הם כיוון *לוגי* קבוע (הראשון/אחרון
        ברשימה), לא כיוון חזותי - נשאר עקבי גם כש-state.language משתנה, ולא
        רק "נראה נכון" בעברית."""
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=(0, 4))
        ctk.CTkButton(
            row, text="◀", width=20, height=16, font=("Segoe UI", 9), fg_color=PALETTE["border"],
            command=lambda: self.move_dashboard_widget(widget_id, -1)
        ).pack(side="right", padx=1)
        ctk.CTkButton(
            row, text="▶", width=20, height=16, font=("Segoe UI", 9), fg_color=PALETTE["border"],
            command=lambda: self.move_dashboard_widget(widget_id, 1)
        ).pack(side="right", padx=1)

    def move_dashboard_widget(self, widget_id, direction):
        self.play_ui_sound()
        order = state.get_dashboard_widget_order()
        idx = order.index(widget_id)
        new_idx = max(0, min(len(order) - 1, idx + direction))
        if new_idx == idx:
            return
        order[idx], order[new_idx] = order[new_idx], order[idx]
        state.dashboard_widget_order_csv = ",".join(order)
        state.save_config()
        self._relayout_dashboard_widgets()

    def _relayout_dashboard_widgets(self):
        order = state.get_dashboard_widget_order()
        total = len(order)
        for i, widget_id in enumerate(order):
            card = self._dashboard_widget_cards.get(widget_id)
            if card is not None:
                card.grid(row=0, column=rtl_column(i, total))

    def draw_ring(self, canvas, percent):
        try:
            if not canvas.winfo_exists():
                return
            canvas.delete("all")
            accent = state.current_theme["accent"]
            canvas.configure(bg=PALETTE["surface"])
            canvas.create_arc(4, 4, 38, 38, start=90, extent=-360, outline=PALETTE["border"], width=4)
            extent = -(percent / 100.0) * 360
            canvas.create_arc(4, 4, 38, 38, start=90, extent=extent, outline=accent, width=4)
            canvas.create_text(21, 21, text=f"{int(percent)}%", fill=PALETTE["white"], font=(FONT_FAMILY, 8, "bold"))
        except Exception:
            pass

    def create_metric_card(self, parent, title, default_val, col, widget_id=None):
        card = ctk.CTkFrame(parent, fg_color=PALETTE["surface"], corner_radius=10, border_width=1, border_color=PALETTE["border"])
        card.grid(row=0, column=col, sticky="ew", padx=4)
        if widget_id:
            self._dashboard_widget_cards[widget_id] = card
        ctk.CTkLabel(card, text=title, font=FONT_BADGE, text_color=PALETTE["text_muted"]).pack(pady=(4, 0))
        lbl_v = ctk.CTkLabel(card, text=default_val, font=FONT_HEBREW_SUB, text_color=state.current_theme["accent"])
        lbl_v.pack(pady=(0, 4))
        if widget_id:
            self._add_widget_reorder_controls(card, widget_id)
        return lbl_v

    def log_message(self, category, message, prefix="ℹ️"):
        def _append():
            try:
                if not hasattr(self, "unified_log") or not self.unified_log.winfo_exists():
                    return

                self.unified_log.configure(state="normal")
                color_tag = "standard"
                
                if category in ["ERROR", "STDERR"]:
                    color_tag = "red"
                    self.unified_log.tag_config("red", text_color=PALETTE["danger"])
                elif category == "AUTOMATION":
                    color_tag = "blue"
                    self.unified_log.tag_config("blue", text_color="#39f")

                if self.ui_settings["syntax_highlight"]:
                    # בודק גם את המרקר האנגלי (הודעות שנוצרות ב-GUI, עם t()) וגם
                    # את העברי (פלט של my_scripts/*.py - אלה תמיד ידפיסו בעברית,
                    # לא משנה איזו שפה נבחרה בממשק, כי לא תורגמו במסגרת הזו)
                    if "SUCCESS" in message or "בהצלחה" in message or "successfully" in message.lower():
                        color_tag = "green"
                        self.unified_log.tag_config("green", text_color=PALETTE["console_text"])

                # עדכון Progress Bar דינמי
                pct_match = re.search(r"(\d+)%\|", message)
                if pct_match:
                    try:
                        val = float(pct_match.group(1)) / 100.0
                        self.progress_bar.set(val)
                    except Exception:
                        pass
                elif "הסתיים בהצלחה" in message or "completed successfully" in message:
                    self.progress_bar.set(1.0)
                    # עדכון שדה המונה ב-UI בסיום מוצלח - getattr כי log_message
                    # יכול להיקרא לפני ש-rocket_settings_comp נבנה בכלל
                    rocket_comp = getattr(self, "rocket_settings_comp", None)
                    if rocket_comp is not None:
                        rocket_comp.counter_var.set(str(rocket_comp.get_current_counter()))

                formatted_line = f"[{prefix} {category}] -> {message}\n"
                # item: סינון לפי קטגוריה - נשמר בהיסטוריה המלאה תמיד (גם
                # קטגוריה שכרגע מוסתרת), כדי שסימון-מחדש של הקטגוריה יחשוף
                # שוב שורות ישנות, לא רק חדשות מכאן ואילך.
                self._log_history.append((category, formatted_line, color_tag))
                if category in self._log_visible_categories:
                    self.unified_log.insert("end", formatted_line, color_tag)
                    if self.auto_scroll_enabled:
                        self.unified_log.see("end")
                self.unified_log.configure(state="disabled")

                if hasattr(self, "drawer") and self.ui_settings["drawer"]:
                    self.drawer.add_notification(f"{category}: {message}")
            except Exception:
                pass

        self._main_dispatcher.call_soon(_append)

    def toggle_log_category(self, category, button):
        """מפעיל/מכבה תצוגת קטגוריה בלוג המאוחד (item: סינון לפי קטגוריה) -
        בונה-מחדש את כל התצוגה מ-self._log_history, כדי שגם שורות ישנות
        (שנכתבו לפני השינוי) יופיעו/ייעלמו בהתאם, לא רק שורות חדשות."""
        self.play_ui_sound()
        if category in self._log_visible_categories:
            self._log_visible_categories.discard(category)
            button.configure(fg_color=PALETTE["border"], text_color=PALETTE["text_faint"])
        else:
            self._log_visible_categories.add(category)
            button.configure(fg_color=state.current_theme["accent"], text_color=PALETTE["bg_root"])

        self.unified_log.configure(state="normal")
        self.unified_log.delete("1.0", "end")
        for hist_category, formatted_line, color_tag in self._log_history:
            if hist_category in self._log_visible_categories:
                self.unified_log.insert("end", formatted_line, color_tag)
        if self.auto_scroll_enabled:
            self.unified_log.see("end")
        self.unified_log.configure(state="disabled")

    def clear_log(self):
        try:
            self.play_ui_sound()
            self.unified_log.configure(state="normal")
            self.unified_log.delete("1.0", "end")
            self.unified_log.configure(state="disabled")
            self.progress_bar.set(0.0)
            self._log_history.clear()
        except Exception:
            pass

    def toggle_log_size(self):
        self.play_ui_sound()
        self.log_expanded = not self.log_expanded
        self.unified_log.configure(height=240 if self.log_expanded else 120)

    def toggle_notification_drawer(self):
        if not self.ui_settings["drawer"]: return
        self.play_ui_sound()
        self.drawer_visible = not self.drawer_visible
        if self.drawer_visible:
            self.drawer.place(relx=0.01, rely=0.08, relheight=0.8, anchor="nw")
        else:
            self.drawer.place_forget()

    def open_command_palette(self):
        if not self.ui_settings["palette"]: return
        self.play_ui_sound()
        scripts = getattr(self.sidebar, "all_scripts", [])
        CommandPalette(self, scripts, self.on_script_selected)

    def toggle_compact_mode(self):
        self.play_ui_sound()
        self.is_compact = not self.is_compact
        if self.is_compact:
            self.tabview.grid_remove()
            self.stats_panel.grid_remove()
            self.geometry("900x480")
            self.btn_compact.configure(text=t("📖 מורחב"))
        else:
            self.stats_panel.grid()
            self.tabview.grid()
            self.geometry("1300x980")
            self.btn_compact.configure(text=t("📐 מרוכז"))

    def toggle_docker_service(self):
        container = state.docker_container
        if not container or self.global_settings_comp.switch_docker is None:
            return
        state_active = self.global_settings_comp.switch_docker.get()
        self.play_ui_sound()
        if state_active:
            self.log_message("SYSTEM", t("מתבצע ניסיון אימות מול קונטיינרים של Docker ברשת..."), "🐳")
            def _docker():
                try:
                    res = subprocess.run(["docker", "start", container], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW_FLAGS)
                    if res.returncode == 0:
                        self.log_message("DOCKER", t("שרת Docker הופעל בהצלחה!"), "✅")
                        # לא self.card_docker_st.configure(...) ישירות - זה thread רקע,
                        # ראו utils/shared/gui_thread.py.
                        if self.card_docker_st is not None:
                            self._main_dispatcher.call_soon(self.card_docker_st.configure, text=t("פעיל"))
                except Exception as e:
                    self.log_message("ERROR", t("שגיאה בהפעלת Docker: {error}", error=e), "⚠️")
            threading.Thread(target=_docker, daemon=True).start()
        else:
            self.log_message("SYSTEM", t("התקבלה הוראת ניתוק משירותי Docker."), "⚠️")
            if self.card_docker_st is not None:
                self.card_docker_st.configure(text=t("לא פעיל"))

    def sync_with_bot_tab(self):
        self.play_ui_sound()
        self.bot_comp.toggle_bot()
        bot_running = self.bot_comp.is_running
        self.global_settings_comp.switch_bot_status.select() if bot_running else self.global_settings_comp.switch_bot_status.deselect()
        self.log_message("DISCORD", t("סטטוס הבוט שונה מהתפריט המהיר ל: {state}.", state=t("פעיל") if bot_running else t("כבוי")), "🤖")

    def on_script_selected(self, path):
        state.selected_script = path
        self.last_run_script_path = path
        metadata = get_script_metadata(path)
        script_name = metadata["name"]
        filename = os.path.basename(path)
        self.lbl_title.configure(text=t("סקריפט: {name} ({filename})", name=script_name, filename=filename))
        self.dashboard_comp.info_label.configure(text=t("> נבחר להרצה: {name}.", name=script_name))
        self.dashboard_comp.run_btn.configure(state="normal")
        self.settings_comp.update_script_context(script_name, metadata["description"], filename)
        self.log_message("AUTOMATION", t("נבחר סקריפט חדש בממשק: {name}", name=script_name), "📁")
        # מסונכרן גם מ-Command Palette/קיצור "הרץ שוב" (שני אלה קוראים לפונקציה
        # הזו ישירות, בלי לעבור דרך SidebarComponent._select_script) - ראו את
        # ההסבר המלא ב-SidebarComponent.refresh_selection_highlight.
        self.sidebar.refresh_selection_highlight()

    def on_global_file_dropped(self, event):
        """גרירה לכל מקום בחלון (לא רק לתוך שדה תיקייה ספציפי) - מנתבת לפי הטאב
        הפעיל כרגע. לפני התיקון הזה תמיד ניתב ל-settings_comp (טאב 'לוח בקרה')
        בלי קשר לאיזה טאב היה פתוח בפועל - גרירה בזמן שטאב אחר (Rocket Shorts,
        Bot, Soundboard וכו') פתוח הייתה מעדכנת בשקט שדה תיקייה בלתי-נראה
        במסך, בלי שום משוב חזותי שמשהו בכלל קרה. עכשיו: 'Rocket Shorts' (תת-מדור
        בטאב '⚙️ הגדרות') מקבל את הגרירה בעצמו, 'לוח בקרה' ממשיך כמו קודם,
        ושאר הטאבים (בלי שדה תיקייה גלוי כרגע) פשוט מתעלמים מהגרירה."""
        active_tab = self.tabview.get()
        if active_tab == t("⚙️ הגדרות"):
            if self.unified_settings_comp.get_active_section_key() == "rocket":
                self.rocket_settings_comp.on_folder_dropped(event)
            return
        if active_tab == t("🎮 לוח בקרה") and hasattr(self, "settings_comp"):
            self.settings_comp.on_folder_dropped(event)

    def update_led_indicator(self, color, text):
        self.lbl_led.configure(text_color=color)
        self.lbl_status_text.configure(text=text)
        self.log_message("SYSTEM", t("סטטוס מערכת עודכן: {text}", text=text), "●")

    def apply_theme_change(self, theme_name):
        state.current_theme_name = theme_name
        color = state.current_theme["accent"]
        hover_color = state.current_theme["accent_hover"]
        self.tabview.configure(border_color=color, segmented_button_selected_color=color)
        self.header_card.configure(border_color=color)
        self.sidebar.update_accent(color)
        self.dashboard_comp.run_btn.configure(fg_color=color)
        self.progress_bar.configure(progress_color=color)
        self.unified_settings_comp.update_accent(color, hover_color)
        state.save_config()
        self.log_message("SYSTEM", t("צבעי הממשק עודכנו אוטומטית לפי פרופיל: {name}", name=theme_name), "🎨")

    def start_loops(self):
        def update_stats():
            if not self.winfo_exists():
                return
            try:
                if psutil:
                    cpu = psutil.cpu_percent()
                    ram = psutil.virtual_memory().percent
                    if self.ui_settings["rings"]:
                        self.draw_ring(self.ring_cpu_canvas, cpu)
                        self.draw_ring(self.ring_ram_canvas, ram)
                        gpu_util, _gpu_vram_pct, _gpu_encoder_pct = get_gpu_stats()
                        # gpu_util is None כשאין GPU של NVIDIA/nvidia-smi לא נמצא -
                        # מציגים 0 (טבעת ריקה) במקום לקרוס/להשמיט את הכרטיס לגמרי.
                        self.draw_ring(self.ring_gpu_canvas, gpu_util if gpu_util is not None else 0)

                    if self.ui_settings["cpu_alerts"] and (cpu > 85 or ram > 90):
                        self.alert_banner.grid(row=0, column=0, sticky="ew", pady=(0, 5))
                    else:
                        self.alert_banner.grid_forget()

                uptime_sec = int(time.time() - self.start_time)
                uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_sec))
                self.card_uptime.configure(text=uptime_str)
            except Exception:
                pass

            if self.winfo_exists():
                self.after(2000, update_stats)

        GAME_LOOP_INTERVAL_SECONDS = 5

        def game_loop():
            if not self.winfo_exists():
                return
            try:
                det = check_active_game(state.turbo_mode_active)
                if det and det != state.current_theme_name:
                    self.after(0, lambda: self.apply_theme_change(det))
                elif not det and getattr(self.sidebar, "all_scripts", None):
                    restore_background_processes()
                # item: personal stats dashboard's "hours played per game" -
                # אותו tick בדיוק שכבר קורה כאן כל GAME_LOOP_INTERVAL_SECONDS
                # שניות, בלי עוד לולאת polling נפרדת.
                if det:
                    record_playtime_tick(det, GAME_LOOP_INTERVAL_SECONDS)
            except Exception:
                pass

            if self.winfo_exists():
                self.after(GAME_LOOP_INTERVAL_SECONDS * 1000, game_loop)

        def scheduler_loop():
            if not self.winfo_exists():
                return
            try:
                for task in check_and_run_due_tasks(worker):
                    self.log_message("SYSTEM", t("⏰ הרצה מתוזמנת התחילה: {name}", name=os.path.basename(task["script_path"])), "⏰")
                maybe_send_weekly_digest()
            except Exception as e:
                self.log_message("ERROR", t("שגיאה בבדיקת משימות מתוזמנות: {error}", error=e), "⏰")

            if self.winfo_exists():
                self.after(60000, scheduler_loop)

        update_stats()
        game_loop()
        scheduler_loop()


if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()