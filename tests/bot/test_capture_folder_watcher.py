# tests/bot/test_capture_folder_watcher.py
#
# בודק את my_scripts/stream/capture_folder_watcher.py's watch() בפועל (item:
# אינטגרציה עם תוכנת לכידה נוספת) - קבצים אמיתיים על דיסק, לולאה אמיתית
# (לא ממופתחת), רק time.sleep מוחלף בפונקציה שעוצרת את הלולאה אחרי N איטרציות
# (מדמה את כפתור "עצור" ב-GUI) כדי שהטסט לא ירוץ לנצח.


import pytest

from my_scripts.stream import capture_folder_watcher


def test_watch_copies_a_file_once_it_becomes_stable(tmp_path, monkeypatch):
    watch_dir = tmp_path / "capture_output"
    watch_dir.mkdir()
    target_dir = tmp_path / "import"
    target_dir.mkdir()
    (watch_dir / "clip.mp4").write_bytes(b"stable content")

    call_count = {"n": 0}

    def fake_sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] >= 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(capture_folder_watcher.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        capture_folder_watcher.watch(str(watch_dir), str(target_dir), poll_interval=0)

    assert (target_dir / "clip.mp4").exists()
    assert (target_dir / "clip.mp4").read_bytes() == b"stable content"
    # copy, לא move - המקור נשאר במקומו (זהה ל-obs_replay_watcher.py)
    assert (watch_dir / "clip.mp4").exists()


def test_watch_does_not_copy_a_file_still_being_written(tmp_path, monkeypatch):
    watch_dir = tmp_path / "capture_output"
    watch_dir.mkdir()
    target_dir = tmp_path / "import"
    target_dir.mkdir()
    clip_path = watch_dir / "clip.mp4"
    clip_path.write_bytes(b"a")

    call_count = {"n": 0}

    def fake_sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] == 1:
            clip_path.write_bytes(b"a" * 500)  # התוכנה עדיין כותבת - הגודל גדל
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(capture_folder_watcher.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        capture_folder_watcher.watch(str(watch_dir), str(target_dir), poll_interval=0)

    assert not (target_dir / "clip.mp4").exists()


def test_watch_does_not_recopy_a_file_already_present_at_the_destination(tmp_path, monkeypatch):
    watch_dir = tmp_path / "capture_output"
    watch_dir.mkdir()
    target_dir = tmp_path / "import"
    target_dir.mkdir()
    (watch_dir / "clip.mp4").write_bytes(b"source content")
    (target_dir / "clip.mp4").write_bytes(b"already there - do not overwrite")

    call_count = {"n": 0}

    def fake_sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(capture_folder_watcher.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        capture_folder_watcher.watch(str(watch_dir), str(target_dir), poll_interval=0)

    assert (target_dir / "clip.mp4").read_bytes() == b"already there - do not overwrite"


def test_watch_ignores_non_video_files(tmp_path, monkeypatch):
    watch_dir = tmp_path / "capture_output"
    watch_dir.mkdir()
    target_dir = tmp_path / "import"
    target_dir.mkdir()
    (watch_dir / "readme.txt").write_bytes(b"not a video")

    call_count = {"n": 0}

    def fake_sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] >= 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(capture_folder_watcher.time, "sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        capture_folder_watcher.watch(str(watch_dir), str(target_dir), poll_interval=0)

    assert list(target_dir.iterdir()) == []
