# tests/infra/test_log_cleanup.py
#
# בודק utils/shared/log_cleanup.py (item 26) - ניקוי גיבויי-לוג ישנים מבוסס-זמן,
# משלים ל-RotatingFileHandler הקיים (utils/shared/logging_setup.py) שכבר מגביל
# לפי גודל בלבד.
import os
import time


from utils.shared.log_cleanup import purge_old_log_backups


def _touch_with_mtime(path, age_days):
    path.write_text("log content", encoding="utf-8")
    old_time = time.time() - age_days * 86400
    os.utime(path, (old_time, old_time))


def test_deletes_backup_files_older_than_max_age(tmp_path):
    old_backup = tmp_path / "gui.log.1"
    _touch_with_mtime(old_backup, age_days=45)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert deleted == ["gui.log.1"]
    assert not old_backup.exists()


def test_keeps_backup_files_within_max_age(tmp_path):
    recent_backup = tmp_path / "gui.log.1"
    _touch_with_mtime(recent_backup, age_days=5)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert deleted == []
    assert recent_backup.exists()


def test_never_touches_the_live_log_file_itself(tmp_path):
    # קובץ ה-.log הפעיל (בלי סיומת מספרית) אסור שייגע, גם אם הוא ישן - הוא
    # עשוי להיות פתוח כרגע ב-handle של תהליך חי (GUI/בוט/web_app).
    live_log = tmp_path / "gui.log"
    _touch_with_mtime(live_log, age_days=100)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert deleted == []
    assert live_log.exists()


def test_handles_multiple_backup_files_across_different_log_streams(tmp_path):
    _touch_with_mtime(tmp_path / "gui.log.1", age_days=45)
    _touch_with_mtime(tmp_path / "web_app.log.2", age_days=60)
    _touch_with_mtime(tmp_path / "web_app.log.1", age_days=5)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert sorted(deleted) == ["gui.log.1", "web_app.log.2"]
    assert (tmp_path / "web_app.log.1").exists()


def test_returns_empty_list_when_logs_dir_is_empty(tmp_path):
    assert purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30) == []


# --- item: לוגים מובנים (JSON-lines) - אותה מדיניות-זמן חלה גם על .jsonl.* ---

def test_deletes_jsonl_backup_files_older_than_max_age(tmp_path):
    old_backup = tmp_path / "gui.jsonl.1"
    _touch_with_mtime(old_backup, age_days=45)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert deleted == ["gui.jsonl.1"]
    assert not old_backup.exists()


def test_never_touches_the_live_jsonl_file_itself(tmp_path):
    live_jsonl = tmp_path / "gui.jsonl"
    _touch_with_mtime(live_jsonl, age_days=100)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert deleted == []
    assert live_jsonl.exists()


def test_handles_mixed_log_and_jsonl_backups_together(tmp_path):
    _touch_with_mtime(tmp_path / "gui.log.1", age_days=45)
    _touch_with_mtime(tmp_path / "gui.jsonl.1", age_days=45)
    _touch_with_mtime(tmp_path / "gui.jsonl.2", age_days=5)

    deleted = purge_old_log_backups(logs_dir=str(tmp_path), max_age_days=30)

    assert sorted(deleted) == ["gui.jsonl.1", "gui.log.1"]
    assert (tmp_path / "gui.jsonl.2").exists()


def test_handles_missing_logs_dir_gracefully(tmp_path):
    missing_dir = str(tmp_path / "does_not_exist")
    assert purge_old_log_backups(logs_dir=missing_dir, max_age_days=30) == []
