# tests/studio/test_encoder_fallback_e2e.py
#
# 17.11.2026 (2.0.1): מקודד של כרטיס שעבר את הבדיקה המוקדמת ונכשל ברינדור עצמו - העורך מנסה שוב במעבד, והקובץ נוצר.
# רינדור אמיתי וקטן: הבדיקה המוקדמת "מוצאת" AMD (מוחלפת בתהליך של הסקריפט), ו-ffmpeg האמיתי נכשל על hevc_amf בכל מחשב
# בלי כרטיס AMD. במחשב עם AMD הקידוד פשוט מצליח - גם זה תקין.
import os
import subprocess
import sys

from tests import PROJECT_ROOT
from tests.conftest import remove_video_editor_output
from tests.media_support import needs_ffmpeg
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.workspace_dir import WORKSPACE_DIR

SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "video_editor.py")

WRAPPER = """
import runpy, sys
sys.path.insert(0, sys.argv[1])
from utils.media import encoders
encoders.detect_backends = lambda *a, **k: {"nvenc": [], "amf": ["hevc"], "qsv": [], "cpu": ["hevc"]}
sys.argv = sys.argv[2:]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


@needs_ffmpeg
def test_a_render_that_fails_on_the_card_is_finished_on_the_cpu(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    source = folder / "fallback_clip.mp4"
    subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=10",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True, timeout=120)
    wrapper = tmp_path / "run_with_amd.py"
    wrapper.write_text(WRAPPER, encoding="utf-8")
    output = os.path.join(WORKSPACE_DIR, "studio", "horizontal", "fallback_clip_edited_horizontal.mp4")
    try:
        result = subprocess.run([sys.executable, str(wrapper), os.path.join(PROJECT_ROOT, "src"), SCRIPT, "--input_dir", str(folder),
                                 "--codec", "hevc", "--encoder-backend", "amf", "--force"],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
        assert os.path.isfile(output), result.stdout[-2000:]
        codec = subprocess.run([get_ffprobe_exe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                                "-of", "csv=p=0", output], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
        assert codec == "hevc"
        from utils.media import encoders
        if encoders._probe(get_ffmpeg_exe(), encoders.codec_args("hevc", "amf"), 0):
            return                                               # מחשב עם כרטיס AMD: הקידוד בכרטיס פשוט הצליח
        assert "מנסה שוב במעבד" in result.stdout, result.stdout[-2000:]   # בלי AMD: הכרטיס נכשל, והמעבד סיים את העבודה
    finally:
        remove_video_editor_output(output)
