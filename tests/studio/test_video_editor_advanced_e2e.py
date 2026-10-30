# tests/studio/test_video_editor_advanced_e2e.py
#
# טסטי end-to-end אמיתיים (מריצים my_scripts/video/video_editor.py כתת-תהליך
# אמיתי, בדיוק כמו tests/studio/test_video_editor_e2e.py) לחמשת ה-Quick Wins וחמשת
# ה-Medium Effort שנוספו לעורך-העל: watermark opacity, smart crop, blurred
# background, trim range, auto-trim silence, denoise/sharpen, configurable
# loudnorm target, skip-if-already-correct-orientation. captions (faster-
# whisper, תלוי-מודל/רשת) לא נבדק כאן end-to-end - רק שה-flag מתעלם בשקט
# בלי --keep-audio (ראו התיעוד המלא ב-README) - אותו עיקרון שכבר נקבע השנה
# ל-utils/media/clip_tagger.py (AI/רשת: unit-tested עם מוק, לא e2e אמיתי).
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys


import pytest
from PIL import Image

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")
VERTICAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "vertical")

# 1920x1080 בדיוק (זהה ל-resolve_output_dimensions(False)) - אותה סיבה כמו
# test_video_editor_watermark_removal_e2e.py: scale/pad הופכים ל-no-op, אז
# קואורדינטת קלט = קואורדינטת פלט בלי מיפוי נוסף.
INPUT_WIDTH, INPUT_HEIGHT = 1920, 1080


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_black_video(path, duration=1, width=INPUT_WIDTH, height=INPUT_HEIGHT):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"color=black:size={width}x{height}:duration={duration}:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_synthetic_video(path, duration=1, width=320, height=240):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_square_video(path, duration=1, size=800):
    _make_synthetic_video(path, duration=duration, width=size, height=size)


def _make_synthetic_video_with_audio(path, duration=1, width=320, height=240):
    # כמו _make_synthetic_video, אבל עם ערוץ אודיו אמיתי (טון sine) - נדרש
    # לטסטים שמעבירים אודיו דרך filter_complex (למשל --loudnorm, loudnorm על
    # [0:a]) - קלט בלי אודיו כלל היה גורם ל-ffmpeg לכשול על "matches no
    # streams" בבניית ה-filtergraph, אבל עדיין משאיר קובץ פלט ריק/פגום מאחוריו,
    # מה שהיה גורם לטסט עם os.path.exists(output_path) בלבד "לעבור" בלי לבדוק
    # בכלל שהרינדור הצליח באמת.
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_video_with_trailing_silence(path, tone_seconds=2, silence_seconds=2, width=320, height=240):
    total_duration = tone_seconds + silence_seconds
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={total_duration}:size={width}x{height}:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={tone_seconds}",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={silence_seconds}",
        "-filter_complex", "[1:a][2:a]concat=n=2:v=0:a=1[outa]",
        "-map", "0:v", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_white_watermark_png(path, size=200):
    Image.new("RGBA", (size, size), (255, 255, 255, 255)).save(path)


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


def _probe_duration(path):
    cmd = [
        get_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return float(result.stdout.strip())


def _run_script(args, timeout=120):
    return subprocess.run(
        [sys.executable, SCRIPT] + args, cwd=BASE_DIR, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, creationflags=NO_WINDOW_FLAGS,
    )


# --- watermark opacity ---

def test_watermark_opacity_blends_with_background(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "opacity_test_clip.mp4"
    _make_black_video(str(src_path))
    watermark_path = tmp_path / "watermark.png"
    _make_white_watermark_png(str(watermark_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "opacity_test_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--watermark_path", str(watermark_path), "--watermark_position", "center",
            "--watermark_scale", "0.3", "--watermark_opacity", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)

        center_pixel = _pixel_rgb_at(output_path, INPUT_WIDTH // 2, INPUT_HEIGHT // 2)
        # רקע שחור טהור + watermark לבן טהור ב-50% שקיפות -> ~(127,127,127).
        # מרווח סבלנות רחב (בגלל דחיסת h264) אבל רחוק מספיק גם משחור וגם מלבן.
        assert _color_distance(center_pixel, (255, 255, 255)) > 60, f"נראה אטום לגמרי (לבן): {center_pixel}"
        assert _color_distance(center_pixel, (0, 0, 0)) > 60, f"נראה שקוף לגמרי (שחור, כאילו אין watermark): {center_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_watermark_opacity_ignored_with_hwaccel_falls_back_to_opaque(tmp_path):
    # nv12 (מה שה-watermark מומר אליו לפני overlay_cuda) אין לו ערוץ אלפא -
    # מוודא בפועל (לא רק בקוד) שה-hwaccel+opacity לא נכשל/לא מפיק תוצאה שקופה
    # "שקטה"-שגויה, אלא נופל בחזרה לאטימות מלאה כמו שמתועד.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "opacity_hwaccel_clip.mp4"
    _make_black_video(str(src_path))
    watermark_path = tmp_path / "watermark.png"
    _make_white_watermark_png(str(watermark_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "opacity_hwaccel_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "hevc", "--hwaccel",
            "--watermark_path", str(watermark_path), "--watermark_position", "center",
            "--watermark_scale", "0.3", "--watermark_opacity", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        center_pixel = _pixel_rgb_at(output_path, INPUT_WIDTH // 2, INPUT_HEIGHT // 2)
        assert _color_distance(center_pixel, (255, 255, 255)) < 40, f"אמור ליפול בחזרה לאטימות מלאה עם --hwaccel: {center_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_watermark_default_opacity_is_fully_opaque(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "opacity_default_clip.mp4"
    _make_black_video(str(src_path))
    watermark_path = tmp_path / "watermark.png"
    _make_white_watermark_png(str(watermark_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "opacity_default_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--watermark_path", str(watermark_path), "--watermark_position", "center", "--watermark_scale", "0.3",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        center_pixel = _pixel_rgb_at(output_path, INPUT_WIDTH // 2, INPUT_HEIGHT // 2)
        assert _color_distance(center_pixel, (255, 255, 255)) < 30, f"ברירת המחדל אמורה להיות אטומה לגמרי: {center_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_watermark_custom_x_y_overrides_position_end_to_end(tmp_path):
    # item: גרירת watermark חופשית - --watermark_x/--watermark_y (0.5,0.5 =
    # מרכז הפריים) גוברים על --watermark_position "bottom-right" בפועל
    # בפייפליין האמיתי, לא רק ביחידת compute_watermark_geometry.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "custom_xy_clip.mp4"
    _make_black_video(str(src_path))
    watermark_path = tmp_path / "watermark.png"
    _make_white_watermark_png(str(watermark_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "custom_xy_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--watermark_path", str(watermark_path), "--watermark_position", "bottom-right",
            "--watermark_scale", "0.3", "--watermark_x", "0.5", "--watermark_y", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)

        center_pixel = _pixel_rgb_at(output_path, INPUT_WIDTH // 2, INPUT_HEIGHT // 2)
        corner_pixel = _pixel_rgb_at(output_path, INPUT_WIDTH - 5, INPUT_HEIGHT - 5)
        assert _color_distance(center_pixel, (255, 255, 255)) < 30, f"מרכז אמור להיות לבן (watermark נגרר לשם): {center_pixel}"
        assert _color_distance(corner_pixel, (0, 0, 0)) < 30, f"פינה ימנית-תחתונה אמורה להיות שחורה (bottom-right בוטל): {corner_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_clip_edit_moves_the_logo_for_one_file_only(tmp_path):
    # גל 30: גרירת הלוגו בעריכת קליפ - watermark_x/y בדריסה פר-קובץ (רק לקובץ הזה), ומיקום
    # פינה מפורש לקובץ מבטל את מרכז הגרירה של כל הקבצים.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for name in ("w30_moved.mp4", "w30_same.mp4", "w30_corner.mp4"):
        _make_black_video(str(input_dir / name))
    watermark_path = tmp_path / "watermark.png"
    _make_white_watermark_png(str(watermark_path))
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({"w30_moved.mp4": {"watermark_x": 0.5, "watermark_y": 0.5},
                                     "w30_corner.mp4": {"watermark_position": "bottom-right"}}), encoding="utf-8")
    outputs = {name: os.path.join(HORIZONTAL_OUTPUT_DIR, f"w30_{name}_edited_horizontal.mp4") for name in ("moved", "same", "corner")}
    for path in outputs.values():
        remove_video_editor_output(path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--force",
            "--watermark_path", str(watermark_path), "--watermark_position", "top-left", "--watermark_scale", "0.3",
            "--batch-overrides", str(overrides),
        ], timeout=240)
        assert result.returncode == 0, result.stdout + result.stderr
        center = (INPUT_WIDTH // 2, INPUT_HEIGHT // 2)
        top_left, bottom_right = (100, 100), (INPUT_WIDTH - 100, INPUT_HEIGHT - 100)  # בתוך הלוגו (יש שוליים)
        white, black = (255, 255, 255), (0, 0, 0)
        assert _color_distance(_pixel_rgb_at(outputs["moved"], *center), white) < 30
        assert _color_distance(_pixel_rgb_at(outputs["moved"], *top_left), black) < 30
        assert _color_distance(_pixel_rgb_at(outputs["same"], *top_left), white) < 30  # שאר הקבצים - כמו כולם
        assert _color_distance(_pixel_rgb_at(outputs["same"], *center), black) < 30
        assert _color_distance(_pixel_rgb_at(outputs["corner"], *bottom_right), white) < 30
        assert _color_distance(_pixel_rgb_at(outputs["corner"], *top_left), black) < 30
    finally:
        for path in outputs.values():
            remove_video_editor_output(path)


def test_watermark_partial_custom_xy_falls_back_to_position(tmp_path):
    # רק --watermark_x בלי --watermark_y (קלט חלקי) - מתעלם משניהם, נופל
    # בחזרה ל---watermark_position כרגיל (לא זורק/לא מתייחס לחצי-קלט כתקין).
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "partial_xy_clip.mp4"
    _make_black_video(str(src_path))
    watermark_path = tmp_path / "watermark.png"
    _make_white_watermark_png(str(watermark_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "partial_xy_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--watermark_path", str(watermark_path), "--watermark_position", "top-left",
            "--watermark_scale", "0.3", "--watermark_x", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        # (30, 30) לא (5, 5) - top-left משאיר margin=20px ברירת מחדל מהקצה עצמו.
        top_left_pixel = _pixel_rgb_at(output_path, 30, 30)
        assert _color_distance(top_left_pixel, (255, 255, 255)) < 30, f"top-left אמור לחול (x חלקי מתעלם): {top_left_pixel}"
    finally:
        remove_video_editor_output(output_path)


# --- trim range ---

def test_trim_start_and_duration_produce_shorter_output(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "trim_test_clip.mp4"
    _make_synthetic_video(str(src_path), duration=5)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "trim_test_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--trim-start", "1", "--trim-duration", "2"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        duration = _probe_duration(output_path)
        assert 1.5 <= duration <= 2.5, f"ציפינו ל-~2 שניות אחרי חיתוך, קיבלנו {duration}"
    finally:
        remove_video_editor_output(output_path)


def test_trim_start_beyond_duration_skips_with_error(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "trim_overflow_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "trim_overflow_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--trim-start", "999"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert '"errors": 1' in result.stdout
        assert not os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- auto-trim silence ---

def test_trim_silence_removes_trailing_silent_portion(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "silence_test_clip.mp4"
    _make_video_with_trailing_silence(str(src_path), tone_seconds=2, silence_seconds=2)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "silence_test_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--trim-silence"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        duration = _probe_duration(output_path)
        # ~2 שניות (רק חלק הטון) - לא 4 (טון+שקט המלא)
        assert duration < 3.0, f"ציפינו שהשקט הנגרר יחתך (~2s), קיבלנו {duration}"
    finally:
        remove_video_editor_output(output_path)


def test_trim_silence_ignored_when_combined_with_explicit_trim(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "silence_explicit_clip.mp4"
    _make_video_with_trailing_silence(str(src_path), tone_seconds=1, silence_seconds=1)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "silence_explicit_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
            "--trim-silence", "--trim-start", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--trim-silence מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- denoise / sharpen (smoke tests - effect is subtle, verify it renders correctly) ---

def test_denoise_and_sharpen_render_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "denoise_sharpen_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "denoise_sharpen_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--denoise", "--sharpen"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


# --- configurable loudnorm target (smoke test - exact LUFS measurement is out of scope) ---

def test_custom_loudnorm_target_renders_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "loudnorm_target_clip.mp4"
    _make_synthetic_video_with_audio(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "loudnorm_target_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--keep-audio", "--loudnorm", "--loudnorm-target", "-20",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert '"files_created": 1' in result.stdout, result.stdout  # לא רק "קובץ קיים" - הרינדור עצמו הצליח בפועל
    finally:
        remove_video_editor_output(output_path)


def test_loudnorm_target_ignored_without_loudnorm_flag(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "loudnorm_target_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "loudnorm_target_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--loudnorm-target", "-20"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--loudnorm-target מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- skip redundant scale (item: skip-if-already-correct-orientation) ---

def test_skip_scale_when_input_already_matches_output_resolution(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "already_1080p_clip.mp4"
    _make_synthetic_video(str(src_path), width=INPUT_WIDTH, height=INPUT_HEIGHT)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "already_1080p_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "מדלג על שינוי גודל מיותר" in result.stdout
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


def test_scale_not_skipped_when_input_resolution_differs(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "small_res_clip.mp4"
    _make_synthetic_video(str(src_path), width=320, height=240)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "small_res_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "מדלג על שינוי גודל מיותר" not in result.stdout
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


# --- smart crop (item) ---

def test_smart_crop_with_vertical_renders_correct_resolution(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smart_crop_clip.mp4"
    _make_synthetic_video(str(src_path), duration=2, width=640, height=360)

    output_path = os.path.join(VERTICAL_OUTPUT_DIR, "smart_crop_clip_edited_vertical.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--vertical", "--smart-crop"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "smart-crop - היסט קרופ" in result.stdout
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1080x1920"
    finally:
        remove_video_editor_output(output_path)


def test_smart_crop_ignored_without_vertical(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smart_crop_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "smart_crop_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--smart-crop"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--smart-crop מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- קרופ חכם לפי זיהוי-פנים (item) - וידאו testsrc לא מכיל פנים אמיתיות
# (אין דרך לייצר את זה עם ffmpeg lavfi), אז הבדיקה כאן לא יכולה להוכיח היסט
# חיובי/שלילי כמו test_smart_crop_with_vertical_renders_correct_resolution -
# מה שהיא כן מוכיחה, ואמיתי: המודל המצורף (assets/face_detection_yunet_
# 2023mar.onnx) באמת נטען ורץ בתת-תהליך אמיתי מקצה-לקצה (לא רק ב-mock של
# test_smart_crop.py), לא מוצא פנים (כצפוי), ונופל בחזרה לקרופ-במרכז בלי
# להפיל את הרינדור. ---

def test_smart_crop_face_with_vertical_renders_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smart_crop_face_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1, width=640, height=360)

    output_path = os.path.join(VERTICAL_OUTPUT_DIR, "smart_crop_face_clip_edited_vertical.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--vertical", "--smart-crop", "--smart-crop-face",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "smart-crop - היסט קרופ" in result.stdout
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1080x1920"
    finally:
        remove_video_editor_output(output_path)


def test_smart_crop_face_ignored_without_smart_crop(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smart_crop_face_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "smart_crop_face_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--smart-crop-face"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--smart-crop-face מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- blurred background instead of black bars (item) ---

def test_blur_background_pad_area_is_not_pure_black(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "blur_bg_clip.mp4"
    _make_square_video(str(src_path))  # 1:1 -> padded left/right when scaled to 16:9

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "blur_bg_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--blur-background"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1920x1080"
        # x=50 יושב בתוך פס ה-padding השמאלי ((1920-1080)/2=420px רוחב) -
        # ברקע מטושטש זה לא אמור להיות שחור טהור יותר.
        pad_pixel = _pixel_rgb_at(output_path, 50, INPUT_HEIGHT // 2)
        assert _color_distance(pad_pixel, (0, 0, 0)) > 15, f"אזור ה-padding עדיין נראה שחור טהור: {pad_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_default_black_padding_still_black_without_blur_background(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "black_pad_clip.mp4"
    _make_square_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "black_pad_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264"])
        assert result.returncode == 0, result.stdout + result.stderr
        pad_pixel = _pixel_rgb_at(output_path, 50, INPUT_HEIGHT // 2)
        assert _color_distance(pad_pixel, (0, 0, 0)) < 15, f"ברירת המחדל (בלי --blur-background) אמורה להישאר שחור טהור: {pad_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_blur_background_fits_full_horizontal_video_into_vertical_without_cropping(tmp_path):
    # item: הכנסת סרטון אופקי לתוך מסגרת אנכית (טיקטוק/שורטס) בלי לחתוך ממנו -
    # --blur-background כבר לא מתעלם עם --vertical (היה כך קודם, ראו ההיסטוריה
    # שהוחלפה כאן): מקור רחב (16:9) מוקטן-שמור-יחס לרוחב מלא בתוך מסגרת 1080x1920,
    # עם רקע מטושטש-מוגדל ממלא את הפס העליון/תחתון - בלי קרופ בכלל.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "wide_clip.mp4"
    _make_synthetic_video(str(src_path), width=640, height=360)  # 16:9 רחב

    output_path = os.path.join(VERTICAL_OUTPUT_DIR, "wide_clip_edited_vertical.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--vertical", "--blur-background"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _probe_dimensions(output_path) == "1080x1920"
        # התוכן המוקטן-שמור-יחס (16:9 לתוך רוחב 1080) תופס רק ~607px גובה
        # מתוך 1920 - y=50 יושב עמוק בתוך פס ה-padding העליון.
        pad_pixel = _pixel_rgb_at(output_path, 540, 50)
        assert _color_distance(pad_pixel, (0, 0, 0)) > 15, f"פס ה-padding העליון נראה שחור טהור (כאילו נחתך/לא מולא): {pad_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_smart_crop_ignored_when_blur_background_used_with_vertical(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "smart_crop_vs_blur_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(VERTICAL_OUTPUT_DIR, "smart_crop_vs_blur_clip_edited_vertical.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--vertical", "--smart-crop", "--blur-background",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--smart-crop מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- captions (item) - רק בדיקת ה-gating, לא whisper אמיתי (ראו הערת המודול) ---

def test_captions_ignored_without_keep_audio(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "captions_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "captions_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--captions"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--captions מתעלם" in result.stdout
        assert os.path.exists(output_path)  # הרינדור עצמו לא נפגע
    finally:
        remove_video_editor_output(output_path)


def test_captions_translate_ignored_without_captions(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "captions_translate_ignored_clip.mp4"
    _make_synthetic_video(str(src_path))

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "captions_translate_ignored_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        # --captions-translate בלי --captions בכלל (ולא רק בלי --keep-audio) -
        # אמור להתעלם גם כן, בלי לפגוע ברינדור עצמו.
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--keep-audio", "--captions-translate"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--captions-translate מתעלם" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)
