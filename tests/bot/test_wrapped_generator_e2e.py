# tests/bot/test_wrapped_generator_e2e.py
#
# בודק my_scripts/video/wrapped_generator.py כתת-תהליך אמיתי (subprocess), עם
# קליפים אמיתיים שנוצרו ע"י ffmpeg - זהה במבנה ל-test_weekly_compilation_e2e.py.
#
# הערה: הסקריפט קורא ל-utils/shared/job_history.py ו-utils/media/game_playtime.py, ששניהם
# תמיד פונים ל-data/clipforge_data.db *האמיתי* של הפרויקט (אין override של נתיב
# DB דרך args - אותה מוסכמה בדיוק בכל הקודבייס הזה). זה קריאה-בלבד (לעולם לא
# כתיבה, מלבד CREATE TABLE IF NOT EXISTS אידמפוטנטי) ולכן בטוח, אבל אומר
# שערכי render_hours/top_game_hours בפועל תלויים בנתונים אמיתיים על המכונה -
# הטסטים כאן בודקים רק דברים דטרמיניסטיים (clips_published, קיום/גודל הפלט),
# לא את הערכים התלויים ב-DB האמיתי.
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys
import time


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "wrapped_generator.py")


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסטי ה-E2E מדולגים (ראו utils/shared/ffmpeg_locator.py)",
)

TEST_YEAR = 2019  # שנה ישנה ומאוד לא סבירה שיש בה נתוני job_history/game_playtime אמיתיים


def _make_clip(path, duration=1, width=320, height=240):
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=10", "-pix_fmt", "yuv420p", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קליפ הבדיקה נכשלה: {result.stderr}"


def _touch_mtime_in_year(path, year, month=6, day=15):
    from datetime import datetime
    ts = datetime(year, month, day, 12, 0, 0).timestamp()
    os.utime(path, (ts, ts))


def _run(output_base, extra_args=()):
    cmd = [sys.executable, SCRIPT, "--output_base", str(output_base), "--year", str(TEST_YEAR), *extra_args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)


def _youtube_dir(output_base):
    d = output_base / "rocket_shorts" / "YouTube"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_builds_a_wrapped_video_from_the_years_clips(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    for i in range(3):
        clip = yt_dir / f"clip_{i}.mp4"
        _make_clip(clip)
        _touch_mtime_in_year(clip, TEST_YEAR)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    outputs = list(yt_dir.glob(f"Wrapped_{TEST_YEAR}.mp4"))
    assert len(outputs) == 1
    assert outputs[0].stat().st_size > 0


def test_result_line_reports_correct_clip_count(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    for i in range(2):
        clip = yt_dir / f"clip_{i}.mp4"
        _make_clip(clip)
        _touch_mtime_in_year(clip, TEST_YEAR)

    result = _run(tmp_path)

    assert result.returncode == 0
    result_line = next(line for line in result.stdout.splitlines() if line.startswith("RESULT: "))
    payload = json.loads(result_line[len("RESULT: "):])
    assert payload["clips_published"] == 2
    assert payload["output"].endswith(f"Wrapped_{TEST_YEAR}.mp4")


def test_excludes_clips_from_other_years(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    in_year = yt_dir / "in_year.mp4"
    other_year = yt_dir / "other_year.mp4"
    _make_clip(in_year)
    _make_clip(other_year)
    _touch_mtime_in_year(in_year, TEST_YEAR)
    _touch_mtime_in_year(other_year, TEST_YEAR - 1)

    result = _run(tmp_path)

    assert result.returncode == 0
    result_line = next(line for line in result.stdout.splitlines() if line.startswith("RESULT: "))
    payload = json.loads(result_line[len("RESULT: "):])
    assert payload["clips_published"] == 1


def test_no_clips_for_year_reports_info_message_and_creates_nothing(tmp_path):
    _youtube_dir(tmp_path)  # תיקייה קיימת, ריקה

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "לא נמצאו קליפים" in result.stdout
    assert list(tmp_path.glob("**/Wrapped_*.mp4")) == []


def test_previous_wrapped_output_is_not_swept_up_as_an_input_clip(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    real_clip = yt_dir / "real_clip.mp4"
    _make_clip(real_clip)
    _touch_mtime_in_year(real_clip, TEST_YEAR)
    fake_previous_wrapped = yt_dir / f"Wrapped_{TEST_YEAR}.mp4"
    _make_clip(fake_previous_wrapped)
    _touch_mtime_in_year(fake_previous_wrapped, TEST_YEAR)

    result = _run(tmp_path)

    assert result.returncode == 0
    result_line = next(line for line in result.stdout.splitlines() if line.startswith("RESULT: "))
    payload = json.loads(result_line[len("RESULT: "):])
    assert payload["clips_published"] == 1


def test_work_directory_is_cleaned_up_after_a_successful_run(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    clip = yt_dir / "clip.mp4"
    _make_clip(clip)
    _touch_mtime_in_year(clip, TEST_YEAR)

    result = _run(tmp_path)

    assert result.returncode == 0
    assert not list(yt_dir.glob(f"_wrapped_{TEST_YEAR}_work"))


def test_tiktok_source_reads_from_the_vertical_tiktok_folder(tmp_path):
    tt_dir = tmp_path / "rocket_shorts" / "TikTok"
    tt_dir.mkdir(parents=True)
    clip = tt_dir / "vertical_clip.mp4"
    _make_clip(clip, width=240, height=320)
    _touch_mtime_in_year(clip, TEST_YEAR)

    result = _run(tmp_path, extra_args=["--source", "tiktok"])

    assert result.returncode == 0
    assert list(tt_dir.glob(f"Wrapped_{TEST_YEAR}.mp4"))


def test_defaults_to_current_year_when_not_specified(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    clip = yt_dir / "clip.mp4"
    _make_clip(clip)  # mtime = עכשיו, בפועל השנה הנוכחית

    cmd = [sys.executable, SCRIPT, "--output_base", str(tmp_path)]
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS)

    assert result.returncode == 0
    current_year = time.strftime("%Y")
    assert list(yt_dir.glob(f"Wrapped_{current_year}.mp4"))
