# tests/gui/test_stats_tab_search.py
#
# בודק את חיפוש ההיסטוריה (item: global search) שנוסף ל-ui/stats_tab.py -
# _run_history_search() נבדק ישירות (בלי לחכות ל-debounce האמיתי, self.after(250, ...))
# כדי שהטסט יהיה דטרמיניסטי ולא תלוי-תזמון.


from utils.shared import hardware_history, job_history
from utils.shared.i18n import t
from ui.stats_tab import StatsTabComponent


def _row_texts(comp):
    """טקסט כל ה-CTkLabel-ים תחת history_scroll - כדי לבדוק מה בפועל מוצג."""
    texts = []
    for w in comp.history_scroll.winfo_children():
        if hasattr(w, "cget"):
            try:
                texts.append(w.cget("text"))
            except Exception:
                pass
        for child in w.winfo_children():
            try:
                texts.append(child.cget("text"))
            except Exception:
                pass
    return texts


def test_stats_tab_shows_recent_jobs_by_default(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0)

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert any("video_editor.py" in text for text in _row_texts(comp))
    finally:
        comp.destroy()


def test_stats_tab_search_filters_to_matching_jobs(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0, result={"file": "clip_42.mp4"})
    job_history.record_job("disk_scanner.py", "success", "t1", "t2", 1.0)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.history_search_var.set("clip_42")
        comp._run_history_search()

        texts = _row_texts(comp)
        assert any("video_editor.py" in text for text in texts)
        assert not any("disk_scanner.py" in text for text in texts)
    finally:
        comp.destroy()


def test_stats_tab_search_no_match_shows_empty_message(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.history_search_var.set("nonexistent_xyz")
        comp._run_history_search()

        texts = _row_texts(comp)
        assert t("לא נמצאו ריצות תואמות.") in texts
    finally:
        comp.destroy()


def test_stats_tab_clearing_search_reverts_to_recent_jobs(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.history_search_var.set("nonexistent_xyz")
        comp._run_history_search()
        assert not any("video_editor.py" in text for text in _row_texts(comp))

        comp.history_search_var.set("")
        comp._run_history_search()
        assert any("video_editor.py" in text for text in _row_texts(comp))
    finally:
        comp.destroy()


def test_refresh_job_history_clears_search_box(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp.history_search_var.set("something")
        comp.refresh_job_history()
        assert comp.history_search_var.get() == ""
    finally:
        comp.destroy()


# --- hwaccel savings label (item: "time saved with --hwaccel" metric) ---

def test_hwaccel_savings_label_empty_without_enough_history(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert comp.hwaccel_savings_label.cget("text") == ""
    finally:
        comp.destroy()


def test_hwaccel_savings_label_shows_comparison_when_available(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "hwaccel": False})

    comp = StatsTabComponent(shared_tk_root)
    try:
        text = comp.hwaccel_savings_label.cget("text")
        assert text != ""
        assert "hwaccel" in text
    finally:
        comp.destroy()
