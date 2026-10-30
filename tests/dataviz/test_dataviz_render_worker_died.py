# tests/dataviz/test_dataviz_render_worker_died.py
#
# תהליך ציור שנסגר באמצע רינדור (קרס, נהרג, או שה-venv הוחלף בזמן הריצה - כך זה נראה פעם אחת): multiprocessing.Pool
# החליף אותו בשקט, ו-imap חיכה לנצח לפריימים שהיו אצלו - הרינדור נתקע בלי הודעה. עכשיו הוא נעצר עם שגיאה ברורה,
# ו-ffmpeg ותהליכי הציור לא נשארים. הרינדור רץ בתהליך נפרד עם timeout, כדי שגם תקיעה תיכשל ולא תתקע את הריצה.
import json
import subprocess
import sys

import psutil
import pytest

from dataviz.episode import load_episode
from dataviz.plan import build_plan
from tests import PROJECT_ROOT
from tests.dataviz_helpers import write_episode
from tests.media_support import needs_ffmpeg

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 40},
         "timing": {"test_main_seconds": 1, "test_intro_seconds": 0.5, "test_outro_seconds": 0.5}}
TIMEOUT = 90   # תקין: כ-10 שניות (הפעלת התהליכים); הקוד הישן נתקע עד הסוף

# -c ולא קובץ: spawn לא מייבא מחדש את __main__ בתהליכי הציור. הם נהרגים כשהפריים הראשון מגיע - שאר הפריימים
# עדיין אצלם (חבילות של 2 פריימים, 20 בתכנית).
_PROBE = r"""
import json, os, sys, time
sys.path[:0] = [os.path.join(sys.argv[1], "src"), sys.argv[1]]
import psutil
from dataviz import render
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from utils.ffmpeg_locator import get_ffmpeg_exe

episode = load_episode(sys.argv[2])
killed = []


def workers():
    found = []
    for child in psutil.Process().children():
        try:
            if "spawn_main" in " ".join(child.cmdline()):
                found.append(child)
        except psutil.Error:
            pass
    return found


def progress(done, total):
    if not killed:
        for child in workers():
            try:
                child.kill()
                killed.append(child.pid)
            except psutil.Error:
                pass


started = time.monotonic()
error = None
try:
    render.render_video(episode, build_plan(episode, "test"), sys.argv[3], ffmpeg=get_ffmpeg_exe(), workers=2, chunksize=2, progress=progress)
except Exception as e:
    error = {"type": type(e).__name__, "message": str(e)}
left = [child.name() for child in psutil.Process().children() if child.is_running()]
print(json.dumps({"error": error, "killed": len(killed), "seconds": round(time.monotonic() - started, 1), "left": left}))
"""


def _kill_tree(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass


@needs_ffmpeg
def test_a_worker_that_dies_mid_render_stops_it_with_a_clear_error(tmp_path):
    folder = write_episode(tmp_path, overrides=SMALL)
    episode = load_episode(folder)
    assert len(build_plan(episode, "test")) >= 10   # יש עוד פריימים בדרך כשהתהליכים נהרגים
    proc = subprocess.Popen([sys.executable, "-c", _PROBE, PROJECT_ROOT, folder, str(tmp_path / "out.mp4")],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        out, err = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)   # הרינדור, ffmpeg ותהליכי הציור שלו בלבד
        proc.communicate()
        pytest.fail(f"הרינדור נתקע יותר מ-{TIMEOUT} שניות אחרי שתהליך ציור מת")
    assert proc.returncode == 0, err[-2000:]
    result = json.loads(out.strip().splitlines()[-1])
    assert result["killed"] >= 1
    assert result["error"] is not None and result["error"]["type"] == "WorkerDiedError", result
    assert "תהליך ציור נסגר באמצע הרינדור" in result["error"]["message"]
    assert result["left"] == [], result   # ffmpeg נהרג ותהליכי הציור נסגרו
