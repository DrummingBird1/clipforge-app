# tests/studio/test_hebrew_path_ffmpeg_output.py
#
# 16.11.2026 (סריקת באגים ל-2.0): פלט של ffmpeg על קובץ עם שם בעברית. ffmpeg כותב UTF-8, ו-subprocess עם text=True בלי
# encoding פענח אותו ב-cp1255 (ה-locale של Windows בעברית): ב-א/ל/מ/ם/ן נפל UnicodeDecodeError, result.stderr חזר None,
# וזיהוי השקט של עורך-העל החזיר בשקט "אין שקט" - חיתוך השקט והסרת השקט באמצע לא עבדו על קבצים כאלה.
import os
import subprocess
import tempfile

from tests.media_support import needs_ffmpeg
from tests.video_editor_golden import _load
from utils.shared.ffmpeg_locator import get_ffmpeg_exe


@needs_ffmpeg
def test_silence_is_found_in_a_file_with_a_hebrew_name():
    with tempfile.TemporaryDirectory(prefix="ve_he_") as tmp:
        source = os.path.join(tmp, "אלמן ממש מלא.wav")
        tone = "sine=frequency=440:duration=1"
        subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", tone, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                        "-f", "lavfi", "-i", tone, "-filter_complex",
                        "[1]atrim=duration=2[s];[0][s][2]concat=n=3:v=0:a=1[a]", "-map", "[a]", source],
                       check=True, capture_output=True, timeout=60)
        module = _load(tmp, ["--remove-mid-silence", "--keep-audio"], 900)
        intervals = module.detect_all_silence_intervals(source, 4.0)
        assert intervals, "השקט באמצע לא זוהה"
        start, end = intervals[0]
        assert 0.9 <= start <= 1.3 and 2.7 <= end <= 3.1
