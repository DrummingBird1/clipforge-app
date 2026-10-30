# tests/dataviz/test_dataviz_fix_skip_keeps_video.py
#
# 23.10.2026, סריקת הבאגים - ק7: דילוג על פרק שמתרנדר במצב מלא מחק את הסרטון הקודם, השלם. במצב מלא (עם מטמון המקטעים)
# render.py כותב את הקובץ רק בחיבור המקטעים שבסוף - בזמן הדילוג מה שיש שם הוא הרינדור הקודם, וה-QueueSkip מחק אותו.
# עכשיו נמחק רק מה שהריצה הזו כתבה (לפי זמן השינוי); סרטון חלקי שהיא התחילה לכתוב (מצב בדיקה) - נמחק כמו קודם.
import argparse
import contextlib
import importlib.util
import os
import time

import pytest

from dataviz.episode import load_episode
from tests import PROJECT_ROOT
from tests.dataviz_helpers import write_episode

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


@pytest.fixture(scope="module")
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_k7", os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(maker, monkeypatch, tmp_path, mode, writes_first):
    import dataviz
    from utils import render_lock
    folder = write_episode(tmp_path, overrides=SMALL, name="ep")
    out_base = str(tmp_path / "out")
    _folder, target = maker.output_paths(load_episode(folder).config, mode, out_base)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(b"PREVIOUS COMPLETE RENDER")
    hour_ago = time.time() - 3600
    os.utime(target, (hour_ago, hour_ago))

    def skipped(episode, plan, out_path, **kwargs):
        if writes_first:                                                        # ffmpeg כבר התחיל לכתוב לקובץ
            with open(out_path, "wb") as f:
                f.write(b"partial")
        raise maker.QueueSkip()
    monkeypatch.setattr(dataviz, "render_video", skipped)
    monkeypatch.setattr(render_lock, "render_lock_if_needed", lambda **k: contextlib.nullcontext())
    args = argparse.Namespace(chart=None, workers=1, target="", output_dir=out_base, captions=False, publish=False, no_publish=True)
    with pytest.raises(maker.QueueSkip):
        maker.render_episode(folder, mode, args, lambda d, t: None, {"files_created": 0, "errors": 0})
    return target


def test_skipping_a_full_render_keeps_the_previous_video(maker, monkeypatch, tmp_path):
    target = _run(maker, monkeypatch, tmp_path, "full", writes_first=False)
    with open(target, "rb") as f:
        assert f.read() == b"PREVIOUS COMPLETE RENDER"                         # קודם: נמחק


def test_a_partial_file_this_run_wrote_is_still_removed(maker, monkeypatch, tmp_path):
    target = _run(maker, monkeypatch, tmp_path, "test", writes_first=True)
    assert not os.path.exists(target)                                           # הסרטון החלקי של הריצה הזו - נמחק
