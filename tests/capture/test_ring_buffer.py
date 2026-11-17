# tests/capture/test_ring_buffer.py
#
# utils/capture/ring_buffer.py: בחירת הקטעים לשמירה, מחיקה לפי חלון ותקרת דיסק, ורשימת ה-concat. בלי ffmpeg.
from utils.capture import ring_buffer as rb


def _segments(count, size=100):
    return [rb.Segment(i, f"C:/r/seg_{i:06d}.ts", size) for i in range(count)]


def test_listing_keeps_only_segment_files_in_order(tmp_path):
    for name in ("seg_000002.ts", "seg_000010.ts", "seg_000001.ts", "notes.txt", "seg_1.ts"):
        (tmp_path / name).write_bytes(b"x")
    assert [s.index for s in rb.list_segments(str(tmp_path))] == [1, 2, 10]
    assert rb.list_segments(str(tmp_path / "missing")) == []


def test_saving_30_seconds_takes_finished_segments_only():
    segments = _segments(40)
    picked = rb.select_for_save(segments, 30, segment_seconds=2)
    assert len(picked) == 16                  # 15 קטעים + אחד חלקי
    assert picked[-1].index == 38             # 39 עוד נכתב
    assert rb.select_for_save(segments[:1], 30) == []
    assert rb.select_for_save(segments, 0) == []


def test_the_window_is_kept_and_older_segments_go():
    segments = _segments(100)
    gone = rb.to_delete(segments, keep_seconds=60, segment_seconds=2)
    assert [s.index for s in gone] == list(range(0, 68))   # נשארים 30 + 2 מרווח


def test_the_disk_cap_trims_the_oldest_but_never_the_live_segment():
    segments = _segments(10, size=1000)
    gone = rb.to_delete(segments, keep_seconds=600, max_bytes=2500)
    assert [s.index for s in gone] == list(range(0, 8))
    assert segments[-1] not in gone


def test_concat_list_escapes_quotes_and_backslashes():
    text = rb.concat_list(["C:\\Clips\\it's.ts", "C:/b.ts"])
    assert text == "file 'C:/Clips/it'\\''s.ts'\nfile 'C:/b.ts'\n"


def test_save_command_copies_without_reencoding():
    cmd = rb.save_command("ffmpeg", "list.txt", "out.mp4")
    assert cmd[-1] == "out.mp4" and "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
    assert "+faststart" in cmd
    assert "+faststart" not in rb.save_command("ffmpeg", "list.txt", "out.mkv")
