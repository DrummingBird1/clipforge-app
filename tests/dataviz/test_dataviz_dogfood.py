# tests/dataviz/test_dataviz_dogfood.py - סבב הייצוב (16.10.2026): מה שנמצא בהרצה אמיתית מקצה לקצה של עורך הגרפים
# (פרק אמיתי בסרטון מלא, Shorts, גרסה באנגלית וחבילת פרסום) - וטסט לכל תיקון:
#  * הכותרת על התמונה הממוזערת: בעברית מימין לשמאל (ב-Pillow בלי libraqm האותיות יצאו הפוכות) ונכנסת ברוחב
#    (כותרת ארוכה נחתכה בשני הצדדים) - utils/dataviz_thumbnail.py
#  * ⏸ / ⏩ / ▶ (עצירה עם הסבר, טיזר וההזמנה בסוף ה-Shorts) לא קיימים ב-Segoe UI - יצאו ריבועים ריקים
#  * ה-bundle הראשון של המסך נשאר עם לפחות 15K פנויים (המדריך, המפות והקריינות עברו ל-dataviz_pro)
# הממשק עצמו (טעינה כפולה של העורך, השוואה עם הטיוטה) - test_web_app_dataviz_dogfood_browser.py.
import json
import warnings


import numpy as np
import pytest
from PIL import Image

from dataviz.charts import make_chart
from dataviz.charts.base import SYMBOL_FONT, with_symbol_font
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.render import chart_context
from dataviz.shorts import build_shorts
from entrypoints.web import frontend_assembly as fa
from tests.dataviz_helpers import write_episode
from dataviz.web import publish as dp
from dataviz.web import thumbnail as dt

LONG_TITLE = "25 שנות ירי מעזה: איזו שנה הייתה הקשה ביותר?"


def _gray(tmp_path, size=(800, 450)):
    path = tmp_path / "frame.png"
    Image.new("RGB", size, (120, 130, 140)).save(path)
    return str(path)


def _title_columns(path, height=450):
    """עמודות הפיקסלים הלבנים (מילוי הכותרת) ברצועה התחתונה, מקובצות לרצפים: (רצפים, העמודה הראשונה, האחרונה)."""
    pixels = np.asarray(Image.open(path).convert("RGB")).astype(int)[int(height * 0.6):]
    cols = np.flatnonzero((pixels.min(axis=2) > 225).any(axis=0))
    assert len(cols), "לא צוירה כותרת"
    breaks = np.flatnonzero(np.diff(cols) > 1)
    starts = [cols[0]] + [cols[b + 1] for b in breaks]
    ends = [cols[b] for b in breaks] + [cols[-1]]
    return list(zip(starts, ends)), cols.min(), cols.max()


# ---------- התמונה הממוזערת ----------
def test_the_thumbnail_title_reads_right_to_left(tmp_path):
    out = str(tmp_path / "thumb.jpg")
    dt.draw_title(_gray(tmp_path), "1 שששש", out)
    runs, _, _ = _title_columns(out)
    gaps = [runs[i + 1][0] - runs[i][1] for i in range(len(runs) - 1)]
    space = int(np.argmax(gaps))                                       # הרווח בין "1" למילה
    # מימין לשמאל: "1" (תחילת המשפט) בצד ימין - רצף אחד; ארבע האותיות משמאל לרווח
    assert (space + 1, len(runs) - space - 1) == (4, 1), runs


def test_a_long_title_fits_inside_the_frame(tmp_path):
    out = str(tmp_path / "thumb.jpg")
    dt.draw_title(_gray(tmp_path), LONG_TITLE, out)
    _, first, last = _title_columns(out)
    margin = 800 * dt.MARGIN * 0.9
    assert first >= margin and last <= 800 - margin, (first, last)
    assert Image.open(out).size == (800, 450)


def test_a_long_title_breaks_into_two_lines_and_a_short_one_stays_on_one(tmp_path):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    fig = Figure(figsize=(14.4, 8.88), dpi=dt.DPI)
    renderer = FigureCanvasAgg(fig).get_renderer()
    lines, _ = dt._layout(fig, renderer, LONG_TITLE, 1440, 888)
    assert lines == ["25 שנות ירי מעזה: איזו", "שנה הייתה הקשה ביותר?"]
    lines, size = dt._layout(fig, renderer, "ירי מרצועת עזה לישראל", 1440, 888)
    assert lines == ["ירי מרצועת עזה לישראל"] and size == pytest.approx(max(36, 1440 // 14) * 72 / dt.DPI)


def test_the_publish_pack_and_the_candidates_use_the_dataviz_title(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(dt, "make_thumbnail", lambda video, out, **kw: calls.append(("thumb", kw["title_text"])) or open(out, "wb").close())
    video = tmp_path / "ep.mp4"
    video.write_bytes(b"video")
    package = dp.prepare_publish(str(video), {"title": "כותרת הפרק", "publish": {"approval": True}})
    assert calls == [("thumb", "כותרת הפרק")] and package["steps"]["thumbnail"] == "ok"
    monkeypatch.setattr(dt, "draw_title", lambda frame, title, out: calls.append(("candidate", title)) or open(out, "wb").close())
    sidecar = str(video)[:-4] + dp.SIDECAR_SUFFIX
    names = dp.thumbnail_candidates(sidecar, extract=lambda *a: open(a[2], "wb").close() or True, duration=10.0)
    assert len(names) == 3 and calls[1:] == [("candidate", "כותרת הפרק")] * 3


# ---------- סמלים בתוך הסרטון ----------
def test_the_symbol_font_comes_right_after_the_first_font():
    assert with_symbol_font(("Segoe UI", "Arial")) == ["Segoe UI", SYMBOL_FONT, "Arial"]
    assert with_symbol_font([SYMBOL_FONT, "Arial"]) == [SYMBOL_FONT, "Arial"]


def _has_symbol_font():
    from matplotlib import font_manager
    try:
        font_manager.findfont(font_manager.FontProperties(family=SYMBOL_FONT), fallback_to_default=False)
        return True
    except ValueError:
        return False


@pytest.mark.skipif(not _has_symbol_font(), reason="בלי Segoe UI Symbol (לא Windows)")
def test_pause_teaser_and_shorts_invite_draw_their_symbols(tmp_path):
    small = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}
    episode = load_episode(write_episode(tmp_path, overrides={**small, "story": {"pauses": [{"date": "2023-10-07", "text": "הקפיצה"}]},
                                                              "teaser": {"enabled": True, "seconds": 1, "label": "בהמשך"}}))
    plan = build_plan(episode, "full")
    frames = [next(f for f in plan if (f.get("hold") or {}).get("kind") == "pause"), next(f for f in plan if f.get("teaser"))]
    shorts = build_shorts(episode, plan)
    assert shorts and "▶" in shorts[0][-1]["hold"]["text"]               # ההזמנה בסוף ה-Short (shorts.cta)
    frames.append(shorts[0][-1])
    chart = make_chart(chart_context(episode))
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for frame in frames:
                chart.render(frame)
    finally:
        chart.close()
    missing = [str(w.message) for w in caught if "missing from font" in str(w.message)]
    assert not missing, missing


def test_the_shorts_invite_is_a_centered_end_card(tmp_path):
    from dataviz.targets import apply_target
    small = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}, "shorts": {"count": 1, "seconds": 8, "cta": "לסרטון המלא"},
             "story": {"pauses": [{"date": "2023-10-07", "text": "הקפיצה"}]}}
    episode = load_episode(write_episode(tmp_path, overrides=small))
    episode.config = apply_target(episode.config, "shorts")
    plan = build_plan(episode, "full")
    closing = build_shorts(episode, plan)[0][-1]
    pause = next(f for f in plan if (f.get("hold") or {}).get("kind") == "pause")
    assert closing["hold"]["kind"] == "invite"
    chart = make_chart(chart_context(episode))
    try:
        positions = {}
        for name, frame, text in (("invite", closing, "לסרטון המלא"), ("pause", pause, "⏸ הקפיצה")):
            chart.render(frame)
            artist = next(a for a in chart._dynamic if getattr(a, "get_text", lambda: None)() == text)
            box = artist.get_window_extent(chart.fig.canvas.get_renderer())
            positions[name] = (box.y0 + box.y1) / 2 / chart.fig.bbox.height
            if name == "invite":
                assert artist.get_alpha() == 1                             # נשארת עד הפריים האחרון (בלי יציאה הדרגתית)
    finally:
        chart.close()
    # ההזמנה באמצע הפריים (לא למעלה, מעל עמודת המוביל), והעצירה של הסיפור נשארת למעלה
    assert 0.4 < positions["invite"] < 0.6 and positions["pause"] > 0.7, positions


# ---------- הגרסה באנגלית: מקרא המקורות והתגיות ----------
def test_the_english_version_translates_the_legends_and_the_hashtags(tmp_path):
    from dataviz.languages import apply_language, clean_translation
    english = clean_translation({"title": "T", "legends": ["Yearly", " ", "Daily"], "publish": {"title": "P", "hashtags": ["rockets", "#data"]}})
    assert english == {"title": "T", "legends": ["Yearly", "Daily"], "publish": {"title": "P", "hashtags": ["rockets", "#data"]}}
    episode = load_episode(write_episode(tmp_path, overrides={"publish": {"hashtags": ["ישראל"]}, "translations": {"en": english}}))
    assert [s["legend"] for s in episode.config["sources"]] == ["שנתי", "יומי"]
    config = apply_language(episode.config, "en")
    assert [s["legend"] for s in config["sources"]] == ["Yearly", "Daily"]
    assert [s["legend"] for s in episode.config["sources"]] == ["שנתי", "יומי"]          # המקור לא השתנה
    assert dp.build_metadata(config)["hashtags"][:2] == ["#rockets", "#data"] and "#ישראל" not in dp.build_metadata(config)["hashtags"]
    assert "#ישראל" in dp.build_metadata(episode.config)["hashtags"]
    with pytest.raises(ValueError):
        clean_translation({"publish": {"hashtags": ["x"] * 31}})


def test_the_english_version_is_laid_out_left_to_right(tmp_path):
    from dataviz.episode import build_episode
    from dataviz.languages import apply_language
    english_texts = {"title": "Rocket fire", "legends": ["Yearly", "Daily"]}
    episode = load_episode(write_episode(tmp_path, overrides={"translations": {"en": english_texts}}))
    english = build_episode(apply_language(episode.config, "en"))
    assert chart_context(english)["ltr"] is True and chart_context(episode)["ltr"] is False
    for ep, title, legend, align in ((episode, episode.config["title"], "שנתי", "right"), (english, "Rocket fire", "Yearly", "left")):
        chart = make_chart(chart_context(ep))
        try:
            texts = {a.get_text(): a for a in chart._header if hasattr(a, "get_text")}
            assert texts[title].get_horizontalalignment() == align and texts[legend].get_horizontalalignment() == align
            x_title, x_legend = texts[title].get_position()[0], texts[legend].get_position()[0]
            assert (x_title < 0.5 and x_legend < 0.5) if align == "left" else (x_title > 0.5 and x_legend > 0.5)
        finally:
            chart.close()


# ---------- עיגול המספרים (החלטת המשתמש, 16.10.2026) ----------
def test_numbers_round_half_up_like_2014_in_the_first_episode():
    from dataviz.charts.base import format_int, format_number, round_half_up
    # 2014 בפרק הראשון: 4,036 בנתונים, 4,035.99... אחרי הפיזור היומי - int() הציג 4,035
    assert format_int(4035.999999) == "4,036" and format_int(4035.5) == "4,036" and format_int(4035.49) == "4,035"
    assert format_int(2.5) == "3" and format_int(-2.5) == "-3"                     # לא חצי לזוגי (round(2.5) == 2)
    assert round_half_up(0.125, 2) == 0.13 and round_half_up(2.675, 2) == 2.68    # format של פייתון: 0.12 / 2.67
    assert format_number(4035.999999, {"style": "plain"}) == "4,036"
    assert format_number(0.125, {"style": "plain", "decimals": 2}) == "0.13"
    assert format_number(1250, {"style": "compact", "decimals": 1}) == "1.3K"     # היה 1.2K
    assert format_number(2_500_000, {"style": "words"}) == "3 מיליון"
    assert format_number(999_960, {"style": "compact", "decimals": 1}) == "1M"    # לא 1000K
    assert format_number(-1234.5, {"style": "plain", "prefix": "₪"}) == "-₪1,235"


def test_a_small_value_axis_has_no_repeated_labels(tmp_path):
    # ציר y של הפיזור בין 0 ל-1: השנתות 0.2, 0.4... הוצגו 0, 0, 0 (קטימה) - או 0, 0, 1, 1 אחרי העיגול
    episode = load_episode(write_episode(tmp_path, overrides={"chart": "scatter_race", "video": {"width": 320, "height": 200, "fps": 10, "dpi": 40}}))
    plan = build_plan(episode, "full")
    chart = make_chart(chart_context(episode))
    try:
        chart.render(plan[int(len(plan) * 0.6)])
        lo, hi = chart.ax.get_ylim()
        labels = [t.get_text() for t in chart.ax.get_yticklabels() if lo <= t.get_position()[1] <= hi and t.get_text()]
    finally:
        chart.close()
    assert labels and len(labels) == len(set(labels)), labels


def test_pie_percentages_round_half_up(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides={"chart": "pie_race", "video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}))
    plan = build_plan(episode, "full")
    chart = make_chart(chart_context(episode))
    try:
        frame = next(f for f in plan if f["k"] == "main" and len(f.get("bars") or []) >= 2)
        chart.render(frame)
        labels = [a.get_text() for a in chart._dynamic if "%" in getattr(a, "get_text", lambda: "")()]
    finally:
        chart.close()
    assert labels and all(text.rstrip("%").split("· ")[-1].isdigit() for text in labels), labels


def test_the_english_outro_box_is_left_aligned(tmp_path):
    from dataviz.episode import build_episode
    from dataviz.languages import apply_language
    episode = load_episode(write_episode(tmp_path, overrides={"translations": {"en": {"title": "T", "outro": {"title": "The top"}}}}))
    for ep, align in ((episode, "right"), (build_episode(apply_language(episode.config, "en")), "left")):
        plan = build_plan(ep, "full")
        chart = make_chart(chart_context(ep))
        try:
            chart.render(next(f for f in plan if f["k"] == "outro"))
            box = next(a for a in chart._dynamic if getattr(a, "get_bbox_patch", lambda: None)() is not None and "\n" in a.get_text())
            assert box._multialignment == align and box.get_horizontalalignment() == "right"   # התיבה באותו מקום
        finally:
            chart.close()


# ---------- האומדן (23:47 דקות הוצגו לרינדור של 6:16) ----------
def _stats(tmp_path, runs):
    path = tmp_path / "stats.json"
    path.write_text(json.dumps({"runs": runs}), encoding="utf-8")
    return str(path)


def _run(rate, frames=11425, pixels=1_278_720, workers=8):
    """ריצה שהקצב האמיתי שלה rate (שניות-תהליך למגה-פיקסל), עם התקורה הקבועה."""
    from dataviz.web.preview import RUN_OVERHEAD_SECONDS
    return {"mode": "full", "frames": frames, "rendered_frames": frames, "pixels": pixels, "workers": workers,
            "seconds": RUN_OVERHEAD_SECONDS + rate * frames * pixels / 1e6 / workers}


def test_one_slow_run_barely_moves_the_estimate(tmp_path):
    from dataviz.web.preview import learned_rate
    rate, runs = learned_rate(_stats(tmp_path, [_run(0.2), _run(0.21), _run(1.0), _run(0.2)]))
    assert rate == pytest.approx(0.2, rel=0.05) and runs == 3                       # המחשב היה עמוס בזמן הריצה האיטית


def test_short_runs_do_not_inflate_the_rate(tmp_path):
    from dataviz.web.preview import learned_rate
    # אותו קצב אמיתי - ריצת בדיקה של 540 פריימים (שבה התקורה היא חלק גדול) וריצה מלאה
    rate, _ = learned_rate(_stats(tmp_path, [_run(0.2), _run(0.2, frames=2000)]))
    assert rate == pytest.approx(0.2, rel=0.01)
    tiny = {**_run(0.2, frames=60), "seconds": 15}                                   # בעיקר תקורה - לא לומדים ממנה
    assert learned_rate(_stats(tmp_path, [tiny])) == (None, 0)


def test_only_the_recent_runs_count(tmp_path):
    from dataviz.web.preview import RECENT_RUNS, learned_rate
    old_slow, new_fast = [_run(1.0)] * 5, [_run(0.2)] * RECENT_RUNS
    assert learned_rate(_stats(tmp_path, old_slow + new_fast))[0] == pytest.approx(0.2, rel=0.01)


def test_the_real_runs_of_this_round_give_a_useful_estimate(tmp_path):
    from dataviz.web.preview import RUN_OVERHEAD_SECONDS, START_SECONDS, learned_rate
    # הריצות שנרשמו בסבב הייצוב (שלוש על מחשב עמוס, ריצת בדיקה קצרה, והמלאה האחרונה: 367.7 שניות)
    real = [{"frames": f, "rendered_frames": f, "pixels": 1_278_720, "workers": 8, "seconds": s}
            for f, s in ((11425, 844.59), (11425, 1423.73), (540, 114.34), (540, 29.73), (11425, 367.68))]
    rate, _ = learned_rate(_stats(tmp_path, real))
    estimate = 11425 * rate * 1.27872 / 8 + RUN_OVERHEAD_SECONDS + START_SECONDS
    assert 330 <= estimate <= 450, estimate                                           # היה 1427 (23:47)


# ---------- התיאור לפרסום בכמה שורות ----------
def test_the_publish_description_keeps_its_line_breaks():
    from dataviz.schema import FIELD_BY_PATH
    assert FIELD_BY_PATH["publish.description"].get("multiline") is True          # בעורך: textarea
    meta = dp.build_metadata({"title": "פרק", "publish": {"description": "שורה   ראשונה  \n\n\n\nשורה שנייה\nשלישית"}})
    assert meta["description"] == "שורה ראשונה\n\nשורה שנייה\nשלישית"
    assert "שורה ראשונה\n\nשורה שנייה\nשלישית" in dp.seo_sheet("ep.mp4", {**meta, "chapters": []})
    assert dp.build_metadata({"title": "פרק", "subtitle": "  תת   כותרת "})["description"] == "תת כותרת"


# ---------- ה-bundle של המסך ----------
def test_the_first_dataviz_bundle_keeps_room():
    assert "js/47-dataviz-engine.js" in fa.LAZY_JS["dataviz_tools"] and "js/47-dataviz-engine.js" not in fa.LAZY_JS["dataviz"]   # 20.10: bundle שלישי
    assert len(fa.lazy_bundle("dataviz").encode("utf-8")) <= 145_000                 # תקרה 160K - לפחות 15K פנויים
    assert "async function dvzOpenHelp(" in fa.lazy_bundle("dataviz_tools")


def test_every_dataviz_bundle_keeps_room_for_new_features():
    # 20.10.2026: dataviz_pro הגיע ל-145K מתוך 160K - ההפקה (מדריך, תור, פרסום) עברה ל-bundle שלישי. לכל bundle של המסך
    # לפחות 25K פנויים מתחת לתקרה של 160K (tests/web/test_web_accessibility.py) - בלי להעלות אותה
    names = [n for n in fa.LAZY_JS if n.startswith("dataviz")]
    assert names == ["dataviz", "dataviz_pro", "dataviz_tools", "dataviz_plus"]   # 27.10.2026: רביעי - 25 ההצעות
    for name in names:
        assert len(fa.lazy_bundle(name).encode("utf-8")) <= 135_000, name
    assert not set(fa.LAZY_JS["dataviz"]) & set(fa.LAZY_JS["dataviz_pro"]) | set(fa.LAZY_JS["dataviz_tools"]) & set(fa.LAZY_JS["dataviz_pro"])
