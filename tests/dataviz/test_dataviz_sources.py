# tests/dataviz/test_dataviz_sources.py
#
# src/dataviz/sources: קריאת CSV / Excel / JSON לטבלה אחידה (time, entity, value), פיזור
# סכום שנתי על ימים או חודשים (גם לפי משקלות חודשיים וחלונות ימים), ומיזוג כל המקורות
# למטריצה יומית אחת.
import json
import os

import numpy as np
import pandas as pd
import pytest

from dataviz.sources import daily_matrix, read_table, source_type
from dataviz.sources.spread import spread_to_days
from tests.dataviz_helpers import write_episode


def test_csv_events_are_counted_per_day_with_filter_and_year_entities(tmp_path):
    folder = write_episode(tmp_path)
    spec = {"path": "alarms.csv", "time": {"column": "time"}, "filter": {"origin": "South"}, "value": "count"}

    table = read_table(spec, folder)

    # שורת "not a date" נזרקת, שורת North מסוננת
    assert len(table) == 5 + 800 + 20
    assert set(table["entity"]) == {2021, 2022, 2023}
    assert (table["time"] == table["time"].dt.normalize()).all()
    day = table[table["time"] == pd.Timestamp("2021-01-05")]
    assert day["value"].sum() == 2


def test_annual_total_spreads_evenly_over_the_days_of_the_year():
    s = spread_to_days(pd.Timestamp("2019-01-01"), "year", 365, {})
    assert len(s) == 365 and s.index[0] == pd.Timestamp("2019-01-01") and s.index[-1] == pd.Timestamp("2019-12-31")
    assert np.allclose(s.values, 1.0)


def test_annual_total_spreads_by_month_when_asked():
    s = spread_to_days(pd.Timestamp("2020-01-01"), "year", 1200, {"per": "month"})
    monthly = s.groupby(s.index.month).sum()
    assert np.allclose(monthly.values, 100.0)
    assert s.sum() == pytest.approx(1200)
    # בתוך חודש - שווה על הימים (פברואר 2020: 29 ימים)
    assert s[pd.Timestamp("2020-02-10")] == pytest.approx(100 / 29)


def test_weights_shape_the_spread_but_the_annual_total_wins():
    weights = pd.DataFrame({"year": [2020, 2020], "month": [1, 12], "total": [10.0, 30.0],
                            "window_start": [np.nan, "2020-12-25"], "window_end": [np.nan, "2020-12-31"]})
    s = spread_to_days(pd.Timestamp("2020-01-01"), "year", 400, {"weights": {"path": "x"}}, weights)

    assert s.sum() == pytest.approx(400)
    # 10:30 - ינואר מקבל רבע, חלון 25-31.12 מקבל שלושה רבעים, ושאר השנה אפס
    assert s[s.index.month == 1].sum() == pytest.approx(100)
    assert s["2020-12-25":"2020-12-31"].sum() == pytest.approx(300)
    assert s["2020-02-01":"2020-12-24"].sum() == 0


def test_rows_of_the_same_period_and_entity_are_summed_before_spreading(monkeypatch):
    # 18.10.2026: קובץ של 25MB עם הרבה שורות לאותה שנה - פיזור אחד לכל (תקופה, ישות), אותה תוצאה
    import dataviz.sources as sources
    calls = []
    monkeypatch.setattr(sources, "spread_to_days", lambda *a, **k: calls.append(a[0]) or spread_to_days(*a, **k))
    times = [pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01")] * 500
    table = pd.DataFrame({"time": times, "entity": ["A", "A", "B", "B"] * 250, "value": 1.0, "period": "year"})
    daily = sources._source_daily(table, {}, ".")
    assert len(calls) == 4
    assert daily["A"].sum() == pytest.approx(500) and daily["B"].sum() == pytest.approx(500)
    assert daily.loc["2020-06-01", "A"] == pytest.approx(250 / 366)


def test_excel_and_json_sources_read_into_the_same_table(tmp_path):
    rows = [{"date": "2024-01-01", "country": "A", "amount": 5}, {"date": "2024-01-02", "country": "B", "amount": 7},
            {"date": "2024-01-02", "country": "A", "amount": 1}]
    pd.DataFrame(rows).to_excel(tmp_path / "data.xlsx", index=False)
    (tmp_path / "data.json").write_text(json.dumps({"payload": {"items": rows}}), encoding="utf-8")
    base = {"time": "date", "entity": {"column": "country"}, "value": {"column": "amount"}}

    from_excel = read_table({**base, "path": "data.xlsx"}, str(tmp_path))
    from_json = read_table({**base, "path": "data.json", "records": "payload.items"}, str(tmp_path))

    assert source_type({"path": "data.xlsx"}) == "excel" and source_type({"path": "data.json"}) == "json"
    for table in (from_excel, from_json):
        assert list(table["entity"]) == ["A", "B", "A"]
        assert list(table["value"]) == [5, 7, 1]


def test_daily_matrix_merges_sources_fills_gaps_and_records_origins(tmp_path):
    folder = write_episode(tmp_path)
    specs = [
        {"path": "annual.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "total"}},
        {"path": "alarms.csv", "time": {"column": "time"}, "filter": {"origin": "South"}, "value": "count"},
    ]
    tables = [read_table(spec, folder) for spec in specs]

    matrix, origins = daily_matrix(tables, specs, folder)

    assert list(matrix.columns) == [2019, 2020, 2021, 2022, 2023]
    assert matrix.index[0] == pd.Timestamp("2019-01-01") and matrix.index[-1] == pd.Timestamp("2023-11-01")
    assert len(matrix) == (matrix.index[-1] - matrix.index[0]).days + 1     # אין ימים חסרים
    assert matrix[2019].sum() == pytest.approx(365) and matrix[2020].sum() == pytest.approx(732)
    assert matrix.loc["2023-10-07", 2023] == 800 and matrix.loc["2023-10-08", 2023] == 0
    assert origins == {2019: 0, 2020: 0, 2021: 1, 2022: 1, 2023: 1}


def test_daily_matrix_rejects_sources_without_any_valid_rows(tmp_path):
    (tmp_path / "empty.csv").write_text("time,origin\nbad,South\n", encoding="utf-8")
    spec = {"path": "empty.csv", "time": "time"}
    with pytest.raises(ValueError, match="אין אף שורת נתונים"):
        daily_matrix([read_table(spec, str(tmp_path))], [spec], str(tmp_path))


# ---------- 18.10.2026: מקור של רמות (kind: level) - טמפרטורה, מפלס: הערך כמו שהוא, לא מצטבר ----------
LEVELS_CSV = "year,entity,level\n2019,T,18.0\n2020,T,19.0\n2021,T,18.5\n2021,K,210.0\n2022,K,212.0\n"


def _level_episode(tmp_path, kind="level", **extra):
    folder = write_episode(tmp_path, overrides={"chart": "line_race", "sources": [dict(
        {"path": "levels.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "level"},
         "entity": {"column": "entity"}}, **({"kind": kind} if kind else {}), **extra)]})
    with open(os.path.join(folder, "levels.csv"), "w", encoding="utf-8") as f:
        f.write(LEVELS_CSV)
    from dataviz.episode import load_episode
    return load_episode(folder)


def _at(episode, entity, date):
    return float(episode.cum[episode.dates.get_loc(pd.Timestamp(date)), episode.entities.index(entity)])


def test_a_yearly_level_source_starts_at_its_first_value_and_moves_toward_each_year(tmp_path):
    episode = _level_episode(tmp_path)
    assert _at(episode, "T", "2019-01-01") == pytest.approx(18.0)     # מהיום הראשון - לא מ-0
    assert _at(episode, "T", "2019-12-31") == pytest.approx(18.0)     # השנה הראשונה מחזיקה את הערך הראשון
    assert _at(episode, "T", "2020-07-01") == pytest.approx(18.0 + 183 / 366)   # בדרך לערך של 2020 (כמו פיזור שנתי)
    assert _at(episode, "T", "2020-12-31") == pytest.approx(19.0)
    assert _at(episode, "T", "2022-12-31") == pytest.approx(18.5)     # אחרי השנה האחרונה - נשאר
    assert _at(episode, "K", "2020-12-31") == 0 and _at(episode, "K", "2021-01-01") == pytest.approx(210.0)
    k = episode.entities.index("K")
    assert episode.dates[episode.start_idx[k]] == pd.Timestamp("2021-01-01")


def test_a_level_line_appears_at_its_first_value_without_a_slow_climb(tmp_path):
    from dataviz.plan import build_plan
    episode = _level_episode(tmp_path)
    plan = [f for f in build_plan(episode, "full") if f["k"] == "main"]
    shown = [v for f in plan for e, v, _p in f["bars"] if e == "K"]
    assert shown and min(shown) >= 210.0 - 1e-6                       # הקו נכנס בערך הראשון שלו
    entry = episode.start_idx[episode.entities.index("K")]
    before_entry = [f for f in plan if entry - 1 <= f["x"] < entry]
    assert len(before_entry) < 5      # הכניסה של רמה היא לא "קפיצה" שכלל ה-STEP מאט עליה (הייתה כ-200 פריימים)


def test_a_daily_level_source_fills_missing_days_between_known_ones(tmp_path):
    folder = write_episode(tmp_path)
    with open(os.path.join(folder, "daily_levels.csv"), "w", encoding="utf-8") as f:
        f.write("date,level\n2020-01-01,5\n2020-01-05,9\n")
    spec = {"path": "daily_levels.csv", "time": {"column": "date"}, "value": {"column": "level"}, "entity": "L", "kind": "level"}
    for missing, expected in ((None, [5, 6, 7, 8, 9]), ("previous", [5, 5, 5, 5, 9])):
        matrix, _ = daily_matrix([read_table(spec, folder)], [dict(spec, missing=missing) if missing else spec], folder)
        assert list(matrix["L"].cumsum().loc["2020-01-01":"2020-01-05"]) == pytest.approx(expected)


def test_without_kind_a_source_still_adds_up_as_before(tmp_path):
    episode = _level_episode(tmp_path, kind=None)
    assert _at(episode, "T", "2019-01-01") == pytest.approx(18.0 / 365)   # ברירת המחדל: הסכום מתפזר ומצטבר
    assert _at(episode, "T", "2020-12-31") == pytest.approx(37.0)
    same = _level_episode(tmp_path / "amount", kind="amount")
    assert np.array_equal(same.cum, episode.cum)


def test_kind_is_validated(tmp_path):
    from dataviz.config import ConfigError
    with pytest.raises(ConfigError, match="kind"):
        _level_episode(tmp_path, kind="levels")
    with pytest.raises(ConfigError, match="kind"):
        _level_episode(tmp_path / "count", value="count")
    from dataviz import schema
    kind = schema.json_schema()["properties"]["sources"]["items"]["properties"]["kind"]
    assert kind["enum"] == ["amount", "level"] and kind["default"] == "amount" and kind["description"]


def _axis_tops(episode, count=6):
    """(ראש ציר ה-y, השנתות המסומנות עד אליו, הערכים בפריים, xmax, x) בפריימים הראשונים של הגרף,
    בכל פריים 24 עד הכניסה של K, ובכניסה עצמה."""
    from dataviz.charts import make_chart
    from dataviz.plan import build_plan
    from dataviz.render import chart_context
    episode.config["ranking"]["axis_min"] = 1.0     # כמו בפרק הכנרת: הציר לא מתחיל מ-60
    plan = [f for f in build_plan(episode, "full") if f["k"] == "main"]
    entry = episode.start_idx[episode.entities.index("K")]
    frames = plan[:count] + [f for f in plan[count::24] if f["x"] < entry] + [next(f for f in plan if f["x"] >= entry)]
    chart = make_chart(chart_context(episode))
    tops = []
    try:
        for f in frames:
            chart.render(f)
            top = chart.ax.get_ylim()[1]
            tops.append((top, [t for t in chart.ax.get_yticks() if t <= top + 1e-9], [v for _e, v, _p in f["bars"]], f["xmax"], f["x"]))
    finally:
        chart.close()
    return tops


def test_with_a_level_source_the_axis_top_is_a_labeled_tick_from_the_first_chart_frame(tmp_path):
    # 18.10.2026: קו של רמה (18) לא יושב מעל קו הרשת האחרון שיש לו מספר (15) - ראש הציר הוא שנתה מסומנת (20)
    episode = _level_episode(tmp_path)
    tops = _axis_tops(episode)
    for top, ticks, values, _xmax, _x in tops:
        assert top == pytest.approx(max(ticks))
        assert all(v <= top for v in values)
    # ובלי מדרגה זמן קצר אחרי ההתחלה (20 ואז 25): עד שנכנסת ישות חדשה הציר לא זז
    entry = episode.start_idx[episode.entities.index("K")]
    assert len({top for top, _t, _v, _m, x in tops if x < entry}) == 1


def test_without_a_level_source_the_axis_top_stays_the_smoothed_value(tmp_path):
    for top, _ticks, _values, xmax, _x in _axis_tops(_level_episode(tmp_path, kind=None)):
        assert top == pytest.approx(xmax)
