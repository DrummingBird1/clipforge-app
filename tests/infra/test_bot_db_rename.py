# tests/infra/test_bot_db_rename.py
#
# 30.10.2026: ה-DB עבר לשם clipforge_data.db. ‏data_paths.migrate_bot_db() מעביר את הקובץ הישן פעם אחת - גיבוי, ואז rename -
# ועד שזה מצליח path(BOT_DB) ממשיך לקרוא את הישן. השם הישן לא כתוב בריפו (רק ה-hash שלו), אז כאן "oldbot_data.db" מחליף אותו.
import hashlib
import os
import sqlite3
import sys

import pytest

from utils.shared import data_paths, db

OLD = "oldbot_data.db"


@pytest.fixture(autouse=True)
def _fake_old_name(monkeypatch):
    monkeypatch.setattr(data_paths, "LEGACY_BOT_DB_SHA256", hashlib.sha256(OLD.encode("utf-8")).digest())


def _make_db(path, rows=3):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)   # לא db.connect: הוא מפנה שם ישן שלא קיים לשם החדש
    conn.execute("PRAGMA journal_mode=WAL")   # כמו ה-DB האמיתי
    with conn:
        conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT)")
        conn.executemany("INSERT INTO jobs (name) VALUES (?)", [(f"job{i}",) for i in range(rows)])
    conn.close()


def _rows(path):
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    finally:
        conn.close()


def test_the_old_db_is_backed_up_then_renamed(tmp_path):
    data = tmp_path / "data"
    _make_db(str(data / OLD))
    assert data_paths.path(data_paths.BOT_DB, str(data)) == str(data / OLD)   # לפני ההעברה - הקובץ הישן

    moved = data_paths.migrate_bot_db(str(data))

    assert moved == str(data / "clipforge_data.db")
    assert not (data / OLD).exists() and not (data / (OLD + "-wal")).exists()
    assert _rows(moved) == 3
    assert _rows(str(data.joinpath(*data_paths.DB_RENAME_BACKUP.split("/")))) == 3
    assert data_paths.path(data_paths.BOT_DB, str(data)) == moved
    assert data_paths.migrate_bot_db(str(data)) is None   # פעם אחת


def test_after_the_layout_migration_the_old_db_moves_into_the_bot_folder(tmp_path):
    data = tmp_path / "data"
    _make_db(str(data / OLD))
    (data / data_paths.LAYOUT_MARKER).write_text("1", encoding="utf-8")

    assert data_paths.migrate_bot_db(str(data)) == str(data / "bot" / "clipforge_data.db")
    assert _rows(str(data / "bot" / "clipforge_data.db")) == 3


def test_when_the_new_db_already_exists_the_old_file_is_left_alone(tmp_path):
    data = tmp_path / "data"
    _make_db(str(data / OLD), rows=1)
    _make_db(str(data / "clipforge_data.db"), rows=5)

    assert data_paths.migrate_bot_db(str(data)) is None
    assert _rows(str(data / OLD)) == 1 and data_paths.path(data_paths.BOT_DB, str(data)) == str(data / "clipforge_data.db")


@pytest.mark.skipif(sys.platform != "win32", reason="ב-Windows קובץ פתוח לא זז - זה מה שמגן על תהליך אחר שעובד עליו")
def test_while_another_process_has_the_old_db_open_nothing_moves(tmp_path):
    data = tmp_path / "data"
    _make_db(str(data / OLD))
    other = sqlite3.connect(str(data / OLD))
    other.execute("SELECT COUNT(*) FROM jobs").fetchone()
    try:
        assert data_paths.migrate_bot_db(str(data)) is None
        assert (data / OLD).exists() and not (data / "clipforge_data.db").exists()
        assert data_paths.path(data_paths.BOT_DB, str(data)) == str(data / OLD)
    finally:
        other.close()
    assert data_paths.migrate_bot_db(str(data)) == str(data / "clipforge_data.db")   # בהפעלה הבאה


def test_a_path_computed_before_the_rename_opens_the_new_db_instead_of_an_empty_old_one(tmp_path, monkeypatch):
    data = tmp_path / "data"
    _make_db(str(data / OLD))
    monkeypatch.setattr(data_paths, "DATA_DIR", str(data))
    stale = data_paths.path(data_paths.BOT_DB)
    data_paths.migrate_bot_db()

    conn = db.connect(stale)
    try:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 3
    finally:
        conn.close()
    assert not (data / OLD).exists()


def test_an_old_backup_restores_under_the_new_name(tmp_path):
    flat, moved = tmp_path / "flat", tmp_path / "moved"
    flat.mkdir()
    moved.mkdir()
    (moved / data_paths.LAYOUT_MARKER).write_text("1", encoding="utf-8")
    assert data_paths.localize(OLD, str(flat)) == "clipforge_data.db"
    assert data_paths.localize("bot/" + OLD, str(flat)) == "clipforge_data.db"
    assert data_paths.localize(OLD, str(moved)) == "bot/clipforge_data.db"


def test_the_old_name_is_only_a_hash_and_the_new_name_is_not_it(monkeypatch):
    monkeypatch.undo()
    assert len(data_paths.LEGACY_BOT_DB_SHA256) == 32 and not data_paths.is_legacy_bot_db(data_paths.BOT_DB)
