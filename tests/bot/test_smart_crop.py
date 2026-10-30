# tests/bot/test_smart_crop.py
import os
import shutil
import subprocess

import numpy as np


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.media.smart_crop import (
    compute_horizontal_crop_offset,
    compute_horizontal_crop_offset_face,
    offset_to_crop_x_expr,
)
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS


def test_offset_to_crop_x_expr_zero_offset_is_centered():
    expr = offset_to_crop_x_expr(0.0, 1080)
    assert expr == "min(max((in_w-1080)/2+(0.000)*(in_w-1080)/2,0),in_w-1080)"


def test_offset_to_crop_x_expr_includes_signed_offset():
    assert "(-1.000)" in offset_to_crop_x_expr(-1.0, 1080)
    assert "(1.000)" in offset_to_crop_x_expr(1.0, 1080)


def test_compute_horizontal_crop_offset_returns_zero_for_missing_file():
    # cv2.VideoCapture על נתיב שלא קיים נכשל לפתוח - הפונקציה חוזרת ל-0.0
    # (התנהגות זהה לקרופ מרכזי) במקום לזרוק חריגה.
    assert compute_horizontal_crop_offset("Z:/does/not/exist.mp4") == 0.0


# --- קרופ חכם לפי זיהוי-פנים (item) - אותו חוזה-החזרה (offset ב--1.0..1.0,
# 0.0 על כל כשל) כמו הגרסה מבוססת-התזוזה. בדיקות ה-mock מדמות תוצאות
# FaceDetectorYN.detect במקום לדרוש וידאו מסונתז עם פנים אמיתיות (לא ניתן
# לייצר באמצעות ffmpeg lavfi כמו testsrc) - זהה בעיקרון לדפוס
# concentrated-right/left למעלה, רק שהקלט מדומה במקום נמדד מווידאו אמיתי. ---

def test_compute_horizontal_crop_offset_face_returns_zero_for_missing_file():
    assert compute_horizontal_crop_offset_face("Z:/does/not/exist.mp4") == 0.0


def test_compute_horizontal_crop_offset_face_returns_zero_when_model_missing(monkeypatch):
    import utils.media.smart_crop as smart_crop_module

    monkeypatch.setattr(smart_crop_module, "FACE_MODEL_PATH", "Z:/does/not/exist.onnx")
    assert compute_horizontal_crop_offset_face("Z:/does/not/exist.mp4") == 0.0


def test_compute_horizontal_crop_offset_face_faces_on_the_right_bias_offset_positive(monkeypatch):
    import utils.media.smart_crop as smart_crop_module

    class _FakeDetector:
        def detect(self, frame):
            # face row: [x, y, w, h, ... , confidence] - ריכוז ימני (x גבוה)
            return None, np.array([[280.0, 40.0, 40.0, 40.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.9]])

    class _FakeCapture:
        def __init__(self, path):
            self._read_count = 0

        def isOpened(self):
            return True

        def get(self, prop):
            return {0x00000007: 3, 0x00000003: 320, 0x00000004: 180}.get(prop, 0)

        def set(self, prop, value):
            pass

        def read(self):
            self._read_count += 1
            if self._read_count > 3:
                return False, None
            return True, np.zeros((180, 320, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(smart_crop_module, "FACE_MODEL_PATH", __file__)  # any existing file - isfile() check only
    monkeypatch.setattr(smart_crop_module.cv2, "VideoCapture", lambda path: _FakeCapture(path))
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_FRAME_COUNT", 0x00000007)
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_FRAME_WIDTH", 0x00000003)
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_FRAME_HEIGHT", 0x00000004)
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_POS_FRAMES", 0x00000001)
    monkeypatch.setattr(smart_crop_module.cv2, "FaceDetectorYN_create", lambda *a, **k: _FakeDetector())

    offset = compute_horizontal_crop_offset_face("fake.mp4")
    assert offset > 0.3, f"פנים מרוכזות בימין היו אמורות לתת offset חיובי משמעותי, קיבלנו {offset}"


def test_compute_horizontal_crop_offset_face_no_faces_detected_returns_zero(monkeypatch):
    import utils.media.smart_crop as smart_crop_module

    class _FakeDetector:
        def detect(self, frame):
            return None, None

    class _FakeCapture:
        def isOpened(self):
            return True

        def get(self, prop):
            return {0x00000007: 3, 0x00000003: 320, 0x00000004: 180}.get(prop, 0)

        def set(self, prop, value):
            pass

        def read(self):
            return True, np.zeros((180, 320, 3), dtype=np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(smart_crop_module, "FACE_MODEL_PATH", __file__)
    monkeypatch.setattr(smart_crop_module.cv2, "VideoCapture", lambda path: _FakeCapture())
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_FRAME_COUNT", 0x00000007)
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_FRAME_WIDTH", 0x00000003)
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_FRAME_HEIGHT", 0x00000004)
    monkeypatch.setattr(smart_crop_module.cv2, "CAP_PROP_POS_FRAMES", 0x00000001)
    monkeypatch.setattr(smart_crop_module.cv2, "FaceDetectorYN_create", lambda *a, **k: _FakeDetector())

    assert compute_horizontal_crop_offset_face("fake.mp4") == 0.0


def test_real_yunet_model_file_loads_and_returns_zero_on_faceless_video(tmp_path):
    # לא mock - טוען את מודל ה-ONNX האמיתי מ-assets/ ומריץ על וידאו מסונתז
    # (testsrc, בלי פנים) - מוודא שהמודל שצורף לריפו באמת תקין/נטען, לא רק
    # שהלוגיקה סביבו נכונה. testsrc לא מכיל פנים, אז אמור לחזור 0.0.
    video_path = str(tmp_path / "faceless.mp4")
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", "testsrc=size=320x180:rate=5:duration=1",
        "-pix_fmt", "yuv420p", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"

    assert compute_horizontal_crop_offset_face(video_path) == 0.0


# --- ניתוח תזוזה אמיתי (item: קרופ חכם) - וידאו מסונתז אמיתי דרך ffmpeg,
# לא mock ל-cv2, כדי לבדוק את השרשרת האמיתית (VideoCapture -> diff -> ממוצע
# משוקלל) ולא רק שהקוד "לא קרס". ---

def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()),
    reason="ffmpeg לא זמין בסביבה הזו - טסטי ה-E2E של smart_crop מדולגים (ראו utils/shared/ffmpeg_locator.py)",
)


def _make_half_static_half_moving_video(path, moving_on_right, width=160, height=180, duration=2):
    """חצי מהפריים (160x180) שחור-קבוע (0 תזוזה), החצי השני testsrc (תזוזה
    ממשית, תבנית-בדיקה נעה) - hstack מרכיב את שני המקורות לפריים אחד רחב,
    כך שהתזוזה שבפועל מתגלה מרוכזת בבירור בצד אחד בלבד."""
    static_src = f"color=black:size={width}x{height}:rate=10:duration={duration}"
    moving_src = f"testsrc=size={width}x{height}:rate=10:duration={duration}"
    first, second = (static_src, moving_src) if moving_on_right else (moving_src, static_src)
    cmd = [
        get_ffmpeg_exe(), "-y",
        "-f", "lavfi", "-i", first,
        "-f", "lavfi", "-i", second,
        "-filter_complex", "hstack=inputs=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def _make_fully_static_video(path, width=320, height=180, duration=1):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"color=gray:size={width}x{height}:rate=10:duration={duration}",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def test_motion_concentrated_on_the_right_biases_offset_positive(tmp_path):
    video_path = str(tmp_path / "motion_right.mp4")
    _make_half_static_half_moving_video(video_path, moving_on_right=True)

    offset = compute_horizontal_crop_offset(video_path)

    assert offset > 0.3, f"תזוזה מרוכזת בימין הייתה אמורה לתת offset חיובי משמעותי, קיבלנו {offset}"


def test_motion_concentrated_on_the_left_biases_offset_negative(tmp_path):
    video_path = str(tmp_path / "motion_left.mp4")
    _make_half_static_half_moving_video(video_path, moving_on_right=False)

    offset = compute_horizontal_crop_offset(video_path)

    # הסף חלש יותר מהמקבילה בימין (0.3) בכוונה - לתבנית testsrc עצמה יש
    # a-סימטריה קלה (התזוזה שבה לא מפוזרת אחידה בתוך התיבה שלה), נמדד בפועל
    # כ--0.18 כשהיא ממוקמת שמאלה מול ~0.82 כשהיא ממוקמת ימינה - הבדיקה הזו
    # מוודאת סימן וגודל-סף משמעותי, לא סימטריה מדויקת בין שני הצדדים.
    assert offset < -0.1, f"תזוזה מרוכזת בשמאל הייתה אמורה לתת offset שלילי משמעותי, קיבלנו {offset}"


def test_completely_static_video_returns_zero_offset(tmp_path):
    video_path = str(tmp_path / "static.mp4")
    _make_fully_static_video(video_path)

    assert compute_horizontal_crop_offset(video_path) == 0.0


def test_single_frame_video_returns_zero_offset(tmp_path):
    # total_frames <= 1 - אין שום דבר להשוות בין פריימים, אז אין תזוזה
    # שאפשר למדוד בכלל (לא רק "אין תזוזה", אין אפילו זוג פריימים לבדוק).
    video_path = str(tmp_path / "single_frame.png")
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=size=160x90", "-frames:v", "1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"

    assert compute_horizontal_crop_offset(video_path) == 0.0
