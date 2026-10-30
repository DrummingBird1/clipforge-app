# utils/media/ffmpeg_progress.py
#
# run_ffmpeg_with_progress הופיע כמעט זהה מילה-במילה בשלושה סקריפטים נפרדים
# (rocket_shorts_publisher.py, timelapse_maker.py, video_editor.py) - כל אחד
# בעצם עותק-הדבק של הקודם. אוחד לכאן אחרי שהופיע בפעם השלישית.

import random
import re
import subprocess
import sys
import threading
import time
from collections import deque
from typing import Callable, List, Optional, Tuple

from tqdm import tqdm

from utils.shared.retry import compute_backoff_delay
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

_FRAME_PATTERN = re.compile(r"frame=\s*(\d+)")

# מספר שורות stderr אחרונות שנשמרות בזיכרון (item: המתנה/ניסיון-חוזר כש-NVENC
# session-limited) - digit-ish ring buffer, לא כל ה-stderr (יכול להגיע לאלפי
# שורות frame= בריצה ארוכה) - כשל אמיתי של NVENC (סשן לא נפתח) תמיד מופיע
# ממש בהתחלה, הרבה לפני שיש בכלל frame= ראשון להדפיס.
_STDERR_TAIL_LINES = 200

# תת-מחרוזות (lowercase) שמעידות על כשל NVENC ספציפית ממגבלת-session (לא כל
# כשל NVENC אחר - פרמטרים לא-נתמכים/GPU לא קיים בכלל צריכים להיכשל מיד, לא
# להסתתר מאחורי ניסיונות-חוזרים מיותרים שרק מאריכים כשל בלתי-נמנע). נצפה
# בפועל בפרודקשן (--parallel 6, קודק av1) - מגבלת-הסשנים שזוהתה ב-probe
# (nvenc_probe.py, קידודים זעירים 64x64) לא בהכרח שורדת קידוד 4K מלא בפועל,
# אז ניסיונות-חוזרים על מגבלת-session הזו הם תרחיש אמיתי, לא רק תיאורטי.
_NVENC_SESSION_LIMIT_MARKERS = (
    "openencodesessionex failed",
    "out of memory (10)",
    "encoder busy",
    "no capacity for new encoding session",
)


class FfmpegCancelled(Exception):
    """הקידוד בוטל מבחוץ (גל 8, item 95: ביטול קובץ בודד תוך ריצה)."""


# control: פונקציה שמחזירה "run"/"pause"/"cancel" (ראו utils/video/run_control.py) -
# נבדקת כל חצי-שנייה ב-thread צדדי: pause משעה את תהליך ה-ffmpeg עצמו (psutil
# suspend - בלי לאבד את מה שכבר קודד), cancel מסיים אותו וזורק FfmpegCancelled.
ControlFn = Callable[[], str]


# סבב ייצוב: השהיה, חזרה וביטול לכל עץ התהליכים, לא רק לתהליך שהפעלנו. משגר (python של venv ב-Windows, shim של
# scoop/chocolatey ל-ffmpeg) מריץ את העבודה בתהליך-בן - השהיה של המשגר בלבד השאירה את הקידוד רץ.
def _descendants(handle) -> list:
    try:
        return handle.children(recursive=True)
    except Exception:
        return []


def _suspend_tree(handle) -> None:
    # קודם ההורה (שלא יוליד ילד חדש באמצע), ואז העץ עד שאין חדשים - כמו Worker._suspend_tree
    handle.suspend()
    done: set = set()
    for _ in range(5):
        fresh = [child for child in _descendants(handle) if child.pid not in done]
        if not fresh:
            return
        for child in fresh:
            done.add(child.pid)
            try:
                child.suspend()
            except Exception:
                pass


def _resume_tree(handle) -> None:
    for proc in [handle] + _descendants(handle):
        try:
            proc.resume()
        except Exception:
            pass


def _terminate_tree(process: "subprocess.Popen[str]", handle) -> None:
    # גם הצאצאים: בלי job object (shim) התהליך האמיתי היה ממשיך לרוץ ומחזיק את ה-stderr פתוח
    descendants = _descendants(handle) if handle is not None else []
    process.terminate()
    for child in descendants:
        try:
            child.terminate()
        except Exception:
            pass


def _watch_control(process: "subprocess.Popen[str]", control: ControlFn, description: str, stop: threading.Event, state: dict) -> None:
    try:
        import psutil
        handle = psutil.Process(process.pid)
    except Exception:
        handle = None
    suspended = False
    while not stop.wait(0.5):
        try:
            action = control()
        except Exception:
            continue
        if action == "cancel":
            state["cancelled"] = True
            try:
                if suspended and handle is not None:
                    _resume_tree(handle)
                _terminate_tree(process, handle)
            except Exception:
                pass
            return
        if action == "pause" and not suspended and handle is not None:
            try:
                _suspend_tree(handle)
                suspended = True
                print(f"[PAUSED] {description}")
                sys.stdout.flush()
            except Exception:
                pass
        elif action != "pause" and suspended and handle is not None:
            try:
                _resume_tree(handle)
                suspended = False
                print(f"[RESUMED] {description}")
                sys.stdout.flush()
            except Exception:
                pass
    if suspended and handle is not None:
        _resume_tree(handle)


def _run_ffmpeg_capturing(
    cmd: List[str], total_frames: int, description: str, position: int = 0, control: Optional[ControlFn] = None,
) -> Tuple[bool, str]:
    """הליבה המשותפת: כמו run_ffmpeg_with_progress, אבל גם מחזירה את שורות
    ה-stderr האחרונות (ראו _STDERR_TAIL_LINES) - כדי ש-run_ffmpeg_with_progress_and_nvenc_retry
    יוכל לבדוק אם כשל תואם לתבנית מגבלת-session בלי לשמור stderr שלם בזיכרון."""
    tail: deque = deque(maxlen=_STDERR_TAIL_LINES)
    control_state = {"cancelled": False}
    stop_watch = threading.Event()
    with tqdm(total=total_frames, desc=description, unit="frames", dynamic_ncols=True, file=sys.stdout, position=position, leave=True) as pbar:
        process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW_FLAGS,
        )
        if control is not None:
            threading.Thread(target=_watch_control, args=(process, control, description, stop_watch, control_state), daemon=True).start()
        try:
            if process.stderr:
                for line in process.stderr:
                    tail.append(line)
                    match = _FRAME_PATTERN.search(line)
                    if match:
                        pbar.n = min(int(match.group(1)), total_frames)
                        pbar.refresh()
            process.communicate()
        finally:
            stop_watch.set()
        if control_state["cancelled"]:
            raise FfmpegCancelled(description)
        pbar.n = total_frames
        pbar.refresh()
    return process.returncode == 0, "".join(tail)


def run_ffmpeg_with_progress(cmd: List[str], total_frames: int, description: str, position: int = 0, control: Optional[ControlFn] = None) -> bool:
    """מריץ פקודת ffmpeg עם מעקב התקדמות חי (tqdm) דרך פרסור frame=NNN מ-stderr.
    tqdm על stdout מזוהה אוטומטית ב-GUI (utils/shared/worker.py) בלי צורך ב-"PROGRESS:"
    ידני. position מאפשר כמה פסי התקדמות בו-זמנית (רינדור מקבילי, כמו ב-
    rocket_shorts_publisher.py) - ברירת המחדל 0 מתאימה לריצה טורית רגילה."""
    ok, _stderr_tail = _run_ffmpeg_capturing(cmd, total_frames, description, position=position, control=control)
    return ok


def run_ffmpeg_with_progress_and_nvenc_retry(
    cmd: List[str], total_frames: int, description: str, position: int = 0,
    is_nvenc: bool = False, max_retries: int = 6, retry_delay_seconds: float = 15.0,
    backoff_factor: float = 1.8, max_retry_delay_seconds: float = 90.0, control: Optional[ControlFn] = None,
    on_stderr: Optional[Callable[[str], None]] = None,
) -> bool:
    """כמו run_ffmpeg_with_progress, עם ניסיון חוזר אוטומטי (item: תור/המתנה
    כש-NVENC session-limited, במקום להיכשל) - רק כש-is_nvenc=True *וגם*
    ה-stderr מכיל אחד מהסימנים המוכרים למגבלת-session שהושגה
    (_NVENC_SESSION_LIMIT_MARKERS) - לא לכל כשל NVENC, כדי לא להסתיר כשלים
    אמיתיים (פרמטרים שגויים, אין GPU בכלל) מאחורי ניסיונות-חוזרים מיותרים
    שרק מאריכים כשל בלתי-נמנע.

    ההמתנה בין ניסיונות (item: תוקן אחרי כשל אמיתי בפרודקשן) גדלה מעריכית
    (compute_backoff_delay - אותה לוגיקה כמו utils/shared/retry.py) עד
    max_retry_delay_seconds, עם jitter אקראי (±15%) - לא המתנה קבועה של כמה
    שניות כמו קודם. הסיבה: הסשן ה"תפוס" שמונע קידוד חדש הוא בד"כ קידוד 4K
    מלא של קובץ מקבילי אחר שיכול לקחת דקות שלמות עד שמשתחרר, לא רגע חולף -
    ותוקן ב-max_retries גבוה יותר בהתאם, כדי שסה"כ זמן ההמתנה יגיע לכמה
    דקות ולא רק לעשרות שניות. ה-jitter מונע ש-worker-ים מקבילים שנתקעו
    בדיוק על אותה מגבלה ינסו שוב כולם באותה השנייה ויתנגשו שוב יחד."""
    attempt = 0
    while True:
        attempt += 1
        ok, stderr_tail = _run_ffmpeg_capturing(cmd, total_frames, description, position=position, control=control)
        if ok and on_stderr is not None:
            on_stderr(stderr_tail)   # 24.10.2026: למשל הסיכום של loudnorm בסוף הקידוד (video_editor.py, LUFS על הפלט)
        if ok or not is_nvenc or attempt > max_retries:
            return ok
        if not any(marker in stderr_tail.lower() for marker in _NVENC_SESSION_LIMIT_MARKERS):
            return False
        delay = compute_backoff_delay(attempt - 1, retry_delay_seconds, backoff_factor, max_retry_delay_seconds)
        delay *= random.uniform(0.85, 1.15)
        print(f"[INFO] {description}: כשל NVENC שנראה כמו מגבלת-session שהושגה (ניסיון {attempt}/{max_retries + 1}) - ממתין כ-{delay:.0f}s ומנסה שוב.")
        sys.stdout.flush()
        time.sleep(delay)
