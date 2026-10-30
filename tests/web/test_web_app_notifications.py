# tests/web/test_web_app_notifications.py
#
# 23.10.2026: מרכז ההתראות בשרת - ה-routes (routes/notifications.py) והאירועים שנרשמים: סוף ריצה (גם בלי טאב מחובר),
# ריצה שנעצרה, פרסום משורשר, תיקיית ייצוא שלא הייתה זמינה, בוט שהפסיק לעלות. ה-DB זמני לכל טסט.
import queue

import pytest

from tests.web_app_support import client, web_app
from utils.shared import export_dir, notification_log


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(notification_log, "DB_PATH", str(tmp_path / "notifications.db"))
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)
    monkeypatch.setattr(web_app, "_current_run", {"script_name": "video_editor.py", "started_at": None})
    yield
    while True:   # _on_task_finished דוחף גם לתור של ה-/ws - לא משאירים בו לטסט הבא
        try:
            web_app._finished_queue.get_nowait()
        except queue.Empty:
            break


def _titles():
    return [(i["title"], i["level"], i["target"]) for i in client.get("/api/notifications").json()["items"]]


def test_a_finished_run_is_recorded_even_with_no_tab_open():
    web_app._current_run["started_at"] = web_app.time.time() - 125
    web_app._on_task_finished({"returncode": 0, "result": {"outputs": 3}})
    item = client.get("/api/notifications").json()["items"][0]
    assert (item["title"], item["level"], item["target"]) == ("✅ הסתיים: video_editor.py", "ok", "outputs")
    assert item["body"] == "משך: 2.1 דקות · outputs: 3"


def test_failed_and_stopped_runs():
    web_app._on_task_finished({"returncode": 1, "result": None})
    web_app._current_run["stop_requested"] = True
    web_app._on_task_finished({"returncode": 1, "result": None})
    assert _titles() == [("⏹️ נעצר: video_editor.py", "info", "scripts"), ("❌ נכשל: video_editor.py", "bad", "scripts")]


def test_stop_marks_the_current_run(monkeypatch):
    monkeypatch.setattr(web_app.worker, "terminate_current", lambda: None)
    assert client.post("/api/stop").status_code == 200
    assert web_app._current_run["stop_requested"] is True


def test_a_chained_publish_is_named_after_the_publisher():
    web_app._on_publisher_finished({"returncode": 0, "result": None})
    assert _titles() == [("✅ הסתיים: rocket_shorts_publisher.py", "ok", "outputs")]


def test_an_unavailable_export_folder_is_a_warning(tmp_path):
    export_dir.save_root(str(tmp_path / "unplugged"))
    web_app._on_task_finished({"returncode": 0, "result": None})
    titles = _titles()
    assert titles[0][1:] == ("warn", "globalsettings") and str(tmp_path / "unplugged") in titles[0][0]
    assert titles[1][0] == "✅ הסתיים: video_editor.py"


def test_a_bot_that_stopped_coming_up():
    web_app._notify_bot("🤖 הבוט נעצר אחרי קריסות חוזרות", "פרטים בלוג")
    assert _titles() == [("🤖 הבוט נעצר אחרי קריסות חוזרות", "bad", "bot")]


def test_a_broken_store_does_not_stop_the_run_from_finishing(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(notification_log, "add", broken)
    web_app._on_task_finished({"returncode": 0, "result": None})
    assert web_app._finished_queue.get_nowait() == {"returncode": 0, "result": None}


def test_unread_and_marking_read():
    first = notification_log.add("run", "a")
    second = notification_log.add("run", "b")
    assert client.get("/api/notifications/unread").json() == {"unread": 2, "latest": second}
    assert client.post("/api/notifications/read", json={"up_to": first}).json() == {"unread": 1, "latest": second}
    data = client.get("/api/notifications").json()
    assert data["unread"] == 1 and [i["read"] for i in data["items"]] == [False, True]


def test_marking_read_needs_an_id_and_the_same_origin():
    notification_log.add("run", "a")
    for bad in ({}, {"up_to": "1"}, {"up_to": True}, ["x"]):
        assert client.post("/api/notifications/read", json=bad).status_code == 400, bad
    foreign = client.post("/api/notifications/read", json={"up_to": 1}, headers={"origin": "https://evil.example.com"})
    assert foreign.status_code == 403 and client.get("/api/notifications/unread").json()["unread"] == 1
