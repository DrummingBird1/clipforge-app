# tests/dataviz/test_dataviz_render.py
#
# src/dataviz/render.py + charts/: ציור פריימים בודדים (stills) של פרק קטן - בלי רינדור
# וידאו מלא - פקודת ffmpeg עם המוזיקה (חיתוך, כניסה ודעיכה), בחירת פריימי הסטילס, וזה
# שפריים מצויר זהה בלי קשר למה שצויר לפניו באותו תהליך.
import os

import pytest
from PIL import Image

from dataviz.charts import CHART_MODULES, chart_class, make_chart
from dataviz.charts.timeseries import spread_labels
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.render import audio_filter, chart_context, ffmpeg_command, render_stills, still_indices
from tests.dataviz_helpers import write_episode


@pytest.fixture(scope="module")
def episode(tmp_path_factory):
    return load_episode(write_episode(tmp_path_factory.mktemp("dv_render")))


@pytest.fixture(scope="module")
def plan(episode):
    return build_plan(episode, "test")


def _first(plan, pred):
    return next(i for i, f in enumerate(plan) if pred(f))


def test_still_indices_cover_intro_main_and_the_last_frame(plan):
    picks = still_indices(plan)
    assert picks[0] == 30 and picks[-1] == len(plan) - 1
    assert len(picks) == 10 and picks == sorted(set(picks))
    assert plan[picks[0]]["k"] == "intro" and plan[picks[-1]]["k"] == "outro"


@pytest.mark.parametrize("chart", [c for c in CHART_MODULES if c != "map_race"])   # מפה צריכה GeoJSON - test_dataviz_wave42.py
def test_every_chart_type_draws_stills_from_the_same_plan(episode, plan, tmp_path, chart):
    picks = [still_indices(plan)[0], _first(plan, lambda f: f.get("card")), len(plan) - 1]
    paths = render_stills(episode, plan, str(tmp_path), picks=picks, chart=chart)

    assert [os.path.basename(p) for p in paths] == [f"still_{i:05d}.png" for i in picks]
    for path in paths:
        with Image.open(path) as im:
            assert im.size == (1440, 888)
            assert len(im.convert("RGB").getcolors(maxcolors=1 << 20)) > 20      # לא פריים ריק


def test_a_frame_draws_the_same_regardless_of_what_was_drawn_before(episode, plan):
    ctx = chart_context(episode)
    target = _first(plan, lambda f: f["k"] == "main" and len(f["bars"]) >= 3)
    fresh = make_chart(ctx).render(plan[target])
    chart = make_chart(ctx)
    for i in (0, len(plan) - 1, target - 20, target - 1):
        chart.render(plan[i])
    assert chart.render(plan[target]) == fresh
    # מסכות החיתוך של הפריים האחרון עם עמודות נשמרות בחיים (ראו BaseChart._clear_dynamic)
    chart.render(plan[0])
    assert chart._retired and all(a.get_clip_path() is not None for a in chart._retired)


def test_chart_context_places_ticks_and_events_on_the_timeline(episode):
    ctx = chart_context(episode)
    assert [label for _, label in ctx["timeline"]["ticks"]] == ["2019"]          # tick_years=5 מ-2019
    assert len(ctx["timeline"]["events"]) == 2 and all(0 < x < 1 for x in ctx["timeline"]["events"])
    assert ctx["palette"] == "ordinal" and ctx["textures"][2019] == "stripes" and ctx["textures"][2023] == "solid"
    assert ctx["legend"] == [("שנתי", "stripes"), ("יומי", "solid")]


def test_ffmpeg_command_pipes_raw_frames_and_mixes_the_music():
    video = {"preset": "veryfast", "crf": 18}
    audio = {"start": 12.5, "fade_in": 2, "fade_out": 6, "bitrate": "192k"}
    cmd = ffmpeg_command("ffmpeg", (1440, 888), 60, 190.416, "out.mp4", video, audio, "music.mp3")

    assert cmd[cmd.index("-s") + 1] == "1440x888" and cmd[cmd.index("-i") + 1] == "-"
    assert cmd[cmd.index("-ss") + 1] == "12.5" and cmd.index("-ss") < cmd.index("music.mp3")
    assert cmd[cmd.index("-af") + 1] == "afade=t=in:st=0:d=2,afade=t=out:st=184.42:d=6"
    assert cmd[-3:] == ["-t", "190.416", "out.mp4"]
    silent = ffmpeg_command("ffmpeg", (100, 100), 30, 5, "o.mp4", video)
    assert "-map" not in silent and "-af" not in silent
    assert audio_filter(4, 2, 6) == "afade=t=in:st=0:d=2,afade=t=out:st=0.00:d=6"


def test_unknown_chart_type_is_a_clear_error():
    with pytest.raises(ValueError, match="rocket_race"):
        chart_class("rocket_race")


def test_line_labels_never_overlap_and_stay_above_the_floor():
    ys = spread_labels([100, 99, 98, 50, 1, 0.5, 0], gap=5)
    assert all(a - b >= 5 - 1e-9 for a, b in zip(ys, ys[1:]))
    assert ys[0] == 100 and ys[3] == 50 and min(ys) == 0
    assert spread_labels([10, 0], gap=3) == [10, 0]


def test_scatter_labels_that_would_overlap_move_up_a_row():
    from dataviz.charts.scatter_race import label_tiers
    # שלוש תוויות צפופות (רוחב 40px) ואחת רחוקה
    assert label_tiers([100, 110, 120, 400], [40, 40, 40, 40]) == [0, 1, 2, 0]
    assert label_tiers([0, 100, 200], [40, 40, 40]) == [0, 0, 0]


def test_dark_theme_keeps_text_readable_on_light_fills():
    from dataviz.themes import get_theme
    dark, light = get_theme("dark"), get_theme("light")
    assert dark.on_light != dark.ink and light.on_light == light.ink
    assert get_theme("light", {"accent": "#000000"}).accent == "#000000"
    with pytest.raises(ValueError):
        get_theme("light", {"no_such_field": 1})


def test_rank_matrix_ranks_active_entities_and_ignores_unstarted_ones():
    import numpy as np
    from dataviz.charts.bump_race import rank_matrix
    cum = np.array([[5.0, 0.0, 0.0], [5.0, 9.0, 0.0], [20.0, 9.0, 12.0], [20.0, 30.0, 12.0]])
    ranks = rank_matrix(cum, [0, 1, 2], smooth=1)
    assert np.isnan(ranks[0, 1]) and np.isnan(ranks[0, 2]) and np.isnan(ranks[1, 2])
    assert ranks[0, 0] == 1 and list(ranks[1, :2]) == [2, 1] and list(ranks[2]) == [1, 3, 2] and list(ranks[3]) == [2, 1, 3]
    smooth = rank_matrix(cum, [0, 1, 2], smooth=2)
    assert smooth[3, 1] == pytest.approx(2.0) and smooth[3, 0] == pytest.approx(1.5)      # ממוצע נע; לא התחילו = NaN
    assert np.isnan(smooth[0, 2])


@pytest.mark.parametrize("chart", ["bump_race", "heatmap_race"])
def test_new_chart_types_draw_different_pictures_than_the_bar_race(episode, plan, chart):
    ctx = chart_context(episode)
    target = _first(plan, lambda f: f["k"] == "main" and len(f["bars"]) >= 3)
    frames = {name: make_chart(chart_class_ctx(ctx, name)).render(plan[target]) for name in ("bar_race", chart)}
    assert frames["bar_race"] != frames[chart]


def chart_class_ctx(ctx, name):
    return {**ctx, "chart": name}


# ---------- 18.10.2026: ליקויי תצוגה שנראו בסרטון אקלים ----------
LONG_NAME = "מפלס הכנרת (מטר מתחת לפני הים, ממוצע שנתי) - שם ארוך במיוחד"


def _last_main(plan):
    return plan[max(i for i, f in enumerate(plan) if f["k"] == "main")]


@pytest.mark.parametrize("chart", ["line_race", "stacked_area_race"])
def test_a_long_line_label_is_wrapped_inside_the_frame_not_cut_at_the_edge(tmp_path, chart):
    # התווית בקצה הקו מתחילה אחרי הנקודה ונכתבת ימינה - שם ארוך יצא מהפריים ונחתך
    episode = load_episode(write_episode(tmp_path, overrides={"chart": chart, "entities": {"aliases": {"2023": LONG_NAME}}}))
    plan = build_plan(episode, "test")
    figure = make_chart(chart_context(episode))
    try:
        figure.render(_last_main(plan))
        renderer = figure.fig.canvas.get_renderer()
        labels = [a for a in figure._dynamic if hasattr(a, "get_text") and "הכנרת" in a.get_text()]
        assert labels, "התווית של הישות הארוכה לא צוירה"
        for label in labels:
            box = label.get_window_extent(renderer)
            assert 0 <= box.x0 and box.x1 <= figure.fig.bbox.width, (box.x0, box.x1, figure.fig.bbox.width)
            assert " ".join(label.get_text().split()).startswith(LONG_NAME)   # השם כולו, רק בשורות
        short = [a for a in figure._dynamic if hasattr(a, "get_text") and a.get_text().startswith("2020")]
        assert short and all("\n" not in a.get_text() for a in short)   # תווית קצרה לא משתנה
    finally:
        figure.close()


def test_three_notes_all_fit_under_the_timeline(tmp_path):
    # NOTE_Y נותן מקום לשתי שורות; השלישית ירדה ל-y שלילי - מתחת לתחתית הפריים
    notes = ["הערה ראשונה", "הערה שנייה", "הערה שלישית"]
    episode = load_episode(write_episode(tmp_path, overrides={"notes": notes}))
    figure = make_chart(chart_context(episode))
    try:
        figure.render(_last_main(build_plan(episode, "test")))
        renderer = figure.fig.canvas.get_renderer()
        boxes = [n.get_window_extent(renderer) for n in figure.notes]
        timeline_bottom = figure.tl.get_tightbbox(renderer).y0
        assert [n.get_text() for n in figure.notes] == notes
        assert all(b.y0 >= 0 and b.y1 <= timeline_bottom for b in boxes), [(b.y0, b.y1, timeline_bottom) for b in boxes]
        assert all(upper.y0 >= lower.y1 for upper, lower in zip(boxes, boxes[1:]))   # בלי חפיפה, לפי הסדר
    finally:
        figure.close()


def test_one_or_two_notes_stay_where_they_were(episode):
    figure = make_chart(chart_context(episode))
    try:
        assert [round(n.get_position()[1], 6) for n in figure.notes] == [0.05, 0.022]
    finally:
        figure.close()
