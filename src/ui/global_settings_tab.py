# ui/global_settings_tab.py
import datetime
import os
import shutil
import customtkinter as ctk
from tkinter import filedialog, messagebox
from utils.shared.state import state, PALETTE, CONFIG_FILE
from utils.shared.hardware import get_disk_status
from utils.shared.sound import play_system_sound
from utils.shared.i18n import t
from utils.shared import encrypted_backup
from ui.widgets import PassphraseDialog

class GlobalSettingsTabComponent(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self._build_tab()
        self._update_disks_loop()

    def _build_tab(self):
        self.grid_columnconfigure((0, 1), weight=1)
        
        # כרטיסיית דיסקורד וטורבו
        self.card_right = ctk.CTkFrame(self, fg_color=PALETTE["surface_purple"])
        self.card_right.grid(row=0, column=1, sticky="nsew", padx=15, pady=10)
        
        self.webhook_entry = ctk.CTkEntry(self.card_right, placeholder_text="Discord Webhook URL")
        self.webhook_entry.pack(pady=15, padx=15, fill="x")
        self.webhook_entry.insert(0, state.discord_webhook_url)
        
        self.turbo_switch = ctk.CTkSwitch(self.card_right, text=t("🔥 מצב טורבו (סגירת תוכנות רקע במשחק)"))
        self.turbo_switch.pack(pady=10, padx=15, anchor="e")
        if state.turbo_mode_active: self.turbo_switch.select()

        # כרטיסיית גיבוי ומצב לילה
        self.card_left = ctk.CTkFrame(self, fg_color=PALETTE["surface_purple"])
        self.card_left.grid(row=0, column=0, sticky="nsew", padx=15, pady=10)
        
        self.nas_entry = ctk.CTkEntry(self.card_left, placeholder_text=t("כונן חיצוני / NAS"))
        self.nas_entry.pack(pady=5, padx=15, fill="x")
        self.nas_entry.insert(0, state.backup_folder_path)

        ctk.CTkButton(self.card_left, text=t("📂 בחר תיקיית גיבוי"), command=self.choose_backup).pack(pady=5, padx=15, fill="x")

        self.backup_switch = ctk.CTkSwitch(self.card_left, text=t("גיבוי תוצרים אוטומטי לתיקייה שנבחרה בסיום ריצה"))
        self.backup_switch.pack(pady=5, padx=15)
        if state.auto_backup_active: self.backup_switch.select()

        self.night_switch = ctk.CTkSwitch(self.card_left, text=t("💤 מצב לילה (כיבוי אוטומטי בסיום)"))
        self.night_switch.pack(pady=5, padx=15, anchor="e")
        if state.night_mode_active: self.night_switch.select()

        # גיבוי מוצפן - קובץ יחיד (הגדרות + DB + מצב תזמון) שמוגן בסיסמה, בניגוד
        # לגיבוי היומי האוטומטי הקיים (cogs/scheduler_cog.py) שכותב zip/DB גלויים
        # לגמרי תחת data/backups/ - זה מיועד להוצאה בטוחה מהמכונה (דיסק חיצוני/ענן).
        ctk.CTkButton(self.card_left, text=t("🔐 צור גיבוי מוצפן"), command=self.create_encrypted_backup).pack(pady=(10, 5), padx=15, fill="x")
        ctk.CTkButton(self.card_left, text=t("♻️ שחזר מגיבוי מוצפן"), fg_color=PALETTE["border"], command=self.restore_encrypted_backup).pack(pady=(0, 10), padx=15, fill="x")

        # ניהול שירותי רשת - עבר לכאן מהחלון הראשי (היה כרטיס תמידי-גלוי ליד
        # הלוג, "מרגיש כמו הגדרה" יותר מפעולה שוטפת) - ראו gui_manager.pyw's
        # toggle_docker_service/sync_with_bot_tab (נשארו שם, כי הם תלויים
        # ב-card_docker_st/bot_comp שנשארים בחלון הראשי; הכפתורים כאן רק קוראים
        # ל-self.app.<method>()).
        self.services_card = ctk.CTkFrame(self, fg_color=PALETTE["surface_purple"])
        self.services_card.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=10)

        ctk.CTkLabel(self.services_card, text=t("🔌 ניהול שירותי רשת"), font=("Segoe UI", 13, "bold"), text_color=state.current_theme["accent"]).pack(pady=(10, 5), padx=15, anchor="e")

        # 30.10.2026: הקונטיינר מ-config.json ("docker_container"); ריק = בלי מתג
        self.switch_docker = None
        if state.docker_container:
            self.switch_docker = ctk.CTkSwitch(self.services_card, text=f"{t('שרת Docker')} ({state.docker_container})",
                                               command=lambda: self.app.toggle_docker_service())
            self.switch_docker.pack(pady=8, padx=15, anchor="e")

        self.switch_bot_status = ctk.CTkSwitch(self.services_card, text=t("סטטוס ClipForge"), command=lambda: self.app.sync_with_bot_tab())
        self.switch_bot_status.pack(pady=(0, 10), padx=15, anchor="e")

        # מדדי דיסק
        self.card_disks = ctk.CTkFrame(self, fg_color=PALETTE["surface_purple"])
        self.card_disks.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=10)

        ctk.CTkLabel(self.card_disks, text=t("💽 כונן עבודה מקור:")).pack(side="right", padx=10)
        self.disk_bar = ctk.CTkProgressBar(self.card_disks, progress_color=PALETTE["disk_bar"], width=200)
        self.disk_bar.pack(side="right", padx=10, fill="x", expand=True)
        self.lbl_disk_status = ctk.CTkLabel(self.card_disks, text=t("סורק..."))
        self.lbl_disk_status.pack(side="right", padx=10)

        # כפתור שמירה
        ctk.CTkButton(self, text=t("💾 שמור הגדרות גלובליות"), fg_color=state.current_theme["accent"], command=self.save_global_settings).grid(row=3, column=0, columnspan=2, pady=15, padx=15, sticky="ew")

        ctk.CTkButton(self, text=t("🔄 איפוס הגדרות לברירת מחדל"), fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"], command=self.reset_settings).grid(row=4, column=0, columnspan=2, pady=(0, 15), padx=15, sticky="ew")

    def choose_backup(self):
        f = filedialog.askdirectory()
        if f:
            state.backup_folder_path = f
            self.nas_entry.delete(0, 'end')
            self.nas_entry.insert(0, f)
            state.save_config()

    def save_global_settings(self):
        state.discord_webhook_url = self.webhook_entry.get().strip()
        state.turbo_mode_active = self.turbo_switch.get() == 1
        state.night_mode_active = self.night_switch.get() == 1
        state.auto_backup_active = self.backup_switch.get() == 1
        state.save_config()
        play_system_sound("success")

    def reset_settings(self):
        """מגבה את config.json הנוכחי ל-.bak (למקרה שרוצים לשחזר) ואז מאפס את
        כל ההגדרות לברירת מחדל - שימושי כשהגדרה ישנה/לא רלוונטית משתרבבת
        (למשל תיקיית עבודה ישנה) בלי דרך נוחה לנקות אותה חוץ מעריכת JSON ידנית."""
        if not messagebox.askyesno(
            t("🔄 איפוס הגדרות"),
            t("לאפס את כל ההגדרות לברירת מחדל? הגדרות נוכחיות יגובו ל-config.json.bak.\nיידרש הפעלה מחדש של התוכנה.")
        ):
            return
        try:
            if os.path.exists(CONFIG_FILE):
                shutil.copy2(CONFIG_FILE, CONFIG_FILE + ".bak")
        except Exception as e:
            messagebox.showerror(t("שגיאה"), t("הגיבוי נכשל, האיפוס בוטל: {error}", error=e))
            return
        state.reset_to_defaults()
        state.save_config()
        messagebox.showinfo(t("🔄 איפוס הגדרות"), t("ההגדרות אופסו. הפעל מחדש את התוכנה כדי שהשינוי ייכנס לתוקף."))

    def create_encrypted_backup(self):
        dialog = PassphraseDialog(self, t("🔐 גיבוי מוצפן"), t("הזן סיסמה לגיבוי (תידרש שוב בשחזור):"))
        self.wait_window(dialog)
        passphrase = dialog.result
        if not passphrase:
            return

        default_name = f"encrypted_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.ibkp"
        output_path = filedialog.asksaveasfilename(
            title=t("שמור גיבוי מוצפן בשם"), defaultextension=".ibkp",
            initialfile=default_name, filetypes=[("Encrypted Backup", "*.ibkp")],
        )
        if not output_path:
            return

        try:
            result = encrypted_backup.create_backup_bundle(passphrase, output_path)
        except encrypted_backup.BackupError as e:
            messagebox.showerror(t("שגיאה"), str(e))
            return
        messagebox.showinfo(
            t("🔐 גיבוי מוצפן"),
            t("הגיבוי נוצר בהצלחה ({count} קבצים):\n{path}", count=len(result["included_files"]), path=output_path),
        )

    def restore_encrypted_backup(self):
        input_path = filedialog.askopenfilename(title=t("בחר קובץ גיבוי מוצפן"), filetypes=[("Encrypted Backup", "*.ibkp")])
        if not input_path:
            return
        if not messagebox.askyesno(
            t("♻️ שחזור מגיבוי מוצפן"),
            t("לשחזר מהגיבוי הזה? כל קובץ קיים שיידרס יגובה קודם ל-.bak, אבל מומלץ לוודא שהבוט אינו פעיל.\nיידרש הפעלה מחדש של התוכנה."),
        ):
            return

        dialog = PassphraseDialog(self, t("♻️ שחזור מגיבוי מוצפן"), t("הזן את הסיסמה של הגיבוי הזה:"))
        self.wait_window(dialog)
        passphrase = dialog.result
        if not passphrase:
            return

        try:
            result = encrypted_backup.restore_backup_bundle(passphrase, input_path)
        except encrypted_backup.BackupError as e:
            messagebox.showerror(t("שגיאה"), str(e))
            return
        messagebox.showinfo(
            t("♻️ שחזור מגיבוי מוצפן"),
            t("שוחזרו {count} קבצים. הפעל מחדש את התוכנה כדי שהשינוי ייכנס לתוקף.", count=len(result["restored_files"])),
        )

    def _update_disks_loop(self):
        p = state.selected_gameplay_folder if state.selected_gameplay_folder else "."
        used_p, free_gb = get_disk_status(p)
        self.disk_bar.set(used_p)
        self.lbl_disk_status.configure(text=t("{gb} GB פנוי", gb=f"{free_gb:.1f}"))
        self.after(10000, self._update_disks_loop)