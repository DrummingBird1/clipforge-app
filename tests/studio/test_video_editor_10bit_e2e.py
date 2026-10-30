# tests/studio/test_video_editor_10bit_e2e.py
#
# הרצה אמיתית מקצה לקצה (16.10): הקלטת משחק 10 ביט SDR (yuv420p10le, bt709) עם --hwaccel ופילטר CPU (צבע/טקסט/
# שכבות) נכשלה מיד - "hwdownload: Invalid output format nv12" - ולא רונדרה בכלל. עכשיו היא מפוענחת ב-CPU.
# צריך ffmpeg עם libx265 (ליצירת המקור) ו-NVENC (מחשב בלי כרטיס NVIDIA מדלג).
import json
import os
import subprocess
import sys


import pytest

from tests.media_support import needs_ffmpeg
from tests.video_editor_golden import SCRIPT
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS


def _ffmpeg(*args):
    return subprocess.run([get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True,
                          timeout=60, creationflags=NO_WINDOW_FLAGS)


@needs_ffmpeg
def test_ten_bit_sdr_source_renders_with_hwaccel_and_cpu_filters(tmp_path):
    if _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=256x144:d=0.2", "-pix_fmt", "yuv420p", "-c:v", "hevc_nvenc", "-f", "null", "-").returncode:
        pytest.skip("אין NVENC במחשב הזה")
    source, workspace = tmp_path / "in", tmp_path / "workspace"
    source.mkdir()
    made = _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=1:size=640x360:rate=10", "-pix_fmt", "yuv420p10le", "-c:v", "libx265",
                   "-x265-params", "log-level=error", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                   str(source / "tenbit.mp4"))
    if made.returncode:
        pytest.skip(f"ה-ffmpeg בלי libx265: {made.stderr[-200:]}")
    env = dict(os.environ, CLIPFORGE_WORKSPACE_DIR=str(workspace))
    result = subprocess.run([sys.executable, "-u", SCRIPT, "--input_dir", str(source), "--codec", "hevc", "--hwaccel", "--eq-contrast", "1.2", "--force"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, creationflags=NO_WINDOW_FLAGS, env=env)
    summary = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("RESULT: "))[len("RESULT: "):])
    assert summary["files_created"] == 1 and summary["errors"] == 0, result.stdout[-2500:]
    assert "יותר מ-8 ביט" in result.stdout
    output = next((workspace / "studio" / "horizontal").glob("tenbit*.mp4"))
    probe = subprocess.run([get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(output)],
                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert probe.stdout.strip() == "hevc"
