# tests/bot/test_weekly_compilation_e2e.py
#
# בודק my_scripts/video/weekly_compilation.py כתת-תהליך אמיתי (subprocess),
# עם קליפים אמיתיים שנוצרו ע"י ffmpeg (לא מוקים) - כולל את ההרחבה ל-ריקאפ
# תקופתי (--period week/month/year) ופרקים אוטומטיים (item).
import os
from tests import PROJECT_ROOT
import shutil
import subprocess
import sys
import time


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "weekly_compilation.py")


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסטי ה-E2E מדולגים (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_clip(path, duration=1, width=320, height=240):
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=10", "-pix_fmt", "yuv420p", path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קליפ הבדיקה נכשלה: {result.stderr}"


def _run(output_base, extra_args=()):
    cmd = [sys.executable, SCRIPT, "--output_base", str(output_base), *extra_args]
    return subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=90, creationflags=NO_WINDOW_FLAGS)


def _youtube_dir(output_base):
    d = output_base / "rocket_shorts" / "YouTube"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _touch_mtime(path, days_ago):
    ts = time.time() - (days_ago * 86400)
    os.utime(path, (ts, ts))


def test_default_period_behaves_like_a_week(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    recent = yt_dir / "recent_clip.mp4"
    old = yt_dir / "old_clip.mp4"
    _make_clip(recent)
    _make_clip(old)
    _touch_mtime(recent, days_ago=2)
    _touch_mtime(old, days_ago=10)  # מחוץ לשבוע, אמור להידחות

    result = _run(tmp_path)

    assert result.returncode == 0
    outputs = list(yt_dir.glob("Weekly_Recap_*.mp4"))
    assert len(outputs) == 1
    assert "recent_clip.mp4" in result.stdout
    assert "old_clip.mp4" not in result.stdout


def test_period_month_includes_a_clip_older_than_a_week(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    clip = yt_dir / "clip_from_20_days_ago.mp4"
    _make_clip(clip)
    _touch_mtime(clip, days_ago=20)  # מחוץ לשבוע, בתוך חודש

    result = _run(tmp_path, extra_args=["--period", "month"])

    assert result.returncode == 0
    outputs = list(yt_dir.glob("Monthly_Recap_*.mp4"))
    assert len(outputs) == 1
    assert "clip_from_20_days_ago.mp4" in result.stdout


def test_period_year_includes_a_clip_older_than_a_month(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    clip = yt_dir / "clip_from_100_days_ago.mp4"
    _make_clip(clip)
    _touch_mtime(clip, days_ago=100)

    result = _run(tmp_path, extra_args=["--period", "year"])

    assert result.returncode == 0
    outputs = list(yt_dir.glob("Yearly_Recap_*.mp4"))
    assert len(outputs) == 1


def test_explicit_days_overrides_period(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    clip = yt_dir / "clip_from_20_days_ago.mp4"
    _make_clip(clip)
    _touch_mtime(clip, days_ago=20)

    # --period year (365 ימים) היה כולל את זה, אבל --days 5 המפורש גובר
    result = _run(tmp_path, extra_args=["--period", "year", "--days", "5"])

    assert result.returncode == 0
    assert "לא נמצאו קליפים חדשים" in result.stdout
    assert list(yt_dir.glob("*_Recap_*.mp4")) == []


def test_chapters_file_is_created_with_correct_cumulative_timestamps(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    clip_a = yt_dir / "aaa_first.mp4"
    clip_b = yt_dir / "bbb_second.mp4"
    _make_clip(clip_a, duration=2)
    _make_clip(clip_b, duration=3)

    result = _run(tmp_path)

    assert result.returncode == 0
    outputs = list(yt_dir.glob("Weekly_Recap_*.mp4"))
    assert len(outputs) == 1
    chapters_path = str(outputs[0]) + ".chapters.txt"
    assert os.path.exists(chapters_path)
    chapters_text = open(chapters_path, encoding="utf-8").read()
    lines = chapters_text.splitlines()
    assert len(lines) == 2
    assert lines[0] == "0:00 aaa_first.mp4"
    assert lines[1].startswith("0:0") and "bbb_second.mp4" in lines[1]  # ~2 שניות אחרי ההתחלה
    assert "פרקים ליוטיוב" in result.stdout


def test_a_previous_recap_output_is_not_swept_up_as_an_input_clip(tmp_path):
    yt_dir = _youtube_dir(tmp_path)
    real_clip = yt_dir / "real_clip.mp4"
    _make_clip(real_clip)
    # מדמה ריקאפ שבועי שכבר נוצר בעבר - חייב להישאר מודר גם מריקאפ חודשי הבא
    fake_previous_recap = yt_dir / "Weekly_Recap_2026-01-01.mp4"
    _make_clip(fake_previous_recap)

    result = _run(tmp_path, extra_args=["--period", "month"])

    assert result.returncode == 0
    assert "real_clip.mp4" in result.stdout
    assert "Weekly_Recap_2026-01-01.mp4" not in result.stdout


def test_no_clips_found_reports_info_message_and_creates_nothing(tmp_path):
    _youtube_dir(tmp_path)  # תיקייה קיימת, ריקה

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "לא נמצאו קליפים חדשים" in result.stdout


def test_tiktok_source_reads_from_the_vertical_tiktok_folder(tmp_path):
    tt_dir = tmp_path / "rocket_shorts" / "TikTok"
    tt_dir.mkdir(parents=True)
    clip = tt_dir / "vertical_clip.mp4"
    _make_clip(clip, width=240, height=320)

    result = _run(tmp_path, extra_args=["--source", "tiktok"])

    assert result.returncode == 0
    assert "vertical_clip.mp4" in result.stdout
    assert list(tt_dir.glob("Weekly_Recap_*.mp4"))
