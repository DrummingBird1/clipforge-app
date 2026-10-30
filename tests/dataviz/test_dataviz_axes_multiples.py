# tests/dataviz/test_dataviz_axes_multiples.py
#
# 20.10.2026: סדרות ביחידות שונות (הכנרת: טמפרטורה 18-22 מול מפלס 208-215) - (א) ציר y שני ב-line_race: מקור עם
# axis: right על הציר הימני, לכל ציר טווח, פורמט וכותרת משלו; (ב) "גרפים קטנים" (small_multiples) - גרף לכל ישות עם ציר
# משלו וזמן משותף. בלי axis: right - ציר אחד בדיוק כמו קודם (וה-ctx בלי מפתחות חדשים).
import os

import pytest

from tests.dataviz_helpers import write_episode

VIDEO = {"video": {"width": 640, "height": 400, "fps": 10, "dpi": 40}}
TEMP = "year,entity,level\n2018,T,18.3\n2019,T,19.1\n2020,T,18.6\n2021,T,21.8\n"
LAKE = "year,entity,level\n2018,K,210.4\n2019,K,209.2\n2020,K,212.1\n2021,K,211.0\n"


def _episode(tmp_path, right=True, **config):
    sources = [{"path": "temp.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "level"},
                "entity": {"column": "entity"}, "kind": "level"},
               {"path": "lake.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "level"},
                "entity": {"column": "entity"}, "kind": "level", **({"axis": "right"} if right else {})}]
    folder = write_episode(tmp_path, overrides={"chart": "line_race", **VIDEO, "sources": sources, **config})
    for name, text in (("temp.csv", TEMP), ("lake.csv", LAKE)):
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)
    from dataviz.episode import load_episode
    return load_episode(folder)


def _render(episode, at=-1, kind="main"):
    from dataviz.charts import make_chart
    from dataviz.plan import build_plan
    from dataviz.render import chart_context
    frames = [f for f in build_plan(episode, "full") if f["k"] == kind]
    chart = make_chart(chart_context(episode))
    chart.render(frames[at])
    return chart


def test_a_right_axis_source_gets_its_own_range_format_and_title(tmp_path):
    episode = _episode(tmp_path, y_axes={"left": {"label": "°C"}, "right": {"label": "מטר", "numbers": {"suffix": " מ'", "decimals": 2}}})
    assert episode.right_axis == ["K"]
    chart = _render(episode)
    try:
        lo_l, hi_l = chart.ax.get_ylim()
        lo_r, hi_r = chart.ax2.get_ylim()
        assert 17 <= lo_l <= 18.3 and 21.8 <= hi_l <= 23                   # הטמפרטורה לא נמעכת
        assert 200 <= lo_r <= 209.2 and 212.1 <= hi_r <= 220                # המפלס על ציר משלו
        texts = [t.get_text() for t in chart.ax.texts + chart.ax2.texts]
        assert any(t.startswith("K") and t.endswith("211.00 מ'") for t in texts)   # פורמט הציר הימני
        assert any(t.startswith("T") and "21.8" in t and "מ'" not in t for t in texts)
        assert {"°C", "מטר"} <= set(texts)                                  # כותרת מעל כל ציר
        assert chart.ax2.lines and chart.ax.lines
    finally:
        chart.close()


def test_without_a_right_axis_source_nothing_changes(tmp_path):
    from dataviz.render import chart_context
    episode = _episode(tmp_path, right=False)
    assert episode.right_axis == [] and "right_axis" not in chart_context(episode) and "y_axes" not in chart_context(episode)
    chart = _render(episode)
    try:
        assert chart.ax2 is None
    finally:
        chart.close()


def test_axis_settings_are_validated(tmp_path):
    from dataviz.config import ConfigError
    with pytest.raises(ConfigError, match="axis"):
        _episode(tmp_path / "a", right=False, sources=[{"path": "temp.csv", "time": {"column": "year", "period": "year"},
                                                        "value": {"column": "level"}, "entity": {"column": "entity"}, "axis": "middle"}])
    with pytest.raises(ConfigError, match="y_axes"):
        _episode(tmp_path / "b", y_axes={"right": {"numbers": {"decimals": 9}}})


def test_the_axis_is_part_of_a_source_mapping(tmp_path):
    from dataviz.web import episodes as de
    mapping = de.clean_mapping({"time_column": "year", "period": "year", "value_column": "level", "axis": "right"})
    assert de.source_spec("lake.csv", mapping)["axis"] == "right"
    assert "axis" not in de.source_spec("lake.csv", de.clean_mapping({"time_column": "year"}))
    with pytest.raises(de.EpisodeError):
        de.clean_mapping({"time_column": "year", "axis": "up"})


def test_small_multiples_give_every_entity_its_own_panel_and_axis(tmp_path):
    episode = _episode(tmp_path, right=False, chart="small_multiples")
    chart = _render(episode)
    try:
        panels = {e: ax for ax, _col, e in chart._panels}
        assert set(panels) == {"T", "K"}
        lo_t, hi_t = panels["T"].get_ylim()
        lo_k, hi_k = panels["K"].get_ylim()
        assert 17 <= lo_t <= 18.3 and 21.8 <= hi_t <= 23 and 200 <= lo_k <= 209.2 and 212.1 <= hi_k <= 220   # כל אחד בטווח שלו
        assert all(ax.lines for ax in panels.values()) and all(ax.get_visible() for ax in panels.values())
        assert not chart.ax.axison                                          # הציר הראשי מוסתר
    finally:
        chart.close()
    intro = _render(episode, at=0, kind="intro")
    try:
        assert not any(ax.get_visible() for ax, _c, _e in intro._panels)     # בפתיח - בלי הגרפים
    finally:
        intro.close()
