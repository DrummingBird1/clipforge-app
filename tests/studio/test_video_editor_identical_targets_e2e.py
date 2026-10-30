# tests/studio/test_video_editor_identical_targets_e2e.py
#
# הרצה אמיתית מקצה לקצה (16.10): Shorts, TikTok ו-Reels הם ריצות נפרדות עם אותן הגדרות בדיוק (רק תת-תיקיית הפלט
# שונה), וכל אחת רינדרה מחדש את אותו סרטון. עכשיו יעד עם אותן הגדרות מקושר לפלט של היעד הקודם (hard link) בלי רינדור,
# ויעד עם הגדרה אחרת - או קובץ לוגו שהשתנה - מרונדר כרגיל.
import os
import subprocess
import sys


from PIL import Image

from tests.media_support import needs_ffmpeg
from tests.video_editor_golden import SCRIPT
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS


def _run(source, workspace, subdir, *extra):
    env = dict(os.environ, CLIPFORGE_WORKSPACE_DIR=str(workspace))
    result = subprocess.run([sys.executable, "-u", SCRIPT, "--input_dir", str(source), "--codec", "h264", "--vertical", "--thumbnail",
                             "--output-subdir", subdir, *extra], capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=180, creationflags=NO_WINDOW_FLAGS, env=env)
    assert result.returncode == 0 and "[APPROVED]" in result.stdout, result.stdout[-2000:]
    return result.stdout, workspace / "studio" / "vertical" / subdir / "clip_edited_vertical.mp4"


@needs_ffmpeg
def test_a_target_with_the_same_settings_is_linked_not_rendered(tmp_path):
    source, workspace = tmp_path / "in", tmp_path / "workspace"
    source.mkdir()
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(source / "clip.mp4")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (32, 16), (255, 0, 0, 255)).save(logo)
    _, shorts = _run(source, workspace, "shorts", "--watermark_path", str(logo))
    out, tiktok = _run(source, workspace, "tiktok", "--watermark_path", str(logo), "--force")   # --force לא משנה את הפלט
    assert "מקושר מ-shorts/" in out and os.path.samefile(shorts, tiktok)
    assert os.path.isfile(str(tiktok).replace(".mp4", "_thumb.jpg"))
    out, reels = _run(source, workspace, "reels", "--watermark_path", str(logo), "--eq-contrast", "1.3")
    assert "מקושר" not in out and not os.path.samefile(shorts, reels)                        # הגדרה אחרת - רינדור
    Image.new("RGBA", (32, 16), (0, 0, 255, 255)).save(logo)
    os.utime(logo, (os.stat(logo).st_atime, os.stat(logo).st_mtime + 5))
    out, other = _run(source, workspace, "other", "--watermark_path", str(logo))
    assert "מקושר" not in out and not os.path.samefile(shorts, other)                        # הלוגו השתנה - רינדור
