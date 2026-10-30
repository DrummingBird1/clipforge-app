# tests/infra/test_notifications.py
import threading


from utils.shared import notifications


def _run_and_join_threads(monkeypatch, fn, *args):
    """send_webhook_notification רץ ב-thread נפרד (item: לא לתקוע את ה-UI) -
    ה-thread יכול להסתיים כל כך מהר (עבודה מדומה, בלי I/O אמיתי) שהוא כבר
    לא "חי" ברשימת threading.enumerate() עד שמגיעים לבדוק - לכן תופסים את
    ה-Thread עצמו ברגע היצירה (monkeypatch על threading.Thread) במקום לנחש
    לפי הפרש-קבוצות אחרי המעשה, ומחכים לו במפורש (join) לפני שבודקים מה קרה
    בתוכו."""
    created = []
    real_thread_cls = threading.Thread

    class _CapturingThread(real_thread_cls):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            created.append(self)

    monkeypatch.setattr(notifications.threading, "Thread", _CapturingThread)
    fn(*args)
    for t in created:
        t.join(timeout=2)
    return created


def test_send_webhook_notification_posts_content_to_the_given_url(monkeypatch):
    calls = []

    class _FakeRequests:
        @staticmethod
        def post(url, json, timeout):
            calls.append((url, json, timeout))

    monkeypatch.setattr(notifications, "requests", _FakeRequests)

    threads = _run_and_join_threads(monkeypatch, notifications.send_webhook_notification, "https://discord.example/webhook", "hello")

    assert len(threads) == 1
    assert threads[0].daemon is True
    assert calls == [("https://discord.example/webhook", {"content": "hello"}, 10)]


def test_send_webhook_notification_does_nothing_without_a_url(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "requests", type("R", (), {"post": staticmethod(lambda *a, **k: calls.append(1))}))

    threads = _run_and_join_threads(monkeypatch, notifications.send_webhook_notification, "", "hello")

    assert threads == []
    assert calls == []


def test_send_webhook_notification_does_nothing_when_requests_is_unavailable(monkeypatch):
    monkeypatch.setattr(notifications, "requests", None)

    threads = _run_and_join_threads(monkeypatch, notifications.send_webhook_notification, "https://discord.example/webhook", "hello")

    assert threads == []


def test_send_webhook_notification_swallows_network_errors(monkeypatch, capsys):
    class _FailingRequests:
        @staticmethod
        def post(url, json, timeout):
            raise ConnectionError("no network")

    monkeypatch.setattr(notifications, "requests", _FailingRequests)

    threads = _run_and_join_threads(monkeypatch, notifications.send_webhook_notification, "https://discord.example/webhook", "hello")

    assert len(threads) == 1  # ה-thread רץ והסתיים בלי לזרוק חוצה
    assert "שגיאה בשליחת Webhook" in capsys.readouterr().out


def test_send_toast_notification_shows_a_windows_toast(monkeypatch):
    created = {}

    class _FakeToast:
        def __init__(self, app_id, title, msg):
            created["app_id"] = app_id
            created["title"] = title
            created["msg"] = msg

        def show(self):
            created["shown"] = True

    monkeypatch.setattr(notifications, "Notification", _FakeToast)

    notifications.send_toast_notification("Title", "Message")

    assert created == {"app_id": "ClipForge", "title": "Title", "msg": "Message", "shown": True}


def test_send_toast_notification_does_nothing_when_winotify_is_unavailable(monkeypatch):
    monkeypatch.setattr(notifications, "Notification", None)

    notifications.send_toast_notification("Title", "Message")  # לא אמור לזרוק


def test_send_toast_notification_swallows_errors_from_the_toast_library(monkeypatch, capsys):
    class _FailingToast:
        def __init__(self, app_id, title, msg):
            pass

        def show(self):
            raise OSError("toast subsystem unavailable")

    monkeypatch.setattr(notifications, "Notification", _FailingToast)

    notifications.send_toast_notification("Title", "Message")  # לא אמור לזרוק

    assert "שגיאה בשליחת התראת Windows" in capsys.readouterr().out
