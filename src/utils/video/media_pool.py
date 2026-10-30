# utils/video/media_pool.py
#
# גל 24: מאגר עבודה מוגבל לקריאות ffmpeg/ffprobe שהשרת מריץ בעצמו (לא הרינדור - הוא
# תהליך נפרד עם מנעול משלו). עד עכשיו כל route הריץ subprocess.run ישירות: תיקייה של
# מאות קבצים שולחת עשרות בקשות תמונה ממוזערת/probe בבת אחת, וכל אחת תופסת thread
# מה-pool של השרת ומריצה ffmpeg משלה - באמצע רינדור זה חונק את המחשב, ובקשות אחרות
# (תצוגה מקדימה, API רגיל) מחכות בתור מאחוריהן.
#
# שלושה "נתיבים" עם תקרה נפרדת, כדי שהצפה של תמונות ממוזערות לא תעכב תצוגה מקדימה:
#   thumbs      - תמונות ממוזערות ו-probe (קצר, הרבה)
#   interactive - תצוגה מקדימה, פריים מקור, ציר-זמן, בדיקת הגדרות (המשתמש מחכה לזה)
#   analysis    - proxy לנגן, זיהוי סצנות, גרף עוצמה (ארוך, ברקע)
#
# single_flight(key): שתי בקשות לאותו פלט (אותה תמונה ממוזערת מהבית וממסך העבודות)
# מריצות ffmpeg פעם אחת - השנייה מחכה ורואה את הקובץ המוכן, במקום לקרוא קובץ חצי-כתוב.

import contextlib
import os
import subprocess
import threading
from typing import Dict, Iterator, List

_CPUS = os.cpu_count() or 4
LANE_LIMITS: Dict[str, int] = {
    "thumbs": max(2, min(4, _CPUS // 4)),
    "interactive": 2,
    "analysis": 2,
}

_semaphores = {lane: threading.BoundedSemaphore(limit) for lane, limit in LANE_LIMITS.items()}
_stats_lock = threading.Lock()
_stats = {lane: {"running": 0, "waiting": 0, "done": 0, "peak": 0} for lane in LANE_LIMITS}


@contextlib.contextmanager
def slot(lane: str = "thumbs") -> Iterator[None]:
    """מקום אחד בנתיב - חוסם עד שמתפנה. לקוד שמריץ ffmpeg דרך פונקציה אחרת (למשל
    utils/media/thumbnail_generator.py) ולא דרך run() כאן."""
    semaphore = _semaphores[lane]
    stats = _stats[lane]
    with _stats_lock:
        stats["waiting"] += 1
    semaphore.acquire()
    with _stats_lock:
        stats["waiting"] -= 1
        stats["running"] += 1
        stats["peak"] = max(stats["peak"], stats["running"])
    try:
        yield
    finally:
        with _stats_lock:
            stats["running"] -= 1
            stats["done"] += 1
        semaphore.release()


def run(cmd: List[str], lane: str = "thumbs", **kwargs) -> "subprocess.CompletedProcess":
    """subprocess.run בתוך מקום בנתיב. אותה חתימה ואותן חריגות כמו subprocess.run."""
    with slot(lane):
        return subprocess.run(cmd, **kwargs)


_flights_lock = threading.Lock()
_flights: Dict[str, list] = {}


@contextlib.contextmanager
def single_flight(key: str) -> Iterator[None]:
    """רק thread אחד בכל רגע בתוך הבלוק לכל key; אחרים מחכים לו (ואז בודקים שוב אם
    הפלט כבר קיים). הרשומה נמחקת כשאף אחד לא מחכה - אין דליפת זיכרון לאורך זמן."""
    with _flights_lock:
        entry = _flights.setdefault(key, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _flights_lock:
            entry[1] -= 1
            if entry[1] == 0:
                _flights.pop(key, None)


def stats() -> Dict[str, Dict[str, int]]:
    with _stats_lock:
        return {lane: dict(values, limit=LANE_LIMITS[lane]) for lane, values in _stats.items()}
