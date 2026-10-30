# tests/dataviz/test_dataviz_smart_scan.py
#
# 20.10.2026: עורך הגרפים החכם, פריטים 1-3 - סיווג הקבצים בתיקייה (סדרה / אירועים / משקלות / גולמי / בדיקה / מסמך),
# תפקיד כל עמודה (זמן + רזולוציה / ישות / ערך) עם ביטחון וסיבה, ויחידות משם העמודה / שמות הישויות / SOURCES.md.
import pandas as pd
import pytest

from dataviz.smart import columns as cols
from dataviz.smart.scan import scan_folder


def _csv(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")


@pytest.fixture
def folder(tmp_path):
    _csv(tmp_path / "prices_year_end.csv", """
year,iso3,entity,product_en,price_nis,delta_price_nis,survey_points
2019,ISR,לחם,bread,5.0,5.0,12
2019,ISR,חלב,milk,6.0,6.0,10
2020,ISR,לחם,bread,5.5,0.5,12
2020,ISR,חלב,milk,6.1,0.1,11
2021,ISR,לחם,bread,5.6,0.1,12
2021,ISR,חלב,milk,6.4,0.3,12""")
    _csv(tmp_path / "events.csv", "date,label\n2020-03-11,קורונה")
    _csv(tmp_path / "totals_check.csv", "year,sum_of_items,official_total,diff\n2019,11,11,0")
    _csv(tmp_path / "monthly_raw_UNUSED.csv", "month,value\n2019-01,1\n2019-02,2")
    _csv(tmp_path / "price_history_raw.csv", "update date,product,price\n24/05/2011,לחם,4\n01/09/2012,לחם,4.2")
    _csv(tmp_path / "survey_raw.csv", "year,entity,level\n2019,a,1\n2020,a,2\n2021,a,3")
    _csv(tmp_path / "spread_weights.csv", "month,weight\n1,0.1")
    (tmp_path / "SOURCES.md").write_text("# SOURCES\n- **Units:** shekels.\n- Engine data: `survey_raw.csv` (cleaned).\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("title: x\n", encoding="utf-8")
    return tmp_path


def test_every_file_gets_a_kind_with_a_reason(folder):
    files = {f["name"]: f for f in scan_folder(str(folder))["files"]}
    kinds = {name: f["kind"] for name, f in files.items()}
    assert kinds == {"prices_year_end.csv": "series", "survey_raw.csv": "series", "events.csv": "events",
                     "spread_weights.csv": "weights", "monthly_raw_UNUSED.csv": "raw_unused",
                     "price_history_raw.csv": "raw_unused", "totals_check.csv": "check", "SOURCES.md": "docs",
                     "config.yaml": "config"}
    assert files["survey_raw.csv"]["engine"] is True and "SOURCES.md" in files["survey_raw.csv"]["reason"]   # "raw" אבל המקור אומר שזה הנתונים
    assert all(f["reason"] and 0 < f["confidence"] <= 1 and f["label"] for f in files.values())


def test_column_roles_with_confidence(folder):
    roles = {f["name"]: f for f in scan_folder(str(folder))["files"]}["prices_year_end.csv"]["roles"]
    assert (roles["time"]["column"], roles["time"]["period"]) == ("year", "year")
    assert roles["entity"]["column"] == "entity"                     # עברית ושם entity - לא product_en, לא iso3
    assert roles["value"]["column"] == "price_nis"                   # הרמה, לא ההפרש delta_ ולא survey_points
    delta = next(v for v in roles["values"] if v["column"] == "delta_price_nis")
    assert delta["derived_from"] == "price_nis" and delta["score"] < roles["value"]["score"]
    assert all(roles[k]["reason"] and 0 < roles[k]["confidence"] < 1 for k in ("time", "entity", "value"))


@pytest.mark.parametrize("values,period", [
    (["1948", "1949", "1950"], "year"),
    (["2017-10-01", "2017-11-01", "2017-12-01"], "month"),
    (["2017-10", "2017-11", "2017-12"], "month"),
    (["1949-01-25", "1951-07-30", "1955-07-26"], "day"),
])
def test_time_resolution(values, period):
    df = pd.DataFrame({"when": values, "x": [1, 2, 3]})
    assert cols.time_column(df)["period"] == period
    assert cols.parse_times(pd.Series(["24/05/2011", "01/09/2012"])).dt.month.tolist() == [5, 9]


def test_an_empty_column_is_not_a_time():
    # 21.10.2026: עמודה ריקה לגמרי (window_start בפרק אמיתי) - ב-pandas 3 היא נשארת float אחרי astype(str), ו"מתיקייה" נפל
    # כשסרק את הפרקים הקיימים (find_series)
    assert cols.parse_times(pd.Series([None] * 5, dtype=float)).isna().all()
    df = pd.DataFrame({"year": [2008, 2009, 2010], "window_start": [None] * 3, "total": [1, 2, 3]})
    assert cols.time_column(df)["column"] == "year"


def test_a_single_series_file_keeps_its_named_entity():
    df = pd.DataFrame({"year": [2000, 2001, 2002], "entity": ["מפלס הכנרת (מטר)"] * 3, "level_value": [1.0, 2.0, 3.0]})
    assert cols.analyze(df)["entity"]["column"] == "entity"


@pytest.mark.parametrize("column,names,docs,label", [
    ("gdp_per_capita_usd", [], "", "$"),
    ("exports_usd_million", [], "", "$ (מיליון)"),
    ("price_incl_vat_nis", [], "", "₪"),
    ("level_value", ["טמפרטורה ממוצעת שנתית (°C, בית דגן)"], "", "°C"),
    ("level_value", ["מפלס הכנרת (מטר מתחת לפני הים)"], "", "מטר"),
    ("value", [], "- **Units:** index points (base 1993 = 100).", "נקודות מדד"),
    ("population_thousands", [], "", "תושבים (אלפים)"),
    ("value", [], "", ""),
])
def test_units_from_name_entities_and_sources(column, names, docs, label):
    unit = cols.unit_of(column, names, docs)
    assert unit["label"] == label and unit["reason"]


def test_v3_shapes(tmp_path):
    from dataviz.smart import draft
    (tmp_path / "revenue.csv").write_text('year,branch,revenue\n2015,A,"₪4,688,143"\n2015,B,"₪2,134,813"\n2016,A,"₪4,700,000"\n2016,B,"₪2,200,000"\n',
                                          encoding="utf-8")
    roles = {f["name"]: f for f in scan_folder(str(tmp_path))["files"]}["revenue.csv"]["roles"]
    assert roles["value"]["column"] == "revenue" and roles["unit"]["label"] == "₪" and "בתאים" in roles["unit"]["reason"]
    units = tmp_path / "units"
    units.mkdir()
    (units / "electricity.csv").write_text("year,sector,consumption\n,,GWh\n2010,A,20572\n2010,B,17789\n2011,A,21000\n2011,B,18000\n2012,A,21500\n2012,B,18300\n",
                                           encoding="utf-8")
    roles = scan_folder(str(units))["files"][0]["roles"]
    assert roles["unit"]["label"] == "GWh" and roles["kind"]["value"] == "amount" and roles["read"]["skip_rows"] == [1]
    readme = tmp_path / "readme"
    readme.mkdir()
    (readme / "README.md").write_text("The episode shows imports (imports_t).\n", encoding="utf-8")
    (readme / "cargo.csv").write_text("year,port,imports_t,exports_t\n2010,A,5,9\n2010,B,6,8\n2011,A,7,9\n2011,B,6,10\n", encoding="utf-8")
    assert {f["name"]: f for f in scan_folder(str(readme))["files"]}["cargo.csv"]["roles"]["value"]["column"] == "imports_t"
    mid = tmp_path / "mid"
    mid.mkdir()
    (mid / "levels.csv").write_text("date,site,height\n2019-01-15,a,1\n2019-02-15,a,2\n2019-03-15,a,3\n", encoding="utf-8")
    assert scan_folder(str(mid))["files"][0]["roles"]["time"]["period"] == "month"
    hebrew = tmp_path / "hebrew_events"
    hebrew.mkdir()
    (hebrew / "אירועים.csv").write_text("תאריך,אירוע\n14.04.23,חופשה\n26.05.23,פסטיבל\n", encoding="utf-8")
    (hebrew / "visits.csv").write_text("תאריך,עיר,מבקרים\n01.03.23,ירושלים,9\n01.04.23,ירושלים,10\n01.05.23,ירושלים,12\n", encoding="utf-8")
    kinds = {f["name"]: f["kind"] for f in scan_folder(str(hebrew))["files"]}
    assert kinds == {"אירועים.csv": "events", "visits.csv": "series"}
    fx = tmp_path / "fx"
    fx.mkdir()
    (fx / "ils_exchange_rates.csv").write_text("month,USD,EUR,GBP,JPY\n2020-01,3.52,3.88,4.43,0.03\n2020-02,3.60,3.85,4.50,0.03\n2020-03,3.61,3.94,4.57,0.03\n",
                                               encoding="utf-8")
    picked = draft.choices(str(fx))
    assert (picked["entity"], picked["value"], picked["unit"], picked["chart"]) == ("<columns>", "<cells>", "₪", "line_race")
