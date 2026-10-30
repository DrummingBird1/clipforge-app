# tests/infra/test_move_undo_log.py
#
# בודק utils/shared/move_undo_log.py (item: undo last file-move operation) - כל
# הטסטים משתמשים בקבצים אמיתיים על דיסק (tmp_path), לא מוקים, כי הפעולה
# עצמה (shutil.move) היא בדיוק מה שנבדק.


from utils.shared import move_undo_log


def test_record_move_batch_writes_a_file(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))

    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": "a", "dst": "b"}])

    assert log_path.exists()
    batch = move_undo_log.get_last_move_batch()
    assert batch["script_name"] == "cleanup_published_sources.py"
    assert batch["moves"] == [{"src": "a", "dst": "b"}]


def test_record_move_batch_with_no_moves_does_not_write(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))

    move_undo_log.record_move_batch("cleanup_published_sources.py", [])

    assert not log_path.exists()


def test_get_last_move_batch_returns_none_when_no_log(tmp_path, monkeypatch):
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "does_not_exist.json"))
    assert move_undo_log.get_last_move_batch() is None


def test_get_last_move_batch_returns_none_for_corrupt_json(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    log_path.write_text("not valid json{{{", encoding="utf-8")
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))
    assert move_undo_log.get_last_move_batch() is None


def test_undo_restores_moved_files_to_their_original_location(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))

    src = tmp_path / "source" / "clip.mp4"
    dst = tmp_path / "archive" / "clip.mp4"
    src.parent.mkdir()
    dst.parent.mkdir()
    dst.write_bytes(b"real content")

    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])
    result = move_undo_log.undo_last_move_batch()

    assert result["restored"] == [{"src": str(src), "dst": str(dst)}]
    assert result["skipped"] == []
    assert src.exists()
    assert src.read_bytes() == b"real content"
    assert not dst.exists()


def test_undo_clears_the_log_so_it_cannot_run_twice(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))
    src = tmp_path / "clip.mp4"
    dst = tmp_path / "archived_clip.mp4"
    dst.write_bytes(b"x")

    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])
    move_undo_log.undo_last_move_batch()

    second_result = move_undo_log.undo_last_move_batch()
    assert second_result == {"restored": [], "skipped": [], "error": "אין פעולה להחזרה"}


def test_undo_skips_when_destination_no_longer_exists(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))
    src = tmp_path / "clip.mp4"
    dst = tmp_path / "archived_clip.mp4"  # לעולם לא נוצר בפועל - מדמה שהוזז/נמחק ידנית

    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])
    result = move_undo_log.undo_last_move_batch()

    assert result["restored"] == []
    assert len(result["skipped"]) == 1
    assert not src.exists()


def test_undo_skips_when_source_already_occupied(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))
    src = tmp_path / "clip.mp4"
    dst = tmp_path / "archived_clip.mp4"
    src.write_bytes(b"a different file now lives here")
    dst.write_bytes(b"archived content")

    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])
    result = move_undo_log.undo_last_move_batch()

    assert result["restored"] == []
    assert len(result["skipped"]) == 1
    assert src.read_bytes() == b"a different file now lives here"  # לא נדרס
    assert dst.exists()  # לא הוזז


def test_undo_partial_batch_some_restored_some_skipped(tmp_path, monkeypatch):
    log_path = tmp_path / "last_move_batch.json"
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(log_path))

    src1, dst1 = tmp_path / "a.mp4", tmp_path / "archive_a.mp4"
    dst1.write_bytes(b"a")
    src2, dst2 = tmp_path / "b.mp4", tmp_path / "archive_b.mp4"  # dst2 לא נוצר - ידלג

    move_undo_log.record_move_batch("cleanup_published_sources.py", [
        {"src": str(src1), "dst": str(dst1)}, {"src": str(src2), "dst": str(dst2)},
    ])
    result = move_undo_log.undo_last_move_batch()

    assert len(result["restored"]) == 1
    assert len(result["skipped"]) == 1
    assert src1.exists()
    assert not src2.exists()
