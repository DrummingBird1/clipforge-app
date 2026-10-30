# tests/studio/test_video_editor_hwaccel_e2e.py
#
# טסט end-to-end אמיתי ל---hwaccel (my_scripts/video/video_editor.py) - מריץ
# את הסקריפט האמיתי כתת-תהליך עם --hwaccel --codec hevc על GPU NVIDIA אמיתי,
# ומוודא בפועל (לא רק "לא קרס") שהתוצר נכון: רזולוציה מדויקת (לא 1088 - ראו
# ההערה ב-utils/video/video_editor.py's build_edit_filter_complex על ההדלפה של
# overlay_cuda שנמצאה תוך כדי פיתוח הפיצ'ר הזה), delogo באמת מוחק, ו-overlay
# חדש באמת מופיע. מדולג אוטומטית גם בלי ffmpeg/ffprobe וגם בלי GPU NVIDIA
# אמיתי בסביבה (nvidia-smi) - שני אלה חסרים ב-CI.
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
HORIZONTAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "horizontal")
VERTICAL_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "studio", "vertical")
OUTPUT_DIR = HORIZONTAL_OUTPUT_DIR  # ברירת מחדל - רוב הטסטים כאן לא מעבירים --vertical

INPUT_WIDTH, INPUT_HEIGHT = 1920, 1080
FAKE_WATERMARK_SIZE = 100
FAKE_WATERMARK_COLOR = "red"
PURE_RED_RGB = (255, 0, 0)


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


def _has_nvidia_gpu():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW_FLAGS,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()) or not _is_runnable(get_ffprobe_exe()) or not _has_nvidia_gpu(),
    reason="ffmpeg/ffprobe ו/או GPU NVIDIA אמיתי (nvidia-smi) לא זמינים בסביבה הזו - טסט ה--hwaccel מדולג",
)


def _make_synthetic_video_with_fake_watermark(path, duration=1):
    drawbox = f"drawbox=x=0:y=0:w={FAKE_WATERMARK_SIZE}:h={FAKE_WATERMARK_SIZE}:color={FAKE_WATERMARK_COLOR}:t=fill"
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={INPUT_WIDTH}x{INPUT_HEIGHT}:rate=10",
        "-vf", drawbox, "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _probe_dimensions(path):
    cmd = [
        get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    return result.stdout.strip()


def _pixel_rgb_at(path, x, y):
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


def test_hwaccel_removes_old_watermark_and_adds_new_one_at_exact_resolution(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_hwaccel_wm.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path))

    probe_x, probe_y = FAKE_WATERMARK_SIZE // 2, FAKE_WATERMARK_SIZE // 2
    source_pixel = _pixel_rgb_at(str(src_path), probe_x, probe_y)
    assert _color_distance(source_pixel, PURE_RED_RGB) < 10, f"המקור לא הכיל את ה-watermark המדומה: {source_pixel}"

    new_watermark_path = tmp_path / "new_logo.png"
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(new_watermark_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, result.stderr

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_hwaccel_wm_edited_horizontal.mp4")
    remove_video_editor_output(output_path)

    try:
        result = subprocess.run(
            [
                sys.executable, SCRIPT, "--input_dir", str(input_dir),
                "--remove_watermark_position", "top-left",
                "--remove_watermark_width_fraction", "0.2", "--remove_watermark_height_fraction", "0.2",
                "--watermark_path", str(new_watermark_path), "--watermark_position", "bottom-right", "--watermark_scale", "0.2",
                "--codec", "hevc", "--hwaccel",
            ],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"

        # לא 1920x1088 - ההדלפה שנמצאה ידנית תוך כדי פיתוח הפיצ'ר (overlay_cuda
        # מיישר גובה ל-16 בפועל, לא רק במטא-דאטה) חייבת להישאר מתוקנת.
        assert _probe_dimensions(output_path) == "1920x1080"

        old_area_pixel = _pixel_rgb_at(output_path, FAKE_WATERMARK_SIZE // 2, FAKE_WATERMARK_SIZE // 2)
        assert _color_distance(old_area_pixel, PURE_RED_RGB) > 40, (
            f"הפיקסל באזור המחיקה עדיין אדום טהור ({old_area_pixel}) - delogo לא באמת שינה שם משהו"
        )

        new_area_pixel = _pixel_rgb_at(output_path, 1700, 850)
        assert _color_distance(new_area_pixel, (0, 0, 255)) < 40, f"ה-watermark החדש לא נמצא במיקום הצפוי: {new_area_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_hwaccel_vertical_produces_correct_resolution(tmp_path):
    # אין crop_cuda ב-ffmpeg בכלל - השרשרת האנכית (VERTICAL_SCALE_CHAIN_CUDA)
    # עדיין צריכה hwdownload/hwupload סביב ה-crop; מוודא שזה לא שובר כלום.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_hwaccel_vertical.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path))

    output_path = os.path.join(VERTICAL_OUTPUT_DIR, "e2e_pytest_hwaccel_vertical_edited_vertical.mp4")
    remove_video_editor_output(output_path)

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--vertical", "--codec", "av1", "--hwaccel"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"
        assert _probe_dimensions(output_path) == "1080x1920"
    finally:
        remove_video_editor_output(output_path)


def test_target_size_mb_hevc_nvenc_multipass_lands_near_target(tmp_path):
    # hevc/av1 - "-multipass fullres" ב-קריאה בודדת (לא שתי קריאות נפרדות כמו
    # ה-h264 two-pass הקלאסי ב-test_video_editor_e2e.py) - מאומת פה מול GPU
    # אמיתי כי -multipass הוא דגל ספציפי ל-NVENC, לא נבדק ע"י הטסט ה-h264.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_hwaccel_2pass.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path), duration=5)

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_hwaccel_2pass_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    target_mb = 0.5

    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "hevc", "--target-size-mb", str(target_mb)],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert '"files_created": 1' in result.stdout
        assert "pass 1/2" not in result.stdout  # NVENC - קריאה בודדת, לא שתי קריאות נפרדות
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"

        actual_mb = os.path.getsize(output_path) / (1024 * 1024)
        assert actual_mb < target_mb * 1.5, f"הפלט ({actual_mb:.2f}MB) חורג משמעותית מהיעד ({target_mb}MB)"
    finally:
        remove_video_editor_output(output_path)


# --- פענוח מואץ-GPU בלי NVENC (item: --hwaccel-decode) ---

def test_hwaccel_decode_with_h264_cpu_codec_renders_successfully(tmp_path):
    # ההבדל המהותי מ---hwaccel: h264 (CPU) לא נתמך בכלל עם --hwaccel הרגיל
    # (דורש --codec hevc/av1), אבל *כן* אמור לעבוד עם --hwaccel-decode - זו
    # בדיוק הנקודה של הפיצ'ר. אם NVDEC לא הצליח לפענח בפועל (למשל דגלי
    # -hwaccel cuda שגויים), ffmpeg היה נכשל כאן על שגיאת אתחול hwaccel.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_hwaccel_decode_h264.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path), duration=2)

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_hwaccel_decode_h264_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--hwaccel-decode"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path), f"קובץ הפלט לא נוצר בפועל: {output_path}\n{result.stdout}"
        assert _probe_dimensions(output_path) == "1920x1080"
    finally:
        remove_video_editor_output(output_path)


def test_hwaccel_decode_with_watermark_overlay_still_composites_correctly(tmp_path):
    # מוודא שה-CPU overlay (לא overlay_cuda) עדיין עובד נכון *אחרי* ה-hwdownload -
    # לא רק "לא קרס", אלא שה-watermark החדש באמת מופיע בפיקסלים הנכונים.
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_hwaccel_decode_wm.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path), duration=2)

    watermark_path = tmp_path / "logo.png"
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64", "-frames:v", "1", str(watermark_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, result.stderr

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_hwaccel_decode_wm_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = subprocess.run(
            [
                sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "h264", "--hwaccel-decode",
                "--watermark_path", str(watermark_path), "--watermark_position", "bottom-right", "--watermark_scale", "0.2",
            ],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert os.path.exists(output_path)
        new_area_pixel = _pixel_rgb_at(output_path, 1700, 850)
        assert _color_distance(new_area_pixel, (0, 0, 255)) < 40, f"ה-watermark לא נמצא במיקום הצפוי: {new_area_pixel}"
    finally:
        remove_video_editor_output(output_path)


def test_hwaccel_decode_ignored_when_hwaccel_already_active(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    src_path = input_dir / "e2e_pytest_hwaccel_decode_ignored.mp4"
    _make_synthetic_video_with_fake_watermark(str(src_path), duration=1)

    output_path = os.path.join(OUTPUT_DIR, "e2e_pytest_hwaccel_decode_ignored_edited_horizontal.mp4")
    remove_video_editor_output(output_path)
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--codec", "hevc", "--hwaccel", "--hwaccel-decode"],
            cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "--hwaccel-decode מתעלם" in result.stdout
        assert os.path.exists(output_path)
    finally:
        remove_video_editor_output(output_path)


