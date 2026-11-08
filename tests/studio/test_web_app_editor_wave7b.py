# tests/studio/test_web_app_editor_wave7b.py
#
# גל 7ב של 102-ההצעות - חיווט הווב (שדות -> דגלי CLI, קובץ שכבות, זיהוי הייליטס),
# רינדור אמיתי עם ffmpeg (שכבות/קישוטים/עיבוד-אחרי) ודפדפן אמיתי (עורך השכבות).
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
from utils.video import video_editor_profiles as vep
from utils.video.video_editor_field_help import FIELD_HELP
from entrypoints.web import frontend_assembly as fa

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")

WAVE7B_FIELDS = (
    "layers", "timestamp_overlay", "progress_bar", "progress_bar_color", "progress_bar_position", "progress_bar_height",
    "frame_thickness", "frame_color", "vignette", "ken_burns", "watermark_move_seconds", "pip_audio", "pip_duck",
    "intro_path", "outro_path", "boomerang", "loop_count", "meta_title", "meta_comment", "chapters",
    "export_gif", "gif_width", "gif_fps", "export_audio", "caption_max_chars",
)


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


def _ffmpeg(*args):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-v", "error", "-y", *args], capture_output=True, timeout=120, creationflags=NO_WINDOW_FLAGS, check=True)


def _make_clip(path, duration=2, size="320x180", audio=False, freq=440):
    args = ["-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=10"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}", "-c:a", "aac", "-shortest"]
    _ffmpeg(*args, "-pix_fmt", "yuv420p", str(path))


def _probe_json(path):
    from utils.shared.ffmpeg_locator import get_ffprobe_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    out = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries",
                          "stream=codec_type,width,height:format=duration:format_tags=title,comment:chapter=start_time:chapter_tags=title",
                          "-of", "json", str(path)], capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True).stdout
    return json.loads(out)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "profiles" / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "profiles" / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "profiles" / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app, "LAYERS_DIR", str(tmp_path / "layers"))
    monkeypatch.setattr(web_app, "BATCH_OVERRIDES_DIR", str(tmp_path / "overrides"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


def _args(payload, layers_path=None):
    return web_app._build_extra_args("video_editor.py", payload, layers_path=layers_path)


# --- מיפוי שדות -> דגלים ---

def test_wave7b_defaults_add_no_flags():
    defaults = {
        "layers": [], "timestamp_overlay": "", "progress_bar": False, "progress_bar_color": "#FF0000", "progress_bar_position": "bottom",
        "progress_bar_height": 8, "frame_thickness": 0, "frame_color": "#FFFFFF", "vignette": "none", "ken_burns": 0,
        "watermark_move_seconds": 0, "pip_audio": False, "pip_duck": False, "intro_path": "", "outro_path": "", "boomerang": False,
        "loop_count": 1, "meta_title": "", "meta_comment": "", "chapters": "", "export_gif": "", "gif_width": 480, "gif_fps": 12,
        "export_audio": "",
    }
    joined = " ".join(_args(defaults))
    for flag in ("--layers-json", "--timestamp-overlay", "--progress-bar", "--frame-thickness", "--vignette", "--ken-burns",
                 "--watermark-move-seconds", "--pip-audio", "--intro-path", "--boomerang", "--loop-count", "--meta-title",
                 "--chapters", "--export-gif", "--gif-width", "--export-audio"):
        assert flag not in joined, flag


def test_wave7b_fields_map_to_flags():
    args = _args({
        "layers": [{"type": "text", "text": "hi"}], "timestamp_overlay": "bottom-left", "progress_bar": True,
        "progress_bar_color": "00ff00", "progress_bar_position": "top", "progress_bar_height": 12, "frame_thickness": 6,
        "frame_color": "#112233", "vignette": "strong", "ken_burns": 0.15, "watermark_path": "C:/w.png", "watermark_move_seconds": 5,
        "pip_path": "C:/p.mp4", "keep_audio": True, "pip_audio": True, "pip_duck": True, "intro_path": "C:/i.mp4", "outro_path": "C:/o.mp4",
        "boomerang": True, "loop_count": 3, "meta_title": "Title", "meta_comment": "Note", "chapters": "0:00 A\n\n1:00 B\n",
        "export_gif": "both", "gif_width": 320, "gif_fps": 15, "export_audio": "m4a",
    }, layers_path="C:/tmp/layers.json")
    joined = " ".join(args)
    for expected in ("--layers-json C:/tmp/layers.json", "--timestamp-overlay bottom-left", "--progress-bar-color #00FF00",
                     "--progress-bar-position top", "--progress-bar-height 12", "--frame-thickness 6", "--frame-color #112233",
                     "--vignette strong", "--ken-burns 0.15", "--watermark-move-seconds 5", "--pip-audio", "--pip-duck",
                     "--intro-path C:/i.mp4", "--outro-path C:/o.mp4", "--boomerang", "--loop-count 3", "--meta-title Title",
                     "--meta-comment Note", "--export-gif both", "--gif-width 320", "--gif-fps 15", "--export-audio m4a"):
        assert expected in joined, expected
    assert args[args.index("--chapters") + 1] == "0:00 A|1:00 B"


def test_wave7b_conditional_flags():
    assert "--layers-json" in _args({"layers": [{"type": "text", "text": "x"}]})  # תצוגת-פקודה: placeholder
    assert "<layers.json>" in _args({"layers": [{"type": "text", "text": "x"}]})
    assert "--layers-json" not in _args({"layers": [{"type": "text", "text": "  "}]})
    assert "--watermark-move-seconds" not in _args({"watermark_move_seconds": 5})
    assert "--pip-audio" not in _args({"pip_path": "C:/p.mp4", "pip_audio": True})  # בלי keep_audio
    assert "--pip-duck" not in _args({"pip_path": "C:/p.mp4", "pip_audio": False, "pip_duck": True, "keep_audio": True})
    assert "--progress-bar-color" not in _args({"progress_bar": False, "progress_bar_color": "#00FF00"})
    assert "--frame-color" not in _args({"frame_thickness": 0, "frame_color": "#00FF00"})
    assert "--timestamp-overlay" not in _args({"timestamp_overlay": "middle"})
    assert "--loop-count" not in _args({"loop_count": "abc"})
    assert "--loop-count 10" in " ".join(_args({"loop_count": 99}))
    assert "--gif-width" not in _args({"gif_width": 320})  # בלי export_gif


def test_wave7b_fields_registered_in_profiles_help_and_page():
    html = fa.assemble_inline_page()
    for field in WAVE7B_FIELDS:
        assert field in vep.PROFILE_FIELDS, field
        assert field in FIELD_HELP, field
        assert len(FIELD_HELP[field].term) <= 30
    for element_id in ("veLayers", "veLayersRows", "veTimestampOverlay", "veProgressBar", "veFrameThickness", "veVignette", "veKenBurns",
                       "veWatermarkMoveSeconds", "vePipAudio", "vePipDuck", "veIntroPath", "veOutroPath", "veBoomerang", "veLoopCount",
                       "veMetaTitle", "veChapters", "veExportGif", "veGifWidth", "veExportAudio", "veHighlightThreshold", "veCaptionMaxChars"):
        assert f'id="{element_id}"' in html, element_id


def test_layers_profile_roundtrip():
    layers = [{"type": "text", "text": "שלום", "start": 1, "end": 3, "animation": "typewriter"}]
    vep.save_profile("L", {"layers": layers, "progress_bar": True})
    assert vep.load_profiles()["L"]["layers"] == layers


def test_run_writes_sanitized_layers_file_and_passes_path(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: captured.update(k))
    folder = tmp_path / "clips"
    folder.mkdir()
    image = tmp_path / "s.png"
    image.write_bytes(b"png")
    script_id = next(s["id"] for s in client.get("/api/scripts").json() if s["id"].endswith("video_editor.py"))
    res = client.post("/api/run", json={"script": script_id, "folder": str(folder), "layers": [
        {"type": "text", "text": "hello", "start": 0, "end": 2},
        {"type": "image", "path": str(tmp_path / "missing.png")},
        {"type": "image", "path": str(image), "scale": 0.3},
    ]})
    assert res.status_code == 200, res.text
    args = captured["extra_args"]
    path = args[args.index("--layers-json") + 1]
    assert os.path.dirname(path) == web_app.LAYERS_DIR
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    assert [layer["type"] for layer in saved] == ["text", "image"]  # התמונה החסרה סוננה בשרת
    assert saved[1]["scale"] == 0.3


# --- item 85: זיהוי הייליטס ---

@needs_ffmpeg
def test_detect_highlights_endpoint_finds_loud_bursts(tmp_path):
    clip = tmp_path / "match.mp4"
    # 30 שניות שקטות עם שני פיצוצי-עוצמה (ב-8s וב-22s)
    _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=30:size=160x90:rate=5",
            "-f", "lavfi", "-i", "aevalsrc='0.01*sin(2*PI*220*t)+if(between(t,8,8.5)+between(t,22,22.5),0.9*sin(2*PI*880*t),0)':d=30",
            "-c:a", "aac", "-shortest", "-pix_fmt", "yuv420p", str(clip))
    data = client.post("/api/video_editor/detect_highlights", json={"folder": str(tmp_path), "file": "match.mp4", "before": 3, "after": 2, "min_gap": 5}).json()
    assert data["file"] == "match.mp4" and len(data["peaks"]) == 2
    assert 7.5 <= data["peaks"][0] <= 8.6 and 21.5 <= data["peaks"][1] <= 22.6
    assert data["remove_ranges"][0][0] == 0.0 and data["kept_seconds"] == pytest.approx(10, abs=0.5)


@needs_ffmpeg
def test_detect_highlights_errors(tmp_path):
    assert client.post("/api/video_editor/detect_highlights", json={"folder": str(tmp_path / "nope")}).status_code == 400
    assert client.post("/api/video_editor/detect_highlights", json={"folder": str(tmp_path)}).status_code == 400  # אין וידאו
    _make_clip(tmp_path / "silent.mp4", duration=1)
    res = client.post("/api/video_editor/detect_highlights", json={"folder": str(tmp_path), "file": "silent.mp4"})
    assert res.status_code == 400 and "פס-קול" in res.json()["error"]


# --- e2e אמיתי: שכבות, קישוטים ועיבוד-אחרי ---

def _outputs(name, orientation, extensions=(".mp4",)):
    return [os.path.join(WORKSPACE_DIR, "studio", orientation, f"{name}_edited_{orientation}{ext}") for ext in extensions]


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


def _run(tmp_path, *args):
    result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(tmp_path / "in"), "--force", *args],
                            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=300)
    line = next((ln for ln in result.stdout.splitlines() if ln.startswith("RESULT: ")), None)
    assert line, result.stdout + result.stderr
    return json.loads(line[len("RESULT: "):]), result.stdout


@needs_ffmpeg
def test_e2e_layers_decor_and_pip_ducking_render(tmp_path):
    (tmp_path / "in").mkdir()
    _make_clip(tmp_path / "in" / "w7blay.mp4", duration=3, audio=True, freq=300)
    _make_clip(tmp_path / "pip.mp4", duration=3, size="160x90", audio=True, freq=900)
    _ffmpeg("-f", "lavfi", "-i", "color=c=yellow:s=64x32", "-frames:v", "1", str(tmp_path / "sticker.png"))
    _ffmpeg("-f", "lavfi", "-i", "color=c=white:s=60x30", "-frames:v", "1", str(tmp_path / "wm.png"))
    layers = tmp_path / "layers.json"
    layers.write_text(json.dumps([
        {"type": "text", "text": "fade 100%: yes", "start": 0, "end": 2, "animation": "fade", "box": True},
        {"type": "text", "text": "typed", "start": 0.5, "animation": "typewriter", "position": "center"},
        {"type": "text", "text": "slide", "start": 1, "animation": "slide", "position": "top-left"},
        {"type": "timer", "start": 0, "timer_mode": "countdown", "position": "top-right"},
        {"type": "image", "path": str(tmp_path / "sticker.png"), "start": 1, "end": 2, "opacity": 0.7},
    ]), encoding="utf-8")
    paths = _outputs("w7blay", "vertical")
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run(tmp_path, "--vertical", "--keep-audio", "--layers-json", str(layers), "--timestamp-overlay", "bottom-right",
                              "--progress-bar", "--frame-thickness", "8", "--vignette", "light", "--ken-burns", "0.1",
                              "--watermark_path", str(tmp_path / "wm.png"), "--watermark-move-seconds", "1",
                              "--pip", str(tmp_path / "pip.mp4"), "--pip-audio", "--pip-duck")
        assert parsed["files_created"] == 1 and parsed["errors"] == 0, stdout
        info = _probe_json(paths[0])
        video = next(s for s in info["streams"] if s["codec_type"] == "video")
        assert (video["width"], video["height"]) == (1080, 1920)
        assert any(s["codec_type"] == "audio" for s in info["streams"])
        assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.35)
    finally:
        _cleanup(paths, parsed)


@needs_ffmpeg
def test_e2e_post_steps_bumpers_boomerang_loop_metadata_and_exports(tmp_path):
    (tmp_path / "in").mkdir()
    _make_clip(tmp_path / "in" / "w7bpost.mp4", duration=2, audio=True)
    _make_clip(tmp_path / "intro.mp4", duration=1, size="640x480")  # בלי שמע -> שקט מושלם אוטומטית
    _make_clip(tmp_path / "outro.mp4", duration=1, size="200x200", audio=True, freq=600)
    paths = _outputs("w7bpost", "horizontal", (".mp4", ".gif", ".webp", ".mp3"))
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run(tmp_path, "--keep-audio", "--intro-path", str(tmp_path / "intro.mp4"), "--outro-path", str(tmp_path / "outro.mp4"),
                              "--boomerang", "--loop-count", "2", "--meta-title", "My clip", "--meta-comment", "made in tests",
                              "--chapters", "0:00 Start|0:01 Middle", "--export-gif", "both", "--gif-width", "160", "--export-audio", "mp3")
        assert parsed["files_created"] == 1, stdout
        for marker in ("נוספו intro + outro", "boomerang", "x2", "מטא-דאטה + 2 פרקים", "יוצא GIF", "יוצא WEBP", "יוצא MP3"):
            assert marker in stdout, (marker, stdout)
        info = _probe_json(paths[0])
        # (1 intro + 2 תוכן + 1 outro) = 4s -> בומרנג 8s -> פעמיים 16s
        assert float(info["format"]["duration"]) == pytest.approx(16.0, abs=0.6)
        assert info["format"]["tags"]["title"] == "My clip"
        assert [c["tags"]["title"] for c in info["chapters"]] == ["Start", "Middle"]
        assert float(info["chapters"][1]["start_time"]) == pytest.approx(2.0, abs=0.05)  # מוזז ב-1s של ה-intro
        for extra in paths[1:]:
            assert os.path.getsize(extra) > 0, extra
        assert not [f for f in os.listdir(os.path.dirname(paths[0])) if f.startswith(".w7bpost")]  # אין קבצים זמניים שנשארו
    finally:
        _cleanup(paths, parsed)


@needs_ffmpeg
def test_e2e_missing_bumper_and_long_boomerang_are_non_fatal(tmp_path):
    (tmp_path / "in").mkdir()
    _make_clip(tmp_path / "in" / "w7bskip.mp4", duration=1)
    paths = _outputs("w7bskip", "horizontal")
    _cleanup(paths)
    parsed = None
    try:
        parsed, stdout = _run(tmp_path, "--intro-path", str(tmp_path / "nope.mp4"), "--export-audio", "wav")
        assert parsed["files_created"] == 1, stdout
        assert "קובץ ה-intro לא נמצא" in stdout and "לפלט אין פס-קול" in stdout
    finally:
        _cleanup(paths, parsed)


# --- דפדפן אמיתי ---

def _set(page, element_id, value):
    page.evaluate(
        """([id, value]) => { const el = document.getElementById(id);
          if (el.type === 'checkbox') el.checked = value; else el.value = value;
          el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }""",
        [element_id, value],
    )


def test_browser_layers_editor_add_edit_reorder_and_restore(editor_page):
    page = editor_page
    page.evaluate("() => { addVeLayer('text'); addVeLayer('timer'); }")
    rows = page.locator("#veLayersRows .ve-layer-row")
    assert rows.count() == 2
    page.locator("#veLayersRows .ve-layer-row").nth(0).locator(".ve-layer-content").fill("כותרת")
    page.locator("#veLayersRows .ve-layer-row").nth(0).locator("input[aria-label='סיום']").fill("0:04")
    page.locator("#veLayersRows .ve-layer-row").nth(0).locator("input[aria-label='סיום']").dispatch_event("change")
    layers = page.evaluate("() => _collectRunOptions().layers")
    assert layers[0]["text"] == "כותרת" and layers[0]["end"] == 4 and layers[1]["type"] == "timer"
    page.locator("#veLayersRows .ve-layer-row").nth(0).locator("button", has_text="↓").click()
    assert page.evaluate("() => _collectRunOptions().layers.map(l => l.type)") == ["timer", "text"]
    page.locator("#veLayersRows .ve-layer-row").nth(0).locator(".ve-layer-remove").click()
    assert page.evaluate("() => _collectRunOptions().layers.map(l => l.type)") == ["text"]
    page.wait_for_function("() => document.getElementById('veSummaryText').textContent.includes('1 שכבות')")
    page.evaluate("() => _applyGenericVeFields({layers: [{type: 'image', path: 'C:/x.png', scale: 0.5, start: 2, end: null, position: 'center', opacity: 1}]})")
    assert rows.count() == 1
    assert page.evaluate("() => document.querySelector('#veLayersRows .ve-layer-row').dataset.type") == "image"
    assert page.input_value("#veLayersRows .ve-layer-row input[type=number]") == "50"
    page.evaluate("() => _applyGenericVeFields({})")  # פרופיל ישן בלי שכבות -> עורך ריק
    assert rows.count() == 0


def test_browser_wave7b_dependencies_rules_and_command(editor_page):
    page = editor_page
    assert page.evaluate("() => document.getElementById('veProgressBarColor').closest('.ve-row').classList.contains('ve-dep-hidden')")
    _set(page, "veProgressBar", True)
    page.wait_for_function("() => !document.getElementById('veProgressBarColor').closest('.ve-row').classList.contains('ve-dep-hidden')")
    _set(page, "veExportAudio", "mp3")
    page.wait_for_function("() => document.getElementById('veWarningsBox').textContent.includes('ייצוא אודיו בלבד')")
    _set(page, "veChapters", "0:00 פתיחה\n1:00 סוף")
    _set(page, "veLoopCount", "3")
    # התקציר מתעדכן ב-debounce - מחכים לשני השבבים, לא רק לראשון (נמצא ב-CI)
    page.wait_for_function("() => { const t = document.getElementById('veSummaryText').textContent; return t.includes('2 פרקים') && t.includes('x3'); }")
    opts = page.evaluate("() => _collectRunOptions()")
    assert opts["progress_bar"] is True and opts["loop_count"] == 3 and opts["export_audio"] == "mp3"
