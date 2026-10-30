# tests/web/test_web_app_runs.py - REST endpoint tests for web_app.py, topic: runs (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
from unittest.mock import MagicMock
import json
import os
from tests.web_app_support import (  # noqa: F401
    _ImmediateThread,
    _isolate_vep_paths,
    client,
    web_app,
)


def test_api_scripts_returns_known_fields():
    resp = client.get("/api/scripts")
    assert resp.status_code == 200
    scripts = resp.json()
    assert len(scripts) > 0
    first = scripts[0]
    assert set(["id", "name", "description", "concurrency", "safety", "category"]).issubset(first.keys())
    # video_editor.py (נוסף באותה סבב עבודה) אמור להופיע ברשימה
    assert any(s["id"].endswith("video_editor.py") for s in scripts)


def test_api_queue_status_reports_pending_counts_by_lane(monkeypatch):
    monkeypatch.setattr(web_app.worker, "pending_counts_by_lane", lambda: {"heavy": 2, "light": 1})

    resp = client.get("/api/queue_status")

    assert resp.status_code == 200
    assert resp.json() == {"pending": 3, "heavy": 2, "light": 1}


def test_api_queue_status_reports_zero_when_empty(monkeypatch):
    monkeypatch.setattr(web_app.worker, "pending_counts_by_lane", lambda: {"heavy": 0, "light": 0})

    resp = client.get("/api/queue_status")

    assert resp.status_code == 200
    assert resp.json() == {"pending": 0, "heavy": 0, "light": 0}


def test_api_run_records_profile_usage_for_video_editor(tmp_path, monkeypatch):
    vep = _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "UsedProfile", "settings": {"codec": "h264"}})
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: None)

    resp = client.post("/api/run", json={
        "script": "video/video_editor.py", "folder": str(tmp_path),
        "ve_profile_name": "UsedProfile",
    })

    assert resp.status_code == 200
    meta = vep.load_profile_meta("UsedProfile")
    assert meta["run_count"] == 1
    assert meta["last_used_at"] is not None


def test_api_run_without_profile_name_does_not_touch_meta(tmp_path, monkeypatch):
    vep = _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Untouched", "settings": {"codec": "h264"}})
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: None)

    client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)})

    assert vep.load_profile_meta("Untouched")["run_count"] == 0


def test_api_run_rejects_script_outside_my_scripts(tmp_path):
    resp = client.post("/api/run", json={"script": "../../secrets_vault.py", "folder": str(tmp_path)})
    assert resp.status_code == 400


def test_api_run_rejects_missing_folder():
    resp = client.post("/api/run", json={"script": "video/video_editor.py", "folder": "Z:\\nope_not_real"})
    assert resp.status_code == 400


def test_api_run_rejects_when_already_running(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.worker, "is_running", True)
    resp = client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)})
    assert resp.status_code == 409


def test_api_run_success_calls_worker_add_script_task(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.worker, "is_running", False)
    calls = []
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True and resp.json()["run_id"]  # גל 8: מזהה הריצה בהיסטוריית העורך
    assert len(calls) == 1
    script_path_arg = calls[0][0][0]
    assert script_path_arg.endswith("video_editor.py")


def test_api_run_records_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: None)
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)})

    assert resp.status_code == 200
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "web"
    assert args[1] == "run_script"
    assert kwargs["details"] == "video_editor.py"


def test_api_stop_records_audit_log_entry(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/stop")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "stop_script")


def test_api_run_rejects_cross_origin_request(tmp_path, monkeypatch):
    # רגרסיה/CSRF: אתר זדוני בטאב אחר של אותו דפדפן יכול לשלוח fetch(POST) לכאן -
    # ה-Origin שלו לא יתאים ל-127.0.0.1/localhost ולכן חייב להידחות.
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: None)
    resp = client.post(
        "/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)},
        headers={"origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_api_run_allows_matching_same_origin(tmp_path, monkeypatch):
    # TestClient שולח Host: testserver כברירת מחדל - Origin תואם צריך להיות
    # http://testserver, לא כתובת מקובעת (הבדיקה בפועל משווה ל-Host header
    # של הבקשה עצמה, לא לרשימה קבועה של 127.0.0.1/localhost - ראו
    # _is_same_origin, כדי שזה יעבוד נכון גם במצב --lan עם כתובת IP ברשת).
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: None)
    resp = client.post(
        "/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)},
        headers={"origin": "http://testserver"},
    )
    assert resp.status_code == 200


def test_api_run_allows_matching_lan_ip_origin(tmp_path, monkeypatch):
    # מצב --lan: השרת נגיש דרך כתובת IP ברשת (למשל http://192.168.1.50:8878),
    # לא רק loopback - Origin שתואם ל-Host header של הבקשה עצמה חייב לעבור,
    # לא רק 127.0.0.1/localhost קבועים מראש.
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: None)
    resp = client.post(
        "/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)},
        headers={"origin": "http://192.168.1.50:8878", "host": "192.168.1.50:8878"},
    )
    assert resp.status_code == 200


def test_api_stop_rejects_cross_origin_request():
    resp = client.post("/api/stop", headers={"origin": "https://evil.example.com"})
    assert resp.status_code == 403


def test_api_stop_does_not_raise_with_nothing_running():
    resp = client.post("/api/stop")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_api_pause_records_audit_log_entry(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/pause")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "pause_script")


def test_api_resume_records_audit_log_entry(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/resume")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "resume_script")


def test_api_pause_rejects_cross_origin_request():
    resp = client.post("/api/pause", headers={"origin": "https://evil.example.com"})
    assert resp.status_code == 403


def test_api_resume_rejects_cross_origin_request():
    resp = client.post("/api/resume", headers={"origin": "https://evil.example.com"})
    assert resp.status_code == 403


def test_api_pause_and_resume_do_not_raise_with_nothing_running():
    assert client.post("/api/pause").json() == {"ok": True}
    assert client.post("/api/resume").json() == {"ok": True}


def test_api_pause_actually_suspends_a_real_running_subprocess(tmp_path, monkeypatch):
    # שרשרת מלאה, subprocess אמיתי - לא רק "לא קרס", אלא שהתהליך באמת קפוא.
    import time

    import psutil
    import utils.shared.worker as worker_module

    monkeypatch.setattr(worker_module, "_touch_render_lock", lambda: None)
    script_path = tmp_path / "slow_script.py"
    script_path.write_text("import time\nprint('starting', flush=True)\ntime.sleep(3)\n", encoding="utf-8")

    # מריצים ישירות דרך ה-worker (לא /api/run) כדי לא להיות תלויים בכל
    # הלוגיקה הספציפית ל-video_editor.py (watermark/vertical/וכו') - רק
    # בתת-תהליך אמיתי שרץ מספיק זמן כדי שנספיק להשהות אותו.
    web_app.worker.add_script_task(str(script_path), str(tmp_path), lambda outcome: None, concurrency="light")
    deadline = time.time() + 3
    while time.time() < deadline and not web_app.worker.active_processes:
        time.sleep(0.02)
    assert web_app.worker.active_processes, "התהליך המדומה מעולם לא התחיל בפועל"
    pid = list(web_app.worker.active_processes.values())[0].pid
    ps_proc = psutil.Process(pid)

    try:
        resp = client.post("/api/pause")
        assert resp.status_code == 200
        deadline = time.time() + 2
        while time.time() < deadline and ps_proc.status() != psutil.STATUS_STOPPED:
            time.sleep(0.02)
        assert ps_proc.status() == psutil.STATUS_STOPPED

        resp = client.post("/api/resume")
        assert resp.status_code == 200
        deadline = time.time() + 2
        while time.time() < deadline and ps_proc.status() == psutil.STATUS_STOPPED:
            time.sleep(0.02)
        assert ps_proc.status() != psutil.STATUS_STOPPED
    finally:
        web_app.worker.terminate_current()


def test_api_history_returns_a_list():
    resp = client.get("/api/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_api_history_search_empty_query_returns_empty_list():
    # q ריק לא אמור להחזיר את כל ההיסטוריה - הלקוח (web_app.py's loadHistory())
    # כבר מטפל בתצוגה הרגילה, /api/history/search הוא רק למצב "יש טקסט חיפוש".
    resp = client.get("/api/history/search", params={"q": ""})
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_history_search_finds_matching_jobs(tmp_path, monkeypatch):
    from utils.shared import job_history
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 1.0, result={"file": "clip_42.mp4"})
    job_history.record_job("disk_scanner.py", "success", "t1", "t2", 1.0)

    resp = client.get("/api/history/search", params={"q": "clip_42"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["script"] == "video_editor.py"


def test_api_history_search_no_match_returns_empty_list(tmp_path, monkeypatch):
    from utils.shared import job_history
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("a.py", "success", "t1", "t2", 1.0)

    resp = client.get("/api/history/search", params={"q": "nonexistent_xyz"})

    assert resp.status_code == 200
    assert resp.json() == []


def test_api_lock_status_when_free(monkeypatch):
    monkeypatch.setattr(web_app, "get_render_lock_status", lambda: None)
    resp = client.get("/api/lock_status")
    assert resp.status_code == 200
    assert resp.json() == {"locked": False}


def test_api_lock_status_when_held(monkeypatch):
    monkeypatch.setattr(web_app, "get_render_lock_status", lambda: {"pid": 1234, "age_seconds": 90, "is_stale": False})
    resp = client.get("/api/lock_status")
    data = resp.json()
    assert data["locked"] is True
    assert data["pid"] == 1234
    assert data["is_stale"] is False
    assert data["age_seconds"] == 90  # גל 30: הממשק מעצב את הזמן בעצמו (בלי "ש'" בממשק האנגלי)


def test_api_run_clears_log_replay_buffer(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: None)
    web_app._LOG_REPLAY_BUFFER.append(("stale line from an old run", None))

    resp = client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path)})
    assert resp.status_code == 200
    assert len(web_app._LOG_REPLAY_BUFFER) == 0


def test_api_scheduler_tasks_list_includes_script_name(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    web_app.scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="04:00")

    resp = client.get("/api/scheduler/tasks")

    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert "script_name" in tasks[0]


def test_api_scheduler_tasks_add_creates_a_real_task(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))

    resp = client.post("/api/scheduler/tasks", json={
        "script_id": "video/video_editor.py", "schedule_type": "daily", "time_str": "05:00",
        "weekday": "sun", "interval_hours": 24,
    })

    assert resp.status_code == 200
    tasks = web_app.scheduler_store.load_tasks()
    assert len(tasks) == 1
    assert tasks[0]["script_path"].endswith("video_editor.py")
    assert tasks[0]["time"] == "05:00"


def test_api_scheduler_tasks_add_records_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/scheduler/tasks", json={
        "script_id": "video/video_editor.py", "schedule_type": "daily", "time_str": "05:00",
        "weekday": "sun", "interval_hours": 24,
    })

    assert resp.status_code == 200
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "scheduler_task_add")
    assert kwargs["details"] == "video_editor.py"


def test_api_scheduler_tasks_add_rejects_unknown_script(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))

    resp = client.post("/api/scheduler/tasks", json={"script_id": "video/nonexistent_script.py", "schedule_type": "daily"})

    assert resp.status_code == 400
    assert web_app.scheduler_store.load_tasks() == []


def test_api_scheduler_tasks_add_rejects_unknown_schedule_type(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))

    resp = client.post("/api/scheduler/tasks", json={"script_id": "video/video_editor.py", "schedule_type": "monthly"})

    assert resp.status_code == 400


def test_api_scheduler_tasks_toggle_flips_enabled_state(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = web_app.scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily")

    resp = client.post(f"/api/scheduler/tasks/{task['id']}/toggle", json={"enabled": False})

    assert resp.status_code == 200
    assert web_app.scheduler_store.load_tasks()[0]["enabled"] is False


def test_api_scheduler_tasks_toggle_reports_missing_task(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))

    resp = client.post("/api/scheduler/tasks/nonexistent-id/toggle", json={"enabled": True})

    assert resp.status_code == 404


def test_api_scheduler_tasks_delete_removes_task(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = web_app.scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily")

    resp = client.delete(f"/api/scheduler/tasks/{task['id']}")

    assert resp.status_code == 200
    assert web_app.scheduler_store.load_tasks() == []


def test_api_scheduler_tasks_delete_records_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = web_app.scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily")
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.delete(f"/api/scheduler/tasks/{task['id']}")

    assert resp.status_code == 200
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "scheduler_task_delete")
    assert kwargs["details"] == task["id"]


def test_side_effects_sends_webhook_on_success(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"webhook": "https://discord.example.com/hook"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    mock_webhook = MagicMock()
    monkeypatch.setattr(web_app, "send_webhook_notification", mock_webhook)

    web_app._run_completion_side_effects("video_editor.py", True, 12.3, {"clips": 3})

    mock_webhook.assert_called_once()
    url, message = mock_webhook.call_args[0]
    assert url == "https://discord.example.com/hook"
    assert "video_editor.py" in message
    assert "clips: 3" in message


def test_side_effects_sends_webhook_on_failure_too(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"webhook": "https://discord.example.com/hook"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    mock_webhook = MagicMock()
    monkeypatch.setattr(web_app, "send_webhook_notification", mock_webhook)

    web_app._run_completion_side_effects("video_editor.py", False, 5.0, None)

    mock_webhook.assert_called_once()
    _url, message = mock_webhook.call_args[0]
    assert "❌" in message


def test_side_effects_skips_webhook_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "does_not_exist.json"))
    mock_webhook = MagicMock()
    monkeypatch.setattr(web_app, "send_webhook_notification", mock_webhook)

    web_app._run_completion_side_effects("video_editor.py", True, 1.0, None)

    mock_webhook.assert_not_called()


def test_side_effects_triggers_backup_mirror_on_success(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"auto_backup_active": True, "nas_folder": "D:/Backups"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)
    # רק vertical/ ו-horizontal/ "קיימות בפועל" - square/ נשארת (בכוונה) בלי
    # תיקייה מזויפת, כדי לוודא שהיא מדולגת בשקט ולא נספרת כשגיאה.
    vertical_dir = tmp_path / "vertical"
    horizontal_dir = tmp_path / "horizontal"
    vertical_dir.mkdir()
    horizontal_dir.mkdir()
    square_dir = tmp_path / "square"  # לא נוצרת בכוונה
    monkeypatch.setattr(web_app, "WEB_APP_EXPORT_DIRS", [str(vertical_dir), str(horizontal_dir), str(square_dir)])
    mock_mirror = MagicMock(return_value=(3, None))
    monkeypatch.setattr(web_app, "mirror_folder", mock_mirror)

    web_app._run_completion_side_effects("video_editor.py", True, 1.0, None)

    assert mock_mirror.call_count == 2
    # כל תיקיית תוצרים ל-<יעד>/<שמה> (מ-19.10.2026 - תיקיות לפי כלי, והישנות לפי כיוון כל עוד הן קיימות)
    mock_mirror.assert_any_call(str(vertical_dir), os.path.join("D:/Backups", "vertical"))
    mock_mirror.assert_any_call(str(horizontal_dir), os.path.join("D:/Backups", "horizontal"))


def test_side_effects_skips_backup_mirror_on_failure(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"auto_backup_active": True, "nas_folder": "D:/Backups"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)
    mock_mirror = MagicMock(return_value=(0, None))
    monkeypatch.setattr(web_app, "mirror_folder", mock_mirror)

    web_app._run_completion_side_effects("video_editor.py", False, 1.0, None)

    mock_mirror.assert_not_called()


def test_side_effects_skips_backup_mirror_when_toggle_off(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"auto_backup_active": False, "nas_folder": "D:/Backups"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)
    mock_mirror = MagicMock(return_value=(0, None))
    monkeypatch.setattr(web_app, "mirror_folder", mock_mirror)

    web_app._run_completion_side_effects("video_editor.py", True, 1.0, None)

    mock_mirror.assert_not_called()


def test_side_effects_triggers_shutdown_and_returns_true_on_night_mode(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"night_active": True}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    mock_system = MagicMock()
    monkeypatch.setattr(web_app.os, "system", mock_system)

    triggered = web_app._run_completion_side_effects("video_editor.py", True, 1.0, None)

    assert triggered is True
    mock_system.assert_called_once()
    assert f"/t {web_app.SHUTDOWN_COUNTDOWN_SECONDS}" in mock_system.call_args[0][0]


def test_side_effects_returns_false_without_night_mode(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"night_active": False}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    mock_system = MagicMock()
    monkeypatch.setattr(web_app.os, "system", mock_system)

    triggered = web_app._run_completion_side_effects("video_editor.py", True, 1.0, None)

    assert triggered is False
    mock_system.assert_not_called()


def test_side_effects_returns_false_on_failed_run_even_with_night_mode(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"night_active": True}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    mock_system = MagicMock()
    monkeypatch.setattr(web_app.os, "system", mock_system)

    triggered = web_app._run_completion_side_effects("video_editor.py", False, 1.0, None)

    assert triggered is False
    mock_system.assert_not_called()


def test_api_cancel_shutdown_calls_shutdown_a(monkeypatch):
    mock_system = MagicMock()
    monkeypatch.setattr(web_app.os, "system", mock_system)

    resp = client.post("/api/cancel_shutdown")

    assert resp.status_code == 200
    mock_system.assert_called_once_with("shutdown /a")


def test_api_cancel_shutdown_requires_same_origin(monkeypatch):
    mock_system = MagicMock()
    monkeypatch.setattr(web_app.os, "system", mock_system)

    resp = client.post("/api/cancel_shutdown", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403
    mock_system.assert_not_called()


# --- Favorites / recently-run (7/N desktop-parity gaps) ---

def test_api_scripts_reports_is_favorite(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"favorite_scripts": "video_editor.py"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    resp = client.get("/api/scripts")

    assert resp.status_code == 200
    scripts = resp.json()
    favorite_flags = {s["id"]: s["is_favorite"] for s in scripts}
    assert any(sid.endswith("video_editor.py") and flag for sid, flag in favorite_flags.items())
    assert any(sid.endswith("disk_scanner.py") and not flag for sid, flag in favorite_flags.items())


def test_the_unused_favorite_write_endpoint_is_gone(tmp_path, monkeypatch):
    """16.10.2026: המועדפים בדפדפן ב-localStorage (test_web_app_scripts_catalog_browser בודק שאין POST), והאפליקציה
    השולחנית כותבת לבד - POST /api/scripts/favorite הוסר. הקריאה (is_favorite ב-/api/scripts) נשארה."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"favorite_scripts": "story_cutter.py"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    assert client.post("/api/scripts/favorite", json={"id": "video/video_editor.py"}).status_code in (404, 405)
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"favorite_scripts": "story_cutter.py"}


def test_api_scripts_recent_returns_names_from_job_history(monkeypatch):
    monkeypatch.setattr(
        web_app.job_history, "get_recently_run_script_names",
        lambda limit=5: ["video_editor.py", "disk_scanner.py"],
    )

    resp = client.get("/api/scripts/recent")

    assert resp.status_code == 200
    assert resp.json() == {"names": ["video_editor.py", "disk_scanner.py"]}
