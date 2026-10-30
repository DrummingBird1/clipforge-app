# tests/studio/test_web_app_editor_wave4.py
#
# גל 4 של 102-ההצעות - תצוגה מקדימה ומשוב (items 40-50): תצוגה מקדימה מלאה דרך
# video_editor.py עצמו (--preview-frame) + לפני/אחרי, ציר-זמן עם ממוזערות, גל-קול
# עם סף-שקט מותאם, בדיקת הגדרות עם שגיאה ליד השדה, הערכת גודל/משך, התקדמות
# פר-קובץ, run-manifest + פאנל תוצאות, זנב-לוג מסונן, ובחירת אזור מחיקת-watermark
# בגרירת מלבן. יחידה (טהור) + endpoints (TestClient) + e2e (ffmpeg אמיתי) + דפדפן.
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.media.captions import build_caption_force_style, write_sample_srt
from utils.video.video_editor import compute_custom_removal_region, parse_region_fractions
from utils.video.video_editor_estimate import estimate_output_mb, estimate_output_seconds
from utils.video.video_editor_validation import map_ffmpeg_error_to_field, parse_validate_output, validate_fields, validate_remove_ranges

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


def _make_clip(path, duration=4, size="320x180", with_audio=False):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=duration={duration}", "-c:a", "aac"]
    cmd += ["-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "workspace" / ".previews"))
    monkeypatch.setattr(web_app, "BATCH_OVERRIDES_DIR", str(tmp_path / "batch_overrides"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


# --- item 44: בדיקות סטטיות ---

def test_validate_fields_reports_each_problem_on_its_field(tmp_path):
    (tmp_path / "logo.txt").write_text("x")
    errors = validate_fields({
        "watermark_path": str(tmp_path / "missing.png"), "pip_path": str(tmp_path), "lut_path": str(tmp_path / "logo.txt"),
        "fps": "abc", "output_template": "{nope}", "remove_ranges": "[[5,2]]", "trim_start": "1:xx",
        "caption_color": "red", "chromakey": True, "chromakey_color": "#00FF00", "target_size_mb": "-3",
    })
    assert "לא נמצא" in errors["watermark_path"]
    assert "תיקייה" in errors["pip_path"]
    assert errors["lut_path"].startswith("⚠️")  # סיומת לא צפויה = אזהרה, לא שגיאה
    for key in ("fps", "output_template", "remove_ranges", "trim_start", "caption_color", "chromakey_color", "target_size_mb"):
        assert key in errors, key


def test_validate_fields_clean_payload_has_no_errors(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"x")
    assert validate_fields({"watermark_path": str(logo), "fps": "30000/1001", "output_template": "{name}_{codec}",
                            "remove_ranges": "[[1,2],[3,4.5]]", "trim_start": "1:30", "caption_color": "#FFFFFF",
                            "chromakey": False, "chromakey_color": "junk"}) == {}


def test_validate_fields_font_warning_only_when_relevant():
    fonts = ["Arial", "Segoe UI"]
    assert validate_fields({"text": "Hi", "text_font": "NoSuchFont"}, known_fonts=fonts)["text_font"].startswith("⚠️")
    assert "text_font" not in validate_fields({"text": "", "text_font": "NoSuchFont"}, known_fonts=fonts)
    assert "caption_font" not in validate_fields({"captions": True, "caption_font": "arial"}, known_fonts=fonts)


@pytest.mark.parametrize("raw,ok", [("", True), ("[[0,1]]", True), ("not json", False), ('{"a":1}', False), ("[[1]]", False), ("[[3,3]]", False), ("[[-1,2]]", False)])
def test_validate_remove_ranges(raw, ok):
    assert (validate_remove_ranges(raw) is None) is ok


def test_map_ffmpeg_error_prefers_matching_path_then_patterns():
    payload = {"lut_path": "C:\\luts\\film.cube", "watermark_path": "C:\\img\\logo.png"}
    assert map_ffmpeg_error_to_field("[Parsed_lut3d_0] Cannot open C:/luts/film.cube", payload) == "lut_path"
    assert map_ffmpeg_error_to_field("logo.png: Invalid data found when processing input", payload) == "watermark_path"
    assert map_ffmpeg_error_to_field("[drawtext] Cannot find a valid font", {}) == "text"
    assert map_ffmpeg_error_to_field("something completely unrelated", {}) is None


def test_parse_validate_output_collects_multiline_invalid_detail():
    stdout = "[INFO] x\n[VALID] a.mp4: ok\n[INVALID] b.mp4: line one\nline two\nPROGRESS:50\n[INVALID] c.mp4: single\n"
    parsed = parse_validate_output(stdout)
    assert [p["file"] for p in parsed] == ["a.mp4", "b.mp4", "c.mp4"]
    assert parsed[1]["detail"] == "line one\nline two"
    assert parsed[2]["detail"] == "single"


# --- item 46: הערכת משך/גודל ---

def test_estimate_output_seconds_trim_ranges_timelapse_and_exactness():
    assert estimate_output_seconds(100, {}) == (100, True)
    assert estimate_output_seconds(100, {"trim_start": "0:10", "trim_duration": 30}) == (30, True)
    assert estimate_output_seconds(100, {"remove_ranges": "[[10,20],[50,55]]"}) == (85, True)
    # חיתוך מפורש גובר על טווחים (כמו בסקריפט עצמו)
    assert estimate_output_seconds(100, {"trim_start": 10, "remove_ranges": "[[20,30]]"}) == (90, True)
    assert estimate_output_seconds(100, {"target_seconds": 60}) == (60, True)
    assert estimate_output_seconds(100, {"trim_silence": True})[1] is False
    assert estimate_output_seconds(100, {"remove_mid_silence": True, "keep_audio": True})[1] is False


def test_estimate_output_mb_target_size_codec_and_audio():
    assert estimate_output_mb(60, 1920, 1080, "30", {"target_size_mb": 25}) == 25.0
    h264 = estimate_output_mb(60, 1920, 1080, "30", {"codec": "h264"})
    hevc = estimate_output_mb(60, 1920, 1080, "30", {"codec": "hevc"})
    av1 = estimate_output_mb(60, 1920, 1080, "30", {"codec": "av1"})
    assert h264 > hevc > av1 > 0
    assert estimate_output_mb(60, 1920, 1080, "30", {"codec": "h264", "keep_audio": True}) > h264
    # CQ גבוה ב-6 ≈ חצי גודל
    lower_quality = estimate_output_mb(60, 1920, 1080, "30", {"codec": "hevc", "nvenc_cq": 25})
    assert abs(lower_quality - hevc / 2) < hevc * 0.05


# --- item 50: אזור מחיקה מותאם ---

def test_parse_region_fractions_and_pixel_region():
    assert parse_region_fractions("0.1,0.2,0.3,0.4") == (0.1, 0.2, 0.3, 0.4)
    assert parse_region_fractions("0.9,0.9,0.5,0.5") == (0.9, 0.9, pytest.approx(0.1), pytest.approx(0.1))
    for bad in ("", "1,2,3", "a,b,c,d", "0.1,0.1,0,0.2", "1.2,0,0.1,0.1", None):
        assert parse_region_fractions(bad) is None
    x, y, w, h = compute_custom_removal_region(1920, 1080, (0.0, 0.0, 1.0, 1.0))
    assert x >= 1 and y >= 1 and x + w <= 1919 and y + h <= 1079  # delogo חייב מרווח מהקצה
    assert compute_custom_removal_region(1000, 500, (0.5, 0.5, 0.1, 0.1)) == (500, 250, 100, 50)


def test_build_extra_args_silence_threshold_and_region():
    args = web_app._build_extra_args("video_editor.py", {"silence_threshold_db": -20, "silence_min_duration": 0.5})
    assert "--silence-threshold-db" not in args  # אין זיהוי-שקט פעיל
    args = web_app._build_extra_args("video_editor.py", {"trim_silence": True, "silence_threshold_db": -20, "silence_min_duration": 0.5})
    assert args[args.index("--silence-threshold-db") + 1] == "-20"
    assert args[args.index("--silence-min-duration") + 1] == "0.5"
    args = web_app._build_extra_args("video_editor.py", {"remove_mid_silence": True, "silence_threshold_db": -30, "silence_min_duration": 0.3})
    assert "--silence-threshold-db" not in args and "--silence-min-duration" not in args
    args = web_app._build_extra_args("video_editor.py", {"remove_watermark_region": "0.1,0.25,0.3,0.1"})
    assert args[args.index("--remove-watermark-region") + 1] == "0.1,0.25,0.3,0.1"
    assert "--remove-watermark-region" not in web_app._build_extra_args("video_editor.py", {"remove_watermark_region": "bogus"})


def test_wave4_fields_are_profile_fields_with_help():
    from utils.video.video_editor_field_help import FIELD_HELP
    from utils.video.video_editor_profiles import PROFILE_FIELDS
    for key in ("silence_threshold_db", "silence_min_duration", "remove_watermark_region"):
        assert key in PROFILE_FIELDS and key in FIELD_HELP


# --- item 40: כתובית-לדוגמה משתמשת באותו עיצוב כמו השריפה האמיתית ---

def test_caption_style_builder_matches_burn_style_and_sample_srt(tmp_path):
    assert build_caption_force_style("Arial", 16, "#FFFF00", "top") == \
        "FontName=Arial,FontSize=16,PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=8,MarginV=60"
    srt = tmp_path / "s.srt"
    write_sample_srt(str(srt), "שלום\nHello", 12.5)
    assert srt.read_text(encoding="utf-8") == "1\n00:00:00,000 --> 00:00:12,500\nשלום\nHello\n\n"


# --- item 47: התקדמות פר-קובץ ---

def test_worker_extracts_tqdm_label_as_file_name():
    from utils.shared.worker import TaskWorker
    w = TaskWorker.__new__(TaskWorker)
    import queue
    w.log_queue, w.progress_queue = queue.Queue(), queue.Queue()
    w._handle_output_line("clip one.mp4:  45%|####      | 45/100 [00:03<00:04, 12.3frames/s]", "video_editor.py")
    w._handle_output_line("PROGRESS:30", "video_editor.py")
    first, second = w.progress_queue.get_nowait(), w.progress_queue.get_nowait()
    assert first["label"] == "clip one.mp4" and first["pct"] == 45
    assert second.get("label") is None and second["pct"] == 30


def test_websocket_sends_overall_pct_and_per_file_map(monkeypatch):
    import threading
    from utils.shared.worker import worker
    while not worker.progress_queue.empty():
        worker.progress_queue.get_nowait()
    received = {}
    done = threading.Event()
    connected = threading.Event()

    def _push_batches():
        # התור משותף לכל ה-handlers בתהליך (גם של שרת טסטי-הדפדפן, שעדיין רץ) -
        # אם צרכן אחר חוטף את השלישייה, דוחפים אותה שוב עד שהחיבור של הטסט מקבל
        # אותה. בבת-אחת, תחת ה-mutex, כדי שה-handler יראה את שלושתם באותו מחזור.
        connected.wait(timeout=20)
        while not done.is_set():
            with worker.progress_queue.mutex:
                worker.progress_queue.queue.extend([
                    {"pct": 20, "eta_seconds": None, "label": None},
                    {"pct": 60, "eta_seconds": 5, "label": "a.mp4"},
                    {"pct": 10, "eta_seconds": 9, "label": "b.mp4"},
                ])
                worker.progress_queue.not_empty.notify()
            done.wait(0.5)

    def _exchange():
        with client.websocket_connect("/ws") as ws:
            connected.set()
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "progress" and msg.get("files") == {"a.mp4": 60, "b.mp4": 10}:
                    received["msg"] = msg
                    done.set()
                    return

    # watchdog: receive_json() חוסם בלי timeout - אם ההודעה לא מגיעה הטסט נכשל
    # תוך 20 שניות במקום לתקוע את כל ה-CI עד ה-timeout של GitHub.
    pusher = threading.Thread(target=_push_batches, daemon=True)
    thread = threading.Thread(target=_exchange, daemon=True)
    pusher.start()
    thread.start()
    thread.join(timeout=20)
    done.set()
    pusher.join(timeout=2)
    while not worker.progress_queue.empty():
        worker.progress_queue.get_nowait()
    assert "msg" in received, "הודעת progress לא הגיעה תוך 20 שניות"
    msg = received["msg"]
    assert msg["pct"] == 20
    assert msg["files"] == {"a.mp4": 60, "b.mp4": 10}


# --- endpoints: run manifest / פתיחת תיקייה / נגן / ממוזערת ---

def test_run_manifest_endpoints_restricted_to_manifest_dir(tmp_path, monkeypatch):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    monkeypatch.setattr(web_app, "RUN_MANIFESTS_DIR", str(manifests))
    good = manifests / "20260101_000000_1.json"
    good.write_text(json.dumps({"input_dir": "C:\\clips", "files": [{"source": "a.mp4", "status": "error"}]}), encoding="utf-8")
    assert client.get("/api/video_editor/run_manifest", params={"path": str(good)}).json()["files"][0]["status"] == "error"
    outside = tmp_path / "evil.json"
    outside.write_text("{}")
    assert client.get("/api/video_editor/run_manifest", params={"path": str(outside)}).status_code == 404
    latest = client.get("/api/video_editor/latest_manifest", params={"folder": "C:\\clips"}).json()
    assert latest["manifest_path"] == str(good)
    assert client.get("/api/video_editor/latest_manifest", params={"folder": "D:\\other"}).status_code == 404
    # הסטטוס בתור (בכל פתיחת תיקייה): "אין עדיין ריצה" בלי 404 אדום בקונסול (הרצה מקצה לקצה, 16.10)
    quiet = client.get("/api/video_editor/latest_manifest", params={"folder": "D:\\other", "quiet": 1})
    assert quiet.status_code == 200 and quiet.json()["files"] == []


def test_open_folder_only_inside_workspace(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(web_app.os, "startfile", lambda p: opened.append(p), raising=False)
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path / "ws"))
    (tmp_path / "ws" / "vertical").mkdir(parents=True)
    video = tmp_path / "ws" / "vertical" / "a.mp4"
    video.write_bytes(b"x")
    assert client.post("/api/open_folder", json={"path": str(video)}).status_code == 200
    assert opened == [str(tmp_path / "ws" / "vertical")]
    assert client.post("/api/open_folder", json={"path": str(tmp_path)}).status_code == 404
    assert client.get("/api/video_editor/stream", params={"path": str(video)}).status_code == 200
    outside = tmp_path / "b.mp4"
    outside.write_bytes(b"x")
    assert client.get("/api/video_editor/stream", params={"path": str(outside)}).status_code == 404
    assert client.get("/api/video_editor/output_thumbnail", params={"path": str(outside)}).status_code == 404


def test_estimate_endpoint_requires_folder():
    assert client.post("/api/video_editor/estimate", json={"folder": "Z:\\nope"}).status_code == 400


def test_validate_endpoint_static_errors_skip_ffmpeg(tmp_path):
    data = client.post("/api/video_editor/validate", json={"folder": str(tmp_path), "lut_path": str(tmp_path / "missing.cube")}).json()
    assert data["valid"] is False
    assert "lut_path" in data["field_errors"]
    assert data["ffmpeg_checked"] is False


def test_preview_frame_rejects_concat_and_missing_folder(tmp_path):
    assert client.post("/api/video_editor/preview_frame", json={"folder": "Z:\\nope"}).status_code == 400
    assert client.post("/api/video_editor/preview_frame", json={"folder": str(tmp_path), "concat_mode": True}).status_code == 400
    assert client.post("/api/video_editor/preview_frame", json={"folder": str(tmp_path)}).status_code == 400  # אין קבצים


# --- e2e אמיתי (ffmpeg) ---

@needs_ffmpeg
def test_e2e_preview_frame_endpoint_renders_after_and_before(tmp_path):
    _make_clip(tmp_path / "clip.mp4", duration=4, with_audio=True)
    data = client.post("/api/video_editor/preview_frame", json={
        "folder": str(tmp_path), "vertical": True, "keep_audio": True, "captions": True, "text": "Hi: 50%", "time": "0:02",
        "number_videos": True, "force": True, "hwaccel": True, "codec": "hevc",
    }).json()
    assert "error" not in data, data
    assert (data["output_width"], data["output_height"]) == (1080, 1920)
    assert data["time"] == 2.0 and data["file"] == "clip.mp4"
    assert any("כתובית" in n for n in data["notes"])
    from urllib.parse import parse_qs, urlparse
    from PIL import Image
    after = parse_qs(urlparse(data["after_url"]).query)["path"][0]
    before = parse_qs(urlparse(data["before_url"]).query)["path"][0]
    assert Image.open(after).size == (1080, 1920) and Image.open(before).size == (1080, 1920)
    assert client.get(data["after_url"]).status_code == 200


@needs_ffmpeg
def test_e2e_preview_mode_never_renders_video_or_writes_manifest(tmp_path, monkeypatch):
    _make_clip(tmp_path / "clip.mp4", duration=3)
    out = tmp_path / "frame.png"
    before_manifests = set(os.listdir(os.path.join(WORKSPACE_DIR, ".cache", "run_manifests"))) if os.path.isdir(os.path.join(WORKSPACE_DIR, ".cache", "run_manifests")) else set()
    result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(tmp_path), "--preview-frame", "1", "--preview-frame-out", str(out)],
                            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.exists()
    assert "RESULT:" not in result.stdout
    assert not os.path.exists(os.path.join(WORKSPACE_DIR, "studio", "horizontal", "clip_edited_horizontal.mp4.partial.mp4"))
    after_manifests = set(os.listdir(os.path.join(WORKSPACE_DIR, ".cache", "run_manifests"))) if os.path.isdir(os.path.join(WORKSPACE_DIR, ".cache", "run_manifests")) else set()
    # גל 23: רק manifest של *הריצה הזו* (לפי תיקיית הקלט) - טסט מקביל אחר יכול לכתוב manifest משלו
    mine = []
    for name in after_manifests - before_manifests:
        try:
            with open(os.path.join(WORKSPACE_DIR, ".cache", "run_manifests", name), encoding="utf-8") as f:
                if json.load(f).get("input_dir") == str(tmp_path):
                    mine.append(name)
        except (OSError, ValueError):
            continue
    assert mine == []


@needs_ffmpeg
def test_e2e_run_writes_manifest_with_created_and_error(tmp_path):
    _make_clip(tmp_path / "good.mp4", duration=2)
    (tmp_path / "broken.mp4").write_bytes(b"not a video at all")
    output = os.path.join(WORKSPACE_DIR, "studio", "horizontal", "good_edited_horizontal.mp4")
    from tests.conftest import remove_video_editor_output
    remove_video_editor_output(output)
    manifest_path = None
    try:
        result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(tmp_path), "--codec", "h264"],
                                cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=180)
        line = next(ln for ln in result.stdout.splitlines() if ln.startswith("RESULT: "))
        manifest_path = json.loads(line[len("RESULT: "):])["manifest_path"]
        manifest = json.load(open(manifest_path, encoding="utf-8"))
        statuses = {f["source"]: f for f in manifest["files"]}
        assert statuses["good.mp4"]["status"] == "created"
        assert statuses["good.mp4"]["output"].endswith("good_edited_horizontal.mp4")
        assert statuses["good.mp4"]["render_seconds"] >= 0
        assert statuses["broken.mp4"]["status"] == "error" and statuses["broken.mp4"]["reason"]
        assert os.path.normpath(manifest["input_dir"]) == os.path.normpath(str(tmp_path))
        # ה-endpoint משרת את אותו manifest
        assert client.get("/api/video_editor/run_manifest", params={"path": manifest_path}).status_code == 200
    finally:
        remove_video_editor_output(output)
        if manifest_path and os.path.exists(manifest_path):
            os.remove(manifest_path)


@needs_ffmpeg
def test_e2e_custom_removal_region_validates(tmp_path):
    _make_clip(tmp_path / "clip.mp4", duration=2)
    result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(tmp_path), "--validate-only", "--remove-watermark-region", "0,0,1,1"],
                            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert "[VALID] clip.mp4" in result.stdout, result.stdout + result.stderr
    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("RESULT: "))
    manifest_path = json.loads(line[len("RESULT: "):]).get("manifest_path")
    if manifest_path and os.path.exists(manifest_path):
        os.remove(manifest_path)


@needs_ffmpeg
def test_e2e_validate_endpoint_runs_ffmpeg_check(tmp_path):
    _make_clip(tmp_path / "clip.mp4", duration=2)
    data = client.post("/api/video_editor/validate", json={"folder": str(tmp_path), "vertical": True, "fps": "30"}).json()
    assert data["valid"] is True, data
    assert data["ffmpeg_checked"] is True


@needs_ffmpeg
def test_e2e_estimate_timeline_and_source_frame_endpoints(tmp_path):
    _make_clip(tmp_path / "a.mp4", duration=4)
    _make_clip(tmp_path / "b.mp4", duration=6)
    est = client.post("/api/video_editor/estimate", json={"folder": str(tmp_path), "trim_duration": 3, "codec": "hevc"}).json()
    assert [r["file"] for r in est["files"]] == ["a.mp4", "b.mp4"]
    assert est["total_output_seconds"] == 6.0 and est["total_output_mb"] > 0
    only = client.post("/api/video_editor/estimate", json={"folder": str(tmp_path), "only_files": ["b.mp4"]}).json()
    assert [r["file"] for r in only["files"]] == ["b.mp4"]
    timeline = client.get("/api/video_editor/timeline", params={"path": str(tmp_path / "b.mp4"), "count": 4}).json()
    assert timeline["count"] == 4 and abs(timeline["duration"] - 6) < 0.3
    from urllib.parse import parse_qs, urlparse
    from PIL import Image
    strip = parse_qs(urlparse(timeline["url"]).query)["path"][0]
    assert Image.open(strip).size[0] == 4 * web_app.TIMELINE_THUMB_WIDTH
    frame = client.get("/api/video_editor/source_frame", params={"path": str(tmp_path / "a.mp4"), "t": "0:01"}).json()
    assert (frame["width"], frame["height"]) == (320, 180) and frame["time"] == 1.0


# --- דפדפן אמיתי ---

def _set_value(page, element_id, value):
    page.evaluate("([id, v]) => _veSetFieldValue(document.getElementById(id), v)", [element_id, value])


def test_browser_preview_category_and_controls_present(editor_page):
    # גל 10: התצוגה המקדימה בחלונית-הצד הקבועה, מתחת ל"קבצים"
    # גל 13: קבצים בחלונית הצד, התצוגה המקדימה (וציר-הזמן) באזור הנגן
    assert editor_page.evaluate("() => [...document.querySelectorAll('#veSide > details[data-cat]')].map(d => d.dataset.cat)") == ["queue"]
    assert editor_page.evaluate("() => [...document.querySelectorAll('#veViewer > details[data-cat]')].map(d => d.dataset.cat)") == ["preview"]
    assert editor_page.evaluate("() => !!document.querySelector('#veViewer #veTimelineDock[data-subcat=timeline]')")
    for element_id in ("vePreviewFile", "vePreviewTime", "vePreviewAuto", "veTimeline", "veWaveformCanvas", "veLogTail", "veRemoveWatermarkRegion"):
        assert editor_page.evaluate(f"() => !!document.getElementById('{element_id}')"), element_id


@needs_ffmpeg
def test_browser_preview_validation_estimate_and_timeline(editor_page, tmp_path):
    _make_clip(tmp_path / "clip.mp4", duration=6, with_audio=True)
    editor_page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    editor_page.wait_for_function("() => document.getElementById('vePreviewFile').options.length === 1", timeout=15000)
    editor_page.evaluate("() => veScrollToCategory('preview')")
    editor_page.click("#veViewer button:has-text('🖼️ פריים')")
    editor_page.wait_for_function("() => !document.getElementById('vePreviewStageWrap').hidden", timeout=60000)
    editor_page.wait_for_function("() => document.getElementById('vePreviewAfter').naturalWidth > 0 && document.getElementById('vePreviewBefore').naturalWidth > 0", timeout=15000)
    editor_page.evaluate("() => { const r = document.getElementById('vePreviewSplit'); r.value = '20'; r.dispatchEvent(new Event('input')); }")
    assert editor_page.evaluate("() => document.getElementById('vePreviewStage').style.getPropertyValue('--ve-split')") == "20%"

    _set_value(editor_page, "veLutPath", str(tmp_path / "missing.cube"))
    editor_page.click("#veRunModeBtn")  # גל 27: בדיקה והערכה עברו לתפריט ההרצה ▾
    editor_page.click("#veRunMenu button:has-text('בדוק הגדרות')")
    editor_page.wait_for_selector("#veCategories .ve-validate-msg", timeout=30000)
    assert "לא נמצא" in editor_page.inner_text("#veCategories .ve-validate-msg")
    assert "❌" in editor_page.inner_text("#veValidationBox")

    editor_page.click("#veRunModeBtn")
    editor_page.click("#veRunMenu button:has-text('הערך גודל ומשך')")
    editor_page.wait_for_selector("#veEstimateBox table", timeout=30000)
    assert "clip.mp4" in editor_page.inner_text("#veEstimateBox")

    editor_page.click("[data-subcat=timeline] .ve-subcat-title button:has-text('טען')")
    editor_page.wait_for_function("() => !document.getElementById('veTimelineBox').hidden && document.getElementById('veTimelineImg').naturalWidth > 0", timeout=60000)
    timeline = editor_page.locator("#veTimeline")
    timeline.scroll_into_view_if_needed()
    box = timeline.bounding_box()
    timeline.click(position={"x": box["width"] * 0.5, "y": box["height"] / 2})
    editor_page.click("button:has-text('התחלה כאן')")
    assert abs(editor_page.evaluate("() => _collectRunOptions().trim_start") - 3.0) < 0.3
    editor_page.click("button:has-text('מכאן'):has-text('הסר')")
    ranges = editor_page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)")
    assert len(ranges) == 1 and abs(ranges[0][0] - 3.0) < 0.3
    editor_page.wait_for_function("() => _veWaveformData !== null", timeout=30000)


@needs_ffmpeg
def test_browser_region_selection_by_dragging(editor_page, tmp_path):
    _make_clip(tmp_path / "clip.mp4", duration=3)
    editor_page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    editor_page.wait_for_function("() => document.getElementById('vePreviewFile').options.length === 1", timeout=15000)
    editor_page.evaluate("() => openVeRegionDialog()")
    editor_page.wait_for_function("() => document.getElementById('veRegionImg').naturalWidth > 0", timeout=30000)
    editor_page.locator("#veRegionImg").scroll_into_view_if_needed()
    box = editor_page.locator("#veRegionImg").bounding_box()
    editor_page.mouse.move(box["x"] + box["width"] * 0.1, box["y"] + box["height"] * 0.2)
    editor_page.mouse.down()
    editor_page.mouse.move(box["x"] + box["width"] * 0.4, box["y"] + box["height"] * 0.5, steps=5)
    editor_page.mouse.up()
    editor_page.click("#veRegionModalBg button:has-text('שמור אזור')")
    parts = [float(v) for v in editor_page.evaluate("() => document.getElementById('veRemoveWatermarkRegion').value").split(",")]
    assert parts == pytest.approx([0.1, 0.2, 0.3, 0.3], abs=0.02)
    assert editor_page.evaluate("() => !document.getElementById('veRegionClearBtn').hidden")
    assert "--remove-watermark-region" in editor_page.evaluate("async () => (await (await fetch('/api/video_editor/preview_command', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(_collectRunOptions())})).json()).command")


def test_browser_results_modal_and_rerun_button(editor_page):
    editor_page.evaluate("""() => _veShowResults({mode: 'render', input_dir: 'C:\\\\x', output_dir: 'C:\\\\out', elapsed_seconds: 75,
        counts: {files_created: 1, skipped: 1, errors: 2},
        files: [{source: 'a.mp4', status: 'created', output: 'C:\\\\out\\\\a_edited.mp4', render_seconds: 12, output_size_mb: 3.2},
                {source: 'b.mp4', status: 'skipped', reason: 'כבר קיים'},
                {source: 'c.mp4', status: 'error', reason: 'הרינדור נכשל'},
                {source: 'd.mp4', status: 'error', reason: 'שטח דיסק'}]})""")
    assert editor_page.is_visible("#veResultsPanel")  # גל 31: בתוך הסטודיו, לא בדיאלוג
    assert editor_page.locator("#veResultsList .ve-result-card").count() == 4
    assert "2 הנכשלים" in editor_page.inner_text("#veResultsRerunFailedBtn")
    assert "1:15" in editor_page.inner_text("#veResultsSummary")


def test_browser_log_tail_filters_important_lines(editor_page):
    editor_page.evaluate("""() => appendLogBatch([{line: '[INFO] a'}, {line: 'noise 12%'}, {line: '[ERROR] boom'}, {line: '[WARNING] careful'}, {line: '[APPROVED] done'}])""")
    editor_page.evaluate("() => { document.getElementById('veRunsDrawer').open = true; document.getElementById('veLogTail').open = true; renderVeLogTail(); }")
    text = editor_page.inner_text("#veLogTailBox")
    assert "[ERROR] boom" in text and "[INFO] a" in text and "noise" not in text
    editor_page.select_option("#veLogTailFilter", "errors")
    text = editor_page.inner_text("#veLogTailBox")
    assert "[ERROR] boom" in text and "[WARNING] careful" in text and "[INFO] a" not in text


def test_browser_sticky_progress_shows_each_active_file(editor_page):
    editor_page.evaluate("() => _veUpdateFileProgress({'first.mp4': 40, 'second.mp4': 75}, 30, '0:12')")
    text = editor_page.inner_text("#veStickyProgress")
    assert "30%" in text and "first.mp4 40%" in text and "second.mp4 75%" in text
