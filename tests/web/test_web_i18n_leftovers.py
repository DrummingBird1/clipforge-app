# tests/web/test_web_i18n_leftovers.py
#
# 31.10.2026: עברית שנשארה בממשק האנגלי ונמצאה בסרטון ההדגמה (dev/make_demo_video.py בודק כל רגע): הזמן שנותר בריצה מגיע
# מהשרת (health_status.format_duration - "18שנ׳", "1ש 5ד"), ושמות הסגנונות המובנים (VIDEO_EDITOR_PRESETS) בבורר. אותה לוגיקת
# תרגום כמו בדף (test_web_i18n_dynamic._Translator).
import json
import re

from tests.web.test_web_i18n_dynamic import I18N_PATH, _Translator
from utils.shared.health_status import format_duration
from utils.video.video_editor_effort import VIDEO_EDITOR_PRESETS

HEBREW = re.compile("[֐-׿]")


def _translator():
    with open(I18N_PATH, encoding="utf-8") as f:
        return _Translator(json.load(f))


def test_the_time_left_in_a_run_is_in_english():
    t = _translator()
    assert t.translate(f"⏳ 30% · {format_duration(18)} · match_01.mp4 92%") == "⏳ 30% · 18s · match_01.mp4 92%"   # קודם: 18שנ׳
    assert t.translate(f"~{format_duration(65)}") == "~1m"
    assert t.translate(format_duration(3 * 3600 + 5 * 60)) == "3h 5m"
    assert t.translate(format_duration(90061)) == "1d 1h 1m"


def test_the_built_in_styles_have_english_names():
    t = _translator()
    for name in VIDEO_EDITOR_PRESETS:
        out = t.translate(name)
        assert out is not None and not HEBREW.search(out), name
