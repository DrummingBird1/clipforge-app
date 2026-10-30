# tests/bot/test_scheduler.py
import datetime


from utils.bot import scheduler, scheduler_store


def _daily_task(time_str="03:00", last_run_at=None, enabled=True):
    return {
        "id": "t1", "script_path": "my_scripts/tools/disk_scanner.py",
        "schedule_type": "daily", "time": time_str, "weekday": "sun",
        "interval_hours": 24, "enabled": enabled, "last_run_at": last_run_at,
    }


def test_daily_task_due_after_scheduled_time_if_never_run():
    task = _daily_task(time_str="03:00")
    now = datetime.datetime(2026, 1, 5, 3, 30)
    assert scheduler.is_due(task, now) is True


def test_daily_task_not_due_before_scheduled_time():
    task = _daily_task(time_str="03:00")
    now = datetime.datetime(2026, 1, 5, 2, 59)
    assert scheduler.is_due(task, now) is False


def test_daily_task_not_due_twice_same_day():
    task = _daily_task(time_str="03:00", last_run_at="2026-01-05T03:00:00")
    now = datetime.datetime(2026, 1, 5, 14, 0)
    assert scheduler.is_due(task, now) is False


def test_daily_task_due_again_next_day():
    task = _daily_task(time_str="03:00", last_run_at="2026-01-04T03:00:00")
    now = datetime.datetime(2026, 1, 5, 3, 30)
    assert scheduler.is_due(task, now) is True


def test_disabled_task_never_due():
    task = _daily_task(enabled=False)
    now = datetime.datetime(2026, 1, 5, 12, 0)
    assert scheduler.is_due(task, now) is False


def test_weekly_task_only_due_on_matching_weekday():
    task = {
        "id": "t2", "script_path": "x.py", "schedule_type": "weekly",
        "time": "10:00", "weekday": "sun", "interval_hours": 24,
        "enabled": True, "last_run_at": None,
    }
    sunday = datetime.datetime(2026, 1, 4, 11, 0)  # 2026-01-04 is a Sunday
    monday = datetime.datetime(2026, 1, 5, 11, 0)
    assert scheduler.is_due(task, sunday) is True
    assert scheduler.is_due(task, monday) is False


def test_interval_hours_due_after_elapsed_time():
    task = {
        "id": "t3", "script_path": "x.py", "schedule_type": "interval_hours",
        "time": "03:00", "weekday": "sun", "interval_hours": 6,
        "enabled": True, "last_run_at": "2026-01-05T00:00:00",
    }
    not_yet = datetime.datetime(2026, 1, 5, 5, 0)
    ready = datetime.datetime(2026, 1, 5, 6, 1)
    assert scheduler.is_due(task, not_yet) is False
    assert scheduler.is_due(task, ready) is True


def test_interval_hours_due_immediately_if_never_run():
    task = {
        "id": "t4", "script_path": "x.py", "schedule_type": "interval_hours",
        "time": "03:00", "weekday": "sun", "interval_hours": 6,
        "enabled": True, "last_run_at": None,
    }
    assert scheduler.is_due(task, datetime.datetime.now()) is True


def test_store_add_remove_and_toggle(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))

    task = scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="04:00")
    assert len(scheduler_store.load_tasks()) == 1

    scheduler_store.set_enabled(task["id"], False)
    assert scheduler_store.load_tasks()[0]["enabled"] is False

    scheduler_store.mark_run(task["id"], "2026-01-05T04:00:00")
    assert scheduler_store.load_tasks()[0]["last_run_at"] == "2026-01-05T04:00:00"

    scheduler_store.remove_task(task["id"])
    assert scheduler_store.load_tasks() == []


def test_store_invalid_schedule_type_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    try:
        scheduler_store.add_task("x.py", "monthly")
        assert False, "expected ValueError for an unknown schedule_type"
    except ValueError:
        pass


def test_check_and_run_due_tasks_triggers_and_marks(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="00:00")

    calls = []

    class FakeWorker:
        def add_script_task(self, script_path, folder, on_finish, concurrency="heavy", extra_args=None):
            calls.append((script_path, concurrency))

    now = datetime.datetime(2026, 1, 5, 12, 0)
    triggered = scheduler.check_and_run_due_tasks(FakeWorker(), now=now)

    assert len(triggered) == 1
    assert calls == [("my_scripts/tools/disk_scanner.py", "light")]
    assert scheduler_store.load_tasks()[0]["last_run_at"] == now.isoformat(timespec="seconds")


def test_scheduled_task_from_editor_passes_folder_and_extra_args(monkeypatch, tmp_path):
    """גל 8 (item 91): משימה שתוזמנה מעורך-העל רצה על התיקייה ועם הדגלים שנשמרו בה."""
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = scheduler_store.add_task("my_scripts/video/video_editor.py", "daily", time_str="00:00",
                                    folder="C:/clips", extra_args=["--codec", "hevc"], label="לילי")
    assert (task["folder"], task["extra_args"], task["label"]) == ("C:/clips", ["--codec", "hevc"], "לילי")
    calls = []

    class FakeWorker:
        def add_script_task(self, script_path, folder, on_finish, concurrency="heavy", extra_args=None):
            calls.append((folder, extra_args))

    scheduler.check_and_run_due_tasks(FakeWorker(), now=datetime.datetime(2026, 1, 5, 12, 0))
    assert calls == [("C:/clips", ["--codec", "hevc"])]


class _RecordingWorker:
    def __init__(self):
        self.calls = []

    def add_script_task(self, script_path, folder, on_finish, concurrency="heavy", extra_args=None):
        self.calls.append(script_path)


def _ticks(worker, start, count=5, every_seconds=30):
    """כמו _run_scheduler_loop בשרת: בדיקה כל 30 שניות, החל מ-start."""
    for i in range(count):
        scheduler.check_and_run_due_tasks(worker, now=start + datetime.timedelta(seconds=every_seconds * i))


def test_daily_task_scheduled_for_this_exact_minute_is_due():
    assert scheduler.is_due(_daily_task(time_str="03:00"), datetime.datetime(2026, 1, 5, 3, 0, 0)) is True


def test_daily_task_missed_while_asleep_runs_once_on_wake(tmp_path, monkeypatch):
    """המחשב ישן ב-03:00 יומיים ברצף והתעורר ב-10:15: ריצה אחת מיד (לא אחת לכל יום שהוחמץ), ולא שוב באותו יום."""
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="03:00")
    scheduler_store.mark_run(task["id"], "2026-01-03T03:00:00")
    worker = _RecordingWorker()

    _ticks(worker, datetime.datetime(2026, 1, 5, 10, 15))
    assert worker.calls == ["my_scripts/tools/disk_scanner.py"]
    assert scheduler_store.load_tasks()[0]["last_run_at"] == "2026-01-05T10:15:00"

    _ticks(worker, datetime.datetime(2026, 1, 6, 3, 0), count=2)
    assert len(worker.calls) == 2


def test_interval_task_after_long_sleep_runs_once_and_counts_from_wake(tmp_path, monkeypatch):
    """כל 6 שעות, והמחשב ישן 3 ימים: ריצה אחת בהתעוררות (לא 12 ברצף), והבאה 6 שעות אחריה."""
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "interval_hours", interval_hours=6)
    scheduler_store.mark_run(task["id"], "2026-01-02T08:00:00")
    worker = _RecordingWorker()
    wake = datetime.datetime(2026, 1, 5, 9, 0)

    _ticks(worker, wake, count=10)
    assert len(worker.calls) == 1

    _ticks(worker, wake + datetime.timedelta(hours=5, minutes=59), count=1)
    assert len(worker.calls) == 1
    _ticks(worker, wake + datetime.timedelta(hours=6), count=1)
    assert len(worker.calls) == 2


def test_weekly_task_missed_while_asleep_runs_once_on_wake_then_back_on_schedule(tmp_path, monkeypatch):
    """ראשון 10:00, והמחשב ישן כל יום ראשון 11.1: רצה פעם אחת בהתעוררות (שני), לא שוב באותו שבוע,
    והריצה הבאה שוב בראשון 18.1 ב-10:00 (החלטת המשתמש, 16.10.2026 - כמו היומית)."""
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    task = scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "weekly", time_str="10:00", weekday="sun")
    scheduler_store.mark_run(task["id"], "2026-01-04T10:00:00")  # ראשון הקודם
    worker = _RecordingWorker()

    _ticks(worker, datetime.datetime(2026, 1, 12, 9, 0))  # שני - ההתעוררות
    assert len(worker.calls) == 1
    for day in (13, 14, 15, 16, 17):  # שלישי עד שבת
        _ticks(worker, datetime.datetime(2026, 1, day, 10, 0), count=2)
    _ticks(worker, datetime.datetime(2026, 1, 18, 9, 59), count=1)
    assert len(worker.calls) == 1

    _ticks(worker, datetime.datetime(2026, 1, 18, 10, 0), count=3)  # ראשון 18.1 - בזמן
    assert len(worker.calls) == 2
    assert scheduler_store.load_tasks()[0]["last_run_at"] == "2026-01-18T10:00:00"


def test_weekly_task_that_ran_on_time_is_not_repeated_after_a_wake_the_same_week():
    task = {
        "id": "w1", "script_path": "x.py", "schedule_type": "weekly", "time": "10:00", "weekday": "sun",
        "interval_hours": 24, "enabled": True, "last_run_at": "2026-01-11T10:00:00",
    }
    assert scheduler.is_due(task, datetime.datetime(2026, 1, 12, 9, 0)) is False
    assert scheduler.is_due(task, datetime.datetime(2026, 1, 17, 23, 59)) is False
    assert scheduler.is_due(task, datetime.datetime(2026, 1, 18, 10, 0)) is True


def test_one_broken_task_does_not_block_the_tasks_after_it(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    broken = scheduler_store.add_task("my_scripts/tools/file_renamer.py", "interval_hours", interval_hours=6)
    scheduler_store.add_task("my_scripts/tools/disk_scanner.py", "daily", time_str="00:00")
    tasks = scheduler_store.load_tasks()
    tasks[0].update(interval_hours="six", last_run_at="2026-01-05T00:00:00")
    tasks.append({"id": "no-path", "schedule_type": "daily", "time": "00:00", "enabled": True})
    scheduler_store.save_tasks(tasks)
    worker = _RecordingWorker()

    triggered = scheduler.check_and_run_due_tasks(worker, now=datetime.datetime(2026, 1, 5, 12, 0))

    assert worker.calls == ["my_scripts/tools/disk_scanner.py"]
    assert [t["script_path"] for t in triggered] == ["my_scripts/tools/disk_scanner.py"]
    assert scheduler_store.load_tasks()[0]["id"] == broken["id"]
