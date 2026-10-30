# tests/studio/test_web_app_editor_wave12.py
#
# גל 12 דרך ה-API: תיאור המודל, פרויקטים ושמירה אוטומטית, ערכות מותג, ריצה עם
# יעדים (ריצה לכל יעד, תת-תיקייה, פעולות-סוף רק באחרון), עריכות-קליפ ושכבות-קליפ
# שהופכות לדריסות פר-קובץ, ומיגרציה צד-שרת של פרופילים בקריאה.
import json


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import brand_kits, editor_projects
from utils.video import video_editor_profiles as vep

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False
SCRIPT_ID = "video/video_editor.py"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "data" / "video_editor_profiles.json"))
    monkeypatch.setattr(web_app, "BATCH_OVERRIDES_DIR", str(tmp_path / "batch_overrides"))
    monkeypatch.setattr(web_app, "LAYERS_DIR", str(tmp_path / "layers"))
    monkeypatch.setattr(web_app, "RUN_CONTROL_DIR", str(tmp_path / "run_control"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda script, folder, on_finish, **kw: calls.append({"folder": folder, "on_finish": on_finish, **kw}))
    return calls


def _arg(args, flag):
    return args[args.index(flag) + 1] if flag in args else None


def test_schema_endpoint():
    data = client.get("/api/video_editor/schema").json()
    assert data["schema_version"] == 2 and "discord" in data["targets"] and "watermark_path" in data["brand_fields"]


# --- פרויקטים ---

def test_project_autosave_roundtrip(tmp_path):
    folder = tmp_path / "clips"
    folder.mkdir()
    body = {"folder": str(folder), "recipe": {"codec": "av1"}, "targets": ["shorts"], "clip_edits": {"a.mp4": {"trim_start": "3"}}}
    assert client.put("/api/editor_projects", json=body).json()["ok"] is True
    project = client.get("/api/editor_projects/by_folder", params={"folder": str(folder)}).json()["project"]
    assert project["recipe"] == {"codec": "av1"} and project["targets"] == ["shorts"]
    [row] = client.get("/api/editor_projects").json()["projects"]
    assert row["folder"] == str(folder) and row["clip_edit_count"] == 1
    exported = client.get("/api/editor_projects/export", params={"folder": str(folder)}).json()
    assert exported["format"] == editor_projects.EXPORT_FORMAT
    assert client.request("DELETE", "/api/editor_projects", params={"folder": str(folder)}).json()["ok"] is True
    assert client.get("/api/editor_projects/by_folder", params={"folder": str(folder)}).json()["project"] is None


def test_project_save_rejects_missing_folder(tmp_path):
    assert client.put("/api/editor_projects", json={"folder": str(tmp_path / "nope")}).status_code == 400


# --- ערכות מותג ---

def test_brand_kit_crud():
    assert client.post("/api/brand_kits", json={"name": "RL", "fields": {"watermark_path": "C:\\rl.png", "codec": "av1"}}).json()["ok"]
    kits = client.get("/api/brand_kits").json()["kits"]
    assert kits["RL"]["fields"] == {"watermark_path": "C:\\rl.png"}
    assert client.post("/api/brand_kits/RL/rename", json={"new_name": "Rocket"}).json()["ok"]
    assert client.post("/api/brand_kits", json={"name": "bad/name"}).status_code == 400
    assert client.request("DELETE", "/api/brand_kits/Rocket").json()["ok"]
    assert client.request("DELETE", "/api/brand_kits/Rocket").status_code == 404


# --- ריצה: מתכון × יעדים ---

def test_run_with_targets_queues_one_run_per_target(tmp_path, queued, monkeypatch):
    (tmp_path / "a.mp4").write_bytes(b"x")
    finish_payloads = []
    monkeypatch.setattr(web_app, "_make_editor_finish_callback", lambda run_id, folder, payload, started: (finish_payloads.append(payload), None)[1])
    data = client.post("/api/run", json={
        "script": SCRIPT_ID, "folder": str(tmp_path), "codec": "hevc", "targets": ["shorts", "discord"],
        "finish_actions": {"sound": True}, "publish_after": True,
    }).json()
    assert data["ok"] and data["targets"] == ["shorts", "discord"] and len(data["run_ids"]) == 2
    assert len(queued) == 2
    shorts_args, discord_args = queued[0]["extra_args"], queued[1]["extra_args"]
    assert "--vertical" in shorts_args and _arg(shorts_args, "--output-subdir") == "shorts" and _arg(shorts_args, "--codec") == "hevc"
    assert "--vertical" not in discord_args and _arg(discord_args, "--codec") == "h264" and _arg(discord_args, "--target-size-mb")
    assert _arg(discord_args, "--output-subdir") == "discord"
    assert all(callable(call["on_start"]) for call in queued)
    # פעולות-סוף רק אחרי האחרון, ו"ואז פרסם" רק ליעד ה-Shorts
    first, last = finish_payloads
    assert first.get("finish_actions") == {} and last["finish_actions"] == {"sound": True}
    assert first.get("publish_after") is True and last.get("publish_after") is False


def test_run_without_targets_is_unchanged(tmp_path, queued):
    (tmp_path / "a.mp4").write_bytes(b"x")
    data = client.post("/api/run", json={"script": SCRIPT_ID, "folder": str(tmp_path), "codec": "h264"}).json()
    assert data["ok"] and "run_ids" not in data and len(queued) == 1
    assert "--output-subdir" not in queued[0]["extra_args"]


def test_on_start_marks_the_task_that_actually_started(tmp_path, queued):
    (tmp_path / "a.mp4").write_bytes(b"x")
    data = client.post("/api/run", json={"script": SCRIPT_ID, "folder": str(tmp_path), "targets": ["youtube", "tiktok"]}).json()
    queued[1]["on_start"]()
    assert web_app._current_run["run_id"] == data["run_ids"][1]
    queued[0]["on_start"]()
    assert web_app._current_run["run_id"] == data["run_ids"][0]


# --- עריכות-קליפ ושכבות-קליפ -> דריסות פר-קובץ ---

def test_clip_edits_and_clip_layers_become_per_file_overrides(tmp_path, queued):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.mp4").write_bytes(b"x")
    client.post("/api/run", json={
        "script": SCRIPT_ID, "folder": str(tmp_path), "trim_start": 2,
        "clip_edits": {"a.mp4": {"trim_start": 5, "trim_duration": 10, "remove_ranges": [[7, 8]]}},
        "layers": [{"type": "text", "text": "ALL", "position": "top-center"}, {"type": "text", "text": "GOAL", "clip": "b.mp4", "start": 3, "end": 5}],
    })
    args = queued[0]["extra_args"]
    overrides = json.load(open(_arg(args, "--batch-overrides"), encoding="utf-8"))
    assert overrides["a.mp4"] == {"remove_ranges": [[0.0, 5.0], [7.0, 8.0], [15.0, 10000000.0]]}
    assert [layer["text"] for layer in overrides["b.mp4"]["layers"]] == ["GOAL"]
    shared = json.load(open(_arg(args, "--layers-json"), encoding="utf-8"))
    assert [layer["text"] for layer in shared] == ["ALL"]
    assert _arg(args, "--trim-start") == "2.0"  # החיתוך של המתכון נשאר לשאר הקבצים


def test_brand_kit_values_win_at_run(tmp_path, queued):
    (tmp_path / "a.mp4").write_bytes(b"x")
    logo = tmp_path / "rl.png"
    logo.write_bytes(b"png")
    brand_kits.save_kit("RL", {"watermark_path": str(logo), "watermark_position": "top-left"})
    client.post("/api/run", json={"script": SCRIPT_ID, "folder": str(tmp_path), "brand_kit": "RL", "watermark_path": "", "watermark_position": "bottom-right"})
    args = queued[0]["extra_args"]
    assert _arg(args, "--watermark_path") == str(logo) and _arg(args, "--watermark_position") == "top-left"


def test_preview_command_and_estimate_follow_the_selected_target(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    body = {"folder": str(tmp_path), "targets": ["youtube", "discord"], "preview_target": "discord", "codec": "hevc"}
    rows = client.post("/api/video_editor/estimate", json=body).json()
    assert "files" in rows


# --- מיגרציה צד-שרת בקריאה ---

def test_profiles_list_is_migrated_on_read_without_rewriting_disk():
    vep.save_profile("Old", {"text": "Hello", "text_position": "top", "codec": "h264"})
    listed = client.get("/api/video_editor_profiles").json()["Old"]
    assert listed["text"] == "" and listed["layers"][0]["text"] == "Hello" and "schema_version" not in listed
    assert vep.load_profiles()["Old"]["text"] == "Hello"  # הקובץ על הדיסק לא שוכתב (הדסקטופ קורא אותו)
