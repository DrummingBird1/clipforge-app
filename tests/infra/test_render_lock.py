# tests/infra/test_render_lock.py
import os
import threading
import time


import pytest

from utils.shared import render_lock


@pytest.fixture
def lock_path(tmp_path):
    return str(tmp_path / "render.lock")


@pytest.fixture
def waiters_path(tmp_path):
    # תמיד ניתנת במפורש בטסטים - בלי זה, כל הטסטים היו חולקים את קובץ הרשימה
    # האמיתי בdata/render_waiters.json (ברירת המחדל), ומזהמים אחד את השני
    # (ובפוטנציה גם ריצה אמיתית) עם רשומות ממתינים משותפות.
    return str(tmp_path / "render_waiters.json")


def _wait_for_waiters(waiters_path, count, timeout=10.0):
    """גל 23: מחכים שהממתינים באמת נרשמו בקובץ, במקום שינה קבועה של 0.15-0.2 שניות."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(render_lock.get_waiters(waiters_path=waiters_path)) >= count:
            return
        time.sleep(0.01)
    raise AssertionError(f"לא נרשמו {count} ממתינים תוך {timeout} שניות")


def test_acquire_and_release_roundtrip(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    assert os.path.exists(lock_path)
    render_lock.release(lock_path=lock_path)
    assert not os.path.exists(lock_path)


def test_release_missing_file_does_not_raise(lock_path):
    render_lock.release(lock_path=lock_path)  # לא קיים בכלל - לא אמור לזרוק


def test_second_acquire_blocks_until_release(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)

    acquired_second = threading.Event()

    def try_second():
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05)
        acquired_second.set()

    t = threading.Thread(target=try_second, daemon=True)
    t.start()
    time.sleep(0.2)
    assert not acquired_second.is_set()  # עדיין תפוס - לא אמור להצליח

    render_lock.release(lock_path=lock_path)
    t.join(timeout=10)  # תחת עומס מלא ב-CI (xdist) הת'רד השני מתעורר לאט; חוזר מיד כשהוא תפס
    assert acquired_second.is_set()


def test_acquire_times_out(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    with pytest.raises(TimeoutError):
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, timeout=0.2)
    render_lock.release(lock_path=lock_path)


def test_stale_lock_from_dead_pid_is_recovered(lock_path, waiters_path, monkeypatch):
    # יוצרים "מנעול תקוע" עם PID שכבר לא רץ (קורה כשתהליך קודם קרס בלי לשחרר)
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    monkeypatch.setattr(render_lock, "_is_pid_alive", lambda pid: False)

    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, timeout=2)  # לא אמור להיתקע/לזרוק
    assert os.path.exists(lock_path)
    render_lock.release(lock_path=lock_path)


def test_on_wait_called_once_when_lock_held(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    calls = []

    def do_wait_then_release():
        time.sleep(0.15)
        render_lock.release(lock_path=lock_path)

    threading.Thread(target=do_wait_then_release, daemon=True).start()
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, on_wait=lambda waited: calls.append(waited))
    assert len(calls) == 1
    render_lock.release(lock_path=lock_path)


def test_get_status_none_when_free(lock_path):
    assert render_lock.get_status(lock_path=lock_path) is None


def test_get_status_reports_holder_when_held(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    status = render_lock.get_status(lock_path=lock_path, waiters_path=waiters_path)
    assert status["pid"] == os.getpid()
    assert status["age_seconds"] >= 0
    assert status["is_stale"] is False
    assert status["queue_length"] == 0
    render_lock.release(lock_path=lock_path)


def test_old_lock_from_still_alive_pid_is_recovered_as_stale(lock_path, waiters_path, monkeypatch):
    # רגרסיה שקרתה בפועל בסשן הזה: תהליך web_app.py ישן ששכחתי לסגור החזיק
    # מנעול "בריא" (PID עדיין חי) במשך שעות וחסם כל רינדור אחר לנצח - בדיקת
    # PID-בלבד לא הייתה תופסת את זה, כי הוא לא באמת קרס.
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    monkeypatch.setattr(render_lock, "_is_pid_alive", lambda pid: True)  # "עדיין חי"

    old_acquired_at = time.time() - (render_lock.MAX_LOCK_AGE_SECONDS + 60)
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f'{{"pid": {os.getpid()}, "acquired_at": {old_acquired_at}}}')

    status = render_lock.get_status(lock_path=lock_path, waiters_path=waiters_path)
    assert status["is_stale"] is True

    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, timeout=2)  # לא אמור להיתקע/לזרוק
    render_lock.release(lock_path=lock_path)


def test_recent_lock_from_alive_pid_is_not_stale(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    status = render_lock.get_status(lock_path=lock_path, waiters_path=waiters_path)
    assert status["is_stale"] is False
    render_lock.release(lock_path=lock_path)


# --- touch (item: Pause/Resume keep-alive against MAX_LOCK_AGE_SECONDS) ---

def test_touch_refreshes_acquired_at_for_own_pid(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    old_acquired_at = time.time() - (render_lock.MAX_LOCK_AGE_SECONDS + 60)
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f'{{"pid": {os.getpid()}, "acquired_at": {old_acquired_at}}}')
    assert render_lock.get_status(lock_path=lock_path, waiters_path=waiters_path)["is_stale"] is True

    render_lock.touch(lock_path=lock_path)

    status = render_lock.get_status(lock_path=lock_path, waiters_path=waiters_path)
    assert status["is_stale"] is False
    assert status["pid"] == os.getpid()
    render_lock.release(lock_path=lock_path)


def test_touch_does_nothing_for_a_lock_owned_by_another_pid(lock_path):
    other_pid = os.getpid() + 1
    old_acquired_at = time.time() - (render_lock.MAX_LOCK_AGE_SECONDS + 60)
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f'{{"pid": {other_pid}, "acquired_at": {old_acquired_at}}}')

    render_lock.touch(lock_path=lock_path)

    with open(lock_path, "r", encoding="utf-8") as f:
        data = f.read()
    assert f'"acquired_at": {old_acquired_at}' in data


def test_touch_on_missing_lock_does_not_raise(lock_path):
    render_lock.touch(lock_path=lock_path)  # לא קיים בכלל - לא אמור לזרוק
    assert not os.path.exists(lock_path)


# --- render_lock_if_needed (item: scripts self-protect even run directly) ---

def test_render_lock_if_needed_acquires_and_releases_by_default(lock_path, waiters_path, monkeypatch):
    monkeypatch.delenv(render_lock.CALLER_HOLDS_LOCK_ENV_VAR, raising=False)
    with render_lock.render_lock_if_needed(lock_path=lock_path, waiters_path=waiters_path):
        assert os.path.exists(lock_path)
    assert not os.path.exists(lock_path)


def test_render_lock_if_needed_skips_acquisition_when_caller_already_holds_it(lock_path, waiters_path, monkeypatch):
    # זה בדיוק המצב שהתיקון הזה נועד למנוע: worker.py כבר תפס את המנעול
    # ומעביר את משתנה הסביבה לתת-התהליך - תפיסה נוספת כאן הייתה נועלת אותו
    # (התהליך היה מחכה למנעול שההורה שלו מחזיק). מדמים "מנעול תפוס על ידי
    # מישהו אחר" בלי לשחרר אותו בכלל - אם render_lock_if_needed בכל זאת מנסה
    # לתפוס, הטסט הזה היה נתקע/נכשל.
    monkeypatch.setenv(render_lock.CALLER_HOLDS_LOCK_ENV_VAR, "1")
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)  # "ההורה" מחזיק את המנעול
    try:
        with render_lock.render_lock_if_needed(lock_path=lock_path, waiters_path=waiters_path, timeout=0.2):
            pass  # לא אמור לנסות לתפוס בכלל, אז לא אמור לחכות/להיכשל
    finally:
        render_lock.release(lock_path=lock_path)


def test_render_lock_if_needed_does_not_release_lock_it_did_not_acquire(lock_path, waiters_path, monkeypatch):
    monkeypatch.setenv(render_lock.CALLER_HOLDS_LOCK_ENV_VAR, "1")
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    try:
        with render_lock.render_lock_if_needed(lock_path=lock_path, waiters_path=waiters_path):
            pass
        assert os.path.exists(lock_path), "render_lock_if_needed שחרר מנעול שהוא בכלל לא תפס"
    finally:
        render_lock.release(lock_path=lock_path)


# --- waiters queue / soft priority (item: render queue visibility) ---

def test_get_waiters_empty_when_nobody_waiting(waiters_path):
    assert render_lock.get_waiters(waiters_path=waiters_path) == []


def test_queue_length_reflects_other_waiters(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)

    waiting_started = threading.Event()

    def wait_forever():
        waiting_started.set()
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05)
        render_lock.release(lock_path=lock_path)

    t = threading.Thread(target=wait_forever, daemon=True)
    t.start()
    waiting_started.wait(timeout=2)
    _wait_for_waiters(waiters_path, 1)

    status = render_lock.get_status(lock_path=lock_path, waiters_path=waiters_path)
    assert status["queue_length"] == 1

    render_lock.release(lock_path=lock_path)
    t.join(timeout=2)


# _next_in_line_key נבדקת ישירות (unit test טהור על dict סינתטי) - המפתחות
# כאן הם דוגמה בלבד, הפונקציה לא תלויה בפורמט שלהם (ראו waiter_key ב-acquire,
# שכולל גם threading.get_ident() כדי ששני threads באותו תהליך לא יחלקו רשומה).
def test_next_in_line_key_prefers_higher_priority():
    waiters = {
        "111:1": {"pid": 111, "registered_at": 100.0, "priority": 0, "label": "low"},
        "222:1": {"pid": 222, "registered_at": 200.0, "priority": 10, "label": "high"},  # נרשם מאוחר יותר אבל עדיפות גבוהה
    }
    assert render_lock._next_in_line_key(waiters) == "222:1"


def test_next_in_line_key_breaks_ties_by_registration_order():
    waiters = {
        "111:1": {"pid": 111, "registered_at": 200.0, "priority": 5, "label": "second"},
        "222:1": {"pid": 222, "registered_at": 100.0, "priority": 5, "label": "first"},  # אותה עדיפות, נרשם קודם
    }
    assert render_lock._next_in_line_key(waiters) == "222:1"


def test_next_in_line_key_none_when_empty():
    assert render_lock._next_in_line_key({}) is None


def test_acquire_records_priority_and_label_while_waiting(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)

    started = threading.Event()

    def wait_with_priority():
        started.set()
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, priority=7, label="my job")
        render_lock.release(lock_path=lock_path)

    t = threading.Thread(target=wait_with_priority, daemon=True)
    t.start()
    started.wait(timeout=2)
    _wait_for_waiters(waiters_path, 1)

    waiters = render_lock.get_waiters(waiters_path=waiters_path)
    assert len(waiters) == 1
    assert waiters[0]["priority"] == 7
    assert waiters[0]["label"] == "my job"

    render_lock.release(lock_path=lock_path)
    t.join(timeout=2)


def test_waiter_unregisters_itself_after_acquiring(lock_path, waiters_path):
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    render_lock.release(lock_path=lock_path)
    assert render_lock.get_waiters(waiters_path=waiters_path) == []


def test_stale_waiter_entry_is_reaped(waiters_path, monkeypatch):
    render_lock._register_waiter(999999, priority=0, label="ghost", waiters_path=waiters_path, waiter_key="999999:1")
    monkeypatch.setattr(render_lock, "_is_pid_alive", lambda pid: False)
    assert render_lock.get_waiters(waiters_path=waiters_path) == []


def test_acquire_never_reaps_its_own_waiter_entry_even_if_is_pid_alive_lies(lock_path, waiters_path, monkeypatch):
    # רגרסיה אמיתית שנתפסה תוך כדי כתיבת הפיצ'ר: _is_pid_alive שמוחזר False
    # לכולם (מוק גורף, בדיוק כמו test_stale_lock_from_dead_pid_is_recovered
    # למעלה) לא אמור לגרום לתהליך לחכות לנצח על ההרשמה-העצמית שלו לתור -
    # תהליך תמיד "חי" מנקודת המבט של עצמו.
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    monkeypatch.setattr(render_lock, "_is_pid_alive", lambda pid: False)
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, timeout=2)
    render_lock.release(lock_path=lock_path)


def test_two_same_process_threads_both_acquire_without_one_hanging_forever(lock_path, waiters_path):
    # item: בדיקת באגים מקיפה - regression אמיתי שנמצא בביקורת: לפני התיקון,
    # שני threads באותו תהליך בדיוק (os.getpid() זהה - למשל cogs/remote_execution.py
    # ו-cogs/scheduler_cog.py, שניהם דרך run_in_executor על אותו תהליך בוט)
    # חלקו רשומת-ממתין אחת ברשימה (מפתח=str(pid) בלבד, בלי thread ident). מי
    # שהצליח לתפוס ראשון ומבטל את הרשמתו-שלו מחק בטעות גם את ההרשמה של השני,
    # שנשאר ממתין לנצח (בלי הרשמה-מחדש בלולאה) בלי שאף אחד ישחרר אותו. שני
    # threads אמיתיים כאן (לא dict סינתטי) בודקים את זה ישירות - עכשיו אפשרי
    # בזכות waiter_key שכולל גם threading.get_ident().
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)  # "מישהו אחר" מחזיק כרגע

    results = []
    started_first = threading.Event()
    started_second = threading.Event()

    def _try_acquire(label, started_event):
        started_event.set()
        # timeout נדיב: תחת עומס (כל החבילה במקביל) ההרשמה של שני ה-threads לבדה יכולה לקחת כמה שניות
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, timeout=20, label=label)
        results.append(label)
        render_lock.release(lock_path=lock_path)

    t1 = threading.Thread(target=_try_acquire, args=("first", started_first), daemon=True)
    t2 = threading.Thread(target=_try_acquire, args=("second", started_second), daemon=True)
    t1.start()
    started_first.wait(timeout=2)
    _wait_for_waiters(waiters_path, 1)  # t1 רשום בפועל בקובץ הממתינים לפני ש-t2 מתחיל
    t2.start()
    started_second.wait(timeout=2)
    _wait_for_waiters(waiters_path, 2)  # גם t2 רשום, לפני ששחררים ושני ה-threads מתחרים

    render_lock.release(lock_path=lock_path)  # עכשיו שני ה-threads הממתינים מתחרים על המנעול שהתפנה

    t1.join(timeout=25)
    t2.join(timeout=25)

    assert sorted(results) == ["first", "second"], (
        f"לפני התיקון, אחד מהשניים היה נתקע לנצח בהמתנה במקום שני ה-threads להצליח: {results}"
    )


def test_release_succeeds_while_a_waiter_has_the_lock_file_open(lock_path):
    # 21.10.2026: ב-Windows os.remove נכשל כשקובץ פתוח אצל מישהו אחר - וממתין פותח את קובץ המנעול בכל סבב (_is_stale).
    # release() בלע את השגיאה, והמנעול נשאר תפוס בשקט: כך נכשל test_two_same_process_threads (2 מתוך 20 תחת עומס).
    render_lock.acquire(lock_path=lock_path, waiters_path=lock_path + ".waiters")
    reader = open(lock_path, encoding="utf-8")
    closer = threading.Timer(0.1, reader.close)
    closer.start()
    try:
        render_lock.release(lock_path=lock_path)
    finally:
        closer.join()
        reader.close()
    assert not os.path.exists(lock_path), "release() החזיר בלי לשחרר את המנעול"


def test_a_waiter_whose_registration_was_lost_still_gets_the_lock(lock_path, waiters_path):
    # 21.10.2026: קובץ הממתינים נכתב בלי נעילה, וממתין אחר שקרא אותו חצי-כתוב (ריק) וכתב בחזרה מוחק הרשמות.
    # ממתין בלי הרשמה לא היה "הבא בתור" אף פעם - חיכה עד ה-timeout גם כשהמנעול פנוי (timelapse_maker תחת עומס).
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path)
    done = threading.Event()

    def _wait_then_take():
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.05, timeout=10)
        render_lock.release(lock_path=lock_path)
        done.set()

    thread = threading.Thread(target=_wait_then_take, daemon=True)
    thread.start()
    _wait_for_waiters(waiters_path, 1)
    with open(waiters_path, "w", encoding="utf-8") as f:
        f.write("{}")   # ההרשמה אבדה
    render_lock.release(lock_path=lock_path)
    assert done.wait(timeout=10), "הממתין נשאר תקוע אחרי שההרשמה שלו אבדה, אף שהמנעול פנוי"
    thread.join(timeout=5)


def _lock_file_mid_deletion(monkeypatch, lock_path, times):
    """os.open(O_CREAT|O_EXCL) על קובץ המנעול זורק PermissionError `times` פעמים - כמו ב-Windows כשקובץ המנעול עוד באמצע
    מחיקה (תהליך אחר, למשל סורק, מחזיק אותו פתוח ברגע ה-release). times=None = תמיד."""
    real_open = os.open
    calls = {"denied": 0}

    def _open(path, flags, *args, **kwargs):
        if path == lock_path and flags & os.O_EXCL and (times is None or calls["denied"] < times):
            calls["denied"] += 1
            raise PermissionError(13, "Access is denied", path)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(render_lock.os, "open", _open)
    return calls


def test_a_lock_file_mid_deletion_means_keep_waiting(lock_path, waiters_path, monkeypatch):
    # 23.10.2026, בריצה המלאה: test_second_acquire_blocks_until_release נפל - os.open של הממתין זרק PermissionError
    # ממש אחרי release(), ה-thread מת, ורינדור אמיתי במקומו היה נכשל במקום לחכות לסבב הבא.
    calls = _lock_file_mid_deletion(monkeypatch, lock_path, times=3)
    render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.01, timeout=10)
    assert calls["denied"] == 3 and os.path.exists(lock_path)
    render_lock.release(lock_path=lock_path)


def test_a_lock_file_that_stays_denied_still_times_out(lock_path, waiters_path, monkeypatch):
    # אותו timeout כמו מנעול תפוס - ממתינים, לא נתקעים מעבר לו ולא נופלים על PermissionError
    _lock_file_mid_deletion(monkeypatch, lock_path, times=None)
    with pytest.raises(TimeoutError):
        render_lock.acquire(lock_path=lock_path, waiters_path=waiters_path, poll_interval=0.01, timeout=0.3)
