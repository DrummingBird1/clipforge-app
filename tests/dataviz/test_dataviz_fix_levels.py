# tests/dataviz/test_dataviz_fix_levels.py
#
# 23.10.2026, סריקת הבאגים - מנה 2b (רמות ומקורות במנוע). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ק5 רמה עם timeline.start מאוחר התחילה מ-0; ג7 missing: previous חזר על הערך האחרון עד סוף המקור; ג10 rolling עם רמה
# הציג 0; ג11 קובץ משקלות איבד סכומים או קרס; ב9 ישות עם סכום שלילי לא נכנסה למרוץ; ב10 ציר הסיום לא מוגבל ל-axis_min;
# ב11 הקצב לא ראה ירידות; נ1 כל רמה סומנה כקפיצה חשודה; נ2 שם חלופי מספרי יצר ישות כפולה; נ3 timeline לא תקין.
import os

import numpy as np
import pytest
import yaml

from dataviz.config import ConfigError
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.web import data as dd


def _write(root, files, sources, **extra):
    folder = os.path.join(str(root), "ep")
    os.makedirs(folder, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "בדיקה", "chart": "line_race", "sources": sources, **extra}, f, allow_unicode=True)
    return folder


def _episode(root, files, sources, **extra):
    return load_episode(_write(root, files, sources, **extra))


def _src(path="a.csv", period="day", **extra):
    return {"path": path, "time": {"column": "date", "period": period}, "value": {"column": "v"}, "entity": {"column": "e"}, **extra}


def _column(episode, name="A"):
    return episode.cum[:, list(map(str, episode.entities)).index(name)]


# ---------- ק5 ----------
def test_a_level_keeps_its_value_when_the_timeline_starts_later(tmp_path):
    rows = "".join(f"2020-{m:02d},A,{20 + m}\n" for m in range(1, 10))
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n" + rows}, [_src(period="month", kind="level")], timeline={"start": "2020-05-01"})
    values = _column(episode)
    assert 24 <= values[0] <= 25 and values[-1] == pytest.approx(29.0)        # קודם: 0.03 עד 5


# ---------- ג7 ----------
def test_missing_previous_stops_at_the_end_of_each_entity(tmp_path):
    rows = "".join(f"2020-01-{d:02d},A,10\n" for d in (1, 2, 3)) + "".join(f"2020-01-{d:02d},B,1\n" for d in range(1, 31))
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n" + rows}, [_src(missing="previous")])
    assert _column(episode)[-1] == pytest.approx(30.0)                          # קודם: 300


# ---------- ג10 ----------
def test_rolling_mode_shows_a_level_as_a_level(tmp_path):
    rows = "".join(f"2020-{m:02d},A,100\n" for m in range(1, 7))
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n" + rows}, [_src(period="month", kind="level")],
                       values={"mode": "rolling", "window_days": 30})
    values = _column(episode)
    assert values[40] == pytest.approx(100.0) and values[-1] == pytest.approx(100.0)   # קודם: 0


# ---------- ג11 ----------
@pytest.mark.parametrize("weights", [
    "year,month,total\n2020,1,0\n2020,2,0\n",                                                   # משקלות שסכומם 0
    "year,month,total,window_start,window_end\n2020,12,30,2020-12-25,2021-01-05\n",             # חלון שחוצה את סוף השנה
    "year,month,total\n2020,,5\n2020,3,5\n",                                                    # חודש ריק
])
def test_a_weights_file_never_loses_the_total_or_crashes(tmp_path, weights):
    spec = {"path": "annual.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "total"}, "entity": "A",
            "spread": {"per": "day", "weights": {"path": "w.csv"}}}
    episode = _episode(tmp_path, {"annual.csv": "year,total\n2020,100\n", "w.csv": weights}, [spec])
    assert _column(episode)[-1] == pytest.approx(100.0)                         # קודם: 0 / KeyError / ValueError


# ---------- ב9 ----------
def test_an_entity_with_a_negative_total_enters_the_race(tmp_path):
    rows = "".join(f"2020-01-{d:02d},A,-5\n2020-01-{d:02d},B,3\n" for d in range(1, 11))
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n" + rows}, [_src()])
    assert {str(e): int(i) for e, i in zip(episode.entities, episode.start_idx)} == {"A": 0, "B": 0}   # קודם: A=10 (אף פעם)


# ---------- ב10 ----------
def test_the_outro_axis_is_never_below_axis_min(tmp_path):
    episode = _episode(tmp_path, {"a.csv": "date,e,v\n2020-01-01,A,0\n2020-01-02,A,0\n"}, [_src(kind="level")])
    outro = [f for f in build_plan(episode, "test") if f["k"] == "outro"]
    assert outro and min(f["xmax"] for f in outro) >= float(episode.config["ranking"]["axis_min"])   # קודם: 0


# ---------- ב11 ----------
def test_a_sharp_drop_gets_frames_like_a_sharp_rise(tmp_path):
    def frames_at_the_jump(values):
        rows = "".join(f"2020-01-{d:02d},A,{v}\n" for d, v in zip(range(1, 32), values))
        episode = _episode(tmp_path / str(values[0]), {"a.csv": "date,e,v\n" + rows}, [_src(kind="level")])
        return sum(1 for f in build_plan(episode, "full") if f["k"] == "main" and 29.0 < f["x"] <= 30.0)
    drop, rise = frames_at_the_jump([1000] * 30 + [1]), frames_at_the_jump([1] * 30 + [1000])
    assert drop >= 0.5 * rise                                                   # קודם: ~2 פריימים מול מאות


# ---------- נ1 ----------
def test_levels_are_not_reported_as_suspicious_jumps(tmp_path):
    rows = "".join(f"2020-{m:02d}-01,A,{20 + m % 3}\n" for m in range(1, 13)) + "".join(f"2020-{m:02d}-01,B,{30 + m % 2}\n" for m in range(6, 13))
    folder = _write(tmp_path, {"a.csv": "date,e,v\n" + rows}, [_src(kind="level")])
    assert dd.cleaning_report(folder, {})["outliers"] == []                     # קודם: היום הראשון של כל רמה


# ---------- נ2 ----------
def test_a_numeric_alias_merges_with_the_year_entity(tmp_path):
    files = {"years.csv": "date,v\n2019-06-01,5\n2020-06-01,7\n", "x.csv": "date,e,v\n2020-07-01,x,1\n"}
    sources = [{"path": "years.csv", "time": {"column": "date"}, "value": {"column": "v"}}, _src("x.csv")]
    episode = _episode(tmp_path, files, sources, entities={"aliases": {"x": "2020"}})
    assert sorted(map(str, episode.entities)) == ["2019", "2020"]               # קודם: 2019, 2020, '2020'


# ---------- נ3 ----------
def test_a_bad_timeline_is_a_clear_error(tmp_path):
    files = {"a.csv": "date,e,v\n2020-01-01,A,1\n2020-01-05,A,1\n"}
    with pytest.raises(ConfigError):
        _episode(tmp_path / "bad", files, [_src()], timeline={"start": "not a date"})
    with pytest.raises(ConfigError):
        _episode(tmp_path / "order", files, [_src()], timeline={"start": "2020-02-01", "end": "2020-01-01"})
    with pytest.raises(ValueError, match="timeline.start"):
        _episode(tmp_path / "late", files, [_src()], timeline={"start": "2021-01-01"})   # קודם: argmax של רשימה ריקה
    assert np.all(np.isfinite(_episode(tmp_path / "ok", files, [_src()]).cum))
