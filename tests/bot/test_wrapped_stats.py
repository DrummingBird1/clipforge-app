# tests/bot/test_wrapped_stats.py
#
# בודק utils/media/wrapped_stats.py (item: annual "Wrapped" video) - כל הלוגיקה כאן
# טהורה (בלי ffmpeg), אז הטסטים משתמשים בקבצים אמיתיים (mtime אמיתי דרך
# os.utime) בלי תוכן וידאו אמיתי בכלל.
import json
import os
from datetime import datetime


from utils.media.wrapped_stats import (
    count_successful_jobs_and_hours_for_year,
    gather_year_clips,
    get_top_tags_for_year,
    sample_highlight_clips,
)


def _touch_with_mtime(path, year, month=6, day=15):
    path.write_bytes(b"fake")
    ts = datetime(year, month, day, 12, 0, 0).timestamp()
    os.utime(path, (ts, ts))


# --- gather_year_clips ---

def test_gather_year_clips_includes_only_matching_year(tmp_path):
    _touch_with_mtime(tmp_path / "in_year.mp4", 2026)
    _touch_with_mtime(tmp_path / "other_year.mp4", 2025)

    clips = gather_year_clips(str(tmp_path), 2026)

    assert [os.path.basename(c) for c in clips] == ["in_year.mp4"]


def test_gather_year_clips_excludes_previous_recap_outputs(tmp_path):
    _touch_with_mtime(tmp_path / "clip.mp4", 2026)
    _touch_with_mtime(tmp_path / "Yearly_Recap_2026-01-01.mp4", 2026)

    clips = gather_year_clips(str(tmp_path), 2026)

    assert [os.path.basename(c) for c in clips] == ["clip.mp4"]


def test_gather_year_clips_excludes_previous_wrapped_outputs(tmp_path):
    _touch_with_mtime(tmp_path / "clip.mp4", 2026)
    _touch_with_mtime(tmp_path / "Wrapped_2026.mp4", 2026)

    clips = gather_year_clips(str(tmp_path), 2026)

    assert [os.path.basename(c) for c in clips] == ["clip.mp4"]


def test_gather_year_clips_sorted_oldest_to_newest(tmp_path):
    _touch_with_mtime(tmp_path / "december.mp4", 2026, month=12, day=1)
    _touch_with_mtime(tmp_path / "january.mp4", 2026, month=1, day=1)

    clips = gather_year_clips(str(tmp_path), 2026)

    assert [os.path.basename(c) for c in clips] == ["january.mp4", "december.mp4"]


def test_gather_year_clips_empty_when_none_match(tmp_path):
    _touch_with_mtime(tmp_path / "clip.mp4", 2025)

    assert gather_year_clips(str(tmp_path), 2026) == []


# --- sample_highlight_clips ---

def test_sample_highlight_clips_returns_all_when_under_the_cap():
    clips = ["a", "b", "c"]
    assert sample_highlight_clips(clips, 12) == clips


def test_sample_highlight_clips_caps_at_max_clips():
    clips = [str(i) for i in range(100)]
    assert len(sample_highlight_clips(clips, 12)) == 12


def test_sample_highlight_clips_spreads_across_the_full_range():
    clips = [str(i) for i in range(100)]
    sampled = sample_highlight_clips(clips, 10)
    assert sampled[0] == "0"
    # דגימה פרוסה - האחרון הנדגם אמור להיות קרוב לסוף הרשימה, לא מרוכז בהתחלה
    assert int(sampled[-1]) >= 80


# --- count_successful_jobs_and_hours_for_year ---

def test_count_successful_jobs_counts_only_success_status_in_year():
    rows = [
        ("video_editor.py", "success", "2026-03-01T10:00:00", 3600.0, None),
        ("video_editor.py", "failed", "2026-03-02T10:00:00", 100.0, None),
        ("video_editor.py", "success", "2025-01-01T10:00:00", 500.0, None),
    ]

    run_count, total_hours = count_successful_jobs_and_hours_for_year(rows, 2026)

    assert run_count == 1
    assert total_hours == 1.0


def test_count_successful_jobs_handles_none_duration():
    rows = [("video_editor.py", "success", "2026-01-01T00:00:00", None, None)]

    run_count, total_hours = count_successful_jobs_and_hours_for_year(rows, 2026)

    assert run_count == 1
    assert total_hours == 0.0


def test_count_successful_jobs_zero_when_no_matches():
    rows = [("video_editor.py", "success", "2025-01-01T00:00:00", 100.0, None)]

    assert count_successful_jobs_and_hours_for_year(rows, 2026) == (0, 0.0)


# --- get_top_tags_for_year ---

def _write_tag_cache(cache_dir, basename, year, tags, month=6, day=15):
    os.makedirs(cache_dir, exist_ok=True)
    mtime = int(datetime(year, month, day, 12, 0, 0).timestamp())
    with open(os.path.join(cache_dir, f"{basename}.{mtime}.json"), "w", encoding="utf-8") as f:
        json.dump({"tags": tags}, f)


def test_get_top_tags_for_year_counts_frequency_across_clips(tmp_path):
    _write_tag_cache(str(tmp_path), "a.mp4", 2026, ["Goal", "Save"])
    _write_tag_cache(str(tmp_path), "b.mp4", 2026, ["Goal"])

    top = get_top_tags_for_year(str(tmp_path), 2026)

    assert top[0] == ("Goal", 2)


def test_get_top_tags_for_year_excludes_other_years(tmp_path):
    _write_tag_cache(str(tmp_path), "a.mp4", 2025, ["OldTag"])
    _write_tag_cache(str(tmp_path), "b.mp4", 2026, ["NewTag"])

    top = get_top_tags_for_year(str(tmp_path), 2026)

    assert top == [("NewTag", 1)]


def test_get_top_tags_for_year_respects_limit(tmp_path):
    for i in range(5):
        _write_tag_cache(str(tmp_path), f"clip{i}.mp4", 2026, [f"tag{i}"])

    assert len(get_top_tags_for_year(str(tmp_path), 2026, limit=2)) == 2


def test_get_top_tags_for_year_empty_when_cache_dir_missing(tmp_path):
    assert get_top_tags_for_year(str(tmp_path / "nonexistent"), 2026) == []


def test_get_top_tags_for_year_ignores_corrupt_cache_files(tmp_path):
    mtime = int(datetime(2026, 6, 15).timestamp())
    os.makedirs(tmp_path, exist_ok=True)
    with open(os.path.join(str(tmp_path), f"broken.{mtime}.json"), "w", encoding="utf-8") as f:
        f.write("not valid json{{{")
    _write_tag_cache(str(tmp_path), "good.mp4", 2026, ["Goal"])

    assert get_top_tags_for_year(str(tmp_path), 2026) == [("Goal", 1)]
