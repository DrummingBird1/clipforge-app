# tests/studio/test_web_app_editor_wave7.py
#
# גל 7א של 102-ההצעות - עריכה ותוכן: ייצוא/סגנון/שפה/מודל של כתוביות (69, 71-72),
# עורך תמלול לפני שריפה (70), מהירות (73), תיקון צבע eq + עוצמת LUT (74),
# יחסי-רוחב/fit/פלט כפול (75-77), רזולוציה ואלגוריתם scale (78), סיבוב/מראה (83),
# רמות רעש/חידוד + tone-mapping (84), CRF ל-H.264 (86), deinterlace/צבע שוליים/
# ערוץ שמע (89).
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys
import time


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.media import captions
from utils.video import video_editor_profiles as vep
from utils.media.timelapse import build_atempo_chain
from utils.video.video_editor import (
    apply_pad_color, apply_resolution_preset, apply_scale_algorithm, build_edit_filter_complex, build_eq_filter,
    build_fit_scale_chain, build_orientation_filters, build_tonemap_filter, orientation_for_dimensions,
    resolve_aspect_dimensions, resolve_output_filename,
)
from utils.video.video_editor_estimate import estimate_output_dimensions, estimate_output_mb, estimate_output_seconds
from utils.video.video_editor_field_help import FIELD_HELP
from entrypoints.web import frontend_assembly as fa

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")

WAVE7_FIELDS = (
    "aspect", "custom_width", "custom_height", "fit", "dual_output", "watermark_position_vertical", "speed", "crf",
    "resolution", "scale_algo", "lut_intensity", "eq_brightness", "eq_contrast", "eq_saturation", "eq_gamma",
    "denoise_level", "sharpen_level", "tonemap", "rotate", "flip", "deinterlace", "pad_color", "audio_track",
    "caption_style", "captions_language", "captions_model", "captions_export", "captions_no_burn",
)


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


def _make_clip(path, duration=2, size="320x180", audio=False):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-c:a", "aac", "-shortest"]
    cmd += ["-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


def _probe(path):
    from utils.shared.ffmpeg_locator import get_ffprobe_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    out = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return video["width"], video["height"], float(data["format"]["duration"])


def _run_script(tmp_path, *args):
    """מריץ את video_editor.py עם --output-template לתוך תיקייה ייחודית לטסט ומחזיר (RESULT, stdout)."""
    result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(tmp_path / "in"), *args],
                            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=240)
    line = next((ln for ln in result.stdout.splitlines() if ln.startswith("RESULT: ")), None)
    assert line, result.stdout + result.stderr
    return json.loads(line[len("RESULT: "):]), result.stdout


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "profiles" / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "profiles" / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "profiles" / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app, "CAPTIONS_EDITS_DIR", str(tmp_path / "captions_edits"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


# --- helpers טהורים: יחסי-רוחב / רזולוציה / scale / צבע / סיבוב ---

def test_resolve_aspect_dimensions_presets_custom_and_errors():
    assert resolve_aspect_dimensions(None) is None
    assert resolve_aspect_dimensions("1:1") == (1080, 1080)
    assert resolve_aspect_dimensions("4:5") == (1080, 1350)
    assert resolve_aspect_dimensions("4:3") == (1440, 1080)
    width, height = resolve_aspect_dimensions("custom", 999, 1001)
    assert width % 2 == 0 and height % 2 == 0
    with pytest.raises(ValueError):
        resolve_aspect_dimensions("custom", 1080, None)
    with pytest.raises(ValueError):
        resolve_aspect_dimensions("21:9")


def test_apply_resolution_preset_scales_short_side_and_keeps_ratio():
    assert apply_resolution_preset((1920, 1080), "720p") == (1280, 720)
    assert apply_resolution_preset((1080, 1920), "720p") == (720, 1280)
    assert apply_resolution_preset((1080, 1350), "2160p") == (2160, 2700)
    assert apply_resolution_preset((1920, 1080), "auto") == (1920, 1080)
    assert apply_resolution_preset((1920, 1080), None) == (1920, 1080)
    with pytest.raises(ValueError):
        apply_resolution_preset((1920, 1080), "480p")


def test_orientation_for_dimensions_and_output_filename():
    assert orientation_for_dimensions(1080, 1080) == "square"
    assert orientation_for_dimensions(1080, 1350) == "vertical"
    assert orientation_for_dimensions(1440, 1080) == "horizontal"
    assert resolve_output_filename("clip", False, orientation="square") == "clip_edited_square.mp4"
    assert resolve_output_filename("clip", True) == "clip_edited_vertical.mp4"


def test_build_fit_scale_chain_modes():
    pad = build_fit_scale_chain(1080, 1080, "pad", pad_color="0xFFFFFF")
    assert pad.startswith("scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080") and "color=0xFFFFFF" in pad
    assert build_fit_scale_chain(1080, 1350, "crop") == "scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350"
    assert "crop=" in build_fit_scale_chain(1080, 1350, "auto")  # אנכי -> crop
    assert "pad=" in build_fit_scale_chain(1440, 1080, "auto")   # אופקי -> pad
    assert "*(1+0.2500)" in build_fit_scale_chain(1080, 1080, "crop", crop_x_offset=0.25)


def test_apply_scale_algorithm_and_pad_color_touch_cpu_filters_only():
    chain = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    assert apply_scale_algorithm(chain, "bicubic") == chain
    tuned = apply_scale_algorithm(chain, "lanczos")
    assert tuned.startswith("scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,pad=")
    assert apply_scale_algorithm("scale_cuda=1920:1080", "lanczos") == "scale_cuda=1920:1080"
    with pytest.raises(ValueError):
        apply_scale_algorithm(chain, "magic")
    assert apply_pad_color(chain, "black") == chain
    assert apply_pad_color(chain, "0x112233").endswith("pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x112233")
    already = "pad=10:10:0:0:color=red"
    assert apply_pad_color(already, "0x112233") == already


def test_eq_orientation_and_tonemap_filters():
    assert build_eq_filter() == ""
    assert build_eq_filter(brightness=0.1, saturation=1.3) == "eq=brightness=0.100:saturation=1.300"
    assert build_orientation_filters(0, "none") == []
    assert build_orientation_filters(90) == ["transpose=1"]
    assert build_orientation_filters(270, "h") == ["transpose=2", "hflip"]
    assert build_orientation_filters(180, "both") == ["hflip", "vflip", "hflip", "vflip"]
    with pytest.raises(ValueError):
        build_orientation_filters(45)
    assert "tonemap=tonemap=mobius" in build_tonemap_filter("mobius")
    with pytest.raises(ValueError):
        build_tonemap_filter("aces")


def test_atempo_chain_supports_slow_motion():
    assert build_atempo_chain(0.25) == "atempo=0.5,atempo=0.500000"
    assert build_atempo_chain(0.75) == "atempo=0.750000"


def test_builder_applies_wave7_filters_in_order():
    fc, _maps = build_edit_filter_complex(
        "scale=1080:1080", 30, deinterlace=True, orientation_filters=["transpose=1"], eq_filter="eq=contrast=1.200",
        denoise=True, denoise_filter="hqdn3d=8:6:12:9",
    )
    assert fc.index("bwdif") < fc.index("transpose=1") < fc.index("scale=1080:1080")
    assert "hqdn3d=8:6:12:9" in fc and "eq=contrast=1.200" in fc


def test_builder_partial_lut_blends_and_hwaccel_skips_cpu_only_filters():
    fc, _maps = build_edit_filter_complex("scale=1920:1080", 30, lut_path="C:/looks/film.cube", lut_intensity=0.4)
    assert "lut3d=" in fc and "blend=all_mode=normal:all_opacity=0.400" in fc
    full, _ = build_edit_filter_complex("scale=1920:1080", 30, lut_path="C:/looks/film.cube", lut_intensity=1.0)
    assert "blend=" not in full
    hw, _ = build_edit_filter_complex("scale_cuda=1920:1080", 30, use_hwaccel=True, deinterlace=True,
                                      orientation_filters=["hflip"], eq_filter="eq=gamma=1.200")
    assert "bwdif" not in hw and "hflip" not in hw and "eq=" not in hw


def test_builder_selects_audio_track():
    _fc, maps = build_edit_filter_complex("scale=1920:1080", 30, keep_audio=True, audio_stream_index=2)
    assert "0:a:2" in " ".join(maps) or "0:a:2" in _fc


# --- captions: סגנונות / SRT / VTT / karaoke / נתיב תמלול ערוך ---

def test_caption_styles_classic_unchanged_and_variants():
    classic = captions.build_caption_force_style()
    assert classic == "FontName=Arial,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=60"
    assert "Bold=1" in captions.build_caption_force_style(style="bold")
    assert "BorderStyle=3" in captions.build_caption_force_style(style="box")
    assert "SecondaryColour" in captions.build_caption_force_style(style="karaoke")
    with pytest.raises(ValueError):
        captions.build_caption_force_style(style="neon")


def test_srt_roundtrip_vtt_and_karaoke(tmp_path):
    segments = [{"start": 0.0, "end": 1.5, "text": "שלום"}, {"start": 1.5, "end": 3.25, "text": "  "}, {"start": 3.25, "end": 62.0, "text": "world"}]
    srt = tmp_path / "a.srt"
    captions.write_srt(segments, str(srt))
    parsed = captions.parse_srt(srt.read_text(encoding="utf-8"))
    assert [(s["start"], s["end"], s["text"]) for s in parsed] == [(0.0, 1.5, "שלום"), (3.25, 62.0, "world")]
    vtt = captions.srt_to_vtt(srt.read_text(encoding="utf-8"))
    assert vtt.startswith("WEBVTT") and "00:01:02.000" in vtt and "," not in vtt.split("\n", 2)[2].split("\n")[0]
    ass = tmp_path / "k.ass"
    captions.write_karaoke_ass([{"start": 0, "end": 1, "text": "hi there", "words": [{"start": 0, "end": 0.4, "word": "hi"}, {"start": 0.4, "end": 1, "word": "there"}]}], str(ass))
    body = ass.read_text(encoding="utf-8")
    assert "{\\kf40}hi {\\kf60}there" in body


def test_edited_captions_path_is_stable_per_source_path(tmp_path):
    a = captions.edited_captions_path(str(tmp_path), "C:/clips/a.mp4")
    assert a == captions.edited_captions_path(str(tmp_path), "C:/clips/a.mp4")
    assert a != captions.edited_captions_path(str(tmp_path), "C:/other/a.mp4")
    assert a.endswith(".srt") and os.path.dirname(a) == str(tmp_path)


def test_burn_captions_with_override_exports_without_whisper(tmp_path, monkeypatch):
    def _no_whisper(*_a, **_k):
        raise AssertionError("Whisper לא אמור לרוץ כשיש תמלול ערוך")
    monkeypatch.setattr(captions, "transcribe_segments", _no_whisper)
    monkeypatch.setattr(captions, "_transcribe_to_srt", _no_whisper)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"not really a video")
    override = tmp_path / "edited.srt"
    captions.write_srt([{"start": 0, "end": 1, "text": "ערוך"}], str(override))
    assert captions.burn_captions(str(video), export_formats="both", burn=False, srt_override_path=str(override)) == str(video)
    assert "ערוך" in (tmp_path / "v.srt").read_text(encoding="utf-8")
    assert (tmp_path / "v.vtt").read_text(encoding="utf-8").startswith("WEBVTT")
    assert video.read_bytes() == b"not really a video"  # burn=False לא נוגע בווידאו


# --- web: מיפוי שדות -> דגלי CLI ---

def _args(payload):
    return web_app._build_extra_args("video_editor.py", payload)


def test_wave7_defaults_add_no_flags():
    defaults = {
        "aspect": "", "fit": "auto", "resolution": "auto", "scale_algo": "bicubic", "tonemap": "hable", "flip": "none",
        "rotate": 0, "speed": 1, "crf": None, "lut_intensity": 1, "eq_brightness": 0, "eq_contrast": 1, "eq_saturation": 1,
        "eq_gamma": 1, "denoise_level": "medium", "sharpen_level": "medium", "pad_color": "#000000", "audio_track": None,
        "dual_output": False, "deinterlace": False,
    }
    args = _args(defaults)
    for flag in ("--aspect", "--fit", "--resolution", "--scale-algo", "--tonemap", "--flip", "--rotate", "--speed", "--crf",
                 "--lut-intensity", "--eq-brightness", "--dual-output", "--deinterlace", "--pad-color", "--audio-track"):
        assert flag not in args, flag


def test_wave7_fields_map_to_flags():
    args = _args({
        "aspect": "4:5", "fit": "pad", "resolution": "720p", "scale_algo": "lanczos", "tonemap": "mobius", "flip": "h",
        "rotate": "90", "speed": 1.5, "eq_brightness": 0.1, "eq_gamma": 1.4, "deinterlace": True, "pad_color": "#112233",
        "audio_track": 1, "codec": "h264", "crf": 18,
    })
    joined = " ".join(args)
    for expected in ("--aspect 4:5", "--fit pad", "--resolution 720p", "--scale-algo lanczos", "--tonemap mobius", "--flip h",
                     "--rotate 90", "--speed 1.5", "--eq-brightness 0.1", "--eq-gamma 1.4", "--deinterlace",
                     "--pad-color #112233", "--audio-track 1", "--crf 18"):
        assert expected in joined, expected


def test_wave7_conditional_flags():
    assert "--aspect" not in _args({"aspect": "custom", "custom_width": 1080})  # בלי גובה - לא נשלח (הסקריפט היה נכשל)
    assert "--custom-height 1350" in " ".join(_args({"aspect": "custom", "custom_width": 1080, "custom_height": 1350}))
    assert "--crf" not in _args({"codec": "hevc", "crf": 18})
    assert "--lut-intensity" not in _args({"lut_intensity": 0.5})
    assert "--lut-intensity 0.5" in " ".join(_args({"lut_intensity": 0.5, "lut_path": "C:/a.cube"}))
    assert "--watermark-position-vertical" not in _args({"watermark_position_vertical": "top-left"})
    assert "--watermark-position-vertical top-left" in " ".join(_args({"watermark_position_vertical": "top-left", "watermark_path": "C:/w.png"}))
    assert "--denoise-level" not in _args({"denoise_level": "strong"})
    assert "--denoise-level strong" in " ".join(_args({"denoise": True, "denoise_level": "strong"}))
    assert "--sharpen-level light" in " ".join(_args({"sharpen": True, "sharpen_level": "light"}))
    assert "--rotate" not in _args({"rotate": 45})
    assert "--pad-color" not in _args({"pad_color": "red; rm -rf"})
    assert "--dual-output" in _args({"dual_output": True})


def test_wave7_caption_flags_only_with_captions_and_audio():
    assert "--caption-style" not in _args({"caption_style": "bold"})
    args = " ".join(_args({"keep_audio": True, "captions": True, "caption_style": "bold", "captions_language": "he",
                           "captions_model": "medium", "captions_export": "both", "captions_no_burn": True}))
    for expected in ("--caption-style bold", "--captions-language he", "--captions-model medium", "--captions-export both",
                     "--captions-no-burn", "--captions-srt-dir"):
        assert expected in args, expected
    assert "--captions-no-burn" not in _args({"keep_audio": True, "captions": True, "captions_no_burn": True})
    assert "--captions-language" not in _args({"keep_audio": True, "captions": True, "captions_language": "hebrew!"})


def test_caption_max_chars_flag_only_with_captions_and_audio_and_clamped():
    on = {"keep_audio": True, "captions": True}
    assert "--caption-max-chars" not in _args({"caption_max_chars": 20})                     # בלי כתוביות
    assert "--caption-max-chars" not in _args({"captions": True, "caption_max_chars": 20})   # בלי שמע
    assert "--caption-max-chars" not in _args({**on, "caption_max_chars": 0})                # 0 = כבוי, הברירת מחדל
    assert "--caption-max-chars" not in _args({**on, "caption_max_chars": "abc"})
    assert "--caption-max-chars 20" in " ".join(_args({**on, "caption_max_chars": 20}))
    assert "--caption-max-chars 80" in " ".join(_args({**on, "caption_max_chars": 999}))     # מוגבל ל-80


def test_wave7_fields_registered_in_profiles_help_and_page():
    html = fa.assemble_inline_page()
    for field in WAVE7_FIELDS:
        assert field in vep.PROFILE_FIELDS, field
        assert field in FIELD_HELP, field
        assert f"  {field}: {{id: " in html, f"{field} חסר ב-VE_WAVE7_FIELDS"
    for element_id in ("veAspect", "veCustomWidth", "veFit", "veDualOutput", "veRotate", "veFlip", "vePadColor", "veSpeed",
                       "veDeinterlace", "veLutIntensity", "veEqBrightness", "veDenoiseLevel", "veTonemap", "veCrf",
                       "veResolution", "veScaleAlgo", "veWatermarkPositionVertical", "veAudioTrack", "veCaptionStyle",
                       "veCaptionsLanguage", "veCaptionsModel", "veCaptionsExport", "veCaptionsNoBurn", "veTranscriptFile"):
        assert f'id="{element_id}"' in html, element_id


def test_profile_roundtrip_keeps_wave7_fields():
    settings = {"aspect": "1:1", "speed": 0.5, "rotate": 270, "caption_style": "karaoke", "eq_saturation": 1.4}
    vep.save_profile("W7", settings)
    loaded = vep.load_profiles()["W7"]
    for key, value in settings.items():
        assert loaded[key] == value


# --- הערכת גודל: יחסי-רוחב / פלט כפול / רזולוציה / סיבוב ---

def test_estimate_output_dimensions_variants():
    assert estimate_output_dimensions({}, 1920, 1080) == [(1920, 1080)]
    assert estimate_output_dimensions({"vertical": True}, 1920, 1080) == [(1080, 1920)]
    assert estimate_output_dimensions({"dual_output": True}, 1920, 1080) == [(1920, 1080), (1080, 1920)]
    assert estimate_output_dimensions({"aspect": "1:1", "resolution": "720p"}, 1920, 1080) == [(720, 720)]
    assert estimate_output_dimensions({"aspect": "9:16", "vertical": False}, 1920, 1080) == [(1080, 1920)]
    assert estimate_output_dimensions({"aspect": "custom", "custom_width": 800, "custom_height": 600}, 1920, 1080) == [(800, 600)]
    assert estimate_output_dimensions({"aspect": "custom"}, 1920, 1080) == [(1920, 1080)]
    assert estimate_output_dimensions({"preserve_resolution": True, "rotate": 90}, 640, 360) == [(360, 640)]


def test_estimate_size_doubles_with_dual_output_and_speed_shortens():
    single = estimate_output_mb(60, 1920, 1080, "30", {})
    assert estimate_output_mb(60, 1920, 1080, "30", {"dual_output": True}) == pytest.approx(single * 2, rel=0.02)
    assert estimate_output_seconds(60, {"speed": 2})[0] == pytest.approx(30)
    assert estimate_output_seconds(60, {"speed": 0.5})[0] == pytest.approx(120)


# --- item 70: endpoints של עורך התמלול ---

def test_captions_edit_save_load_delete_roundtrip(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    assert client.get("/api/video_editor/captions_edit", params={"path": str(source)}).json() == {"exists": False, "segments": []}
    res = client.post("/api/video_editor/captions_edit", json={"path": str(source), "segments": [
        {"start": 2, "end": 3.5, "text": "second"}, {"start": 0, "end": 1.25, "text": "first"}, {"start": 4, "end": 5, "text": "   "},
    ]})
    assert res.status_code == 200 and res.json()["count"] == 2
    saved_path = captions.edited_captions_path(web_app.CAPTIONS_EDITS_DIR, str(source))
    assert res.json()["srt_path"] == saved_path and os.path.isfile(saved_path)
    loaded = client.get("/api/video_editor/captions_edit", params={"path": str(source)}).json()
    assert loaded["exists"] and [s["text"] for s in loaded["segments"]] == ["first", "second"]
    assert client.request("DELETE", "/api/video_editor/captions_edit", params={"path": str(source)}).json() == {"deleted": True}
    assert not os.path.exists(saved_path)
    assert client.request("DELETE", "/api/video_editor/captions_edit", params={"path": str(source)}).json() == {"deleted": False}


def test_captions_edit_rejects_bad_input(tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    post = lambda segments: client.post("/api/video_editor/captions_edit", json={"path": str(source), "segments": segments})  # noqa: E731
    assert post([{"start": 3, "end": 1, "text": "backwards"}]).status_code == 400
    assert post([{"start": "a", "end": 1, "text": "nan"}]).status_code == 400
    assert post("not a list").status_code == 400
    assert post([{"start": 0, "end": 1, "text": "   "}]).status_code == 400
    assert client.post("/api/video_editor/captions_edit", json={"path": str(tmp_path / "missing.mp4"), "segments": []}).status_code == 400
    # קובץ קיים תחת data/ (זמני, בשם ייחודי - לא נוגעים בקבצי-המשתמש האמיתיים שם)
    os.makedirs(web_app.DATA_DIR, exist_ok=True)
    data_file = os.path.join(web_app.DATA_DIR, f"_w7_probe_{os.getpid()}.mp4")
    with open(data_file, "wb") as f:
        f.write(b"x")
    try:
        assert client.get("/api/video_editor/captions_edit", params={"path": data_file}).status_code == 403
    finally:
        os.remove(data_file)
    cross = client.post("/api/video_editor/captions_edit", json={"path": str(source), "segments": [{"start": 0, "end": 1, "text": "x"}]},
                        headers={"origin": "http://evil.example"})
    assert cross.status_code == 403


def _wait_job(job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get("/api/video_editor/transcribe_status", params={"job_id": job_id}).json()
        if job.get("status") != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("משימת התמלול לא הסתיימה")


def test_transcribe_job_success_and_error(tmp_path, monkeypatch):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    calls = []

    def _fake(path, language, model_size):
        calls.append((path, language, model_size))
        return [{"start": 0.123456, "end": 1.5, "text": "hello", "words": []}]
    monkeypatch.setattr(web_app, "_transcribe_video_segments", _fake)
    res = client.post("/api/video_editor/transcribe", json={"path": str(source), "language": "he", "model": "tiny"})
    job = _wait_job(res.json()["job_id"])
    assert job["status"] == "done" and job["segments"] == [{"start": 0.123, "end": 1.5, "text": "hello"}]
    assert calls == [(str(source), "he", "tiny")]

    def _boom(*_a):
        raise ImportError("No module named 'faster_whisper'")
    monkeypatch.setattr(web_app, "_transcribe_video_segments", _boom)
    job = _wait_job(client.post("/api/video_editor/transcribe", json={"path": str(source)}).json()["job_id"])
    assert job["status"] == "error" and "faster_whisper" in job["error"]
    assert client.post("/api/video_editor/transcribe", json={"path": str(source), "model": "huge"}).status_code == 400
    assert client.post("/api/video_editor/transcribe", json={"path": str(source), "language": "Hebrew"}).status_code == 400
    assert client.get("/api/video_editor/transcribe_status", params={"job_id": "nope"}).status_code == 404


# --- e2e אמיתי עם ffmpeg ---
# הסקריפט כותב תמיד תחת workspace/studio/<orientation> (כמו שאר טסטי ה-e2e) -
# שמות קבצים ייחודיים לגל הזה, ניקוי לפני ואחרי.

def _outputs(name, orientations, extensions=(".mp4",)):
    return [os.path.join(WORKSPACE_DIR, "studio", o, f"{name}_edited_{o}{ext}") for o in orientations for ext in extensions]


def _cleanup(paths, parsed=None):
    from tests.conftest import remove_video_editor_output
    for path in paths:
        if path.endswith(".mp4"):
            remove_video_editor_output(path)
        elif os.path.exists(path):
            os.remove(path)
    manifest = (parsed or {}).get("manifest_path")
    if manifest and os.path.exists(manifest):
        os.remove(manifest)


@needs_ffmpeg
def test_e2e_square_aspect_speed_and_rotate(tmp_path):
    (tmp_path / "in").mkdir()
    _make_clip(tmp_path / "in" / "w7sq.mp4", duration=4, size="320x180")
    paths = _outputs("w7sq", ["square"])
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run_script(tmp_path, "--aspect", "1:1", "--resolution", "720p", "--speed", "2", "--rotate", "90", "--force")
        assert parsed["files_created"] == 1, stdout
        width, height, duration = _probe(paths[0])
        assert (width, height) == (720, 720)
        assert duration == pytest.approx(2.0, abs=0.35)
    finally:
        _cleanup(paths, parsed)


@needs_ffmpeg
def test_e2e_dual_output_creates_horizontal_and_vertical(tmp_path):
    (tmp_path / "in").mkdir()
    _make_clip(tmp_path / "in" / "w7dual.mp4", duration=1, size="320x180")
    paths = _outputs("w7dual", ["horizontal", "vertical"])
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run_script(tmp_path, "--dual-output", "--force")
        assert parsed["files_created"] == 2, stdout
        assert _probe(paths[0])[:2] == (1920, 1080)
        assert _probe(paths[1])[:2] == (1080, 1920)
    finally:
        _cleanup(paths, parsed)


@needs_ffmpeg
def test_e2e_edited_transcript_is_exported_without_whisper(tmp_path):
    (tmp_path / "in").mkdir()
    source = tmp_path / "in" / "w7cap.mp4"
    _make_clip(source, duration=2, size="320x180", audio=True)
    srt_dir = tmp_path / "edits"
    srt_dir.mkdir()
    captions.write_srt([{"start": 0.2, "end": 1.6, "text": "טקסט ערוך ידנית"}], captions.edited_captions_path(str(srt_dir), str(source)))
    paths = _outputs("w7cap", ["horizontal"], (".mp4", ".srt", ".vtt"))
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run_script(tmp_path, "--keep-audio", "--captions", "--captions-export", "both", "--captions-no-burn",
                                     "--captions-srt-dir", str(srt_dir), "--force")
        assert parsed["files_created"] == 1, stdout
        assert "שימוש בתמלול ערוך" in stdout and "יוצא (בלי שריפה)" in stdout, stdout
        with open(paths[1], encoding="utf-8") as f:
            assert "טקסט ערוך ידנית" in f.read()
        with open(paths[2], encoding="utf-8") as f:
            assert f.read().startswith("WEBVTT")
    finally:
        _cleanup(paths, parsed)


@needs_ffmpeg
def test_e2e_edited_transcript_burns_with_style(tmp_path):
    (tmp_path / "in").mkdir()
    source = tmp_path / "in" / "w7burn.mp4"
    _make_clip(source, duration=2, size="320x180", audio=True)
    srt_dir = tmp_path / "edits"
    srt_dir.mkdir()
    captions.write_srt([{"start": 0.0, "end": 1.5, "text": "burned"}], captions.edited_captions_path(str(srt_dir), str(source)))
    paths = _outputs("w7burn", ["vertical"])
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run_script(tmp_path, "--vertical", "--keep-audio", "--captions", "--caption-style", "box",
                                     "--captions-srt-dir", str(srt_dir), "--force")
        assert parsed["files_created"] == 1, stdout
        assert "כתוביות נשרפו" in stdout, stdout
        assert _probe(paths[0])[:2] == (1080, 1920)
    finally:
        _cleanup(paths, parsed)


# --- דפדפן אמיתי (Edge/Chromium דרך Playwright) ---

def _set(page, element_id, value):
    page.evaluate(
        """([id, value]) => { const el = document.getElementById(id);
          if (el.type === 'checkbox') el.checked = value; else el.value = value;
          el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }""",
        [element_id, value],
    )


def _row_hidden(page, element_id):
    return page.evaluate("(id) => document.getElementById(id).closest('.ve-row').classList.contains('ve-dep-hidden')", element_id)


def test_browser_wave7_dependencies_rules_and_chips(editor_page):
    page = editor_page
    assert _row_hidden(page, "veCustomWidth")
    _set(page, "veAspect", "custom")
    page.wait_for_function("() => !document.getElementById('veCustomWidth').closest('.ve-row').classList.contains('ve-dep-hidden')")
    page.wait_for_function("() => document.getElementById('veWarningsBox').textContent.includes('רוחב וגובה')")
    _set(page, "veCustomWidth", "1080")
    _set(page, "veCustomHeight", "1350")
    _set(page, "veDualOutput", True)
    page.wait_for_function("() => document.getElementById('veWarningsBox').textContent.includes('פלט כפול')")
    _set(page, "veSpeed", "1.5")
    page.wait_for_function("() => document.getElementById('veSummaryText').textContent.includes('x1.5')")
    assert "16:9 + 9:16" in page.inner_text("#veSummaryText")
    # גל 10: CRF ו-CQ באותה שורת "איכות ידנית" - מוסתר רק החלק שלא שייך לקודק
    _set(page, "veCodec", "hevc")
    assert page.evaluate("() => document.getElementById('veCrf').closest('.ve-h264-only').hidden") is True
    assert page.evaluate("() => document.getElementById('veNvencCq').closest('.ve-nvenc-only').hidden") is False
    _set(page, "veCodec", "h264")
    assert page.evaluate("() => document.getElementById('veCrf').closest('.ve-h264-only').hidden") is False
    # גל 10: הפחתת רעש + רמה אוחדו לבורר אחד (כבוי/קל/בינוני/חזק)
    assert page.evaluate("() => document.getElementById('veDenoiseMode').value") == "off"
    _set(page, "veDenoise", True)
    page.wait_for_function("() => document.getElementById('veDenoiseMode').value === 'medium'")
    opts = page.evaluate("() => _collectRunOptions()")
    assert opts["aspect"] == "custom" and opts["custom_width"] == 1080 and opts["speed"] == 1.5 and opts["dual_output"] is True


def test_browser_wave7_fields_restore_from_profile(editor_page):
    page = editor_page
    page.evaluate("""() => _applyGenericVeFields({aspect: '4:5', rotate: 270, flip: 'h', eq_saturation: 1.4, caption_style: 'box',
                                                 captions_model: 'medium', crf: 23})""")
    values = page.evaluate("""() => ['veAspect', 'veRotate', 'veFlip', 'veEqSaturation', 'veCaptionStyle', 'veCaptionsModel', 'veCrf']
                                     .map(id => document.getElementById(id).value)""")
    assert values == ["4:5", "270", "h", "1.4", "box", "medium", "23"]
    page.evaluate("() => _applyGenericVeFields({})")  # פרופיל ישן בלי השדות -> ברירות המחדל של ה-HTML
    assert page.evaluate("() => [veAspect.value, veCaptionsModel.value, veSpeed.value]") == ["", "small", "1"]


def test_browser_transcript_editor_transcribe_edit_and_save(editor_page, tmp_path, monkeypatch):
    page = editor_page
    clip = tmp_path / "talk.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "_transcribe_video_segments",
                        lambda path, language, model: [{"start": 0.5, "end": 2.0, "text": "שלום עולם"}, {"start": 2.0, "end": 3.5, "text": "שורה שנייה"}])
    page.evaluate("() => openVeTranscriptDialog()")  # גל 10: עורך התמלול בדיאלוג משלו
    page.evaluate("""(folder) => { state.folder = folder; const sel = document.getElementById('veTranscriptFile');
                      sel.innerHTML = '<option value="talk.mp4">talk.mp4</option>'; sel.value = 'talk.mp4'; }""", str(tmp_path))
    page.evaluate("() => startVeTranscription()")
    page.wait_for_function("() => document.querySelectorAll('#veTranscriptRows .ve-transcript-row').length === 2")
    assert page.input_value("#veTranscriptRows .ve-transcript-row:first-child .ve-tr-start") == "00:00:00.50"
    page.fill("#veTranscriptRows .ve-transcript-row:first-child .ve-tr-text", "שלום עולם ערוך")
    page.click("#veTranscriptRows .ve-transcript-row:nth-child(2) button")  # מחיקת השורה השנייה
    page.evaluate("() => saveVeEditedTranscript()")
    page.wait_for_function("() => document.getElementById('veTranscriptStatus').textContent.includes('נשמר')")
    saved = captions.edited_captions_path(web_app.CAPTIONS_EDITS_DIR, str(clip))
    with open(saved, encoding="utf-8") as f:
        body = f.read()
    assert "שלום עולם ערוך" in body and "שורה שנייה" not in body
    # שורה עם זמן לא תקין מסומנת ולא נשמרת
    page.fill("#veTranscriptRows .ve-transcript-row:first-child .ve-tr-end", "abc")
    page.evaluate("() => saveVeEditedTranscript()")
    page.wait_for_function("() => document.getElementById('veTranscriptStatus').textContent.includes('זמן לא תקין')")
    page.evaluate("() => { document.getElementById('veTranscriptRows').innerHTML = ''; return loadVeEditedTranscript(); }")
    page.wait_for_function("() => document.querySelectorAll('#veTranscriptRows .ve-transcript-row').length === 1")
    page.evaluate("() => { deleteVeEditedTranscript(); }")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.getElementById('veTranscriptStatus').textContent.includes('נמחק')")
    assert not os.path.exists(saved)
