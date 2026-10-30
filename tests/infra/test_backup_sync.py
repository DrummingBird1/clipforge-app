# tests/infra/test_backup_sync.py
import time


from utils.shared.backup_sync import mirror_folder


def test_missing_source_dir_returns_error(tmp_path):
    copied, error = mirror_folder(str(tmp_path / "does_not_exist"), str(tmp_path / "dest"))
    assert copied == 0
    assert "לא קיימת" in error


def test_empty_dest_dir_string_returns_error(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    copied, error = mirror_folder(str(source), "")
    assert copied == 0
    assert error


def test_copies_new_files_and_creates_dest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.mp4").write_text("video a")
    (source / "b.mp4").write_text("video b")
    dest = tmp_path / "dest"

    copied, error = mirror_folder(str(source), str(dest))

    assert error is None
    assert copied == 2
    assert (dest / "a.mp4").read_text() == "video a"
    assert (dest / "b.mp4").read_text() == "video b"


def test_copies_nested_subdirectories(tmp_path):
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "sub" / "c.mp4").write_text("video c")
    dest = tmp_path / "dest"

    copied, error = mirror_folder(str(source), str(dest))

    assert error is None
    assert copied == 1
    assert (dest / "sub" / "c.mp4").exists()


def test_unchanged_files_are_not_recopied(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.mp4").write_text("video a")
    dest = tmp_path / "dest"

    first_copied, _ = mirror_folder(str(source), str(dest))
    assert first_copied == 1

    second_copied, _ = mirror_folder(str(source), str(dest))
    assert second_copied == 0, "קובץ שלא השתנה (גודל+זמן שינוי זהים) לא אמור להיות מועתק שוב"


def test_changed_file_is_recopied(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    src_file = source / "a.mp4"
    src_file.write_text("video a")
    dest = tmp_path / "dest"

    mirror_folder(str(source), str(dest))

    time.sleep(0.05)
    src_file.write_text("video a - updated with more content")
    copied, _ = mirror_folder(str(source), str(dest))

    assert copied == 1
    assert (dest / "a.mp4").read_text() == "video a - updated with more content"
