# tests/bot/test_capture_watcher.py
#
# בודק את utils/media/capture_watcher.py - הלוגיקה הטהורה (זיהוי קבצים/יציבות/
# כבר-הועתק) שמאחורי my_scripts/stream/capture_folder_watcher.py (item:
# אינטגרציה עם תוכנת לכידה נוספת - Streamlabs/ShadowPlay/כל כלי אחר).


from utils.media.capture_watcher import already_copied, list_video_files, update_size_history


# --- list_video_files ---

def test_list_video_files_finds_recognized_extensions_only(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"x")
    (tmp_path / "clip.mkv").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"x")

    result = list_video_files(str(tmp_path))

    assert set(result.keys()) == {"clip.mp4", "clip.mkv"}


def test_stream_and_console_formats_are_picked_up_too(tmp_path):
    """16.11.2026: .ts (OBS/Steam/לכידה), .flv ו-.m4v - המאזין דילג עליהם, וגם עורך-העל והשרשור האוטומטי."""
    from entrypoints import web_app
    from utils.video import editor_projects
    for name in ("a.ts", "b.flv", "c.M4V"):
        (tmp_path / name).write_bytes(b"x")
    assert set(list_video_files(str(tmp_path))) == {"a.ts", "b.flv", "c.M4V"}
    assert ".ts" in web_app.EDITOR_VIDEO_EXTENSIONS and ".m4v" in editor_projects._VIDEO_EXTENSIONS


def test_list_video_files_ignores_subdirectories(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.mp4").write_bytes(b"x")

    assert list_video_files(str(tmp_path)) == {}


def test_list_video_files_returns_empty_dict_for_missing_folder():
    assert list_video_files("Z:\\does_not_exist_at_all") == {}


def test_list_video_files_is_case_insensitive_on_extension(tmp_path):
    (tmp_path / "CLIP.MP4").write_bytes(b"x")
    assert "CLIP.MP4" in list_video_files(str(tmp_path))


# --- already_copied ---

def test_already_copied_true_when_file_exists_in_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "clip.mp4").write_bytes(b"x")

    assert already_copied("clip.mp4", str(target)) is True


def test_already_copied_false_when_not_present(tmp_path):
    target = tmp_path / "target"
    target.mkdir()

    assert already_copied("clip.mp4", str(target)) is False


# --- update_size_history ---

def test_update_size_history_not_stable_after_one_measurement():
    history = {}
    assert update_size_history(history, "clip.mp4", 100) is False


def test_update_size_history_stable_after_two_identical_measurements():
    history = {}
    update_size_history(history, "clip.mp4", 100)
    assert update_size_history(history, "clip.mp4", 100) is True


def test_update_size_history_not_stable_when_size_changed():
    history = {}
    update_size_history(history, "clip.mp4", 100)
    assert update_size_history(history, "clip.mp4", 150) is False


def test_update_size_history_caps_at_stable_checks_required():
    history = {}
    update_size_history(history, "clip.mp4", 100, stable_checks_required=3)
    update_size_history(history, "clip.mp4", 100, stable_checks_required=3)
    assert len(history["clip.mp4"]) == 2
    assert update_size_history(history, "clip.mp4", 100, stable_checks_required=3) is True
    assert len(history["clip.mp4"]) == 3
    # מדידה רביעית - הראשונה נגרעת, עדיין 3 בהיסטוריה
    update_size_history(history, "clip.mp4", 100, stable_checks_required=3)
    assert len(history["clip.mp4"]) == 3


def test_update_size_history_tracks_multiple_files_independently():
    history = {}
    update_size_history(history, "a.mp4", 100)
    update_size_history(history, "b.mp4", 200)
    assert update_size_history(history, "a.mp4", 100) is True
    assert update_size_history(history, "b.mp4", 999) is False
