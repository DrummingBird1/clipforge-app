# tests/gui/test_stats_tab_undo.py
#
# בודק את כפתור "בטל פעולה אחרונה" ב-ui/stats_tab.py (item: undo last file-move
# operation) - קבצים אמיתיים על דיסק (tmp_path), לא מוקים, כי move_undo_log
# עצמו כבר נבדק ביסודיות ב-test_move_undo_log.py; זה בודק את חוט ה-UI סביבו
# (הכפתור מוצג/מוסתר נכון, הלחיצה בפועל מזיזה קבצים בחזרה).


from utils.shared import hardware_history, job_history, move_undo_log
from ui.stats_tab import StatsTabComponent


def test_undo_button_hidden_when_no_pending_batch(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert comp.undo_btn.winfo_manager() == ""
    finally:
        comp.destroy()


def test_undo_button_shown_when_batch_pending(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": "a", "dst": "b"}])

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert comp.undo_btn.winfo_manager() == "pack"
    finally:
        comp.destroy()


def test_clicking_undo_restores_files_and_hides_button(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))

    src = tmp_path / "source" / "clip.mp4"
    dst = tmp_path / "archive" / "clip.mp4"
    src.parent.mkdir()
    dst.parent.mkdir()
    dst.write_bytes(b"archived content")
    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert comp.undo_btn.winfo_manager() == "pack"
        comp._on_undo_last_move_batch()

        assert src.exists()
        assert src.read_bytes() == b"archived content"
        assert not dst.exists()
        assert comp.undo_btn.winfo_manager() == ""  # אין עוד batch ממתין - הכפתור נעלם
        assert move_undo_log.get_last_move_batch() is None
    finally:
        comp.destroy()


def test_refresh_job_history_updates_undo_button_visibility(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert comp.undo_btn.winfo_manager() == ""

        move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": "a", "dst": "b"}])
        comp.refresh_job_history()
        assert comp.undo_btn.winfo_manager() == "pack"
    finally:
        comp.destroy()
