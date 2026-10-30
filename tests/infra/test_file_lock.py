# tests/infra/test_file_lock.py
#
# בודק utils/shared/file_lock.py (item: בדיקת באגים מקיפה - מנעול קצר-טווח חוצה-
# תהליכים ל-config.json) - תופס/משחרר תקין, מונע כניסה כפולה בו-זמנית,
# TimeoutError כשהמנעול תפוס ולא משתחרר, ומדלג על מנעול תקוע (PID מת/ישן מדי).
import os
import time


import pytest

import utils.shared.file_lock as file_lock_module
from utils.shared.file_lock import file_lock


def test_acquires_and_releases_lock(tmp_path):
    lock_path = str(tmp_path / "test.lock")

    with file_lock(lock_path):
        assert os.path.exists(lock_path)

    assert not os.path.exists(lock_path)  # שוחרר (נמחק) אחרי היציאה מה-with


def test_releases_lock_even_on_exception(tmp_path):
    lock_path = str(tmp_path / "test.lock")

    with pytest.raises(RuntimeError):
        with file_lock(lock_path):
            raise RuntimeError("boom")

    assert not os.path.exists(lock_path)


def test_second_caller_waits_for_first_to_release(tmp_path):
    lock_path = str(tmp_path / "test.lock")

    with file_lock(lock_path):
        # מנעול כבר תפוס - ניסיון שני עם timeout קצר אמור להיכשל
        with pytest.raises(TimeoutError):
            with file_lock(lock_path, timeout=0.2, poll_interval=0.05):
                pass


def test_raises_timeout_error_with_descriptive_message(tmp_path):
    lock_path = str(tmp_path / "test.lock")
    os.makedirs(tmp_path, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))  # מנעול "תפוס" ע"י תהליך חי (עצמנו)

    with pytest.raises(TimeoutError, match="לא הצלחתי לתפוס מנעול"):
        with file_lock(lock_path, timeout=0.15, poll_interval=0.05):
            pass


def test_skips_stale_lock_from_a_dead_pid(tmp_path, monkeypatch):
    lock_path = str(tmp_path / "test.lock")
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write("999999999")  # PID שכמעט בוודאות לא רץ

    monkeypatch.setattr(file_lock_module, "_is_pid_alive", lambda pid: False)

    with file_lock(lock_path, timeout=1.0):
        assert os.path.exists(lock_path)


def test_skips_stale_lock_older_than_threshold(tmp_path, monkeypatch):
    lock_path = str(tmp_path / "test.lock")
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))  # PID חי, אבל המנעול "ישן" בכל זאת

    monkeypatch.setattr(file_lock_module, "_STALE_SECONDS", 0.0)
    old_time = time.time() - 100
    os.utime(lock_path, (old_time, old_time))

    with file_lock(lock_path, timeout=1.0):
        assert os.path.exists(lock_path)


def test_creates_parent_directory_if_missing(tmp_path):
    lock_path = str(tmp_path / "nested" / "dir" / "test.lock")

    with file_lock(lock_path):
        assert os.path.exists(lock_path)


def test_sequential_acquisitions_both_succeed(tmp_path):
    lock_path = str(tmp_path / "test.lock")

    with file_lock(lock_path):
        pass
    with file_lock(lock_path):
        pass  # השני לא אמור להיתקע - הראשון שוחרר כראוי
