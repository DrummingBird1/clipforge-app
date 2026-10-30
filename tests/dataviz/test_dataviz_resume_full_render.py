# tests/dataviz/test_dataviz_resume_full_render.py
#
# 23.10.2026, המלצה 9: רינדור מלא שנקטע ממשיך מהמקטע האחרון שהסתיים. עד היום המקטעים במטמון היו רצפים של אותו סוג פריים -
# הקטע הראשי (כמעט כל הסרטון) היה מקטע אחד, ועצירה ב-80% התחילה אותו מחדש. עכשיו רצף ארוך נחתך לחתיכות של עד
# SEGMENT_SECONDS, וכל חתיכה שהסתיימה נשמרת.
import os
import subprocess

import pytest

from dataviz import render
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from tests.dataviz_helpers import write_episode
from tests.media_support import needs_ffmpeg

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


def test_long_runs_are_cut_into_pieces_in_order(tmp_path):
    plan = build_plan(load_episode(write_episode(tmp_path, overrides=SMALL)), "full")
    whole = render.plan_segments(plan)
    pieces = render.plan_segments(plan, 600)
    assert len(pieces) > len(whole)                                             # הקטע הראשי (3,253 פריימים) - כמה חתיכות
    assert all(0 < b - a <= 600 for a, b, _k in pieces)
    assert pieces[0][0] == 0 and pieces[-1][1] == len(plan) and all(pieces[i][1] == pieces[i + 1][0] for i in range(len(pieces) - 1))
    grouped = [k for i, (_a, _b, k) in enumerate(pieces) if i == 0 or pieces[i - 1][2] != k]
    assert grouped == [k for _a, _b, k in whole]                                 # אותם סוגים, באותו סדר


@needs_ffmpeg
def test_an_interrupted_full_render_resumes_from_the_last_finished_piece(tmp_path, monkeypatch):
    from utils.ffmpeg_locator import get_ffmpeg_exe
    monkeypatch.setattr(render, "SEGMENT_SECONDS", 2, raising=False)           # 20 פריימים לחתיכה (10 לשנייה)
    episode = load_episode(write_episode(tmp_path / "ep", overrides=SMALL))
    plan = build_plan(episode, "test")                                          # פתיח 10, ראשי 70 (20+20+20+10), סיום 10
    cache = str(tmp_path / "segments")
    real_encode, sent = render._encode, [0]

    def stopped_after_60_frames(frames, *args, **kwargs):
        def counted():
            for frame in frames:
                if sent[0] == 60:
                    raise RuntimeError("הרינדור נעצר")                          # כמו עצירה / דילוג / קריסה באמצע הקטע הראשי
                sent[0] += 1
                yield frame
        return real_encode(counted(), *args, **kwargs)
    monkeypatch.setattr(render, "_encode", stopped_after_60_frames)
    with pytest.raises(RuntimeError):
        render.render_video(episode, plan, str(tmp_path / "a.mp4"), ffmpeg=get_ffmpeg_exe(), workers=1, segment_cache=cache)
    monkeypatch.setattr(render, "_encode", real_encode)
    second = render.render_video(episode, plan, str(tmp_path / "a.mp4"), ffmpeg=get_ffmpeg_exe(), workers=1, segment_cache=cache)
    assert second["cached_frames"] == 50                                         # פתיח + שתי חתיכות ראשונות; קודם: 10 (רק הפתיח)
    assert second["frames"] == len(plan) and os.path.getsize(tmp_path / "a.mp4") > 0
    from utils.ffmpeg_locator import get_ffprobe_exe
    probe = subprocess.run([get_ffprobe_exe(), "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames",
                            "-of", "csv=p=0", str(tmp_path / "a.mp4")], capture_output=True, text=True, timeout=60)
    assert probe.stdout.strip() == str(len(plan))                               # החיבור של שש החתיכות - בלי פריים חסר או כפול
