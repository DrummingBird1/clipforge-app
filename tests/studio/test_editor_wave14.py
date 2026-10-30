# tests/studio/test_editor_wave14.py
#
# גל 14: שגיאות עם פתרון (utils/video/editor_errors.py), keyframes לשכבות (ביטויי ffmpeg
# ומול ffmpeg אמיתי), תור רינדור עם קדימות/השהיה/המתנה-כשעסוק (utils/shared/worker.py),
# ו-endpoints: תור, הסבר שגיאה, manifest מוסבר, חילופי-סצנה ועוצמה (LUFS).
import json
import os
import shutil
import subprocess
import threading
import time


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import editor_errors, video_editor_layers as vel
from utils.video import video_editor_profiles as vep
from utils.shared.worker import RenderQueue

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "data" / "video_editor_profiles.json"))
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "previews"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


# --- שגיאות עם פתרון ---

@pytest.mark.parametrize("reason, expected_id, first_action", [
    ("[h264_nvenc @ 0x1] OpenEncodeSessionEx failed: out of memory (10)", "nvenc_busy", "retry_serial"),
    ("OSError: [Errno 28] No space left on device", "disk_full", "open_folder"),
    ("PermissionError: [WinError 32] The process cannot access the file because it is being used by another process", "file_locked", "retry"),
    ("[Parsed_lut3d_0] Failed to open file look.cube", "bad_lut", "clear_field"),
    ("moov atom not found", "corrupt_input", "skip"),
    ("Stream specifier ':a' in filtergraph description matches no streams.", "no_audio", "clear_field"),
    ("Error initializing complex filters. Invalid argument", "filter_graph", "validate"),
    ("something nobody expected", "unknown", "retry"),
])
def test_explain_error_maps_reasons_to_fixes(reason, expected_id, first_action):
    explanation = editor_errors.explain_error(reason)
    assert explanation["id"] == expected_id
    assert explanation["actions"][0]["id"] == first_action and explanation["title"]


def test_clear_field_actions_carry_the_field():
    [action] = [a for a in editor_errors.explain_error("Failed to open file x.cube lut3d")["actions"] if a["id"] == "clear_field"]
    assert action["field"] == "lut_path" and "LUT" in action["label"]


def test_annotate_manifest_only_explains_failures():
    manifest = {"files": [{"status": "created"}, {"status": "error", "reason": "No space left on device"}, {"status": "cancelled"}]}
    editor_errors.annotate_manifest(manifest)
    assert "explanation" not in manifest["files"][0]
    assert manifest["files"][1]["explanation"]["id"] == "disk_full" and manifest["files"][2]["explanation"]["id"] == "cancelled"


def test_run_manifest_endpoint_adds_explanations(tmp_path, monkeypatch):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    monkeypatch.setattr(web_app, "RUN_MANIFESTS_DIR", str(manifests))
    path = manifests / "20260101_1.json"
    path.write_text(json.dumps({"files": [{"source": "a.mp4", "status": "error", "reason": "OpenEncodeSessionEx failed"}]}), encoding="utf-8")
    data = client.get("/api/video_editor/run_manifest", params={"path": str(path)}).json()
    assert data["files"][0]["explanation"]["id"] == "nvenc_busy"
    assert client.post("/api/video_editor/explain_error", json={"reason": "disk full"}).json()["id"] == "disk_full"


# --- keyframes ---

def test_sanitize_keyframes_sorts_clamps_and_needs_two():
    frames = vel.sanitize_keyframes([{"t": 3, "x": 1.5}, {"t": 1, "x": 0.2, "opacity": -1}, {"bad": 1}])
    assert frames == [{"t": 1.0, "x": 0.2, "opacity": 0.0}, {"t": 3.0, "x": 1.0}]
    assert vel.sanitize_keyframes([{"t": 1, "x": 0.5}]) == []


def test_keyframe_expr_linear_and_ease():
    frames = [{"t": 0, "x": 0.1}, {"t": 2, "x": 0.9}]
    linear = vel.keyframe_expr(frames, "x")
    assert linear == "if(lt(t,0),0.1,if(lt(t,2),0.1+(0.8)*((t-0)/2),0.9))"
    ease = vel.keyframe_expr(frames, "x", "ease")
    assert "*(3-2*(" in ease
    assert vel.keyframe_expr(frames, "opacity") is None


def test_text_layer_with_keyframes_animates_position_opacity_and_size():
    [layer] = vel.sanitize_layers([{"type": "text", "text": "GO", "font_size": 40, "keyframes": [
        {"t": 0, "x": 0.2, "y": 0.5, "opacity": 0, "scale": 1}, {"t": 1, "x": 0.8, "y": 0.5, "opacity": 1, "scale": 2}], "easing": "ease"}])
    [drawtext] = vel.build_text_layer_filters(layer, ["C:/t.txt"])
    assert "x='max(0,min(w-text_w,w*(if(lt(t,0)" in drawtext
    assert "fontsize='40*(if(lt(t,0),1," in drawtext
    assert "alpha='if(lt(t,0),0," in drawtext


def test_image_layer_keyframes_move_the_overlay(tmp_path):
    image = tmp_path / "s.png"
    image.write_bytes(b"x")
    layers = vel.sanitize_layers([{"type": "image", "path": str(image), "keyframes": [{"t": 0, "x": 0.1, "y": 0.1}, {"t": 2, "x": 0.9, "y": 0.9}]}])
    parts, _ = vel.build_layer_parts("base", layers, {}, {0: 2}, 1920, 30, 10.0)
    assert any("overlay=x='max(0,min(W-w,W*(if(lt(t,0),0.1," in p for p in parts)


@needs_ffmpeg
def test_keyframed_text_renders_with_real_ffmpeg(tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    [layer] = vel.sanitize_layers([{"type": "text", "text": "GO", "font_size": 30, "keyframes": [
        {"t": 0, "x": 0.2, "y": 0.3, "opacity": 0.2, "scale": 1}, {"t": 1, "x": 0.8, "y": 0.7, "opacity": 1, "scale": 2}], "easing": "ease"}])
    text_file = tmp_path / "t.txt"
    text_file.write_text("GO", encoding="utf-8")
    chain = ",".join(vel.build_text_layer_filters(layer, [str(text_file)]))
    result = subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=black:size=320x180:duration=1.5:rate=10", "-vf", chain,
                             str(tmp_path / "out.mp4")], capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS, cwd=str(tmp_path))
    assert result.returncode == 0, result.stderr[-800:]


# --- תור הרינדור ---

def test_render_queue_order_priority_move_remove():
    q = RenderQueue()
    a = q.put("A", meta={"label": "a"})
    b = q.put("B", meta={"label": "b"})
    c = q.put("C", front=True, meta={"label": "c", "priority": "high"})
    assert [e["label"] for e in q.snapshot()] == ["c", "a", "b"] and q.qsize() == 3
    assert q.move(b, "top") is True
    assert [e["id"] for e in q.snapshot()] == [b, c, a]
    assert q.remove(c) == "C" and q.remove(c) is None
    assert q.get() == "B" and q.get() == "A" and q.qsize() == 0


def test_paused_render_queue_holds_items_until_resumed():
    q = RenderQueue()
    q.set_paused(True)
    q.put("X")
    got = []
    worker = threading.Thread(target=lambda: got.append(q.get()), daemon=True)
    worker.start()
    time.sleep(0.2)
    assert got == []
    q.set_paused(False)
    worker.join(2)
    assert got == ["X"]


def test_busy_reason_detects_running_process_and_gpu(monkeypatch):
    import psutil
    me = psutil.Process().name()
    assert me.lower() in (web_app.worker.busy_reason({"processes": [me.upper()]}) or "").lower()
    assert web_app.worker.busy_reason({"processes": ["definitely-not-running-xyz.exe"]}) is None
    import utils.shared.hardware as hardware
    monkeypatch.setattr(hardware, "get_gpu_stats", lambda: (97.0, 20.0, 5.0))
    assert "97" in web_app.worker.busy_reason({"gpu_percent": 90})
    monkeypatch.setattr(hardware, "get_gpu_stats", lambda: (3.0, 20.0, 95.0))  # NVENC עסוק (הקלטה) גם כשהכללי נמוך
    assert "95" in web_app.worker.busy_reason({"gpu_percent": 90})
    monkeypatch.setattr(hardware, "get_gpu_stats", lambda: (None, None, None))  # אין GPU של NVIDIA
    assert web_app.worker.busy_reason({"gpu_percent": 90}) is None


def test_render_queue_endpoints(monkeypatch):
    q = web_app.worker.heavy_queue
    q.set_paused(True)
    try:
        closed = []
        first = q.put((lambda: {"returncode": 0}, [], lambda outcome: closed.append(outcome)), meta={"label": "first"})
        second = q.put((lambda: {"returncode": 0}, [], None), meta={"label": "second"})
        data = client.get("/api/render_queue").json()
        assert data["paused"] is True and [t["label"] for t in data["pending"]][-2:] == ["first", "second"]
        assert client.post("/api/render_queue/move", json={"id": second, "direction": "up"}).json()["ok"] is True
        assert client.post("/api/render_queue/remove", json={"id": first}).json()["ok"] is True
        assert closed and closed[0]["removed_from_queue"] is True
        client.post("/api/render_queue/remove", json={"id": second})
        resumed = client.post("/api/render_queue/pause", json={"paused": True, "until": "03:30"}).json()
        assert resumed["resume_at"].endswith("03:30")
        assert client.post("/api/render_queue/pause", json={"paused": True, "until": "25:00"}).status_code == 400
    finally:
        client.post("/api/render_queue/pause", json={"paused": False})
    assert web_app.worker.heavy_queue.paused is False


def test_queue_settings_saved_next_to_profiles_and_used_for_runs(tmp_path, monkeypatch):
    import utils.shared.hardware as hardware
    # בלי זה השמירה מפעילה את דוגם ה-GPU האמיתי (thread רקע שישן 2 שניות בלולאה)
    monkeypatch.setattr(hardware, "get_gpu_stats", lambda: (None, None, None))
    saved = client.post("/api/render_queue/settings", json={"wait_when_busy": True, "processes": "obs64.exe, Game.exe", "gpu_percent": 5}).json()
    assert saved["settings"] == {"wait_when_busy": True, "processes": ["obs64.exe", "Game.exe"], "gpu_percent": 10}
    assert (tmp_path / "data" / "render_queue.json").is_file()
    calls = []
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(web_app, "BATCH_OVERRIDES_DIR", str(tmp_path / "bo"))
    monkeypatch.setattr(web_app, "RUN_CONTROL_DIR", str(tmp_path / "rc"))
    (tmp_path / "a.mp4").write_bytes(b"x")
    client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path), "priority": "high"})
    assert calls[0]["priority"] == "high" and calls[0]["busy_guard"] == {"processes": ["obs64.exe", "Game.exe"], "gpu_percent": 10}
    assert calls[0]["label"] == tmp_path.name


# --- ניתוח קובץ ---

@needs_ffmpeg
def test_scene_cuts_and_loudness_endpoints(tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=red:size=160x90:duration=1:rate=10", "-f", "lavfi", "-i", "color=blue:size=160x90:duration=1:rate=10",
                    "-f", "lavfi", "-i", "sine=duration=2", "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-map", "2:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(tmp_path / "cut.mp4")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    cuts = client.get("/api/video_editor/scene_cuts", params={"folder": str(tmp_path), "file": "cut.mp4"}).json()["cuts"]
    assert any(abs(c - 1.0) < 0.15 for c in cuts), cuts
    loud = client.get("/api/video_editor/loudness", params={"folder": str(tmp_path), "file": "cut.mp4"}).json()
    assert loud["points"] and loud["integrated"] is not None and -40 < loud["integrated"] < -5
    assert client.get("/api/video_editor/scene_cuts", params={"folder": str(tmp_path), "file": "..\\x.mp4"}).status_code == 404


@pytest.mark.parametrize("duration, keyframes_only", [(30.0, False), (3397.6, True)])
def test_scene_cuts_of_a_long_recording_decode_only_keyframes(monkeypatch, duration, keyframes_only):
    # הרצה מקצה לקצה (16.10): הקלטה של שעה ב-4K פוענחה כולה ב-CPU (יותר מ-15 דק') - גם באמצע רינדור
    from entrypoints.web.routes import pro
    from utils.media import ffprobe_cache
    calls = []
    monkeypatch.setattr(ffprobe_cache, "probe_video", lambda path: {"duration": duration})
    monkeypatch.setattr(pro, "_run_ffmpeg", lambda args, timeout: (calls.append(args), subprocess.CompletedProcess(args, 0, "", "pts_time:4.5"))[1])
    assert pro.compute_scene_cuts("C:\\clips\\long.mp4") == {"cuts": [4.5]}
    assert (calls[0][:2] == ["-skip_frame", "nokey"]) is keyframes_only


def test_parse_ebur128_sample():
    text = ("[Parsed_ebur128_0 @ 1] t: 0.1  TARGET:-23 LUFS    M:-120.7 S:-inf     I: -70.0 LUFS       LRA:   0.0 LU\n"
            "[Parsed_ebur128_0 @ 1] t: 0.2  TARGET:-23 LUFS    M: -20.5 S: -21.0     I: -21.0 LUFS       LRA:   0.0 LU\n"
            "  Summary:\n    I:         -21.8 LUFS\n    LRA:         1.5 LU\n")
    from entrypoints.web.routes.pro import parse_ebur128
    data = parse_ebur128(text)
    assert data["points"] == [[0.1, -120.7, None], [0.2, -20.5, -21.0]] and data["integrated"] == -21.8 and data["lra"] == 1.5
