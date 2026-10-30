# tests/studio/test_video_editor_concat_e2e.py
#
# טסטי end-to-end אמיתיים (מריצים my_scripts/video/video_editor.py כתת-תהליך
# אמיתי) למצב-הריצה הנפרד --concat-files (item: מעברים בין כמה קטעים) -
# מאחה כמה קבצים לתוצר אחד עם מעבר קרוספייד/דיסולב (xfade/acrossfade) או
# חיתוך קשה (concat רגיל). דוגמים פיקסלים בזמנים ספציפיים (לא רק "לא קרס")
# כדי לוודא שהמעבר קורה *בדיוק* בזמן הנכון - נבדק ידנית תוך כדי פיתוח מול
# ffmpeg אמיתי (ראו סיכום השיחה): t=4.5 על שני קטעים של 5s עם T=1s (מעבר
# מתחיל ב-t=4.0) נתן בדיוק תערובת 50/50 בין שני הצבעים.
import os
from tests import PROJECT_ROOT
import subprocess
import sys


import json
import shutil

import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _run_script(args, timeout=60):
    return subprocess.run(
        [sys.executable, SCRIPT] + args, cwd=BASE_DIR, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, creationflags=NO_WINDOW_FLAGS,
    )


def _make_solid_color_clip_with_audio(path, color_hex, duration=5, width=640, height=480):
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"color=c={color_hex}:s={width}x{height}:d={duration}:r=10",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _pixel_rgb_at_center(path, t):
    cmd = [
        get_ffmpeg_exe(), "-v", "error", "-ss", str(t), "-i", path,
        "-vf", "crop=2:2:960:540", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert len(result.stdout) == 12, f"ציפינו לבלוק 2x2 (12 בתים), קיבלנו {len(result.stdout)}"
    return tuple(result.stdout[:3])


def _color_distance(rgb_a, rgb_b):
    return sum(abs(a - b) for a, b in zip(rgb_a, rgb_b))


def _probe_duration(path):
    cmd = [get_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return float(result.stdout.strip())


def _has_audio_stream(path):
    cmd = [get_ffprobe_exe(), "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return "audio" in result.stdout


RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


def test_concat_fade_three_clips_crossfades_at_exact_computed_times(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000")
    _make_solid_color_clip_with_audio(str(input_dir / "green.mp4"), "0x00FF00")
    _make_solid_color_clip_with_audio(str(input_dir / "blue.mp4"), "0x0000FF")

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "concat_test_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
            "--concat-files", json.dumps(["red.mp4", "green.mp4", "blue.mp4"]),
            "--concat-transition", "fade", "--concat-transition-duration", "1.0",
            "--concat-output-name", "concat_test",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)

        # 3 קטעים של 5s, T=1s -> 15 - 2*1 = 13s (שני מעברים חופפים).
        assert abs(_probe_duration(output_path) - 13.0) < 0.3

        # לפני המעבר הראשון (מתחיל ב-offset=4.0): אדום טהור.
        assert _color_distance(_pixel_rgb_at_center(output_path, 2.0), RED) < 15
        # אמצע המעבר הראשון בדיוק (offset=4.0, d=1.0 -> אמצע ב-4.5): תערובת 50/50.
        mid1 = _pixel_rgb_at_center(output_path, 4.5)
        assert _color_distance(mid1, RED) > 40 and _color_distance(mid1, GREEN) > 40, f"ציפינו לתערובת, קיבלנו {mid1}"
        # אחרי המעבר הראשון: ירוק טהור.
        assert _color_distance(_pixel_rgb_at_center(output_path, 6.5), GREEN) < 15
        # אמצע המעבר השני (offset=8.0, d=1.0 -> אמצע ב-8.5): תערובת ירוק/כחול.
        mid2 = _pixel_rgb_at_center(output_path, 8.5)
        assert _color_distance(mid2, GREEN) > 40 and _color_distance(mid2, BLUE) > 40, f"ציפינו לתערובת, קיבלנו {mid2}"
        # אחרי המעבר השני: כחול טהור.
        assert _color_distance(_pixel_rgb_at_center(output_path, 11.0), BLUE) < 15

        assert _has_audio_stream(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_concat_none_transition_is_a_hard_cut_with_full_duration(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000")
    _make_solid_color_clip_with_audio(str(input_dir / "green.mp4"), "0x00FF00")

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "concat_hardcut_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--concat-files", json.dumps(["red.mp4", "green.mp4"]),
            "--concat-transition", "none", "--concat-output-name", "concat_hardcut",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        # בלי חפיפה - 5+5=10s בדיוק (לא 10-T כמו fade).
        assert abs(_probe_duration(output_path) - 10.0) < 0.3
        # חיתוך קשה - ממש ליד הגבול (t=4.9) עדיין אדום טהור, אין הדרגתיות.
        assert _color_distance(_pixel_rgb_at_center(output_path, 4.8), RED) < 15
        assert _color_distance(_pixel_rgb_at_center(output_path, 5.2), GREEN) < 15
    finally:
        remove_video_editor_output(output_path)


def test_concat_vertical_scales_all_clips_to_common_dimensions(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000")
    _make_solid_color_clip_with_audio(str(input_dir / "green.mp4"), "0x00FF00")

    output_dir = os.path.join(WORKSPACE_DIR, "studio", "vertical")
    output_path = os.path.join(output_dir, "concat_vertical_edited_vertical.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--vertical",
            "--concat-files", json.dumps(["red.mp4", "green.mp4"]),
            "--concat-output-name", "concat_vertical",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        cmd = [get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", output_path]
        dims = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS).stdout.strip()
        assert dims == "1080x1920"
    finally:
        remove_video_editor_output(output_path)


def test_concat_missing_clip_errors_clearly(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000")

    result = _run_script([
        "--input_dir", str(input_dir), "--codec", "h264",
        "--concat-files", json.dumps(["red.mp4", "does_not_exist.mp4"]),
    ])
    assert result.returncode == 0  # לא crash - שגיאה מטופלת, מסתיים בנימוס
    assert "קובץ לא נמצא" in result.stdout


def test_concat_transition_duration_longer_than_shortest_clip_errors_clearly(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000", duration=2)
    _make_solid_color_clip_with_audio(str(input_dir / "green.mp4"), "0x00FF00", duration=5)

    result = _run_script([
        "--input_dir", str(input_dir), "--codec", "h264",
        "--concat-files", json.dumps(["red.mp4", "green.mp4"]),
        "--concat-transition-duration", "3.0",
    ])
    assert result.returncode == 0
    assert "ארוך מדי" in result.stdout


def test_concat_invalid_json_errors_clearly(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000")

    result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--concat-files", "not valid json"])
    assert result.returncode == 0
    assert "--concat-files אינו JSON תקין" in result.stdout


def test_concat_single_file_list_rejected():
    result = _run_script(["--input_dir", ".", "--codec", "h264", "--concat-files", json.dumps(["only_one.mp4"])])
    assert result.returncode == 0
    assert "לפחות שני שמות-קבצים" in result.stdout


def test_concat_missing_audio_on_some_clips_falls_back_to_video_only(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_solid_color_clip_with_audio(str(input_dir / "red.mp4"), "0xFF0000")
    # ירוק בלי אודיו בכלל.
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=c=0x00FF00:s=640x480:d=5:r=10", "-pix_fmt", "yuv420p", str(input_dir / "green.mp4")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert r.returncode == 0

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "concat_noaudio_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
            "--concat-files", json.dumps(["red.mp4", "green.mp4"]),
            "--concat-output-name", "concat_noaudio",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "לא לכל הקטעים יש אודיו" in result.stdout
        assert os.path.exists(output_path)
        assert not _has_audio_stream(output_path)
    finally:
        remove_video_editor_output(output_path)
