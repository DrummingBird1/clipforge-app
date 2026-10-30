# utils/bot/wake_timer.py
#
# הערת המחשב למשימה המתוזמנת הבאה (19.10.2026, כבוי כברירת מחדל): כשיש משימה פעילה ב-utils/bot/scheduler_store,
# נרשמת משימה אחת ב-Task Scheduler של Windows - "ClipForge\WakeForNextTask" - עם WakeToRun, דקה-שתיים לפני המועד.
# היא רק מעירה את המחשב (פעולה ריקה): האפליקציה כבר רצה, ממשיכה מהשינה, ולולאת המתזמן מריצה את המשימה כרגיל.
# מתעדכנת כשהלוח משתנה (וכשמשימה רצה), ונמחקת כשמכבים או כשאין משימה. schtasks נקרא רק כשהמועד באמת משתנה.
#
# כדי שזה יעבוד צריך שבתוכנית החשמל של Windows "Allow wake timers" יהיה Enable (powercfg; מוצג באבחון). ב-BIOS לא צריך
# "RTC/Resume by Alarm" בשביל טיימרים של Task Scheduler. בטסטים run הוא תמיד פונקציה מזויפת - אף פעם לא schtasks אמיתי.
import datetime
import json
import os
import re
import subprocess
import tempfile
from typing import Any, Callable, Dict, Iterable, Optional

from utils.shared.atomic_write import atomic_write_json
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared import data_paths

TASK_NAME = "ClipForge\\WakeForNextTask"
LEAD = datetime.timedelta(minutes=2)          # מעירים קצת לפני - Windows צריך כמה שניות לחזור, ולולאת המתזמן בודקת כל 30 שנ'
MIN_AHEAD = datetime.timedelta(minutes=1)     # מועד שכמעט הגיע - המחשב ער ממילא, לא רושמים
STATE_PATH = data_paths.path(data_paths.WAKE_TIMER)
WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

Runner = Callable[..., Any]
# tests/conftest.py מגדיר אותו לכל ריצת pytest (גם לתתי-תהליכים): schtasks אמיתי לא נקרא אף פעם מטסט
NO_SCHTASKS_ENV = "CLIPFORGE_NO_SCHTASKS"


def _time_of(task) -> datetime.time:
    try:
        hour, minute = (int(p) for p in str(task.get("time", "03:00")).split(":"))
        return datetime.time(hour, minute)
    except ValueError:
        return datetime.time(3, 0)


def next_run_after(task: Dict[str, Any], now: datetime.datetime) -> Optional[datetime.datetime]:
    """המועד הבא (אחרי now) של משימה פעילה, או None. משימה שכבר "הגיע זמנה" רצה עכשיו - הלולאה תחשב שוב אחריה."""
    if not task.get("enabled", True):
        return None
    schedule_type = task.get("schedule_type")
    if schedule_type == "interval_hours":
        try:
            last = datetime.datetime.fromisoformat(task.get("last_run_at") or "")
            hours = float(task.get("interval_hours", 24))
        except (TypeError, ValueError):
            return None
        candidate = last + datetime.timedelta(hours=hours)
        return candidate if candidate > now else None
    if schedule_type in ("daily", "weekly"):
        at = datetime.datetime.combine(now.date(), _time_of(task))
        if schedule_type == "weekly":
            at += datetime.timedelta(days=(WEEKDAY_INDEX.get(task.get("weekday", "sun"), 6) - now.weekday()) % 7)
            return at if at > now else at + datetime.timedelta(days=7)
        return at if at > now else at + datetime.timedelta(days=1)
    return None


def next_wake(tasks: Iterable[Dict[str, Any]], now: datetime.datetime) -> Optional[datetime.datetime]:
    """מתי להעיר: LEAD לפני המשימה הקרובה, או None (אין משימה, או שהמועד קרוב מדי)."""
    runs = []
    for task in tasks:
        try:
            run_at = next_run_after(task, now)
        except Exception:   # משימה פגומה בקובץ - מדלגים רק עליה, כמו scheduler.check_and_run_due_tasks
            run_at = None
        if run_at:
            runs.append(run_at)
    if not runs:
        return None
    wake = min(runs) - LEAD
    return wake if wake > now + MIN_AHEAD else None


def load_state(path: str = "") -> Dict[str, Any]:
    try:
        with open(path or STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {"enabled": bool(data.get("enabled")), "wake_at": data.get("wake_at"), "error": data.get("error") or ""}
    except (OSError, ValueError):
        pass
    return {"enabled": False, "wake_at": None, "error": ""}


def _save_state(state: Dict[str, Any], path: str = "") -> None:
    path = path or STATE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, state, ensure_ascii=False, indent=2)


def task_xml(wake_at: datetime.datetime) -> str:
    """הגדרת המשימה: טריגר חד-פעמי בשעה המקומית, WakeToRun, משתמש מחובר בלי הרשאות מנהל, ופעולה ריקה."""
    start = wake_at.replace(microsecond=0).isoformat()
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>ClipForge: wakes the PC shortly before its next scheduled task (the running app does the work). Managed by ClipForge - turn it off in the scheduler screen.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <WakeToRun>true</WakeToRun>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>%SystemRoot%\\System32\\cmd.exe</Command>
      <Arguments>/c exit 0</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(run: Optional[Runner], *args: str):
    if run is None:
        if os.environ.get(NO_SCHTASKS_ENV):
            raise OSError(f"schtasks חסום בריצת טסטים ({NO_SCHTASKS_ENV})")
        run = subprocess.run
    return run(["schtasks", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
               timeout=20, creationflags=NO_WINDOW_FLAGS)


def _register(wake_at: datetime.datetime, run: Optional[Runner]) -> str:
    """רושם (או מחליף) את המשימה. מחזיר הודעת שגיאה או ''."""
    fd, xml_path = tempfile.mkstemp(prefix="clipforge_wake_", suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-16") as f:
            f.write(task_xml(wake_at))
        result = _schtasks(run, "/Create", "/TN", TASK_NAME, "/XML", xml_path, "/F")
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    finally:
        try:
            os.remove(xml_path)  # safe: our own temp XML from mkstemp above
        except OSError:
            pass
    return "" if result.returncode == 0 else (result.stderr or result.stdout or f"schtasks exit {result.returncode}").strip()


def _unregister(run: Optional[Runner]) -> str:
    try:
        result = _schtasks(run, "/Delete", "/TN", TASK_NAME, "/F")
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    return "" if result.returncode == 0 else (result.stderr or result.stdout or "").strip()


def sync(tasks: Iterable[Dict[str, Any]], now: Optional[datetime.datetime] = None, run: Optional[Runner] = None,
         path: str = "") -> Dict[str, Any]:
    """מיישר את משימת ההערה ללוח הנוכחי. נקרא מלולאת המתזמן (כל 30 שנ') - schtasks רק כשהמועד משתנה."""
    now = now or datetime.datetime.now()
    state = load_state(path)
    wake = next_wake(tasks, now) if state["enabled"] else None
    wanted = wake.replace(microsecond=0).isoformat() if wake else None
    if wanted == state["wake_at"]:
        return state
    if wake:
        error = _register(wake, run)
    else:
        error = _unregister(run) if state["wake_at"] else ""
    state = {"enabled": state["enabled"], "wake_at": wanted if (wake and not error) else None, "error": error}
    _save_state(state, path)
    return state


def set_enabled(enabled: bool, tasks: Iterable[Dict[str, Any]], run: Optional[Runner] = None, path: str = "") -> Dict[str, Any]:
    state = load_state(path)
    _save_state({**state, "enabled": bool(enabled)}, path)
    return sync(tasks, run=run, path=path)


def windows_allows_wake_timers(run: Optional[Runner] = None) -> Optional[bool]:
    """'Allow wake timers' בתוכנית החשמל הנוכחית (במתח רשת): True/False, או None כשאי אפשר לדעת. קריאה בלבד."""
    run = run or subprocess.run
    try:
        result = run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE"], capture_output=True, text=True,
                     encoding="utf-8", errors="replace", timeout=10, creationflags=NO_WINDOW_FLAGS)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"AC Power Setting Index:\s*0x([0-9a-fA-F]+)", result.stdout or "")
    return None if not match else int(match.group(1), 16) != 0   # 0 = Disable, 1 = Enable, 2 = Important only


def current_wake_timers(run: Optional[Runner] = None) -> str:
    """powercfg /waketimers - מה Windows מתכנן להעיר כרגע (קריאה בלבד)."""
    run = run or subprocess.run
    try:
        result = run(["powercfg", "/waketimers"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                     timeout=10, creationflags=NO_WINDOW_FLAGS)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    return (result.stdout or result.stderr or "").strip()
