# tests/dataviz/test_dataviz_engine_periods.py
#
# 20.10.2026: המנוע קורא עכשיו גם רבעונים ("2020-Q3", "Q3 2020", "רבעון 3 2020" - period: quarter), חודשים בעברית
# ("ינואר 2022"), טבלה רחבה (השנים ככותרות - wide: true) ומוציא שורת סך (exclude_entities). פרקים קיימים לא משתנים -
# כל אלה רק כשהמקור מבקש, או בערכים שקודם לא נקראו בכלל.
import pandas as pd
import yaml

from dataviz.episode import load_episode
from dataviz.sources import read_table
from dataviz.sources.spread import period_days


def _cum(episode, entity):
    """המצטבר של ישות לפי תאריך (episode.daily הוא מערך: יום x ישות)."""
    col = [str(e) for e in episode.entities].index(entity)
    return pd.Series(episode.daily[:, col].cumsum(), index=episode.dates)


def _folder(tmp_path, name, text, source, kind=None):
    folder = tmp_path / name
    folder.mkdir()
    (folder / "data.csv").write_text(text.strip() + "\n", encoding="utf-8")
    spec = {"path": "data.csv", **source}
    if kind:
        spec["kind"] = kind
    (folder / "config.yaml").write_text(yaml.safe_dump({"title": name, "sources": [spec]}, allow_unicode=True), encoding="utf-8")
    return str(folder)


def test_quarters():
    assert len(period_days(pd.Timestamp("2020-07-01"), "quarter")) == 92
    spec = {"path": "x", "time": {"column": "q", "period": "quarter"}, "entity": {"column": "e"}, "value": {"column": "v"}}
    table = pd.DataFrame({"q": ["2020-Q3", "Q4 2020", "רבעון 1 2021"], "e": ["a", "a", "a"], "v": [1, 2, 3]})
    import dataviz.sources as sources
    original = sources.read_raw
    sources.read_raw = lambda spec, base: table
    try:
        result = read_table(spec, "")
    finally:
        sources.read_raw = original
    assert result["time"].dt.strftime("%Y-%m-%d").tolist() == ["2020-07-01", "2020-10-01", "2021-01-01"]


def test_a_quarterly_level_episode_loads(tmp_path):
    folder = _folder(tmp_path, "q", "quarter,sector,output_index\n2020-Q1,a,100\n2020-Q2,a,104\n2020-Q3,a,102\n2020-Q4,a,110",
                     {"time": {"column": "quarter", "period": "quarter"}, "entity": {"column": "sector"}, "value": {"column": "output_index"}},
                     kind="level")
    episode = load_episode(folder)
    cum = _cum(episode, "a")
    assert round(float(cum["2020-06-30"]), 1) == 104.0 and round(float(cum.iloc[-1]), 1) == 110.0


def test_hebrew_month_names(tmp_path):
    folder = _folder(tmp_path, "he", "חודש,תחנה,משקעים\nינואר 2022,ירושלים,90\nפברואר 2022,ירושלים,60\nמרץ 2022,ירושלים,30",
                     {"time": {"column": "חודש", "period": "month"}, "entity": {"column": "תחנה"}, "value": {"column": "משקעים"}})
    episode = load_episode(folder)
    assert episode.dates[0] == pd.Timestamp("2022-01-01") and episode.dates[-1] == pd.Timestamp("2022-03-31")
    assert round(float(_cum(episode, "ירושלים").iloc[-1])) == 180


def test_a_wide_table_and_a_totals_row(tmp_path):
    folder = _folder(tmp_path, "wide", "city,2015,2016,2017\nירושלים,865,880,896\nחיפה,279,284,290\nTotal,1144,1164,1186",
                     {"wide": True, "time": {"column": "<years-as-columns>", "period": "year"}, "entity": {"column": "city"},
                      "value": {"column": "<cells>"}, "exclude_entities": ["Total"]}, kind="level")
    episode = load_episode(folder)
    assert sorted(map(str, episode.entities)) == ["חיפה", "ירושלים"]                  # בלי שורת הסך
    assert round(float(_cum(episode, "ירושלים").iloc[-1])) == 896


def test_csv_options_fiscal_years_and_json_records(tmp_path):
    folder = tmp_path / "opts"
    folder.mkdir()
    (folder / "fuel.csv").write_text("date;fuel;price\n2022-01-03;Super;1,722\n2022-01-10;Super;1,743\n", encoding="utf-8")
    (folder / "titled.csv").write_text("נתוני תעסוקה,,\nשנה,מחוז,מועסקים\n2012,ירושלים,5\n2013,ירושלים,6\n", encoding="utf-8")
    (folder / "budget.csv").write_text("fiscal_year,ministry,budget\n2014/15,Education,69.3\n2015/16,Education,70.1\n", encoding="utf-8")
    (folder / "nested.json").write_text('{"data": [{"month": "2021-01", "app": "Waze", "downloads": 5}, {"month": "2021-02", "app": "Waze", "downloads": 7}]}',
                                        encoding="utf-8")
    fuel = read_table({"path": "fuel.csv", "sep": ";", "decimal": ",", "time": {"column": "date", "period": "day"},
                       "entity": {"column": "fuel"}, "value": {"column": "price"}}, str(folder))
    assert fuel["value"].tolist() == [1.722, 1.743]
    titled = read_table({"path": "titled.csv", "header_row": 1, "time": {"column": "שנה", "period": "year"},
                         "entity": {"column": "מחוז"}, "value": {"column": "מועסקים"}}, str(folder))
    assert titled["value"].tolist() == [5.0, 6.0]
    budget = read_table({"path": "budget.csv", "time": {"column": "fiscal_year", "period": "year"}, "entity": {"column": "ministry"},
                         "value": {"column": "budget"}}, str(folder))
    assert budget["time"].dt.year.tolist() == [2014, 2015]                     # שנת כספים = השנה שבה מתחילה
    nested = read_table({"path": "nested.json", "records": "data", "time": {"column": "month", "period": "month"},
                         "entity": {"column": "app"}, "value": {"column": "downloads"}}, str(folder))
    assert nested["value"].tolist() == [5.0, 7.0]


def test_numbers_with_symbols_dotted_dates_units_row_and_entity_columns(tmp_path):
    from dataviz.sources import normalize_time_text, to_numbers
    assert to_numbers(pd.Series(["₪4,688,143", "$1.2M", "12%", "-3.5", "abc"])).tolist()[:4] == [4688143.0, 1200000.0, 12.0, -3.5]
    assert to_numbers(pd.Series([1, 2.5])).tolist() == [1.0, 2.5]                  # מספרים רגילים - כמו קודם
    assert normalize_time_text("14.04.23") == "2023-04-14" and normalize_time_text("2023-04-14") == "2023-04-14"
    folder = tmp_path / "v3"
    folder.mkdir()
    (folder / "energy.csv").write_text("year,sector,consumption\n,,GWh\n2010,Residential,20572\n2011,Residential,21000\n", encoding="utf-8")
    (folder / "fx.csv").write_text("month,USD,EUR,GBP\n2020-01,3.52,3.88,4.43\n2020-02,3.60,3.85,4.50\n", encoding="utf-8")
    energy = read_table({"path": "energy.csv", "skip_rows": [1], "time": {"column": "year", "period": "year"}, "entity": {"column": "sector"},
                         "value": {"column": "consumption"}}, str(folder))
    assert energy["value"].tolist() == [20572.0, 21000.0]                          # שורת היחידות לא נתון
    fx = read_table({"path": "fx.csv", "entity_columns": True, "time": {"column": "month", "period": "month"}, "entity": {"column": "<columns>"},
                     "value": {"column": "<cells>"}}, str(folder))
    assert sorted(set(fx["entity"])) == ["EUR", "GBP", "USD"] and len(fx) == 6
