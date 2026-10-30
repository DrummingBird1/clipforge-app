# tests/bot/test_timelapse.py
import os


from utils.media.timelapse import (
    build_atempo_chain,
    build_filter_complex,
    compute_speed_factor,
    find_video_files,
    find_video_files_by_folder,
)


def test_compute_speed_factor_basic():
    assert compute_speed_factor(600, 60) == 10.0


def test_compute_speed_factor_returns_none_when_already_short():
    assert compute_speed_factor(30, 60) is None
    assert compute_speed_factor(60, 60) is None  # בדיוק שווה - אין מה להאיץ


def test_compute_speed_factor_rejects_non_positive_target():
    import pytest
    with pytest.raises(ValueError):
        compute_speed_factor(600, 0)


def test_build_atempo_chain_single_stage_when_within_range():
    assert build_atempo_chain(1.5) == "atempo=1.500000"


def test_build_atempo_chain_chains_multiple_stages_for_high_factor():
    # 180 = 2*2*2*2*2*2*2 * (180/128) -> 7 שלבי atempo=2.0 + שארית
    chain = build_atempo_chain(180)
    stages = chain.split(",")
    assert stages.count("atempo=2.0") == 7
    assert stages[-1] != "atempo=2.0"


def test_build_atempo_chain_rejects_non_positive():
    import pytest
    with pytest.raises(ValueError):
        build_atempo_chain(0)


def test_build_filter_complex_without_audio():
    filter_str, maps = build_filter_complex("setpts=PTS/10.0", "scale=1920:1080", 30, 10.0, keep_audio=False)
    assert filter_str == "[0:v]setpts=PTS/10.0,scale=1920:1080,fps=30[outv]"
    assert maps == ["-map", "[outv]"]


def test_build_filter_complex_with_audio():
    filter_str, maps = build_filter_complex("setpts=PTS/4.0", "scale=1080:1920", 30, 4.0, keep_audio=True)
    assert "[0:v]setpts=PTS/4.0,scale=1080:1920,fps=30[outv]" in filter_str
    assert "[0:a]atempo=2.0,atempo=2.000000[outa]" in filter_str
    assert maps == ["-map", "[outv]", "-map", "[outa]"]


def test_find_video_files_matches_known_extensions(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    (tmp_path / "clip.mkv").write_bytes(b"x")
    (tmp_path / "clip.webm").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    found = find_video_files(str(tmp_path))

    names = sorted(os.path.basename(f) for f in found)
    assert names == ["clip.mkv", "clip.mp4", "clip.webm"]


def test_find_video_files_by_folder_groups_by_containing_folder(tmp_path):
    (tmp_path / "root_clip.mp4").write_bytes(b"x")
    sub1 = tmp_path / "Session1"
    sub1.mkdir()
    (sub1 / "a.mp4").write_bytes(b"x")
    (sub1 / "b.mkv").write_bytes(b"x")
    sub2 = tmp_path / "Session2" / "Nested"
    sub2.mkdir(parents=True)
    (sub2 / "c.mp4").write_bytes(b"x")
    empty_dir = tmp_path / "EmptyFolder"
    empty_dir.mkdir()

    groups = find_video_files_by_folder(str(tmp_path))

    by_folder = {os.path.relpath(folder, str(tmp_path)): sorted(os.path.basename(f) for f in files) for folder, files in groups}
    assert by_folder == {
        ".": ["root_clip.mp4"],
        "Session1": ["a.mp4", "b.mkv"],
        os.path.join("Session2", "Nested"): ["c.mp4"],
    }


def test_find_video_files_by_folder_skips_folders_with_no_videos(tmp_path):
    only_notes = tmp_path / "JustNotes"
    only_notes.mkdir()
    (only_notes / "notes.txt").write_bytes(b"x")

    groups = find_video_files_by_folder(str(tmp_path))

    assert groups == []
