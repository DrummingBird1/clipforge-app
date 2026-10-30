# tests/test_dataviz_level_defaults.py
#
# 19.10.2026: ברירות מחדל לפי סוג הנתונים במקורות kind: level (טמפרטורה, מפלס) - אושרו ע"י המשתמש:
# ציר ה-y של line_race לא מתחיל מ-0 כשכל המקורות רמות, ספרה אחת אחרי הנקודה כשיש ברמות ערכים לא שלמים (אלא אם
# numbers.decimals נקבע), תיבת הסיום לא מכסה את הקווים, ורמה שהערך הראשון שלה 0 נכנסת ביום הראשון שלה.
# פרקים בלי רמות - בלי שינוי (וה-goldens ב-tests/data/dataviz_golden זהים).
import os


import numpy as np
import pandas as pd

from tests.dataviz_helpers import write_episode

VIDEO = {"video": {"width": 640, "height": 400, "fps": 10, "dpi": 40}}


def _episode(tmp_path, csv, kind="level", **config):
    source = {"path": "levels.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "level"},
              "entity": {"column": "entity"}, **({"kind": kind} if kind else {})}
    folder = write_episode(tmp_path, overrides={"chart": "line_race", **VIDEO, "sources": [source], **config})
    with open(os.path.join(folder, "levels.csv"), "w", encoding="utf-8") as f:
        f.write(csv)
    from dataviz.episode import load_episode
    return load_episode(folder)


def _chart(episode):
    from dataviz.charts import make_chart
    from dataviz.render import chart_context
    return make_chart(chart_context(episode))


def _main_frames(episode):
    from dataviz.plan import build_plan
    return [f for f in build_plan(episode, "full") if f["k"] == "main"]


TEMPERATURE = "year,entity,level\n2018,T,18.3\n2019,T,19.1\n2020,T,18.6\n2021,T,21.8\n"


def test_when_every_source_is_a_level_the_axis_does_not_start_at_zero(tmp_path):
    episode = _episode(tmp_path, TEMPERATURE)
    chart = _chart(episode)
    ranges = set()
    try:
        for frame in _main_frames(episode)[::40]:
            chart.render(frame)
            bottom, top = chart.ax.get_ylim()
            ticks = list(chart.ax.get_yticks())
            assert 0 < bottom <= 18.3 and 21.8 <= top < 30           # 18-22 לא נמעך מעל 0
            assert any(abs(t - bottom) < 1e-9 for t in ticks) and any(abs(t - top) < 1e-9 for t in ticks)   # עם מספר
            assert all(bottom <= v <= top for _e, v, _p in frame["bars"])
            ranges.add((bottom, top))
    finally:
        chart.close()
    assert len(ranges) == 1                                         # קו אחד לאורך כל הפרק - הציר לא זז


def test_with_one_amount_source_the_axis_still_starts_at_zero(tmp_path):
    folder = write_episode(tmp_path, overrides={"chart": "line_race", **VIDEO, "sources": [
        {"path": "levels.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "level"}, "entity": {"column": "entity"}, "kind": "level"},
        {"path": "amounts.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "n"}, "entity": "A"}]})
    with open(os.path.join(folder, "levels.csv"), "w", encoding="utf-8") as f:
        f.write(TEMPERATURE)
    with open(os.path.join(folder, "amounts.csv"), "w", encoding="utf-8") as f:
        f.write("year,n\n2018,5\n2019,7\n2020,9\n2021,4\n")
    from dataviz.episode import load_episode
    episode = load_episode(folder)
    chart = _chart(episode)
    try:
        chart.render(_main_frames(episode)[-1])
        assert chart.ax.get_ylim()[0] == 0
    finally:
        chart.close()


def test_fractional_levels_get_one_decimal_unless_decimals_is_set(tmp_path):
    chart = _chart(_episode(tmp_path / "a", TEMPERATURE))
    try:
        assert chart.fmt(21.799) == "21.8" and chart.fmt(212.199) == "212.2"
    finally:
        chart.close()
    chart = _chart(_episode(tmp_path / "b", TEMPERATURE, numbers={"decimals": 0}))   # המשתמש קבע - לא דורסים
    try:
        assert chart.fmt(21.799) == "22"
    finally:
        chart.close()
    chart = _chart(_episode(tmp_path / "c", "year,entity,level\n2018,T,18\n2019,T,19\n2020,T,20\n"))   # רמות שלמות
    try:
        assert chart.fmt(19.4) == "19"
    finally:
        chart.close()
    chart = _chart(_episode(tmp_path / "d", TEMPERATURE, kind=None))   # בלי רמות - כמו קודם
    try:
        assert chart.fmt(21.799) == "22"
    finally:
        chart.close()


def test_a_level_whose_first_value_is_zero_enters_on_its_first_day(tmp_path):
    episode = _episode(tmp_path, "year,entity,level\n2018,T,18.3\n2019,T,19.1\n2020,T,18.6\n2019,Z,0\n2020,Z,3\n2021,Z,5\n")
    z = episode.entities.index("Z")
    assert episode.dates[episode.start_idx[z]] == pd.Timestamp("2019-01-01")     # לא 2020, כשהערך כבר זז מ-0
    frames = _main_frames(episode)
    first = next(f for f in frames if f["x"] >= episode.start_idx[z])
    assert "Z" in [e for e, _v, _p in first["bars"]]


def test_the_end_box_moves_off_the_level_lines(tmp_path):
    # הקו גבוה בהתחלה (שמאל למעלה, איפה שתיבת הסיום יושבת) ונמוך בסוף
    csv = "year,entity,level\n2010,T,30\n2011,T,29.5\n2012,T,29\n2013,T,12\n2014,T,10.5\n2015,T,10\n"
    episode = _episode(tmp_path, csv, outro={"title": "המצב בסוף", "places": ["ראשון"]})
    from dataviz.plan import build_plan
    outro = [f for f in build_plan(episode, "full") if f["k"] not in ("intro", "main") and f.get("end_screen") is None][-1]
    chart = _chart(episode)
    try:
        chart.render(outro)
        renderer = chart.fig.canvas.get_renderer()
        box = next(t for t in chart.ax.texts if "המצב בסוף" in t.get_text()).get_bbox_patch().get_window_extent(renderer)
        xy = np.vstack([line.get_transform().transform(np.column_stack(line.get_data())) for line in chart.ax.lines if len(line.get_xdata())])
        inside = ((xy[:, 0] >= box.x0) & (xy[:, 0] <= box.x1) & (xy[:, 1] >= box.y0) & (xy[:, 1] <= box.y1)).sum()
        assert inside == 0
    finally:
        chart.close()


def test_six_note_lines_get_a_full_line_each(tmp_path):
    # 19.10.2026: 6 שורות הערה נדחסו לרווח של כ-0.014 מגובה הפריים (בין התחתית לציר הזמן) - עכשיו הגרף עולה
    from dataviz.charts.base import NOTE_STEP, TIMELINE_RECT
    notes = [f"הערה מספר {k}" for k in range(6)]
    chart = _chart(_episode(tmp_path / "six", TEMPERATURE, notes=notes))
    try:
        ys = [n.get_position()[1] for n in chart.notes]
        assert min(a - b for a, b in zip(ys, ys[1:])) >= NOTE_STEP - 1e-9
        assert min(ys) >= 0.0 and max(ys) < chart.tl.get_position().y0           # כולן בין התחתית לציר הזמן
    finally:
        chart.close()
    chart = _chart(_episode(tmp_path / "two", TEMPERATURE, notes=notes[:2]))      # שתי שורות - בדיוק כמו קודם
    try:
        assert abs(chart.tl.get_position().y0 - TIMELINE_RECT[1]) < 1e-9
    finally:
        chart.close()
