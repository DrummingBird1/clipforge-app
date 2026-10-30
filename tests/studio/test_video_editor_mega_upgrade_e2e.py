# tests/studio/test_video_editor_mega_upgrade_e2e.py
#
# טסטי end-to-end אמיתיים (מריצים my_scripts/video/video_editor.py כתת-תהליך
# אמיתי, בדיוק כמו test_video_editor_advanced_e2e.py) לתכונות ה"שדרוג הענקי"
# שנוספו לעורך-העל: LUT, auto-levels, אינטרפולציית פריימים חלקה, שער רעש,
# הסרת שקט באמצע הקובץ, ייצוב וידאו, כרומה קי, versioning (--force snapshot),
# ודוח סיכום ריצה.
import os
from tests import PROJECT_ROOT
import shutil
import subprocess
import tempfile
import sys


import csv
import json

import pytest
from openpyxl import load_workbook

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.video.video_editor import resolve_sig_path

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
REPORTS_DIR = os.path.join(WORKSPACE_DIR, "reports")
# המונה של הטסטים בתיקייה זמנית (utils/video/video_editor_counter.py קורא את משתנה הסביבה) - לעולם
# לא data/video_editor_counter.txt של המשתמש. קודם הטסטים שמרו ושחזרו את הקובץ האמיתי, ושתי
# ריצות במקביל מחקו אותו (אחת שמרה "אין קובץ" אחרי שהשנייה כבר מחקה).
COUNTER_PATH = os.path.join(tempfile.mkdtemp(prefix="ve_counter_test_"), "video_editor_counter.txt")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_synthetic_video(path, duration=1, width=320, height=240, rate=10):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={rate}",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_synthetic_video_with_audio(path, duration=1, width=320, height=240, rate=10):
    # כמו _make_synthetic_video, אבל עם ערוץ אודיו אמיתי (טון sine) - נדרש
    # לטסטים שמעבירים אודיו דרך filter_complex (למשל --noise-gate, agate על
    # [0:a]) - קלט בלי אודיו כלל היה גורם ל-ffmpeg לכשול על "matches no
    # streams" בבניית ה-filtergraph, אבל עדיין משאיר קובץ פלט ריק/פגום מאחוריו
    # (ffmpeg פותח את קובץ הפלט למיוקס לפני שנכשל על בניית הפילטרגרף) - מה
    # שגרם לטסט עם os.path.exists(output_path) בלבד "לעבור" בלי לבדוק בכלל
    # שהרינדור הצליח באמת.
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={rate}",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_green_video(path, duration=1, width=320, height=240):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"color=0x00FF00:size={width}x{height}:duration={duration}:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_solid_color_video(path, hex_color, duration=1, width=320, height=240):
    # item: PiP - שני מקורות בצבע-אחיד-שונה (לא testsrc, שהתבנית שלו לא
    # מובטחת "לא-אדומה"/"לא-כחולה" בפינה מסוימת) כדי שדגימת פיקסל בפינת
    # ה-overlay תהיה חד-משמעית, זהה בעיקרון ל-_make_green_video אבל עם צבע
    # פרמטרי כדי להבחין במפורש בין הווידאו הראשי לבין מקור ה-PiP.
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"color={hex_color}:size={width}x{height}:duration={duration}:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_video_with_mid_silence(path, width=320, height=240):
    # טון(2s) - שקט(2s) - טון(2s) = 6 שניות, עם שקט *באמצע* (לא בקצוות) -
    # שונה מ-_make_video_with_trailing_silence (test_video_editor_advanced_e2e.py).
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"testsrc=duration=6:size={width}x{height}:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
        "-filter_complex", "[1:a][2:a][3:a]concat=n=3:v=0:a=1[outa]",
        "-map", "0:v", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_identity_cube_lut(path):
    # LUT זהות (לא משנה שום צבע) - גודל 2x2x2 המינימלי, מספיק כדי לוודא
    # ש-lut3d נטען ומופעל בלי לקרוס, בלי לבדוק תזוזת-צבע ספציפית.
    with open(path, "w", encoding="utf-8") as f:
        f.write("LUT_3D_SIZE 2\n")
        for b in (0.0, 1.0):
            for g in (0.0, 1.0):
                for r in (0.0, 1.0):
                    f.write(f"{r} {g} {b}\n")


def _pixel_rgb_at(path, x, y):
    cmd = [
        get_ffmpeg_exe(), "-v", "error", "-i", path,
        "-vf", f"crop=2:2:{x}:{y}", "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert len(result.stdout) == 12, f"ציפינו לבלוק 2x2 (12 בתים), קיבלנו {len(result.stdout)}"
    return tuple(result.stdout[:3])


def _color_distance(rgb_a, rgb_b):
    return sum(abs(a - b) for a, b in zip(rgb_a, rgb_b))


def _probe_dimensions(path):
    cmd = [
        get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return result.stdout.strip()


def _probe_fps(path):
    cmd = [
        get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return result.stdout.strip()


def _probe_duration(path):
    cmd = [get_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return float(result.stdout.strip())


def _run_script(args, timeout=120):
    return subprocess.run(
        [sys.executable, SCRIPT] + args, cwd=BASE_DIR, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, creationflags=NO_WINDOW_FLAGS,
        env={**os.environ, "CLIPFORGE_VIDEO_EDITOR_COUNTER_PATH": COUNTER_PATH},
    )


def test_the_numbering_tests_never_touch_the_real_counter():
    real = os.path.join(BASE_DIR, "data", "video_editor_counter.txt")
    assert os.path.normcase(os.path.abspath(COUNTER_PATH)) != os.path.normcase(os.path.abspath(real))
    assert not os.path.normcase(os.path.abspath(COUNTER_PATH)).startswith(os.path.normcase(os.path.join(BASE_DIR, "data")))


def _result_json(stdout):
    for line in stdout.splitlines():
        if line.startswith("RESULT: "):
            return json.loads(line[len("RESULT: "):])
    raise AssertionError(f"לא נמצאה שורת RESULT: בפלט:\n{stdout}")


# --- LUT (item) ---

def test_lut_applies_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "lut_clip.mp4"
    _make_synthetic_video(str(src_path))
    lut_path = tmp_path / "identity.cube"
    _make_identity_cube_lut(str(lut_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "lut_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--lut", str(lut_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


def test_lut_missing_file_warns_and_continues_without_it(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "lut_missing_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "lut_missing_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--lut", str(tmp_path / "does_not_exist.cube")])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "קובץ ה-LUT לא נמצא" in result.stdout
        assert os.path.exists(output_path)  # הרינדור עצמו לא נפגע
    finally:
        remove_video_editor_output(output_path)


# --- auto-levels (item) ---

def test_auto_levels_renders_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "auto_levels_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "auto_levels_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--auto-levels"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- אינטרפולציית פריימים חלקה (item) ---

def test_smooth_fps_upscales_to_target_rate(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smooth_fps_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1, rate=10)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "smooth_fps_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--fps", "30", "--smooth-fps"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_fps(output_path) == "30/1"
    finally:
        remove_video_editor_output(output_path)


def test_smooth_fps_ignored_with_hwaccel(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smooth_fps_hwaccel_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "smooth_fps_hwaccel_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "hevc", "--hwaccel", "--smooth-fps"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--smooth-fps מתעלם" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- שער רעש (item) ---

def test_noise_gate_renders_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "noise_gate_clip.mp4"
    _make_synthetic_video_with_audio(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "noise_gate_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--noise-gate"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert '"files_created": 1' in result.stdout, result.stdout  # לא רק "קובץ קיים" - הרינדור עצמו הצליח בפועל
    finally:
        remove_video_editor_output(output_path)


def test_noise_gate_ignored_without_keep_audio(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "noise_gate_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "noise_gate_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--noise-gate"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--noise-gate מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- הסרת שקט באמצע הקובץ (item) ---

def test_remove_mid_silence_shortens_output_and_keeps_av_in_sync(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "mid_silence_clip.mp4"
    _make_video_with_mid_silence(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "mid_silence_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--remove-mid-silence"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "טווחי שקט זוהו" in result.stdout
        assert os.path.exists(output_path)
        duration = _probe_duration(output_path)
        # מקור 6s (2 טון + 2 שקט + 2 טון) - אחרי הסרה, ~4s (רק הטון) נשאר.
        assert duration < 5.0, f"ציפינו שהשקט באמצע יוסר (~4s), קיבלנו {duration}"
    finally:
        remove_video_editor_output(output_path)


def test_remove_mid_silence_ignored_without_keep_audio(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "mid_silence_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "mid_silence_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--remove-mid-silence"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--remove-mid-silence מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


def test_remove_mid_silence_ignored_when_combined_with_explicit_trim(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "mid_silence_vs_trim_clip.mp4"
    _make_video_with_mid_silence(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "mid_silence_vs_trim_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
            "--remove-mid-silence", "--trim-start", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--remove-mid-silence מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- ייצוב וידאו (item) ---

def test_stabilize_renders_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "stabilize_clip.mp4"
    _make_synthetic_video(str(src_path), duration=2)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "stabilize_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--stabilize"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ניתוח ייצוב וידאו הושלם" in result.stdout
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


def test_stabilize_ignored_with_hwaccel(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "stabilize_hwaccel_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "stabilize_hwaccel_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "hevc", "--hwaccel", "--stabilize"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--stabilize מתעלם" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- כרומה קי (item) ---

def test_chromakey_replaces_green_with_black_background(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "chromakey_clip.mp4"
    _make_green_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "chromakey_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--chromakey"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        center_pixel = _pixel_rgb_at(output_path, 960, 540)
        assert _color_distance(center_pixel, (0, 255, 0)) > 100, f"עדיין נראה ירוק - הכרומה קי לא הופעל: {center_pixel}"
        assert _color_distance(center_pixel, (0, 0, 0)) < 60, f"ציפינו לרקע שחור (ברירת המחדל) אחרי הסרת הירוק: {center_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_chromakey_custom_bg_color(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "chromakey_bg_clip.mp4"
    _make_green_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "chromakey_bg_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--chromakey", "--chromakey-bg-color", "0xFF0000",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        center_pixel = _pixel_rgb_at(output_path, 960, 540)
        assert _color_distance(center_pixel, (255, 0, 0)) < 80, f"ציפינו לרקע אדום מותאם-אישית: {center_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_chromakey_ignored_with_blur_background(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "chromakey_vs_blur_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "chromakey_vs_blur_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--chromakey", "--blur-background"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--chromakey מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


def test_chromakey_ignored_with_hwaccel(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "chromakey_hwaccel_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "chromakey_hwaccel_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "hevc", "--hwaccel", "--chromakey"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--chromakey מתעלם" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- versioning (item: snapshot לפני --force) ---

def test_force_rerender_snapshots_previous_output(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "versioning_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "versioning_clip_edited_horizontal.mp4")
    previous_dir = os.path.join(HORIZONTAL_OUTPUT_DIR, "_previous")
    remove_video_editor_output(output_path)
    try:
        first = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert first.returncode == 0, first.stdout + first.stderr
        assert os.path.exists(output_path)

        second = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--force"])
        assert second.returncode == 0, second.stdout + second.stderr
        assert "גרסה קודמת" in second.stdout
        assert os.path.isdir(previous_dir)
        snapshotted = [f for f in os.listdir(previous_dir) if f.endswith("versioning_clip_edited_horizontal.mp4")]
        assert snapshotted, f"ציפינו לגרסה קודמת שמורה תחת _previous/, קיבלנו: {os.listdir(previous_dir)}"
        assert os.path.exists(output_path)  # הפלט החדש עדיין נוצר כרגיל
    finally:
        remove_video_editor_output(output_path)
        if os.path.isdir(previous_dir):
            shutil.rmtree(previous_dir)


# --- דוח סיכום ריצה (item) ---

def test_render_report_includes_timing_in_result_and_log(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "report_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "report_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[REPORT]" in result.stdout
        data = _result_json(result.stdout)
        assert "elapsed_seconds" in data
        assert data["elapsed_seconds"] >= 0
        assert data["avg_seconds_per_file"] is not None
    finally:
        remove_video_editor_output(output_path)


# --- שימור רזולוציית מקור (item: --preserve-resolution) ---

def test_preserve_resolution_horizontal_keeps_native_size(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "preserve_horizontal_clip.mp4"
    _make_synthetic_video(str(src_path), width=640, height=360)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "preserve_horizontal_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--preserve-resolution"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "640x360"
        assert "--preserve-resolution" in result.stdout
    finally:
        remove_video_editor_output(output_path)


def test_preserve_resolution_disabled_still_forces_fixed_1080p(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "no_preserve_clip.mp4"
    _make_synthetic_video(str(src_path), width=640, height=360)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "no_preserve_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


def test_preserve_resolution_vertical_does_not_downscale_larger_than_1080p_source(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "preserve_vertical_clip.mp4"
    _make_synthetic_video(str(src_path), width=2560, height=1440, duration=1, rate=5)

    vertical_output_dir = os.path.join(WORKSPACE_DIR, "studio", "vertical")
    output_path = os.path.join(vertical_output_dir, "preserve_vertical_clip_edited_vertical.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--vertical", "--preserve-resolution"], timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        # 2560x1440 גדול מ-1080p - הקופסה האנכית 9:16 נשארת בגודל תואם-מקור
        # (1440x2560), לא מוקטנת ל-1080x1920 הקבועים.
        assert _probe_dimensions(output_path) == "1440x2560"
    finally:
        remove_video_editor_output(output_path)


# --- ביטול סיומת שם קובץ הפלט (item: --no-suffix) ---

def test_no_suffix_drops_edited_suffix_from_output_filename(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "no_suffix_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "no_suffix_clip.mp4")
    suffixed_output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "no_suffix_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    remove_video_editor_output(suffixed_output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--no-suffix"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert not os.path.exists(suffixed_output_path)
    finally:
        remove_video_editor_output(output_path)
        remove_video_editor_output(suffixed_output_path)


# --- קידוד מספר סרטונים בו-זמנית ודרגות מאמץ (item: --parallel/--effort) ---

def test_parallel_encodes_all_files_and_reports_parallel_count(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_paths = []
    for i in range(3):
        src_path = input_dir / f"parallel_clip_{i}.mp4"
        _make_synthetic_video(str(src_path), duration=1)
        output_paths.append(os.path.join(HORIZONTAL_OUTPUT_DIR, f"parallel_clip_{i}_edited_horizontal.mp4"))
    for output_path in output_paths:
        remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--parallel", "3"], timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "מקודד עד 3 סרטונים בו-זמנית" in result.stdout
        for output_path in output_paths:
            assert os.path.exists(output_path)
        data = _result_json(result.stdout)
        assert data["files_created"] == 3
        assert data["parallel"] == 3
    finally:
        for output_path in output_paths:
            remove_video_editor_output(output_path)


def test_parallel_invalid_value_clamped_to_one(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "parallel_clamp_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "parallel_clamp_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--parallel", "0"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--parallel 0 לא תקין" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- מגבלת-מקביליות אמיתית ל-NVENC (item: --max-concurrent-nvenc) - כל הבדיקות
# משתמשות ב---validate-only כדי להישאר מהירות ולא תלויות בכרטיס NVIDIA אמיתי:
# NVENC_SEMAPHORE נבנה לפני לולאת הקבצים בלי קשר ל---validate-only, אז אפשר
# להוכיח שהבדיקה/ההודעות רצות נכון בלי לחכות לרינדור אמיתי בכלל. ---

def test_max_concurrent_nvenc_manual_value_skips_auto_probe(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "nvenc_manual_clip.mp4"))

    result = _run_script([
        "--input_dir", str(input_dir), "--codec", "hevc", "--parallel", "2",
        "--max-concurrent-nvenc", "1", "--validate-only",
    ])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "מגבלת NVENC מקבילים: 1 (הוגדר ידנית עם --max-concurrent-nvenc)" in result.stdout
    assert "בודק מגבלת NVENC בפועל" not in result.stdout


def test_max_concurrent_nvenc_auto_probes_when_not_set(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "nvenc_auto_clip.mp4"))

    result = _run_script([
        "--input_dir", str(input_dir), "--codec", "hevc", "--parallel", "2", "--validate-only",
    ])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "בודק מגבלת NVENC בפועל" in result.stdout
    # תלוי-חומרה: או שזוהה מספר סשנים בפועל, או שלא זוהה אף סשן (בלי GPU של NVIDIA) - אחד משני המסרים חייב להופיע.
    assert ("מגבלת NVENC בפועל שזוהתה" in result.stdout) or ("לא זוהה אף סשן NVENC פעיל" in result.stdout)


def test_max_concurrent_nvenc_not_probed_with_h264(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "nvenc_h264_clip.mp4"))

    result = _run_script([
        "--input_dir", str(input_dir), "--codec", "h264", "--parallel", "2", "--validate-only",
    ])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "בודק מגבלת NVENC בפועל" not in result.stdout
    assert "מגבלת NVENC" not in result.stdout


def test_max_concurrent_nvenc_not_probed_with_parallel_one(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "nvenc_sequential_clip.mp4"))

    result = _run_script([
        "--input_dir", str(input_dir), "--codec", "hevc", "--validate-only",
    ])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "בודק מגבלת NVENC בפועל" not in result.stdout
    assert "מגבלת NVENC" not in result.stdout


def test_effort_low_renders_successfully_and_reports_in_result(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "effort_low_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "effort_low_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--effort", "low"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        data = _result_json(result.stdout)
        assert data["effort"] == "low"
    finally:
        remove_video_editor_output(output_path)


def test_effort_auto_renders_successfully_and_logs_chosen_level(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "effort_auto_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "effort_auto_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--effort", "auto"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert "--effort auto בחר" in result.stdout
        data = _result_json(result.stdout)
        assert data["effort"] == "auto"
        assert data["files_created"] == 1
    finally:
        remove_video_editor_output(output_path)


# --- מיכל יצוא (item: --container) ---

def test_container_mkv_produces_mkv_output(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "container_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "container_clip_edited_horizontal.mkv")
    mp4_output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "container_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    remove_video_editor_output(mp4_output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--container", "mkv"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert not os.path.exists(mp4_output_path)
        probe_cmd = [get_ffprobe_exe(), "-v", "error", "-show_entries", "format=format_name", "-of", "csv=p=0", output_path]
        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
        assert "matroska" in probe_result.stdout.lower()
    finally:
        remove_video_editor_output(output_path)
        remove_video_editor_output(mp4_output_path)


def test_container_webm_rejected_by_argparse(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "webm_clip.mp4"
    _make_synthetic_video(str(src_path))

    result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--container", "webm"])
    assert result.returncode != 0  # argparse choices לא כולל webm בכוונה - ראו SUPPORTED_CONTAINERS


# --- תבנית שם-קובץ מותאמת אישית (item: --output-template) ---

def test_output_template_overrides_default_naming(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "template_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "MYTEMPLATE_template_clip_h264.mp4")
    default_output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "template_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    remove_video_editor_output(default_output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--output-template", "MYTEMPLATE_{name}_{codec}"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert not os.path.exists(default_output_path)
    finally:
        remove_video_editor_output(output_path)
        remove_video_editor_output(default_output_path)


def test_output_template_invalid_placeholder_fails_fast(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "bad_template_clip.mp4"
    _make_synthetic_video(str(src_path))

    result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--output-template", "{unknown_field}"])
    assert result.returncode == 0, result.stdout + result.stderr  # הסקריפט לא קורס - exit() רגיל
    assert "[ERROR]" in result.stdout
    assert "--output-template" in result.stdout


# --- אימות מוקדם של שרשרת הפילטרים (item: --validate-only) ---

def test_validate_only_valid_combination_reports_valid_without_full_render(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "validate_ok_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "validate_ok_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--auto-levels", "--validate-only"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[VALID]" in result.stdout
        assert not os.path.exists(output_path)  # --validate-only לא מפיק פלט אמיתי בכלל
        data = _result_json(result.stdout)
        assert data["valid"] == 1
        assert data["invalid"] == 0
    finally:
        remove_video_editor_output(output_path)


def test_validate_only_invalid_combination_reports_invalid(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "validate_bad_clip.mp4"
    # וידאו בלי אודיו + --noise-gate (agate על [0:a]) - שילוב שנכשל בהכרח
    # (ראו test_noise_gate_renders_successfully) - שימושי כאן בדיוק בשביל זה.
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "validate_bad_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--noise-gate", "--validate-only"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[INVALID]" in result.stdout
        assert not os.path.exists(output_path)
        data = _result_json(result.stdout)
        assert data["valid"] == 0
        assert data["invalid"] == 1
    finally:
        remove_video_editor_output(output_path)


def test_validate_only_ignores_existing_output_and_force(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "validate_skip_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "validate_skip_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        first = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert first.returncode == 0, first.stdout + first.stderr
        assert os.path.exists(output_path)

        # --validate-only בודק את הקובץ בכל מקרה, גם שכבר קיים פלט קודם (בניגוד
        # לדילוג-החכם הרגיל) - ולא נוגע/דורס את הפלט הקיים בכלל.
        second = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--validate-only"])
        assert second.returncode == 0, second.stdout + second.stderr
        assert "[VALID]" in second.stdout
        assert "[SKIP]" not in second.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- שליחת התראה פר-קובץ (item: --notify-per-file) - סמוק בלבד, בלי webhook מוגדר ---

def test_notify_per_file_does_not_break_normal_render(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "notify_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "notify_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--notify-per-file"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- פלט אטומי - resume batch שנקטע (item: partial-then-rename) ---

def test_failed_render_leaves_no_output_or_partial_file_behind(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "atomic_fail_clip.mp4"
    # שוב וידאו בלי אודיו + --noise-gate - שילוב שנכשל בהכרח בשלב בניית
    # ה-filtergraph (ראו test_noise_gate_renders_successfully) - מטרת הטסט
    # הזה היא לוודא שכשל אמיתי לא משאיר קובץ פלט חצי-כתוב/ריק במקום שתוצר
    # גמור אמור להיות, ולא משאיר גם קובץ ביניים (.partial) מאחוריו.
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "atomic_fail_clip_edited_horizontal.mp4")
    partial_output_path = output_path + ".partial.mp4"
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--noise-gate"])
        assert result.returncode == 0, result.stdout + result.stderr
        data = _result_json(result.stdout)
        assert data["errors"] == 1
        assert data["files_created"] == 0
        assert not os.path.exists(output_path)
        assert not os.path.exists(partial_output_path)
    finally:
        remove_video_editor_output(output_path)
        if os.path.exists(partial_output_path):
            os.remove(partial_output_path)


# --- תיקיית SIG נפרדת (item: --sig בתת-תיקייה) ---

def test_sig_file_lands_in_separate_sig_subfolder(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "sig_folder_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "sig_folder_clip_edited_horizontal.mp4")
    sig_path = resolve_sig_path(output_path)
    legacy_sig_path = output_path + ".sig.json"  # המקום הישן (ליד הפלט עצמו) - לא אמור להיווצר יותר
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert os.path.exists(sig_path)
        assert os.path.dirname(sig_path) == os.path.join(HORIZONTAL_OUTPUT_DIR, "_sig")
        assert not os.path.exists(legacy_sig_path)
        # תיקיית הפלט עצמה מכילה רק את הסרטון (ותת-תיקיית _sig) - בלי שום
        # קובץ .sig.json ישירות בתוכה.
        top_level_entries = os.listdir(HORIZONTAL_OUTPUT_DIR)
        assert not any(name.endswith(".sig.json") for name in top_level_entries)
    finally:
        remove_video_editor_output(output_path)


# --- ייצוא דוח קידוד (item: CSV/Excel) ---

def _new_report_files(before, extension):
    if not os.path.isdir(REPORTS_DIR):
        return []
    after = set(os.listdir(REPORTS_DIR))
    return sorted(name for name in (after - before) if name.endswith(extension))


def _reports_snapshot():
    return set(os.listdir(REPORTS_DIR)) if os.path.isdir(REPORTS_DIR) else set()


def test_export_report_csv_creates_report_with_run_and_file_data(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "report_csv_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "report_csv_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    before = _reports_snapshot()
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--export-report", "csv"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)

        new_files = _new_report_files(before, ".csv")
        assert len(new_files) == 1, f"ציפינו לדוח CSV חדש אחד, קיבלנו: {new_files}"
        report_path = os.path.join(REPORTS_DIR, new_files[0])
        with open(report_path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        flat_rows = {row[0]: row[1] for row in rows if len(row) == 2}
        assert flat_rows["קבצים שנוצרו"] == "1"
        assert flat_rows["קודק"] == "h264"
        file_rows = [row for row in rows if len(row) == 10 and row[0] == "report_csv_clip.mp4"]
        assert len(file_rows) == 1
        assert file_rows[0][2] == "h264"  # קודק
        assert file_rows[0][3] == "mp4"  # מיכל
        os.remove(report_path)
    finally:
        remove_video_editor_output(output_path)


def test_export_report_xlsx_creates_styled_workbook(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "report_xlsx_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "report_xlsx_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    before = _reports_snapshot()
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--export-report", "xlsx"])
        assert result.returncode == 0, result.stdout + result.stderr

        new_files = _new_report_files(before, ".xlsx")
        assert len(new_files) == 1, f"ציפינו לדוח Excel חדש אחד, קיבלנו: {new_files}"
        report_path = os.path.join(REPORTS_DIR, new_files[0])
        wb = load_workbook(report_path)
        assert wb.sheetnames == ["סיכום", "קבצים"]
        file_rows = list(wb["קבצים"].iter_rows(min_row=2, values_only=True))
        assert len(file_rows) == 1
        assert file_rows[0][0] == "report_xlsx_clip.mp4"
        os.remove(report_path)
    finally:
        remove_video_editor_output(output_path)


def test_export_report_both_creates_csv_and_xlsx(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "report_both_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "report_both_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    before = _reports_snapshot()
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--export-report", "both"])
        assert result.returncode == 0, result.stdout + result.stderr

        new_csv = _new_report_files(before, ".csv")
        new_xlsx = _new_report_files(before, ".xlsx")
        assert len(new_csv) == 1
        assert len(new_xlsx) == 1
        os.remove(os.path.join(REPORTS_DIR, new_csv[0]))
        os.remove(os.path.join(REPORTS_DIR, new_xlsx[0]))
    finally:
        remove_video_editor_output(output_path)


def test_export_report_not_created_by_default(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "report_default_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "report_default_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    before = _reports_snapshot()
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert _new_report_files(before, ".csv") == []
        assert _new_report_files(before, ".xlsx") == []
    finally:
        remove_video_editor_output(output_path)


def test_export_report_ignored_with_validate_only(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "report_validate_clip.mp4"
    _make_synthetic_video(str(src_path))

    before = _reports_snapshot()
    result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--validate-only", "--export-report", "csv"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--export-report מתעלם" in result.stdout
    assert _new_report_files(before, ".csv") == []


# --- מספור סרטונים (item: --number-videos) ---

def _read_counter():
    if not os.path.exists(COUNTER_PATH):
        return None
    with open(COUNTER_PATH, "r", encoding="utf-8") as f:
        return f.read().strip()


def _write_counter(value):
    """value=None מוחק את קובץ המונה (מדמה "עדיין לא נוצר בכלל" - כדי
    ש---number-start יתפוס בטסט, ראו utils/video/video_editor_counter.py)."""
    if value is None:
        if os.path.exists(COUNTER_PATH):
            os.remove(COUNTER_PATH)
        return
    os.makedirs(os.path.dirname(COUNTER_PATH), exist_ok=True)
    with open(COUNTER_PATH, "w", encoding="utf-8") as f:
        f.write(value)


def test_number_videos_uses_prefix_and_sequential_numbers(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for i in range(3):
        _make_synthetic_video(str(input_dir / f"clip_{i}.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    expected_names = [f"TestClip #{n}.mp4" for n in (10, 11, 12)]
    output_paths = [os.path.join(HORIZONTAL_OUTPUT_DIR, name) for name in expected_names]
    for p in output_paths:
        remove_video_editor_output(p)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--number-videos", "--number-prefix", "TestClip", "--number-start", "10",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        data = _result_json(result.stdout)
        assert data["files_created"] == 3
        for p in output_paths:
            assert os.path.exists(p), f"ציפינו לקובץ {p}, קיים בתיקייה: {os.listdir(HORIZONTAL_OUTPUT_DIR)}"
        assert _read_counter() == "13"  # 10,11,12 נוצלו - הבא שיישמר הוא 13
    finally:
        for p in output_paths:
            remove_video_editor_output(p)
        _write_counter(previous_counter)


def test_number_videos_counter_persists_across_separate_runs(tmp_path):
    input_dir1 = tmp_path / "input1"
    input_dir1.mkdir()
    _make_synthetic_video(str(input_dir1 / "clip_a.mp4"))
    input_dir2 = tmp_path / "input2"
    input_dir2.mkdir()
    _make_synthetic_video(str(input_dir2 / "clip_b.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    first_output = os.path.join(HORIZONTAL_OUTPUT_DIR, "Seq #1.mp4")
    second_output = os.path.join(HORIZONTAL_OUTPUT_DIR, "Seq #2.mp4")
    remove_video_editor_output(first_output)
    remove_video_editor_output(second_output)
    try:
        first = _run_script(["--input_dir", str(input_dir1), "--codec", "h264", "--number-videos", "--number-prefix", "Seq"])
        assert first.returncode == 0, first.stdout + first.stderr
        assert os.path.exists(first_output)

        # ריצה שנייה, נפרדת (תת-תהליך חדש) - ממשיכה מהמספר הבא שנשמר, לא מ-1.
        second = _run_script(["--input_dir", str(input_dir2), "--codec", "h264", "--number-videos", "--number-prefix", "Seq"])
        assert second.returncode == 0, second.stdout + second.stderr
        assert os.path.exists(second_output)
    finally:
        remove_video_editor_output(first_output)
        remove_video_editor_output(second_output)
        _write_counter(previous_counter)


def test_number_videos_validate_only_does_not_advance_counter(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "clip.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--number-videos", "--number-start", "5", "--validate-only",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "[VALID]" in result.stdout
        # --validate-only לא מרנדר בפועל - המונה לא אמור להיווצר/להתקדם בכלל.
        assert _read_counter() is None
    finally:
        _write_counter(previous_counter)


def test_number_videos_combined_with_output_template_number_placeholder(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "clip.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "clip_no1.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--number-videos", "--number-start", "1",
            "--output-template", "{name}_no{number}",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)
        _write_counter(previous_counter)


def test_number_videos_ignored_message_when_no_suffix_also_given(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "clip.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "Clip #1.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--number-videos", "--number-start", "1", "--no-suffix",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--no-suffix מתעלם - --number-videos גובר עליו" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)
        _write_counter(previous_counter)


def test_number_videos_restart_on_already_rendered_folder_skips_without_burning_new_numbers(tmp_path):
    # item: מספור סרטונים - regression: לפני התיקון, שם-הפלט המספרי החדש
    # בכל ריצה שבר את הדילוג-החכם (שם הקובץ לא היה קיים בעבר, אף שהתוכן זהה) -
    # restart על תיקייה שכבר עובדה היה מרנדר ומספר הכל מחדש. כאן מריצים
    # פעמיים על אותם קבצים בדיוק - הריצה השנייה חייבת לדלג על שניהם ולא
    # להקצות מספרים חדשים בכלל.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "clip_a.mp4"))
    _make_synthetic_video(str(input_dir / "clip_b.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    output_paths = [os.path.join(HORIZONTAL_OUTPUT_DIR, f"RestartClip #{n}.mp4") for n in (300, 301)]
    for p in output_paths:
        remove_video_editor_output(p)
    try:
        first = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--number-videos", "--number-prefix", "RestartClip", "--number-start", "300",
        ])
        assert first.returncode == 0, first.stdout + first.stderr
        first_data = _result_json(first.stdout)
        assert first_data["files_created"] == 2
        for p in output_paths:
            assert os.path.exists(p)
        assert _read_counter() == "302"

        second = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--number-videos", "--number-prefix", "RestartClip", "--number-start", "300",
        ])
        assert second.returncode == 0, second.stdout + second.stderr
        second_data = _result_json(second.stdout)
        assert second_data["files_created"] == 0
        assert second_data["skipped"] == 2
        # המונה לא זז - שני הקבצים דולגו, אף מספר חדש לא הוקצה בריצה השנייה.
        assert _read_counter() == "302"
        assert not os.path.exists(os.path.join(HORIZONTAL_OUTPUT_DIR, "RestartClip #302.mp4"))
        assert not os.path.exists(os.path.join(HORIZONTAL_OUTPUT_DIR, "RestartClip #303.mp4"))
    finally:
        for p in output_paths:
            remove_video_editor_output(p)
        remove_video_editor_output(os.path.join(HORIZONTAL_OUTPUT_DIR, "RestartClip #302.mp4"))
        remove_video_editor_output(os.path.join(HORIZONTAL_OUTPUT_DIR, "RestartClip #303.mp4"))
        _write_counter(previous_counter)


def test_number_videos_partial_batch_failure_returns_unused_numbers_to_the_pool(tmp_path):
    # item: מספור סרטונים - regression: לפני התיקון, קובץ שנכשל "שרף" את
    # המספר שהוקצה לו לצמיתות (גם כשהבאצ' כולו הסתיים כרגיל). כאן a_good/
    # c_good מצליחים ו-b_bad (בלי אודיו + --noise-gate) נכשל בהכרח - המונה
    # שנשמר בסוף חייב לשקף רק את המספר הגבוה ביותר שבאמת נוצל בהצלחה (202,
    # מ-c_good שמספרו 202 אחרי b_bad שנכשל וקיבל 201) - לא 201 (שהיה גורם
    # להתנגשות עם c_good#202 שכבר קיים) ולא "נשאר על 203 לצמיתות" בלי תיקון.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video_with_audio(str(input_dir / "a_good.mp4"))
    _make_synthetic_video(str(input_dir / "b_bad.mp4"))  # בלי אודיו - נכשל עם --noise-gate
    _make_synthetic_video_with_audio(str(input_dir / "c_good.mp4"))

    previous_counter = _read_counter()
    _write_counter(None)
    good_a_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "PartialClip #200.mp4")
    bad_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "PartialClip #201.mp4")
    good_c_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "PartialClip #202.mp4")
    for p in (good_a_path, bad_path, good_c_path):
        remove_video_editor_output(p)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--noise-gate",
            "--number-videos", "--number-prefix", "PartialClip", "--number-start", "200",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        data = _result_json(result.stdout)
        assert data["files_created"] == 2
        assert data["errors"] == 1
        assert os.path.exists(good_a_path)
        assert not os.path.exists(bad_path)
        assert os.path.exists(good_c_path)
        # 202 (c_good, ההצלחה הגבוהה ביותר) + 1 = 203 - זה בדיוק גם הערך
        # הגולמי-שהוקצה (200,201,202 הוקצו, הבא=203), כי ההצלחה האחרונה בסדר
        # ההקצאה (202) היתה גם הגבוהה ביותר - אין כאן "תיקון" בפועל, ראו
        # את הטסט הבא (trailing_failure) למקרה שבו כן יש תיקון בפועל.
        assert _read_counter() == "203"
    finally:
        for p in (good_a_path, bad_path, good_c_path):
            remove_video_editor_output(p)
        _write_counter(previous_counter)


def test_number_videos_trailing_failure_rolls_the_counter_back(tmp_path):
    # item: מספור סרטונים - כשהכשל הוא *האחרון* בסדר ההקצאה (לא מכוסה ע"י
    # הצלחה מאוחרת יותר), המונה חייב לחזור בפועל למספר הראשון-שלא-נוצל (לא
    # להישאר על הערך הגולמי-שהוקצה) - וגם להדפיס על כך הודעת [INFO].
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video_with_audio(str(input_dir / "a_good.mp4"))
    _make_synthetic_video(str(input_dir / "b_bad.mp4"))  # בלי אודיו - נכשל עם --noise-gate

    previous_counter = _read_counter()
    _write_counter(None)
    good_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "TrailClip #500.mp4")
    bad_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "TrailClip #501.mp4")
    for p in (good_path, bad_path):
        remove_video_editor_output(p)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--noise-gate",
            "--number-videos", "--number-prefix", "TrailClip", "--number-start", "500",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        data = _result_json(result.stdout)
        assert data["files_created"] == 1
        assert data["errors"] == 1
        assert os.path.exists(good_path)
        assert not os.path.exists(bad_path)
        # 500 נוצל בהצלחה, 501 נכשל ולא נוצל ע"י אף הצלחה מאוחרת יותר - המונה
        # חוזר ל-501 (לא נשאר על 502, הערך הגולמי-שהוקצה בזמן ההרצה).
        assert _read_counter() == "501"
        assert "המונה תוקן חזרה ל-501" in result.stdout
    finally:
        for p in (good_path, bad_path):
            remove_video_editor_output(p)
        _write_counter(previous_counter)


# --- תמונה-בתוך-תמונה / PiP (item) ---

def test_pip_composites_second_video_at_default_bottom_right_position(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "pip_main_clip.mp4"
    _make_solid_color_video(str(src_path), "0x0000FF", width=640, height=360)  # כחול טהור, 16:9 - בלי pillarboxing שיפריע לדגימת הפינה
    pip_path = tmp_path / "pip_overlay.mp4"
    _make_solid_color_video(str(pip_path), "0xFF0000")  # אדום טהור

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "pip_main_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--pip", str(pip_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1920x1080"
        # ברירת המחדל (--pip-position bottom-right, --pip-scale 0.3) - פינה
        # ימנית-תחתונה אמורה להיות אדומה (ה-PiP), פינה שמאלית-עליונה נשארת
        # כחולה (הווידאו הראשי, לא מושפע מה-PiP בכלל).
        bottom_right_pixel = _pixel_rgb_at(output_path, 1850, 1000)
        top_left_pixel = _pixel_rgb_at(output_path, 20, 20)
        assert _color_distance(bottom_right_pixel, (255, 0, 0)) < 60, f"ציפינו ל-PiP אדום בפינה ימנית-תחתונה: {bottom_right_pixel}"
        assert _color_distance(top_left_pixel, (0, 0, 255)) < 60, f"ציפינו לווידאו הראשי הכחול, לא מושפע מה-PiP: {top_left_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_pip_custom_position_and_opacity(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "pip_position_clip.mp4"
    _make_solid_color_video(str(src_path), "0x0000FF", width=640, height=360)
    pip_path = tmp_path / "pip_overlay_top_left.mp4"
    _make_solid_color_video(str(pip_path), "0x00FF00")  # ירוק טהור

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "pip_position_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--pip", str(pip_path),
            "--pip-position", "top-left", "--pip-scale", "0.2",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        top_left_pixel = _pixel_rgb_at(output_path, 20, 20)
        assert _color_distance(top_left_pixel, (0, 255, 0)) < 60, f"ציפינו ל-PiP ירוק בפינה שמאלית-עליונה: {top_left_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_pip_missing_file_warns_and_continues_without_it(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "pip_missing_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "pip_missing_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--pip", str(tmp_path / "does_not_exist.mp4")])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "קובץ ה-PiP לא נמצא" in result.stdout
        assert os.path.exists(output_path)  # הרינדור עצמו לא נפגע
    finally:
        remove_video_editor_output(output_path)


def test_pip_ignored_with_hwaccel(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "pip_hwaccel_clip.mp4"
    _make_synthetic_video(str(src_path))
    pip_path = tmp_path / "pip_hwaccel_overlay.mp4"
    _make_solid_color_video(str(pip_path), "0xFF0000")

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "pip_hwaccel_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "hevc", "--hwaccel", "--pip", str(pip_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--pip מתעלם" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_only_files_processes_selected_subset_in_given_order(tmp_path):
    # item: תור-אצווה ניתן-לעריכה - שלושה קבצים, --only-files בוחר רק שניים
    # מהם בסדר-הפוך מהסדר האלפביתי - בודק גם סינון וגם שהסדר בפועל נשמר
    # (לא רק "אילו קבצים", גם "באיזה סדר").
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "a_first.mp4"), duration=1)
    _make_synthetic_video(str(input_dir / "b_second.mp4"), duration=1)
    _make_synthetic_video(str(input_dir / "c_third.mp4"), duration=1)

    paths = {
        name: os.path.join(HORIZONTAL_OUTPUT_DIR, f"{name}_edited_horizontal.mp4")
        for name in ("a_first", "b_second", "c_third")
    }
    for p in paths.values():
        remove_video_editor_output(p)
    try:
        only_files = json.dumps(["c_third.mp4", "a_first.mp4"])
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--only-files", only_files])
        assert result.returncode == 0, result.stdout + result.stderr
        data = _result_json(result.stdout)
        assert data["files_created"] == 2
        assert os.path.exists(paths["a_first"])
        assert os.path.exists(paths["c_third"])
        assert not os.path.exists(paths["b_second"])  # לא ברשימה - לא מעובד בכלל
        # סדר העיבוד בפועל תואם את סדר --only-files (c לפני a), לא אלפביתי
        c_pos = result.stdout.index("c_third.mp4")
        a_pos = result.stdout.index("a_first.mp4")
        assert c_pos < a_pos, "צפוי היה שc_third יעובד לפני a_first (סדר --only-files), לא סדר אלפביתי"
    finally:
        for p in paths.values():
            remove_video_editor_output(p)


def test_only_files_unknown_name_ignored_silently(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "real_clip.mp4"))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "real_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        only_files = json.dumps(["real_clip.mp4", "ghost_clip_does_not_exist.mp4"])
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--only-files", only_files])
        assert result.returncode == 0, result.stdout + result.stderr
        data = _result_json(result.stdout)
        assert data["files_created"] == 1
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_only_files_invalid_json_falls_back_to_all_files(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "clip_one.mp4"))
    _make_synthetic_video(str(input_dir / "clip_two.mp4"))

    paths = [
        os.path.join(HORIZONTAL_OUTPUT_DIR, "clip_one_edited_horizontal.mp4"),
        os.path.join(HORIZONTAL_OUTPUT_DIR, "clip_two_edited_horizontal.mp4"),
    ]
    for p in paths:
        remove_video_editor_output(p)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--only-files", "not valid json"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--only-files אינו JSON תקין" in result.stdout
        data = _result_json(result.stdout)
        assert data["files_created"] == 2
    finally:
        for p in paths:
            remove_video_editor_output(p)


def test_pip_combined_with_watermark_both_visible(tmp_path):
    # item: PiP - watermark נשאר עליון/אחרון כשהשניים חופפים בפועל (אותה
    # פינה) - כאן הם בפינות שונות בכוונה כדי לבדוק ששניהם מרונדרים בנפרד,
    # לא (רק) את סדר השכבות כשהם חופפים.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "pip_wm_clip.mp4"
    _make_solid_color_video(str(src_path), "0x0000FF", width=640, height=360)
    pip_path = tmp_path / "pip_wm_overlay.mp4"
    _make_solid_color_video(str(pip_path), "0xFF0000")
    watermark_path = tmp_path / "watermark.png"
    from PIL import Image
    Image.new("RGBA", (64, 64), (0, 255, 0, 255)).save(str(watermark_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "pip_wm_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--pip", str(pip_path), "--pip-position", "bottom-right",
            "--watermark_path", str(watermark_path), "--watermark_position", "top-right", "--watermark_scale", "0.1",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        bottom_right_pixel = _pixel_rgb_at(output_path, 1850, 1000)
        top_right_pixel = _pixel_rgb_at(output_path, 1850, 50)
        assert _color_distance(bottom_right_pixel, (255, 0, 0)) < 60, f"ציפינו ל-PiP אדום: {bottom_right_pixel}"
        assert _color_distance(top_right_pixel, (0, 255, 0)) < 60, f"ציפינו ל-watermark ירוק: {top_right_pixel}"
    finally:
        remove_video_editor_output(output_path)
