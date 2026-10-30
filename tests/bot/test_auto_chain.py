# tests/bot/test_auto_chain.py
#
# גל 32: שרשור מלא מ-OBS/תיקיית לכידה ועד פרסום - המאזין מדפיס שורת EVENT אחרי שהעתיק קליפ
# ל-Import, worker.py מעביר אותה ל-handler, והשרת עורך בסגנון שמור ו/או מפרסם לפי ההגדרות.
import json
import os
import threading


import pytest

from my_scripts.stream import capture_folder_watcher
from utils.media import auto_chain
from utils.shared.worker import TaskWorker


def _clip(tmp_path, name="replay 2026-10-09.mp4"):
    path = tmp_path / "import" / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"video")
    return str(path)


STYLE = {"schema_version": 2, "eq_contrast": 1.15, "targets": ["shorts"], "only_files": ["old.mp4"],
         "clip_edits": {"old.mp4": {}}, "publish_after": False, "finish_actions": {"sound": True}}


# --- התכנון (לוגיקה טהורה) ---

def test_plan_is_off_by_default_so_watchers_only_copy_as_before(tmp_path):
    assert auto_chain.plan({}, _clip(tmp_path), {"s": STYLE}) == {"action": None, "reason": "off"}
    assert auto_chain.settings_from({"auto_chain": "nonsense"})["mode"] == "off"


def test_plan_edit_applies_the_style_to_the_new_clip_only(tmp_path):
    clip = _clip(tmp_path)
    plan = auto_chain.plan({"auto_chain": "edit_publish", "auto_chain_profile": "s", "auto_chain_dry_run": True}, clip, {"s": STYLE})

    assert plan["action"] == "edit" and plan["folder"] == os.path.dirname(clip) and plan["publish"] is True
    payload = plan["payload"]
    assert payload["only_files"] == ["replay 2026-10-09.mp4"]
    assert payload["eq_contrast"] == 1.15 and payload["targets"] == ["shorts"]
    assert payload["publish_after"] is True and payload["publish_dry_run"] is True and payload["ve_profile_name"] == "s"
    # שדות של ריצה/קובץ אחרים לא עוברים מהסגנון לקליפ החדש
    for key in ("schema_version", "clip_edits", "finish_actions"):
        assert key not in payload
    assert auto_chain.plan({"auto_chain": "edit", "auto_chain_profile": "s"}, clip, {"s": STYLE})["payload"]["publish_after"] is False


def test_plan_reports_a_missing_style_and_ignores_non_video_files(tmp_path):
    clip = _clip(tmp_path)
    plan = auto_chain.plan({"auto_chain": "edit", "auto_chain_profile": "gone"}, clip, {"s": STYLE})
    assert plan == {"action": None, "reason": "no_style", "profile": "gone"}
    assert "\"gone\" לא נמצא" in auto_chain.describe(plan, "a.mp4")
    assert auto_chain.plan({"auto_chain": "publish"}, _clip(tmp_path, "notes.txt"), {})["reason"] == "missing"
    assert auto_chain.plan({"auto_chain": "publish"}, str(tmp_path / "nope.mp4"), {})["reason"] == "missing"


def test_clip_ready_line_is_one_json_event_line(tmp_path):
    line = auto_chain.clip_ready_line(str(tmp_path / "a b.mp4"), "obs")
    assert line.startswith("EVENT: ") and "\n" not in line
    assert json.loads(line[len("EVENT: "):]) == {"type": "clip_ready", "path": str(tmp_path / "a b.mp4"), "source": "obs"}


# --- worker.py: שורות EVENT ---

def test_worker_dispatches_event_lines_to_the_handler_and_hides_them():
    worker = TaskWorker()
    seen = []
    worker.on_event("clip_ready", seen.append)

    worker._handle_output_line('EVENT: {"type": "clip_ready", "path": "C:/a.mp4"}', "super_streamer.py")
    worker._handle_output_line('EVENT: {"type": "other"}', "super_streamer.py")
    worker._handle_output_line("EVENT: not json", "super_streamer.py")

    assert seen == [{"type": "clip_ready", "path": "C:/a.mp4", "script": "super_streamer.py"}]
    assert worker.log_queue.empty()  # שורת האירוע עצמה לא מציפה את הקונסולה


def test_worker_survives_a_failing_event_handler():
    worker = TaskWorker()

    def broken(_event):
        raise RuntimeError("boom")

    worker.on_event("clip_ready", broken)
    worker._handle_output_line('EVENT: {"type": "clip_ready"}', "super_streamer.py")

    text, tone = worker.log_queue.get_nowait()
    assert "boom" in text and tone == "red"


def test_event_from_a_real_running_script_reaches_the_handler_mid_run(tmp_path):
    # אירוע מגיע באמצע ריצה ארוכה (מאזין לא מסתיים), לא רק בסוף
    script = tmp_path / "listener.py"
    script.write_text(
        "import sys, time\n"
        "print('EVENT: {\"type\": \"clip_ready\", \"path\": \"x.mp4\"}', flush=True)\n"
        "time.sleep(1)\n", encoding="utf-8")
    worker = TaskWorker()
    got = threading.Event()
    finished = threading.Event()
    worker.on_event("clip_ready", lambda event: got.set() if not finished.is_set() else None)

    worker.add_script_task(str(script), str(tmp_path), lambda _outcome: finished.set(), concurrency="light")

    assert got.wait(15) and not finished.is_set()
    assert finished.wait(15)


def test_capture_folder_watcher_announces_each_copied_clip(tmp_path, monkeypatch, capsys):
    watch_dir, target_dir = tmp_path / "capture", tmp_path / "import"
    watch_dir.mkdir()
    target_dir.mkdir()
    (watch_dir / "clip.mp4").write_bytes(b"stable")
    calls = {"n": 0}

    def fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(capture_folder_watcher.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        capture_folder_watcher.watch(str(watch_dir), str(target_dir), poll_interval=0)

    events = [json.loads(line[len("EVENT: "):]) for line in capsys.readouterr().out.splitlines() if line.startswith("EVENT: ")]
    assert events == [{"type": "clip_ready", "path": str(target_dir / "clip.mp4"), "source": "folder"}]


# --- השרת: מה קורה כשקליפ נכנס ---

@pytest.fixture
def chain_env(tmp_path, monkeypatch):
    from entrypoints import web_app
    env = {"settings": {}, "runs": [], "tasks": [], "web_app": web_app}
    monkeypatch.setattr(web_app, "_load_rocket_settings", lambda: env["settings"])
    monkeypatch.setattr(web_app.video_editor_profiles, "load_profiles", lambda: {"Shorts": dict(STYLE)})
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: env["runs"].append((script, folder, payload, host)) or {"ok": True})
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda script, folder, *_a, **kw: env["tasks"].append((script, folder, kw)))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *_a, **_kw: None)
    monkeypatch.setattr(web_app, "_auto_chain_recent", [])
    return env


def test_server_edits_a_new_obs_clip_with_the_saved_style_then_publishes(tmp_path, chain_env):
    web_app = chain_env["web_app"]
    chain_env["settings"] = {"auto_chain": "edit_publish", "auto_chain_profile": "Shorts"}
    clip = _clip(tmp_path)

    web_app.worker._handle_output_line(auto_chain.clip_ready_line(clip, "obs"), "super_streamer.py")

    [(script, folder, payload, host)] = chain_env["runs"]
    assert script == web_app.VIDEO_EDITOR_SCRIPT_PATH and folder == os.path.dirname(clip) and host == "auto_chain"
    assert payload["only_files"] == [os.path.basename(clip)] and payload["publish_after"] is True
    [entry] = web_app._auto_chain_recent
    assert entry["file"] == os.path.basename(clip) and entry["action"] == "edit" and "ואז לפרסום" in entry["text"]


def test_server_publishes_a_new_clip_directly_in_its_own_batch(tmp_path, chain_env):
    web_app = chain_env["web_app"]
    chain_env["settings"] = {"auto_chain": "publish", "auto_chain_dry_run": True}
    _clip(tmp_path, "old.mp4")
    clip = _clip(tmp_path)

    web_app.worker._handle_output_line(auto_chain.clip_ready_line(clip, "folder"), "super_streamer.py")

    [(script, batch, kwargs)] = chain_env["tasks"]
    assert script == web_app.PUBLISHER_SCRIPT_PATH and kwargs["extra_args"] == ["--dry-run"]
    # רק הקליפ החדש באצווה - Rocket Shorts מעבד את כל התיקייה, ו-Import מכיל גם קליפים ישנים
    assert os.listdir(batch) == [os.path.basename(clip)]
    assert chain_env["runs"] == []


def test_server_does_nothing_when_off_or_when_another_script_prints_the_event(tmp_path, chain_env):
    web_app = chain_env["web_app"]
    clip = _clip(tmp_path)
    web_app.worker._handle_output_line(auto_chain.clip_ready_line(clip, "obs"), "super_streamer.py")  # off
    chain_env["settings"] = {"auto_chain": "publish"}
    web_app.worker._handle_output_line(auto_chain.clip_ready_line(clip, "obs"), "some_other_script.py")

    assert chain_env["runs"] == [] and chain_env["tasks"] == [] and web_app._auto_chain_recent == []


def test_rocket_settings_round_trip_the_chain_fields(chain_env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    web_app = chain_env["web_app"]
    saved = {}
    monkeypatch.setattr(web_app, "_load_rocket_settings", lambda: dict(saved))
    monkeypatch.setattr(web_app, "_save_rocket_settings", lambda data: saved.update(data))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    client = TestClient(web_app.app)
    client.cookies.set(web_app._AUTH_COOKIE_NAME, web_app.ACCESS_TOKEN)

    before = client.get("/api/rocket_settings").json()
    assert (before["auto_chain"], before["auto_chain_profile"], before["auto_chain_dry_run"], before["seo_ai"]) == ("off", "", False, True)
    assert client.post("/api/rocket_settings", json={"auto_chain": "edit", "auto_chain_profile": " Shorts ", "auto_chain_dry_run": True,
                                                     "seo_ai": False}).status_code == 200
    after = client.get("/api/rocket_settings").json()
    assert (after["auto_chain"], after["auto_chain_profile"], after["auto_chain_dry_run"], after["seo_ai"]) == ("edit", "Shorts", True, False)
    assert client.get("/api/auto_chain/recent").json() == {"recent": []}
