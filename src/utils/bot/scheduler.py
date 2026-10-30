# utils/bot/scheduler.py
#
# בודק אם משימה מתוזמנת (utils/bot/scheduler_store.py) "צריכה לרוץ עכשיו", ומריץ
# אותה דרך אותו utils/shared/worker.py שהכפתור "הרץ סקריפט" משתמש בו - כדי שלא
# תהיה שום התנהגות כפולה בין הרצה ידנית להרצה מתוזמנת. נבדק פעם בדקה
# מ-thread הראשי (ראו gui_manager.pyw) - אין thread נפרד משלו.
import datetime
import os

from utils.shared import job_history
from utils.shared.script_metadata import get_script_metadata
from utils.bot.scheduler_store import load_tasks, mark_run

WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_reported_broken_tasks: set = set()


def _parse_last_run(last_run_at):
    if not last_run_at:
        return None
    try:
        return datetime.datetime.fromisoformat(last_run_at)
    except ValueError:
        return None


def is_due(task, now):
    """קובע האם task צריך לרוץ ברגע now (datetime), בלי שום side effect -
    נבדק בנפרד מ-check_and_run_due_tasks() כדי שקל לבדוק את הלוגיקה עצמה."""
    if not task.get("enabled", True):
        return False

    last_run = _parse_last_run(task.get("last_run_at"))
    schedule_type = task.get("schedule_type")

    if schedule_type == "interval_hours":
        if last_run is None:
            return True
        hours = task.get("interval_hours", 24)
        return (now - last_run) >= datetime.timedelta(hours=hours)

    if schedule_type in ("daily", "weekly"):
        try:
            hour, minute = (int(p) for p in task.get("time", "03:00").split(":"))
        except ValueError:
            hour, minute = 3, 0
        scheduled_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if schedule_type == "weekly":
            # המועד השבועי האחרון שכבר הגיע (היום או עד 6 ימים אחורה)
            weekday = WEEKDAY_INDEX.get(task.get("weekday", "sun"), 6)
            latest = scheduled_today - datetime.timedelta(days=(now.weekday() - weekday) % 7)
            if latest > now:
                latest -= datetime.timedelta(days=7)
            if last_run is None:
                # משימה חדשה מתחילה ביום שלה - לא מיד כשהיא נוצרת
                return latest.date() == now.date()
            # המחשב ישן במועד: רצה פעם אחת כשהוא מתעורר (כמו היומית), ואז חוזרת ליום שלה.
            # לפי תאריך, כמו ביומית - לא פעמיים באותו יום גם אם שינו את השעה.
            return last_run.date() < latest.date()
        if now < scheduled_today:
            return False
        # כבר רץ היום (לא משנה באיזו שעה) - לא רץ פעמיים באותו יום
        return last_run is None or last_run.date() < now.date()

    return False


def check_and_run_due_tasks(worker, now=None):
    """עובר על כל המשימות המתוזמנות, מריץ את מה שצריך דרך worker.add_script_task()
    (אותו מסלול שהכפתור "הרץ סקריפט" משתמש בו), ומעדכן last_run_at. מחזיר
    את רשימת המשימות שהופעלו בקריאה הזו (לצורך לוג/בדיקה)."""
    now = now or datetime.datetime.now()
    triggered = []
    for task in load_tasks():
        # משימה פגומה בקובץ (interval_hours לא מספר, תאריך עם אזור זמן, בלי script_path) - מדלגים רק עליה.
        # קודם החריגה עצרה את כל הבדיקה, וכל המשימות שאחריה ברשימה לא רצו אף פעם.
        try:
            if not is_due(task, now):
                continue
            script_path = task["script_path"]
        except Exception as e:
            task_id = task.get("id", "?") if isinstance(task, dict) else "?"
            # הבדיקה רצה כל 30-60 שניות - הודעה אחת לכל תקלה, לא שורה בלוג בכל סבב
            if (task_id, str(e)) not in _reported_broken_tasks:
                _reported_broken_tasks.add((task_id, str(e)))
                print(f"[scheduler] דילוג על משימה פגומה ({task_id}): {e}")
            continue

        concurrency = get_script_metadata(script_path).get("concurrency", "heavy")
        started_at = now.isoformat(timespec="seconds")

        def _on_finish(outcome, _script_path=script_path, _started_at=started_at):
            success = outcome.get("returncode") == 0 if outcome else False
            job_history.record_job(
                f"⏰ {os.path.basename(_script_path)}",
                "success" if success else "failed",
                _started_at, datetime.datetime.now().isoformat(timespec="seconds"),
                0.0, result=outcome.get("result") if outcome else None,
            )

        # folder/extra_args (גל 8, item 91): משימה שנוצרה מעורך-העל רצה על התיקייה
        # ועם הדגלים שנשמרו בה - משימות ישנות (בלעדיהם) רצות בדיוק כמו קודם.
        extra_args = task.get("extra_args") if isinstance(task.get("extra_args"), list) else None
        worker.add_script_task(script_path, task.get("folder", ""), _on_finish, concurrency=concurrency, extra_args=extra_args)
        mark_run(task["id"], now.isoformat(timespec="seconds"))
        triggered.append(task)

    return triggered
