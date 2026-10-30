# tests/studio/test_contact_sheet.py
#
# compute_contact_sheet_columns - unit test טהור (לוגיקת grid). generate_contact_sheet
# עצמו נבדק ב-e2e אמיתי (ffmpeg lavfi + PIL אמיתי) - מדלג אוטומטית בלי ffmpeg זמין.
import os
import shutil
import subprocess


import pytest
from PIL import Image

from utils.video.contact_sheet import compute_contact_sheet_columns, generate_contact_sheet
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS


def test_compute_contact_sheet_columns_caps_at_max():
    assert compute_contact_sheet_columns(20, max_columns=5) == 5


def test_compute_contact_sheet_columns_smaller_batch_uses_exact_count():
    assert compute_contact_sheet_columns(3, max_columns=5) == 3


def test_compute_contact_sheet_columns_single_video():
    assert compute_contact_sheet_columns(1) == 1


def test_compute_contact_sheet_columns_rejects_non_positive():
    with pytest.raises(ValueError):
        compute_contact_sheet_columns(0)


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג",
)


def _make_synthetic_video(path, duration=2, color="red"):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"color=c={color}:size=320x240:duration={duration}:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def test_generate_contact_sheet_produces_correctly_sized_grid(tmp_path):
    video_paths = []
    for i, color in enumerate(["red", "green", "blue"]):
        path = str(tmp_path / f"clip_{i}.mp4")
        _make_synthetic_video(path, color=color)
        video_paths.append(path)

    output_path = str(tmp_path / "sheet.png")
    result_path = generate_contact_sheet(video_paths, output_path, ffmpeg_exe=get_ffmpeg_exe(), ffprobe_exe=get_ffprobe_exe())

    assert result_path == output_path
    assert os.path.exists(output_path)
    with Image.open(output_path) as sheet:
        # 3 סרטונים, MAX_COLUMNS=5 ברירת מחדל -> 3 עמודות, שורה אחת
        from utils.video.contact_sheet import CAPTION_HEIGHT, CELL_PADDING, THUMB_ASPECT_RATIO, THUMB_WIDTH
        expected_cell_w = THUMB_WIDTH + CELL_PADDING * 2
        expected_cell_h = int(THUMB_WIDTH * THUMB_ASPECT_RATIO) + CAPTION_HEIGHT + CELL_PADDING * 2
        assert sheet.size == (expected_cell_w * 3, expected_cell_h * 1)


def test_generate_contact_sheet_wraps_to_multiple_rows_beyond_max_columns(tmp_path):
    video_paths = []
    for i in range(7):  # יותר מ-MAX_COLUMNS (5) - אמור לגלוש לשורה שנייה
        path = str(tmp_path / f"clip_{i}.mp4")
        _make_synthetic_video(path, duration=1)
        video_paths.append(path)

    output_path = str(tmp_path / "sheet.png")
    generate_contact_sheet(video_paths, output_path, ffmpeg_exe=get_ffmpeg_exe(), ffprobe_exe=get_ffprobe_exe())

    with Image.open(output_path) as sheet:
        from utils.video.contact_sheet import CAPTION_HEIGHT, CELL_PADDING, THUMB_ASPECT_RATIO, THUMB_WIDTH
        expected_cell_w = THUMB_WIDTH + CELL_PADDING * 2
        expected_cell_h = int(THUMB_WIDTH * THUMB_ASPECT_RATIO) + CAPTION_HEIGHT + CELL_PADDING * 2
        assert sheet.size == (expected_cell_w * 5, expected_cell_h * 2)  # 7 סרטונים -> 5 עמודות, 2 שורות


def test_generate_contact_sheet_handles_unreadable_video_with_placeholder(tmp_path):
    good_path = str(tmp_path / "good.mp4")
    _make_synthetic_video(good_path, duration=1)
    broken_path = str(tmp_path / "broken.mp4")
    with open(broken_path, "wb") as f:
        f.write(b"not a real video file")

    output_path = str(tmp_path / "sheet.png")
    # לא אמור לזרוק חריגה - הקובץ השבור מקבל placeholder אפור במקום להפיל את כל התהליך
    generate_contact_sheet([good_path, broken_path], output_path, ffmpeg_exe=get_ffmpeg_exe(), ffprobe_exe=get_ffprobe_exe())
    assert os.path.exists(output_path)


def test_generate_contact_sheet_rejects_empty_video_list(tmp_path):
    with pytest.raises(ValueError):
        generate_contact_sheet([], str(tmp_path / "sheet.png"), ffmpeg_exe=get_ffmpeg_exe(), ffprobe_exe=get_ffprobe_exe())
