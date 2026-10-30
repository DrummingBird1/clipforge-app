# ui/stats_tab.py
import customtkinter as ctk
import glob
import os
import threading
import tkinter as tk
import webbrowser
from PIL import Image
from utils.shared.workspace_dir import WORKSPACE_DIR  # CLIPFORGE_WORKSPACE_DIR (טסטים, שרת בדיקה) - ברירת המחדל workspace/ כמו קודם
from utils.shared.state import state, PALETTE
from utils.bot.seo_generator import generate_seo_metadata
from utils.media import game_playtime
from utils.shared import hardware_history
from utils.shared import job_history
from utils.shared import move_undo_log
from utils.bot import youtube_analytics
from utils.bot import youtube_publish_log
from utils.bot import youtube_thumbnail_log
from utils.bot import youtube_uploader
from utils.media.clip_stats import get_clips_captured_by_day
from utils.media.clip_tagger import read_cached_tags, list_all_cached_tags
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.gui_thread import MainThreadDispatcher
from utils.shared.i18n import t
from utils.media.thumbnail_candidates import generate_candidates

CLIPS_CAPTURED_HISTORY_DAYS = 30

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIPS_DIR = os.path.join(WORKSPACE_DIR, "clips")
# זהה ל-web_app.py's THUMBNAIL_CANDIDATES_DIR בדיוק (item: A/B thumbnail
# testing) - keyed by video_id, כדי ששני הצדדים יראו את אותן תמונות מועמדות
# בלי קשר לאיזה מהם בפועל העלה את הסרטון.
THUMBNAIL_CANDIDATES_DIR = os.path.join(WORKSPACE_DIR, ".cache", "thumbnail_candidates")  # = web_app
# זהה ל-web_app.py's TAGS_CACHE_DIR בדיוק - שני הצדדים קוראים מאותו מטמון
# תגיות (item: clip gallery search/filter by tag), כדי שתיוג שנעשה דרך הווב
# יהיה זמין לסינון גם בדסקטופ, בלי לשכפל.
TAGS_CACHE_DIR = os.path.join(WORKSPACE_DIR, ".tags_cache")
ALL_TAGS_LABEL = "🏷️ כל התגיות"

class StatsTabComponent(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        # export_youtube() מריץ את ההעלאה ב-thread רקע ומעדכן widgets דרך
        # progress_callback/סיום - ראו utils/shared/gui_thread.py.
        self._dispatcher = MainThreadDispatcher()
        self._build_tab()
        self.refresh_gallery()
        self.refresh_job_history()
        self._drain_dispatcher()

    def _drain_dispatcher(self):
        self._dispatcher.drain()
        if self.winfo_exists():
            self.after(50, self._drain_dispatcher)

    def _build_tab(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=3)
        self.grid_rowconfigure(1, weight=2)

        self.gallery_frame = ctk.CTkFrame(self, fg_color=PALETTE["surface_alt"])
        self.gallery_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=15)
        
        ctk.CTkLabel(self.gallery_frame, text=t("🎬 גלריית קליפים מסווגים"), font=("Segoe UI", 12, "bold")).pack(pady=5)

        # חיפוש+סינון-לפי-תגית (item: clip gallery search/filter by tag) - אותה
        # תגית מטמון בדיוק כמו web_app.py, אבל כאן לא קורא ל-AI בכלל (אין כאן
        # כפתור "תייג" - התיוג עצמו נשאר פעולה שקיימת רק בגרסת הווב); הסינון
        # פשוט משקף תגיות שכבר נוצרו שם. self._all_clips נשמר במטמון (לא glob
        # מחדש בכל הקשת מקש) כדי שהסינון יהיה מיידי.
        self._all_clips = []
        self.gallery_search_var = ctk.StringVar()
        self.gallery_search_var.trace_add("write", lambda *_: self._render_gallery())
        ctk.CTkEntry(
            self.gallery_frame, textvariable=self.gallery_search_var,
            placeholder_text=t("🔍 חפש לפי שם קליפ..."),
        ).pack(fill="x", padx=10, pady=(0, 4))

        self.gallery_tag_var = ctk.StringVar(value=t(ALL_TAGS_LABEL))
        self.gallery_tag_menu = ctk.CTkOptionMenu(
            self.gallery_frame, variable=self.gallery_tag_var,
            values=[t(ALL_TAGS_LABEL)], command=lambda _: self._render_gallery(),
        )
        self.gallery_tag_menu.pack(fill="x", padx=10, pady=(0, 6))

        self.scroll = ctk.CTkScrollableFrame(self.gallery_frame, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self.side_card = ctk.CTkFrame(self, fg_color=PALETTE["surface_stats"])
        self.side_card.grid(row=0, column=1, sticky="nsew", padx=10, pady=15)

        self.lbl_status = ctk.CTkLabel(self.side_card, text=t("בחר סרטון מהגלריה ליצוא"), font=("Segoe UI", 12))
        self.lbl_status.pack(pady=15)
        
        self.btn_tiktok = ctk.CTkButton(self.side_card, text="🎵 TikTok Export Pro", state="disabled", command=lambda: self.export_wizard("https://www.tiktok.com/tiktokstudio/upload"))
        self.btn_tiktok.pack(pady=5, padx=15, fill="x")
        
        self.btn_yt = ctk.CTkButton(self.side_card, text="📺 YouTube Export Pro", state="disabled", command=self.export_youtube)
        self.btn_yt.pack(pady=5, padx=15, fill="x")

        yt_hint = t("🔗 העלאה אוטומטית פעילה") if youtube_uploader.is_configured() else t("🔗 פותח דפדפן (הגדר client_secret.json להעלאה אוטומטית)")
        ctk.CTkLabel(self.side_card, text=yt_hint, font=("Segoe UI", 9), text_color=PALETTE["text_muted"]).pack(pady=(0, 10))

        # --- אנליטיקס YouTube (item: YouTube Analytics feedback loop) - "רענן"
        # ידני בלבד (לא אוטומטי) כדי לא לצרוך quota בלי בקשה; פעם ראשונה עשויה
        # לפתוח דפדפן לאישור הרשאה נוספת (youtube.readonly) אם עדיין לא ניתנה.
        yt_analytics_header = ctk.CTkFrame(self.side_card, fg_color="transparent")
        yt_analytics_header.pack(fill="x", padx=15, pady=(6, 2))
        ctk.CTkLabel(yt_analytics_header, text=t("📈 אנליטיקס YouTube"), font=("Segoe UI", 11, "bold")).pack(side="right")
        self.yt_analytics_refresh_btn = ctk.CTkButton(
            yt_analytics_header, text="🔄", width=28, height=24, fg_color=PALETTE["border"],
            command=self.refresh_youtube_analytics,
        )
        self.yt_analytics_refresh_btn.pack(side="left")

        self.yt_analytics_scroll = ctk.CTkScrollableFrame(self.side_card, fg_color="transparent", height=90)
        self.yt_analytics_scroll.pack(fill="x", padx=15, pady=(0, 10))
        self._render_youtube_analytics_list()

        # "time saved with --hwaccel" metric - מתעדכן יחד עם היסטוריית הריצות
        # (refresh_job_history), לא בזמן אמת - השוואה כזו לא משתנה תוך כדי ריצה בודדת.
        self.hwaccel_savings_label = ctk.CTkLabel(self.side_card, text="", font=("Segoe UI", 9), text_color=PALETTE["text_muted"], wraplength=220, justify="right")
        self.hwaccel_savings_label.pack(pady=(0, 6), padx=15)

        # --- היסטוריית חומרה (item: historical hardware usage graph) - מעבר
        # לגרף "3 דקות אחרונות" שכבר קיים בסיידבר (utils/shared/hardware.py's in-memory
        # arrays) - טווח ארוך בהרבה (24 שעות), נשמר ל-DB דרך utils/shared/hardware_history.py
        # כדי לשרוד restart. מתעדכן לאט (כל 60 שניות - זהה לתדירות הרישום עצמו
        # ב-record_sample, אין טעם לרענן מהר יותר) בניגוד לגרף החי בסיידבר.
        ctk.CTkLabel(self.side_card, text=t("📈 היסטוריית חומרה (24 שעות)"), font=("Segoe UI", 11, "bold")).pack(pady=(10, 4))
        self.hw_history_canvas = tk.Canvas(self.side_card, height=80, bg=PALETTE["surface_alt"], highlightthickness=0)
        self.hw_history_canvas.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_hardware_history_graph()

        # --- "שעות משחק" ו"קליפים שנלכדו" (item: personal stats dashboard) -
        # שני "טרנדים איטיים" נוספים תחת אותו side_card, אז אותה תדירות רענון
        # (60 שניות) שכבר קיימת לגרף החומרה מעל הגיונית גם כאן.
        ctk.CTkLabel(self.side_card, text=t("🎮 שעות משחק"), font=("Segoe UI", 11, "bold")).pack(pady=(10, 4))
        self.game_playtime_label = ctk.CTkLabel(
            self.side_card, text="", font=("Segoe UI", 10), text_color=PALETTE["text_muted"], justify="right",
        )
        self.game_playtime_label.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_game_playtime_summary()

        ctk.CTkLabel(
            self.side_card, text=t("📅 קליפים שנלכדו ({days} ימים אחרונים)", days=CLIPS_CAPTURED_HISTORY_DAYS),
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(0, 4))
        self.clips_history_canvas = tk.Canvas(self.side_card, height=60, bg=PALETTE["surface_alt"], highlightthickness=0)
        self.clips_history_canvas.pack(fill="x", padx=15, pady=(0, 10))
        self._refresh_clips_captured_graph()

        # --- היסטוריית עבודות ---
        self.history_frame = ctk.CTkFrame(self, fg_color=PALETTE["surface_alt"])
        self.history_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 15))

        history_header = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        history_header.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(history_header, text=t("📜 היסטוריית ריצות אחרונות"), font=("Segoe UI", 12, "bold")).pack(side="right")
        ctk.CTkButton(history_header, text="🔄", width=28, height=24, fg_color=PALETTE["border"], command=self.refresh_job_history).pack(side="left")
        # "בטל פעולה אחרונה" (item: undo last file-move operation) - רק
        # cleanup_published_sources.py כרגע כותב ל-move_undo_log (ראו שם), אז
        # הכפתור מוצג רק כשיש בפועל batch ממתין - לא "מת" קבוע על המסך.
        self.undo_btn = ctk.CTkButton(
            history_header, text=t("↩️ בטל פעולה אחרונה"), width=140, height=24,
            fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"], command=self._on_undo_last_move_batch,
        )
        self._refresh_undo_button_visibility()

        # חיפוש בהיסטוריה (item: global search) - script_name/status/result_json
        # (utils/shared/job_history.py's search_jobs), לא רק שם סקריפט. debounce ידני
        # (self.after + ביטול הקריאה הקודמת) כדי לא לשאול את ה-DB על כל הקשת מקש.
        self._history_search_after_id = None
        self.history_search_var = ctk.StringVar()
        self.history_search_var.trace_add("write", lambda *_: self._on_history_search_changed())
        ctk.CTkEntry(
            self.history_frame, textvariable=self.history_search_var,
            placeholder_text=t("🔍 חפש בהיסטוריה (שם סקריפט, קובץ, סטטוס, תאריך...)"),
        ).pack(fill="x", padx=10, pady=(6, 0))

        self.history_scroll = ctk.CTkScrollableFrame(self.history_frame, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh_job_history(self):
        self.history_search_var.set("")  # מנקה גם חיפוש קודם - "רענן" אמור להחזיר לתצוגה הרגילה
        self._render_job_rows(job_history.get_recent_jobs(limit=15), empty_text=t("עוד לא בוצעו ריצות."))
        self._refresh_undo_button_visibility()
        self._refresh_hwaccel_savings_label()

    def _refresh_hwaccel_savings_label(self):
        comparison = job_history.get_hwaccel_time_comparison()
        if comparison is None:
            self.hwaccel_savings_label.configure(text="")
            return
        direction = t("מהיר יותר") if comparison["percent_faster"] >= 0 else t("איטי יותר")
        self.hwaccel_savings_label.configure(text=t(
            "⚡ --hwaccel ב-video_editor.py: {pct}% {direction} בממוצע ({n1} ריצות לעומת {n2})",
            pct=f"{abs(comparison['percent_faster']):.0f}", direction=direction,
            n1=comparison["hwaccel_run_count"], n2=comparison["no_hwaccel_run_count"],
        ))

    def _refresh_undo_button_visibility(self):
        if move_undo_log.get_last_move_batch() is not None:
            self.undo_btn.pack(side="left", padx=(4, 0))
        else:
            self.undo_btn.pack_forget()

    def _on_undo_last_move_batch(self):
        result = move_undo_log.undo_last_move_batch()
        restored = len(result.get("restored", []))
        skipped = len(result.get("skipped", []))
        if "error" in result:
            self.lbl_status.configure(text=result["error"])
        else:
            self.lbl_status.configure(text=t("↩️ הוחזרו {restored} קבצים למקורם ({skipped} דולגו)", restored=restored, skipped=skipped))
        self._refresh_undo_button_visibility()

    def _refresh_hardware_history_graph(self):
        rows = hardware_history.get_recent_samples(hours=24)
        cpu_hist = [row[1] for row in rows]
        ram_hist = [row[2] for row in rows]
        # gpu יכול להיות None לדגימות בלי GPU של NVIDIA זמין - קו GPU מצויר רק
        # אם *כל* הדגימות בטווח כוללות ערך אמיתי (בדיוק כמו ui/sidebar.py, ששם
        # קו שטוח-על-0 היה נראה כמו "GPU בניצולת אפס" ולא כמו "אין מדידה").
        gpu_hist = [row[3] for row in rows] if rows and all(row[3] is not None for row in rows) else None
        self._draw_hardware_history_graph(cpu_hist, ram_hist, gpu_hist)
        if self.winfo_exists():
            self.after(60000, self._refresh_hardware_history_graph)

    def _draw_hardware_history_graph(self, cpu_hist, ram_hist, gpu_hist):
        """זהה בעיקרון ל-ui/sidebar.py's _draw_history_graph - אותו רעיון
        (קו לכל סדרה, מנורמל 0-100 לגובה ה-canvas), אבל טווח הנתונים כאן הוא
        24 שעות מה-DB (utils/shared/hardware_history.py), לא 3 הדקות האחרונות בזיכרון."""
        canvas = self.hw_history_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return

        def _plot(history, color):
            n = len(history)
            if n < 2:
                return
            step = width / (n - 1)
            points = []
            for i, v in enumerate(history):
                x = i * step
                y = height - (min(100, max(0, v)) / 100.0 * height)
                points.extend([x, y])
            canvas.create_line(*points, fill=color, width=1.5, smooth=True)

        _plot(cpu_hist, PALETTE["cpu_ring"])
        _plot(ram_hist, PALETTE["pink_accent"])
        if gpu_hist is not None:
            _plot(gpu_hist, PALETTE["gpu_ring"])

    def _refresh_game_playtime_summary(self):
        # item: personal stats dashboard - נצבר מ-gui_manager.pyw's game_loop
        # (ראו utils/media/game_playtime.py), לא כאן; זה רק קורא ומציג את המצטבר.
        summary = game_playtime.get_playtime_summary()
        if not summary:
            self.game_playtime_label.configure(text=t("עוד לא נרשם זמן משחק."))
        else:
            lines = [
                t("{name}: {hours:.1f} שעות", name=name, hours=total_seconds / 3600)
                for name, total_seconds, _last_played_at in summary
            ]
            self.game_playtime_label.configure(text="\n".join(lines))
        if self.winfo_exists():
            self.after(60000, self._refresh_game_playtime_summary)

    def _refresh_clips_captured_graph(self):
        counts = get_clips_captured_by_day(CLIPS_DIR, days=CLIPS_CAPTURED_HISTORY_DAYS)
        self._draw_clips_captured_graph(list(counts.values()))
        if self.winfo_exists():
            self.after(60000, self._refresh_clips_captured_graph)

    def _draw_clips_captured_graph(self, daily_counts):
        """גרף עמודות פשוט (לא קו, כמו גרף החומרה) - כל עמודה היא יום, גובה
        יחסי למקסימום בטווח המוצג. יום ללא קליפים = עמודה בגובה 0, לא נעדר."""
        canvas = self.clips_history_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1 or not daily_counts:
            return
        max_count = max(daily_counts) or 1
        bar_width = width / len(daily_counts)
        for i, count in enumerate(daily_counts):
            bar_height = (count / max_count) * height
            canvas.create_rectangle(
                i * bar_width + 1, height - bar_height, (i + 1) * bar_width - 1, height,
                fill=state.current_theme["accent"], outline="",
            )

    def _on_history_search_changed(self):
        if self._history_search_after_id is not None:
            self.after_cancel(self._history_search_after_id)
        self._history_search_after_id = self.after(250, self._run_history_search)

    def _run_history_search(self):
        query = self.history_search_var.get().strip()
        if not query:
            self._render_job_rows(job_history.get_recent_jobs(limit=15), empty_text=t("עוד לא בוצעו ריצות."))
            return
        self._render_job_rows(job_history.search_jobs(query, limit=50), empty_text=t("לא נמצאו ריצות תואמות."))

    def _render_job_rows(self, rows, empty_text):
        for w in self.history_scroll.winfo_children(): w.destroy()
        if not rows:
            ctk.CTkLabel(self.history_scroll, text=empty_text, text_color=PALETTE["text_muted"]).pack(pady=10)
            return

        for script_name, status, started_at, duration_seconds, result_json in rows:
            icon = "✅" if status == "success" else "❌"
            color = state.current_theme["accent"] if status == "success" else PALETTE["danger"]
            duration_str = f"{duration_seconds:.0f}s" if duration_seconds < 60 else f"{duration_seconds / 60:.1f}m"
            row = ctk.CTkFrame(self.history_scroll, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"{icon} {script_name}", font=("Segoe UI", 11), text_color=color, anchor="e").pack(side="right", padx=5)
            ctk.CTkLabel(row, text=f"{started_at.replace('T', ' ')} · {duration_str}", font=("Consolas", 10), text_color=PALETTE["text_muted"], anchor="w").pack(side="left", padx=5)

            # result_json (אם הסקריפט הדפיס "RESULT: {...}" - ראו utils/shared/worker.py) -
            # שורה שנייה קטנה מתחת עם פירוט אמיתי במקום רק ✅/❌+משך. שורה נפרדת
            # (לא עוד label באותה row) כדי לא להצטופף עם שם הסקריפט/המשך בשורה אחת.
            summary = job_history.format_result_summary(result_json)
            if summary:
                ctk.CTkLabel(self.history_scroll, text=summary, font=("Consolas", 9), text_color=PALETTE["text_muted"], anchor="e", justify="right").pack(fill="x", padx=5, pady=(0, 2))

    def refresh_gallery(self):
        self._all_clips = sorted(glob.glob(os.path.join(CLIPS_DIR, "*.mp4")), key=os.path.getmtime, reverse=True)
        self._refresh_gallery_tag_options()
        self._render_gallery()

    def _refresh_gallery_tag_options(self):
        # רק סורק מטמון קיים (list_all_cached_tags) - שומר על הבחירה הנוכחית
        # אם היא עדיין ברשימה המחודשת, כדי ש"רענן" לא יאפס סינון-תגית פעיל.
        all_tags_label = t(ALL_TAGS_LABEL)
        values = [all_tags_label] + list_all_cached_tags(TAGS_CACHE_DIR)
        current = self.gallery_tag_var.get()
        self.gallery_tag_menu.configure(values=values)
        if current not in values:
            self.gallery_tag_var.set(all_tags_label)

    def _render_gallery(self):
        for w in self.scroll.winfo_children(): w.destroy()
        query = self.gallery_search_var.get().strip().lower()
        tag_filter = self.gallery_tag_var.get()
        show_all_tags = tag_filter == t(ALL_TAGS_LABEL)
        for c in self._all_clips:
            if query and query not in os.path.basename(c).lower():
                continue
            if not show_all_tags and tag_filter not in (read_cached_tags(c, TAGS_CACHE_DIR) or []):
                continue
            btn = ctk.CTkButton(self.scroll, text=os.path.basename(c), anchor="e", fg_color=PALETTE["bg_root"])
            btn.pack(pady=2, fill="x")
            btn.bind("<Button-1>", lambda e, p=c: self.select_clip(p))
            btn.bind("<Double-Button-1>", lambda e, p=c: webbrowser.open(p))

    def select_clip(self, path):
        state.last_selected_clip_path = path
        self.lbl_status.configure(text=t("נבחר: {name}", name=os.path.basename(path)))
        self.btn_tiktok.configure(state="normal")
        self.btn_yt.configure(state="normal")

    def export_wizard(self, url):
        if state.last_selected_clip_path:
            generate_seo_metadata(state.last_selected_clip_path)
            webbrowser.open(url)

    def export_youtube(self):
        clip_path = state.last_selected_clip_path
        if not clip_path:
            return

        generate_seo_metadata(clip_path)

        if not youtube_uploader.is_configured():
            # אין client_secret.json מוגדר - נופלים חזרה לפתיחת דפדפן להעלאה ידנית
            webbrowser.open("https://youtube.com/upload")
            return

        self.btn_yt.configure(state="disabled", text=t("⏳ מעלה... {pct}%", pct=0))
        title = os.path.splitext(os.path.basename(clip_path))[0]

        def progress(pct):
            self._dispatcher.call_soon(self.btn_yt.configure, text=t("⏳ מעלה... {pct}%", pct=pct))

        def do_upload():
            try:
                video_id = youtube_uploader.upload_video(
                    clip_path, title=title, description="",
                    tags=["gaming", "shorts"], privacy_status="private",
                    progress_callback=progress
                )
                youtube_publish_log.record_upload(video_id, os.path.basename(clip_path), title)
                self._generate_and_record_thumbnail_candidates(video_id, clip_path)
                self._dispatcher.call_soon(self._on_youtube_upload_done, True, video_id)
            except Exception as e:
                # פייתון מוחק אוטומטית את משתנה ה-except (e) ביציאה מהבלוק - כש-
                # call_soon דוחה את הקריאה בפועל למחזור אירועים מאוחר יותר, e כבר
                # לא קיים וזה יקרוס עם NameError, מה שמסתיר את שגיאת ההעלאה האמיתית
                # לגמרי. וגם: self.after ישיר מ-thread רקע לא בטוח - ראו utils/shared/gui_thread.py.
                error_msg = str(e)
                self._dispatcher.call_soon(self._on_youtube_upload_done, False, error_msg)

        threading.Thread(target=do_upload, daemon=True).start()

    def _on_youtube_upload_done(self, success, result):
        self.btn_yt.configure(state="normal", text="📺 YouTube Export Pro")
        if success:
            self.lbl_status.configure(text=t("✅ הועלה ל-YouTube! ID: {id}", id=result))
            self._render_youtube_analytics_list()
        else:
            self.lbl_status.configure(text=t("❌ העלאה נכשלה: {error}", error=result))

    def _generate_and_record_thumbnail_candidates(self, video_id, clip_path):
        """נקרא מ-do_upload's thread רקע (כבר לא ה-thread הראשי) מיד אחרי
        העלאה מוצלחת, בזמן שקובץ הקליפ המקורי עדיין ודאי קיים (item: A/B
        thumbnail testing) - זהה ל-web_app.py's הפונקציה המקבילה, אותה
        THUMBNAIL_CANDIDATES_DIR משותפת. כשל כאן לא אמור להפיל את ההעלאה
        שכבר הצליחה - תמונות מועמדות הן שיפור-חוויה אופציונלי."""
        try:
            out_dir = os.path.join(THUMBNAIL_CANDIDATES_DIR, video_id)
            candidate_paths = generate_candidates(clip_path, out_dir, get_ffmpeg_exe(), get_ffprobe_exe())
            youtube_thumbnail_log.record_candidates(video_id, candidate_paths)
        except Exception as e:
            print(f"[stats_tab] שגיאה ביצירת תמונות ממוזערות מועמדות: {e}")

    def _render_youtube_analytics_list(self):
        for w in self.yt_analytics_scroll.winfo_children():
            w.destroy()
        rows = youtube_publish_log.get_published_videos()
        if not rows:
            ctk.CTkLabel(
                self.yt_analytics_scroll, text=t('עוד לא הועלו סרטונים דרך "📺 YouTube Export Pro".'),
                text_color=PALETTE["text_muted"], font=("Segoe UI", 9), wraplength=200, justify="right",
            ).pack(pady=4)
            return
        for video_id, clip_filename, title, _uploaded_at, views, likes, comments, _stats_updated_at in rows:
            row = ctk.CTkFrame(self.yt_analytics_scroll, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=title or clip_filename, font=("Segoe UI", 10), anchor="e", justify="right").pack(fill="x")
            meta = t("עוד לא רוענן") if views is None else f"👁 {views} · 👍 {likes} · 💬 {comments}"
            latest_switch = youtube_thumbnail_log.get_latest_switch(video_id)
            if latest_switch and views is not None:
                _candidate_index, _set_at, views_at_switch = latest_switch
                meta += f" · 🖼️ +{views - views_at_switch} {t('מאז ההחלפה')}"
            ctk.CTkLabel(row, text=meta, font=("Segoe UI", 9), text_color=PALETTE["text_muted"], anchor="e").pack(fill="x")
            ctk.CTkButton(
                row, text=t("🖼️ תמונות ממוזערות"), font=("Segoe UI", 9), height=22, fg_color=PALETTE["border"],
                command=lambda vid=video_id: self._open_thumbnail_candidates_dialog(vid),
            ).pack(anchor="e", pady=(2, 0))

    def _open_thumbnail_candidates_dialog(self, video_id):
        candidates = youtube_thumbnail_log.get_candidates(video_id)
        dialog = ctk.CTkToplevel(self)
        dialog.title(t("🖼️ תמונות ממוזערות מועמדות"))
        dialog.geometry("560x230")
        dialog._image_refs = []  # רפרנס חי כל עוד הדיאלוג פתוח - ראו ApprovalsTabComponent's אותה הערה

        if not candidates:
            ctk.CTkLabel(dialog, text=t("אין תמונות מועמדות לסרטון הזה.")).pack(pady=30)
            return

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(fill="both", expand=True, padx=10, pady=10)
        for index, image_path in candidates:
            card = ctk.CTkFrame(row, fg_color=PALETTE["surface_alt"])
            card.pack(side="right", padx=6, fill="both", expand=True)
            try:
                image = Image.open(image_path)
                image.thumbnail((160, 160))
                ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                dialog._image_refs.append(ctk_image)
                ctk.CTkLabel(card, image=ctk_image, text="").pack(pady=6)
            except Exception:
                pass
            ctk.CTkButton(
                card, text=t("✅ הגדר"),
                command=lambda idx=index, vid=video_id, d=dialog: self._set_video_thumbnail(vid, idx, d),
            ).pack(pady=(0, 8), padx=8, fill="x")

    def _set_video_thumbnail(self, video_id, candidate_index, dialog):
        candidates = dict(youtube_thumbnail_log.get_candidates(video_id))
        image_path = candidates.get(candidate_index)
        if not image_path:
            return

        def do_set():
            try:
                youtube_analytics.set_video_thumbnail(video_id, image_path)
                published = {row[0]: row[4] for row in youtube_publish_log.get_published_videos()}
                views_at_switch = published.get(video_id) or 0
                youtube_thumbnail_log.record_switch(video_id, candidate_index, views_at_switch)
                self._dispatcher.call_soon(self._on_thumbnail_set_done, True, dialog, None)
            except Exception as e:
                self._dispatcher.call_soon(self._on_thumbnail_set_done, False, dialog, str(e))

        threading.Thread(target=do_set, daemon=True).start()

    def _on_thumbnail_set_done(self, success, dialog, error):
        if dialog.winfo_exists():
            dialog.destroy()
        self._render_youtube_analytics_list()
        if not success:
            print(f"[stats_tab] שגיאה בהגדרת תמונה ממוזערת: {error}")

    def refresh_youtube_analytics(self):
        if not youtube_uploader.is_configured():
            return
        self.yt_analytics_refresh_btn.configure(state="disabled", text="⏳")

        def do_refresh():
            errors = []
            for video_id, *_rest in youtube_publish_log.get_published_videos():
                try:
                    stats = youtube_analytics.get_video_stats(video_id)
                except Exception as e:
                    errors.append(str(e))
                    continue
                if stats is None:
                    continue
                youtube_publish_log.update_cached_stats(video_id, stats["views"], stats["likes"], stats["comments"])
            self._dispatcher.call_soon(self._on_youtube_analytics_refresh_done, errors)

        threading.Thread(target=do_refresh, daemon=True).start()

    def _on_youtube_analytics_refresh_done(self, errors):
        self.yt_analytics_refresh_btn.configure(state="normal", text="🔄")
        self._render_youtube_analytics_list()
        if errors:
            print(f"[stats_tab] שגיאות ברענון אנליטיקס YouTube: {errors}")