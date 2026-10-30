# tests/studio/test_video_editor_wave12_e2e.py
#
# גל 12 מול ffmpeg אמיתי: עריכת-קליפ בדריסות פר-קובץ (טווחים להסרה ושכבה רק
# לקובץ אחד) ותת-תיקיית פלט ליעד (--output-subdir). הפלט נכתב לתת-תיקייה ייחודית
# משלו תחת workspace/ ונמחק בסוף - אותו דפוס כמו שאר טסטי ה-e2e של הרנדרר.
import json
from tests import PROJECT_ROOT
import os
import secrets
import shutil
import subprocess
import sys


import pytest

from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = PROJECT_ROOT
from utils.shared.workspace_dir import WORKSPACE_DIR  # הזמני של הריצה (tests/conftest.py) - לא workspace/ של המשתמש
SCRIPT = os.path.join(BASE_DIR, "my_scripts", "video", "video_editor.py")


def _runnable(exe):
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


pytestmark = pytest.mark.skipif(not _runnable(get_ffmpeg_exe()) or not _runnable(get_ffprobe_exe()), reason="ffmpeg לא זמין")


def _make_clip(path, seconds):
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=10",
                    "-pix_fmt", "yuv420p", str(path)], capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


def _duration(path):
    out = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS).stdout.strip()
    return float(out)


def test_clip_overrides_and_output_subdir(tmp_path):
    token = secrets.token_hex(4)
    subdir = f"w12test_{token}"
    out_dir = os.path.join(WORKSPACE_DIR, "studio", "horizontal", subdir)
    a, b = f"w12a_{token}.mp4", f"w12b_{token}.mp4"
    _make_clip(tmp_path / a, 4)
    _make_clip(tmp_path / b, 3)
    overrides = tmp_path / "overrides.json"
    overrides.write_text(json.dumps({
        a: {"remove_ranges": [[0.0, 1.0], [3.0, 10000000.0]]},  # נשארות השניות 1-3
        b: {"layers": [{"type": "text", "text": "ONLY-B", "position": "custom", "x": 0.5, "y": 0.5}]},
    }), encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, "-u", SCRIPT, "--input_dir", str(tmp_path), "--codec", "h264", "--force",
             "--output-subdir", subdir, "--batch-overrides", str(overrides)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, creationflags=NO_WINDOW_FLAGS,
        )
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
        outputs = sorted(n for n in os.listdir(out_dir) if n.endswith(".mp4"))
        assert len(outputs) == 2, outputs
        out_a = os.path.join(out_dir, next(n for n in outputs if n.startswith("w12a_")))
        out_b = os.path.join(out_dir, next(n for n in outputs if n.startswith("w12b_")))
        assert abs(_duration(out_a) - 2.0) < 0.35
        assert abs(_duration(out_b) - 3.0) < 0.35
        assert "טווחים יוסרו" in result.stdout
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)  # safe: this test's own unique output folder (w12test_<random>) under workspace/
