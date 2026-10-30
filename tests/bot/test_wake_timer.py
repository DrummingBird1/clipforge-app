# tests/bot/test_wake_timer.py
#
# utils/bot/wake_timer.py: משימה אחת ב-Task Scheduler ("ClipForge\WakeForNextTask", WakeToRun) כשתי דקות לפני המשימה
# המתוזמנת הבאה - כבוי כברירת מחדל, מתעדכן רק כשהמועד משתנה, ונמחק כשמכבים. schtasks כאן תמיד מזויף; גם בלי זיוף
# CLIPFORGE_NO_SCHTASKS (tests/conftest.py) חוסם קריאה אמיתית.
import datetime
import subprocess

import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.bot import wake_timer as wt

NOW = datetime.datetime(2026, 10, 19, 22, 0)   # יום שני


class FakeSchtasks:
    def __init__(self, returncode=0, stderr=""):
        self.calls, self.returncode, self.stderr, self.xml = [], returncode, stderr, []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if "/XML" in cmd:
            with open(cmd[cmd.index("/XML") + 1], encoding="utf-16") as f:
                self.xml.append(f.read())
        return subprocess.CompletedProcess(cmd, self.returncode, stdout="", stderr=self.stderr)


def _daily(time_str, **extra):
    return {"id": "d", "schedule_type": "daily", "time": time_str, "enabled": True, **extra}


# ---------- מתי המשימה הבאה ----------
def test_next_run_for_daily_weekly_and_interval_tasks():
    assert wt.next_run_after(_daily("23:30"), NOW) == datetime.datetime(2026, 10, 19, 23, 30)
    assert wt.next_run_after(_daily("03:00"), NOW) == datetime.datetime(2026, 10, 20, 3, 0)          # כבר עבר היום -> מחר
    weekly = {"schedule_type": "weekly", "weekday": "sun", "time": "10:00", "enabled": True}
    assert wt.next_run_after(weekly, NOW) == datetime.datetime(2026, 10, 25, 10, 0)
    interval = {"schedule_type": "interval_hours", "interval_hours": 6, "last_run_at": "2026-10-19T20:00:00", "enabled": True}
    assert wt.next_run_after(interval, NOW) == datetime.datetime(2026, 10, 20, 2, 0)
    assert wt.next_run_after({**interval, "last_run_at": None}, NOW) is None       # רצה עכשיו - הלולאה תחשב שוב אחריה
    assert wt.next_run_after(_daily("23:30", enabled=False), NOW) is None


def test_next_wake_is_two_minutes_before_the_nearest_task_and_skips_broken_ones():
    tasks = [_daily("23:30"), _daily("22:40"), {"schedule_type": "interval_hours", "interval_hours": "x", "last_run_at": "bad"}]
    assert wt.next_wake(tasks, NOW) == datetime.datetime(2026, 10, 19, 22, 38)
    assert wt.next_wake([_daily("22:02")], NOW) is None      # קרוב מדי - המחשב ער
    assert wt.next_wake([], NOW) is None


# ---------- הרישום ----------
def test_off_by_default_and_nothing_is_registered(tmp_path):
    fake = FakeSchtasks()
    state = wt.sync([_daily("23:30")], now=NOW, run=fake, path=str(tmp_path / "w.json"))
    assert state["enabled"] is False and state["wake_at"] is None and fake.calls == []


def test_registers_once_updates_on_change_and_deletes_when_off(tmp_path):
    path, fake = str(tmp_path / "w.json"), FakeSchtasks()
    wt.set_enabled(True, [], run=fake, path=path)
    assert fake.calls == []                                   # אין משימות - אין מה לרשום
    state = wt.sync([_daily("23:30")], now=NOW, run=fake, path=path)
    assert state["wake_at"] == "2026-10-19T23:28:00"
    create = fake.calls[-1]
    assert create[:5] == ["schtasks", "/Create", "/TN", wt.TASK_NAME, "/XML"] and create[-1] == "/F"
    assert "<WakeToRun>true</WakeToRun>" in fake.xml[-1] and "<StartBoundary>2026-10-19T23:28:00</StartBoundary>" in fake.xml[-1]
    wt.sync([_daily("23:30")], now=NOW + datetime.timedelta(seconds=30), run=fake, path=path)
    assert len(fake.calls) == 1                               # אותו מועד - בלי קריאה נוספת
    wt.sync([_daily("23:45")], now=NOW, run=fake, path=path)
    assert len(fake.calls) == 2 and wt.load_state(path)["wake_at"] == "2026-10-19T23:43:00"
    wt.set_enabled(False, [_daily("23:45")], run=fake, path=path)
    assert fake.calls[-1] == ["schtasks", "/Delete", "/TN", wt.TASK_NAME, "/F"] and wt.load_state(path)["wake_at"] is None


def test_a_failed_registration_is_reported_and_retried(tmp_path):
    path = str(tmp_path / "w.json")
    wt.set_enabled(True, [], run=FakeSchtasks(), path=path)
    failing = FakeSchtasks(returncode=1, stderr="ERROR: Access is denied.")
    state = wt.sync([_daily("23:30")], now=NOW, run=failing, path=path)
    assert state["wake_at"] is None and "Access is denied" in state["error"]
    ok = FakeSchtasks()
    assert wt.sync([_daily("23:30")], now=NOW, run=ok, path=path)["error"] == "" and len(ok.calls) == 1


def test_the_real_schtasks_is_blocked_during_tests(tmp_path):
    path = str(tmp_path / "w.json")
    wt.set_enabled(True, [], run=FakeSchtasks(), path=path)
    state = wt.sync([_daily("23:30")], now=NOW, path=path)        # בלי run מזויף
    assert wt.NO_SCHTASKS_ENV in state["error"] and state["wake_at"] is None


def test_windows_wake_timer_setting_is_read_from_powercfg():
    def out(text):
        return lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=text, stderr="")
    assert wt.windows_allows_wake_timers(out("    Current AC Power Setting Index: 0x00000001\n")) is True
    assert wt.windows_allows_wake_timers(out("    Current AC Power Setting Index: 0x00000000\n")) is False
    assert wt.windows_allows_wake_timers(out("Invalid Parameters")) is None


# ---------- API ומסך האבחון ----------
@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(wt, "STATE_PATH", str(tmp_path / "wake_timer.json"))
    monkeypatch.setattr(wt, "windows_allows_wake_timers", lambda run=None: True)
    monkeypatch.setattr(web_app.scheduler_store, "load_tasks", lambda: [_daily("23:59")])
    client = TestClient(app)
    client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
    return client


def test_the_api_toggles_it_and_reports_the_state(api):
    assert api.get("/api/scheduler/wake_timer").json()["enabled"] is False
    data = api.post("/api/scheduler/wake_timer", json={"enabled": True}).json()
    assert data["enabled"] is True and data["task_name"] == wt.TASK_NAME and data["windows_allows"] is True
    assert wt.NO_SCHTASKS_ENV in data["error"]                   # הקריאה האמיתית חסומה בטסטים - ולא נרשם כלום
    assert api.post("/api/scheduler/wake_timer", json={"enabled": False}).json()["enabled"] is False
    assert api.post("/api/scheduler/wake_timer", json={"enabled": True}, headers={"origin": "http://evil.example"}).status_code == 403


def test_diagnostics_shows_off_as_healthy(api):
    from utils.shared import diagnostics
    name, ok, details = diagnostics._check_wake_timers()
    assert ok is True and details
