import customtkinter as ctk
import os
import subprocess
import sys
import threading
import time
from utils.shared import db
from utils.shared.crash_supervisor import record_crash_and_check_giveup
from utils.shared.python_locator import get_python_executable
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared.state import PALETTE
from utils.shared.gui_thread import MainThreadDispatcher
from utils.shared.i18n import t
from utils.shared import data_paths

# כמה קריסות בלתי-צפויות (התהליך יצא לבד, לא כי המשתמש לחץ "כבה בוט") מותר
# לספוג ב-5 הדקות האחרונות לפני שמפסיקים לנסות להפעיל מחדש אוטומטית ומחכים
# להתערבות ידנית - ראו utils/shared/crash_supervisor.py.
MAX_AUTO_RESTARTS = 5
AUTO_RESTART_WINDOW_SECONDS = 300

# זהה ל-CONFIG_ERROR_EXIT_CODE ב-main.py (אין טוקן / Discord דחה אותו / חסר Intent) - הפעלה מחדש לא תעזור,
# לכן לא מפעילים מחדש. לא מייבאים מ-main.py: הייבוא שלו עוטף את stdout ובודק טוקן.
BOT_CONFIG_ERROR_EXIT_CODE = 2

FONT_FAMILY = "Segoe UI" if sys.platform == "win32" else "Helvetica"
FONT_SUBTITLE = (FONT_FAMILY, 16, "bold")
FONT_BODY = (FONT_FAMILY, 14)
FONT_LOGS = ("Consolas", 13)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAIN_PY_PATH = os.path.join(BASE_DIR, "src", "entrypoints", "main.py")

# הבוט (main.py) ניגש לאותו קובץ DB דרך aiosqlite - כאן ניגשים אליו סינכרונית מה-GUI
# כדי שהוספה/מחיקה של פיד או משחק תשפיע מיד גם על הבוט וגם על ה-GUI, בלי כפילות מקורות
DB_PATH = data_paths.path(data_paths.BOT_DB)

class BotTabComponent(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        
        self.bot_process = None
        self.is_running = False
        self.crash_timestamps = []  # קריסות בלתי-צפויות אחרונות - ראו utils/shared/crash_supervisor.py
        # run_bot_process() קורא ל-write_to_log() מ-thread רקע (הבוט עצמו) לכל
        # שורת פלט - עדכון ישיר של widget מ-thread שאינו הראשי לא בטוח, ראו
        # utils/shared/gui_thread.py.
        self._dispatcher = MainThreadDispatcher()

        # יצירת טאבים פנימיים לניהול הבוט
        self.bot_tabs = ctk.CTkTabview(self, corner_radius=10)
        self.bot_tabs.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_dash = self.bot_tabs.add(t("בקרה ולוגים"))
        self.tab_rss = self.bot_tabs.add("RSS & AI")
        self.tab_steam = self.bot_tabs.add("Steam")

        self._ensure_tables()
        self.build_dashboard()
        self.build_rss()
        self.build_steam()
        self._drain_dispatcher()

    def _drain_dispatcher(self):
        self._dispatcher.drain()
        if self.winfo_exists():
            self.after(50, self._drain_dispatcher)

    def _ensure_tables(self):
        """יוצר את הטבלאות אם ה-GUI נפתח לפני שהבוט רץ ולו פעם אחת."""
        with db.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rss_feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT, url TEXT, channel_id INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS steam_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT, app_id TEXT, channel_id INTEGER
                )
            """)

    # --- מסך בקרה ולוגים ---
    def build_dashboard(self):
        control_frame = ctk.CTkFrame(self.tab_dash, fg_color="transparent")
        control_frame.pack(fill="x", pady=10)

        self.btn_toggle_bot = ctk.CTkButton(
            control_frame, text=t("הפעל בוט 🚀"), font=(FONT_FAMILY, 15, "bold"),
            fg_color=PALETTE["success_btn"], hover_color=PALETTE["success_btn_hover"], command=self.toggle_bot
        )
        self.btn_toggle_bot.pack(side="right", padx=20)

        self.lbl_status = ctk.CTkLabel(control_frame, text=t("סטטוס בוט: כבוי 🔴"), font=FONT_SUBTITLE)
        self.lbl_status.pack(side="right", padx=20)
        
        self.log_textbox = ctk.CTkTextbox(self.tab_dash, font=FONT_LOGS)
        self.log_textbox.pack(padx=10, pady=10, fill="both", expand=True)
        self.log_textbox.configure(state="disabled")

    # --- מסך RSS ---
    def build_rss(self):
        form = ctk.CTkFrame(self.tab_rss)
        form.pack(fill="x", padx=10, pady=10)
        
        self.rss_chan = ctk.CTkEntry(form, placeholder_text=t("ערוץ דיסקורד ID"), justify="right")
        self.rss_chan.pack(side="right", padx=5, expand=True, fill="x")
        self.rss_url = ctk.CTkEntry(form, placeholder_text=t("כתובת RSS"), justify="left")
        self.rss_url.pack(side="right", padx=5, expand=True, fill="x")
        self.rss_name = ctk.CTkEntry(form, placeholder_text=t("שם המקור"), justify="right")
        self.rss_name.pack(side="right", padx=5, expand=True, fill="x")

        btn_add = ctk.CTkButton(form, text=t("הוסף מקור"), command=self.add_rss)
        btn_add.pack(side="right", padx=5)
        
        self.rss_list_frame = ctk.CTkScrollableFrame(self.tab_rss)
        self.rss_list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.refresh_rss_list()

    def add_rss(self):
        name, url, chan = self.rss_name.get().strip(), self.rss_url.get().strip(), self.rss_chan.get().strip()
        if name and url and chan:
            try:
                with db.connect(DB_PATH) as conn:
                    conn.execute(
                        "INSERT INTO rss_feeds (name, url, channel_id) VALUES (?, ?, ?)",
                        (name, url, int(chan))
                    )
                self.rss_name.delete(0, "end")
                self.rss_url.delete(0, "end")
                self.rss_chan.delete(0, "end")
                self.refresh_rss_list()
            except ValueError:
                pass  # channel_id לא מספרי - מתעלמים בשקט מהשדה

    def delete_rss(self, feed_id):
        with db.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
        self.refresh_rss_list()

    def refresh_rss_list(self):
        for w in self.rss_list_frame.winfo_children(): w.destroy()
        with db.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT id, name, url, channel_id FROM rss_feeds").fetchall()
        for feed_id, name, url, channel_id in rows:
            frame = ctk.CTkFrame(self.rss_list_frame)
            frame.pack(fill="x", pady=2)
            ctk.CTkLabel(frame, text=t("📰 {name} | ערוץ: {channel_id}", name=name, channel_id=channel_id), font=FONT_BODY).pack(side="right", padx=10)
            ctk.CTkButton(frame, text=t("מחיקה"), fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"], width=60, command=lambda fid=feed_id: self.delete_rss(fid)).pack(side="left", padx=10, pady=5)

    # --- מסך Steam ---
    def build_steam(self):
        form = ctk.CTkFrame(self.tab_steam)
        form.pack(fill="x", padx=10, pady=10)
        
        self.stm_chan = ctk.CTkEntry(form, placeholder_text=t("ערוץ דיסקורד ID"), justify="right")
        self.stm_chan.pack(side="right", padx=5, expand=True, fill="x")
        self.stm_appid = ctk.CTkEntry(form, placeholder_text="App ID", justify="left")
        self.stm_appid.pack(side="right", padx=5, expand=True, fill="x")
        self.stm_name = ctk.CTkEntry(form, placeholder_text=t("שם משחק"), justify="right")
        self.stm_name.pack(side="right", padx=5, expand=True, fill="x")

        btn_add = ctk.CTkButton(form, text=t("עקוב"), command=self.add_steam)
        btn_add.pack(side="right", padx=5)
        
        self.stm_list_frame = ctk.CTkScrollableFrame(self.tab_steam)
        self.stm_list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.refresh_stm_list()

    def add_steam(self):
        name, appid, chan = self.stm_name.get().strip(), self.stm_appid.get().strip(), self.stm_chan.get().strip()
        if name and appid and chan:
            try:
                with db.connect(DB_PATH) as conn:
                    conn.execute(
                        "INSERT INTO steam_games (name, app_id, channel_id) VALUES (?, ?, ?)",
                        (name, appid, int(chan))
                    )
                self.stm_name.delete(0, "end")
                self.stm_appid.delete(0, "end")
                self.stm_chan.delete(0, "end")
                self.refresh_stm_list()
            except ValueError:
                pass  # channel_id לא מספרי - מתעלמים בשקט מהשדה

    def delete_steam(self, game_id):
        with db.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM steam_games WHERE id = ?", (game_id,))
        self.refresh_stm_list()

    def refresh_stm_list(self):
        for w in self.stm_list_frame.winfo_children(): w.destroy()
        with db.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT id, name, app_id, channel_id FROM steam_games").fetchall()
        for game_id, name, app_id, channel_id in rows:
            frame = ctk.CTkFrame(self.stm_list_frame)
            frame.pack(fill="x", pady=2)
            ctk.CTkLabel(frame, text=t("🎮 {name} ({app_id}) | ערוץ: {channel_id}", name=name, app_id=app_id, channel_id=channel_id), font=FONT_BODY).pack(side="right", padx=10)
            ctk.CTkButton(frame, text=t("מחיקה"), fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"], width=60, command=lambda gid=game_id: self.delete_steam(gid)).pack(side="left", padx=10, pady=5)

    # --- פונקציות הרצת הבוט ---
    def toggle_bot(self):
        if self.is_running:
            if self.bot_process:
                self.bot_process.terminate()
                self.bot_process = None
            self.is_running = False
            self.btn_toggle_bot.configure(text=t("הפעל בוט 🚀"), fg_color=PALETTE["success_btn"], hover_color=PALETTE["success_btn_hover"])
            self.lbl_status.configure(text=t("סטטוס בוט: כבוי 🔴"))
            self.write_to_log(t("\n--- הבוט כובה על ידי המשתמש ---"))
        else:
            self.is_running = True
            self.crash_timestamps = []
            self.btn_toggle_bot.configure(text=t("כבה בוט 🛑"), fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"])
            self.lbl_status.configure(text=t("סטטוס בוט: מחובר ורץ 🟢"))
            threading.Thread(target=self.run_bot_process, daemon=True).start()

    def run_bot_process(self):
        # לולאה (לא ריצה חד-פעמית) - אם התהליך יוצא בלי שהמשתמש ביקש (קריסה),
        # מפעילים אותו מחדש אוטומטית, עד MAX_AUTO_RESTARTS קריסות תוך
        # AUTO_RESTART_WINDOW_SECONDS (ראו utils/shared/crash_supervisor.py) - אחרת
        # עלולה להיווצר לולאת קריסה-הפעלה-קריסה אינסופית על תקלה קבועה.
        while self.is_running:
            # שומרים הפניה מקומית (proc) ולא חוזרים לקרוא את self.bot_process
            # לאורך הפונקציה: toggle_bot() (thread ראשי) יכול לאפס אותו ל-None
            # בדיוק תוך כדי שהריצה הזו עדיין משתמשת בו - אותו מרוץ בדיוק שכבר
            # תוקן ב-utils/shared/worker.py (terminate_current). proc.wait() על משתנה
            # מקומי בטוח תמיד, גם אם self.bot_process כבר None.
            returncode = None
            try:
                proc = subprocess.Popen(
                    [get_python_executable(), MAIN_PY_PATH], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", bufsize=1,
                    creationflags=NO_WINDOW_FLAGS
                )
                self.bot_process = proc
                for line in iter(proc.stdout.readline, ""):
                    self.write_to_log(line)
                returncode = proc.wait()
            except Exception as e:
                self.write_to_log(t("\n[שגיאה בהרצה]: {error}", error=e))
            self.bot_process = None

            if not self.is_running:
                # כיבוי יזום על ידי המשתמש (toggle_bot כבר עדכן סטטוס/כפתור) - לא קריסה
                return

            if returncode == BOT_CONFIG_ERROR_EXIT_CODE:
                # שגיאת הגדרה (ההודעה של main.py כבר בלוג) - לא קריסה, ולא מפעילים מחדש 5 פעמים לשווא
                self.is_running = False
                self.write_to_log(t("\n[שגיאת הגדרה] הבוט לא הופעל מחדש - תקן את ההגדרה שמופיעה למעלה ולחץ שוב על 'הפעל בוט'."))
                self._dispatcher.call_soon(self._on_bot_config_error)
                return

            self.crash_timestamps, give_up = record_crash_and_check_giveup(
                self.crash_timestamps, time.time(), AUTO_RESTART_WINDOW_SECONDS, MAX_AUTO_RESTARTS
            )
            if give_up:
                self.is_running = False
                self.write_to_log(t(
                    "\n[קריסה חוזרת] הבוט קרס {n} פעמים ב-5 הדקות האחרונות - עצירת ניסיונות הפעלה מחדש אוטומטיים. "
                    "תקן את הבעיה ולחץ שוב על 'הפעל בוט' ידנית.", n=len(self.crash_timestamps)
                ))
                self._dispatcher.call_soon(self._on_bot_gave_up)
                return

            self.write_to_log(t(
                "\n[קריסה] הבוט נסגר בלי שביקשת - מפעיל מחדש אוטומטית ({n}/{max})...",
                n=len(self.crash_timestamps), max=MAX_AUTO_RESTARTS
            ))
            time.sleep(3)

    def _on_bot_gave_up(self):
        self.btn_toggle_bot.configure(text=t("הפעל בוט 🚀"), fg_color=PALETTE["success_btn"], hover_color=PALETTE["success_btn_hover"])
        self.lbl_status.configure(text=t("סטטוס בוט: קרס - נדרשת הפעלה ידנית 🔴"))

    def _on_bot_config_error(self):
        self.btn_toggle_bot.configure(text=t("הפעל בוט 🚀"), fg_color=PALETTE["success_btn"], hover_color=PALETTE["success_btn_hover"])
        self.lbl_status.configure(text=t("סטטוס בוט: שגיאת הגדרה - ראו את הלוג 🔴"))

    def write_to_log(self, text):
        # run_bot_process() קורא לזה מ-thread רקע לכל שורת פלט - לכן תמיד עובר
        # דרך ה-dispatcher (בטוח גם כשנקרא מה-thread הראשי, כמו ב-toggle_bot).
        self._dispatcher.call_soon(self._do_write_to_log, text)

    def _do_write_to_log(self, text):
        if self.log_textbox.winfo_exists():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", text)
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")