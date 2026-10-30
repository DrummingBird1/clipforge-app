# tests/studio/test_video_editor_wave10.py
#
# גל 10 - סידור עורך-העל + ביצועים + תצוגה מקדימה: פייפליין GPU היברידי
# (deinterlace/סיבוב/הקטנה מוקדמת על ה-GPU לפני הסינון ב-CPU), מיקום חופשי
# לשכבות ול-PiP (גרירה על התצוגה המקדימה), וקטע תצוגה מקדימה עם שמע
# (--preview-clip-seconds). יחידה (טהור) + endpoints (TestClient) + e2e (ffmpeg אמיתי).
import os
from tests import PROJECT_ROOT
import shutil
import subprocess


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import video_editor_profiles as vep
from utils.video.video_editor import build_edit_filter_complex, build_hybrid_gpu_prefix, build_orientation_filters, parse_cuda_filters
from utils.video.video_editor_layers import build_layer_parts, build_text_layer_filters, sanitize_layers
from entrypoints.web import frontend_assembly as fa

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
    monkeypatch.setattr(web_app, "PREVIEWS_DIR", str(tmp_path / "workspace" / ".previews"))
    monkeypatch.setattr(web_app, "BATCH_OVERRIDES_DIR", str(tmp_path / "batch_overrides"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


# --- פייפליין GPU היברידי ---

def test_hybrid_prescales_4k_to_cover_the_output_on_gpu():
    prefix, orient, deint = build_hybrid_gpu_prefix([], False, 3840, 2160, 1920, 1080)
    assert prefix == ["scale_cuda=w=1920:h=1080:interp_algo=lanczos"]
    assert (orient, deint) == (False, False)


def test_hybrid_cover_scale_keeps_both_sides_at_least_the_output():
    # 4K אופקי -> 9:16: גודל "כיסוי" = הגובה נוגע ב-1920, הרוחב גדול מ-1080 (לקרופ ב-CPU)
    [scale] = build_hybrid_gpu_prefix([], False, 3840, 2160, 1080, 1920)[0]
    assert scale == "scale_cuda=w=3414:h=1920:interp_algo=lanczos"
    # מידות אי-זוגיות מעוגלות למעלה לזוגי (דרישת nv12)
    [scale] = build_hybrid_gpu_prefix([], False, 3001, 1999, 1280, 720)[0]
    width, height = (int(v.split("=")[-1]) for v in scale.split(":")[:2])
    assert width % 2 == 0 and height % 2 == 0 and width >= 1280 and height >= 720


def test_hybrid_rotation_and_flip_map_to_transpose_cuda():
    assert build_hybrid_gpu_prefix(build_orientation_filters(90), False, 2160, 3840, 1080, 1920)[0][0] == "transpose_cuda=dir=clock"
    assert build_hybrid_gpu_prefix(build_orientation_filters(270), False, None, None, None, None)[0] == ["transpose_cuda=dir=cclock"]
    # 180 (hflip+vflip) ו"מראה כפול" = חצי-סיבוב במעבר אחד
    assert build_hybrid_gpu_prefix(build_orientation_filters(180), False, None, None, None, None)[0] == ["transpose_cuda=dir=reversal"]
    assert build_hybrid_gpu_prefix(build_orientation_filters(0, "both"), False, None, None, None, None)[0] == ["transpose_cuda=dir=reversal"]
    assert build_hybrid_gpu_prefix(build_orientation_filters(90, "h"), False, None, None, None, None)[0] == [
        "transpose_cuda=dir=clock", "transpose_cuda=dir=hflip"]


def test_hybrid_deinterlace_runs_first_then_rotation_then_scale():
    prefix, orient, deint = build_hybrid_gpu_prefix(["transpose=1"], True, 2160, 3840, 1080, 1920)
    assert [p.split("=")[0] for p in prefix] == ["bwdif_cuda", "transpose_cuda", "scale_cuda"]
    assert orient and deint


def test_hybrid_no_prescale_when_not_allowed_or_not_worth_it():
    assert build_hybrid_gpu_prefix([], False, 3840, 2160, 1920, 1080, allow_prescale=False)[0] == []
    assert build_hybrid_gpu_prefix([], False, 1920, 1080, 1920, 1080)[0] == []  # אותן מידות
    assert build_hybrid_gpu_prefix([], False, 1280, 720, 1920, 1080)[0] == []  # הגדלה - נשארת ב-CPU
    assert build_hybrid_gpu_prefix([], False, 1980, 1114, 1920, 1080)[0] == []  # פחות מ-5% הקטנה


def test_hybrid_falls_back_per_step_when_a_cuda_filter_is_missing():
    # בלי transpose_cuda: הסיבוב נשאר ב-CPU, ולכן גם אין הקטנה מוקדמת (היא הייתה רצה על פריים לא-מסובב)
    prefix, orient, deint = build_hybrid_gpu_prefix(["transpose=1"], False, 2160, 3840, 1080, 1920, available_filters={"scale_cuda"})
    assert (prefix, orient, deint) == ([], False, False)
    # בלי bwdif_cuda: deinterlace ב-CPU, ובלי הקטנה לפניו
    prefix, orient, deint = build_hybrid_gpu_prefix([], True, 3840, 2160, 1920, 1080, available_filters={"scale_cuda", "transpose_cuda"})
    assert (prefix, deint) == ([], False)


def test_parse_cuda_filters_reads_ffmpeg_listing():
    listing = " T. bwdif_cuda        V->V       Deinterlace CUDA frames\n .. scale_cuda        V->V       GPU accelerated\n .. scale             V->V       Scale\nFilters:\n"
    assert parse_cuda_filters(listing) == ["bwdif_cuda", "scale_cuda"]


def test_filter_complex_puts_gpu_prefix_before_hwdownload_only_in_decode_mode():
    common = dict(output_width=1920, output_height=1080, eq_filter="eq=saturation=1.2")
    graph, _ = build_edit_filter_complex("scale=1920:1080", 30, hwaccel_decode_only=True, gpu_prefix=["transpose_cuda=dir=clock", "scale_cuda=w=1920:h=1080"], **common)
    assert "[0:v]transpose_cuda=dir=clock,scale_cuda=w=1920:h=1080,hwdownload,format=nv12," in graph
    graph, _ = build_edit_filter_complex("scale=1920:1080", 30, hwaccel_decode_only=False, gpu_prefix=["scale_cuda=w=1"], **common)
    assert "scale_cuda" not in graph and "hwdownload" not in graph


def test_renderer_wires_hybrid_prefix_and_escape_hatch():
    source = open(os.path.join(PROJECT_ROOT, "my_scripts", "video", "video_editor.py"), encoding="utf-8").read() + open(os.path.join(PROJECT_ROOT, "src", "utils", "video", "video_editor_cli.py"), encoding="utf-8").read()
    assert '"--no-gpu-hybrid"' in source
    assert "orientation_filters=[] if orientation_on_gpu else cfg.ORIENTATION_FILTERS" in source
    assert "deinterlace=cfg.DEINTERLACE and not deinterlace_on_gpu" in source


# --- מיקום חופשי לשכבות (גרירה על התצוגה המקדימה) ---

def test_custom_layer_position_keeps_center_fractions():
    [layer] = sanitize_layers([{"type": "text", "text": "Hi", "position": "custom", "x": 0.25, "y": 1.7}])
    assert (layer["position"], layer["x"], layer["y"]) == ("custom", 0.25, 1.0)  # מהודק לפריים
    [layer] = sanitize_layers([{"type": "text", "text": "Hi", "position": "custom"}])
    assert layer["position"] == "bottom-center" and "x" not in layer


def test_custom_text_layer_is_centered_on_the_point_and_clamped():
    [layer] = sanitize_layers([{"type": "text", "text": "Hi", "position": "custom", "x": 0.25, "y": 0.75}])
    [drawtext] = build_text_layer_filters(layer, ["C:/t.txt"])
    assert "x='max(0,min(w-text_w,w*0.25-text_w/2))'" in drawtext
    assert "y='max(0,min(h-text_h,h*0.75-text_h/2))'" in drawtext


def test_custom_image_layer_overlay_uses_center_fractions(tmp_path):
    image = tmp_path / "s.png"
    image.write_bytes(b"x")
    layers = sanitize_layers([{"type": "image", "path": str(image), "position": "custom", "x": 0.5, "y": 0.1}])
    parts, _ = build_layer_parts("base", layers, {}, {0: 2}, 1920, 30, 10.0)
    assert any("overlay=x='max(0,min(W-w,W*0.5-w/2))':y='max(0,min(H-h,H*0.1-h/2))'" in p for p in parts)


# --- PiP נגרר ---

def test_pip_xy_sent_only_as_a_pair_and_clamped():
    base = {"pip_path": "C:\\cam.mp4", "pip_position": "top-left"}
    args = web_app._build_extra_args("video_editor.py", {**base, "pip_x": 0.3, "pip_y": 1.4})
    assert args[args.index("--pip-x") + 1] == "0.3" and args[args.index("--pip-y") + 1] == "1"
    assert "--pip-x" not in web_app._build_extra_args("video_editor.py", {**base, "pip_x": 0.3, "pip_y": None})
    assert "--pip-x" not in web_app._build_extra_args("video_editor.py", {"pip_x": 0.3, "pip_y": 0.3})  # בלי PiP בכלל


def test_pip_xy_are_profile_fields():
    assert {"pip_x", "pip_y"} <= set(vep.PROFILE_FIELDS)


# --- קטע תצוגה מקדימה ---

def test_preview_media_serves_only_plain_names_inside_previews(tmp_path):
    previews = tmp_path / "workspace" / ".previews"
    previews.mkdir(parents=True)
    (previews / "clip_after_1.mp4").write_bytes(b"mp4")
    assert client.get("/api/video_editor/preview_media?name=clip_after_1.mp4").content == b"mp4"
    for bad in ("..\\secret.mp4", "../secret.mp4", "sub/clip.mp4", "C:\\x\\clip.mp4", "notes.txt", ""):
        assert client.get("/api/video_editor/preview_media", params={"name": bad}).status_code == 400, bad
    assert client.get("/api/video_editor/preview_media?name=missing.mp4").status_code == 404


def test_preview_clip_rejects_missing_folder_concat_and_empty(tmp_path):
    assert client.post("/api/video_editor/preview_clip", json={"folder": "Z:\\nope"}).status_code == 400
    assert client.post("/api/video_editor/preview_clip", json={"folder": str(tmp_path), "concat_mode": True}).status_code == 400
    assert client.post("/api/video_editor/preview_clip", json={"folder": str(tmp_path)}).status_code == 400


def test_preview_clip_builds_renderer_args(tmp_path, monkeypatch):
    (tmp_path / "a.mp4").write_bytes(b"x")
    seen = {}

    def fake_run(folder, args, timeout):
        seen["args"] = args
        out = args[args.index("--preview-frame-out") + 1]
        open(out, "wb").close()
        return subprocess.CompletedProcess(args, 0, stdout='PREVIEW_FRAME: {"time": 1.0, "clip_seconds": 3.0, "output_width": 1920, "output_height": 1080, "notes": []}\n', stderr="")

    monkeypatch.setattr(web_app, "_run_editor_subprocess", fake_run)
    data = client.post("/api/video_editor/preview_clip", json={"folder": str(tmp_path), "time": "0:01", "clip_seconds": 99, "hwaccel": True}).json()
    args = seen["args"]
    assert args[args.index("--preview-clip-seconds") + 1] == "10"  # מהודק ל-1..10
    assert args[args.index("--preview-frame") + 1] == "1"
    assert "--hwaccel" not in args  # תצוגה מקדימה תמיד ב-CPU
    assert data["after_url"].startswith("/api/video_editor/preview_media?name=clip_after_")
    assert data["before_url"] is None  # הרנדרר המדומה לא יצר קטע "לפני"


@needs_ffmpeg
def test_e2e_preview_clip_renders_video_with_audio_and_before_clip(tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x180:rate=10", "-f", "lavfi", "-i", "sine=duration=6",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest", str(tmp_path / "clip.mp4")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    data = client.post("/api/video_editor/preview_clip", json={
        "folder": str(tmp_path), "vertical": True, "keep_audio": True, "time": "0:01", "clip_seconds": 3, "eq_saturation": 1.3,
    }).json()
    assert "error" not in data, data
    assert (data["output_width"], data["output_height"]) == (1080, 1920)
    assert data["time"] == 1.0 and data["clip_seconds"] == 3.0
    from utils.media.ffprobe_cache import probe_video
    previews = os.path.join(str(tmp_path), "workspace", ".previews")
    after = os.path.join(previews, data["after_url"].split("name=")[1])
    before = os.path.join(previews, data["before_url"].split("name=")[1])
    after_info, before_info = probe_video(after), probe_video(before)
    assert (after_info["width"], after_info["height"]) == (1080, 1920) and after_info["has_audio"]
    assert abs(after_info["duration"] - 3.0) < 0.35
    assert (before_info["width"], before_info["height"]) == (1080, 1920) and not before_info["has_audio"]
    assert client.get(data["after_url"]).status_code == 200


def test_page_has_new_preview_and_timeline_controls():
    html = fa.assemble_inline_page()
    for element_id in ("vePreviewClipBtn", "vePreviewClipSeconds", "vePreviewClipBefore", "vePreviewClipSeek", "veSafeZones",
                       "veSafeZonesOverlay", "veDragHandles", "vePreviewHandles", "vePipX", "vePipY", "veSafeZonesWarn"):
        assert f'id="{element_id}"' in html, element_id
    # select לא יושב יותר בתוך <button> (HTML לא תקין - לחיצה על הבורר הפעילה את הכפתור)
    assert '<button type="button" onclick="refreshVePreviewClip()"' not in html
    for fn in ("function refreshVePreviewClip", "function applyVeSafeZones", "function _veRenderDragHandles", "function _veRenderTimelineExtras"):
        assert fn in html, fn
