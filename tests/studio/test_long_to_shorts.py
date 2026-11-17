# tests/studio/test_long_to_shorts.py
#
# 16.11.2026 (2.0): "הקלטה ארוכה לכמה שורטס" - moment_finder (בחירת רגעים), shorts_layout (הפקודה), והסקריפט מקצה לקצה על
# הקלטה קטנה אמיתית: שני "פיצוצים" בשמע ומצלמה כ-stream וידאו שני -> שני שורטס אנכיים 1080x1920 עם Facecam.
import os
import subprocess
import sys

from tests import PROJECT_ROOT
from tests.media_support import needs_ffmpeg
from utils.media import moment_finder as mf
from utils.media import shorts_layout as sl
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe

SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "long_to_shorts.py")


def _levels(peaks, total_seconds, loud=-5.0, quiet=-40.0):
    levels = [quiet] * int(total_seconds * 10)
    for second, extra in peaks:
        levels[int(second * 10)] = loud + extra
    return levels


def test_the_strongest_moments_win_and_never_overlap():
    levels = _levels([(50, 0), (55, 5), (200, 2), (400, 1)], 600)
    moments = mf.find_moments(levels, -40.0, 600, count=3, length=30)
    assert [m.peak for m in moments] == [55.0, 200.0, 400.0]       # 50 נבלע בחלון של 55 (החזק יותר)
    assert all(m.end - m.start == 30 for m in moments)
    assert moments[0].start == 34.0 and moments[0].peak_in_clip == 21.0   # השיא ב-70% מהחלון


def test_windows_stay_inside_the_file_and_quiet_files_have_none():
    moments = mf.find_moments(_levels([(1, 0), (59, 0)], 60), -40.0, 60, count=5, length=30)
    assert [(m.start, m.end) for m in moments] == [(0.0, 30.0), (30.0, 60.0)]
    assert mf.find_moments([-40.0] * 100, -40.0, 10) == []


def test_layout_commands():
    center = sl.build_command("ffmpeg", "in.mkv", 10, 30, "out.mp4")
    graph = center[center.index("-filter_complex") + 1]
    assert "crop=1080:1920" in graph and "between" not in graph and center[center.index("-ss") + 1] == "10.00"
    face = sl.build_command("ffmpeg", "in.mkv", 0, 30, "out.mp4", layout="facecam", has_cam=True, punch_at=21, mic_track=1)
    graph = face[face.index("-filter_complex") + 1]
    assert "[0:v:1]" in graph and "vstack" in graph and "between(t\\,20.00\\,22.50)" in graph and "[0:a:1]" in graph
    no_cam = sl.build_command("ffmpeg", "in.mkv", 0, 30, "o.mp4", layout="facecam", has_cam=False)
    assert "vstack" not in no_cam[no_cam.index("-filter_complex") + 1]


@needs_ffmpeg
def test_a_long_recording_becomes_vertical_facecam_shorts(tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    source = folder / "session.mkv"
    loud = "volume='if(between(t,4,4.5)+between(t,14,14.5),8,0.02)':eval=frame"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=20",
                    "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=10:duration=20", "-f", "lavfi", "-i", "sine=f=300:d=20",
                    "-filter_complex", f"[2:a]{loud}[a]", "-map", "0:v", "-map", "1:v", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(source)], check=True, capture_output=True, timeout=120)
    (tmp_path / "exports").mkdir()   # תיקיית ייצוא שלא קיימת = workspace (export_dir)
    env = dict(os.environ, CLIPFORGE_EXPORT_DIR=str(tmp_path / "exports"))
    result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(folder), "--count", "2", "--length", "5", "--threshold", "10"],
                            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    out_dir = tmp_path / "exports" / "long_to_shorts" / "vertical"
    outputs = sorted(os.listdir(out_dir))
    assert outputs == ["session_short_1.mp4", "session_short_2.mp4"], result.stdout
    size = subprocess.run([get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(out_dir / outputs[0])], capture_output=True, text=True, encoding="utf-8").stdout.strip()
    assert size == "1080,1920"
