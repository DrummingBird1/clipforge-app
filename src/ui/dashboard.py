# ui/dashboard.py
import collections
import customtkinter as ctk
import os
import queue
import random
import threading
import time
from datetime import datetime
from utils.shared.workspace_dir import WORKSPACE_DIR  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.state import state, PALETTE
from utils.video.video_editor import WATERMARK_POSITIONS, parse_fps_value, validate_output_template
from utils.shared.worker import worker
from utils.shared.gui_thread import MainThreadDispatcher
from utils.shared.sound import play_system_sound
from utils.bot.seo_generator import get_confetti_particles
from utils.shared.notifications import send_webhook_notification, send_toast_notification
from utils.shared.script_metadata import get_script_metadata
from utils.shared.render_lock import get_status as get_render_lock_status
from utils.shared.health_status import format_duration
from utils.shared import job_history
from utils.shared.i18n import t

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHUTDOWN_COUNTDOWN_SECONDS = 60

# item: log spam - ריצה ארוכה (רינדור ffmpeg על תיקייה שלמה) יכולה להזרים
# אלפי שורות קונסולה; בלי תקרה הן נשארות בטקסטבוקס לצמיתות וממשיכות לתפוס
# זיכרון/רינדור גם אחרי שהן כבר לא רלוונטיות. שני תנאים משלימים - מה שמוחק
# יותר קובע: חלון-זמן (30 דקות אחורה) לריצה רגילה, ותקרת-מספר-שורות כרשת
# ביטחון נגד התקפה של הרבה שורות אמיתיות (לא רק tqdm) בפרק זמן קצר. ההיסטוריה
# המלאה תמיד נשארת ב-data/logs/script_runs.log (ראו utils/shared/worker.py) - זו רק
# תקרה על מה שמוצג *כרגע* בקונסולה החיה.
CONSOLE_LOG_RETENTION_SECONDS = 30 * 60
CONSOLE_LOG_MAX_LINES = 4000

# item: log spam - זו לא תקרה על *סך* מה שמוצג (זה כבר CONSOLE_LOG_MAX_LINES
# למעלה) אלא על כמות העבודה שמותר ל-tick בודד (50ms, ראו _poll_logs) לעשות.
# בלי זה, כל סקריפט שמדפיס פרץ גדול של שורות *אמיתיות* בין tick ל-tick
# (למשל אלפי "[SKIP] קובץ קיים כבר" ברצף מהיר על ספריית-וידאו ענקית - לא
# רק עדכוני tqdm, שכבר סוננו למעלה) היה גורם ל-_poll_logs בודד לבצע אלפי
# קריאות Tkinter נפרדות ולתקוע את ה-GUI thread. העודף פשוט ממתין בתור
# ומתנקז ב-ticks הבאים - שום דבר לא הולך לאיבוד, רק נפרש על פני זמן; ההיסטוריה
# המלאה ממילא כבר נכתבה ל-script_runs.log ברגע שנוצרה, בלי קשר לקצב הניקוז כאן.
MAX_CONSOLE_LINES_PER_TICK = 300

class DashboardTabComponent(ctk.CTkFrame):
    def __init__(self, parent, set_led_callback):
        super().__init__(parent, fg_color="transparent")
        self.set_led = set_led_callback
        self.confetti_count = 0
        self.task_start_time = None
        self.task_script_name = None
        self._toast_milestones_enabled = False
        self._toast_50pct_fired = False
        # אנימציית מילוי חלקה לפס ההתקדמות (ראו _poll_logs) - קודם progress_bar.set()
        # היה קופץ מיידית לכל ערך חדש שמגיע מ-worker.progress_queue, מה שהרגיש
        # "מקוטע" בהשוואה למד-בר עם מעבר רציף.
        self._progress_target = 0.0
        self._progress_displayed = 0.0
        self._finished_queue = queue.Queue()
        # item: log spam - זמן (monotonic) של כל שורה שכבר הוכנסה לקונסולה,
        # בסדר הכנסה (=סדר עולה) - ראו _prune_console.
        self._console_line_times = collections.deque()
        # ראו utils/shared/gui_thread.py - _run_backup_mirror() מריץ גיבוי ב-thread רקע
        # ומעדכן widget בסיום; self.after() ישיר מ-thread כזה לא מובטח בטוח.
        self._dispatcher = MainThreadDispatcher()

        # שרשור סקריפטים (item 15) - רשימה מסודרת שנבנית ב-open_pipeline_dialog
        # ורצה ברצף (כל שלב רק אחרי שהקודם הצליח, על אותה תיקיית עבודה) דרך
        # run_pipeline/on_task_finished. נשמר על ה-instance (לא state.py הגלובלי)
        # כי זה state זמני של "מה עוד נשאר להריץ", לא הגדרה שצריכה להישרד restart.
        self.pipeline_scripts = []
        self.pipeline_running = False
        self.pipeline_index = 0
        self._build_tab()
        self._poll_logs()
        self._poll_render_lock()

    def _build_tab(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        # שורה 4 (רק גובה קבוע, לא weight) - ראו mini_history_frame למטה

        self.info_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=PALETTE["surface_deep"], height=80, border_color=PALETTE["border_dim"], border_width=1)
        self.info_frame.grid(row=0, column=0, sticky="ew", pady=(10, 15), padx=15)
        self.info_label = ctk.CTkLabel(self.info_frame, text=t("> מערכת מודולרית מוכנה לפעולה. בחר סקריפט."), font=("Consolas", 11), text_color=PALETTE["text_muted"], justify="right")
        self.info_label.pack(fill="both", expand=True, padx=15, pady=10)

        self.controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_frame.grid(row=1, column=0, sticky="ew", pady=5, padx=15)

        self.run_btn = ctk.CTkButton(self.controls_frame, text=t("▶ הרץ סקריפט"), font=("Segoe UI", 13, "bold"), fg_color=state.current_theme["accent"], state="disabled", command=self.run_task)
        self.run_btn.pack(side="right", padx=5)

        self.stop_btn = ctk.CTkButton(self.controls_frame, text=t("🛑 עצור"), font=("Segoe UI", 13, "bold"), fg_color=PALETTE["stop_btn"], state="disabled", command=worker.terminate_current)
        self.stop_btn.pack(side="right", padx=5)

        # השהיה/המשך (item: Pause) - מקפיא את התהליך הרץ (psutil.suspend, לא
        # עוצר) כדי לפנות CPU/GPU זמנית בלי לאבד התקדמות; resume ממשיך מדויק
        # מאיפה שנעצר. אותו מחזור-חיים בדיוק כמו stop_btn (מופעל/מכובה יחד).
        self.pause_btn = ctk.CTkButton(self.controls_frame, text=t("⏸️ השהה"), font=("Segoe UI", 13, "bold"), fg_color=PALETTE["queued"], state="disabled", command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=5)

        self.pipeline_btn = ctk.CTkButton(self.controls_frame, text=t("🔗 פייפליין"), font=("Segoe UI", 12), fg_color=PALETTE["border"], command=self.open_pipeline_dialog)
        self.pipeline_btn.pack(side="right", padx=5)

        # חיפוש בקונסולה (item 18) - אותו UX בדיוק כמו "🔍 חיפוש" של הלוג המאוחד
        # ב-gui_manager.pyw (search_bar_frame/search_log), רק על self.console
        # (פלט הסקריפט הנוכחי) במקום unified_log (stdout/stderr גלובלי).
        self.console_search_btn = ctk.CTkButton(self.controls_frame, text="🔍", width=32, font=("Segoe UI", 12), fg_color=PALETTE["border"], command=self.toggle_console_search)
        self.console_search_btn.pack(side="right", padx=5)

        self.queue_label = ctk.CTkLabel(self.controls_frame, text="", font=("Segoe UI", 11), text_color=PALETTE["text_muted"])
        self.queue_label.pack(side="left", padx=5)

        # מנעול הרינדור החוצה-תהליכים (utils/shared/render_lock.py) כבר גלוי ב-/status
        # ו-web_app.py - חסר היה אינדיקטור קבוע כאן ב-GUI השולחני עצמו, שהוא
        # בפועל אחד משני הצדדים שיכולים להיתקע ממתין לו.
        self.render_lock_label = ctk.CTkLabel(self.controls_frame, text="", font=("Segoe UI", 11), text_color=PALETTE["queued"])
        self.render_lock_label.pack(side="left", padx=5)

        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5), padx=15)
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, progress_color=state.current_theme["accent"], fg_color=PALETTE["border"], height=8)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.progress_bar.set(0)

        self.progress_pct_label = ctk.CTkLabel(self.progress_frame, text="", font=("Consolas", 11), text_color=PALETTE["text_muted"], width=40)
        self.progress_pct_label.grid(row=0, column=1)

        # console_container עוטף את שורת החיפוש (מוסתרת כברירת מחדל, ראו
        # toggle_console_search) + הקונסולה עצמה - שתיהן packed בתוך אותו
        # container (לא grid) כי לא ניתן לערבב pack/grid על ילדי אותו parent.
        self.console_container = ctk.CTkFrame(self, fg_color="transparent")
        self.console_container.grid(row=3, column=0, sticky="nsew", pady=(10, 5), padx=15)

        self.console_search_bar = ctk.CTkFrame(self.console_container, fg_color="transparent")
        self.console_search_entry = ctk.CTkEntry(self.console_search_bar, placeholder_text=t("🔍 חפש בקונסולה..."), font=("Consolas", 11), justify="right")
        self.console_search_entry.pack(side="right", fill="x", expand=True)
        self.console_search_entry.bind("<KeyRelease>", self.search_console_log)
        # לא packed כרגע בכוונה - שורת החיפוש מוצגת/מוסתרת רק ע"י toggle_console_search

        self.console = ctk.CTkTextbox(self.console_container, font=("Consolas", 11, "bold"), fg_color=PALETTE["surface_console"], text_color=PALETTE["console_text"], border_color=PALETTE["border_console"], border_width=1, state="disabled")
        self.console.pack(fill="both", expand=True)

        # רצועת "ריצות אחרונות" קומפקטית - כדי לראות אם ריצה קודמת הצליחה/נכשלה
        # בלי לעזוב את טאב הדשבורד (ההיסטוריה המלאה, עם גלריה וייצוא, נשארת
        # בטאב הסטטיסטיקה - ui/stats_tab.py; זו רק תזכורת מהירה תוך כדי עבודה).
        self.mini_history_frame = ctk.CTkFrame(self, fg_color=PALETTE["surface_deep"], corner_radius=8, border_color=PALETTE["border_dim"], border_width=1)
        self.mini_history_frame.grid(row=4, column=0, sticky="ew", pady=(0, 15), padx=15)
        self.mini_history_label = ctk.CTkLabel(
            self.mini_history_frame, text="", font=("Consolas", 10), text_color=PALETTE["text_muted"],
            anchor="e", justify="right", wraplength=600
        )
        self.mini_history_label.pack(fill="x", padx=10, pady=6)
        self._refresh_mini_history()

    def _refresh_mini_history(self):
        rows = job_history.get_recent_jobs(limit=5)
        if not rows:
            self.mini_history_label.configure(text=t("📜 עוד לא בוצעו ריצות."))
            return
        parts = [f"{'✅' if status == 'success' else '❌'} {script_name}" for script_name, status, _started_at, _duration, _result in rows]
        self.mini_history_label.configure(text=t("📜 ריצות אחרונות: ") + "  ·  ".join(parts))

    def _build_extra_args(self, script_path):
        """דגלים ספציפיים-לסקריפט - זהה בעיקרון ל-web_app.py, ראו ההסבר המלא
        ב-worker.add_script_task למה זה חייב להישאר ספציפי-לסקריפט ולא דגל
        גורף לכולם. מופרד מ-_start_script_task כדי ש-run_pipeline_step יוכל
        לבנות את הדגלים הנכונים לכל שלב בפייפליין, לא רק לסקריפט שנבחר בסיידבר."""
        extra_args = []
        basename = os.path.basename(script_path)
        if basename == "story_cutter.py":
            extra_args = ["--ai-provider", state.story_cutter_ai_provider]
        elif basename == "video_editor.py":
            extra_args = ["--codec", state.video_editor_codec]
            if state.video_editor_fps:
                try:
                    parse_fps_value(state.video_editor_fps)
                    extra_args += ["--fps", state.video_editor_fps]
                except ValueError:
                    pass  # קלט לא תקין - מתעלם בשקט, בדיוק כמו web_app.py's _build_extra_args
            if state.video_editor_watermark_path:
                extra_args += [
                    "--watermark_path", state.video_editor_watermark_path,
                    "--watermark_position", state.video_editor_watermark_position,
                ]
                try:
                    opacity = max(0.0, min(1.0, float(state.video_editor_watermark_opacity)))
                except ValueError:
                    opacity = 1.0
                if opacity < 1.0:
                    extra_args += ["--watermark_opacity", str(opacity)]
                try:
                    scale = float(state.video_editor_watermark_scale)
                    if scale > 0 and abs(scale - 0.15) >= 0.0001:
                        extra_args += ["--watermark_scale", str(scale)]
                except ValueError:
                    pass
                # item: גרירת watermark חופשית - שני השדות ביחד, אחרת מתעלם
                # משניהם (video_editor.py עצמו כבר נופל בחזרה ל--watermark_position
                # במקרה הזה, ראו שם - אין צורך לכפול את הבדיקה כאן, רק לא
                # לשלוח קלט חלקי בכוונה).
                try:
                    wm_x = float(state.video_editor_watermark_x)
                    wm_y = float(state.video_editor_watermark_y)
                    extra_args += ["--watermark_x", str(wm_x), "--watermark_y", str(wm_y)]
                except ValueError:
                    pass
            if state.video_editor_remove_watermark_position in WATERMARK_POSITIONS:
                extra_args += ["--remove_watermark_position", state.video_editor_remove_watermark_position]
            if state.video_editor_vertical:
                extra_args += ["--vertical"]
                if state.video_editor_smart_crop:
                    extra_args += ["--smart-crop"]
            if state.video_editor_blur_background:
                extra_args += ["--blur-background"]
            try:
                trim_start = max(0.0, float(state.video_editor_trim_start))
            except ValueError:
                trim_start = 0.0
            if trim_start > 0:
                extra_args += ["--trim-start", str(trim_start)]
            if state.video_editor_trim_duration:
                try:
                    trim_duration = max(0.0, float(state.video_editor_trim_duration))
                    extra_args += ["--trim-duration", str(trim_duration)]
                except ValueError:
                    pass
            if state.video_editor_trim_silence:
                extra_args += ["--trim-silence"]
            try:
                target_seconds = int(state.video_editor_target_seconds)
            except ValueError:
                target_seconds = 0
            if target_seconds > 0:
                extra_args += ["--target-seconds", str(target_seconds)]
            if state.video_editor_keep_audio:
                extra_args += ["--keep-audio"]
                if state.video_editor_captions:
                    extra_args += ["--captions"]
                    if state.video_editor_captions_translate:
                        extra_args += ["--captions-translate"]
                    try:
                        caption_font_size = max(1, int(state.video_editor_caption_font_size))
                    except (TypeError, ValueError):
                        caption_font_size = 16
                    extra_args += [
                        "--caption-font", state.video_editor_caption_font,
                        "--caption-font-size", str(caption_font_size),
                        "--caption-color", state.video_editor_caption_color,
                        "--caption-position", state.video_editor_caption_position,
                    ]
            if state.video_editor_loudnorm:
                extra_args += ["--loudnorm"]
                if state.video_editor_loudnorm_target:
                    try:
                        loudnorm_target = float(state.video_editor_loudnorm_target)
                        extra_args += ["--loudnorm-target", str(loudnorm_target)]
                    except ValueError:
                        pass
            if state.video_editor_denoise:
                extra_args += ["--denoise"]
            if state.video_editor_sharpen:
                extra_args += ["--sharpen"]
            if state.video_editor_thumbnail:
                extra_args += ["--thumbnail"]
            if state.video_editor_lut_path:
                extra_args += ["--lut", state.video_editor_lut_path]
            if state.video_editor_auto_levels:
                extra_args += ["--auto-levels"]
            if state.video_editor_noise_gate:
                extra_args += ["--noise-gate"]
            if state.video_editor_remove_mid_silence:
                extra_args += ["--remove-mid-silence"]
            if state.video_editor_stabilize:
                extra_args += ["--stabilize"]
            if state.video_editor_chromakey:
                extra_args += [
                    "--chromakey",
                    "--chromakey-color", state.video_editor_chromakey_color,
                    "--chromakey-bg-color", state.video_editor_chromakey_bg_color,
                ]
            if state.video_editor_preserve_resolution:
                extra_args += ["--preserve-resolution"]
            if state.video_editor_no_suffix:
                extra_args += ["--no-suffix"]
            if state.video_editor_number_videos:
                extra_args += ["--number-videos"]
                if state.video_editor_number_prefix.strip():
                    extra_args += ["--number-prefix", state.video_editor_number_prefix.strip()]
                if state.video_editor_number_start.strip():
                    try:
                        number_start = max(1, int(state.video_editor_number_start))
                        extra_args += ["--number-start", str(number_start)]
                    except ValueError:
                        pass
            try:
                parallel = max(1, int(state.video_editor_parallel))
            except ValueError:
                parallel = 1
            if parallel > 1:
                extra_args += ["--parallel", str(parallel)]
            if parallel > 1 and state.video_editor_max_concurrent_nvenc.strip():
                try:
                    max_concurrent_nvenc = max(1, int(state.video_editor_max_concurrent_nvenc))
                    extra_args += ["--max-concurrent-nvenc", str(max_concurrent_nvenc)]
                except ValueError:
                    pass
            if state.video_editor_effort != "high":
                extra_args += ["--effort", state.video_editor_effort]
            if state.video_editor_container != "mp4":
                extra_args += ["--container", state.video_editor_container]
            output_template = state.video_editor_output_template.strip()
            if output_template:
                try:
                    validate_output_template(output_template)
                    extra_args += ["--output-template", output_template]
                except ValueError:
                    pass  # placeholder לא מוכר - מתעלם בשקט, בדיוק כמו web_app.py's _build_extra_args
            if state.video_editor_validate_only:
                extra_args += ["--validate-only"]
            if state.video_editor_notify_per_file:
                extra_args += ["--notify-per-file"]
            if state.video_editor_export_report:
                extra_args += ["--export-report", state.video_editor_export_report]
        elif basename == "timelapse_maker.py":
            try:
                timelapse_target_seconds = int(state.timelapse_target_seconds)
            except ValueError:
                timelapse_target_seconds = 60
            extra_args = ["--target-seconds", str(timelapse_target_seconds)]
            if state.timelapse_keep_audio:
                extra_args += ["--keep-audio"]
        return extra_args

    def _start_script_task(self, script_path):
        """מריץ סקריפט בודד - הלוגיקה המשותפת בין כפתור 'הרץ' הרגיל לבין כל
        שלב בפייפליין (ראו run_pipeline/on_task_finished)."""
        self.info_label.configure(text=t("▶ מריץ את {name}...", name=os.path.basename(script_path)))

        # אין כאן disable ל-run_btn: סקריפטים "קלים" (# Concurrency: light) רצים
        # במאגר מקביל משלהם (utils/shared/worker.py) בדיוק כדי שאפשר יהיה להריץ אותם
        # בלי לחכות מאחורי רינדור ffmpeg כבד שכבר רץ - חסימת הכפתור כל עוד
        # *משהו* רץ הייתה מבטלת את התועלת הזו לגמרי.
        self.stop_btn.configure(state="normal")
        self.pause_btn.configure(state="normal", text=t("⏸️ השהה"))

        try:
            concurrency = get_script_metadata(script_path).get("concurrency", "heavy")

            if worker.is_running:
                self.set_led(PALETTE["queued"], t("ממתין בתור"))
            else:
                self.set_led(state.current_theme["accent"], t("ריצה פעילה ברקע"))
            self._progress_target = 0.0
            self._progress_displayed = 0.0
            self.progress_bar.set(0)
            self.progress_pct_label.configure(text="")
            play_system_sound("start")

            self.task_start_time = time.time()
            self.task_script_name = os.path.basename(script_path)

            # התראות "אבן דרך" (התחיל/50%) - רק למשימות heavy (רינדור GPU ארוך),
            # לא light - סקריפט קל שמסתיים תוך שניות לא צריך שלוש התראות רצופות
            # (התחיל/50%/הסתיים) על אותה ריצה כמעט-מיידית. השלמה (_record_and_notify)
            # ממשיכה לשלוח תמיד, גם למשימות light - זה כבר היה קיים קודם.
            self._toast_milestones_enabled = concurrency == "heavy"
            self._toast_50pct_fired = False
            if self._toast_milestones_enabled:
                send_toast_notification(f"▶️ {self.task_script_name}", t("הריצה התחילה..."))

            # worker.py קורא ל-callback ישירות מה-thread של המשימה עצמה (heavy/light),
            # לא מ-thread הראשי - קריאה ישירה ל-on_task_finished (שמעדכן widgets של
            # Tkinter) משם לא בטוחה ("main thread is not in main loop"), וגם
            # self.after() עצמו אסור לקרוא לו מ-thread שאינו הראשי. לכן רק דוחפים
            # ל-_finished_queue כאן, ו-_poll_logs (שכבר רץ מה-thread הראשי, בדיוק
            # כמו log_queue/progress_queue) הוא זה שבפועל קורא ל-on_task_finished.
            worker.add_script_task(
                script_path, state.selected_gameplay_folder,
                self._finished_queue.put,
                concurrency=concurrency,
                extra_args=self._build_extra_args(script_path),
            )
        except Exception as e:
            # בלי הבלוק הזה, כל כשל כאן (למשל בבניית שורת הפקודה) היה נבלע בשקט
            # על ידי מטפל-החריגות הכללי של Tkinter - בדיוק כמו הבאג הקודם שבו
            # לחיצה על הרצה לא נתנה שום משוב. עכשיו הוא מתגלגל לקונסולה במקום.
            if not worker.is_running:
                self.stop_btn.configure(state="disabled")
                self.pause_btn.configure(state="disabled")
            worker.log_queue.put((t("❌ שגיאה בהפעלת הסקריפט: {error}\n", error=e), "red"))
            # כשל בבניית הפקודה עוצר גם פייפליין פעיל - בלי זה, on_task_finished
            # לא היה נקרא בכלל (הריצה מעולם לא התחילה) והפייפליין היה נשאר תקוע
            # "פעיל" לצמיתות בלי שיהיה אפשר להריץ אותו מחדש.
            self.pipeline_running = False

    def toggle_pause(self):
        if worker.is_paused():
            worker.resume_current()
            self.pause_btn.configure(text=t("⏸️ השהה"))
            self.set_led(state.current_theme["accent"], t("ריצה פעילה ברקע"))
        else:
            worker.pause_current()
            self.pause_btn.configure(text=t("▶️ המשך"))
            self.set_led(PALETTE["queued"], t("מושהה"))

    def run_task(self):
        # היה גם דורש state.selected_gameplay_folder בלי קשר לסקריפט הנבחר - אם
        # שדה זה ריק, הפונקציה הייתה חוזרת מיד (return) בלי שום משוב, אפילו
        # שהתקבלה לחיצה על הכפתור. לא כל סקריפט זקוק לתיקיית גיימפליי בכלל -
        # disk_scanner.py למשל סורק כונן שלם עם ברירת מחדל משלו (D:\) ומתעלם
        # לגמרי מהתיקייה הזו, אז דרישה גורפת ממנו הייתה חוסמת אותו בלי הסבר.
        if not state.selected_script:
            return
        self._start_script_task(state.selected_script)

    def open_pipeline_dialog(self):
        """בונה/עורך את רשימת הפייפליין (סקריפטים ברצף) בחלון נפרד - זהה
        בעיקרון לדיאלוג כיבוי הלילה (_start_shutdown_countdown), CTkToplevel
        פשוט במקום מסך שלם. השינויים נשמרים ישירות על self.pipeline_scripts
        תוך כדי עריכה, כך שסגירת הדיאלוג בלי ללחוץ "הרץ" פשוט משאירה את
        הרשימה כמו שהיא לפעם הבאה שנפתח."""
        import glob
        scripts_dir = os.path.join(BASE_DIR, "my_scripts")
        all_scripts = sorted(glob.glob(os.path.join(scripts_dir, "**", "*.py"), recursive=True))

        dialog = ctk.CTkToplevel(self.winfo_toplevel())
        dialog.title(t("🔗 פייפליין - הרצת כמה סקריפטים ברצף"))
        dialog.geometry("520x560")
        dialog.attributes("-topmost", True)

        ctk.CTkLabel(
            dialog,
            text=t("בחר סקריפטים לפי הסדר הרצוי. כל שלב מתחיל רק אחרי שהקודם הצליח, על אותה תיקיית עבודה שנבחרה למעלה."),
            font=("Segoe UI", 11), wraplength=480, justify="right",
        ).pack(padx=15, pady=(15, 5), fill="x")

        picker_frame = ctk.CTkScrollableFrame(dialog, label_text=t("סקריפטים זמינים"), height=170)
        picker_frame.pack(fill="both", expand=True, padx=15, pady=5)

        order_frame = ctk.CTkScrollableFrame(dialog, label_text=t("סדר הפייפליין"), height=170)
        order_frame.pack(fill="both", expand=True, padx=15, pady=5)

        def refresh_order():
            for w in order_frame.winfo_children():
                w.destroy()
            if not self.pipeline_scripts:
                ctk.CTkLabel(order_frame, text=t("הפייפליין ריק - הוסף סקריפטים מלמעלה."), text_color=PALETTE["text_muted"]).pack(pady=5)
                return
            for i, path in enumerate(self.pipeline_scripts):
                row = ctk.CTkFrame(order_frame, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkButton(row, text="✖", width=28, fg_color=PALETTE["danger"], command=lambda idx=i: remove_step(idx)).pack(side="left", padx=5)
                ctk.CTkLabel(row, text=f"{i + 1}. {os.path.basename(path)}", anchor="e").pack(side="right", padx=5, fill="x", expand=True)

        def remove_step(idx):
            del self.pipeline_scripts[idx]
            refresh_order()

        def add_step(path):
            self.pipeline_scripts.append(path)
            refresh_order()

        for path in all_scripts:
            meta = get_script_metadata(path)
            row = ctk.CTkFrame(picker_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkButton(row, text="➕", width=28, fg_color=PALETTE["border"], command=lambda p=path: add_step(p)).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=meta["name"], anchor="e").pack(side="right", padx=5, fill="x", expand=True)

        refresh_order()

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=15, pady=(5, 15))

        def clear_all():
            self.pipeline_scripts.clear()
            refresh_order()

        def start_pipeline():
            if not self.pipeline_scripts or not state.selected_gameplay_folder:
                return
            dialog.destroy()
            self.run_pipeline()

        ctk.CTkButton(actions, text=t("🗑️ נקה הכל"), fg_color=PALETTE["border"], command=clear_all).pack(side="left", padx=5)
        ctk.CTkButton(actions, text=t("▶ הרץ פייפליין"), fg_color=state.current_theme["accent"], command=start_pipeline).pack(side="right", padx=5)

    def run_pipeline(self):
        """מתחיל להריץ את self.pipeline_scripts ברצף, החל מהשלב הראשון -
        ההמשך בפועל (שלב הבא רק אחרי שהקודם הצליח) קורה ב-on_task_finished."""
        if not self.pipeline_scripts:
            return
        self.pipeline_running = True
        self.pipeline_index = 0
        self._start_script_task(self.pipeline_scripts[0])

    def on_task_finished(self, outcome=None):
        # outcome (מ-utils/shared/worker.py) הוא dict {"returncode":.., "result":..} של
        # *המשימה הזו בלבד* - לא נקרא worker.last_returncode כי עם ריצה מקבילה
        # (מסלול "light") ייתכן שכבר התחילה/הסתיימה משימה אחרת ודרסה אותו.
        if outcome is None:
            outcome = {"returncode": worker.last_returncode, "result": None}
        success = outcome.get("returncode") == 0

        # פייפליין פעיל ממשיך לשלב הבא בלי "לחזור למצב המתנה" ביניים - בלי
        # ההבחנה הזו, ה-LED/stop_btn היו מהבהבים ל"כבוי" לרגע בין שני שלבים
        # רצופים בפייפליין, ונראים כאילו הכל נעצר גם כשעוד יש מה להריץ.
        is_last_pipeline_step = self.pipeline_running and self.pipeline_index >= len(self.pipeline_scripts) - 1
        pipeline_continues = self.pipeline_running and success and not is_last_pipeline_step

        # רק אם באמת שום דבר אחר לא רץ יותר (אולי יש עדיין משימה light/heavy
        # אחרת פעילה) - אחרת היינו "מכבים" בטעות משוב על עבודה שעדיין מתבצעת.
        if not worker.is_running and not pipeline_continues:
            self.stop_btn.configure(state="disabled")
            self.pause_btn.configure(state="disabled", text=t("⏸️ השהה"))
            self.set_led(PALETTE["led_off"], t("מערכת בהמתנה"))

        self._record_and_notify(success, outcome.get("result"))
        self._refresh_mini_history()

        if success:
            # הדלקת קונפטי בטרמינל Matrix אם הריצה הצליחה
            play_system_sound("success")
            self._trigger_confetti()
            # גיבוי אוטומטי/כיבוי לילה רק בסיום *כל* הפייפליין (או ריצה בודדת
            # רגילה, שבה pipeline_running הוא ממילא False) - לא אחרי כל שלב
            # ביניים, אחרת גיבוי/כיבוי היו קורים באמצע רצף שעדיין ממשיך לרוץ.
            if not self.pipeline_running or is_last_pipeline_step:
                if state.auto_backup_active and state.backup_folder_path:
                    self._run_backup_mirror()
        else:
            play_system_sound("error")

        if success and state.night_mode_active and (not self.pipeline_running or is_last_pipeline_step):
            self._start_shutdown_countdown()

        if pipeline_continues:
            self.pipeline_index += 1
            self._start_script_task(self.pipeline_scripts[self.pipeline_index])
        elif self.pipeline_running:
            self.pipeline_running = False
            if success:
                worker.log_queue.put((t("✅ הפייפליין הושלם בהצלחה ({n} שלבים).\n", n=len(self.pipeline_scripts)), None))
            else:
                worker.log_queue.put((t("❌ הפייפליין נעצר - שלב {step} נכשל.\n", step=self.pipeline_index + 1), "red"))

    def _run_backup_mirror(self):
        from utils.shared.backup_sync import mirror_folder

        # תיקיות התוצרים לפי כלי (19.10.2026), ותיקיות הכיוון הישנות כל עוד הן קיימות - כמו web_app._mirror_export_dirs
        from utils.shared import workspace_dir as layout
        export_dirs = [os.path.join(WORKSPACE_DIR, name) for name in layout.TOOLS + layout.ORIENTATIONS]

        def _do_mirror():
            total_copied = 0
            errors = []
            for export_dir in export_dirs:
                # לא כל אוריינטציה בהכרח נוצרה אצל המשתמש הזה (square/ למשל
                # רק אם enable_square_export מופעל) - תיקייה שלא קיימת בכלל
                # מדולגת בשקט, לא נספרת כ"גיבוי נכשל".
                if not os.path.isdir(export_dir):
                    continue
                copied, error = mirror_folder(export_dir, os.path.join(state.backup_folder_path, os.path.basename(export_dir)))
                total_copied += copied
                if error:
                    errors.append(error)

            if errors:
                self._dispatcher.call_soon(self.info_label.configure, text=t("⚠️ גיבוי אוטומטי נכשל: {error}", error="; ".join(errors)))
            elif total_copied:
                self._dispatcher.call_soon(self.info_label.configure, text=t("💾 גיבוי אוטומטי הושלם - {n} קבצים הועתקו ל-{path}", n=total_copied, path=state.backup_folder_path))

        threading.Thread(target=_do_mirror, daemon=True).start()

    def _record_and_notify(self, success, result=None):
        if not self.task_start_time or not self.task_script_name:
            return

        started_at = self.task_start_time
        finished_at = time.time()
        duration = finished_at - started_at
        status = "success" if success else "failed"

        job_history.record_job(
            self.task_script_name, status,
            datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
            datetime.fromtimestamp(finished_at).isoformat(timespec="seconds"),
            round(duration, 1), result=result
        )

        icon = "✅" if success else "❌"
        duration_str = t("{sec} שניות", sec=f"{duration:.0f}") if duration < 60 else t("{minutes} דקות", minutes=f"{duration / 60:.1f}")
        status_text = t("הסתיים בהצלחה") if success else t("נכשל")

        # result (אם הסקריפט הדפיס שורת "RESULT: {...}" - ראו utils/shared/worker.py)
        # נותן סיכום קריא במקום רק ✅/❌ גולמי, כשהוא זמין. סקריפט שלא מדפיס
        # RESULT פשוט לא יוסיף כלום כאן - לא שינוי שובר.
        summary = job_history.format_result_summary(result) if result else ""

        if state.discord_webhook_url:
            message = t("{icon} **{name}** {status} (משך ריצה: {duration})", icon=icon, name=self.task_script_name, status=status_text, duration=duration_str)
            if summary:
                message += f"\n{summary}"
            send_webhook_notification(state.discord_webhook_url, message)

        toast_body = t("{status} - משך ריצה: {duration}", status=status_text, duration=duration_str)
        if summary:
            toast_body += f"\n{summary}"
        send_toast_notification(f"{icon} {self.task_script_name}", toast_body)

        self.task_start_time = None
        self.task_script_name = None

    def _start_shutdown_countdown(self):
        """מפעיל כיבוי מתוזמן, עם חלון נראה לעין שמאפשר ביטול - במקום כיבוי שקט ב-10 שניות בלבד."""
        os.system(f"shutdown /s /t {SHUTDOWN_COUNTDOWN_SECONDS}")

        dialog = ctk.CTkToplevel(self.winfo_toplevel())
        dialog.title(t("💤 מצב לילה - כיבוי אוטומטי"))
        dialog.geometry("380x180")
        dialog.attributes("-topmost", True)

        remaining = {"seconds": SHUTDOWN_COUNTDOWN_SECONDS}

        lbl = ctk.CTkLabel(dialog, text="", font=("Segoe UI", 14, "bold"), justify="center")
        lbl.pack(pady=(25, 15), padx=15)

        def cancel_shutdown():
            os.system("shutdown /a")
            dialog.destroy()

        btn = ctk.CTkButton(dialog, text=t("🛑 בטל כיבוי"), fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"], command=cancel_shutdown)
        btn.pack(pady=5)

        def tick():
            if not dialog.winfo_exists():
                return
            if remaining["seconds"] <= 0:
                dialog.destroy()
                return
            lbl.configure(text=t("הריצה הסתיימה בהצלחה.\nהמחשב יכבה בעוד {sec} שניות.", sec=remaining["seconds"]))
            remaining["seconds"] -= 1
            dialog.after(1000, tick)

        tick()

    def _trigger_confetti(self):
        if self.confetti_count < 15:
            pt = get_confetti_particles()
            line = "".join(random.choice(pt) + " " * random.randint(1, 4) for _ in range(12)) + "\n"
            self.console.configure(state="normal")
            self.console.insert("1.0", line)
            self.console.configure(state="disabled")
            self.confetti_count += 1
            self.after(100, self._trigger_confetti)
        else:
            self.confetti_count = 0

    def toggle_console_search(self):
        # winfo_manager() (רשום/לא-רשום אצל pack) ולא winfo_ismapped() - השני
        # דורש שהחלון באמת יצויר על המסך, מה שלא קורה תחת root שהוסתר
        # (withdraw), כולל ה-Tk root המשותף שבדיקות האוטומציה משתמשות בו.
        if self.console_search_bar.winfo_manager() == "pack":
            self.console_search_bar.pack_forget()
        else:
            self.console_search_bar.pack(fill="x", pady=(0, 4), before=self.console)
            self.console_search_entry.focus_set()

    def search_console_log(self, event=None):
        """מדגיש (לא מסנן) כל התאמה בקונסולה - אותו UX בדיוק כמו search_log
        ב-gui_manager.pyw (חיפוש בלוג המאוחד). מדגיש הכל בבת אחת ומדלג לראשונה
        (see) במקום "הבא/הקודם" צעד-אחר-צעד - מספיק לקונסולת סקריפט בודד
        (בדרך כלל הרבה יותר קצרה מהלוג המאוחד שרץ לאורך כל חיי האפליקציה)."""
        query = self.console_search_entry.get()
        self.console.tag_remove("search_hit", "1.0", "end")
        if not query:
            return

        self.console.tag_config("search_hit", background=state.current_theme["accent"], foreground=PALETTE["bg_root"])
        start = "1.0"
        first_match = None
        while True:
            idx = self.console.search(query, start, stopindex="end", nocase=True)
            if not idx:
                break
            end_idx = f"{idx}+{len(query)}c"
            self.console.tag_add("search_hit", idx, end_idx)
            if first_match is None:
                first_match = idx
            start = end_idx

        if first_match:
            self.console.see(first_match)

    def _prune_console(self):
        """שומר את הקונסולה החיה בגבולות (item: log spam) - מוחק שורות ישנות
        מההתחלה כשהן חורגות מ-CONSOLE_LOG_RETENTION_SECONDS אחורה *או* כשיש
        יותר מ-CONSOLE_LOG_MAX_LINES סה"כ (המחמיר מבין השניים קובע). ההיסטוריה
        המלאה תמיד נשארת ב-data/logs/script_runs.log - זו רק תקרה על מה
        שמוצג *כרגע*, לא מחיקה של מידע."""
        cutoff = time.monotonic() - CONSOLE_LOG_RETENTION_SECONDS
        excess = len(self._console_line_times) - CONSOLE_LOG_MAX_LINES
        removed = 0
        while self._console_line_times and (self._console_line_times[0] < cutoff or removed < excess):
            self._console_line_times.popleft()
            removed += 1
        if removed:
            self.console.configure(state="normal")
            self.console.delete("1.0", f"{removed + 1}.0")
            self.console.configure(state="disabled")

    def _poll_logs(self):
        # item: log spam - כל השורות שמצטברות עד MAX_CONSOLE_LINES_PER_TICK
        # נאספות כאן ומוכנסות ב-*פעולת widget אחת* למטה, לא קריאת Tkinter
        # נפרדת לכל שורה (ראו MAX_CONSOLE_LINES_PER_TICK למעלה) - זה מה שבפועל
        # מונע קפיאה בפרץ גדול, לא רק התקרה על הכמות.
        batch = []
        try:
            while len(batch) < MAX_CONSOLE_LINES_PER_TICK:
                line, _tag = worker.log_queue.get_nowait()
                batch.append(line)
        except queue.Empty:
            pass
        if batch:
            self.console.configure(state="normal")
            self.console.insert("end", "".join(batch))
            self.console.see("end")
            self.console.configure(state="disabled")
            now = time.monotonic()
            self._console_line_times.extend(now for _ in batch)
            self._prune_console()

        try:
            latest_progress = None
            while True:
                latest_progress = worker.progress_queue.get_nowait()
        except queue.Empty:
            pass
        if latest_progress is not None:
            pct = latest_progress["pct"]
            eta_seconds = latest_progress["eta_seconds"]
            self._progress_target = pct / 100.0
            label_text = f"{pct}%"
            if eta_seconds is not None and pct < 100:
                label_text += f" · נותרו כ-{format_duration(eta_seconds)}"
            self.progress_pct_label.configure(text=label_text)

            if self._toast_milestones_enabled and not self._toast_50pct_fired and pct >= 50:
                self._toast_50pct_fired = True
                send_toast_notification(f"⏳ {self.task_script_name}", t("הגיע ל-50% מהריצה..."))

        # אנימציית מילוי הדרגתית (ease-out) לעבר היעד האחרון, במקום קפיצה מיידית -
        # רץ על כל tick (50ms, ראו after() בסוף הפונקציה) גם כשלא הגיע pct חדש,
        # כך שהמד-בר ממשיך "לזרום" חלק עד שהוא מגיע ליעד בפועל.
        if abs(self._progress_target - self._progress_displayed) > 0.0005:
            step = (self._progress_target - self._progress_displayed) * 0.3
            min_step = 0.004 if self._progress_target > self._progress_displayed else -0.004
            if abs(step) < abs(min_step):
                step = min_step
            self._progress_displayed = max(0.0, min(1.0, self._progress_displayed + step))
            if abs(self._progress_target - self._progress_displayed) < 0.004:
                self._progress_displayed = self._progress_target
            self.progress_bar.set(self._progress_displayed)

        # מפורק לפי מסלול (heavy/light) ולא רק מספר גולמי - כדי שיהיה ברור *למה*
        # סקריפט ממתין (למשל: מסלול ה-light פנוי לגמרי אבל heavy עמוס).
        counts = worker.pending_counts_by_lane()
        pending = counts["heavy"] + counts["light"]
        if pending:
            self.queue_label.configure(text=t("🗂️ {n} בתור ({light} קל, {heavy} כבד)", n=pending, light=counts["light"], heavy=counts["heavy"]))
        else:
            self.queue_label.configure(text="")

        try:
            while True:
                outcome = self._finished_queue.get_nowait()
                self.on_task_finished(outcome)
        except queue.Empty:
            pass

        self._dispatcher.drain()

        self.after(50, self._poll_logs)

    def _poll_render_lock(self):
        """כל 2 שניות (לא כל tick כמו _poll_logs - זו קריאת דיסק, לא רק תור
        בזיכרון) - אותו מנעול חוצה-תהליכים שכבר גלוי ב-/status וב-web_app.py,
        אבל עד כה בלי שום אינדיקטור קבוע כאן ב-GUI השולחני עצמו."""
        if not self.winfo_exists():
            return
        status = get_render_lock_status()
        if status is None:
            self.render_lock_label.configure(text="")
        elif status["is_stale"]:
            age_text = format_duration(status["age_seconds"]) if status["age_seconds"] is not None else "?"
            self.render_lock_label.configure(text=t("⚠️ מנעול רינדור תקוע (PID {pid}, {age})", pid=status["pid"], age=age_text))
        elif status["pid"] == os.getpid():
            # utils/shared/worker.py תופס את המנעול הזה מתוך תהליך ה-GUI עצמו (לא תוך
            # תת-תהליך נפרד) עבור כל משימה "heavy" שה-GUI מריץ - כך שה-PID השמור
            # הוא תמיד ה-PID של ה-GUI עצמו כשהוא זה שמריץ כרגע. "רינדור אחר תפוס"
            # היה מוצג בטעות בכל פעם שהמשתמש הריץ סקריפט כבד מה-GUI, גם כשלא
            # רץ שום דבר "אחר" באמת - queue_label/progress_bar כבר מראים שיש
            # משימה רצה, אין צורך להתריע כאילו תהליך חיצוני תפוס.
            self.render_lock_label.configure(text="")
        else:
            age_text = format_duration(status["age_seconds"]) if status["age_seconds"] is not None else "?"
            queue_length = status.get("queue_length", 0)
            queue_suffix = t(" · עוד {n} בתור", n=queue_length) if queue_length else ""
            self.render_lock_label.configure(text=t("🔒 רינדור אחר תפוס (PID {pid}, {age})", pid=status["pid"], age=age_text) + queue_suffix)
        self.after(2000, self._poll_render_lock)