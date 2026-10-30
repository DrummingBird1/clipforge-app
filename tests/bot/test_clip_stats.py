# tests/bot/test_clip_stats.py
#
# בודק utils/media/clip_stats.py's get_clips_captured_by_day (item: personal stats
# dashboard) - mtime אמיתי של קבצים ב-tmp_path, לא ממופתח.
import os
from datetime import date, datetime, timedelta


from utils.media.clip_stats import get_clips_captured_by_day


def _make_clip(clips_dir, name, days_ago):
    clips_dir.mkdir(parents=True, exist_ok=True)
    path = clips_dir / name
    path.write_bytes(b"fake")
    target_day = date.today() - timedelta(days=days_ago)
    target_time = datetime(target_day.year, target_day.month, target_day.day, 12, 0, 0).timestamp()
    os.utime(path, (target_time, target_time))
    return path


def test_returns_zero_filled_entry_for_every_day_in_range(tmp_path):
    counts = get_clips_captured_by_day(str(tmp_path / "clips"), days=7)

    assert len(counts) == 7
    assert all(v == 0 for v in counts.values())


def test_days_are_ordered_oldest_to_newest(tmp_path):
    counts = get_clips_captured_by_day(str(tmp_path / "clips"), days=5)

    keys = list(counts.keys())
    assert keys == sorted(keys)
    assert keys[-1] == date.today().isoformat()


def test_counts_clips_on_their_capture_day(tmp_path):
    clips_dir = tmp_path / "clips"
    _make_clip(clips_dir, "today_a.mp4", days_ago=0)
    _make_clip(clips_dir, "today_b.mp4", days_ago=0)
    _make_clip(clips_dir, "yesterday.mp4", days_ago=1)

    counts = get_clips_captured_by_day(str(clips_dir), days=7)

    assert counts[date.today().isoformat()] == 2
    assert counts[(date.today() - timedelta(days=1)).isoformat()] == 1


def test_clips_older_than_range_are_excluded(tmp_path):
    clips_dir = tmp_path / "clips"
    _make_clip(clips_dir, "ancient.mp4", days_ago=100)

    counts = get_clips_captured_by_day(str(clips_dir), days=7)

    assert sum(counts.values()) == 0


def test_missing_clips_dir_returns_all_zero_days(tmp_path):
    counts = get_clips_captured_by_day(str(tmp_path / "nonexistent"), days=10)

    assert len(counts) == 10
    assert sum(counts.values()) == 0
