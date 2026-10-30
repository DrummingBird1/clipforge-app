# tests/dataviz/test_dataviz_render_partial_file.py
#
# 23.10.2026 (תיקיית הייצוא, גם בכונן רשת): render_video כתב ישר לשם הסופי של הסרטון - ffmpeg (‏-y) קיצר אותו כבר בהתחלה, אז
# רינדור שנקטע (דילוג בתור, כשל, ניתוק) השאיר בשם של הסרטון קובץ חלקי במקום הסרטון הקודם. עכשיו הוא נכתב לקובץ מוסתר באותה
# תיקייה ומקבל את השם רק בסוף, כמו בסטודיו.
import os

import pytest

from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.render import render_video
from tests.dataviz_helpers import write_episode
from utils.ffmpeg_locator import get_ffmpeg_exe

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


class Stop(BaseException):   # כמו QueueSkip של התור
    pass


def _setup(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides=SMALL, name="ep"))
    plan = build_plan(episode, "test")
    assert len(plan) >= 20
    out = tmp_path / "out" / "ep_test.mp4"
    out.parent.mkdir()
    out.write_bytes(b"PREVIOUS RENDER")
    return episode, plan, out


def test_an_interrupted_render_keeps_the_previous_video_and_leaves_no_partial_file(tmp_path):
    episode, plan, out = _setup(tmp_path)
    during = []

    def progress(done, total):
        if done == total // 2:
            during.append(out.read_bytes())
            raise Stop()
    with pytest.raises(Stop):
        render_video(episode, plan, str(out), ffmpeg=get_ffmpeg_exe(), workers=1, progress=progress)
    assert during == [b"PREVIOUS RENDER"]                                       # קודם: ffmpeg כבר קיצר אותו
    assert out.read_bytes() == b"PREVIOUS RENDER"
    assert os.listdir(out.parent) == ["ep_test.mp4"]                            # בלי קובץ חלקי


def test_a_finished_render_takes_the_name_and_leaves_nothing_else(tmp_path):
    episode, plan, out = _setup(tmp_path)
    result = render_video(episode, plan, str(out), ffmpeg=get_ffmpeg_exe(), workers=1)
    assert result["path"] == str(out)
    assert out.read_bytes()[4:8] == b"ftyp"                                     # סרטון אמיתי, לא הקודם
    assert os.listdir(out.parent) == ["ep_test.mp4"]
