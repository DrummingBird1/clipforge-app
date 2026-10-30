# tests/dataviz/test_dataviz_focus.py
#
# 20.10.2026: מצב פוקוס - focus.entities בצבע מלא והשאר מעומעמות לפי focus.dim, ו-story.focus מחליף את הפוקוס מתאריך.
# בעמודות, בקווים ובדירוגים. בלי פוקוס - הפריים זהה פיקסל לפיקסל.
import numpy as np
import pytest

from tests.dataviz_helpers import write_episode

VIDEO = {"video": {"width": 640, "height": 400, "fps": 10, "dpi": 40}}


def _episode(tmp_path, chart="bar_race", **config):
    from dataviz.episode import load_episode
    return load_episode(write_episode(tmp_path, overrides={"chart": chart, **VIDEO, **config}))


def _main(episode):
    from dataviz.plan import build_plan
    return [f for f in build_plan(episode, "full") if f["k"] == "main"]


def _render(episode, frame):
    from dataviz.charts import make_chart
    from dataviz.render import chart_context
    chart = make_chart(chart_context(episode))
    try:
        return chart, np.frombuffer(chart.render(frame), dtype=np.uint8)
    finally:
        chart.close()


def test_focused_entities_stay_bright_and_the_rest_are_dimmed(tmp_path):
    episode = _episode(tmp_path, focus={"entities": [2023], "dim": 0.2})
    frame = _main(episode)[-1]
    assert frame["focus"] == ("2023",) and frame["focus_dim"] == 0.2
    chart, _ = _render(episode, frame)
    labels = {t.get_text(): t.get_alpha() for t in chart.ax.texts if t.get_text() in ("2023", "2020") and t.get_fontsize() == 12.5}   # שם העמודה (לא השנה ברקע)
    assert labels["2023"] == pytest.approx(1.0) and labels["2020"] == pytest.approx(0.2)


def test_the_focus_switches_on_a_date(tmp_path):
    episode = _episode(tmp_path, focus={"entities": [2020]}, story={"focus": [{"date": "2022-01-01", "entities": [2021, 2023]}]})
    frames = _main(episode)
    switch = episode.dates.get_loc(__import__("pandas").Timestamp("2022-01-01"))
    assert {f["focus"] for f in frames if f["x"] < switch} == {("2020",)}
    assert {f["focus"] for f in frames if f["x"] >= switch} == {("2021", "2023")}


@pytest.mark.parametrize("chart", ["bar_race", "line_race", "bump_race"])
def test_without_focus_nothing_changes(tmp_path, chart):
    plain = _episode(tmp_path / "a", chart)
    frame = _main(plain)[-1]
    assert "focus" not in frame
    _c1, before = _render(plain, frame)
    focused = _episode(tmp_path / "b", chart, focus={"entities": [], "dim": 0.3})   # רשימה ריקה = בלי פוקוס
    _c2, after = _render(focused, _main(focused)[-1])
    assert np.array_equal(before, after)


def test_focus_is_saved_and_validated(tmp_path):
    from dataviz.config import ConfigError
    from dataviz.web import episodes as de
    data = tmp_path / "data"
    write_episode(data / "dataviz_episodes", name="tiny")
    saved = de.update_override_fields(str(data), "tiny", {"focus.entities": [2023, "2020"], "focus.dim": 0.4,
                                                           "story.focus": [{"date": "2022-01-01", "entities": "2021, 2023"}]}, [])
    assert saved["focus"] == {"entities": ["2023", "2020"], "dim": 0.4}
    assert saved["story"]["focus"] == [{"date": "2022-01-01", "entities": ["2021", "2023"]}]
    with pytest.raises(ConfigError, match="focus.dim"):
        _episode(tmp_path / "bad", focus={"entities": [], "dim": 3})
