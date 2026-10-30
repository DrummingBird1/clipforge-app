# tests/dataviz/test_dataviz_wave49.py - גל 49 בעורך הגרפים, "המספרים": פורמט מספרים (K / M, מילים, ספרות, קידומת וסיומת),
# חלון מתגלגל במקום מצטבר, לנפש לפי אוכלוסייה, ציר לוגריתמי, חיצי דירוג ▲▼ ותוויות "+N". בלי ffmpeg - רק תכנית
# ופריימים קטנים; כל התוספות כבויות כברירת מחדל, וטסט מוודא שפריים בלי הן זהה בדיוק לפריים של קודם.
import os


import numpy as np
import pytest
import yaml

from dataviz.charts import CHART_MODULES, make_chart
from dataviz.charts.base import format_int, format_number
from dataviz.config import ConfigError, load_config
from dataviz.episode import build_episode, load_episode
from dataviz.plan import build_plan
from dataviz.render import chart_context
from tests.dataviz_helpers import write_episode

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}

# שלוש ערים: א' מובילה בהתחלה, ב' עוקפת בקפיצה ב-10.1, ג' קטנה
CITY_ROWS = ([("2024-01-%02d" % d, "א", 10) for d in range(1, 31)] + [("2024-01-%02d" % d, "ב", 4) for d in range(1, 31)]
             + [("2024-01-10", "ב", 400), ("2024-01-05", "ג", 3)])


def city_episode(root, extra=None, populations=None):
    folder = os.path.join(str(root), "cities")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "data.csv"), "w", encoding="utf-8") as f:
        f.write("date,city,value\n" + "".join(f"{d},{c},{v}\n" for d, c, v in CITY_ROWS))
    if populations is not None:
        with open(os.path.join(folder, "pop.csv"), "w", encoding="utf-8") as f:
            f.write("entity,population\n" + "".join(f"{k},{v}\n" for k, v in populations.items()))
    config = {"title": "ערים", "ranking": {"top_n": 3, "axis_min": 1.0}, **SMALL,
              "sources": [{"path": "data.csv", "time": {"column": "date"}, "value": {"column": "value"}, "entity": {"column": "city"}}]}
    for key, value in (extra or {}).items():
        config[key] = value
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return folder


# ---------- פורמט מספרים ----------
@pytest.mark.parametrize("value,numbers,expected", [
    (1234567.8, None, "1,234,568"),   # 16.10: עיגול חצי למעלה (היה קטימה)
    (1234567.8, {"style": "plain", "decimals": 0, "prefix": "", "suffix": "", "thousands": True}, "1,234,568"),
    (1234567.8, {"style": "compact", "decimals": 1}, "1.2M"),
    (2500, {"style": "compact", "decimals": 0}, "3K"),   # חצי למעלה, לא לזוגי
    (999, {"style": "compact", "decimals": 1}, "999"),
    (3_400_000_000, {"style": "words", "decimals": 1}, "3.4 מיליארד"),
    (12.345, {"decimals": 2, "suffix": "%"}, "12.35%"),
    (1500, {"prefix": "₪"}, "₪1,500"),
    (42, {"suffix": "ק\"מ"}, "42 ק\"מ"),
    (42, {"prefix": "USD"}, "USD 42"),
    (-1500.5, {"prefix": "$", "decimals": 1}, "-$1,500.5"),
    (1234567, {"thousands": False}, "1234567"),
])
def test_number_format(value, numbers, expected):
    assert format_number(value, numbers) == expected


def test_default_numbers_are_exactly_the_first_video():
    for value in (0, 0.9, 59.99, 1234.5, 10 ** 7 + 0.4, -3.7):
        assert format_number(value, load_config_defaults()["numbers"]) == format_int(value)


def load_config_defaults():
    from dataviz.config import DEFAULTS
    return DEFAULTS


# ---------- חלון מתגלגל ולנפש ----------
def test_rolling_window_shows_only_the_last_days(tmp_path):
    cumulative = load_episode(city_episode(tmp_path))
    rolling = load_episode(city_episode(tmp_path, {"values": {"mode": "rolling", "window_days": 3}}))
    col = rolling.entities.index("א")
    assert cumulative.cum[-1, col] == 300 and rolling.cum[-1, col] == 30   # 3 ימים x 10
    b = rolling.entities.index("ב")
    assert rolling.cum[9, b] == 4 * 2 + 404 and rolling.cum[12, b] == 12   # הקפיצה יוצאת מהחלון
    assert list(rolling.start_idx) == list(cumulative.start_idx)
    plan = build_plan(rolling, "test")
    assert plan and all(f["k"] in ("intro", "main", "outro") for f in plan)


def test_per_capita_divides_by_population_and_drops_unknown_entities(tmp_path):
    folder = city_episode(tmp_path, {"values": {"per_capita": {"enabled": True, "file": "pop.csv", "per": 1000}}},
                          populations={"א": 2000, "ב": 50000})
    episode = load_episode(folder)
    assert episode.entities == ["א", "ב"]                                  # ג בלי אוכלוסייה - לא מוצגת
    assert episode.cum[-1, 0] == pytest.approx(300 / 2000 * 1000)
    assert episode.cum[-1, 1] == pytest.approx((120 + 400) / 50000 * 1000)


def test_per_capita_inline_populations_and_clear_errors(tmp_path):
    folder = city_episode(tmp_path, {"values": {"per_capita": {"enabled": True, "populations": {"ג": 10}}}})
    assert load_episode(folder).entities == ["ג"]
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(city_episode(tmp_path, {"values": {"per_capita": {"enabled": True}}}), "config.yaml"))
    assert any("קובץ אוכלוסייה" in m for m in e.value.errors)
    with pytest.raises(ValueError, match="לאף ישות אין אוכלוסייה"):
        load_episode(city_episode(tmp_path, {"values": {"per_capita": {"enabled": True, "populations": {"zzz": 5}}}}))


def test_bad_number_settings_are_reported_together(tmp_path):
    folder = city_episode(tmp_path, {"values": {"mode": "weekly", "window_days": 0},
                                     "numbers": {"style": "roman", "decimals": 9, "prefix": "x" * 20},
                                     "ranking": {"log_scale": "yes"}, "labels": {"rank_window_days": 0, "gains_min": 3}})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    text = "\n".join(e.value.errors)
    for key in ("values.mode", "values.window_days", "numbers.style", "numbers.decimals", "numbers.prefix",
                "ranking.log_scale", "labels.rank_window_days", "labels.gains_min"):
        assert key in text, key


# ---------- חיצי דירוג ו-"+N" בתכנית ----------
def test_arrows_and_gains_only_when_enabled(tmp_path):
    plain = build_plan(load_episode(city_episode(tmp_path)), "full")
    assert not any("moves" in f or "gains" in f for f in plain)
    folder = city_episode(tmp_path, {"labels": {"rank_arrows": True, "rank_window_days": 2, "gains": True, "gains_min": 0.1}})
    plan = build_plan(load_episode(folder), "full")
    main = [f for f in plan if f["k"] == "main"]
    overtake = [f for f in main if f["moves"].get("ב", 0) > 0]
    assert overtake and overtake[0]["date"].startswith("10/01/2024")      # ב' עלתה מקום אחד בקפיצה
    assert any(f["moves"].get("א", 0) < 0 for f in main)                 # וא' ירדה
    jumps = [f["gains"]["ב"] for f in main if "ב" in f.get("gains", {})]
    assert jumps and max(jumps) == pytest.approx(404)
    late = [f for f in main if f["date"] >= "15/01/2024"]
    assert late and not any("א" in f.get("gains", {}) for f in late)      # אחרי הקפיצה 10 ביום זה פחות מ-10% מהציר


# ---------- ציור: כל התרשימים עם כל התוספות ----------
@pytest.mark.parametrize("chart", [c for c in CHART_MODULES if c != "map_race"])
def test_every_chart_draws_with_log_axis_arrows_gains_and_formats(tmp_path, chart):
    folder = city_episode(tmp_path, {"chart": chart, "ranking": {"top_n": 3, "axis_min": 1.0, "log_scale": True},
                                     "labels": {"rank_arrows": True, "gains": True, "gains_min": 0.0},
                                     "numbers": {"style": "compact", "decimals": 1, "prefix": "₪"},
                                     "values": {"mode": "rolling", "window_days": 5}})
    episode = load_episode(folder)
    plan = build_plan(episode, "test")
    chart_obj = make_chart(chart_context(episode))
    try:
        for frame in (plan[len(plan) // 2], plan[-1]):
            assert len(chart_obj.render(frame)) == 320 * 200 * 4
    finally:
        chart_obj.close()


def test_default_settings_draw_the_same_pixels_as_before(tmp_path):
    """בלי התוספות: אותו פריים בדיוק עם ctx בלי numbers / log_scale (כמו לפני גל 49) ועם ברירות המחדל."""
    episode = load_episode(write_episode(tmp_path, overrides=SMALL))
    plan = build_plan(episode, "test")
    frame = plan[len(plan) // 2]
    for chart in ("bar_race", "line_race", "scatter_race", "heatmap_race"):
        ctx = chart_context(episode, chart)
        before = {k: v for k, v in ctx.items() if k not in ("numbers", "log_scale")}
        images = []
        for context in (before, ctx):
            obj = make_chart(context)
            try:
                images.append(obj.render(frame))
            finally:
                obj.close()
        assert images[0] == images[1], chart


def test_build_episode_keeps_cumulative_by_default(tmp_path):
    episode = build_episode(load_config(os.path.join(write_episode(tmp_path, overrides=SMALL), "config.yaml")))
    assert np.allclose(episode.cum, np.cumsum(episode.daily, axis=0))
