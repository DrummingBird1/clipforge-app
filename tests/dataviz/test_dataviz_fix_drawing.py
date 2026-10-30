# tests/dataviz/test_dataviz_fix_drawing.py
#
# 23.10.2026, סריקת הבאגים - מנה 5 (הציור). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ג5 מרוץ העמודות בלי עמודה מתחת ל-0.5 ובלי ערך מתחת ל-1; ג6 משפט מהתסריט בתאריך של עצירה הוקרא בכל פריים קפוא;
# ב12 הטיזר - פריים קפוא, ואירוע ותסריט פעמיים; ב13 map_race עם log וערך שלילי קרס; ב14 scatter_race עם ערך שלילי
# קרס; ב15 פרק קצר תפס חלק קטן מהרוחב, בלי שנתות; ב16 שמות ארוכים יצאו מהפריים; ב17 ב-rolling ההיסטוריה נחתכה
# מלמעלה; ב18 שנתות compact כפולות או שגויות; ב19 בועות מתחת לפריים; נ11 תגית התקופה על המקרא בגרסה באנגלית;
# נ12 עוגה עם ישות שלילית; נ13 "-0" על המסך; נ14 בלי יחידה מעל מיליארד, ו-999.6 נשאר "1,000".
import json
import os

import pytest
import yaml
from matplotlib.collections import PathCollection, PolyCollection
from matplotlib.image import AxesImage
from matplotlib.patches import Rectangle, Wedge
from matplotlib.text import Text

from dataviz.captions import caption_spans
from dataviz.charts import make_chart
from dataviz.charts.base import format_number
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.render import chart_context
from tests.dataviz_helpers import write_episode

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}
WIDE = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


def _episode(root, rows, extra=None, name="ep"):
    """פרק מקובץ אחד: (תאריך, ישות, ערך) לשורה."""
    folder = os.path.join(str(root), name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "data.csv"), "w", encoding="utf-8") as f:
        f.write("date,name,value\n" + "".join(f"{d},{e},{v}\n" for d, e, v in rows))
    config = {"title": "בדיקה", "ranking": {"top_n": 4, "axis_min": 0.1}, **SMALL,
              "sources": [{"path": "data.csv", "time": {"column": "date"}, "value": {"column": "value"}, "entity": {"column": "name"}}]}
    config.update(extra or {})
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return folder


def _days(n, start="2024-01-01"):
    import pandas as pd
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, periods=n)]


@pytest.fixture
def draw():
    """מצייר פריים (ברירת מחדל: האחרון של התכנית) ומחזיר את התרשים - נסגר בסוף הטסט."""
    charts = []

    def _draw(folder, pick=-1, ctx_extra=None):
        episode = load_episode(folder)
        plan = build_plan(episode, "test")
        ctx = {**chart_context(episode), **(ctx_extra or {})}
        chart = make_chart(ctx)
        charts.append(chart)
        chart.render(pick(plan) if callable(pick) else plan[pick])
        return chart
    yield _draw
    for chart in charts:
        chart.close()


def _texts(chart):
    return [a.get_text() for a in chart._dynamic if isinstance(a, Text)]


def _last_main(plan):
    return [f for f in plan if f["k"] == "main"][-1]


# ---------- ג5 ----------
def test_bar_race_draws_and_labels_small_values(tmp_path, draw):
    days = _days(10)
    rows = [(d, "א", 0.03) for d in days] + [(d, "ב", 0.08) for d in days] + [(d, "ג", 0) for d in days]
    chart = draw(_episode(tmp_path, rows, {"numbers": {"decimals": 1}}))          # הסיום: 0.3, 0.8, 0
    texts = _texts(chart)
    assert "0.3" in texts and "0.8" in texts                                    # קודם: שום ערך מתחת ל-1
    assert "0.0" not in texts                                                   # ישות שהערך שלה 0 - בלי תווית
    assert sum(isinstance(a, AxesImage) for a in chart._dynamic) == 2           # קודם: רק העמודה של 0.8


def test_bar_race_shows_the_value_of_a_negative_entity(tmp_path, draw):
    days = _days(10)
    rows = [(d, "א", 5) for d in days] + [(d, "ב", -0.5) for d in days]
    chart = draw(_episode(tmp_path, rows))
    assert "-5" in _texts(chart)                                                # קודם: בלי תווית


# ---------- ג6 ----------
def test_a_script_line_on_a_hold_is_said_once(tmp_path):
    story = {"pauses": [{"date": "2022-01-01", "text": "עצירה"}], "chapters": [{"date": "2022-01-01", "title": "פרק"}],
             "script": [{"date": "2022-01-01", "text": "משפט מהתסריט"}]}
    plan = build_plan(load_episode(write_episode(tmp_path, overrides={**SMALL, "story": story})), "test")
    assert sum(len(f.get("say") or []) for f in plan) == 1                      # קודם: בכל פריים קפוא
    first = next(i for i, f in enumerate(plan) if f.get("say"))
    assert plan[first].get("hold") and not plan[first - 1].get("hold")         # בתחילת העצירה, כמו קודם
    assert sum(s["kind"] == "script" for s in caption_spans(plan, 10)) == 1


# ---------- ב12 ----------
def test_the_teaser_moves_and_does_not_repeat_events_and_script(tmp_path):
    story = {"pauses": [{"date": "2023-10-07", "text": "עצירה"}], "script": [{"date": "2023-10-07", "text": "משפט"}]}
    plan = build_plan(load_episode(write_episode(tmp_path, overrides={**SMALL, "story": story, "teaser": {"enabled": True}})), "test")
    teaser = [f for f in plan if f.get("teaser")]
    assert len(teaser) == 30 and len({f["x"] for f in teaser}) == len(teaser)  # קודם: רובו פריים קפוא אחד
    assert not any(f.get(key) for f in teaser for key in ("say", "card", "toast", "hold"))
    spans = caption_spans(plan, 10)
    assert sum(s["kind"] == "script" for s in spans) == 1                       # קודם: גם בטיזר
    assert sum(s["kind"] == "event" and s["label"] == "אירוע גדול" for s in spans) == 1


# ---------- ב13 ----------
def test_map_race_with_log_scale_and_a_negative_value_draws(tmp_path, draw):
    days = _days(10)
    rows = [(d, "צפון", 50) for d in days] + [(d, "דרום", -5) for d in days]
    folder = _episode(tmp_path, rows, {"chart": "map_race", "map": {"geojson": "regions.geojson"}, "ranking": {"top_n": 2, "log_scale": True}})
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": name}, "geometry": {"type": "Polygon", "coordinates": [[[34 + i, 31], [35 + i, 31], [35 + i, 32], [34 + i, 32], [34 + i, 31]]]}}
        for i, name in enumerate(("צפון", "דרום"))]}
    with open(os.path.join(folder, "regions.geojson"), "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)
    draw(folder, _last_main)                                                    # קודם: ValueError (log1p של -50)


# ---------- ב14 / ב19 ----------
def test_scatter_race_with_negative_values_draws(tmp_path, draw):
    days = _days(40)
    rows = [(d, "א", 10) for d in days] + [(d, "ב", 50 if i == 0 else -100) for i, d in enumerate(days)]   # מתחיל חיובי ויורד מתחת ל-0
    draw(_episode(tmp_path, rows, {"chart": "scatter_race"}), _last_main)       # קודם: ValueError (sqrt של גודל שלילי)


def test_scatter_bubbles_with_a_falling_rate_stay_in_the_frame(tmp_path, draw):
    days = _days(120)
    rows = [(d, "א", 100 if i < 40 else 1) for i, d in enumerate(days)] + [(d, "ב", 5) for d in days]
    chart = draw(_episode(tmp_path, rows, {"chart": "scatter_race", "values": {"mode": "rolling", "window_days": 30},
                                           "scatter": {"window_days": 30}}), lambda plan: [f for f in plan if f["k"] == "main"][-10])
    bottom = chart.ax.get_ylim()[0]
    ys = [y for a in chart._dynamic if isinstance(a, PathCollection) for _x, y in a.get_offsets()]
    assert min(ys) < 0 and min(ys) >= bottom                                    # קודם: הבועה מתחת לתחתית הציר


# ---------- ב15 ----------
def test_a_short_episode_fills_the_width_and_has_month_ticks(tmp_path, draw):
    days = _days(70)
    rows = [(d, "א", 3) for d in days] + [(d, "ב", 2) for d in days]
    chart = draw(_episode(tmp_path, rows, {"chart": "line_race"}), _last_main)
    assert chart.ax.get_xlim()[1] < 69 * 1.2                                    # קודם: 365 ימים - הקו ב-20% מהרוחב
    labels = [t.get_text() for t in chart.ax.get_xticklabels() if t.get_text()]
    assert labels == ["1/2024", "2/2024", "3/2024"]                             # קודם: רק "2024"


# ---------- ב16 ----------
LONG = "הממלכה המאוחדת של בריטניה הגדולה וצפון אירלנד"


@pytest.mark.parametrize("chart_name", ["bar_race", "bump_race", "heatmap_race", "scatter_race"])
def test_long_names_stay_inside_the_frame(tmp_path, draw, chart_name):
    days = _days(800)                                                           # ציר הזמן מלא - התווית בקצה הימני
    rows = [(d, LONG, 10) for d in days] + [(d, "ב", 4) for d in days] + [(d, "ג", 2) for d in days]
    chart = draw(_episode(tmp_path, rows, {"chart": chart_name, **WIDE}), _last_main)
    renderer = chart.fig.canvas.get_renderer()
    width = chart.fig.bbox.width
    names = [a for a in chart._dynamic if isinstance(a, Text) and LONG.split()[0] in a.get_text()]
    assert names
    for name in names:
        box = name.get_window_extent(renderer)
        assert box.x0 >= 0 and box.x1 <= width, (chart_name, box.x0, box.x1)   # קודם: יצא מהפריים


# ---------- ב17 ----------
@pytest.mark.parametrize("chart_name", ["line_race", "stacked_area_race"])
def test_rolling_history_is_not_cut_at_the_top(tmp_path, draw, chart_name):
    days = _days(60)
    rows = [(d, "א", 100 if i < 10 else 1) for i, d in enumerate(days)] + [(d, "ב", 1) for d in days]
    chart = draw(_episode(tmp_path, rows, {"chart": chart_name, "values": {"mode": "rolling", "window_days": 5}}))   # הסיום
    top = chart.ax.get_ylim()[1]
    if chart_name == "line_race":
        peak = max(max(line.get_ydata()) for line in chart.ax.get_lines() if line in chart._dynamic)
    else:
        peak = max(path.vertices[:, 1].max() for a in chart._dynamic if isinstance(a, PolyCollection) for path in a.get_paths())
    assert peak >= 400 and top >= peak                                          # קודם: הציר עד 5.65 - השיא בחוץ


# ---------- ב18 ----------
@pytest.mark.parametrize("chart_name,axis", [("bar_race", "xaxis"), ("line_race", "yaxis"), ("scatter_race", "yaxis")])
def test_compact_ticks_are_distinct_and_exact(tmp_path, draw, chart_name, axis):
    days = _days(10)
    rows = [(d, "א", 300) for d in days] + [(d, "ב", 100) for d in days]
    chart = draw(_episode(tmp_path, rows, {"chart": chart_name, "numbers": {"style": "compact", "decimals": 0}}))
    formatter = getattr(chart.ax, axis).get_major_formatter()
    assert formatter.format_ticks([0, 500, 1000, 1500, 2000, 2500]) == ["0", "500", "1K", "1.5K", "2K", "2.5K"]   # קודם: 2K, 2K, 3K
    assert formatter.format_ticks([0, 1000, 2000]) == ["0", "1K", "2K"]         # בלי ספרות מיותרות


# ---------- נ11 ----------
def test_the_period_tag_does_not_cover_the_legend_in_english(tmp_path, draw):
    story = {"periods": [{"start": "2019-01-01", "end": "2023-12-31", "label": "Period"}]}
    folder = write_episode(tmp_path, overrides={**WIDE, "language": "en", "story": story})
    chart = draw(folder, _last_main)
    renderer = chart.fig.canvas.get_renderer()
    tag = next(a for a in chart._dynamic if isinstance(a, Text) and a.get_text() == "Period").get_bbox_patch()
    legend = [a for a in chart._header if isinstance(a, Rectangle) or (isinstance(a, Text) and a.get_text() in ("שנתי", "יומי"))]
    assert len(legend) == 4                                                     # שתי דוגמיות ושתי תוויות
    for item in legend:
        assert not tag.get_window_extent(renderer).overlaps(item.get_window_extent(renderer))   # קודם: על הדוגמית הראשונה


# ---------- נ12 ----------
def test_a_pie_with_a_negative_entity_adds_up_to_a_full_circle(tmp_path, draw):
    days = _days(10)
    rows = [(d, "א", 10) for d in days] + [(d, "ב", 5) for d in days] + [(d, "ג", -3) for d in days]
    chart = draw(_episode(tmp_path, rows, {"chart": "pie_race", "ranking": {"top_n": 3, "axis_min": 0.1}}))
    sweep = sum(w.theta2 - w.theta1 for w in chart._dynamic if isinstance(w, Wedge) and w.get_facecolor()[3] > 0)
    assert sweep == pytest.approx(360.0)                                        # קודם: 450 - הטבעות חופפות
    percents = [int(t.rsplit("· ", 1)[1].rstrip("%")) for t in _texts(chart) if "%" in t]
    assert percents and max(percents) <= 100 and sum(percents) <= 101


# ---------- נ13 / נ14 ----------
@pytest.mark.parametrize("value,numbers,expected", [
    (-0.4, {"decimals": 0}, "0"),                                               # נ13: קודם "-0"
    (-0.04, {"decimals": 1}, "0.0"),                                            # קודם "-0.0"
    (-0.4, {"style": "compact", "decimals": 0}, "0"),
    (-0.4, {"decimals": 0, "prefix": "$"}, "$0"),
    (-0.6, {"decimals": 0}, "-1"),                                              # שלילי אמיתי - נשאר
    (999.6, {"style": "compact", "decimals": 0}, "1K"),                         # נ14: קודם "1,000"
    (-999.6, {"style": "compact", "decimals": 0}, "-1K"),
    (2.5e12, {"style": "compact", "decimals": 1}, "2.5T"),                      # קודם "2,500B"
    (2.5e12, {"style": "words", "decimals": 1}, "2.5 טריליון"),
    (2.5e12, {"style": "words", "decimals": 1, "lang": "en"}, "2.5 trillion"),
    (999_960_000_000, {"style": "compact", "decimals": 1}, "1T"),               # כמו 1M ולא 1000K
    (3_400_000_000, {"style": "words", "decimals": 1}, "3.4 מיליארד"),          # מה שהיה - בלי שינוי
    (2500, {"style": "compact", "decimals": 0}, "3K"),
])
def test_number_format_edges(value, numbers, expected):
    assert format_number(value, numbers) == expected
