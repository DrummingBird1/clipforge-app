# ui/widgets.py
#
# ווידג'טים עצמאיים ופונטים משותפים שהיו מוגדרים בראש gui_manager.pyw - בלי
# תלות ב-LauncherApp עצמו (רק בפרמטרים שכבר מועברים לבנאי), כך שהיה אפשר
# להעביר אותם לכאן כמעט מילה במילה. חלק מהעבודה על צמצום גודל gui_manager.pyw.

import os
import sys
import time
import tkinter as tk

import customtkinter as ctk

from utils.shared.state import PALETTE
from utils.shared.script_metadata import get_script_metadata
from utils.shared.i18n import t, fix_hebrew_word_order

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"
# סקאלת טיפוגרפיה - עד כה כל הפונטים המשותפים (כותרת/כותרת-משנה/טקסט-גוף/תגית)
# היו bold, כולל טקסט-גוף רגיל (תוויות, checkbox, entry) - בלי שום היררכיה
# ויזואלית בין כותרת לתוכן, מה שגורם למסכים להרגיש "צועקים" באופן אחיד. עכשיו
# רק כותרות/הדגשה אמיתית הן bold; FONT_HEBREW_TEXT (טקסט-גוף, השימוש הנפוץ
# ביותר) חזר למשקל רגיל. FONT_HEBREW_TEXT_BOLD קיים למקומות שבאמת רוצים הדגשה
# מפורשת בתוך טקסט-גוף (למשל מצב נבחר/פעיל).
FONT_HEBREW_TITLE = (FONT_FAMILY, 20, "bold")
FONT_HEBREW_SUB = (FONT_FAMILY, 13, "bold")
FONT_HEBREW_TEXT = (FONT_FAMILY, 11, "normal")
FONT_HEBREW_TEXT_BOLD = (FONT_FAMILY, 11, "bold")
FONT_BADGE = (FONT_FAMILY, 9, "bold")
FONT_LOGS = ("Consolas", 10)


class Spinner:
    """אנימציית טעינה קלה (תווי braille מסתובבים) על CTkLabel קיים - למצבי המתנה
    בלתי-קבועים (בלי אחוז התקדמות אמיתי, כמו "בודק..."), שקודם היו טקסט סטטי
    בלבד. לא דורש שום asset חיצוני (גופן/תמונה) - רק תווי Unicode רגילים.
    start()/stop() שולטים על הלולאה; stop() לא משנה את הטקסט - הקורא אחראי
    להחליף אותו בהודעת סיום."""
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, widget, label, text_template="{spinner} {label}", interval_ms=90):
        self.widget = widget
        self.label = label
        self.text_template = text_template
        self.interval_ms = interval_ms
        self._frame_index = 0
        self._running = False
        self._after_id = None

    def start(self):
        self._running = True
        self._tick()

    def _tick(self):
        if not self._running or not self.widget.winfo_exists():
            return
        frame = self.FRAMES[self._frame_index % len(self.FRAMES)]
        self._frame_index += 1
        self.widget.configure(text=self.text_template.format(spinner=frame, label=self.label))
        self._after_id = self.widget.after(self.interval_ms, self._tick)

    def stop(self):
        self._running = False
        if self._after_id is not None:
            try:
                if self.widget.winfo_exists():
                    self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


class TextRedirector:
    """מזרים stdout/stderr גם ל-widget (log_callback, מובטח thread-safe דרכו)
    וגם הלאה לזרם המקורי - שבשלב הזה כבר עטוף ב-_TeeStream של
    setup_persistent_logging (utils/shared/logging_setup.py). בלי ה-forwarding הזה
    sys.stdout = TextRedirector(...) היה *מחליף* את ה-_TeeStream לגמרי (לא
    עוטף אותו) - כל print() אחרי האתחול היה מגיע רק ל-widget של ה-GUI ואף
    פעם לא ל-data/logs/gui.log, מה שהשאיר את הקובץ ריק תמיד."""
    def __init__(self, log_callback, category="INFO", prefix="ℹ️", original_stream=None):
        self.log_callback = log_callback
        self.category = category
        self.prefix = prefix
        self._original = original_stream

    def write(self, string):
        if self._original is not None:
            try:
                self._original.write(string)
            except Exception:
                pass
        cleaned = string.strip()
        if cleaned:
            self.log_callback(self.category, cleaned, self.prefix)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass


class CommandPalette(ctk.CTkToplevel):
    def __init__(self, parent, scripts, on_select):
        super().__init__(parent)
        self.title(t("🔍 חיפוש פקודות וסקריפטים"))
        self.geometry("500x320")
        self.configure(fg_color=PALETTE["bg_root"])
        self.transient(parent)
        self.grab_set()

        self.on_select = on_select
        self.scripts = scripts

        self.entry = ctk.CTkEntry(self, placeholder_text=t("חפש סקריפט... (Ctrl+K)"), font=FONT_HEBREW_TEXT, height=35, justify="right")
        self.entry.pack(fill="x", padx=15, pady=15)
        self.entry.bind("<KeyRelease>", self.filter_list)

        self.listbox_frame = ctk.CTkScrollableFrame(self, fg_color=PALETTE["surface"])
        self.listbox_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.populate("")

    def populate(self, query):
        for child in self.listbox_frame.winfo_children():
            child.destroy()

        for script in self.scripts:
            script_name = get_script_metadata(script)["name"]
            if query.lower() in os.path.basename(script).lower() or query.lower() in script_name.lower():
                btn = ctk.CTkButton(
                    self.listbox_frame, text=fix_hebrew_word_order(script_name), font=FONT_HEBREW_TEXT,
                    anchor="e", fg_color="transparent", hover_color=PALETTE["border"],
                    command=lambda s=script: self.select_script(s)
                )
                btn.pack(fill="x", pady=2)

    def filter_list(self, event):
        self.populate(self.entry.get())

    def select_script(self, script):
        self.on_select(script)
        self.destroy()


class PassphraseDialog(ctk.CTkToplevel):
    """דיאלוג סיסמה ממוסך (show="•") - customtkinter's CTkInputDialog המובנה
    לא תומך במיסוך טקסט בכלל, לא מתאים לסיסמת גיבוי. חסימה סינכרונית דרך
    self.wait_window(dialog) בקוד הקורא (אותו דפוס בדיוק כמו tkinter.simpledialog
    הרגיל), ואז קורא ל-dialog.result."""
    def __init__(self, parent, title, prompt):
        super().__init__(parent)
        self.title(title)
        self.geometry("360x170")
        self.configure(fg_color=PALETTE["bg_root"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None

        ctk.CTkLabel(self, text=prompt, font=FONT_HEBREW_TEXT, wraplength=320).pack(padx=15, pady=(15, 5), anchor="e")
        self.entry = ctk.CTkEntry(self, show="•", font=FONT_HEBREW_TEXT, justify="right")
        self.entry.pack(fill="x", padx=15, pady=5)
        self.entry.bind("<Return>", lambda _e: self._submit())
        self.entry.focus_set()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=15)
        ctk.CTkButton(btn_row, text=t("אישור"), command=self._submit).pack(side="right", padx=5)
        ctk.CTkButton(btn_row, text=t("ביטול"), fg_color=PALETTE["border"], command=self.destroy).pack(side="right", padx=5)

    def _submit(self):
        self.result = self.entry.get()
        self.destroy()


class Tooltip:
    """טולטיפ hover קל (item: הסבר קצר על כל הגדרה בעורך-העל) - customtkinter
    אין לו רכיב tooltip מובנה, אז זה Toplevel בלי מסגרת שמוצג ליד העכבר.
    show_delay_ms דוחה את ההופעה כדי שמעבר-עכבר חולף בין widgets לא יהבהב
    טולטיפים כל הזמן; ההסתרה (Leave/לחיצה) מיידית. widget.after/after_cancel
    (לא threading.Timer) כדי שהתזמון ירוץ על ה-Tk event loop הרגיל, כמו כל
    טיימר אחר ב-UI הזה (ראו Spinner למעלה)."""
    _SHOW_DELAY_MS = 450

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel_pending()
        self._after_id = self.widget.after(self._SHOW_DELAY_MS, self._show)

    def _cancel_pending(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        self._after_id = None
        if self._tip is not None or not self.text or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        try:
            self._tip.attributes("-topmost", True)
        except Exception:
            pass  # לא קריטי - חלונות ישנים/מנהלי-חלונות לא-סטנדרטיים עדיין יציגו את הטולטיפ, רק אולי לא תמיד מעל הכל
        tk.Label(
            self._tip, text=t(self.text), justify="right", background=PALETTE["surface_alt"],
            foreground=PALETTE["text_dim"], relief="solid", borderwidth=1, wraplength=280,
            font=FONT_HEBREW_TEXT, padx=8, pady=5,
        ).pack()

    def _hide(self, _event=None):
        self._cancel_pending()
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def update_text(self, text):
        self.text = text


class NotificationDrawer(ctk.CTkFrame):
    def __init__(self, parent, accent_color):
        super().__init__(parent, fg_color=PALETTE["surface"], border_width=1, border_color=accent_color, width=280)
        self.accent = accent_color

        lbl = ctk.CTkLabel(self, text=t("🔔 מרכז התראות"), font=FONT_HEBREW_SUB, text_color=accent_color)
        lbl.pack(pady=10, padx=10, anchor="ne")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=PALETTE["bg_root"])
        self.scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def add_notification(self, text):
        t_str = time.strftime("%H:%M:%S")
        lbl = ctk.CTkLabel(self.scroll, text=f"[{t_str}] {text}", font=FONT_BADGE, text_color=PALETTE["text_dim"], wraplength=230, anchor="e")
        lbl.pack(fill="x", pady=4, padx=4)
