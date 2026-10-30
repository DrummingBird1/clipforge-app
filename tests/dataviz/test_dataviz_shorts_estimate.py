# tests/dataviz/test_dataviz_shorts_estimate.py
#
# 23.10.2026, המלצה 10: ב"מה להפיק" לא היה אומדן ל-Shorts (התיבה נשארה ריקה). עכשיו estimate() מחזיר גם shorts - כמה ייצאו
# (הימים הדרמטיים), האורך של כל אחד וזמן הרינדור בגודל לאורך, עם התקורה הקבועה לכל Short (כל אחד ריצה משלו).
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.shorts import build_shorts
from dataviz.web import preview
from tests.dataviz_helpers import write_episode

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


def test_the_estimate_has_shorts_with_their_count_length_and_render_time(tmp_path):
    folder = write_episode(tmp_path, overrides={**SMALL, "shorts": {"count": 2, "seconds": 8}})
    est = preview.estimate(folder, {}, workers=2)
    shorts = est["modes"]["shorts"]                                             # קודם: KeyError
    episode = load_episode(folder)
    expected = build_shorts(episode, build_plan(episode, "full"))
    assert shorts["count"] == len(expected) == 2
    assert shorts["frames"] == sum(len(s) for s in expected)
    assert shorts["seconds"] == round(shorts["frames"] / 2 / 10, 1)
    # כל Short ריצה משלו - התקורה פעמיים, ועוד עליית התהליך פעם אחת
    assert shorts["render_seconds"] >= 2 * preview.RUN_OVERHEAD_SECONDS + preview.START_SECONDS
    assert set(est["modes"]) == {"full", "test", "preview", "shorts"}
