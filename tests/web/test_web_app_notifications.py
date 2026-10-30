# tests/web/test_web_app_notifications.py
#
# 23.10.2026: מרכז ההתראות בשרת - ה-routes (routes/notifications.py) והאירועים שנרשמים: סוף ריצה (גם בלי טאב מחובר),
# ריצה שנעצרה, פרסום משורשר, תיקיית ייצוא שלא הייתה זמינה, בוט שהפסיק לעלות. ה-DB זמני לכל טסט.
import json
import queue
import re

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
    web_app._on_task_finished({"returncode": 0, "result": {"files_created": 3}})
    item = client.get("/api/notifications").json()["items"][0]
    assert (item["title"], item["level"], item["target"]) == ("✅ הסתיים: video_editor.py", "ok", "outputs")
    assert item["body"] == "3 נוצרו · 2:05"


def test_a_studio_run_body_is_readable_with_no_paths_or_raw_keys(tmp_path, monkeypatch):
    """30.10.2026: הגוף היה הסיכום הגולמי של RESULT ("files_created: 3 | ... | manifest_path: C:\\...") - עכשיו ספירות, משך
    וגודל התוצרים, וכל חלק מתורגם לאנגלית בדף."""
    from tests.web.test_web_i18n_dynamic import _translator
    manifests = tmp_path / "run_manifests"
    manifests.mkdir()
    monkeypatch.setattr(web_app, "RUN_MANIFESTS_DIR", str(manifests))
    outputs = []
    for name, size in (("a_shorts.mp4", 3_000_000), ("b_shorts.mp4", 1_900_000)):
        (tmp_path / name).write_bytes(b"\0" * size)
        outputs.append({"status": "created", "output": str(tmp_path / name)})
    manifest = manifests / "20261030_204421_1.json"
    manifest.write_text(json.dumps({"files": outputs + [{"status": "error", "output": ""}]}), encoding="utf-8")
    web_app._current_run["started_at"] = web_app.time.time() - 17
    web_app._on_task_finished({"returncode": 0, "result": {
        "files_created": 2, "errors": 1, "skipped": 0, "valid": 0, "invalid": 0, "hwaccel": False, "codec": "h264",
        "cancelled": 0, "elapsed_seconds": 16.2, "avg_seconds_per_file": 8.1, "manifest_path": str(manifest)}})
    body = client.get("/api/notifications").json()["items"][0]["body"]
    assert body == "2 נוצרו · 1 נכשלו · 0:17 · 4.9 MB"
    assert str(tmp_path) not in body and ":\\" not in body and not re.search(r"\w: ", body)
    assert _translator().translate(body) == "2 created · 1 failed · 0:17 · 4.9 MB"


@pytest.mark.parametrize("result, body", [
    ({"valid": 4, "invalid": 1, "files_created": 0}, "4 תקינים · 1 לא תקינים"),
    ({"files_created": 0, "errors": 0}, "0 נוצרו"),
    ({"renamed": 3, "errors": 0, "total": 3}, "3 שמות שונו"),
    ({"preview_path": "C:\\x\\preview.mp4", "videos_found": 2}, ""),
    ("not a dict", ""),
])
def test_the_body_counts_known_keys_and_drops_the_rest(result, body):
    from entrypoints.web import run_lifecycle
    assert run_lifecycle._run_notification_body(result, None) == body


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


def test_marking_read_on_a_locked_db_does_not_stop_the_server():
    """30.10.2026: ה-route הוא async, וה-sqlite שלו רץ בתוך ה-event loop - כשכותב אחר החזיק את ה-DB, כל השרת עמד עד
    busy_timeout (10 שניות): /api/notifications ושאר הבקשות חיכו מאחוריו. עכשיו ה-sqlite ב-threadpool."""
    import asyncio
    import sqlite3
    import threading

    from starlette.requests import Request

    from entrypoints.web.routes.notifications import api_notifications_read

    first = notification_log.add("run", "a")
    blocker = sqlite3.connect(notification_log.DB_PATH, check_same_thread=False)
    blocker.execute("BEGIN IMMEDIATE")   # כותב אחר מחזיק את ה-DB
    release = threading.Timer(1.0, blocker.rollback)
    body = json.dumps({"up_to": first}).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request({"type": "http", "method": "POST", "path": "/api/notifications/read", "query_string": b"",
                       "headers": [(b"content-type", b"application/json")]}, receive)

    async def scenario():
        ticks = 0

        async def other_requests():
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        other = asyncio.create_task(other_requests())
        release.start()
        response = await api_notifications_read(request)
        other.cancel()
        return ticks, response

    try:
        ticks, response = asyncio.run(scenario())
    finally:
        release.cancel()
        blocker.close()
    assert response == {"unread": 0, "latest": first}
    assert ticks >= 20, f"ה-event loop עמד בזמן שה-DB היה נעול ({ticks} סבבים בשנייה)"
