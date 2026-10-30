# tests/infra/test_job_history.py


from utils.shared import job_history


def test_get_recently_run_script_names_deduplicates_and_orders_by_recency(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))

    job_history.record_job("a.py", "success", "t1", "t2", 1.0)
    job_history.record_job("b.py", "success", "t1", "t2", 1.0)
    job_history.record_job("a.py", "success", "t1", "t2", 1.0)  # a.py runs again, most recent now
    job_history.record_job("c.py", "failed", "t1", "t2", 1.0)

    names = job_history.get_recently_run_script_names(limit=5)

    assert names == ["c.py", "a.py", "b.py"]  # most-recent-first, no duplicate a.py


def test_get_recently_run_script_names_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    for name in ["a.py", "b.py", "c.py", "d.py"]:
        job_history.record_job(name, "success", "t1", "t2", 1.0)

    assert job_history.get_recently_run_script_names(limit=2) == ["d.py", "c.py"]


def test_get_recently_run_script_names_empty_history(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    assert job_history.get_recently_run_script_names() == []


def test_format_result_summary_from_dict():
    assert job_history.format_result_summary({"files": 3, "errors": 0}) == "files: 3 | errors: 0"


def test_format_result_summary_from_json_string():
    assert job_history.format_result_summary('{"files": 3}') == "files: 3"


def test_format_result_summary_none_or_empty():
    assert job_history.format_result_summary(None) == ""
    assert job_history.format_result_summary("") == ""
    assert job_history.format_result_summary("not json") == ""


def test_record_and_retrieve_job_with_result(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("disk_scanner.py", "success", "t1", "t2", 42.0, result={"files_scanned": 10})

    rows = job_history.get_recent_jobs(limit=1)
    script_name, status, started_at, duration_seconds, result_json = rows[0]
    assert script_name == "disk_scanner.py"
    assert status == "success"
    assert duration_seconds == 42.0
    assert job_history.format_result_summary(result_json) == "files_scanned: 10"


def test_get_average_render_durations_averages_successful_runs_only(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0)
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0)
    job_history.record_job("video_editor.py", "failed", "t1", "t2", 1.0)  # excluded from average
    job_history.record_job("timelapse_maker.py", "success", "t1", "t2", 100.0)

    averages = job_history.get_average_render_durations()

    by_script = {name: (avg, count) for name, avg, count in averages}
    assert by_script["video_editor.py"] == (15.0, 2)
    assert by_script["timelapse_maker.py"] == (100.0, 1)


def test_get_average_render_durations_empty_history(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    assert job_history.get_average_render_durations() == []


# --- search_jobs (item: global search) ---

def test_search_jobs_matches_script_name(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0)
    job_history.record_job("disk_scanner.py", "success", "t1", "t2", 1.0)

    rows = job_history.search_jobs("video_editor")

    assert len(rows) == 1
    assert rows[0][0] == "video_editor.py"


def test_search_jobs_matches_status(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("a.py", "success", "t1", "t2", 1.0)
    job_history.record_job("b.py", "failed", "t1", "t2", 1.0)

    rows = job_history.search_jobs("failed")

    assert len(rows) == 1
    assert rows[0][0] == "b.py"


def test_search_jobs_matches_result_json_content(tmp_path, monkeypatch):
    # זה בדיוק המקרה שהפיצ'ר נועד לו - למצוא "איפה עיבדתי clip_42.mp4" בלי
    # לזכור באיזה סקריפט/מתי זה קרה.
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0, result={"file": "clip_42.mp4"})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0, result={"file": "clip_99.mp4"})

    rows = job_history.search_jobs("clip_42")

    assert len(rows) == 1
    assert job_history.format_result_summary(rows[0][4]) == "file: clip_42.mp4"


def test_search_jobs_is_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("Video_Editor.py", "success", "t1", "t2", 1.0)

    assert len(job_history.search_jobs("video_editor")) == 1


def test_search_jobs_matches_started_at_date(tmp_path, monkeypatch):
    # item: חיפוש בהיסטוריית עבודות גם לפי תאריך - לא רק script_name/status/
    # result_json. started_at הוא ISO, אז חיפוש-תת-מחרוזת על תאריך עובד ישר
    # בלי לפרש/לפרסר תאריך בעצמנו.
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("a.py", "success", "2026-09-18T14:30:00", "2026-09-18T14:31:00", 1.0)
    job_history.record_job("b.py", "success", "2026-01-01T09:00:00", "2026-01-01T09:01:00", 1.0)

    rows = job_history.search_jobs("2026-09-18")

    assert len(rows) == 1
    assert rows[0][0] == "a.py"


def test_search_jobs_matches_partial_date(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("a.py", "success", "2026-09-18T14:30:00", "2026-09-18T14:31:00", 1.0)
    job_history.record_job("b.py", "success", "2026-01-01T09:00:00", "2026-01-01T09:01:00", 1.0)

    rows = job_history.search_jobs("09-18")

    assert len(rows) == 1
    assert rows[0][0] == "a.py"


def test_search_jobs_no_match_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("a.py", "success", "t1", "t2", 1.0)

    assert job_history.search_jobs("nonexistent_xyz") == []


def test_search_jobs_orders_most_recent_first(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("script.py", "success", "t1", "t2", 1.0, result={"n": 1})
    job_history.record_job("script.py", "success", "t1", "t2", 1.0, result={"n": 2})

    rows = job_history.search_jobs("script")

    assert job_history.format_result_summary(rows[0][4]) == "n: 2"  # האחרון שנרשם קודם


# --- get_hwaccel_time_comparison (item: "time saved with --hwaccel" metric) ---

def test_get_hwaccel_time_comparison_computes_seconds_per_file(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    # עם --hwaccel: 10 שניות ל-5 קבצים = 2s/קובץ, פעמיים
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    # בלי --hwaccel: 20 שניות ל-5 קבצים = 4s/קובץ
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "hwaccel": False})

    comparison = job_history.get_hwaccel_time_comparison()

    assert comparison["hwaccel_avg_seconds_per_file"] == 2.0
    assert comparison["hwaccel_run_count"] == 2
    assert comparison["no_hwaccel_avg_seconds_per_file"] == 4.0
    assert comparison["no_hwaccel_run_count"] == 1
    assert comparison["percent_faster"] == 50.0


def test_get_hwaccel_time_comparison_none_when_missing_a_group(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})

    assert job_history.get_hwaccel_time_comparison() is None


def test_get_hwaccel_time_comparison_none_when_no_runs_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    assert job_history.get_hwaccel_time_comparison() is None


def test_get_hwaccel_time_comparison_skips_runs_without_hwaccel_field(tmp_path, monkeypatch):
    # ריצות מלפני שהפיצ'ר הזה נוסף - result_json בלי "hwaccel" בכלל
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "hwaccel": False})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 999.0, result={"files_created": 5})  # ישן, בלי hwaccel

    comparison = job_history.get_hwaccel_time_comparison()

    assert comparison["hwaccel_run_count"] == 1
    assert comparison["no_hwaccel_run_count"] == 1


def test_get_hwaccel_time_comparison_skips_zero_files_created(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "hwaccel": False})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 5.0, result={"files_created": 0, "hwaccel": True})  # כל הקבצים דולגו (smart skip)

    comparison = job_history.get_hwaccel_time_comparison()

    assert comparison["hwaccel_run_count"] == 1  # רק הריצה עם files_created>0


def test_get_hwaccel_time_comparison_ignores_failed_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "hwaccel": False})
    job_history.record_job("video_editor.py", "failed", "t1", "t2", 1.0, result={"files_created": 100, "hwaccel": True})

    comparison = job_history.get_hwaccel_time_comparison()

    assert comparison["hwaccel_run_count"] == 1


def test_get_hwaccel_time_comparison_scoped_to_script_name(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "hwaccel": False})
    job_history.record_job("other_script.py", "success", "t1", "t2", 1.0, result={"files_created": 5, "hwaccel": True})

    comparison = job_history.get_hwaccel_time_comparison(script_name="video_editor.py")

    assert comparison["hwaccel_run_count"] == 1


# --- get_video_editor_eta_estimate (item: הערכת זמן-ריצה משוער) ---

def test_get_video_editor_eta_estimate_computes_seconds_per_file(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "codec": "h264", "hwaccel": False})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 20.0, result={"files_created": 5, "codec": "h264", "hwaccel": False})

    estimate = job_history.get_video_editor_eta_estimate("h264", False)

    assert estimate["avg_seconds_per_file"] == 3.0
    assert estimate["run_count"] == 2


def test_get_video_editor_eta_estimate_scoped_to_exact_codec_and_hwaccel_combo(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 2.0, result={"files_created": 1, "codec": "h264", "hwaccel": False})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 100.0, result={"files_created": 1, "codec": "hevc", "hwaccel": True})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 100.0, result={"files_created": 1, "codec": "h264", "hwaccel": True})

    estimate = job_history.get_video_editor_eta_estimate("h264", False)

    assert estimate["run_count"] == 1
    assert estimate["avg_seconds_per_file"] == 2.0


def test_get_video_editor_eta_estimate_none_when_no_matching_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "codec": "h264", "hwaccel": False})

    assert job_history.get_video_editor_eta_estimate("av1", True) is None


def test_get_video_editor_eta_estimate_none_when_no_runs_at_all(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    assert job_history.get_video_editor_eta_estimate("h264", False) is None


def test_get_video_editor_eta_estimate_ignores_failed_and_zero_file_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "codec": "h264", "hwaccel": False})
    job_history.record_job("video_editor.py", "failed", "t1", "t2", 1.0, result={"files_created": 5, "codec": "h264", "hwaccel": False})
    job_history.record_job("video_editor.py", "success", "t1", "t2", 5.0, result={"files_created": 0, "codec": "h264", "hwaccel": False})

    estimate = job_history.get_video_editor_eta_estimate("h264", False)

    assert estimate["run_count"] == 1


def test_search_jobs_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    for _ in range(5):
        job_history.record_job("script.py", "success", "t1", "t2", 1.0)

    assert len(job_history.search_jobs("script", limit=2)) == 2


def test_typical_duration_is_the_median_of_recent_successes(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "t.db"))
    assert job_history.get_typical_duration("a.py") is None
    for status, dur in (("success", 10), ("failed", 999), ("success", 30), ("success", 20), ("success", 1000)):
        job_history.record_job("a.py", status, "2026-01-01T00:00:00", "2026-01-01T00:00:10", dur)
    job_history.record_job("b.py", "success", "2026-01-01T00:00:00", "2026-01-01T00:00:10", 5)
    assert job_history.get_typical_duration("a.py") == 25          # חציון של 10,30,20,1000 (הכושל מתעלמים)
    assert job_history.get_typical_duration("b.py") == 5


def test_estimate_remaining_blends_history_and_progress():
    est = job_history.estimate_remaining_seconds
    assert est(5, 100, 50) == 0
    assert est(1, 0, None) is None and est(1, 0, 60) == 59                      # בלי התקדמות: ההיסטוריה בלבד
    assert est(100, 50, None) == 100                                            # התקדמות בלבד: לינארי
    assert est(60, 50, 1000) == 60                                              # התקדמות 50%+: מסתמכים על האקסטרפולציה
    assert est(10, 10, 100) == int(0.2 * 90 + 0.8 * 90)                         # 10%: מעורבב (כאן שניהם 90)
    assert est(500, 10, 100) < 4500 and est(500, 10, 100) > 0
    assert est(10, 5, 5) is not None and est(10, 5, 5) >= 0