# tests/bot/test_scheduler_db_backup_restore.py
#
# בודק _backup_database() (item 27) - עד כה אף טסט לא בדק אפילו את יצירת
# הגיבוי הזה, ובוודאי לא ש*אפשר לשחזר ממנו בפועל* (שהקובץ שנוצר הוא DB תקין
# עם אותם נתונים בדיוק כמו המקור, לא רק "קובץ נוצר בגודל כלשהו"). זו בדיוק
# הבדיקה שהייתה חסרה - פתיחת קובץ הגיבוי עצמו (לא המקור) ושליפת שורות ממנו.
import os
import sqlite3


from cogs import scheduler_cog


def _make_real_sqlite_db(db_path, rows):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE job_history (id INTEGER PRIMARY KEY AUTOINCREMENT, script_name TEXT, status TEXT)")
    conn.executemany("INSERT INTO job_history (script_name, status) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def test_backup_database_is_a_valid_sqlite_file_with_identical_data(tmp_path, monkeypatch):
    db_path = tmp_path / "clipforge_data.db"
    backups_dir = tmp_path / "backups"
    monkeypatch.setattr(scheduler_cog, "DB_PATH", str(db_path))
    monkeypatch.setattr(scheduler_cog, "BACKUPS_DIR", str(backups_dir))

    rows = [("story_cutter.py", "success"), ("video_editor.py", "failed")]
    _make_real_sqlite_db(db_path, rows)

    ok, error = scheduler_cog._backup_database()
    assert ok is True
    assert error is None

    backup_files = list(backups_dir.glob("clipforge_data_*.db"))
    assert len(backup_files) == 1

    # השחזור האמיתי - פותחים את קובץ ה*גיבוי* עצמו (לא את המקור) ומוודאים
    # שהוא DB תקין (לא קובץ ריק/פגום) עם בדיוק אותם נתונים.
    restored_conn = sqlite3.connect(str(backup_files[0]))
    restored_rows = restored_conn.execute("SELECT script_name, status FROM job_history ORDER BY id").fetchall()
    restored_conn.close()

    assert restored_rows == rows


def test_backup_database_restored_copy_is_independent_of_original(tmp_path, monkeypatch):
    # שינוי במקור *אחרי* הגיבוי לא אמור להשפיע על הקובץ המגובה כבר - אחרת
    # זה לא באמת "גיבוי" (עותק עצמאי) אלא רק הפניה/קישור למקור.
    db_path = tmp_path / "clipforge_data.db"
    backups_dir = tmp_path / "backups"
    monkeypatch.setattr(scheduler_cog, "DB_PATH", str(db_path))
    monkeypatch.setattr(scheduler_cog, "BACKUPS_DIR", str(backups_dir))

    _make_real_sqlite_db(db_path, [("story_cutter.py", "success")])
    ok, _error = scheduler_cog._backup_database()
    assert ok is True
    backup_path = list(backups_dir.glob("clipforge_data_*.db"))[0]

    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO job_history (script_name, status) VALUES ('added_after_backup.py', 'success')")
    conn.commit()
    conn.close()

    restored_conn = sqlite3.connect(str(backup_path))
    restored_rows = restored_conn.execute("SELECT script_name FROM job_history").fetchall()
    restored_conn.close()

    assert restored_rows == [("story_cutter.py",)]


def test_backup_database_missing_source_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_cog, "DB_PATH", str(tmp_path / "does_not_exist.db"))
    monkeypatch.setattr(scheduler_cog, "BACKUPS_DIR", str(tmp_path / "backups"))

    ok, error = scheduler_cog._backup_database()
    assert ok is True
    assert error is None
    assert not os.path.isdir(str(tmp_path / "backups")), "אין סיבה ליצור תיקיית גיבויים כשאין בכלל DB לגבות"


def test_backup_database_retention_trims_old_backups(tmp_path, monkeypatch):
    db_path = tmp_path / "clipforge_data.db"
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()
    monkeypatch.setattr(scheduler_cog, "DB_PATH", str(db_path))
    monkeypatch.setattr(scheduler_cog, "BACKUPS_DIR", str(backups_dir))
    _make_real_sqlite_db(db_path, [("x.py", "success")])

    for i in range(scheduler_cog.DB_BACKUPS_TO_KEEP + 2):
        (backups_dir / f"clipforge_data_2020-01-{i + 1:02d}.db").write_bytes(b"fake old backup")

    ok, _error = scheduler_cog._backup_database()
    assert ok is True
    remaining = sorted(backups_dir.glob("clipforge_data_*.db"))
    assert len(remaining) == scheduler_cog.DB_BACKUPS_TO_KEEP
