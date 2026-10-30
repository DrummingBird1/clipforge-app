# tests/infra/test_worker_pause_resume.py
#
# Pause/Resume (item: השהיה/המשך של ריצה - כדי לפנות CPU/GPU זמנית בלי לאבד
# התקדמות) - בודק עם תת-תהליכים אמיתיים (לא mock ל-psutil) שההשהיה/המשך
# באמת קופאים/ממשיכים תהליך ותת-תהליכיו, ושה-keepalive מרענן את render_lock.
import subprocess
import sys
import time


import psutil
import pytest

import utils.shared.worker as worker_module
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

# הנכד (המפרש האמיתי, ראו _process_tree) מדפיס את זה רק כשכל שרשרת ה-CreateProcess כבר הסתיימה.
_READY = "ready"

# תהליך שמריץ תת-תהליך משלו (מדמה video_editor.py שמריץ ffmpeg) - כדי לוודא
# שההשהיה מגיעה גם לילדים, לא רק לתהליך העליון עצמו.
_SLEEP_CHILD = f"print({_READY!r}, flush=True)\nimport time\ntime.sleep(6)\n"
_PARENT_WITH_CHILD_SCRIPT = (
    "import subprocess, sys\n"
    f"subprocess.Popen([sys.executable, '-c', {_SLEEP_CHILD!r}]).wait()\n"
)

# לולאה עסוקה (שורפת CPU), עד 30 שניות - רשת ביטחון לתהליך יתום אם ה-teardown לא הספיק להרוג אותו.
_BUSY_LOOP = "import time\nend = time.time() + 30\nwhile time.time() < end:\n    pass\n"

# כמו _PARENT_WITH_CHILD_SCRIPT, אבל ההורה והילד עסוקים ב-CPU (כמו video_editor.py + ffmpeg באמצע רינדור):
# תהליך שממתין ב-wait() לא צורך CPU גם בלי השהיה, אז רק תהליך עסוק מוכיח שההשהיה באמת עוצרת אותו.
_BUSY_CHILD = f"print({_READY!r}, flush=True)\n{_BUSY_LOOP}"
_BUSY_PARENT_WITH_CHILD_SCRIPT = (
    "import subprocess, sys\n"
    f"subprocess.Popen([sys.executable, '-c', {_BUSY_CHILD!r}])\n"
    f"{_BUSY_LOOP}"
)


def _real_children(pid):
    # CREATE_NO_WINDOW (NO_WINDOW_FLAGS) נותן לתהליך conhost.exe משלו, ו-psutil מונה אותו כילד. הוא לא חלק
    # מהעבודה שמשהים, ולפעמים לא מדווח STOPPED אחרי suspend - אז מתעלמים ממנו.
    return [c for c in psutil.Process(pid).children(recursive=True) if c.name().lower() != "conhost.exe"]


def _process_tree(script):
    proc = subprocess.Popen([sys.executable, "-c", script], creationflags=NO_WINDOW_FLAGS, stdout=subprocess.PIPE)
    # מחכים ל-ready מהנכד, לא ל"עץ יציב" לפי זמן: python של venv ב-Windows הוא launcher שמריץ את המפרש האמיתי
    # כתהליך-בן, וכל אחד מהשניים (ההורה והילד) הוא launcher + מפרש. השהיה באמצע השרשרת משאירה תהליך שנולד
    # אחריה רץ, או מכשילה את ה-CreateProcess ("Access is denied") - בלי קשר למה שהטסטים בודקים.
    assert proc.stdout.readline().decode().strip() == _READY
    # שומרים את כל העץ מראש - proc.kill() לבד הורג רק את ה-launcher העליון ומשאיר את השאר (מושהים לנצח,
    # בטסטים שלא עושים resume) כתהליכים יתומים.
    tree = [psutil.Process(proc.pid), *psutil.Process(proc.pid).children(recursive=True)]
    yield proc
    for p in tree:
        try:
            p.kill()
        except psutil.Error:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    proc.stdout.close()


@pytest.fixture
def real_proc_with_child():
    yield from _process_tree(_PARENT_WITH_CHILD_SCRIPT)


@pytest.fixture
def busy_proc_with_child():
    yield from _process_tree(_BUSY_PARENT_WITH_CHILD_SCRIPT)


def _wait_until(predicate, timeout=5.0, interval=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("התנאי לא התקיים בזמן (כשל מפורש במקום המשך שקט לאסרציה מטעה)")


def test_pause_current_suspends_process_and_its_children(real_proc_with_child, monkeypatch):
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    w = worker_module.TaskWorker()
    w.active_processes[id(real_proc_with_child)] = real_proc_with_child
    children = _real_children(real_proc_with_child.pid)
    assert children, "התהליך המדומה אמור להוליד תת-תהליך משלו"

    w.pause_current()
    # polling (לא sleep קבוע של 0.2s) - תחת עומס (כל הסוויטה + טסטי דפדפן במקביל)
    # Windows לפעמים מדווח את מצב ה-suspend באיחור, והטסט נכשל לסירוגין בלי באג אמיתי.
    _wait_until(lambda: all(p.status() == psutil.STATUS_STOPPED for p in [psutil.Process(real_proc_with_child.pid), *children]))

    assert w.is_paused() is True
    # psutil ב-Windows מחשב "stopped" לפי מצב *כל* ה-threads, ו-thread שנולד ממש אחרי ה-suspend (סיום אתחול המפרש)
    # נראה running לרגע - לכן גם האימות הסופי הוא "מגיע ליציב stopped" ולא קריאה בודדת (זה היה הכשל לסירוגין)
    _wait_until(lambda: all(p.status() == psutil.STATUS_STOPPED for p in [psutil.Process(real_proc_with_child.pid), *children]))


def test_resume_current_resumes_process_and_its_children(real_proc_with_child, monkeypatch):
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    w = worker_module.TaskWorker()
    w.active_processes[id(real_proc_with_child)] = real_proc_with_child
    children = _real_children(real_proc_with_child.pid)
    w.pause_current()
    _wait_until(lambda: psutil.Process(real_proc_with_child.pid).status() == psutil.STATUS_STOPPED)

    w.resume_current()
    _wait_until(lambda: all(p.status() != psutil.STATUS_STOPPED for p in [psutil.Process(real_proc_with_child.pid), *children]))

    assert w.is_paused() is False
    assert psutil.Process(real_proc_with_child.pid).status() != psutil.STATUS_STOPPED
    for child in children:
        assert child.status() != psutil.STATUS_STOPPED


# Windows סופר זמן CPU ביחידות של tick של השעון (15.625ms), וההשהיה עצמה יכולה עוד להיות מחויבת ב-tick אחד
# אחרי ש-pause_current() חוזר - מרשים tick אחד לכל היותר. תהליך עסוק שבאמת רץ בשנייה הזו צובר קרוב לשנייה שלמה.
_ONE_CPU_TICK_SECONDS = 0.016


def test_a_suspended_process_consumes_no_cpu_time_while_paused(busy_proc_with_child, monkeypatch):
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    w = worker_module.TaskWorker()
    w.active_processes[id(busy_proc_with_child)] = busy_proc_with_child
    tree = [psutil.Process(busy_proc_with_child.pid), *_real_children(busy_proc_with_child.pid)]
    assert len(tree) >= 2, "התהליך המדומה אמור להוליד תת-תהליך משלו"

    w.pause_current()
    # מודדים רק אחרי שכולם מדווחים STOPPED - אחרת ה-tick האחרון לפני שההשהיה נכנסה לתוקף נספר בשנייה הנמדדת
    _wait_until(lambda: all(p.status() == psutil.STATUS_STOPPED for p in tree))

    before = [p.cpu_times() for p in tree]
    time.sleep(1.0)
    after = [p.cpu_times() for p in tree]

    for p, b, a in zip(tree, before, after):
        assert a.user - b.user <= _ONE_CPU_TICK_SECONDS, f"pid {p.pid} צבר זמן CPU (user) בזמן ההשהיה"
        assert a.system - b.system <= _ONE_CPU_TICK_SECONDS, f"pid {p.pid} צבר זמן CPU (system) בזמן ההשהיה"


def test_pause_current_with_no_active_processes_is_a_noop():
    w = worker_module.TaskWorker()
    w.pause_current()
    assert w.is_paused() is False


def test_pause_current_without_psutil_logs_a_warning_and_does_not_crash(monkeypatch):
    monkeypatch.setattr(worker_module, "psutil", None)
    w = worker_module.TaskWorker()
    w.pause_current()
    assert w.is_paused() is False
    line, tag = w.log_queue.get_nowait()
    assert "psutil" in line
    assert tag == "red"


def test_terminate_current_clears_paused_state_and_stops_keepalive(real_proc_with_child, monkeypatch):
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    w = worker_module.TaskWorker()
    w.active_processes[id(real_proc_with_child)] = real_proc_with_child
    w.pause_current()
    assert w.is_paused() is True

    w.terminate_current()

    assert w.is_paused() is False
    assert w._pause_stop_event.is_set()


def test_terminate_current_kills_child_process_too(real_proc_with_child, monkeypatch):
    # item: בדיקת באגים מקיפה - terminate_current בעבר עצר רק את התהליך
    # העליון (python.exe), והשאיר את תת-התהליך (מדמה ffmpeg.exe) רץ כתהליך-
    # יתום. עכשיו, כמו pause_current/_suspend_tree, גם הילד נעצר.
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    w = worker_module.TaskWorker()
    w.active_processes[id(real_proc_with_child)] = real_proc_with_child
    children = _real_children(real_proc_with_child.pid)
    assert children, "התהליך המדומה אמור להוליד תת-תהליך משלו"

    w.terminate_current()
    real_proc_with_child.wait(timeout=5)

    for child in children:
        deadline = time.time() + 5
        while child.is_running() and time.time() < deadline:
            time.sleep(0.05)
        assert not child.is_running(), "תת-התהליך אמור להיעצר יחד עם ההורה, לא להישאר תלוי כתהליך-יתום"


def test_terminate_current_without_psutil_falls_back_to_plain_terminate(real_proc_with_child, monkeypatch):
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    monkeypatch.setattr(worker_module, "psutil", None)
    w = worker_module.TaskWorker()
    w.active_processes[id(real_proc_with_child)] = real_proc_with_child

    w.terminate_current()  # לא אמור לזרוק גם בלי psutil - נופל ל-proc.terminate() הרגיל
    real_proc_with_child.wait(timeout=5)

    assert real_proc_with_child.poll() is not None


def test_pause_keepalive_touches_render_lock_periodically(real_proc_with_child, monkeypatch):
    monkeypatch.setattr(worker_module, "_PAUSE_KEEPALIVE_INTERVAL_SECONDS", 0.05)
    touch_calls = []
    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: touch_calls.append(1))
    w = worker_module.TaskWorker()
    w.active_processes[id(real_proc_with_child)] = real_proc_with_child

    w.pause_current()
    time.sleep(0.3)
    w.resume_current()
    calls_at_resume = len(touch_calls)
    time.sleep(0.3)

    assert calls_at_resume >= 1, "ה-keepalive אמור לרענן את render_lock לפחות פעם אחת בזמן ההשהיה"
    assert len(touch_calls) == calls_at_resume, "אחרי resume, ה-keepalive לא אמור לרענן יותר"
