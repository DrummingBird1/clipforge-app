# tests/dataviz/test_dataviz_plan.py
#
# src/dataviz/plan.py - תכנון הפריימים כפונקציה טהורה: כלל הקצב (אף עמודה לא מתקדמת
# ביותר מ-STEP מהציר בפריים), האטה מוחלקת סביב אירועים, דירוג וציר מוחלקים, כניסה
# ויציאה הדרגתיות, כרטיסי אירוע, "שיא חדש", אינטרו/אאוטרו ומצב test.
import copy

import numpy as np
import pytest

from dataviz.episode import load_episode
from dataviz.plan import build_plan, frame_days, pacing_weights
from tests.dataviz_helpers import write_episode

PACING = dict(step=0.005, base=0.7, axis_min=60.0, before=10, after=30, extra=2.0, window=5)


@pytest.fixture(scope="module")
def episode(tmp_path_factory):
    return load_episode(write_episode(tmp_path_factory.mktemp("dv_plan")))


@pytest.fixture(scope="module")
def plan(episode):
    return build_plan(episode, "full")


def _main(plan):
    return [f for f in plan if f["k"] == "main"]


def test_pacing_gives_each_day_enough_frames_for_the_step_rule():
    rng = np.random.default_rng(7)
    daily = rng.integers(0, 5, size=(400, 3)).astype(float)
    daily[200, 1] = 5000.0                                  # יום קפיצה
    cum = daily.cumsum(axis=0)
    w = pacing_weights(daily, cum, [], **PACING)

    axis = np.maximum(np.maximum.accumulate(cum.max(axis=1)), 60.0)
    need = daily.max(axis=1) / axis / 0.005
    assert (need <= w + 1e-9).all()
    # בין יום d ל-d+1 מונפשת התוספת של יום d+1 - גם לה מספיק פריימים
    assert (need[1:] <= w[:-1] + 1e-9).all()
    assert w.min() >= 0.7
    # ההחלקה פורשת את ההאטה גם על הימים שסביב הקפיצה, בלי לשטח את השיא עצמו
    raw_peak = 5000.0 / axis[200] / 0.005
    assert w[200] == pytest.approx(raw_peak)
    assert w[198] > 0.7 and w[202] > 0.7


def test_legacy_pacing_reproduces_the_first_video_and_can_overshoot_before_a_spike():
    daily = np.ones((100, 2))
    daily[50, 0] = 3000.0
    cum = daily.cumsum(axis=0)
    legacy = pacing_weights(daily, cum, [], **PACING, strict=False)
    strict = pacing_weights(daily, cum, [], **PACING)
    need = daily.max(axis=1) / np.maximum(np.maximum.accumulate(cum.max(axis=1)), 60.0) / 0.005
    # מעבר הממוצע מוריד את היום שלפני הקפיצה מתחת למה שהקפיצה דורשת - strict מתקן רק אותו
    assert legacy[49] < need[50] <= strict[49]
    assert np.array_equal(np.delete(legacy, 49), np.delete(strict, 49))


def test_event_slowdown_ramps_in_and_out():
    daily = np.ones((300, 2))
    cum = daily.cumsum(axis=0)
    w = pacing_weights(daily, cum, [150], **PACING)
    flat = pacing_weights(daily, cum, [], **PACING)

    assert w[150] == pytest.approx(flat[150] + 2.0)
    assert w[150 - 10 - 5] == pytest.approx(flat[150 - 10 - 5])       # מחוץ לטווח ההחלקה
    ramp = w[150 - 10 - 4:150 - 10 + 1]
    assert (np.diff(ramp) > 0).all()                                    # כניסה הדרגתית, לא מדרגה
    exit_ramp = w[150 + 30 - 2:150 + 30 + 3]
    assert (np.diff(exit_ramp) < 0).all()


def test_no_bar_advances_more_than_step_of_the_axis_per_frame(episode, plan):
    main = _main(plan)
    axis = np.maximum(np.maximum.accumulate(episode.cum.max(axis=1)), 60.0)
    worst = 0.0
    for prev, cur in zip(main, main[1:]):
        before = {e: v for e, v, _ in prev["bars"]}
        # בין יום d ל-d+1 מונפשת התוספת של יום d+1, ביחס לציר שכבר כולל אותה (כמו בסרטון המקורי;
        # חלון המקסימום של ההחלקה נותן ליום d לפחות את המשקל של d+1)
        day = min(int(np.floor(cur["x"])) + 1, episode.n_days - 1)
        for e, v, _ in cur["bars"]:
            if e in before:
                worst = max(worst, (v - before[e]) / axis[day])
    assert 0 < worst <= 0.005 * 1.02          # עיגול במעבר בין ימים


def test_frame_days_cover_the_whole_range_monotonically():
    w = np.array([1.0, 3.0, 1.0, 1.0])
    days = frame_days(w, 6)
    assert days[0] == 0 and days[-1] == pytest.approx(3.0)
    assert (np.diff(days) >= 0).all()
    # יום עם משקל 3 מקבל יותר פריימים מיום עם משקל 1
    assert np.sum((days >= 1) & (days < 2)) > np.sum((days >= 0) & (days < 1))


def test_ranking_and_axis_move_smoothly(plan):
    main = _main(plan)
    for prev, cur in zip(main, main[1:]):
        p_prev = {e: p for e, _, p in prev["bars"]}
        for e, _, p in cur["bars"]:
            if e in p_prev:
                assert abs(p - p_prev[e]) <= 0.07 * 4 + 1e-3        # smoothing x המרחק המקסימלי
        top = max((v for _, v, p in cur["bars"] if p < 3), default=0.0)
        assert cur["xmax"] >= top * 1.06 - 1e-9                      # המוביל תמיד בתוך הציר
        assert cur["xmax"] >= 60.0


def test_a_new_year_enters_from_below_and_a_dropped_one_fades_out(episode, plan):
    main = [f for f in _main(plan) if f["year"] == 2023]
    pos_2023 = {e: p for e, _, p in main[0]["bars"]}[2023]
    assert pos_2023 > 2.5          # נכנסת מתחתית (top_n=3), לא קופצת למקומה
    # 2022 (2 התרעות) יוצאת מהטופ-3 כש-2023 נכנסת: יורדת בהדרגה מתחת למקום האחרון ואז נעלמת
    positions = [next((p for e, _, p in f["bars"] if e == 2022), None) for f in main]
    shown = [p for p in positions if p is not None]
    assert len(shown) > 5 and shown == sorted(shown) and 2.0 < shown[-1] < 3.01
    assert positions[len(shown)] is None and all(p is None for p in positions[len(shown):])


def test_current_year_is_highlighted_and_always_in_view(plan):
    for f in _main(plan):
        assert f["current"] == f["year"]
        assert f["current"] in [e for e, _, p in f["bars"] if p < 3.5]


def test_event_cards_and_record_toast(plan):
    main = _main(plan)
    cards = [f["card"] for f in main if f["card"]]
    assert {c[0] for c in cards} == {"אירוע גדול", "אירוע קטן"}
    big = [c for c in cards if c[0] == "אירוע גדול"]
    assert big[0][1] == "07/10/2023" and big[0][2] == 0.0           # נכנס מאפס (fade in)
    assert max(c[2] for c in big) == 1.0
    texts = [f["toast"][0] for f in main if f["toast"]]
    assert list(dict.fromkeys(texts)) == ["שיא חדש: 2020", "שיא חדש: 2023"]


def test_intro_main_outro_lengths_and_outro_ranking(episode, plan):
    kinds = [f["k"] for f in plan]
    assert kinds[:360] == ["intro"] * 360 and kinds[-600:] == ["outro"] * 600
    outro = plan[-1]
    assert [e for e, _ in outro["top"]] == [2023, 2020, 2019]
    assert outro["total"] == pytest.approx(episode.cum[-1].sum())
    assert outro["xmax"] == pytest.approx(outro["bars"][0][1] * 1.13)


def test_test_mode_has_a_fixed_short_main_part(episode):
    plan = build_plan(episode, "test")
    assert len(plan) == 60 + 420 + 60
    assert _main(plan)[-1]["frac"] == pytest.approx(1.0)


def test_plan_is_a_pure_function_of_the_episode(episode, plan):
    before = copy.deepcopy(episode.cum)
    again = build_plan(episode, "full")
    assert again == plan
    assert np.array_equal(episode.cum, before)
