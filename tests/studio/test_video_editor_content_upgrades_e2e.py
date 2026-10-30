# tests/studio/test_video_editor_content_upgrades_e2e.py
#
# טסטי end-to-end אמיתיים (מריצים my_scripts/video/video_editor.py כתת-תהליך
# אמיתי, בדיוק כמו test_video_editor_mega_upgrade_e2e.py) לחמש התכונות
# שנוספו בסבב "עריכה ותוכן": Fade-in/fade-out, כיתוב טקסט קבוע, החלפת פס קול
# חלופי, חיתוך כמה טווחים (--remove-ranges), וממשק batch לדריסת דגלים פר-קובץ.
import os
from tests import PROJECT_ROOT
import subprocess
import sys


import json

import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")


def _is_runnable(exe_path):
    import shutil
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _run_script(args, timeout=120):
    return subprocess.run(
        [sys.executable, SCRIPT] + args, cwd=BASE_DIR, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, creationflags=NO_WINDOW_FLAGS,
    )


def _make_synthetic_video(path, duration=4, width=320, height=240, rate=10):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={rate}",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_synthetic_video_with_audio(path, duration=4, width=320, height=240, rate=10):
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={rate}",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "aac",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_audio_only_file(path, duration=2, frequency=440):
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={duration}", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _pixel_rgb_at(path, x, y, frame_time=0.0):
    cmd = [
        get_ffmpeg_exe(), "-v", "error", "-ss", f"{frame_time}", "-i", path,
        "-vf", f"crop=2:2:{x}:{y}", "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert len(result.stdout) == 12, f"ציפינו לבלוק 2x2 (12 בתים), קיבלנו {len(result.stdout)}"
    return tuple(result.stdout[:3])


def _probe_duration(path):
    cmd = [get_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return float(result.stdout.strip())


def _has_audio_stream(path):
    cmd = [get_ffprobe_exe(), "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return "audio" in result.stdout


def _result_json(stdout):
    for line in stdout.splitlines():
        if line.startswith("RESULT: "):
            return json.loads(line[len("RESULT: "):])
    raise AssertionError(f"לא נמצאה שורת RESULT: בפלט:\n{stdout}")


# --- Fade-in/fade-out (item) ---

def test_fade_in_darkens_first_frame(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "fade_in_clip.mp4"
    _make_synthetic_video(str(src_path), duration=3)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "fade_in_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--fade-in-seconds", "1.0"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        # הפריים הראשון-ממש (t=0) אמור להיות שחור-לגמרי (תחילת fade-in).
        rgb_at_start = _pixel_rgb_at(output_path, 100, 100, frame_time=0.0)
        assert sum(rgb_at_start) < 20, f"ציפינו לפריים כמעט-שחור בהתחלה עם fade-in, קיבלנו {rgb_at_start}"
    finally:
        remove_video_editor_output(output_path)


def test_fade_out_darkens_last_frame(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "fade_out_clip.mp4"
    _make_synthetic_video(str(src_path), duration=3)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "fade_out_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--fade-out-seconds", "1.0"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        duration = _probe_duration(output_path)
        rgb_near_end = _pixel_rgb_at(output_path, 100, 100, frame_time=max(0.0, duration - 0.15))
        assert sum(rgb_near_end) < 20, f"ציפינו לפריים כמעט-שחור בסוף עם fade-out, קיבלנו {rgb_near_end}"
    finally:
        remove_video_editor_output(output_path)


def test_fade_in_and_out_with_audio_render_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "fade_both_clip.mp4"
    _make_synthetic_video_with_audio(str(src_path), duration=3)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "fade_both_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
            "--fade-in-seconds", "0.5", "--fade-out-seconds", "0.5",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _has_audio_stream(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- כיתוב טקסט קבוע (item) ---

def test_text_overlay_renders_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "text_clip.mp4"
    _make_synthetic_video(str(src_path), duration=2)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "text_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--text", "Hello World"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_text_overlay_with_special_characters_does_not_break_filtergraph(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "text_special_clip.mp4"
    _make_synthetic_video(str(src_path), duration=2)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "text_special_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--text", "Score: 10:5 (50%) - it's close!"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_text_overlay_all_positions_render_successfully(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "text_positions_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1)

    for position in ("bottom", "top", "center"):
        output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "text_positions_clip_edited_horizontal.mp4")
        remove_video_editor_output(output_path)
        try:
            result = _run_script([
                "--input_dir", str(input_dir), "--codec", "h264", "--text", "Pos", "--text-position", position,
            ])
            assert result.returncode == 0, f"position={position}: {result.stdout + result.stderr}"
            assert os.path.exists(output_path)
        finally:
            remove_video_editor_output(output_path)


# --- החלפת פס קול חלופי (item) ---

def test_replace_audio_swaps_the_audio_track(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "replace_audio_clip.mp4"
    _make_synthetic_video_with_audio(str(src_path), duration=2)
    replacement_path = tmp_path / "replacement.wav"
    _make_audio_only_file(str(replacement_path), duration=2, frequency=200)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "replace_audio_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--replace-audio", str(replacement_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _has_audio_stream(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_replace_audio_implies_keep_audio_without_explicit_flag(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "replace_audio_implicit_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1)  # בלי אודיו במקור בכלל
    replacement_path = tmp_path / "replacement2.wav"
    _make_audio_only_file(str(replacement_path), duration=1)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "replace_audio_implicit_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--replace-audio", str(replacement_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "מפעיל שמירת אודיו אוטומטית" in result.stdout
        assert _has_audio_stream(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_replace_audio_with_watermark_and_pip_uses_correct_input_index(tmp_path):
    # item: הרגרסיה החשובה ביותר לבדוק - replace_audio_input_index חייב להתחשב
    # בכל ה--i-ים שכבר נוספו (video+PiP+watermark) לפני שלו, אחרת הוא היה
    # מצביע בטעות על קובץ ה-watermark/PiP במקום על קובץ האודיו האמיתי.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "replace_audio_wm_pip_clip.mp4"
    _make_synthetic_video_with_audio(str(src_path), duration=2)
    from PIL import Image
    watermark_path = tmp_path / "logo.png"
    Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(str(watermark_path))
    pip_path = tmp_path / "pip.mp4"
    _make_synthetic_video(str(pip_path), duration=2, width=160, height=120)
    replacement_path = tmp_path / "replacement3.wav"
    _make_audio_only_file(str(replacement_path), duration=2)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "replace_audio_wm_pip_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--watermark_path", str(watermark_path), "--pip", str(pip_path),
            "--replace-audio", str(replacement_path),
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        assert _has_audio_stream(output_path)
    finally:
        remove_video_editor_output(output_path)


# --- חיתוך כמה טווחים (item: --remove-ranges) ---

def test_remove_ranges_shortens_output(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "remove_ranges_clip.mp4"
    _make_synthetic_video_with_audio(str(src_path), duration=6)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "remove_ranges_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264", "--keep-audio",
            "--remove-ranges", "[[2,4]]",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        duration = _probe_duration(output_path)
        # מקור 6s, מסירים [2,4] (2s) - נשארים ~4s.
        assert duration < 5.0, f"ציפינו ש-2s יוסרו (~4s נשאר), קיבלנו {duration}"
    finally:
        remove_video_editor_output(output_path)


def test_remove_ranges_invalid_json_warns_and_continues(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "remove_ranges_invalid_clip.mp4"
    _make_synthetic_video(str(src_path), duration=2)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "remove_ranges_invalid_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--remove-ranges", "not json"])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--remove-ranges אינו JSON תקין" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_remove_ranges_ignored_when_combined_with_explicit_trim(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "remove_ranges_vs_trim_clip.mp4"
    _make_synthetic_video(str(src_path), duration=6)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "remove_ranges_vs_trim_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--trim-start", "1", "--remove-ranges", "[[2,3]]",
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--remove-ranges מתעלם" in result.stdout
    finally:
        remove_video_editor_output(output_path)


# --- ממשק batch לדריסת דגלים פר-קובץ (item: --batch-overrides) ---

def test_batch_overrides_applies_per_file_trim(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    default_clip = input_dir / "default_clip.mp4"
    overridden_clip = input_dir / "overridden_clip.mp4"
    _make_synthetic_video(str(default_clip), duration=4)
    _make_synthetic_video(str(overridden_clip), duration=4)
    overrides_path = tmp_path / "overrides.json"
    overrides_path.write_text(json.dumps({"overridden_clip.mp4": {"trim_duration": 1}}), encoding="utf-8")

    default_output = os.path.join(HORIZONTAL_OUTPUT_DIR, "default_clip_edited_horizontal.mp4")
    overridden_output = os.path.join(HORIZONTAL_OUTPUT_DIR, "overridden_clip_edited_horizontal.mp4")
    remove_video_editor_output(default_output)
    remove_video_editor_output(overridden_output)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--batch-overrides", str(overrides_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(default_output) and os.path.exists(overridden_output)
        default_duration = _probe_duration(default_output)
        overridden_duration = _probe_duration(overridden_output)
        assert default_duration > 2.0, f"הקובץ בלי override אמור לשמור על האורך המלא (~4s), קיבלנו {default_duration}"
        assert overridden_duration < 2.0, f"הקובץ עם trim_duration=1 override אמור להתקצר ל-~1s, קיבלנו {overridden_duration}"
    finally:
        remove_video_editor_output(default_output)
        remove_video_editor_output(overridden_output)


def test_batch_overrides_missing_file_warns_and_continues(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "batch_overrides_missing_clip.mp4"
    _make_synthetic_video(str(src_path), duration=1)

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "batch_overrides_missing_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script([
            "--input_dir", str(input_dir), "--codec", "h264",
            "--batch-overrides", str(tmp_path / "does_not_exist.json"),
        ])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--batch-overrides" in result.stdout and "לא ניתן לקרוא" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


def test_batch_overrides_unknown_field_warns_but_applies_known_ones(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "batch_overrides_unknown_field_clip.mp4"
    _make_synthetic_video(str(src_path), duration=4)
    overrides_path = tmp_path / "overrides_unknown.json"
    overrides_path.write_text(
        json.dumps({"batch_overrides_unknown_field_clip.mp4": {"trim_duration": 1, "codec": "hevc"}}), encoding="utf-8",
    )

    output_path = os.path.join(HORIZONTAL_OUTPUT_DIR, "batch_overrides_unknown_field_clip_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = _run_script(["--input_dir", str(input_dir), "--codec", "h264", "--batch-overrides", str(overrides_path)])
        assert result.returncode == 0, result.stdout + result.stderr
        assert "שדות לא-נתמכים" in result.stdout and "codec" in result.stdout
        assert os.path.exists(output_path)
        assert _probe_duration(output_path) < 2.0  # trim_duration=1 עדיין הוחל
    finally:
        remove_video_editor_output(output_path)
