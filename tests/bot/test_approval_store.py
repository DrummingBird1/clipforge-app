# tests/bot/test_approval_store.py
#
# בודק utils/bot/approval_store.py (item: mobile-friendly clip-approval view) -
# הגישה הסינכרונית (sqlite3) לטבלת pending_approvals, מקבילה ל-cogs/
# approval_cog.py's גרסתה האסינכרונית (aiosqlite) - נבדקת בנפרד ב-
# test_approval_cog.py. DB_PATH/CLIPS_REVIEW_DIR/REJECTED_DIR/get_rocket_input_dir
# כולם ממופתחים ל-tmp_path בכל טסט.
import os


import utils.bot.approval_store as approval_store
from utils.shared import db
from utils.bot.approval_store import get_pending_approvals, resolve_pending, validate_pending_video_path


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_store, "DB_PATH", str(tmp_path / "test.db"))
    clips_dir = tmp_path / "clips"
    monkeypatch.setattr(approval_store, "CLIPS_REVIEW_DIR", str(clips_dir))
    monkeypatch.setattr(approval_store, "REJECTED_DIR", str(tmp_path / "rejected"))
    monkeypatch.setattr(approval_store, "get_rocket_input_dir", lambda: str(tmp_path / "rocket_input"))
    return clips_dir


def _insert_pending(db_path, video_path):
    with db.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pending_approvals ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, video_path TEXT UNIQUE, "
            "status TEXT DEFAULT 'pending', channel_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor = conn.execute(
            "INSERT INTO pending_approvals (video_path, status, channel_id) VALUES (?, 'pending', ?)",
            (video_path, 123),
        )
    return cursor.lastrowid


def test_get_pending_approvals_empty_when_nothing_pending(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    assert get_pending_approvals() == []


def test_get_pending_approvals_returns_only_pending_rows_oldest_first(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    id_a = _insert_pending(approval_store.DB_PATH, "/clips/a.mp4")
    id_b = _insert_pending(approval_store.DB_PATH, "/clips/b.mp4")
    with db.connect(approval_store.DB_PATH) as conn:
        conn.execute("UPDATE pending_approvals SET status = 'approved' WHERE id = ?", (id_b,))

    rows = get_pending_approvals()

    assert [r[0] for r in rows] == [id_a]


def test_validate_pending_video_path_accepts_file_inside_review_dir(tmp_path, monkeypatch):
    clips_dir = _setup(tmp_path, monkeypatch)
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")

    assert validate_pending_video_path(str(clip)) == os.path.realpath(str(clip))


def test_validate_pending_video_path_rejects_path_outside_review_dir(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"fake")

    assert validate_pending_video_path(str(outside_file)) is None


def test_validate_pending_video_path_rejects_missing_file(tmp_path, monkeypatch):
    clips_dir = _setup(tmp_path, monkeypatch)
    clips_dir.mkdir()

    assert validate_pending_video_path(str(clips_dir / "nonexistent.mp4")) is None


def test_validate_pending_video_path_rejects_empty_path(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    assert validate_pending_video_path("") is None


def test_resolve_pending_approved_moves_file_to_rocket_input_dir(tmp_path, monkeypatch):
    clips_dir = _setup(tmp_path, monkeypatch)
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    pending_id = _insert_pending(approval_store.DB_PATH, str(clip))

    resolve_pending(pending_id, str(clip), approved=True)

    assert not clip.exists()
    assert (tmp_path / "rocket_input" / "clip.mp4").exists()
    with db.connect(approval_store.DB_PATH) as conn:
        status, resolved_at = conn.execute(
            "SELECT status, resolved_at FROM pending_approvals WHERE id = ?", (pending_id,)
        ).fetchone()
    assert status == "approved"
    assert resolved_at is not None


def test_resolve_pending_rejected_moves_file_to_rejected_dir(tmp_path, monkeypatch):
    clips_dir = _setup(tmp_path, monkeypatch)
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    pending_id = _insert_pending(approval_store.DB_PATH, str(clip))

    resolve_pending(pending_id, str(clip), approved=False)

    assert not clip.exists()
    assert (tmp_path / "rejected" / "clip.mp4").exists()
    with db.connect(approval_store.DB_PATH) as conn:
        (status,) = conn.execute(
            "SELECT status FROM pending_approvals WHERE id = ?", (pending_id,)
        ).fetchone()
    assert status == "rejected"


def test_resolve_pending_updates_db_even_if_file_already_gone(tmp_path, monkeypatch):
    clips_dir = _setup(tmp_path, monkeypatch)
    clips_dir.mkdir()
    clip_path = str(clips_dir / "already_moved.mp4")
    pending_id = _insert_pending(approval_store.DB_PATH, clip_path)

    resolve_pending(pending_id, clip_path, approved=True)

    with db.connect(approval_store.DB_PATH) as conn:
        (status,) = conn.execute(
            "SELECT status FROM pending_approvals WHERE id = ?", (pending_id,)
        ).fetchone()
    assert status == "approved"


def test_ensure_table_migration_is_idempotent(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    with db.connect(approval_store.DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_path TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                channel_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    approval_store._ensure_table()
    approval_store._ensure_table()

    with db.connect(approval_store.DB_PATH) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pending_approvals)").fetchall()}
    assert "resolved_at" in columns


def test_get_rocket_input_dir_reads_from_settings_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "data" / "rocket_settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text('{"input_dir": "E:/somewhere"}', encoding="utf-8")
    monkeypatch.setattr(approval_store, "DATA_DIR", str(settings_path.parent))

    assert approval_store.get_rocket_input_dir() == "E:/somewhere"


def test_get_rocket_input_dir_falls_back_to_base_dir_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(approval_store, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(approval_store, "BASE_DIR", str(tmp_path))

    assert approval_store.get_rocket_input_dir() == str(tmp_path)
