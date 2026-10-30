# tests/bot/test_duplicate_scene_detector_e2e.py
#
# טסט end-to-end אמיתי: מריץ my_scripts/video/duplicate_scene_detector.py כתת-תהליך
# אמיתי על שני קובצי וידאו זהים (נוצרו עם ffmpeg lavfi, בלי נכס בינארי שמור בריפו)
# תחת שני שמות שונים - מוודא ש-cross-file duplicate detection (item) מזהה אותם
# כ"כנראה אותו קליפ" בפועל, לא רק שהלוגיקה הטהורה נכונה בבידוד.
import json
from tests import PROJECT_ROOT
import os
import shutil
import subprocess
import sys


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = PROJECT_ROOT
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "duplicate_scene_detector.py")


def _is_runnable(exe_path):
    return (os.path.isabs(exe_path) and os.path.exists(exe_path)) or bool(shutil.which(exe_path))


pytestmark = pytest.mark.skipif(
    not _is_runnable(get_ffmpeg_exe()),
    reason="ffmpeg לא זמין בסביבה הזו - טסט ה-E2E מדולג",
)


def _make_synthetic_video(path, duration=12, pattern="testsrc"):
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", f"{pattern}=duration={duration}:size=320x240:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, f"יצירת קובץ הבדיקה נכשלה: {result.stderr}"


def test_cross_file_duplicate_detection_flags_two_copies_of_the_same_clip(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    # אותו תוכן בדיוק, שני שמות שונים - מדמה "אותו highlight יוצא/יובא פעמיים בטעות".
    _make_synthetic_video(str(input_dir / "highlight_original.mp4"))
    _make_synthetic_video(str(input_dir / "highlight_copy.mp4"))

    output_report = tmp_path / "report.json"

    result = subprocess.run(
        [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--output", str(output_report)],
        cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULT:" in result.stdout
    assert '"cross_file_duplicates_found": 1' in result.stdout
    assert "highlight_original.mp4" in result.stdout and "highlight_copy.mp4" in result.stdout

    assert output_report.exists()
    report = json.loads(output_report.read_text(encoding="utf-8"))
    assert "_cross_file_duplicates" in report
    assert len(report["_cross_file_duplicates"]) == 1
    pair = report["_cross_file_duplicates"][0]
    assert {pair["file_a"], pair["file_b"]} == {"highlight_original.mp4", "highlight_copy.mp4"}
    # "_hashes" הפנימי לא אמור לדלוף לדוח הסופי שנכתב לדיסק (ראו main() - .pop אחרי החישוב)
    assert "_hashes" not in report["highlight_original.mp4"]


def test_cross_file_duplicate_detection_does_not_flag_different_clips(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _make_synthetic_video(str(input_dir / "clip_a.mp4"), pattern="testsrc")
    _make_synthetic_video(str(input_dir / "clip_b.mp4"), pattern="testsrc2")  # דפוס חזותי שונה לגמרי

    output_report = tmp_path / "report.json"

    result = subprocess.run(
        [sys.executable, SCRIPT, "--input_dir", str(input_dir), "--output", str(output_report)],
        cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", timeout=120, creationflags=NO_WINDOW_FLAGS,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert '"cross_file_duplicates_found": 0' in result.stdout
