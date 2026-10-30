# tests/studio/test_video_editor_workspace_env.py
#
# הרצה אמיתית מקצה לקצה (16.10): עורך-העל כותב את התוצרים, הדוחות וה-run manifest לתיקייה שב-CLIPFORGE_WORKSPACE_DIR -
# אותה תיקייה ש-web_app.WORKSPACE_DIR קורא ממנה. קודם הסקריפט כתב תמיד ל-workspace/ של הפרויקט, ומהדפדפן (שרץ עם
# התיקייה החלופית) "פרטי הריצה" החזירו 404 והתוצרים לא נמצאו.
import os
import subprocess
import sys


from tests import video_editor_golden as golden
from tests.media_support import needs_ffmpeg
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS


def test_output_folders_follow_the_workspace_env(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    source = tmp_path / "in"
    source.mkdir()
    module = golden._load(str(source), ["--vertical"], 0)
    assert module.OUTPUT_DIR == os.path.join(str(workspace), "studio", "vertical")
    assert module.REPORTS_DIR == os.path.join(str(workspace), "reports")
    assert module.RUN_MANIFESTS_DIR == os.path.join(str(workspace), ".cache", "run_manifests")


def test_default_is_still_the_project_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("CLIPFORGE_WORKSPACE_DIR", raising=False)
    module = golden._load(str(tmp_path), [], 0)
    assert module.RUN_MANIFESTS_DIR == os.path.join(golden.BASE_DIR, "workspace", ".cache", "run_manifests")


@needs_ffmpeg
def test_a_real_render_lands_in_the_env_workspace(tmp_path):
    source, workspace = tmp_path / "in", tmp_path / "workspace"
    source.mkdir()
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10", "-pix_fmt", "yuv420p",
                    str(source / "envclip.mp4")], capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    env = dict(os.environ, CLIPFORGE_WORKSPACE_DIR=str(workspace))
    result = subprocess.run([sys.executable, "-u", golden.SCRIPT, "--input_dir", str(source), "--codec", "h264", "--force"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                            creationflags=NO_WINDOW_FLAGS, env=env)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    outputs = [n for n in os.listdir(workspace / "studio" / "horizontal") if n.endswith(".mp4")]
    assert len(outputs) == 1 and outputs[0].startswith("envclip")
    assert len(list((workspace / ".cache" / "run_manifests").glob("*.json"))) == 1
    assert not os.path.exists(os.path.join(golden.BASE_DIR, "workspace", "studio", "horizontal", outputs[0]))
