# tests/web/test_web_app_run_end.py
#
# 23.10.2026: מה שקורה בסוף ריצה - היסטוריית הריצות, ה-webhook, הגיבוי האוטומטי ומצב לילה - קורה בסוף הריצה עצמה
# (web_app._record_run_end), גם כשאין טאב מחובר; עד עכשיו זה היה רק בלולאת ה-/ws. כשטאב מחובר - כל אחד פעם אחת בדיוק,
# והספירה לאחור של הכיבוי מגיעה לדפדפן עם ביטול, כמו קודם. os.system וה-webhook מזויפים: אין כיבוי ואין רשת.
import json
import queue
import time
from unittest.mock import MagicMock

import pytest

from tests.web_app_support import _ImmediateThread, client, web_app
from utils.shared import job_history, notification_log

WEBHOOK = "https://discord.example.com/hook"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(notification_log, "DB_PATH", str(tmp_path / "notifications.db"))
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(web_app, "_current_run", {"script_name": "video_editor.py", "started_at": time.time() - 30})
    monkeypatch.setattr(web_app, "send_webhook_notification", MagicMock())
    monkeypatch.setattr(web_app.os, "system", MagicMock())   # כיבוי אמיתי - אף פעם
    monkeypatch.setattr(web_app, "_night_shutdown_waiting", False, raising=False)
    monkeypatch.setattr(web_app.worker, "pending_count", lambda: 0)   # תור ריק ושום מסלול לא רץ, אלא אם הטסט אומר אחרת
    monkeypatch.setattr(web_app.worker, "active_processes", {})
    yield
    while True:
        try:
            web_app._finished_queue.get_nowait()
        except queue.Empty:
            break


def _config(tmp_path, **values):
    (tmp_path / "config.json").write_text(json.dumps(values), encoding="utf-8")


def _finish(returncode=0, **extra):
    outcome = {"returncode": returncode, "result": {"clips": 3}, **extra}
    web_app._on_task_finished(outcome)
    return outcome


def _jobs():
    return [(row[0], row[1]) for row in job_history.get_recent_jobs()]


def test_the_run_is_in_the_history_with_no_tab_open():
    _finish()
    assert _jobs() == [("video_editor.py", "success")]


def test_the_webhook_goes_out_with_no_tab_open(tmp_path):
    _config(tmp_path, webhook=WEBHOOK)
    _finish()
    web_app.send_webhook_notification.assert_called_once()
    url, message = web_app.send_webhook_notification.call_args[0]
    assert url == WEBHOOK and "video_editor.py" in message and "clips: 3" in message


def test_the_automatic_backup_runs_with_no_tab_open(tmp_path, monkeypatch):
    _config(tmp_path, auto_backup_active=True, nas_folder=str(tmp_path / "nas"))
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)
    mirror = MagicMock()
    monkeypatch.setattr(web_app, "_mirror_export_dirs", mirror)
    _finish()
    mirror.assert_called_once_with(str(tmp_path / "nas"))


def test_night_mode_shuts_down_with_the_cancellable_countdown_with_no_tab_open(tmp_path):
    _config(tmp_path, night_active=True)
    outcome = _finish()
    web_app.os.system.assert_called_once()
    assert f"/t {web_app.SHUTDOWN_COUNTDOWN_SECONDS}" in web_app.os.system.call_args[0][0]
    assert outcome["shutdown_seconds"] == web_app.SHUTDOWN_COUNTDOWN_SECONDS   # מה שה-/ws שולח לדפדפן (ביטול)


def test_night_mode_only_when_it_is_on_and_the_run_succeeded(tmp_path):
    _config(tmp_path, night_active=True)
    assert "shutdown_seconds" not in _finish(returncode=1)
    _config(tmp_path, night_active=False)
    assert "shutdown_seconds" not in _finish()
    web_app.os.system.assert_not_called()


def test_with_a_tab_open_each_happens_exactly_once(tmp_path):
    _config(tmp_path, webhook=WEBHOOK, night_active=True)
    web_app._LOG_REPLAY_BUFFER.clear()
    with client.websocket_connect("/ws") as ws:
        _finish()
        for _ in range(50):
            message = ws.receive_json()
            if message["type"] == "finished":
                break
    assert message["type"] == "finished" and message["success"] is True
    assert message["shutdown_seconds"] == web_app.SHUTDOWN_COUNTDOWN_SECONDS
    assert _jobs() == [("video_editor.py", "success")]
    web_app.send_webhook_notification.assert_called_once()
    web_app.os.system.assert_called_once()


def test_a_task_removed_from_the_queue_records_nothing(tmp_path):
    _config(tmp_path, webhook=WEBHOOK, night_active=True)
    _finish(returncode=-1, removed_from_queue=True)
    assert _jobs() == [] and notification_log.recent() == []
    web_app.send_webhook_notification.assert_not_called()
    web_app.os.system.assert_not_called()
    assert web_app._finished_queue.get_nowait()["removed_from_queue"] is True   # הדפדפן עדיין מקבל אותה, כמו קודם


def test_a_chained_publish_is_not_recorded_as_the_run_before_it(tmp_path):
    _config(tmp_path, webhook=WEBHOOK)
    web_app._on_publisher_finished({"returncode": 0, "result": None})
    assert _jobs() == []
    web_app.send_webhook_notification.assert_not_called()


# --- מצב לילה ותור (23.10.2026, בקשת המפנה): בלי טאב אין מי שיבטל, אז לא מכבים באמצע התור ---

def _log_lines():
    lines = []
    while True:
        try:
            lines.append(web_app.worker.log_queue.get_nowait()[0])
        except queue.Empty:
            return lines


def _shutdown_calls():
    return [call.args[0] for call in web_app.os.system.call_args_list if "/s" in call.args[0]]


def test_night_mode_waits_for_the_last_task_in_the_queue(tmp_path, monkeypatch):
    _config(tmp_path, night_active=True)
    pending = [1]
    monkeypatch.setattr(web_app.worker, "pending_count", lambda: pending[0])
    _log_lines()
    first = _finish()
    assert _shutdown_calls() == [] and "shutdown_seconds" not in first
    assert any("מצב לילה" in line and "יחכה לסוף" in line for line in _log_lines())
    pending[0] = 0
    second = _finish()
    assert len(_shutdown_calls()) == 1 and second["shutdown_seconds"] == web_app.SHUTDOWN_COUNTDOWN_SECONDS


def test_night_mode_waits_while_the_other_lane_is_running(tmp_path, monkeypatch):
    _config(tmp_path, night_active=True)
    monkeypatch.setattr(web_app.worker, "active_processes", {1: object()})
    assert "shutdown_seconds" not in _finish()
    assert _shutdown_calls() == []
    monkeypatch.setattr(web_app.worker, "active_processes", {})
    assert _finish(returncode=1)["shutdown_seconds"] == web_app.SHUTDOWN_COUNTDOWN_SECONDS   # גם כשהאחרונה נכשלה


def test_the_waiting_shutdown_comes_after_a_chained_publish(tmp_path, monkeypatch):
    _config(tmp_path, night_active=True)
    pending = [1]                                     # הפרסום המשורשר כבר בתור כשעורך-העל מסתיים
    monkeypatch.setattr(web_app.worker, "pending_count", lambda: pending[0])
    _finish()
    pending[0] = 0
    publish = {"returncode": 0, "result": None}
    web_app._on_publisher_finished(publish)
    assert len(_shutdown_calls()) == 1 and publish["shutdown_seconds"] == web_app.SHUTDOWN_COUNTDOWN_SECONDS


def test_a_waiting_shutdown_is_dropped_by_cancel_or_by_turning_night_mode_off(tmp_path, monkeypatch):
    _config(tmp_path, night_active=True)
    pending = [1]
    monkeypatch.setattr(web_app.worker, "pending_count", lambda: pending[0])
    _finish()
    assert client.post("/api/cancel_shutdown").status_code == 200
    pending[0] = 0
    _finish(returncode=1)
    assert _shutdown_calls() == []

    pending[0] = 1
    _finish()
    _config(tmp_path, night_active=False)
    pending[0] = 0
    _finish(returncode=1)
    assert _shutdown_calls() == []
