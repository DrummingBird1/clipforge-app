# ui/scheduler_tab.py
import glob
import os
import customtkinter as ctk

from utils.shared.state import PALETTE
from utils.shared.script_metadata import get_script_metadata
from utils.bot import scheduler_store
from utils.shared.sound import play_system_sound
from utils.shared.i18n import t, fix_hebrew_word_order

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE_DIR, "my_scripts")

SCHEDULE_TYPE_LABELS = {
    "daily": t("יומי"),
    "weekly": t("שבועי"),
    "interval_hours": t("כל X שעות"),
}
SCHEDULE_TYPE_BY_LABEL = {v: k for k, v in SCHEDULE_TYPE_LABELS.items()}

WEEKDAY_LABELS = {
    "sun": t("ראשון"), "mon": t("שני"), "tue": t("שלישי"), "wed": t("רביעי"),
    "thu": t("חמישי"), "fri": t("שישי"), "sat": t("שבת"),
}
WEEKDAY_BY_LABEL = {v: k for k, v in WEEKDAY_LABELS.items()}


class SchedulerTabComponent(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._script_by_display_name = {}
        self._build_tab()
        self.refresh_task_list()

    def _build_tab(self):
        form = ctk.CTkFrame(self, fg_color=PALETTE["surface_purple"])
        form.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(form, text=t("⏰ הוסף משימה מתוזמנת חדשה"), font=("Segoe UI", 13, "bold")).pack(pady=(12, 8), anchor="e", padx=15)

        scripts = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.py"), recursive=True))
        # fix_hebrew_word_order כי השם מוצג לבד ב-CTkOptionMenu - ראו
        # utils/shared/script_metadata.py למה get_script_metadata() כבר לא מפעיל את זה בעצמו.
        self._script_by_display_name = {fix_hebrew_word_order(get_script_metadata(p)["name"]): p for p in scripts}
        display_names = list(self._script_by_display_name.keys()) or [t("אין סקריפטים זמינים")]

        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=4)
        ctk.CTkLabel(row1, text=t("סקריפט:"), width=90, anchor="e").pack(side="right", padx=(5, 0))
        self.script_combo = ctk.CTkOptionMenu(row1, values=display_names, width=260)
        self.script_combo.pack(side="right", padx=5)

        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=4)
        ctk.CTkLabel(row2, text=t("תדירות:"), width=90, anchor="e").pack(side="right", padx=(5, 0))
        self.schedule_type_combo = ctk.CTkOptionMenu(row2, values=list(SCHEDULE_TYPE_LABELS.values()), width=120)
        self.schedule_type_combo.pack(side="right", padx=5)

        ctk.CTkLabel(row2, text=t("שעה (HH:MM):"), anchor="e").pack(side="right", padx=(15, 0))
        self.time_entry = ctk.CTkEntry(row2, width=70, placeholder_text="03:00")
        self.time_entry.pack(side="right", padx=5)

        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.pack(fill="x", padx=15, pady=4)
        ctk.CTkLabel(row3, text=t("יום (לשבועי):"), width=90, anchor="e").pack(side="right", padx=(5, 0))
        self.weekday_combo = ctk.CTkOptionMenu(row3, values=list(WEEKDAY_LABELS.values()), width=120)
        self.weekday_combo.pack(side="right", padx=5)

        ctk.CTkLabel(row3, text=t("מספר שעות (ל'כל X שעות'):"), anchor="e").pack(side="right", padx=(15, 0))
        self.interval_entry = ctk.CTkEntry(row3, width=70, placeholder_text="24")
        self.interval_entry.pack(side="right", padx=5)

        ctk.CTkButton(form, text=t("➕ הוסף משימה מתוזמנת"), command=self.add_task).pack(pady=(8, 15), padx=15, fill="x")

        ctk.CTkLabel(self, text=t("📋 משימות מתוזמנות"), font=("Segoe UI", 13, "bold")).pack(pady=(5, 5), anchor="e", padx=25)
        self.task_list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.task_list_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def add_task(self):
        display_name = self.script_combo.get()
        script_path = self._script_by_display_name.get(display_name)
        if not script_path:
            return

        schedule_type = SCHEDULE_TYPE_BY_LABEL.get(self.schedule_type_combo.get(), "daily")
        time_str = self.time_entry.get().strip() or "03:00"
        weekday = WEEKDAY_BY_LABEL.get(self.weekday_combo.get(), "sun")
        try:
            interval_hours = max(1, int(self.interval_entry.get().strip() or "24"))
        except ValueError:
            interval_hours = 24

        scheduler_store.add_task(script_path, schedule_type, time_str=time_str, weekday=weekday, interval_hours=interval_hours)
        play_system_sound("success")
        self.refresh_task_list()

    def _describe_schedule(self, task):
        if task["schedule_type"] == "daily":
            return t("כל יום ב-{time}", time=task["time"])
        if task["schedule_type"] == "weekly":
            return t("כל {weekday} ב-{time}", weekday=WEEKDAY_LABELS.get(task["weekday"], task["weekday"]), time=task["time"])
        return t("כל {hours} שעות", hours=task["interval_hours"])

    def refresh_task_list(self):
        for w in self.task_list_frame.winfo_children():
            w.destroy()

        tasks = scheduler_store.load_tasks()
        if not tasks:
            ctk.CTkLabel(self.task_list_frame, text=t("אין משימות מתוזמנות עדיין."), text_color=PALETTE["text_muted"]).pack(pady=10)
            return

        for task in tasks:
            row = ctk.CTkFrame(self.task_list_frame, fg_color=PALETTE["surface_alt"])
            row.pack(fill="x", pady=3, padx=2)

            script_name = get_script_metadata(task["script_path"])["name"]
            ctk.CTkLabel(row, text=f"{script_name} - {self._describe_schedule(task)}", anchor="e").pack(side="right", padx=10, pady=8)

            ctk.CTkButton(row, text=t("🗑️ מחק"), width=60, fg_color=PALETTE["danger"], hover_color=PALETTE["danger_hover"],
                          command=lambda tid=task["id"]: self.delete_task(tid)).pack(side="left", padx=5, pady=5)

            enabled_var = ctk.BooleanVar(value=task["enabled"])
            ctk.CTkSwitch(row, text=t("פעיל"), variable=enabled_var, width=60, onvalue=True, offvalue=False,
                          command=lambda tid=task["id"], var=enabled_var: self.toggle_task(tid, var.get())).pack(side="left", padx=5, pady=5)

    def delete_task(self, task_id):
        scheduler_store.remove_task(task_id)
        play_system_sound("start")
        self.refresh_task_list()

    def toggle_task(self, task_id, is_enabled):
        scheduler_store.set_enabled(task_id, bool(is_enabled))
