# ui/sidebar.py
import customtkinter as ctk
import os
import glob
import tkinter as tk
from utils.shared.state import PALETTE, state
from utils.shared.hardware import get_system_stats, get_performance_history, get_gpu_stats, get_gpu_performance_history
from utils.shared.script_metadata import get_script_metadata
from utils.shared import job_history
from utils.shared.i18n import t, fix_hebrew_word_order
from ui.widgets import FONT_HEBREW_SUB, FONT_HEBREW_TEXT, FONT_HEBREW_TEXT_BOLD

RECENTLY_RUN_LABEL = t("🕐 הורצו לאחרונה")
FAVORITES_LABEL = t("⭐ מועדפים")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE_DIR, "my_scripts")

# הקטגוריה נגזרת מתת-התיקייה שבה יושב הסקריפט (my_scripts/video, my_scripts/tools
# וכו') במקום ממיפוי שם-קובץ ידני - כך שאי אפשר "לשכוח" לקטלג סקריפט חדש: הוא
# פשוט יורש את הקטגוריה של התיקייה שהוא נוצר בתוכה. סקריפט שיושב ישירות תחת
# my_scripts/ (בלי תת-תיקייה) נופל ל-DEFAULT_CATEGORY.
FOLDER_CATEGORY_LABELS = {
    "video": t("🎬 פייפליין וידאו"),
    "stream": t("📡 סטרימינג"),
    "steam": t("🎮 Steam"),
    "tools": t("🛠️ כלי עזר"),
}
CATEGORY_ORDER = [t("🎬 פייפליין וידאו"), t("📡 סטרימינג"), t("🎮 Steam"), t("🛠️ כלי עזר")]
DEFAULT_CATEGORY = t("🛠️ כלי עזר")


def _category_for(script_path):
    folder_name = os.path.basename(os.path.dirname(script_path))
    return FOLDER_CATEGORY_LABELS.get(folder_name, DEFAULT_CATEGORY)

class SidebarComponent(ctk.CTkFrame):
    def __init__(self, parent, on_script_select):
        super().__init__(parent, width=280, corner_radius=0, fg_color=PALETTE["surface"], border_color=PALETTE["border_sidebar"], border_width=1)
        self.pack_propagate(False)
        self.on_script_select = on_script_select
        self.all_scripts = []
        self._current_script_list = []
        self._show_all_categories = True
        # path -> [button, ...] (רשימה, לא כפתור בודד - סקריפט מועדף מופיע גם
        # תחת "מועדפים" וגם תחת הקטגוריה שלו, שני כפתורים לאותו path) - כדי
        # ש-_select_script יוכל להדגיש/לבטל הדגשה ישירות בלי לפרק ולבנות
        # מחדש את כל הרשימה על כל לחיצה (ראו _select_script).
        self._script_buttons = {}
        self._highlighted_path = None
        self._build_component()
        self.load_scripts()
        self._update_hw_loop()

    def _build_component(self):
        self.sidebar_title = ctk.CTkLabel(self, text=t("🚀 הסטודיו שלי"), font=FONT_HEBREW_SUB)
        self.sidebar_title.pack(pady=(25, 15), padx=10)

        self.search_entry = ctk.CTkEntry(self, placeholder_text=t("🔍 חפש סקריפט..."), justify="right", fg_color=PALETTE["bg_root"], border_color=PALETTE["border_search"])
        self.search_entry.pack(pady=5, padx=15, fill="x")
        self.search_entry.bind("<KeyRelease>", self._filter_scripts)

        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text=t("בחר סקריפט להפעלה"), fg_color="transparent")
        self.scrollable_frame.pack(pady=15, padx=10, fill="both", expand=True)

        self.hw_frame = ctk.CTkFrame(self, corner_radius=10, fg_color=PALETTE["surface_alt"], border_color=PALETTE["border_dim"], border_width=1)
        self.hw_frame.pack(pady=10, padx=15, fill="x")
        
        self.lbl_cpu = ctk.CTkLabel(self.hw_frame, text=t("CPU: {pct}%", pct=0), font=("Segoe UI", 12))
        self.lbl_cpu.pack(padx=10, anchor="e")
        self.cpu_bar = ctk.CTkProgressBar(self.hw_frame, progress_color=PALETTE["cpu_ring"], fg_color=PALETTE["bg_root"], height=6)
        self.cpu_bar.pack(fill="x", padx=10, pady=(0, 8))

        self.lbl_ram = ctk.CTkLabel(self.hw_frame, text=t("RAM: {pct}%", pct=0), font=("Segoe UI", 12))
        self.lbl_ram.pack(padx=10, anchor="e")
        self.ram_bar = ctk.CTkProgressBar(self.hw_frame, progress_color=PALETTE["pink_accent"], fg_color=PALETTE["bg_root"], height=6)
        self.ram_bar.pack(fill="x", padx=10, pady=(0, 8))

        # GPU/VRAM - רלוונטי במיוחד לכלי הזה שכל הפייפליין שלו מבוסס NVENC
        self.lbl_gpu = ctk.CTkLabel(self.hw_frame, text=t("GPU: -"), font=("Segoe UI", 12))
        self.lbl_gpu.pack(padx=10, anchor="e")
        self.gpu_bar = ctk.CTkProgressBar(self.hw_frame, progress_color=PALETTE["gpu_ring"], fg_color=PALETTE["bg_root"], height=6)
        self.gpu_bar.pack(fill="x", padx=10, pady=(0, 8))

        self.lbl_vram = ctk.CTkLabel(self.hw_frame, text=t("VRAM: -"), font=("Segoe UI", 12))
        self.lbl_vram.pack(padx=10, anchor="e")
        self.vram_bar = ctk.CTkProgressBar(self.hw_frame, progress_color=PALETTE["gpu_ring"], fg_color=PALETTE["bg_root"], height=6)
        self.vram_bar.pack(fill="x", padx=10, pady=(0, 8))

        # מנוע ה-NVENC הייעודי - מד נפרד מ-GPU למעלה (שהוא CUDA/shader כללי
        # בלבד) כדי שרינדור מבוסס hevc_nvenc/av1_nvenc יראה בפירוש שה-GPU
        # באמת עסוק, גם כשה-GPU הכללי נראה כמעט פנוי (הפילטרים שלפני הקידוד
        # רצים כולם ב-CPU).
        self.lbl_encoder = ctk.CTkLabel(self.hw_frame, text=t("Encoder (NVENC): -"), font=("Segoe UI", 12))
        self.lbl_encoder.pack(padx=10, anchor="e")
        self.encoder_bar = ctk.CTkProgressBar(self.hw_frame, progress_color=PALETTE["gpu_ring"], fg_color=PALETTE["bg_root"], height=6)
        self.encoder_bar.pack(fill="x", padx=10, pady=(0, 8))

        # גרף ניצולת לאורך זמן (item 17) - עד כה היו רק מדי-האחוזים הרגעיים
        # למעלה; זה מציג את ~3 הדקות האחרונות (utils/shared/hardware.py's HISTORY_LENGTH)
        # כדי לראות מגמה (למשל דליפת RAM הדרגתית) ולא רק נקודה בזמן. Canvas גולמי
        # (לא widget של CustomTkinter - אין לה widget גרפים מובנה) מצויר מחדש
        # בכל טיק של _update_hw_loop, אותו קצב בדיוק כמו שאר הבר.
        self.lbl_history_graph = ctk.CTkLabel(self.hw_frame, text=t("📈 ניצולת לאורך זמן"), font=("Segoe UI", 10), text_color=PALETTE["text_muted"])
        self.lbl_history_graph.pack(padx=10, anchor="e", pady=(4, 0))
        self.history_canvas = tk.Canvas(self.hw_frame, height=60, bg=PALETTE["surface_alt"], highlightthickness=0)
        self.history_canvas.pack(fill="x", padx=10, pady=(2, 10))

    def load_scripts(self):
        self.all_scripts = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.py"), recursive=True))
        # תצוגה מצומצמת (מועדפים+הורצו-לאחרונה בלבד) כברירת מחדל רק אם כבר יש
        # מועדפים - אחרת המסך הראשוני של משתמש חדש (בלי מועדפים בכלל) היה נראה
        # כמעט ריק, בלי שום דרך אינטואיטיבית להבין שצריך ללחוץ "הצג הכל".
        self._show_all_categories = not bool(state.get_favorite_scripts())
        self._render_buttons(self.all_scripts)

    def _make_script_button(self, parent, path):
        metadata = get_script_metadata(path)
        # "⚡" לסקריפטים "קלים" (# Concurrency: light) - רצים במאגר מקביל של
        # utils/shared/worker.py ולא מחכים בתור מאחורי רינדור כבד שכבר רץ.
        concurrency_badge = "⚡ " if metadata["concurrency"] == "light" else ""
        # "⚠️" רק לסקריפטים שמזיזים/משנים שם/מוחקים קובץ קיים (# Safety:
        # modifies) - קריאה-בלבד לא מקבל תג, כדי שהאזהרה תבלוט בדיוק במקום
        # שבו היא רלוונטית ולא תיטבע ברעש ויזואלי.
        safety_badge = "⚠️ " if metadata["safety"] == "modifies" else ""
        prefix = f"{safety_badge}{concurrency_badge}"

        basename = os.path.basename(path)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=2, fill="x")

        # side="right" (לא "left") - בקריאה מימין-לשמאל סמן מוביל כמו כוכב
        # "לפני" התווית אמור לשבת בקצה הימני (שם קריאה עברית מתחילה), עם
        # התווית ממלאת את השטח שמשמאלו. פריסה קודמת (star ב-side="left")
        # שמה את הכוכב בקצה השמאלי - "הפוך" יחסית לאיך ש-RTL אמיתי (dir="rtl"
        # ב-web_app.py) היה מסדר את אותם שני אלמנטים.
        is_favorite = basename in state.get_favorite_scripts()
        ctk.CTkButton(
            row, text="⭐" if is_favorite else "☆", width=28, fg_color=PALETTE["border_dim2"],
            command=lambda b=basename: self._toggle_favorite(b)
        ).pack(side="right", padx=(4, 0))

        # fix_hebrew_word_order על המחרוזת המורכבת השלמה (prefix+name), לא רק
        # על metadata['name'] בבידוד - ראו utils/shared/script_metadata.py: get_script_metadata
        # כבר לא מפעיל את זה בעצמו, בדיוק כדי שכל תצוגה תפעיל את זה בעצמה על
        # הטקסט הסופי שהיא בונה (זה בדיוק מה שהיה שבור קודם).
        button_text = fix_hebrew_word_order(f"{prefix}{metadata['name']}")
        # הסקריפט הנבחר כרגע (state.selected_script) מודגש בצבע ה-accent - קודם
        # כל כפתור נראה זהה לחלוטין, בלי שום דרך לדעת מהסיידבר לבד מה רץ/נבחר.
        is_selected = path == state.selected_script
        btn = ctk.CTkButton(
            row, text=button_text, anchor="e",
            fg_color=state.current_theme["accent"] if is_selected else PALETTE["border_dim2"],
            hover_color=state.current_theme["accent_hover"] if is_selected else PALETTE["script_btn_hover"],
            # border/corner_radius מפורשים (לא ברירת המחדל הסתמית של CTkButton) -
            # כדי שכל כרטיס יהיה בעל מתאר גלוי, כמו .script-btn ב-web_app.py,
            # במקום שורה שטוחה שקשה להבחין בינה לבין רקע הסיידבר הריק.
            border_width=1, border_color=PALETTE["border"], corner_radius=8,
            font=FONT_HEBREW_TEXT_BOLD if is_selected else FONT_HEBREW_TEXT,
            command=lambda p=path: self._select_script(p)
        )
        btn.pack(side="left", fill="x", expand=True)
        self._script_buttons.setdefault(path, []).append(btn)

    def _select_script(self, path):
        self.on_script_select(path)
        self.refresh_selection_highlight()

    def refresh_selection_highlight(self):
        """מעדכן ישירות רק את הכפתור/ים הישן/ים והחדש/ים (fg_color+font) במקום
        להרוס ולבנות מחדש את כל רשימת הסקריפטים על כל בחירה - עם רשימה ארוכה
        (הרבה קטגוריות/מועדפים) פירוק-ובנייה-מחדש היה מורגש כ"קיפאון" רגעי של
        כל הסיידבר בכל החלפת סקריפט. ציבורית (לא רק _select_script) כי בחירת
        סקריפט יכולה לקרות גם דרך Command Palette או קיצור "הרץ שוב" (שני
        המקרים קוראים ל-on_script_selected ישירות, בלי לעבור דרך הסיידבר בכלל) -
        gui_manager.pyw קורא לזה בסוף on_script_selected כדי שההדגשה תישאר
        מסונכרנת בלי קשר איך הבחירה קרתה בפועל."""
        previous_path = self._highlighted_path
        current_path = state.selected_script
        if previous_path == current_path:
            return
        self._update_button_highlight(previous_path)
        self._update_button_highlight(current_path)
        self._highlighted_path = current_path

    def _update_button_highlight(self, path):
        is_selected = path == state.selected_script
        for btn in self._script_buttons.get(path, []):
            if btn.winfo_exists():
                btn.configure(
                    fg_color=state.current_theme["accent"] if is_selected else PALETTE["border_dim2"],
                    font=FONT_HEBREW_TEXT_BOLD if is_selected else FONT_HEBREW_TEXT,
                )

    def _toggle_favorite(self, basename):
        state.toggle_favorite_script(basename)
        self._render_buttons(self._current_script_list)

    def _expand_categories(self):
        self._show_all_categories = True
        self._render_buttons(self._current_script_list)

    def _collapse_categories(self):
        self._show_all_categories = False
        self._render_buttons(self._current_script_list)

    def _render_buttons(self, script_list):
        self._current_script_list = script_list
        for widget in self.scrollable_frame.winfo_children(): widget.destroy()
        # מתאפס כאן (לא ב-_make_script_button) כי כל קריאה ל-_render_buttons
        # הורסת ובונה מחדש את כל העץ - כפתורים ישנים כבר לא קיימים, אז
        # ההפניות הישנות אליהם חייבות להיזרק גם הן. כל כפתור נבנה מחדש כבר עם
        # is_selected נכון (ראו _make_script_button), אז מספיק לסנכרן את
        # _highlighted_path בלי לקרוא ל-_update_button_highlight בפועל.
        self._script_buttons = {}
        self._highlighted_path = state.selected_script

        # "מועדפים"/"הורצו לאחרונה" מוצגים רק על הרשימה המלאה (לא תוך כדי סינון
        # חיפוש) - script_list is self.all_scripts מזהה את זה בלי צורך בדגל נפרד.
        is_unfiltered = script_list is self.all_scripts
        by_basename = {os.path.basename(p): p for p in self.all_scripts}

        favorite_names = state.get_favorite_scripts()
        favorite_paths = [by_basename[name] for name in sorted(favorite_names) if name in by_basename]
        if favorite_paths and is_unfiltered:
            ctk.CTkLabel(
                self.scrollable_frame, text=FAVORITES_LABEL, font=("Segoe UI", 11, "bold"),
                text_color=PALETTE["text_category"], anchor="e"
            ).pack(pady=(0, 2), fill="x")
            for path in favorite_paths:
                self._make_script_button(self.scrollable_frame, path)

        # "הורצו לאחרונה" - קיצור דרך מבוסס job_history. מחושב פעם אחת בטעינה
        # (לא מתעדכן חי תוך כדי ריצה) - כמו שאר גילוי הסקריפטים כאן.
        recent_paths = [by_basename[name] for name in job_history.get_recently_run_script_names(limit=5) if name in by_basename]
        if recent_paths and is_unfiltered:
            ctk.CTkLabel(
                self.scrollable_frame, text=RECENTLY_RUN_LABEL, font=("Segoe UI", 11, "bold"),
                text_color=PALETTE["text_category"], anchor="e"
            ).pack(pady=(10 if favorite_paths else 0, 2), fill="x")
            for path in recent_paths:
                self._make_script_button(self.scrollable_frame, path)

        # תצוגה מצומצמת: כשיש מועדפים ולא ביקשו "הצג הכל", מסתירים את רשימת
        # הקטגוריות המלאה מאחורי כפתור אחד - כדי שהמסך הראשוני לא יהיה עמוס.
        if is_unfiltered and favorite_paths and not self._show_all_categories:
            ctk.CTkButton(
                self.scrollable_frame, text=t("📋 הצג את כל הסקריפטים"), fg_color=PALETTE["border_dim2"],
                command=self._expand_categories
            ).pack(pady=(15, 2), fill="x")
            return

        grouped = {}
        for path in script_list:
            grouped.setdefault(_category_for(path), []).append(path)

        ordered_categories = [c for c in CATEGORY_ORDER if c in grouped]
        ordered_categories += [c for c in grouped if c not in ordered_categories]

        for category in ordered_categories:
            ctk.CTkLabel(
                self.scrollable_frame, text=category, font=("Segoe UI", 11, "bold"),
                text_color=PALETTE["text_category"], anchor="e"
            ).pack(pady=(10, 2), fill="x")
            for path in grouped[category]:
                self._make_script_button(self.scrollable_frame, path)

        if is_unfiltered and favorite_paths and self._show_all_categories:
            ctk.CTkButton(
                self.scrollable_frame, text=t("📋 הצג פחות"), fg_color=PALETTE["border_dim2"],
                command=self._collapse_categories
            ).pack(pady=(10, 2), fill="x")

    def _filter_scripts(self, event):
        q = self.search_entry.get().lower()
        filtered = [
            s for s in self.all_scripts
            if q in os.path.basename(s).lower() or q in get_script_metadata(s)["name"].lower()
        ]
        self._render_buttons(filtered)

    def _update_hw_loop(self):
        cpu, ram = get_system_stats()
        cpu_hist, ram_hist = get_performance_history()
        bars = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        spark = lambda h: "".join(bars[min(7, int(v / 13))] for v in h[-12:])
        
        self.lbl_cpu.configure(text=t("CPU: {pct}%  [{spark}]", pct=cpu, spark=spark(cpu_hist)))
        self.cpu_bar.set(cpu / 100.0)
        self.lbl_ram.configure(text=t("RAM: {pct}%  [{spark}]", pct=ram, spark=spark(ram_hist)))
        self.ram_bar.set(ram / 100.0)

        gpu_util, vram_pct, encoder_pct = get_gpu_stats()
        gpu_hist_for_graph = None
        if gpu_util is not None:
            # GPU כאן הוא ניצולת ה-CUDA/shader הכללית, לא ה-NVENC - יכולה
            # להיראות נמוכה גם בזמן רינדור hevc_nvenc/av1_nvenc עמוס לגמרי
            # (הפילטרים delogo/scale/overlay רצים ב-CPU, לא ב-GPU). Encoder
            # למטה הוא המד הרלוונטי בפועל לבדוק אם ה-NVENC עסוק.
            self.lbl_gpu.configure(text=t("GPU: {pct}%", pct=f"{gpu_util:.0f}"))
            self.gpu_bar.set(gpu_util / 100.0)
            self.lbl_vram.configure(text=t("VRAM: {pct}%", pct=f"{vram_pct:.0f}"))
            self.vram_bar.set(vram_pct / 100.0)
            self.lbl_encoder.configure(text=t("Encoder (NVENC): {pct}%", pct=f"{encoder_pct:.0f}"))
            self.encoder_bar.set(encoder_pct / 100.0)
            gpu_hist_for_graph, _vram_hist = get_gpu_performance_history()
        else:
            self.lbl_gpu.configure(text=t("GPU: לא זמין (אין NVIDIA)"))
            self.lbl_vram.configure(text="")
            self.lbl_encoder.configure(text="")

        self._draw_history_graph(cpu_hist, ram_hist, gpu_hist_for_graph)

        self.after(1500, self._update_hw_loop)

    def _draw_history_graph(self, cpu_hist, ram_hist, gpu_hist):
        """מצייר קו ניצולת לאורך זמן ל-CPU/RAM (תמיד) ול-GPU (רק אם יש GPU
        של NVIDIA זמין בכלל - קו שטוח על 0 היה נראה כמו "GPU בניצולת אפס"
        ולא כמו "אין מדידה", בדיוק כמו שהתווית הטקסטואלית כבר מבחינה ביניהם)."""
        canvas = self.history_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return  # עדיין לפני ה-map הראשון של ה-widget - הטיק הבא כבר יראה גודל אמיתי

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

    def update_accent(self, color):
        self.sidebar_title.configure(text_color=color)
        # מרענן את כפתורי הסקריפטים כדי שהדגשת "הסקריפט הנבחר" (fg_color=accent,
        # ראו _make_script_button) תעבור לצבע ערכת הנושא החדשה מיד, לא רק
        # בבחירת סקריפט הבאה.
        self._render_buttons(self._current_script_list)