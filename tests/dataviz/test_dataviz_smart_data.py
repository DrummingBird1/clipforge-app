# tests/dataviz/test_dataviz_smart_data.py
#
# 20.10.2026: עורך הגרפים החכם, פריטים 4-6 - כמות או רמה (יחידות, מילים, התנהגות הערכים), איך קבצים משתלבים (אותן
# יחידות יחד, שתי יחידות - שני צירים, יותר - גרפים קטנים, רמה דלילה - השלמה) וניקוי אוטומטי (שמות זהים בכתיב שונה
# מתמזגים; שמות דומים / קפיצות / כפולות - רק הצעה לאישור).
import pandas as pd
import pytest

from dataviz.smart import draft
from dataviz.smart.kinds import guess_kind


def _csv(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")


@pytest.mark.parametrize("column,file_name,unit,kind", [
    ("immigrants", "immigrants_by_continent.csv", "עולים", "amount"),
    ("total_medals", "medals_per_games_year.csv", "מדליות", "amount"),
    ("exports_usd_million", "exports_annual.csv", "$ (מיליון)", "amount"),
    ("level_value", "temperature.csv", "°C", "level"),
    ("price_incl_vat_nis", "prices_year_end.csv", "₪", "level"),
    ("vehicles", "vehicle_fleet_by_type.csv", "כלי רכב", "level"),
    ("seats", "seats_by_election.csv", "מושבים", "level"),
])
def test_amount_or_level_from_units_and_words(column, file_name, unit, kind):
    result = guess_kind(column, file_name, {"label": unit})
    assert result["value"] == kind and result["reason"] and 0 < result["confidence"] <= 0.95


def test_value_behavior_decides_when_the_words_do_not():
    smooth = pd.DataFrame({"year": [2000, 2001, 2002, 2003] * 2, "entity": ["a"] * 4 + ["b"] * 4,
                           "x": [100, 101, 103, 102, 50, 51, 50, 52]})
    jumpy = smooth.assign(x=[5, 40, 2, 30, 1, 20, 3, 25])
    rising = smooth.assign(x=[1, 5, 9, 20, 2, 3, 8, 9])
    assert guess_kind("x", "", None, smooth, "year", "entity")["value"] == "level"
    assert guess_kind("x", "", None, jumpy, "year", "entity")["value"] == "amount"
    assert "כבר מצטבר" in guess_kind("x", "", None, rising, "year", "entity")["reason"]


def test_two_units_get_two_axes_and_a_sparse_level_gets_filled(tmp_path):
    _csv(tmp_path / "temperature.csv", "year,entity,level_value\n2000,טמפרטורה (°C),18\n2001,טמפרטורה (°C),19\n2002,טמפרטורה (°C),18.5")
    _csv(tmp_path / "lake.csv", "year,entity,level_value\n2000,מפלס (מטר),210\n2001,מפלס (מטר),211\n2002,מפלס (מטר),209")
    plan = draft.analyze(str(tmp_path))["plan"]
    assert plan["layout"] == "dual" and plan["sources"][1]["axis"] == "right"
    assert plan["y_axes"] == {"left": {"label": "מטר"}, "right": {"label": "°C"}}
    assert all(s["kind"] == "level" and isinstance(s["entity"], str) for s in plan["sources"])   # סדרה אחת בקובץ - השם שלה
    census = tmp_path / "census"
    census.mkdir()
    _csv(census / "city_population_levels.csv", "year,entity,population\n1948,חיפה,100\n1948,עכו,10\n1961,חיפה,180\n1961,עכו,25\n1972,חיפה,220\n1972,עכו,33")
    _csv(census / "seats_by_election.csv", "date,entity,seats\n1949-01-25,א,46\n1949-01-25,ב,19\n1951-07-30,א,45\n1951-07-30,ב,15\n1955-07-26,א,40\n1955-07-26,ב,9")
    fills = {s["path"]: s.get("fill") for s in draft.analyze(str(census))["plan"]["sources"]}
    assert fills == {"city_population_levels.csv": "linear", "seats_by_election.csv": "step"}


def test_same_units_go_together_and_three_units_get_small_multiples(tmp_path):
    for name, unit in (("a_usd.csv", "usd"), ("b_usd.csv", "usd")):
        _csv(tmp_path / name, f"year,entity,value_{unit}\n2000,{name[0]}1,1\n2000,{name[0]}2,2\n2001,{name[0]}1,3\n2001,{name[0]}2,4")
    assert draft.analyze(str(tmp_path))["plan"]["layout"] == "merge"
    _csv(tmp_path / "c_pct.csv", "year,entity,share_pct\n2000,c1,10\n2000,c2,20\n2001,c1,30\n2001,c2,40")
    _csv(tmp_path / "d_index.csv", "year,entity,price_index\n2000,d1,100\n2000,d2,101\n2001,d1,102\n2001,d2,103")
    assert draft.analyze(str(tmp_path))["plan"]["layout"] == "small_multiples"


def test_cleaning_merges_spellings_and_only_suggests_the_rest(tmp_path):
    _csv(tmp_path / "alarms_by_city.csv", """
month,entity,alarms
2023-01,תל-אביב,5
2023-02,תל אביב,6
2023-03,תל-אביב,4
2023-04,תל-אביב,5
2023-05,תל-אביב,6
2023-06,תל-אביב,400
2023-07,תל-אביב,5
2023-08,תל-אביב,4
2023-09,תל-אביב,5
2023-01,מעלות תרשיחא,7
2023-02,מעלות-תרשיחה,3
2023-02,מעלות-תרשיחה,3
2023-03,מעלות תרשיחא,8
2023-04,אוסטריה,1
2023-04,אוסטרליה,1""")
    result = draft.analyze(str(tmp_path))["cleaning"]
    assert result["aliases"] == {"תל אביב": "תל-אביב"}                          # זהים אחרי ניקוי כתיב - מוחל
    whats = [s["what"] for s in result["suggestions"]]
    assert "similar_names" in whats and "duplicates" in whats and "outlier" in whats   # רק הצעות
    assert all(s["needs_approval"] for s in result["suggestions"])
    similar = next(s for s in result["suggestions"] if s["what"] == "similar_names")
    assert set(similar["names"]) == {"מעלות תרשיחא", "מעלות-תרשיחה"}               # אוסטריה/אוסטרליה יחד באותו חודש - לא מוצע
    assert result["fixed"][0]["what"] == "merge_names"
