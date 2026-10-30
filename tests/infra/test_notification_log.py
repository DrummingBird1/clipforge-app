# tests/infra/test_notification_log.py
#
# 23.10.2026: המאגר של מרכז ההתראות (utils/shared/notification_log.py), ב-DB זמני לכל טסט.
import pytest

from utils.shared import notification_log


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "notifications.db")


def test_newest_first_with_a_shared_unread_count(path):
    first = notification_log.add("run", "✅ הסתיים: a.py", body="משך: 3 שניות", level="ok", target="outputs", path=path)
    second = notification_log.add("bot", "🤖 הבוט נעצר", level="bad", target="bot", path=path)
    items = notification_log.recent(path=path)
    assert [i["id"] for i in items] == [second, first]
    assert items[1]["title"] == "✅ הסתיים: a.py" and items[1]["body"] == "משך: 3 שניות" and items[1]["target"] == "outputs"
    assert items[0]["level"] == "bad" and items[0]["read"] is False and items[0]["created_at"] > 0
    assert notification_log.unread(path=path) == {"unread": 2, "latest": second}


def test_read_up_to_the_last_one_shown(path):
    shown = notification_log.add("run", "a", path=path)
    arrived_later = notification_log.add("run", "b", path=path)
    notification_log.mark_read(shown, path=path)
    assert notification_log.unread(path=path) == {"unread": 1, "latest": arrived_later}
    assert [i["read"] for i in notification_log.recent(path=path)] == [False, True]
    notification_log.mark_read(path=path)
    assert notification_log.unread(path=path)["unread"] == 0


def test_an_empty_log(path):
    assert notification_log.recent(path=path) == []
    assert notification_log.unread(path=path) == {"unread": 0, "latest": 0}


def test_only_the_newest_are_kept(path, monkeypatch):
    monkeypatch.setattr(notification_log, "KEEP", 3)
    ids = [notification_log.add("run", f"n{n}", path=path) for n in range(5)]
    assert [i["id"] for i in notification_log.recent(path=path)] == ids[:1:-1]


def test_unknown_levels_and_long_texts_are_tamed(path):
    notification_log.add("run", "x" * 2000, body="y" * 2000, level="explode", path=path)
    item = notification_log.recent(path=path)[0]
    assert item["level"] == "info" and len(item["title"]) == notification_log.MAX_TEXT and len(item["body"]) == notification_log.MAX_TEXT
