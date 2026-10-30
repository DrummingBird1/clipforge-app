# tests/bot/test_thumbnail_candidates.py
#
# בודק utils/media/thumbnail_candidates.py עם ffmpeg אמיתי (item: A/B thumbnail testing) -
# קליפ testsrc אמיתי, לא מוק.
import os
import shutil
import subprocess


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.media.thumbnail_candidates import generate_candidates


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - הטסטים האלה מדולגים",
)


def _make_clip(path, duration=3):
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=640x360:rate=10", "-pix_fmt", "yuv420p", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, result.stderr


def test_generates_three_candidates_for_a_normal_clip(tmp_path):
    clip = tmp_path / "clip.mp4"
    _make_clip(clip)
    out_dir = tmp_path / "candidates"

    paths = generate_candidates(str(clip), str(out_dir), get_ffmpeg_exe(), get_ffprobe_exe())

    assert len(paths) == 3
    for p in paths:
        assert os.path.exists(p)
        assert os.path.getsize(p) > 0


def test_candidate_filenames_are_indexed_in_order(tmp_path):
    clip = tmp_path / "clip.mp4"
    _make_clip(clip)
    out_dir = tmp_path / "candidates"

    paths = generate_candidates(str(clip), str(out_dir), get_ffmpeg_exe(), get_ffprobe_exe())

    assert [os.path.basename(p) for p in paths] == ["candidate_0.jpg", "candidate_1.jpg", "candidate_2.jpg"]


def test_creates_out_dir_if_missing(tmp_path):
    clip = tmp_path / "clip.mp4"
    _make_clip(clip)
    out_dir = tmp_path / "nested" / "candidates"

    generate_candidates(str(clip), str(out_dir), get_ffmpeg_exe(), get_ffprobe_exe())

    assert out_dir.exists()


def test_returns_empty_list_for_a_corrupt_video_file(tmp_path):
    fake_video = tmp_path / "not_really_a_video.mp4"
    fake_video.write_bytes(b"this is not video data")
    out_dir = tmp_path / "candidates"

    paths = generate_candidates(str(fake_video), str(out_dir), get_ffmpeg_exe(), get_ffprobe_exe())

    assert paths == []
