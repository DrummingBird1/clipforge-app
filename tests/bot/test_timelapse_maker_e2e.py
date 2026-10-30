# tests/bot/test_timelapse_maker_e2e.py
#
# טסט end-to-end אמיתי ל-my_scripts/video/timelapse_maker.py, עם דגש על אודיו:
# רגרסיה אמיתית שנתקל בה המשתמש - טיימלאפסים שהופקו מה-GUI יצאו שקטים לגמרי,
# כי --keep-audio (כבוי כברירת מחדל ב-CLI של הסקריפט) לא היה נגיש מהממשק בכלל
# (תוקן ב-ui/settings_tab.py + ui/dashboard.py + utils/shared/state.py). הטסט הזה מריץ
# את הסקריפט כתת-תהליך אמיתי על מקור עם וידאו+אודיו אמיתיים (ffmpeg lavfi -
# testsrc + sine, בלי נכס בינארי שמור בריפו), פעם עם --keep-audio ופעם בלי,
# ומוודא עם ffprobe שהפלט בפועל מכיל (או לא מכיל) זרם אודיו בהתאם.
import os
from tests import PROJECT_ROOT
import shutil
import subprocess
import sys
import uuid


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "timelapse_maker.py")
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "timelapses", "horizontal")
VERTICAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "timelapses", "vertical")


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_synthetic_video_with_audio(path, duration=3, width=320, height=240):
    """יוצר קובץ mp4 זעיר-אך-אמיתי עם וידאו (testsrc) ואודיו (sine) אמיתיים -
    בלי צורך בקובץ מדיה שמור בריפו."""
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=10",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
        "-shortest", "-pix_fmt", "yuv420p", "-c:a", "aac", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _has_audio_stream(path):
    cmd = [
        get_ffprobe_exe(), "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return "audio" in result.stdout.strip()


def _run_timelapse_maker(input_dir, extra_args):
    return subprocess.run(
        [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--target-seconds", "1", *extra_args],
        cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=60, creationflags=NO_WINDOW_FLAGS,
    )


def _output_paths(base_name):
    # timelapse_maker.py תמיד מייצא גם אופקי וגם אנכי מכל מקור - שני קבצים,
    # לא אחד (ראו process_video() - לולאה על ("horizontal", "vertical")).
    return [
        os.path.join(HORIZONTAL_OUTPUT_DIR, f"{base_name}_horizontal.mp4"),
        os.path.join(VERTICAL_OUTPUT_DIR, f"{base_name}_vertical.mp4"),
    ]


def _probe_name(prefix):
    # שם ייחודי לכל ריצה: תיקיית הפלט משותפת לכל ה-workers, וטסט שרץ פעמיים במקביל (או ניקוי של ריצה אחרת)
    # היה מוחק את הפלט של השני לפני הבדיקה
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_timelapse_maker_e2e_keep_audio_produces_a_real_audio_stream(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    name = _probe_name("e2e_pytest_probe_clip")
    src_path = input_dir / f"{name}.mp4"
    _make_synthetic_video_with_audio(str(src_path))

    output_paths = _output_paths(name)
    for p in output_paths:
        if os.path.exists(p):
            os.remove(p)

    try:
        result = _run_timelapse_maker(input_dir, ["--keep-audio"])
        assert result.returncode == 0, result.stdout + result.stderr
        for p in output_paths:
            assert os.path.exists(p), f"קובץ הפלט לא נוצר בפועל: {p}\n{result.stdout}"
            assert _has_audio_stream(p), f"הפלט ({p}) אמור להכיל זרם אודיו כש---keep-audio מועבר"
    finally:
        for p in output_paths:
            if os.path.exists(p):
                os.remove(p)


def test_timelapse_maker_e2e_without_keep_audio_produces_silent_output(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    name = _probe_name("e2e_pytest_probe_clip_silent")
    src_path = input_dir / f"{name}.mp4"
    _make_synthetic_video_with_audio(str(src_path))

    output_paths = _output_paths(name)
    for p in output_paths:
        if os.path.exists(p):
            os.remove(p)

    try:
        result = _run_timelapse_maker(input_dir, [])
        assert result.returncode == 0, result.stdout + result.stderr
        for p in output_paths:
            assert os.path.exists(p), f"קובץ הפלט לא נוצר בפועל: {p}\n{result.stdout}"
            assert not _has_audio_stream(p), f"ברירת המחדל של הסקריפט עצמו (בלי --keep-audio) היא ללא אודיו ({p})"
    finally:
        for p in output_paths:
            if os.path.exists(p):
                os.remove(p)
