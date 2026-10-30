# tests/bot/test_scheduler_data_backup.py
#
# בודק _backup_data_directory() (גיבוי zip של כל data/, לא רק ה-DB) בבידוד -
# על ידי monkeypatch של DATA_DIR/BACKUPS_DIR למודול ל-תיקיית tmp_path, כדי
# שהטסט לא נוגע בפועל בתיקיית data/ האמיתית של הפרויקט.
import os
import zipfile


from cogs import scheduler_cog


def _setup_fake_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    backups_dir = data_dir / "backups"
    logs_dir = data_dir / "logs"
    data_dir.mkdir()
    backups_dir.mkdir()
    logs_dir.mkdir()

    (data_dir / "config.json").write_text("{}", encoding="utf-8")
    (data_dir / "rocket_settings.json").write_text("{}", encoding="utf-8")
    (data_dir / "clipforge_data.db").write_text("fake db bytes", encoding="utf-8")
    (data_dir / "render.lock").write_text("{}", encoding="utf-8")
    (logs_dir / "bot.log").write_text("log line", encoding="utf-8")

    monkeypatch.setattr(scheduler_cog, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(scheduler_cog, "BACKUPS_DIR", str(backups_dir))
    return data_dir, backups_dir


def test_backup_data_directory_creates_zip_excluding_db_lock_and_subdirs(tmp_path, monkeypatch):
    _data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)

    ok, error = scheduler_cog._backup_data_directory()
    assert ok is True
    assert error is None

    zips = list(backups_dir.glob("data_snapshot_*.zip"))
    assert len(zips) == 1

    with zipfile.ZipFile(zips[0]) as zf:
        names = set(zf.namelist())
    assert "config.json" in names
    assert "rocket_settings.json" in names
    assert "clipforge_data.db" not in names
    assert "render.lock" not in names
    assert not any(n.startswith("backups" + os.sep) or n.startswith("logs" + os.sep) for n in names)


def test_backup_data_directory_restored_contents_match_source_bytes_exactly(tmp_path, monkeypatch):
    # item 27: הטסט למעלה בודק רק שהקבצים *קיימים* ברשימת הקבצים של ה-zip -
    # לא מוודא שאפשר לחלץ אותם בפועל ושהתוכן שלהם זהה ביט-לביט למקור. zip
    # שנוצר עם קידוד/דחיסה שגויים היה יכול לעבור את הטסט הקודם ועדיין להיות
    # חסר ערך לשחזור אמיתי.
    data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)

    ok, _error = scheduler_cog._backup_data_directory()
    assert ok is True

    zips = list(backups_dir.glob("data_snapshot_*.zip"))
    with zipfile.ZipFile(zips[0]) as zf:
        extracted_config = zf.read("config.json")
        extracted_rocket_settings = zf.read("rocket_settings.json")

    assert extracted_config == (data_dir / "config.json").read_bytes()
    assert extracted_rocket_settings == (data_dir / "rocket_settings.json").read_bytes()


def test_backup_data_directory_missing_dir_is_ok(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(scheduler_cog, "DATA_DIR", str(missing_dir))
    monkeypatch.setattr(scheduler_cog, "BACKUPS_DIR", str(tmp_path / "backups"))

    ok, error = scheduler_cog._backup_data_directory()
    assert ok is True
    assert error is None


def test_backup_data_directory_retention_trims_old_snapshots(tmp_path, monkeypatch):
    _data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)

    # יוצרים יותר snapshots "ישנים" מדומים מ-DATA_SNAPSHOTS_TO_KEEP, ואז מריצים
    # גיבוי חדש - אמורים להישאר בדיוק DATA_SNAPSHOTS_TO_KEEP הכי חדשים.
    for i in range(scheduler_cog.DATA_SNAPSHOTS_TO_KEEP + 2):
        (backups_dir / f"data_snapshot_2020-01-{i + 1:02d}.zip").write_bytes(b"fake")

    ok, _error = scheduler_cog._backup_data_directory()
    assert ok is True
    remaining = sorted(backups_dir.glob("data_snapshot_*.zip"))
    assert len(remaining) == scheduler_cog.DATA_SNAPSHOTS_TO_KEEP
