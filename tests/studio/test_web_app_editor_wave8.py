# tests/studio/test_web_app_editor_wave8.py
#
# גל 8 של 102-ההצעות - ריצה, אוטומציה ואינטגרציה: ריצה->פרסום (90), תזמון מהעורך
# (91), ריצות אחרונות + "הרץ שוב" (92), פעולות סוף-ריצה (93), "תמיד לבדוק" (94),
# השהיה/ביטול קובץ בודד (95) ושינוי סדר תוך ריצה (96). אף טסט כאן לא מכניס את
# המחשב לשינה ולא מפרסם באמת - _put_computer_to_sleep/add_script_task ממופתחים.
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys
import threading
import time


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import editor_runs
from utils.video import run_control as rc
from utils.bot import scheduler_store
from utils.video import video_editor_profiles as vep

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


def _make_clip(path, duration=1, size="320x180", rate=10, source="testsrc"):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-v", "error", "-y", "-f", "lavfi", "-i", f"{source}=duration={duration}:size={size}:rate={rate}",
                    "-pix_fmt", "yuv420p", str(path)], capture_output=True, timeout=180, creationflags=NO_WINDOW_FLAGS, check=True)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "profiles" / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "profiles" / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "profiles" / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app, "RUN_CONTROL_DIR", str(tmp_path / "control"))
    monkeypatch.setattr(web_app, "PUBLISH_BATCHES_DIR", str(tmp_path / "publish"))
    monkeypatch.setattr(web_app, "RUN_MANIFESTS_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(web_app, "LAYERS_DIR", str(tmp_path / "layers"))
    monkeypatch.setattr(scheduler_store, "STORE_PATH", str(tmp_path / "scheduled_tasks.json"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)
    slept = []
    monkeypatch.setattr(web_app, "_put_computer_to_sleep", lambda: slept.append(time.time()))
    monkeypatch.setattr(web_app, "_play_finish_sound", lambda: None)
    monkeypatch.setattr(web_app, "_open_folder_on_host", lambda path: None)
    yield slept
    web_app._cancel_pending_sleep()
    web_app._current_run.update(control_file=None, run_id=None)


def _script_id():
    return next(s["id"] for s in client.get("/api/scripts").json() if s["id"].endswith("video_editor.py"))


# --- /api/run: קובץ-בקרה + היסטוריה ---

def test_editor_run_creates_control_file_and_history_entry(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: captured.append((a, k)))
    folder = tmp_path / "clips"
    folder.mkdir()
    res = client.post("/api/run", json={"script": _script_id(), "folder": str(folder), "codec": "hevc", "ve_profile_name": "Mine"})
    run_id = res.json()["run_id"]
    args = captured[0][1]["extra_args"]
    control = args[args.index("--control-file") + 1]
    assert os.path.dirname(control) == web_app.RUN_CONTROL_DIR
    with open(control, encoding="utf-8") as f:
        assert json.load(f) == {"pause": [], "cancel": [], "priority": []}
    [run] = client.get("/api/video_editor/runs").json()["runs"]
    assert run["id"] == run_id and run["status"] == "running" and run["settings"]["codec"] == "hevc" and run["profile_name"] == "Mine"
    assert os.path.dirname(web_app._editor_runs_path()) == os.path.dirname(vep.PROFILES_PATH)  # לא data/ האמיתית


def test_concat_run_has_no_control_file(tmp_path, monkeypatch):
    captured = []
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: captured.append(k))
    client.post("/api/run", json={"script": _script_id(), "folder": str(tmp_path), "concat_mode": True, "concat_files": ["a.mp4", "b.mp4"]})
    assert "--control-file" not in captured[0]["extra_args"]


# --- items 95/96: endpoints של שליטה בריצה ---

def test_run_control_endpoints(tmp_path, monkeypatch):
    assert client.get("/api/video_editor/run_control").json() == {"active": False, "pause": [], "cancel": [], "priority": []}
    assert client.post("/api/video_editor/run_control", json={"action": "pause", "file": "a.mp4"}).status_code == 404
    control = str(tmp_path / "ctl.json")
    rc.write_state(control, rc.EMPTY_STATE)
    web_app._current_run["control_file"] = control
    monkeypatch.setattr(web_app.worker, "is_running", True)
    assert client.post("/api/video_editor/run_control", json={"action": "pause", "file": "a.mp4"}).json()["pause"] == ["a.mp4"]
    client.post("/api/video_editor/run_control", json={"action": "prioritize", "file": "C:\\x\\c.mp4"})
    state = client.post("/api/video_editor/run_control", json={"action": "cancel", "file": "a.mp4"}).json()
    assert state == {"active": True, "pause": [], "cancel": ["a.mp4"], "priority": ["c.mp4"]}
    assert rc.RunControl(control).action_for("a.mp4") == "cancel"
    assert client.post("/api/video_editor/run_control", json={"action": "explode", "file": "a.mp4"}).status_code == 400
    assert client.post("/api/video_editor/run_control", json={"action": "pause", "file": "a.mp4"}, headers={"origin": "http://evil.example"}).status_code == 403


# --- item 92: היסטוריה + הרץ שוב ---

def test_rerun_uses_stored_settings_folder_and_queue(tmp_path, monkeypatch):
    folder = tmp_path / "clips"
    folder.mkdir()
    run_id = editor_runs.record_start(web_app._editor_runs_path(), str(folder), {
        "codec": "av1", "vertical": True, "only_files": ["b.mp4"], "folder": str(folder), "script": "x",
    }, "Profile")
    captured = []
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: captured.append((a, k)))
    res = client.post(f"/api/video_editor/runs/{run_id}/rerun", json={"publish_after": True, "publish_dry_run": True})
    assert res.status_code == 200, res.text
    (script_path, run_folder, _cb), kwargs = captured[0]
    assert script_path.endswith("video_editor.py") and run_folder == str(folder)
    args = kwargs["extra_args"]
    assert args[args.index("--codec") + 1] == "av1" and "--vertical" in args
    assert json.loads(args[args.index("--only-files") + 1]) == ["b.mp4"]
    runs = client.get("/api/video_editor/runs").json()["runs"]
    assert len(runs) == 2 and runs[0]["profile_name"] == "Profile"  # ההרצה החוזרת נרשמה כריצה חדשה
    assert "publish_after" not in runs[0]["settings"]  # העדפות-ריצה לא נשמרות כ"הגדרות" (לא יפרסמו שוב בשקט)
    assert client.post("/api/video_editor/runs/nope/rerun").status_code == 404
    monkeypatch.setattr(web_app.worker, "is_running", True)
    assert client.post(f"/api/video_editor/runs/{run_id}/rerun").status_code == 409
    shutil.rmtree(folder)
    monkeypatch.setattr(web_app.worker, "is_running", False)
    assert client.post(f"/api/video_editor/runs/{run_id}/rerun").status_code == 400
    assert client.delete(f"/api/video_editor/runs/{run_id}").json() == {"ok": True}
    assert client.delete(f"/api/video_editor/runs/{run_id}").status_code == 404


# --- items 90/93: פעולות סוף-ריצה ---

def _fake_manifest(tmp_path, outputs):
    os.makedirs(web_app.RUN_MANIFESTS_DIR, exist_ok=True)
    path = os.path.join(web_app.RUN_MANIFESTS_DIR, "20260101_000000_1.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"files": [{"source": os.path.basename(o), "status": "created", "output": o} for o in outputs]
                   + [{"source": "bad.mp4", "status": "error"}]}, f)
    return path


def test_finish_callback_publishes_only_this_runs_outputs_and_schedules_sleep(tmp_path, monkeypatch, _isolate):
    slept = _isolate
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    outputs = []
    for name in ("a_edited.mp4", "b_edited.mp4"):
        (out_dir / name).write_bytes(b"video")
        outputs.append(str(out_dir / name))
    (out_dir / "old_already_published.mp4").write_bytes(b"old")
    manifest = _fake_manifest(tmp_path, outputs)
    opened, enqueued, finished = [], [], []
    monkeypatch.setattr(web_app, "_open_folder_on_host", opened.append)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: enqueued.append((a, k)))
    monkeypatch.setattr(web_app, "_on_task_finished", finished.append)
    monkeypatch.setattr(web_app, "SLEEP_COUNTDOWN_SECONDS", 0.05)
    run_id = editor_runs.record_start(web_app._editor_runs_path(), str(tmp_path), {})
    payload = {"publish_after": True, "publish_dry_run": True, "finish_actions": {"open_folder": True, "sound": True, "sleep": True}}
    callback = web_app._make_editor_finish_callback(run_id, str(tmp_path), payload, time.time() - 5)
    callback({"returncode": 0, "result": {"files_created": 2, "errors": 1, "manifest_path": manifest}})
    (script_path, batch_dir, _cb), kwargs = enqueued[0]
    assert script_path == web_app.PUBLISHER_SCRIPT_PATH and kwargs["extra_args"] == ["--dry-run"]
    assert sorted(os.listdir(batch_dir)) == ["a_edited.mp4", "b_edited.mp4"]  # בלי הפלט הישן
    assert opened == [str(out_dir)]
    outcome = finished[0]
    assert outcome["publish_started"] is True and outcome["sleep_seconds"] == 0.05 and outcome["finish_sound"] is True
    assert outcome["editor_run_id"] == run_id
    run = editor_runs.get_run(web_app._editor_runs_path(), run_id)
    assert run["status"] == "success" and run["files_created"] == 2 and run["errors"] == 1 and run["duration_seconds"] >= 5
    deadline = time.time() + 2
    while not slept and time.time() < deadline:
        time.sleep(0.02)
    assert len(slept) == 1


def test_failed_run_never_publishes_or_sleeps_and_sleep_can_be_cancelled(tmp_path, monkeypatch, _isolate):
    slept = _isolate
    enqueued, finished = [], []
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: enqueued.append(a))
    monkeypatch.setattr(web_app, "_on_task_finished", finished.append)
    out = tmp_path / "x.mp4"
    out.write_bytes(b"v")
    manifest = _fake_manifest(tmp_path, [str(out)])
    payload = {"publish_after": True, "finish_actions": {"sleep": True}}
    run_id = editor_runs.record_start(web_app._editor_runs_path(), str(tmp_path), {})
    web_app._make_editor_finish_callback(run_id, str(tmp_path), payload, time.time())({"returncode": 1, "result": {"manifest_path": manifest}})
    assert enqueued == [] and finished[0].get("sleep_seconds") is None
    assert editor_runs.get_run(web_app._editor_runs_path(), run_id)["status"] == "failed"
    # הצלחה עם שינה ארוכה -> ביטול מהממשק לפני שהגיע הזמן
    monkeypatch.setattr(web_app, "SLEEP_COUNTDOWN_SECONDS", 30)
    web_app._make_editor_finish_callback(run_id, str(tmp_path), {"finish_actions": {"sleep": True}}, time.time())({"returncode": 0, "result": {}})
    assert web_app._pending_sleep["timer"] is not None
    assert client.post("/api/video_editor/cancel_sleep").json() == {"cancelled": True}
    assert client.post("/api/video_editor/cancel_sleep").json() == {"cancelled": False}
    assert slept == []


def test_finish_callback_errors_still_deliver_the_finished_message(tmp_path, monkeypatch):
    finished = []
    monkeypatch.setattr(web_app, "_on_task_finished", finished.append)
    monkeypatch.setattr(web_app, "_handle_editor_run_finished", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    web_app._make_editor_finish_callback("x", str(tmp_path), {}, time.time())({"returncode": 0, "result": None})
    assert finished and finished[0]["returncode"] == 0


def test_manifest_outputs_restricted_to_manifest_dir(tmp_path):
    evil = tmp_path / "evil.json"
    evil.write_text(json.dumps({"files": [{"status": "created", "output": str(evil)}]}), encoding="utf-8")
    assert web_app._manifest_created_outputs(str(evil)) == []
    assert web_app._manifest_created_outputs(None) == []


# --- item 91: תזמון מהעורך ---

def test_schedule_from_editor_stores_folder_args_and_persistent_layers(tmp_path):
    folder = tmp_path / "clips"
    folder.mkdir()
    image = tmp_path / "s.png"
    image.write_bytes(b"png")
    res = client.post("/api/video_editor/schedule", json={
        "folder": str(folder), "schedule_type": "weekly", "time_str": "04:30", "weekday": "fri", "label": "לילי",
        "options": {"codec": "hevc", "layers": [{"type": "image", "path": str(image)}], "batch_overrides": {"a.mp4": {"codec": "av1"}}},
    })
    assert res.status_code == 200, res.text
    [task] = scheduler_store.load_tasks()
    assert task["id"] == res.json()["id"] and task["folder"] == str(folder) and task["label"] == "לילי"
    assert (task["schedule_type"], task["time"], task["weekday"]) == ("weekly", "04:30", "fri")
    args = task["extra_args"]
    assert args[args.index("--codec") + 1] == "hevc" and "--batch-overrides" not in args
    layers_file = args[args.index("--layers-json") + 1]
    assert os.path.basename(layers_file).startswith("scheduled_") and os.path.isfile(layers_file)
    assert client.post("/api/video_editor/schedule", json={"folder": str(folder), "time_str": "25:00"}).status_code == 400
    assert client.post("/api/video_editor/schedule", json={"folder": str(tmp_path / "nope")}).status_code == 400
    assert client.post("/api/video_editor/schedule", json={"folder": str(folder), "schedule_type": "hourly"}).status_code == 400


def test_scheduled_editor_task_runs_through_scheduler_with_its_args(tmp_path):
    import datetime

    from utils.bot import scheduler
    task = scheduler_store.add_task(web_app.VIDEO_EDITOR_SCRIPT_PATH, "daily", time_str="00:00", folder=str(tmp_path), extra_args=["--codec", "av1"])
    calls = []

    class FakeWorker:
        def add_script_task(self, script_path, folder, on_finish, concurrency="heavy", extra_args=None):
            calls.append((script_path, folder, extra_args))
    scheduler.check_and_run_due_tasks(FakeWorker(), now=datetime.datetime(2026, 1, 5, 1, 0))
    assert calls == [(task["script_path"], str(tmp_path), ["--codec", "av1"])]


# --- ffmpeg_progress: השהיה/ביטול של תהליך אמיתי (בלי ffmpeg - תהליך Python ארוך) ---

# התהליך שעושה את העבודה מדווח בעצמו את ה-pid שלו ואת הפריים (שורה לכל אחד, לקובץ). sys.executable של venv
# ב-Windows הוא משגר שמריץ את ה-python האמיתי כתהליך-בן - כמו shim של scoop/chocolatey ל-ffmpeg
_FAKE_FFMPEG = (
    "import os, sys, time\n"
    "out = open(sys.argv[1], 'a', encoding='utf-8')\n"
    "out.write('%d\\n' % os.getpid()); out.flush()\n"
    "for i in range(300):\n"
    "    sys.stderr.write('frame=%d\\n' % i); sys.stderr.flush()\n"
    "    out.write('%d\\n' % i); out.flush()\n"
    "    time.sleep(0.05)\n"
)


def test_control_pauses_resumes_and_cancels_a_real_process(tmp_path):
    # סבב ייצוב: קודם הטסט מצא את התהליך בסריקה של כל הילדים של תהליך הטסט (children() ואז cmdline()) - ילד אחר
    # שנסגר בין השתיים (שאריות של טסטים קודמים באותו worker של xdist) זרק NoSuchProcess, ה-thread נפל בשקט, הביטול
    # לא נשלח והטסט נכשל רק תחת עומס. וגם: הוא בדק את המשגר, בזמן שהתהליך האמיתי המשיך לרוץ "בהשהיה".
    psutil = pytest.importorskip("psutil")
    from utils.media import ffmpeg_progress
    progress = tmp_path / "progress.txt"
    actions = {"value": "run"}
    seen = {}

    def _state():
        """(pid, הפריים האחרון) של התהליך שעושה את העבודה - רק שורות שלמות."""
        try:
            lines = progress.read_text(encoding="utf-8").split("\n")[:-1]
        except OSError:
            return None, -1
        return (int(lines[0]) if lines else None), (int(lines[-1]) if len(lines) > 1 else -1)

    def _until(condition, timeout=30.0):
        # המתנה למצב האמיתי (לא לזמן קבוע); התקרה רק כדי שכשל ייכשל ולא ייתקע
        deadline = time.time() + timeout
        while time.time() < deadline:
            value = condition()
            if value:
                return value
            time.sleep(0.02)
        return None

    def _drive():
        try:
            pid = _until(lambda: _state()[0])
            seen["pid"] = pid
            worker = psutil.Process(pid)
            actions["value"] = "pause"
            seen["paused"] = _until(lambda: worker.status() == psutil.STATUS_STOPPED)
            seen["frame_at_pause"] = _state()[1]
            actions["value"] = "run"
            seen["resumed"] = _until(lambda: worker.status() != psutil.STATUS_STOPPED and _state()[1] > seen["frame_at_pause"])
        except Exception as e:  # כשל צריך להיראות כאן, לא כ-"DID NOT RAISE" אחרי 15 שניות
            seen["error"] = repr(e)
        finally:
            actions["value"] = "cancel"
    driver = threading.Thread(target=_drive, daemon=True)
    driver.start()
    with pytest.raises(ffmpeg_progress.FfmpegCancelled):
        ffmpeg_progress.run_ffmpeg_with_progress([sys.executable, "-c", _FAKE_FFMPEG, str(progress)], 300, "fake.mp4", control=lambda: actions["value"])
    driver.join(timeout=30)
    assert "error" not in seen, seen["error"]
    assert seen["paused"], "התהליך שעושה את העבודה לא הושהה"
    assert seen["resumed"], "התהליך לא חזר לרוץ אחרי ההשהיה"
    assert _state()[1] < 299  # הביטול עצר אותו באמצע
    try:
        psutil.Process(seen["pid"]).wait(timeout=10)  # ולא השאיר אותו רץ מאחורי המשגר
    except psutil.NoSuchProcess:
        pass


# --- e2e אמיתי: ביטול/סדר דרך קובץ-הבקרה ---

def _outputs(names):
    return [os.path.join(WORKSPACE_DIR, "studio", "horizontal", f"{n}_edited_horizontal.mp4") for n in names]


def _cleanup(paths, stdout=""):
    from tests.conftest import remove_video_editor_output
    for path in paths:
        remove_video_editor_output(path)
        partial = path + ".partial.mp4"
        if os.path.exists(partial):
            os.remove(partial)
    for line in stdout.splitlines():
        if line.startswith("RUN_MANIFEST: "):
            manifest = line[len("RUN_MANIFEST: "):].strip()
            if os.path.exists(manifest):
                os.remove(manifest)


@needs_ffmpeg
def test_e2e_control_file_cancels_and_reorders_before_start(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    for name in ("w8a", "w8b", "w8c"):
        _make_clip(folder / f"{name}.mp4")
    control = str(tmp_path / "ctl.json")
    rc.write_state(control, {"cancel": ["w8b.mp4"], "priority": ["w8c.mp4"]})
    paths = _outputs(["w8a", "w8b", "w8c"])
    _cleanup(paths)
    stdout = ""
    try:
        result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(folder), "--force", "--control-file", control],
                                cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=240)
        stdout = result.stdout
        parsed = json.loads(next(ln for ln in stdout.splitlines() if ln.startswith("RESULT: "))[len("RESULT: "):])
        assert parsed["files_created"] == 2 and parsed["cancelled"] == 1, stdout
        approved = [ln for ln in stdout.splitlines() if ln.startswith("[APPROVED]")]
        assert "w8c" in approved[0] and "w8a" in approved[1]  # c קודם ל-a (עדיפות)
        assert "[CANCELLED] w8b.mp4" in stdout and not os.path.exists(paths[1])
        with open(parsed["manifest_path"], encoding="utf-8") as f:
            statuses = {r["source"]: r["status"] for r in json.load(f)["files"]}
        assert statuses["w8b.mp4"] == "cancelled"
    finally:
        _cleanup(paths, stdout)


@needs_ffmpeg
def test_e2e_cancel_mid_encode_removes_partial_and_continues(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    _make_clip(folder / "w8long.mp4", duration=40, size="1280x720", rate=30, source="testsrc2")
    _make_clip(folder / "w8short.mp4")
    control = str(tmp_path / "ctl.json")
    rc.write_state(control, {"priority": ["w8long.mp4"]})
    paths = _outputs(["w8long", "w8short"])
    _cleanup(paths)
    stdout = ""
    try:
        proc = subprocess.Popen([sys.executable, SCRIPT, "--input_dir", str(folder), "--force", "--control-file", control],
                                cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        partial = paths[0] + ".partial.mp4"
        deadline = time.time() + 60
        while time.time() < deadline and not os.path.exists(partial):
            time.sleep(0.05)
        assert os.path.exists(partial), "הקידוד של הקובץ הארוך לא התחיל"
        rc.write_state(control, {"cancel": ["w8long.mp4"]})
        stdout, _ = proc.communicate(timeout=180)
        assert "[CANCELLED] w8long.mp4: בוטל באמצע הקידוד." in stdout, stdout
        assert not os.path.exists(paths[0]) and not os.path.exists(partial)
        assert os.path.exists(paths[1])  # הקובץ הבא עדיין רונדר
    finally:
        _cleanup(paths, stdout)


# --- דפדפן אמיתי ---

def test_browser_recent_runs_load_and_delete(editor_page, tmp_path):
    folder = tmp_path / "clips"
    folder.mkdir()
    run_id = editor_runs.record_start(web_app._editor_runs_path(), str(folder), {"codec": "av1", "vertical": True}, "Saved")
    editor_runs.record_finish(web_app._editor_runs_path(), run_id, True, {"files_created": 4, "errors": 1}, 75)
    page = editor_page
    page.evaluate("() => { document.querySelector('[data-cat=runs]').open = true; return loadVeRuns(); }")
    row = page.locator(f"#veRunsList .ve-run-row[data-run-id='{run_id}']")
    assert "4 נוצרו · 1 נכשלו" in row.inner_text() and "✅" in row.inner_text()
    row.locator("button", has_text="טען").click()
    assert page.evaluate("() => [document.getElementById('veCodec').value, document.getElementById('veVertical').checked, state.folder]") == ["av1", True, str(folder)]
    row.locator("button", has_text="✕").click()
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => !document.querySelector('#veRunsList .ve-run-row')")
    assert editor_runs.load_runs(web_app._editor_runs_path()) == []


def test_browser_schedule_dialog_creates_task(editor_page, tmp_path):
    page = editor_page
    page.evaluate("(folder) => { state.folder = folder; document.getElementById('veCodec').value = 'hevc'; }", str(tmp_path))
    page.click("#veRunModeBtn")  # גל 27: "תזמן ריצה" בתפריט ההרצה ▾
    page.click("#veScheduleBtn")
    page.select_option("#veScheduleType", "interval_hours")
    assert page.is_hidden("#veScheduleTime") and page.is_visible("#veScheduleHours")
    page.fill("#veScheduleHours", "6")
    page.fill("#veScheduleLabel", "כל 6 שעות")
    page.click("#veScheduleModalBg button.btn-run")
    page.wait_for_function("() => document.getElementById('veScheduleStatus').textContent.includes('נוסף')")
    [task] = scheduler_store.load_tasks()
    assert (task["schedule_type"], task["interval_hours"], task["label"], task["folder"]) == ("interval_hours", 6, "כל 6 שעות", str(tmp_path))
    assert task["extra_args"][task["extra_args"].index("--codec") + 1] == "hevc"


def test_browser_always_validate_blocks_run_until_confirmed(editor_page, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: calls.append(a))
    page = editor_page
    page.evaluate("(folder) => { state.folder = folder; document.querySelector('[data-cat=runs]').open = true; }", str(tmp_path))  # תיקייה בלי וידאו -> הבדיקה מחזירה בעיה
    page.click("#veRunModeBtn")  # גל 10: "תמיד לבדוק" בתפריט ▾ של כפתור ההרצה
    page.check("#veAlwaysValidate")
    assert page.evaluate("() => _veLoadPref('runPref:veAlwaysValidate', false)") is True
    page.evaluate("() => { runScript(); }")
    page.wait_for_selector("#veConfirmModalBg.show")
    assert "הבדיקה מצאה בעיות" in page.inner_text("#veConfirmMessage")
    page.click("#veConfirmCancelBtn")
    page.wait_for_timeout(300)
    assert calls == []
    page.evaluate("() => { runScript(); }")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => state.running === true")
    assert len(calls) == 1


def test_browser_run_control_panel_actions(editor_page, tmp_path, monkeypatch):
    control = str(tmp_path / "ctl.json")
    rc.write_state(control, rc.EMPTY_STATE)
    web_app._current_run["control_file"] = control
    monkeypatch.setattr(web_app.worker, "is_running", True)
    page = editor_page
    page.evaluate("""() => {
      _veFileProgress = {"live.mp4": 40};
      _veQueueState = [{name: "live.mp4", selected: true}, {name: "next1.mp4", selected: true}, {name: "next2.mp4", selected: true}];
      _veStartRunControl(); toggleVeRunControl(true);
    }""")
    page.wait_for_selector("#veRunControlActive .ve-rc-row")
    page.click("#veRunControlActive button:has-text('השהה')")
    page.wait_for_selector("#veRunControlActive .ve-rc-row.paused")
    assert rc.RunControl(control).action_for("live.mp4") == "pause"
    page.click("#veRunControlPending .ve-rc-row:has-text('next2.mp4') button:has-text('הבא בתור')")
    page.wait_for_function("() => document.querySelector('#veRunControlPending .ve-rc-row .ve-rc-name').textContent.includes('next2.mp4')")
    assert rc.RunControl(control).priority() == ["next2.mp4"]
    page.click("#veRunControlActive button:has-text('בטל')")
    page.click("#veConfirmOkBtn")
    page.wait_for_selector("#veRunControlActive .ve-rc-row.cancelled")
    assert rc.RunControl(control).action_for("live.mp4") == "cancel"
    page.evaluate("() => _veOnRunFinished({})")
    assert page.is_hidden("#veRunControlBtn")
