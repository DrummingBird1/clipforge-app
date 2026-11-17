# tests/studio/test_mic_mix_e2e.py
#
# 16.11.2026 (2.0): ערוץ מיקרופון נפרד (--mic-track) - רינדור אמיתי וקטן של קובץ עם שני ערוצי שמע (משחק + מיקרופון, כמו
# מה שמסך ההקלטה ו-OBS מקליטים), עם ניקוי רעשים והנמכת המשחק. בודק שהפילטרים תקינים ב-ffmpeg האמיתי ושיוצא ערוץ שמע אחד.
import os
import subprocess
import sys

from tests import PROJECT_ROOT
from tests.conftest import remove_video_editor_output
from tests.media_support import needs_ffmpeg
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.workspace_dir import WORKSPACE_DIR

SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "video_editor.py")


@needs_ffmpeg
def test_a_mic_track_is_mixed_over_the_game_track(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    source = folder / "mic_mix_clip.mp4"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-f", "lavfi", "-i", "sine=f=220:d=2", "-f", "lavfi", "-i", "sine=f=880:d=2",
                    "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(source)], check=True, capture_output=True, timeout=120)
    output = os.path.join(WORKSPACE_DIR, "studio", "horizontal", "mic_mix_clip_edited_horizontal.mp4")
    try:
        result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(folder), "--codec", "h264", "--keep-audio",
                                 "--mic-track", "1", "--mic-gain", "1.5", "--mic-denoise", "--duck-game", "--force"],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
        assert os.path.isfile(output), result.stdout[-2000:]
        streams = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", output],
                                 capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
        assert streams.count("audio") == 1 and streams.count("video") == 1
    finally:
        remove_video_editor_output(output)


@needs_ffmpeg
def test_a_clip_without_the_mic_track_is_still_rendered(tmp_path):
    # 2.0.0: פרופיל עם ערוץ מיקרופון הפיל את הרינדור של כל קליפ עם ערוץ שמע אחד (השרשור האוטומטי מעתיק את הפרופיל לכל קליפ)
    folder = tmp_path / "in"
    folder.mkdir()
    source = folder / "one_track_clip.mp4"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-f", "lavfi", "-i", "sine=f=220:d=2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(source)], check=True, capture_output=True, timeout=120)
    output = os.path.join(WORKSPACE_DIR, "studio", "horizontal", "one_track_clip_edited_horizontal.mp4")
    try:
        result = subprocess.run([sys.executable, SCRIPT, "--input_dir", str(folder), "--codec", "h264", "--keep-audio",
                                 "--mic-track", "1", "--mic-denoise", "--duck-game", "--force"],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
        assert os.path.isfile(output) and "בלי ערבוב המיקרופון" in result.stdout, result.stdout[-2000:]
        streams = subprocess.run([get_ffprobe_exe(), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", output],
                                 capture_output=True, text=True, encoding="utf-8", check=True).stdout.split()
        assert streams.count("audio") == 1 and streams.count("video") == 1
    finally:
        remove_video_editor_output(output)
