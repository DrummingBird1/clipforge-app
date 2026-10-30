# tests/dataviz/test_dataviz_fix_audit.py - באגים שנמצאו בבדיקה הטכנית של 25.10.2026 (fuzz של המנוע על נתונים קיצוניים):
# מינוס שהתהפך בתווית עם שם בעברית, ערכים שליליים בעמודות, מספרים ענקיים, תיבת הסיום ושמות ישויות.
# בלי ffmpeg - רק תכנית ופריימים קטנים.
import os

import pytest
import yaml

from dataviz.charts import make_chart
from dataviz.charts.base import ltr_number
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.render import chart_context

SMALL = {"video": {"width": 640, "height": 400, "fps": 10, "dpi": 40}}


def daily_episode(root, rows, extra=None, source=None, name="ep"):
    """פרק עם קובץ אחד: date,entity,v (שורה לכל יום וישות)."""
    folder = os.path.join(str(root), name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "d.csv"), "w", encoding="utf-8") as f:
        f.write("date,entity,v\n" + "".join(f'{d},"{e}",{v}\n' for d, e, v in rows))
    src = {"path": "d.csv", "time": {"column": "date"}, "entity": {"column": "entity"}, "value": {"column": "v"}, **(source or {})}
    config = {"title": "בדיקה", "ranking": {"top_n": 5}, **SMALL, "sources": [src], **(extra or {})}
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return folder


def days(n=30):
    return ["2024-01-%02d" % d for d in range(1, n + 1)] if n <= 31 else [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]


def texts_of(chart_obj):
    found = []
    for artist in [*chart_obj.fig.texts, *[t for ax in chart_obj.fig.axes for t in ax.texts]]:
        found.append(artist.get_text())
    return found


def render_frame(folder, chart, kind="main"):
    """פריים מאמצע הקטע הראשי (kind="main") או הפריים האחרון בסיום (kind="outro")."""
    episode = load_episode(folder)
    plan = build_plan(episode, "test")
    picks = [f for f in plan if f["k"] == kind]
    chart_obj = make_chart(chart_context(episode, chart))
    try:
        chart_obj.render(picks[len(picks) // 2] if kind == "main" else picks[-1])
        return chart_obj, plan, texts_of(chart_obj)
    finally:
        chart_obj.close()


# ---------- 1. מינוס בתווית עם שם בעברית ----------
def test_ltr_number_marks_only_negative_numbers():
    assert ltr_number("-210.1") == "‎-210.1"
    assert ltr_number("-1,430 ▲2") == "‎-1,430 ▲2"
    assert ltr_number("210.1") == "210.1"      # חיובי - אותו טקסט בדיוק, אותם פיקסלים
    assert ltr_number("₪5") == "₪5"


@pytest.mark.parametrize("chart", ["line_race", "heatmap_race"])
def test_negative_level_label_keeps_the_minus_before_the_number(tmp_path, chart):
    """הכנרת: ‎-210.1 הוצג "210.1-" כי המינוס (תו ניטרלי) הלך עם כיוון השורה העברית."""
    rows = [(d, "כנרת", -209.5 - i * 0.01) for i, d in enumerate(days())] + [(d, "ים המלח", -430.2) for d in days()]
    folder = daily_episode(tmp_path, rows, source={"kind": "level"}, extra={"chart": chart})
    _, _, texts = render_frame(folder, chart)
    labels = [t for t in texts if "כנרת" in t and "-" in t]
    assert labels, texts
    assert all("‎-" in t for t in labels), labels


# ---------- 4. ערכים שליליים בעמודות ----------
def test_negative_bars_open_the_axis_to_the_left_and_are_drawn(tmp_path):
    """עד 25.10.2026 הציר התחיל תמיד ב-0 - עמודה שלילית לא צוירה, ונשארו רק שם ומספר."""
    rows = [(d, e, v) for d in days() for e, v in (("א", -10), ("ב", -4), ("ג", 2))]
    folder = daily_episode(tmp_path, rows, extra={"chart": "bar_race"})
    episode = load_episode(folder)
    plan = build_plan(episode, "test")
    main = [f for f in plan if f["k"] == "main"]
    chart_obj = make_chart(chart_context(episode, "bar_race"))
    try:
        chart_obj.render(main[-1])
        x0, x1 = chart_obj.ax.get_xlim()
        lowest = min(v for _, v, _ in main[-1]["bars"])
        assert lowest < 0 and x0 <= lowest < 0 < x1
        images = [im for im in chart_obj.ax.images if im.get_extent()[0] < 0]   # עמודה שנמשכת שמאלה מ-0
        assert len(images) == 2
    finally:
        chart_obj.close()


def test_positive_bars_keep_the_axis_at_zero(tmp_path):
    rows = [(d, e, v) for d in days() for e, v in (("א", 10), ("ב", 4))]
    episode = load_episode(daily_episode(tmp_path, rows, extra={"chart": "bar_race"}))
    chart_obj = make_chart(chart_context(episode, "bar_race"))
    try:
        chart_obj.render([f for f in build_plan(episode, "test") if f["k"] == "main"][-1])
        assert chart_obj.ax.get_xlim()[0] == 0
    finally:
        chart_obj.close()


# ---------- 5. מספרים ענקיים ----------
def test_huge_plain_numbers_are_written_compact():
    from dataviz.charts.base import NumberTicks, format_number
    assert format_number(1_830_000_000_000) == "1.8T"
    assert format_number(-2_500_000_000_000, {"style": "plain", "decimals": 0}) == "-2.5T"
    assert format_number(999_999_999_999) == "999,999,999,999"   # מתחת לטריליון - כמו קודם
    assert format_number(1_234_567, {"style": "plain"}) == "1,234,567"
    ticks = NumberTicks(None).format_ticks([0, 5e11, 1e12, 1.5e12])
    assert ticks == ["0", "500B", "1T", "1.5T"]     # כל השנתות באותו סגנון, לא 500,000,000,000 ליד 1T


# ---------- 6. תיבת הסיום מעל המספרים ----------
def test_outro_box_does_not_cover_the_bar_values(tmp_path):
    """חמש עמודות באורך מלא: התיבה בפינה הקבועה (ימין, 30% מלמטה) כיסתה את המספרים בקצה של שתיים מהן."""
    rows = [(d, e, i + 1) for i, d in enumerate(days(60)) for e in "אבגדהו"]
    folder = daily_episode(tmp_path, rows, extra={"chart": "bar_race"})
    episode = load_episode(folder)
    outro = [f for f in build_plan(episode, "test") if f["k"] == "outro"]
    chart_obj = make_chart(chart_context(episode, "bar_race"))
    try:
        chart_obj.render(outro[-1])
        renderer = chart_obj.fig.canvas.get_renderer()
        box_text = [t for t in chart_obj.ax.texts if t.get_bbox_patch() is not None][-1]
        box = box_text.get_bbox_patch().get_window_extent(renderer)
        values = [t.get_window_extent(renderer) for t in chart_obj.ax.texts if t.get_text().replace(",", "").isdigit()]
        assert values
        assert not any(box.overlaps(v) for v in values)
    finally:
        chart_obj.close()


# ---------- 7. שמות ישויות ----------
def test_entity_names_are_trimmed_so_spaced_copies_merge(tmp_path):
    """"  ישראל " ו-"ישראל" היו שתי ישויות נפרדות, והרווחים הזיזו את השם בתווית."""
    rows = [(d, "ישראל", 1) for d in days()] + [(d, "  ישראל ", 1) for d in days()] + [(d, "ירדן", 1) for d in days()]
    episode = load_episode(daily_episode(tmp_path, rows))
    assert sorted(map(str, episode.entities)) == ["ירדן", "ישראל"]


def test_emoji_font_is_the_last_fallback():
    """דגל ו-⚽ בשם ישות יצאו ריבועים ריקים: אין אותם באף גופן של הערכות."""
    from dataviz.themes import EMOJI_FONT, _emoji_font_installed, apply_rc, get_theme
    rc = {}
    theme = get_theme()
    apply_rc(theme, rc)
    assert rc["font.sans-serif"][:len(theme.fonts)] == list(theme.fonts)   # הגופנים של הערכה קודמים, באותו סדר
    if _emoji_font_installed():
        assert rc["font.sans-serif"][-1] == EMOJI_FONT
    else:
        assert EMOJI_FONT not in rc["font.sans-serif"]
