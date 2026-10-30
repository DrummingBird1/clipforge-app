# tests/dataviz/test_dataviz_fix_reading.py
#
# 23.10.2026, סריקת הבאגים - מנה 2a (קריאת נתונים ותאריכים במנוע). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ק1 תא ריק נקרא 0; ק2 decimal / thousands הלכו לאיבוד כשבעמודה "-" או ".."; ק3 DD/MM/YYYY נקרא חודש-ראשון ושורות
# נזרקו; ג8 period: year קרס על תא ריק / שורת הערה / תאריך מלא; ג9 זמן מספרי ביום / חודש נחת ב-1970; ב8 תאריך ותאריך-שעה
# באותה עמודה; נ4 קיצורי חודשים בעברית, ומקור ‎.tsv מכתובת שנקרא עם פסיק.
import hashlib
import os

import pytest
import yaml

from dataviz.episode import load_episode


def _episode(root, files, sources, **extra):
    folder = os.path.join(str(root), "ep")
    os.makedirs(folder, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "בדיקה", "chart": "line_race", "sources": sources, **extra}, f, allow_unicode=True)
    return load_episode(folder)


def _src(path="a.csv", period="day", **extra):
    return {"path": path, "time": {"column": "date", "period": period}, "value": {"column": "v"}, "entity": {"column": "e"}, **extra}


def _column(episode, name="A"):
    return [float(x) for x in episode.cum[:, list(map(str, episode.entities)).index(name)]]


def _day(episode, date):
    return list(episode.dates.strftime("%Y-%m-%d")).index(date)


# ---------- ק1: תא ריק ----------
def test_an_empty_cell_in_a_level_series_is_unknown_not_zero(tmp_path):
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n2020-01-01,A,20\n2020-01-02,A,\n2020-01-03,A,22\n"}, [_src(kind="level")])
    assert _column(episode) == [20.0, 21.0, 22.0]                               # קודם: [20, 0, 22]


def test_empty_year_columns_in_a_wide_table_are_filled(tmp_path):
    files = {"w.csv": "e,2000,2001,2002,2003\nA,10,,,40\n"}
    spec = {"path": "w.csv", "wide": True, "time": {"column": "<years-as-columns>", "period": "year"}, "value": {"column": "<cells>"},
            "entity": {"column": "e"}, "kind": "level", "fill": "linear"}
    episode = _episode(tmp_path, files, [spec])
    assert round(_column(episode)[_day(episode, "2001-12-31")]) == 20 and round(_column(episode)[_day(episode, "2002-12-31")]) == 30   # קודם: 0


def test_a_daily_gap_with_an_empty_cell_is_interpolated(tmp_path):
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n2020-01-01,A,10\n2020-01-02,A,\n2020-01-03,A,30\n"}, [_src(missing="interpolate")])
    assert _column(episode) == [10.0, 30.0, 60.0]                               # קודם: 10, 10, 40 (היום הריק = 0)


# ---------- ק2: decimal / thousands עם ממלא מקום ----------
def test_decimal_comma_survives_a_dash_cell(tmp_path):
    files = {"a.csv": "date;e;v\n2020-01-01;A;1,5\n2020-01-02;A;-\n2020-01-03;A;2,25\n"}
    assert _column(_episode(tmp_path, files, [_src(sep=";", decimal=",")]))[-1] == 3.75   # קודם: 0


def test_thousands_dot_survives_a_dots_cell(tmp_path):
    files = {"a.csv": "date;e;v\n2020-01-01;A;1.234\n2020-01-02;A;..\n2020-01-03;A;2.500\n"}
    assert _column(_episode(tmp_path, files, [_src(sep=";", thousands=".")]))[-1] == 3734.0   # קודם: 3.734


# ---------- ק3: DD/MM/YYYY ----------
def test_israeli_day_first_dates_are_read_day_first(tmp_path):
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n01/01/2020,A,1\n02/01/2020,A,1\n15/01/2020,A,1\n31/01/2020,A,1\n"}, [_src()])
    assert _column(episode)[-1] == 4.0                                          # קודם: 2 (15/01 ו-31/01 נזרקו)
    assert (str(episode.dates[0].date()), str(episode.dates[-1].date())) == ("2020-01-01", "2020-01-31")


def test_monthly_day_first_dates_keep_their_months(tmp_path):
    rows = "".join(f"01/{m:02d}/2021,A,1\n" for m in range(1, 13))
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n" + rows}, [_src(period="month")])
    assert _column(episode)[-1] == pytest.approx(12.0) and str(episode.dates[-1].date()) == "2021-12-31"   # קודם: כולם בינואר


# ---------- ג8: period: year ----------
@pytest.mark.parametrize("bad", ["", "Source: CBS", "2021-06-30"])
def test_a_year_column_with_an_odd_row_does_not_crash(tmp_path, bad):
    episode = _episode(tmp_path, {"a.csv": f"date,e,v\n2019,A,5\n{bad},A,3\n2020,A,1\n"}, [_src(period="year")])
    expected = 9.0 if bad == "2021-06-30" else 6.0                              # תאריך מלא = השנה שלו; השאר נזרקים
    assert _column(episode)[-1] == pytest.approx(expected)                                     # קודם: IntCastingNaNError / ValueError


# ---------- ג9: זמן מספרי ----------
def test_numeric_years_and_yyyymm_are_dates_not_1970(tmp_path):
    years = _episode(tmp_path / "y", {"a.csv": "date,e,v\n2019,A,1\n2020,A,2\n"}, [_src()])
    assert str(years.dates[0].date()) == "2019-01-01"                           # קודם: 1970-01-01
    months = _episode(tmp_path / "m", {"a.csv": "date,e,v\n202001,A,1\n202003,A,2\n"}, [_src(period="month")])
    assert (str(months.dates[0].date()), str(months.dates[-1].date())) == ("2020-01-01", "2020-03-31")


def test_month_dot_year_text_is_read(tmp_path):
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n01.2020,A,1\n02.2020,A,2\nהערה,A,9\n"}, [_src(period="month")])
    assert (str(episode.dates[0].date()), str(episode.dates[-1].date())) == ("2020-01-01", "2020-02-29")   # קודם: 0001-01-01


# ---------- ב8: תאריך ותאריך-שעה באותה עמודה ----------
def test_dates_and_date_times_mixed_in_one_column(tmp_path):
    files = {"a.csv": "date,e,v\n2020-01-05,A,1\n2020-01-06 10:00:00,A,1\n2020-01-07T08:00,A,1\n"}
    assert _column(_episode(tmp_path, files, [_src()]))[-1] == 3.0              # קודם: 1


# ---------- נ4 ----------
def test_hebrew_month_spellings_and_abbreviations(tmp_path):
    files = {"a.csv": "date,e,v\nינו׳ 2022,A,1\nפבר' 2022,A,1\nמארס 2022,A,1\nאפר. 2022,A,1\n"}
    episode = _episode(tmp_path, files, [_src(period="month")])
    assert _column(episode)[-1] == pytest.approx(4.0) and str(episode.dates[-1].date()) == "2022-04-30"


def test_a_tsv_url_source_is_read_with_tabs(tmp_path):
    url = "https://example.com/data.tsv"
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".csv")).write_text("date\te\tv\n2020-01-01\tA\t3\n", encoding="utf-8")
    spec = {"url": url, "time": {"column": "date"}, "value": {"column": "v"}, "entity": {"column": "e"}}
    assert _column(_episode(tmp_path, {}, [spec], data={"cache_dir": str(cache)}))[-1] == 3.0   # קודם: KeyError 'date'
