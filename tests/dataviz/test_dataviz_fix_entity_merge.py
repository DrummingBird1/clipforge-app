# tests/dataviz/test_dataviz_fix_entity_merge.py
#
# 23.10.2026, סריקת הבאגים - ק4 (החלטת המשתמש): אותה ישות בשני מקורות חוברה לסכום - גם ברמות (20 + 22 = 44 במקום 22)
# וגם בשני צירים (אוכלוסייה + תמ"ג = קו אחד). עכשיו: בלי חפיפה בזמן - סדרה אחת לפי הזמן (ברמה ובכמות); עם חפיפה - ישות
# לכל מקור עם סיומת ("ISR (gdp)") ואזהרה ב"לפני רינדור". אף מקרה לא מתחבר לסכום. תקופה משותפת אחת עם אותו ערך = תפר.
import os

import numpy as np
import pytest
import yaml

from dataviz.episode import load_episode
from dataviz.smart import draft
from dataviz.web import data as dvdata


def _write(folder, files, sources):
    os.makedirs(folder, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "בדיקה", "sources": sources}, f, allow_unicode=True, sort_keys=False)
    return str(folder)


def _src(path, period="day", **extra):
    return {"path": path, "time": {"column": "t", "period": period}, "value": {"column": "v"}, "entity": {"column": "e"}, **extra}


def _final(episode):
    return {e: float(episode.cum[-1, i]) for i, e in enumerate(episode.entities)}


def _rows(rows):
    return "t,e,v\n" + "\n".join(f"{t},{e},{v}" for t, e, v in rows)


# ---------- בלי חפיפה: סדרה אחת לפי הזמן ----------
def test_two_level_sources_without_overlap_continue_one_line(tmp_path):
    folder = _write(tmp_path / "ep", {"a.csv": _rows([("2020-01-01", "A", 20), ("2020-01-02", "A", 21)]),
                                      "b.csv": _rows([("2020-01-03", "A", 22), ("2020-01-04", "A", 23)])},
                    [_src("a.csv", kind="level"), _src("b.csv", kind="level")])
    episode = load_episode(folder)
    assert episode.entities == ["A"] and episode.levels == ["A"]
    assert list(episode.cum[:, 0]) == [20, 21, 22, 23]                          # קודם: 20, 21, 43, 44 (סכום)


YEARS_A = [(str(y), "A", 100 + y % 7) for y in range(2000, 2011)]
YEARS_B = [(str(y), "A", 100 + y % 7) for y in range(2010, 2021)]               # 2010 בשני הקבצים, אותו ערך - תפר


@pytest.mark.parametrize("kind", ["level", "amount"])
def test_files_split_by_time_are_exactly_one_file(tmp_path, kind):
    extra = {"kind": "level"} if kind == "level" else {}
    split = load_episode(_write(tmp_path / "split", {"a.csv": _rows(YEARS_A), "b.csv": _rows(YEARS_B)},
                                [_src("a.csv", "year", **extra), _src("b.csv", "year", **extra)]))
    whole = load_episode(_write(tmp_path / "whole", {"all.csv": _rows(YEARS_A + YEARS_B[1:])}, [_src("all.csv", "year", **extra)]))
    assert split.entities == whole.entities == ["A"]
    assert np.array_equal(split.cum, whole.cum)                                 # קודם: 2010 פעמיים, וברמה - סכום של שני קווים


def test_a_yearly_level_followed_by_a_monthly_one_joins_at_the_border(tmp_path):
    folder = _write(tmp_path / "ep", {"a.csv": _rows([("2018", "A", 10), ("2019", "A", 12)]),
                                      "b.csv": _rows([("2020-01", "A", 13), ("2020-02", "A", 14)])},
                    [_src("a.csv", "year", kind="level"), _src("b.csv", "month", kind="level")])
    episode = load_episode(folder)
    levels = dict(zip(episode.dates.strftime("%Y-%m-%d"), episode.cum[:, 0]))
    assert episode.entities == ["A"]
    assert levels["2019-12-31"] == pytest.approx(12) and levels["2020-01-31"] == pytest.approx(13) and levels["2020-02-29"] == pytest.approx(14)


# ---------- חפיפה: ישות לכל מקור, עם סיומת ואזהרה ----------
def test_overlapping_level_sources_get_a_suffix_and_a_warning(tmp_path):
    folder = _write(tmp_path / "ep", {"a.csv": _rows([("2020-01-01", "A", 20), ("2020-01-02", "A", 21)]),
                                      "b.csv": _rows([("2020-01-02", "A", 30), ("2020-01-03", "A", 31)])},
                    [_src("a.csv", kind="level"), _src("b.csv", kind="level", legend="מדידה שנייה")])
    episode = load_episode(folder)
    assert _final(episode) == {"A (a)": 21, "A (מדידה שנייה)": 31}               # קודם: ישות אחת, 52
    assert set(episode.levels) == {"A (a)", "A (מדידה שנייה)"}
    warning = [f for f in dvdata.data_check(folder, {})["findings"] if f["kind"] == "shared_entity"]
    assert len(warning) == 1 and warning[0]["level"] == "warn"
    assert all(part in warning[0]["text"] for part in ("A", "a", "מדידה שנייה"))


def test_the_same_country_on_two_axes_is_two_lines(tmp_path):
    years = range(2000, 2005)
    folder = _write(tmp_path / "ep", {"population.csv": _rows([(y, "ISR", 6000 + y) for y in years]),
                                      "gdp.csv": _rows([(y, "ISR", 40000 + y) for y in years])},
                    [_src("population.csv", "year", kind="level"), _src("gdp.csv", "year", kind="level", axis="right")])
    episode = load_episode(folder)
    assert _final(episode) == {"ISR (gdp)": 42004, "ISR (population)": 8004}    # קודם: ISR אחת, 50008
    assert episode.right_axis == ["ISR (gdp)"]


def test_one_shared_period_with_a_different_value_is_an_overlap(tmp_path):
    folder = _write(tmp_path / "ep", {"a.csv": _rows(YEARS_A), "b.csv": _rows([("2010", "A", 999)] + YEARS_B[1:])},
                    [_src("a.csv", "year"), _src("b.csv", "year")])
    assert sorted(load_episode(folder).entities) == ["A (a)", "A (b)"]


def test_entities_in_one_source_only_are_untouched(tmp_path):
    folder = _write(tmp_path / "ep", {"a.csv": _rows([("2020-01-01", "A", 1), ("2020-01-02", "B", 2)]),
                                      "b.csv": _rows([("2020-01-01", "C", 3), ("2020-01-03", "C", 4)])},
                    [_src("a.csv"), _src("b.csv")])
    episode = load_episode(folder)
    assert _final(episode) == {"A": 1, "B": 2, "C": 7}
    assert not [f for f in dvdata.data_check(folder, {})["findings"] if f["kind"] == "shared_entity"]


# ---------- טיוטת האשף: אותו כלל ----------
COUNTRIES = ("ישראל", "יוון")


def _country_file(column, years):
    return f"year,entity,{column}\n" + "\n".join(f"{y},{e},{y - 1990 + k * 100}" for y in years for k, e in enumerate(COUNTRIES))


@pytest.mark.parametrize("files,layout,expected,right", [
    # merge (אותן יחידות) בלי חפיפה - שני קבצים של אותה רמה לפי תקופה: סדרה אחת, שממשיכה מהערך האחרון
    ({"price_usd.csv": ("price_usd", range(2000, 2006)), "price_late_usd.csv": ("price_level_usd", range(2006, 2011))},
     "merge", ["יוון", "ישראל"], []),
    # merge עם חפיפה - יצוא ויבוא באותן שנים: ישות לכל קובץ
    ({"exports_usd.csv": ("exports_usd", range(2000, 2006)), "imports_usd.csv": ("imports_usd", range(2000, 2006))},
     "merge", ["יוון (exports_usd)", "יוון (imports_usd)", "ישראל (exports_usd)", "ישראל (imports_usd)"], []),
    # dual (יחידות שונות) - אוכלוסייה ותמ"ג: ישות לכל קובץ, התמ"ג על הציר הימני
    ({"population.csv": ("population", range(2000, 2006)), "gdp_usd.csv": ("gdp_usd", range(2000, 2006))},
     "dual", None, None),
])
def test_a_wizard_draft_with_the_same_entities_in_two_files_follows_the_rule(tmp_path, files, layout, expected, right):
    texts = {name: _country_file(column, years) for name, (column, years) in files.items()}
    folder = tmp_path / "ep"
    _write(folder, texts, [])
    plan = draft.analyze(str(folder))["plan"]
    assert plan["layout"] == layout
    _write(folder, texts, plan["sources"])
    episode = load_episode(str(folder))
    if layout == "dual":
        names = [s["path"].rsplit(".", 1)[0] for s in plan["sources"]]
        expected = sorted(f"{e} ({n})" for e in COUNTRIES for n in names)
        right = sorted(f"{e} ({names[1]})" for e in COUNTRIES)
    assert sorted(episode.entities) == expected                                 # קודם: שתי ישויות - סכום של שני הקבצים
    assert sorted(episode.right_axis) == right
    if expected == ["יוון", "ישראל"]:
        assert _final(episode) == {"ישראל": 20, "יוון": 120}                    # הערך של 2010, לא סכום של שני הקווים
