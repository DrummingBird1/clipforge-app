# tests/dataviz/test_dataviz_sparse_fill.py
#
# 20.10.2026: נתונים דלילים (נקודה כל ~10 שנים, כמו מפקד) - fill לכל מקור: step (הערך הקודם עד הנקודה הבאה) או linear
# (קו ישר בין הנקודות), גם לכמות (שנה / חודש - התקופות החסרות מקבלות ערך ואז מתפזרות) וגם לרמה. בלי fill - כמו תמיד.
import os

import pandas as pd
import pytest

from tests.dataviz_helpers import write_episode

CENSUS = "year,entity,n\n1950,A,100\n1960,A,200\n1970,A,200\n"


def _episode(tmp_path, kind=None, fill=None):
    spec = {"path": "census.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "n"}, "entity": {"column": "entity"},
            **({"kind": kind} if kind else {}), **({"fill": fill} if fill else {})}
    folder = write_episode(tmp_path, overrides={"chart": "line_race", "sources": [spec]})
    with open(os.path.join(folder, "census.csv"), "w", encoding="utf-8") as f:
        f.write(CENSUS)
    from dataviz.episode import load_episode
    return load_episode(folder)


def _year_total(episode, year):
    """כמה נוסף בשנה (כמות) - לפי ההפרש במצטבר."""
    col = episode.entities.index("A")
    end = episode.cum[episode.dates.get_loc(pd.Timestamp(f"{year}-12-31")), col]
    before = episode.cum[episode.dates.get_loc(pd.Timestamp(f"{year - 1}-12-31")), col] if year > 1950 else 0.0
    return float(end - before)


def _level(episode, date):
    return float(episode.cum[episode.dates.get_loc(pd.Timestamp(date)), episode.entities.index("A")])


def test_an_amount_without_fill_is_empty_between_the_points(tmp_path):
    episode = _episode(tmp_path)
    assert _year_total(episode, 1955) == 0 and _year_total(episode, 1960) == pytest.approx(200)


def test_an_amount_with_steps_repeats_the_last_point_and_linear_draws_a_line(tmp_path):
    step = _episode(tmp_path / "s", fill="step")
    assert _year_total(step, 1955) == pytest.approx(100) and _year_total(step, 1960) == pytest.approx(200)
    linear = _episode(tmp_path / "l", fill="linear")
    assert _year_total(linear, 1955) == pytest.approx(150) and _year_total(linear, 1965) == pytest.approx(200)
    assert _year_total(linear, 1950) == pytest.approx(100)                              # הנקודות עצמן לא זזות


def test_a_level_holds_with_steps_and_draws_a_line_with_linear(tmp_path):
    step = _episode(tmp_path / "s", kind="level", fill="step")
    assert _level(step, "1955-07-01") == pytest.approx(100)                            # נשאר עד הנקודה הבאה
    linear = _episode(tmp_path / "l", kind="level", fill="linear")
    assert 100 < _level(linear, "1955-07-01") < 200
    plain = _episode(tmp_path / "p", kind="level")                                      # ברירת המחדל של רמה - קו ישר, כמו קודם
    assert _level(plain, "1955-07-01") == pytest.approx(_level(linear, "1955-07-01"))


def test_fill_is_validated_and_part_of_the_mapping(tmp_path):
    from dataviz.config import ConfigError
    from dataviz.web import episodes as de
    with pytest.raises(ConfigError, match="fill"):
        _episode(tmp_path, fill="cubic")
    assert de.source_spec("x.csv", de.clean_mapping({"time_column": "year", "fill": "step"}))["fill"] == "step"
    assert "fill" not in de.source_spec("x.csv", de.clean_mapping({"time_column": "year"}))
    with pytest.raises(de.EpisodeError):
        de.clean_mapping({"time_column": "year", "fill": "spline"})
