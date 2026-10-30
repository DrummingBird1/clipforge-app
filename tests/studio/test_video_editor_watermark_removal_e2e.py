# tests/studio/test_video_editor_watermark_removal_e2e.py
#
# טסט end-to-end אמיתי ל-features החדשים במחיקת/החלפת watermark ב-
# my_scripts/video/video_editor.py (--remove_watermark_position). לא מסתפק
# ב"הפקודה לא קרסה" - בונה קלט עם ריבוע אדום מלא (drawbox) במיקום ידוע (ffmpeg
# lavfi, בלי נכס בינארי שמור בריפו), מריץ את הסקריפט כתת-תהליך אמיתי, ואז
# בודק בפועל עם ffmpeg שהפיקסלים במרכז האזור הזה כבר לא אדום טהור - כלומר
# ש-delogo באמת שינה את התוכן שם, לא רק שהריצה "הצליחה" טכנית.
import os
from tests import PROJECT_ROOT
import shutil
import subprocess
import sys


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

from tests.conftest import remove_video_editor_output

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")

# הקלט נוצר בדיוק ברזולוציית הפלט הקבועה (resolve_output_dimensions(False),
# ראו utils/video/video_editor.py) בכוונה: HORIZONTAL_SCALE_CHAIN הוא scale+pad עם
# force_original_aspect_ratio=decrease - על קלט בגודל אחר (למשל 320x240) הוא
# משנה גודל/מוסיף פסי pad, מה שהופך את מיקום הפיקסלים בפלט לפונקציה לא-טריוויאלית
# של הקלט (וכמעט גרם לטסט הזה "לעבור" מהסיבה הלא נכונה - בדק פס pad שחור
# ולא בכלל את אזור ה-delogo). קלט באותה רזולוציה בדיוק = scale/pad הם no-op,
# ואז קואורדינטת קלט = קואורדינטת פלט, בלי שום חישוב מיפוי נוסף.
INPUT_WIDTH, INPUT_HEIGHT = 1920, 1080
# ריבוע "watermark" מדומה - אדום טהור, פינה שמאלית-עליונה, קטן מספיק שאזור
# המחיקה (20% מהרוחב/גובה כברירת מחדל) יכסה אותו לגמרי.
FAKE_WATERMARK_SIZE = 100
FAKE_WATERMARK_COLOR = "red"
PURE_RED_RGB = (255, 0, 0)


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()),
    reason="ffmpeg/ffprobe לא זמינים בסביבה הזו - טסט ה-E2E מדולג (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_synthetic_video_with_fake_watermark(path, duration=1):
    """יוצר קובץ mp4 זעיר-אך-אמיתי: testsrc עם ריבוע אדום מלא ("watermark" מדומה)
    צרוב בפינה שמאלית-עליונה במיקום ידוע - בלי צורך בקובץ מדיה שמור בריפו."""
    drawbox = f"drawbox=x=0:y=0:w={FAKE_WATERMARK_SIZE}:h={FAKE_WATERMARK_SIZE}:color={FAKE_WATERMARK_COLOR}:t=fill"
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={INPUT_WIDTH}x{INPUT_HEIGHT}:rate=10",
        "-vf", drawbox, "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _pixel_rgb_at(path, x, y):
    """קורא את צבע ה-RGB של פיקסל בודד (בקירוב - פינת בלוק 2x2, לא 1x1 שנכשל
    ב-yuv420p שדורש מידות זוגיות) מהפריים הראשון - דרך rawvideo, בלי תלות
    בספריות תמונה חיצוניות (PIL כבר תלות של הפרויקט, אבל לא נחוץ כאן)."""
    cmd = [
        get_ffmpeg_exe(), "-v", "error", "-i", path,
        "-vf", f"crop=2:2:{x}:{y}", "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert len(result.stdout) == 12, f"ציפינו לבלוק 2x2 (12 בתים), קיבלנו {len(result.stdout)}"
    return tuple(result.stdout[:3])


def _color_distance(rgb_a, rgb_b):
    return sum(abs(a - b) for a, b in zip(rgb_a, rgb_b))


def test_remove_watermark_position_actually_alters_the_pixels_there(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_probe_wm_removal.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path))

    # ודאות שהמקור באמת מכיל את ה-"watermark" האדום המדומה במרכז האזור, לפני
    # שמריצים את הסקריפט - אחרת הטסט לא בודק מה שהוא חושב שהוא בודק.
    probe_x, probe_y = FAKE_WATERMARK_SIZE // 2, FAKE_WATERMARK_SIZE // 2
    source_pixel = _pixel_rgb_at(str(src_path), probe_x, probe_y)
    assert _color_distance(source_pixel, PURE_RED_RGB) < 10, f"המקור לא הכיל את ה-watermark המדומה במיקום הצפוי: {source_pixel}"

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_probe_wm_removal_edited_horizontal.mp4")
    remove_video_editor_output(output_path)

    try:
        result = subprocess.run(
            [
                sys.executable, SCRIPT, "--input_dir", str(input_dir),
                "--remove_watermark_position", "top-left",
                "--remove_watermark_width_fraction", "0.2", "--remove_watermark_height_fraction", "0.2",
                "--codec", "h264",
            ],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"

        output_pixel = _pixel_rgb_at(output_path, probe_x, probe_y)
        assert _color_distance(output_pixel, PURE_RED_RGB) > 40, (
            f"הפיקסל באזור המחיקה עדיין אדום טהור ({output_pixel}) - delogo לא באמת שינה שם משהו"
        )
    finally:
        remove_video_editor_output(output_path)


def test_remove_watermark_position_combined_with_new_watermark(tmp_path):
    # מוחקים את ה-"watermark" האדום המדומה, ובאותה ריצה מוסיפים watermark חדש
    # (תמונה שקופה-למחצה) בפינה הנגדית - מוודא ששני הפילטרים (delogo + overlay)
    # עובדים יחד בפועל, לא רק בבידוד זה מזה.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_probe_wm_replace.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path))

    new_watermark_path = tmp_path / "new_logo.png"
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64",
        "-frames:v", "1", str(new_watermark_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, result.stderr

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_probe_wm_replace_edited_horizontal.mp4")
    remove_video_editor_output(output_path)

    try:
        result = subprocess.run(
            [
                sys.executable, SCRIPT, "--input_dir", str(input_dir),
                "--remove_watermark_position", "top-left",
                "--watermark_path", str(new_watermark_path), "--watermark_position", "bottom-right", "--watermark_scale", "0.2",
                "--codec", "h264",
            ],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"

        # האדום הישן נמחק
        old_area_pixel = _pixel_rgb_at(output_path, FAKE_WATERMARK_SIZE // 2, FAKE_WATERMARK_SIZE // 2)
        assert _color_distance(old_area_pixel, PURE_RED_RGB) > 40

        # והכחול החדש מופיע בפינה הנגדית - בתוך אזור ה-watermark החדש (מרכזו בקירוב,
        # לפי compute_watermark_geometry(1920, 1080, 64, 64, "bottom-right", scale_fraction=0.2))
        new_area_pixel = _pixel_rgb_at(output_path, 1700, 850)
        assert _color_distance(new_area_pixel, (0, 0, 255)) < 40, f"ה-watermark החדש לא נמצא במיקום הצפוי: {new_area_pixel}"
    finally:
        remove_video_editor_output(output_path)
