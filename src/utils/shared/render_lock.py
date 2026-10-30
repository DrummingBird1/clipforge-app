# utils/shared/render_lock.py
#
# מנעול קובץ חוצה-תהליכים (cross-process) שמונע משני רינדורים כבדי-GPU
# (ffmpeg עם NVENC) לרוץ בו-זמנית בטעות. utils/shared/worker.py כבר מבטיח את זה
# בתוך ה-GUI לבדו (heavy_queue עם thread צרכן יחיד) - אבל הבוט (main.py) רץ
# בתהליך נפרד לגמרי ומריץ תת-תהליכים ישירות משלו (cogs/scheduler_cog.py,
# cogs/remote_execution.py), בלי שום קשר לתור של ה-GUI. שני התהליכים האלה
# יכלו עד כה להריץ רינדור כבד בו-זמנית ולהתחרות על אותו GPU בלי לדעת אחד על
# השני. מנעול קובץ (לא in-memory lock) הוא הדרך היחידה לתאם בין שני תהליכי
# פייתון נפרדים לגמרי.

import contextlib
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterator, Optional

try:
    import psutil
except ImportError:
    psutil = None

from utils.shared import data_paths

LOCK_PATH = data_paths.path(data_paths.RENDER_LOCK)
WAITERS_PATH = data_paths.path(data_paths.RENDER_WAITERS)

# מרווח בטחון גדול בהרבה מכל המתנת רינדור סבירה - רשומת ממתין שעברה את הגיל הזה
# מדולגת (בנוסף לבדיקת PID-חי) גם אם psutil לא מותקן (_is_pid_alive מחזיר False
# תמיד בלעדיו - בלי הגנת הגיל הזו, רשימת הממתינים הייתה מתרוקנת תמיד בטעות).
_WAITER_STALE_SECONDS = 6 * 3600

# מוגדר ב-env של תת-התהליך ע"י קורא שכבר תפס את render_lock בעצמו לפני
# שהפעיל אותו (utils/shared/worker.py, cogs/remote_execution.py) - ראו
# render_lock_if_needed() למטה. בלי זה, סקריפט כבד (video_editor.py וכו')
# שמנסה לתפוס את אותו מנעול בעצמו היה נועל את עצמו: ההורה כבר מחזיק בו
# וממתין לתת-התהליך שיסתיים, ותת-התהליך מחכה למנעול שההורה מחזיק - deadlock
# אמיתי, לא רק המתנה ארוכה.
CALLER_HOLDS_LOCK_ENV_VAR = "RENDER_LOCK_HELD_BY_CALLER"

# רינדור אמיתי (אפילו כבד) כמעט אף פעם לא לוקח יותר מזה - מנעול ישן יותר נחשב
# תקוע (תהליך שהחזיק אותו נתקע/דלף בלי לקרוס - ה-PID עדיין "חי" טכנית, אז
# בדיקת _is_pid_alive לבדה לא הייתה תופסת את זה) ומשוחרר אוטומטית בניסיון
# התפיסה הבא. נמצא בפועל בסשן הזה - Web App ישן שנשכח פתוח החזיק את המנעול
# שעות, וחסם כל רינדור אחר במערכת בלי שום סימן למה.
MAX_LOCK_AGE_SECONDS = 4 * 3600


def _read_lock_data(lock_path: str) -> Dict[str, Any]:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _is_pid_alive(pid: Optional[int]) -> bool:
    if psutil is None or pid is None:
        return False
    try:
        return bool(psutil.pid_exists(pid))
    except Exception:
        return False


def _is_stale(lock_path: str) -> bool:
    data = _read_lock_data(lock_path)
    acquired_at = data.get("acquired_at")
    if acquired_at is not None and (time.time() - acquired_at) > MAX_LOCK_AGE_SECONDS:
        return True
    return not _is_pid_alive(data.get("pid"))


def _try_acquire(lock_path: str) -> bool:
    """מנסה ליצור את קובץ המנעול אטומית (O_EXCL - כישלון אם כבר קיים). מטפל
    ב-stale lock (PID שכתב את הקובץ כבר לא רץ, או שהמנעול פשוט ישן מדי -
    ראו MAX_LOCK_AGE_SECONDS) על ידי מחיקת הקובץ הישן וחזרה (הניסיון הבא
    בלולאת acquire() יצליח)."""
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "acquired_at": time.time()}, f)
        return True
    except FileExistsError:
        if _is_stale(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass
        return False
    except PermissionError:
        # ב-Windows יצירה של קובץ שעוד באמצע מחיקה (release() מחק אותו, ותהליך אחר - למשל סורק - עוד מחזיק אותו פתוח)
        # נכשלת ב-ACCESS_DENIED ולא ב-FileExistsError. כמו מנעול תפוס: הסבב הבא של acquire() מנסה שוב, עם אותו timeout.
        # נצפה בריצה המלאה ב-23.10.2026 - ה-thread הממתין נפל, ורינדור אמיתי היה נכשל במקום לחכות.
        return False


def _read_waiters(waiters_path: str, exempt_pid: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """קורא את קובץ רשימת הממתינים ומנקה תוך כדי קריאה רשומות מתות (PID שכבר
    לא רץ, או רשומה ישנה מדי - ראו _WAITER_STALE_SECONDS) - כך שהרשימה לעולם
    לא צוברת "רפאים" מתהליכים שקרסו בלי לבטל את הרשמתם.

    exempt_pid: תמיד עובר את בדיקת ה"חי" בלי קשר לתוצאת _is_pid_alive - נועד
    ל-acquire() לספק את ה-PID של עצמו: תהליך תמיד "חי" מנקודת המבט של עצמו
    (הוא זה שמריץ את הקוד הזה כרגע), כך שההרשמה העצמית שלו לעולם לא תיפול
    קורבן לבדיקת-חיות שגויה (למשל psutil שמתנהג בצורה לא צפויה, או במוקים
    בטסטים) ותגרום לו לחכות לנצח בלי שאף אחד אחר ישחרר את המנעול."""
    try:
        with open(waiters_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    now = time.time()
    alive = {}
    for waiter_key, info in data.items():
        if not isinstance(info, dict):
            continue
        pid = info.get("pid")
        if pid != exempt_pid and psutil is not None and not _is_pid_alive(pid):
            continue
        if (now - info.get("registered_at", 0)) > _WAITER_STALE_SECONDS:
            continue
        alive[waiter_key] = info
    if alive != data:
        _write_waiters(waiters_path, alive)
    return alive


def _write_waiters(waiters_path: str, waiters: Dict[str, Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(waiters_path), exist_ok=True)
    try:
        with open(waiters_path, "w", encoding="utf-8") as f:
            json.dump(waiters, f)
    except OSError:
        pass


def _register_waiter(pid: int, priority: int, label: Optional[str], waiters_path: str, waiter_key: str,
                     registered_at: Optional[float] = None) -> float:
    waiters = _read_waiters(waiters_path)
    registered_at = time.time() if registered_at is None else registered_at
    waiters[waiter_key] = {"pid": pid, "registered_at": registered_at, "priority": priority, "label": label}
    _write_waiters(waiters_path, waiters)
    return registered_at


def _unregister_waiter(waiter_key: str, waiters_path: str) -> None:
    waiters = _read_waiters(waiters_path)
    waiters.pop(waiter_key, None)
    _write_waiters(waiters_path, waiters)


def _next_in_line_key(waiters: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """מפתח-הממתין (לא רק PID - ראו waiter_key ב-acquire) שאמור לנסות לתפוס
    את המנעול הבא - עדיפות גבוהה יותר קודם, בין שתי רשומות עם אותה עדיפות
    הוותיקה יותר (registered_at קטן יותר) קודמת. זו תזמון "רך" בלבד (best-
    effort, לא אטומי) - כל ממתין בודק את זה בעצמו לפני שהוא בכלל מנסה את
    מרוץ ה-O_EXCL, כך שממתינים עם עדיפות נמוכה יותר נמנעים באופן יזום
    מלהתחרות על מנעול שהתפנה לפני שהראשון בתור הספיק לתפוס."""
    if not waiters:
        return None
    return min(waiters.items(), key=lambda kv: (-kv[1].get("priority", 0), kv[1].get("registered_at", 0)))[0]


def get_waiters(waiters_path: str = WAITERS_PATH) -> list:
    """רשימת הממתינים כרגע (ממוינת לפי סדר התור), לשימוש ב-UI (web_app.py,
    dashboard.py, cogs/status_cog.py) כדי להראות "עוד 2 ממתינים בתור" במקום
    רק "יש מישהו אחר רץ" בינארי."""
    waiters = _read_waiters(waiters_path)
    ordered = sorted(waiters.items(), key=lambda kv: (-kv[1].get("priority", 0), kv[1].get("registered_at", 0)))
    return [info for _waiter_key, info in ordered]  # "pid" כבר בתוך info (ראו _register_waiter)


def get_status(lock_path: str = LOCK_PATH, waiters_path: str = WAITERS_PATH) -> Optional[Dict[str, Any]]:
    """מחזיר None אם המנעול פנוי, אחרת dict עם pid/acquired_at/age_seconds/
    is_stale/queue_length - כדי שמנעול תפוס (ובמיוחד תקוע) יהיה נראה וניתן
    לאבחון (cogs/status_cog.py, web_app.py) במקום פשוט "נתקע בשקט" בלי שום
    רמז למה, וכדי שאפשר יהיה לראות כמה עוד רינדורים מחכים בתור."""
    if not os.path.exists(lock_path):
        return None
    data = _read_lock_data(lock_path)
    acquired_at = data.get("acquired_at")
    age_seconds = (time.time() - acquired_at) if acquired_at is not None else None
    return {
        "pid": data.get("pid"), "acquired_at": acquired_at, "age_seconds": age_seconds,
        "is_stale": _is_stale(lock_path), "queue_length": len(_read_waiters(waiters_path)),
    }


def acquire(
    poll_interval: float = 2.0,
    timeout: Optional[float] = None,
    on_wait: Optional[Callable[[float], Any]] = None,
    lock_path: str = LOCK_PATH,
    priority: int = 0,
    label: Optional[str] = None,
    waiters_path: str = WAITERS_PATH,
) -> None:
    """חוסם (poll_interval שניות בין ניסיונות) עד שהמנעול נתפס. timeout=None
    (ברירת מחדל) ממתין ללא הגבלה - רינדור אחר יכול לקחת שעה; timeout מספרי
    זורק TimeoutError אם חורג. on_wait(seconds_waited) נקרא פעם אחת (רק
    בהמתנה הראשונה) אם המנעול לא היה פנוי מיד - לשימוש בהודעת לוג.

    priority: מספר גבוה יותר = תור קודם (ברירת מחדל 0 לכולם - זהה להתנהגות
    הישנה, פשוט FIFO דטרמיניסטי במקום מרוץ). label: תיאור חופשי (למשל שם
    הסקריפט) לתצוגה ב-get_waiters(). נרשמים לתור *לפני* הניסיון הראשון,
    ומבטלים את ההרשמה תמיד (גם על חריגה/timeout) כדי לא להשאיר רשומת-רפאים.

    waiter_key כולל גם threading.get_ident() (לא רק PID) - item: בדיקת באגים
    מקיפה: שני callers מה-thread-ים שונים באותו תהליך בדיוק (למשל
    cogs/remote_execution.py + cogs/scheduler_cog.py, שניהם דרך run_in_executor
    על אותו תהליך בוט) היו חולקים בעבר את אותה רשומת-ממתין יחידה (מפתח=str(pid)
    בלבד) - מי מהם שהצליח לתפוס את המנעול ומבטל את הרשמתו היה מוחק בטעות גם
    את ההרשמה של השני, שנשאר ממתין לנצח בלי אף אחד שישחרר אותו (הוא לא נרשם
    מחדש בלולאה, רק פעם אחת לפני ה-while)."""
    start = time.time()
    logged_wait = False
    pid = os.getpid()
    waiter_key = f"{pid}:{threading.get_ident()}"
    registered_at = _register_waiter(pid, priority, label, waiters_path, waiter_key)
    try:
        while True:
            waiters = _read_waiters(waiters_path, exempt_pid=pid)
            # קובץ הממתינים נכתב בקריאה-שינוי-כתיבה בלי נעילה: ממתין אחר שקרא קובץ חצי-כתוב (ריק) וכתב אותו בחזרה
            # מוחק את ההרשמה שלנו, ובלעדיה אנחנו אף פעם לא "הבאים בתור" - ממתינים עד ה-timeout גם כשהמנעול פנוי
            # (test_two_same_process_threads, timelapse_maker תחת עומס). נרשמים מחדש עם אותו registered_at - אותו מקום בתור.
            # הקריאה יכולה גם להיכשל רגעית (קובץ באמצע כתיבה = {}), ואז ההרשמה מחדש רק מחזירה את מה שכבר שם.
            if waiter_key not in waiters:
                _register_waiter(pid, priority, label, waiters_path, waiter_key, registered_at)
                waiters[waiter_key] = {"pid": pid, "registered_at": registered_at, "priority": priority, "label": label}
            am_i_next = _next_in_line_key(waiters) == waiter_key
            if am_i_next and _try_acquire(lock_path):
                return
            waited = time.time() - start
            if timeout is not None and waited >= timeout:
                raise TimeoutError(f"לא הצלחתי לתפוס את מנעול הרינדור אחרי {timeout:.0f} שניות - תהליך רינדור אחר עדיין רץ.")
            if on_wait and not logged_wait:
                on_wait(waited)
                logged_wait = True
            time.sleep(poll_interval)
    finally:
        _unregister_waiter(waiter_key, waiters_path)


def touch(lock_path: str = LOCK_PATH) -> None:
    """מרעיש את acquired_at ל"עכשיו" (בלי לשנות את ה-pid) - נועד לתהליך
    שמחזיק את המנעול ומריץ ריצה שהושהתה (Pause, ראו utils/shared/worker.py) ממושכת:
    בלי זה, MAX_LOCK_AGE_SECONDS היה גורם ל-_is_stale() להחשיב את המנעול
    "תקוע" ולתת לתהליך אחר לתפוס אותו בטעות בזמן שהריצה המקורית רק קפואה,
    לא מתה. לא עושה כלום אם המנעול לא קיים, או שייך לתהליך אחר (אין מה
    לגעת במנעול של מישהו אחר)."""
    data = _read_lock_data(lock_path)
    if not data or data.get("pid") != os.getpid():
        return
    try:
        with open(lock_path, "w", encoding="utf-8") as f:
            json.dump({"pid": data["pid"], "acquired_at": time.time()}, f)
    except OSError:
        pass


def release(lock_path: str = LOCK_PATH) -> None:
    # ב-Windows os.remove נכשל (PermissionError) כל עוד מישהו אחר מחזיק את הקובץ פתוח - וממתין קורא אותו
    # (_is_stale) בכל סבב. קודם השגיאה נבלעה והמנעול נשאר תפוס בשקט עד שהמחזיק מת או עד MAX_LOCK_AGE_SECONDS;
    # הקריאה אורכת מיקרו-שניות, אז מנסים שוב עד שהיא נגמרת (עד שנייה בערך).
    for _attempt in range(50):
        try:
            os.remove(lock_path)
            return
        except PermissionError:
            time.sleep(0.02)
        except OSError:
            return


@contextlib.contextmanager
def render_lock(
    poll_interval: float = 2.0,
    timeout: Optional[float] = None,
    on_wait: Optional[Callable[[float], Any]] = None,
    lock_path: str = LOCK_PATH,
    priority: int = 0,
    label: Optional[str] = None,
    waiters_path: str = WAITERS_PATH,
) -> Iterator[None]:
    """Context manager נוח לקוד סינכרוני (worker.py, scheduler_cog.py) - תופס
    ב-acquire() ומשחרר תמיד ב-release(), גם על חריגה. קוד אסינכרוני
    (remote_execution.py) לא יכול להשתמש בזה ישירות כי acquire() חוסם עם
    time.sleep - שם קוראים ל-acquire()/release() בנפרד דרך run_in_executor."""
    acquire(poll_interval=poll_interval, timeout=timeout, on_wait=on_wait, lock_path=lock_path, priority=priority, label=label, waiters_path=waiters_path)
    try:
        yield
    finally:
        release(lock_path=lock_path)


@contextlib.contextmanager
def render_lock_if_needed(
    poll_interval: float = 2.0,
    timeout: Optional[float] = None,
    on_wait: Optional[Callable[[float], Any]] = None,
    lock_path: str = LOCK_PATH,
    priority: int = 0,
    label: Optional[str] = None,
    waiters_path: str = WAITERS_PATH,
) -> Iterator[None]:
    """כמו render_lock(), אבל מדלגת על התפיסה בכלל אם CALLER_HOLDS_LOCK_ENV_VAR
    מוגדר בסביבה - כלומר caller חיצוני כבר תפס את אותו מנעול בעצמו לפני
    שהפעיל את תת-התהליך הזה (ראו ההערה למעלה). מיועדת לשימוש *בתוך* סקריפט
    כבד עצמו (video_editor.py/rocket_shorts_publisher.py/timelapse_maker.py),
    כדי שהוא יגן על עצמו גם כשהוא מופעל ישירות (טרמינל, בלי דרך ה-GUI/הבוט
    שכבר נועלים בעצמם)."""
    if os.environ.get(CALLER_HOLDS_LOCK_ENV_VAR):
        yield
        return
    with render_lock(poll_interval=poll_interval, timeout=timeout, on_wait=on_wait, lock_path=lock_path, priority=priority, label=label, waiters_path=waiters_path):
        yield
