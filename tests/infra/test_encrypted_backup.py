# tests/infra/test_encrypted_backup.py
import io
import json
import os
import sqlite3
import zipfile


import pytest

from utils.shared import encrypted_backup


def _make_fake_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.json").write_text(json.dumps({"theme": "Green"}), encoding="utf-8")
    (data_dir / "rocket_settings.json").write_text(json.dumps({"counter": 5}), encoding="utf-8")
    (data_dir / "logs").mkdir()
    (data_dir / "logs" / "app.log").write_text("should not be backed up", encoding="utf-8")
    (data_dir / "backups").mkdir()
    (data_dir / "backups" / "old_snapshot.zip").write_bytes(b"should not be backed up either")
    (data_dir / "render.lock").write_text("1234", encoding="utf-8")

    db_path = data_dir / "clipforge_data.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO jobs (name) VALUES ('render1')")
    conn.commit()
    conn.close()
    return data_dir


def test_create_backup_bundle_requires_a_passphrase(tmp_path):
    data_dir = _make_fake_data_dir(tmp_path)
    with pytest.raises(encrypted_backup.BackupError):
        encrypted_backup.create_backup_bundle("", str(tmp_path / "out.ibkp"), data_dir=str(data_dir))


def test_create_backup_bundle_includes_config_settings_and_db_but_not_excluded(tmp_path):
    data_dir = _make_fake_data_dir(tmp_path)
    output_path = tmp_path / "out.ibkp"

    result = encrypted_backup.create_backup_bundle("hunter2", str(output_path), data_dir=str(data_dir))

    assert output_path.exists()
    assert "config.json" in result["included_files"]
    assert "rocket_settings.json" in result["included_files"]
    assert "clipforge_data.db" in result["included_files"]
    assert "render.lock" not in result["included_files"]
    assert not any(f.startswith("logs") for f in result["included_files"])
    assert not any(f.startswith("backups") for f in result["included_files"])
    assert result["size_bytes"] == output_path.stat().st_size


def test_round_trip_restores_exact_config_and_db_contents(tmp_path):
    data_dir = _make_fake_data_dir(tmp_path)
    output_path = tmp_path / "out.ibkp"
    encrypted_backup.create_backup_bundle("correct-horse-battery-staple", str(output_path), data_dir=str(data_dir))

    restore_dir = tmp_path / "restored"
    result = encrypted_backup.restore_backup_bundle(
        "correct-horse-battery-staple", str(output_path), data_dir=str(restore_dir)
    )

    assert "config.json" in result["restored_files"]
    assert "clipforge_data.db" in result["restored_files"]
    restored_config = json.loads((restore_dir / "config.json").read_text(encoding="utf-8"))
    assert restored_config == {"theme": "Green"}

    conn = sqlite3.connect(str(restore_dir / "clipforge_data.db"))
    rows = conn.execute("SELECT name FROM jobs").fetchall()
    conn.close()
    assert rows == [("render1",)]


def test_restore_backs_up_existing_file_before_overwriting(tmp_path):
    data_dir = _make_fake_data_dir(tmp_path)
    output_path = tmp_path / "out.ibkp"
    encrypted_backup.create_backup_bundle("pw", str(output_path), data_dir=str(data_dir))

    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()
    (restore_dir / "config.json").write_text(json.dumps({"theme": "Pink"}), encoding="utf-8")

    encrypted_backup.restore_backup_bundle("pw", str(output_path), data_dir=str(restore_dir))

    backup_of_old = json.loads((restore_dir / "config.json.bak").read_text(encoding="utf-8"))
    assert backup_of_old == {"theme": "Pink"}
    new_config = json.loads((restore_dir / "config.json").read_text(encoding="utf-8"))
    assert new_config == {"theme": "Green"}


def test_restore_with_wrong_passphrase_raises_clear_error(tmp_path):
    data_dir = _make_fake_data_dir(tmp_path)
    output_path = tmp_path / "out.ibkp"
    encrypted_backup.create_backup_bundle("right-password", str(output_path), data_dir=str(data_dir))

    with pytest.raises(encrypted_backup.BackupError):
        encrypted_backup.restore_backup_bundle("wrong-password", str(output_path), data_dir=str(tmp_path / "restored"))


def test_restore_with_corrupt_file_raises_clear_error(tmp_path):
    bad_path = tmp_path / "corrupt.ibkp"
    bad_path.write_bytes(b"not a real backup file")

    with pytest.raises(encrypted_backup.BackupError):
        encrypted_backup.restore_backup_bundle("any-password", str(bad_path), data_dir=str(tmp_path / "restored"))


def test_restore_rejects_zip_slip_path_traversal(tmp_path):
    # מדמה ארכיון-גיבוי זדוני/פגום עם ערך בתוך ה-zip שמנסה "לברוח" מ-data_dir
    # (../../evil.txt) - restore_backup_bundle צריך לזרוק BackupError ולא לכתוב
    # שום קובץ מחוץ ל-data_dir שהתבקש.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("../../evil.txt", "pwned")
    salt = os.urandom(encrypted_backup.SALT_SIZE)
    key = encrypted_backup._derive_key("pw", salt)
    from cryptography.fernet import Fernet
    token = Fernet(key).encrypt(buffer.getvalue())

    malicious_path = tmp_path / "malicious.ibkp"
    malicious_path.write_bytes(salt + token)

    restore_dir = tmp_path / "restored"
    outside_marker = tmp_path / "evil.txt"
    with pytest.raises(encrypted_backup.BackupError):
        encrypted_backup.restore_backup_bundle("pw", str(malicious_path), data_dir=str(restore_dir))
    assert not outside_marker.exists()


def test_create_backup_bundle_works_when_db_does_not_exist_yet(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.json").write_text("{}", encoding="utf-8")
    output_path = tmp_path / "out.ibkp"

    result = encrypted_backup.create_backup_bundle("pw", str(output_path), data_dir=str(data_dir))

    assert "clipforge_data.db" not in result["included_files"]
    assert "config.json" in result["included_files"]
