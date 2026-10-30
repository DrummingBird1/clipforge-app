# tests/studio/test_run_control_wave8.py
#
# גל 8 של 102-ההצעות - לוגיקה טהורה: קובץ-בקרה לריצה (השהיה/ביטול/עדיפות לקובץ
# בודד, items 95-96), תזמון משימות דינמי (הבאה נבחרת רק כשמתפנה worker), והיסטוריית
# ריצות העורך (item 92).
import json
import os
import threading
import time


import pytest

from utils.video import editor_runs
from utils.video import run_control as rc


def test_apply_action_transitions():
    state = rc.normalize_state(None)
    state = rc.apply_action(state, "pause", "C:\\clips\\a.mp4")
    assert state["pause"] == ["a.mp4"]
    state = rc.apply_action(state, "pause", "a.mp4")
    assert state["pause"] == ["a.mp4"]  # בלי כפילויות
    state = rc.apply_action(state, "cancel", "a.mp4")
    assert state["cancel"] == ["a.mp4"] and state["pause"] == []  # ביטול גובר על השהיה
    state = rc.apply_action(state, "prioritize", "b.mp4")
    state = rc.apply_action(state, "prioritize", "c.mp4")
    assert state["priority"] == ["c.mp4", "b.mp4"]
    state = rc.apply_action(state, "prioritize", "b.mp4")
    assert state["priority"] == ["b.mp4", "c.mp4"]
    state = rc.apply_action(state, "unprioritize", "b.mp4")
    assert state["priority"] == ["c.mp4"]
    state = rc.apply_action(rc.apply_action(state, "pause", "d.mp4"), "resume", "d.mp4")
    assert state["pause"] == []
    with pytest.raises(ValueError):
        rc.apply_action(state, "explode", "a.mp4")


def test_normalize_state_is_defensive():
    assert rc.normalize_state("junk") == {"pause": [], "cancel": [], "priority": []}
    assert rc.normalize_state({"pause": ["x/../../y.mp4", "y.mp4", ""], "cancel": "nope"}) == {"pause": ["y.mp4"], "cancel": [], "priority": []}


def test_next_task_index():
    assert rc.next_task_index(["a", "b", "c"], []) == 0
    assert rc.next_task_index(["a", "b", "c"], ["c"]) == 2
    assert rc.next_task_index(["a", "b", "c"], ["zzz", "b", "c"]) == 1
    assert rc.next_task_index(["a"], ["b"]) == 0


def test_run_control_reads_file_and_survives_partial_writes(tmp_path):
    path = tmp_path / "ctl.json"
    control = rc.RunControl(str(path))
    assert control.action_for("a.mp4") == "run"  # אין קובץ עדיין
    rc.write_state(str(path), {"pause": ["a.mp4"], "cancel": ["b.mp4"], "priority": ["c.mp4"]})
    assert control.action_for("C:/x/a.mp4") == "pause" and control.action_for("b.mp4") == "cancel"
    assert control.priority() == ["c.mp4"]
    time.sleep(0.02)
    path.write_text("{ half written", encoding="utf-8")
    os.utime(path, None)
    assert control.action_for("a.mp4") == "pause"  # נשאר עם המצב התקין האחרון


def test_wait_while_paused_returns_when_resumed_or_cancelled(tmp_path):
    path = str(tmp_path / "ctl.json")
    rc.write_state(path, {"pause": ["a.mp4"]})
    control = rc.RunControl(path)
    announced = []

    def _resume_later():
        time.sleep(0.15)
        rc.write_state(path, {"pause": []})
    threading.Thread(target=_resume_later, daemon=True).start()
    assert control.wait_while_paused("a.mp4", poll_seconds=0.02, on_pause=lambda: announced.append(1)) == "run"
    assert announced == [1]
    rc.write_state(path, {"pause": ["b.mp4"], "cancel": ["b.mp4"]})
    assert control.wait_while_paused("b.mp4", poll_seconds=0.02) == "cancel"


def test_run_tasks_sequential_respects_dynamic_priority():
    order = []
    priority = []

    def run_one(name):
        order.append(name)
        if name == "a":
            priority.append("d")  # "תוך ריצה": d מקודם אחרי שa התחיל
    rc.run_tasks([("a",), ("b",), ("c",), ("d",)], run_one, 1, pick=lambda pending: rc.next_task_index([t[0] for t in pending], priority))
    assert order == ["a", "d", "b", "c"]


def test_run_tasks_parallel_runs_all_and_limits_concurrency():
    active, peak, done = [0], [0], []
    lock = threading.Lock()

    def run_one(name):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.03)
        with lock:
            active[0] -= 1
            done.append(name)
    rc.run_tasks([(str(i),) for i in range(8)], run_one, 3)
    assert sorted(done, key=int) == [str(i) for i in range(8)] and peak[0] <= 3


def test_run_tasks_parallel_propagates_errors_and_stops_taking_new_tasks():
    started = []

    def run_one(name):
        started.append(name)
        if name == "0":
            raise RuntimeError("boom")
        time.sleep(0.05)
    with pytest.raises(RuntimeError, match="boom"):
        rc.run_tasks([(str(i),) for i in range(20)], run_one, 2)
    assert len(started) < 20


# --- היסטוריית ריצות ---

def test_editor_runs_record_finish_and_cap(tmp_path, monkeypatch):
    path = str(tmp_path / "runs.json")
    run_id = editor_runs.record_start(path, "C:/clips", {"codec": "hevc", "folder": "C:/clips", "script": "x", "only_files": ["a.mp4"]}, "Mine")
    [run] = editor_runs.load_runs(path)
    assert run["status"] == "running" and run["settings"] == {"codec": "hevc"} and run["only_files"] == ["a.mp4"]
    editor_runs.record_finish(path, run_id, True, {"files_created": 3, "errors": 1, "manifest_path": "m.json", "noise": 1}, 12.345)
    run = editor_runs.get_run(path, run_id)
    assert run["status"] == "success" and run["files_created"] == 3 and run["duration_seconds"] == 12.3 and "noise" not in run
    monkeypatch.setattr(editor_runs, "MAX_RUNS", 3)
    for i in range(5):
        editor_runs.record_start(path, f"C:/f{i}", {})
    assert [r["folder"] for r in editor_runs.load_runs(path)] == ["C:/f4", "C:/f3", "C:/f2"]
    assert editor_runs.delete_run(path, editor_runs.load_runs(path)[0]["id"]) is True
    assert editor_runs.delete_run(path, "nope") is False
    with open(path, encoding="utf-8") as f:
        assert len(json.load(f)) == 2


def test_editor_runs_load_is_defensive(tmp_path):
    path = tmp_path / "runs.json"
    assert editor_runs.load_runs(str(path)) == []
    path.write_text("not json", encoding="utf-8")
    assert editor_runs.load_runs(str(path)) == []
    path.write_text(json.dumps([{"no": "id"}, {"id": "x"}, "junk"]), encoding="utf-8")
    assert editor_runs.load_runs(str(path)) == [{"id": "x"}]
