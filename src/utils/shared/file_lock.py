# utils/shared/file_lock.py
#
# מנעול-קובץ קצר-טווח, חוצה-תהליכים, לקטעי קריאה-שינוי-כתיבה מהירים על קובץ
# JSON קטן (data/config.json, שגם הדסקטופ - utils/shared/state.py - וגם הווב-אפ
# כותבים אליו) - לא utils/shared/render_lock.py: זה בנוי לרינדורים ארוכים (שעות,
# עם תור-ממתינים ועדיפויות). קטע קריטי של שמירת הגדרות אמור לקחת אלפיות
# שנייה, לא לחכות בתור מאחורי רינדור כבד ולא לחסום רינדור שממתין (item:
# בדיקת באגים מקיפה - נמצא: כתיבה מקבילה לא-מתואמת בין שני התהליכים יכולה
# לדרוס בשקט שינוי הגדרות של האחד עם זה של השני).

import contextlib
import os
import time

try:
    import psutil
except ImportError:
    psutil = None

# קטע קריטי תקין (open+json.load/dump קטן) אף פעם לא אמור לקחת יותר מזה -
# מנעול ישן יותר נחשב תקוע (תהליך שהחזיק אותו קרס בלי לשחרר) ומדולג.
_STALE_SECONDS = 10.0


def _is_pid_alive(pid):
    if psutil is None or pid is None:
        return False
    try:
        return bool(psutil.pid_exists(pid))
    except Exception:
        return False


def _read_holder_pid(lock_path):
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


@contextlib.contextmanager
def file_lock(lock_path, timeout=5.0, poll_interval=0.05):
    """תופס lock_path (יצירה אטומית O_EXCL) לפני ה-yield, משחרר (מוחק) תמיד
    אחריו - גם על חריגה. TimeoutError אם לא הצליח תוך timeout שניות; קטעים
    קריטיים שהשתמשו בזה תמיד קצרים, אז ברירת המחדל נמוכה בכוונה (לא ממתינים
    כמו render_lock שיכול לחכות שעה שלמה)."""
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            break
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(lock_path)
            except OSError:
                age = None
            is_stale = (age is not None and age > _STALE_SECONDS) or not _is_pid_alive(_read_holder_pid(lock_path))
            if is_stale:
                try:
                    os.remove(lock_path)
                except OSError:
                    pass
                continue
            if time.time() - start >= timeout:
                raise TimeoutError(f"לא הצלחתי לתפוס מנעול {lock_path} אחרי {timeout:.1f} שניות.")
            time.sleep(poll_interval)
    try:
        yield
    finally:
        try:
            os.remove(lock_path)
        except OSError:
            pass
