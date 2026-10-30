# utils/bot/scheduler_store.py
#
# אחסון JSON פשוט למשימות מתוזמנות מה-GUI (להבדיל מ-cogs/scheduler_cog.py,
# שמתזמן משימות קבועות בצד הבוט/Discord ולא ניתן להגדרה מהממשק). הפרדה
# מכוונת מלוגיקת "מתי משימה צריכה לרוץ" (utils/bot/scheduler.py) כדי שקל
# לבדוק כל חלק בנפרד.
import json
import os
import uuid

from utils.shared.atomic_write import atomic_write_json
from utils.shared import data_paths

STORE_PATH = data_paths.path(data_paths.SCHEDULED_TASKS)

VALID_SCHEDULE_TYPES = ("daily", "weekly", "interval_hours")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def load_tasks():
    if not os.path.exists(STORE_PATH):
        return []
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            tasks = json.load(f)
        return tasks if isinstance(tasks, list) else []
    except Exception as e:
        print(f"[scheduler_store] שגיאה בטעינת {STORE_PATH}: {e}")
        return []


def save_tasks(tasks):
    atomic_write_json(STORE_PATH, tasks, ensure_ascii=False, indent=2)


def add_task(script_path, schedule_type, time_str="03:00", weekday="sun", interval_hours=24, folder="", extra_args=None, label=""):
    """schedule_type: 'daily' (בשעה time_str כל יום), 'weekly' (בשעה time_str
    ביום weekday), 'interval_hours' (כל interval_hours שעות מהריצה הקודמת).
    folder/extra_args/label (גל 8, item 91: תזמון מעורך-העל) - תיקיית-קלט ודגלים
    שמועברים לסקריפט בדיוק כמו בהרצה ידנית; ריקים = ההתנהגות הקודמת."""
    if schedule_type not in VALID_SCHEDULE_TYPES:
        raise ValueError(f"schedule_type לא מוכר: {schedule_type}")
    tasks = load_tasks()
    task = {
        "id": str(uuid.uuid4()),
        "script_path": script_path,
        "schedule_type": schedule_type,
        "time": time_str,
        "weekday": weekday,
        "interval_hours": interval_hours,
        "enabled": True,
        "last_run_at": None,
    }
    if folder:
        task["folder"] = folder
    if extra_args:
        task["extra_args"] = [str(a) for a in extra_args]
    if label:
        task["label"] = label
    tasks.append(task)
    save_tasks(tasks)
    return task


def remove_task(task_id):
    tasks = [t for t in load_tasks() if t["id"] != task_id]
    save_tasks(tasks)


def set_enabled(task_id, enabled):
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["enabled"] = enabled
    save_tasks(tasks)


def mark_run(task_id, run_at_iso):
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == task_id:
            t["last_run_at"] = run_at_iso
    save_tasks(tasks)
