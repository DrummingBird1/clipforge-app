# tests/dataviz/test_dataviz_fix_smart.py
#
# 23.10.2026, סריקת הבאגים - מנה 6 (העורך החכם, המעקב וסקריפט הרינדור). המספרים לפי הדוח (dataviz-bug-hunt-2026-10-23.md):
# ג13 "data" ב-SOURCES.md סימן את קובץ הנתונים היחיד כלא בשימוש; ג14 קבצים מפוצלים לפי שנים - רק הראשון נכנס; ב20 כמות /
# רמה לפי תאריכים שמוינו כטקסט; ב21 תשובה לשאלת כמות / רמה לא חישבה מחדש את הטקסטים; ב23 מפה ששמורה כ-.json לא הועתקה;
# ב24 ניסיון והחזרה השאירו העדפה הפוכה; ב25 "סדרה" לפי שורת המקור לבד; ב26 המעקב עם השם הגולמי של התיקייה; ב27 מעקב על
# שורש כונן; ב28 --only-if-changed השאיר את הפרק "pending"; ב29 שגיאה בשלב הכתוביות / הפרקים עצרה את התור; נ7 Short
# חלקי נשאר; נ8 קובץ סטטיסטיקה בצורה שגויה הפיל רינדור שהצליח.
import contextlib
import importlib.util
import json
import os
import sys

import pandas as pd
import pytest
import yaml

from dataviz import schema
from dataviz.episode import load_episode
from dataviz.smart import create, draft, learn, watch
from dataviz.smart.kinds import guess_kind
from dataviz.smart.texts import facts
from dataviz.web import episodes as de
from tests import PROJECT_ROOT
from tests.dataviz_helpers import write_episode


def _csv(path, text):
    path.write_text(text.strip() + "\n", encoding="utf-8")


@pytest.fixture
def data_dir(tmp_path):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    return str(data)


# ---------- ג13 ----------
def test_a_common_word_in_sources_md_does_not_hide_the_data_file(tmp_path):
    _csv(tmp_path / "data.csv", "year,entity,value\n" + "\n".join(f"{y},{e},{y - 1990 + k}" for y in range(2000, 2008) for k, e in enumerate("אבג")))
    _csv(tmp_path / "SOURCES.md", "# Sources\nRows with missing data are not used.\n")
    assert [f["name"] for f in draft.analyze(str(tmp_path))["series"]] == ["data.csv"]   # קודם: "לא נמצאה סדרה"
    _csv(tmp_path / "SOURCES.md", "# Sources\nexports_raw_2020.csv is not used.\n")
    _csv(tmp_path / "exports_raw_2020.csv", "year,entity,value\n2000,א,1\n2001,א,2\n2002,א,3\n")
    hint = {f["name"]: f.get("kind") for f in draft.scan_folder(str(tmp_path))["files"]}
    assert hint["exports_raw_2020.csv"] != "series"                             # שם מלא - עדיין מזוהה


# ---------- ג14 ----------
def test_files_split_by_years_both_go_into_the_episode(tmp_path):
    for first, last in ((2000, 2009), (2010, 2019)):
        _csv(tmp_path / f"exports_{first}_{last}.csv",
             "year,entity,exports_usd\n" + "\n".join(f"{y},{e},{(y - 1990) * (k + 1)}" for y in range(first, last + 1) for k, e in enumerate(("ישראל", "יוון"))))
    analysis = draft.analyze(str(tmp_path))
    assert sorted(f["name"] for f in analysis["series"]) == ["exports_2000_2009.csv", "exports_2010_2019.csv"]   # קודם: רק הראשון
    found = facts(analysis, "exports", str(tmp_path))
    assert (found["start"], found["end"]) == ("2000", "2019")                  # קודם: 2000-2009 בכותרת
    with open(tmp_path / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "יצוא", "sources": analysis["plan"]["sources"]}, f, allow_unicode=True)
    episode = load_episode(str(tmp_path))
    assert (episode.dates[0].year, episode.dates[-1].year) == (2000, 2019)


# ---------- ב20 ----------
def test_cumulative_values_with_day_first_dates_are_a_level():
    dates = [f"01/{m:02d}/{y}" for y in (2019, 2020) for m in range(1, 13)]
    rows = [(d, e, 100 * (k + 1) + i * (k + 2)) for i, d in enumerate(dates) for k, e in enumerate(("a", "b"))]
    df = pd.DataFrame(rows, columns=["date", "entity", "x"])
    result = guess_kind("x", "", None, df, "date", "entity")
    assert result["value"] == "level" and "כבר מצטבר" in result["reason"]     # קודם: מיון כטקסט - כמות, ומצטבר פעמיים


# ---------- ב21 ----------
def test_answering_the_kind_question_recomputes_the_texts(data_dir, tmp_path):
    vague = tmp_path / "vague"
    vague.mkdir()
    _csv(vague / "numbers.csv", "year,entity,x\n" + "\n".join(f"{2000 + i},{e},{v}" for i in range(6)
                                                                for e, v in (("a", 10 + i * 3), ("b", 12 + (i % 2) * 5), ("c", 7))))
    record = create.create_from_folder(data_dir, str(vague), "vague", thumbnail=False)
    record["question"] = {"about": "kind", "question": "?", "options": [{"value": "amount"}, {"value": "level"}], "current": "amount"}
    create.save_record(data_dir, "vague", record)
    folder = de.episode_folder(data_dir, "vague")
    before = de.load_overrides_for_path(folder)
    create.answer(data_dir, "vague", "level")
    after = de.load_overrides_for_path(folder)
    # מה שטיוטה מאפס הייתה נותנת כשהערכים רמה
    analysis = draft.analyze(folder)
    for f in analysis["series"]:
        f["roles"]["kind"] = {"value": "level", "confidence": 0.95, "reason": ""}
    for spec in analysis["plan"]["sources"]:
        spec["kind"] = "level"
    from dataviz.smart.story import find_story
    analysis["story"] = find_story(folder, analysis)
    expected = create.build_draft(folder, "vague", analysis)["set"]
    texts = ("title", "subtitle", "intro.question", "story.script")
    assert any(schema.get_path(before, p)[1] != expected.get(p) for p in texts)   # הטקסטים של כמות באמת שונים
    assert all(schema.get_path(after, p)[1] == expected.get(p) for p in texts)    # קודם: נשארו של כמות ("השיא: ...")


# ---------- ב23 ----------
def test_a_map_saved_as_json_is_copied_with_the_episode(data_dir, tmp_path):
    source = tmp_path / "regions"
    source.mkdir()
    names = ["צפון", "דרום", "מרכז"]
    _csv(source / "population.csv", "year,region,population\n" + "\n".join(f"{y},{n},{100 + k * 10 + y - 2000}" for y in range(2000, 2006) for k, n in enumerate(names)))
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": n}, "geometry": {"type": "Polygon", "coordinates": [[[34 + k, 31], [35 + k, 31], [35 + k, 32], [34 + k, 31]]]}}
        for k, n in enumerate(names)]}
    (source / "regions.json").write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
    create.create_from_folder(data_dir, str(source), "regions", thumbnail=False)
    folder = de.episode_folder(data_dir, "regions")
    overrides = de.load_overrides_for_path(folder)
    assert overrides.get("chart") == "map_race" and overrides["map"]["geojson"] == "regions.json"
    assert os.path.isfile(os.path.join(folder, "regions.json"))                  # קודם: התרשים מפה, והקובץ לא שם


# ---------- ב24 ----------
def test_trying_another_chart_and_going_back_leaves_no_preference(data_dir):
    record = {"kit": "", "choices": [{"path": "chart", "value": "bar_race", "where": "override"}]}
    create.save_record(data_dir, "ep", record)
    assert learn.observe(data_dir, "ep", {"chart": "line_race"}) == ["chart"]
    assert learn.load_prefs(data_dir)["default"]["chart"] == {"bar_race": "line_race"}
    learn.observe(data_dir, "ep", {"chart": "bar_race"})                       # חזר לבחירה האוטומטית
    assert learn.load_prefs(data_dir)["default"].get("chart") in (None, {})   # קודם: נשאר bar_race -> line_race
    create.save_record(data_dir, "other", {"kit": "", "choices": [{"path": "ranking.top_n", "value": 10, "where": "override"}]})
    learn.observe(data_dir, "other", {"ranking": {"top_n": 5}})
    learn.observe(data_dir, "other", {})                                       # השדה הוסר
    assert "ranking.top_n" not in learn.load_prefs(data_dir)["default"]


# ---------- ב25 ----------
def test_the_same_source_line_alone_is_not_a_series(data_dir, tmp_path):
    old = write_episode(os.path.join(data_dir, "dataviz_episodes"), name="cbs_old")
    _csv(tmp_path / "SOURCES.md", "# Sources\n- **Source:** CBS\n")
    with open(os.path.join(old, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("# Sources\n- **Source:** CBS\n")
    _csv(tmp_path / "rain.csv", "month,station,rain_mm\n2020-01,חיפה,100\n2020-02,חיפה,80\n2020-03,חיפה,50\n")
    assert learn.find_series(data_dir, str(tmp_path)) is None                  # קודם: הסדרה של cbs_old (מקור זהה לבד)


# ---------- ב26 / ב27 ----------
def test_the_watch_uses_the_episode_name_and_survives_unreadable_folders(data_dir, tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "my data").mkdir(parents=True)
    _csv(root / "my data" / "medals.csv", "year,country,total_medals\n" + "\n".join(f"{y},{c},{v + y - 1990}" for y in range(1990, 1996) for c, v in (("צרפת", 20), ("יפן", 5))))
    (root / "locked").mkdir()
    write_episode(os.path.join(data_dir, "dataviz_episodes"), name="my_data")   # השם כבר תפוס
    real_listdir = os.listdir

    def listdir(path="."):
        if os.path.basename(os.path.normpath(str(path))) == "locked":
            raise PermissionError("System Volume Information")
        return real_listdir(path)
    monkeypatch.setattr(os, "listdir", listdir)
    runs = []
    from dataviz.web import batch
    monkeypatch.setattr(batch, "run", lambda d, w, items, out: runs.append(items) or {"failed": 0})
    monkeypatch.setattr(batch, "_new_out_dir", lambda w: os.path.join(str(tmp_path), "out"))
    watch.configure(data_dir, True, str(root))                                 # קודם: PermissionError
    watch._save(data_dir, {**watch.load(data_dir), "seen": []})
    done = watch.check(data_dir, str(tmp_path / "ws"), send=lambda text: True)
    assert [e.get("episode") for e in done] == ["my_data_2"]                   # קודם: נכשל ("כבר קיים") ונרשם כנראה
    assert runs and runs[0][0]["name"] == "my_data_2" and runs[0][0]["path"]   # קודם: הדוח על נתיב ריק


# ---------- סקריפט הרינדור ----------
@pytest.fixture(scope="module")
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_fix6", os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main(maker, monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["dataviz_maker.py", *args])
    monkeypatch.setattr(maker, "notify_finished", lambda *a, **k: False)
    with contextlib.suppress(SystemExit):
        maker.main()


def test_only_if_changed_marks_the_queued_episode_as_skipped(maker, monkeypatch, tmp_path, capsys):
    folder = write_episode(tmp_path, name="ep")
    from dataviz.web import remote
    monkeypatch.setattr(remote, "refresh_sources", lambda d, n: {"sources": [{"url": "https://x", "changed": False}], "changed": False})
    queue = tmp_path / "queue.json"
    _main(maker, monkeypatch, "--input_dir", folder, "--mode", "stills", "--refresh-data", "--only-if-changed",
          "--queue-file", str(queue), "--output_dir", str(tmp_path / "out"))
    assert json.loads(queue.read_text(encoding="utf-8"))["episodes"][0]["state"] == "skipped"   # קודם: pending לתמיד


def test_an_error_in_one_episode_does_not_stop_the_queue(maker, monkeypatch, tmp_path, capsys):
    first = write_episode(tmp_path, name="a")
    write_episode(tmp_path, name="b")
    real = maker.render_episode

    def render(path, *args, **kwargs):
        if path == first:
            raise OSError("srt locked")                                         # כמו write_srt שנכשל
        return real(path, *args, **kwargs)
    monkeypatch.setattr(maker, "render_episode", render)
    queue = tmp_path / "queue.json"
    _main(maker, monkeypatch, "--input_dir", str(tmp_path), "--mode", "stills", "--queue-file", str(queue), "--output_dir", str(tmp_path / "out"))
    out = capsys.readouterr().out
    assert "RESULT:" in out                                                      # קודם: הריצה קרסה בלי RESULT
    states = {e["name"]: e["state"] for e in json.loads(queue.read_text(encoding="utf-8"))["episodes"]}
    assert states == {"a": "failed", "b": "done"}                                # קודם: a נשאר "running", b לא רץ


def test_a_failed_chapters_or_captions_step_keeps_the_video(maker, monkeypatch, tmp_path):
    from dataviz import captions
    monkeypatch.setattr(captions, "write_chapters", lambda *a: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr(captions, "write_srt", lambda *a: (_ for _ in ()).throw(OSError("locked")))
    monkeypatch.setattr(captions, "youtube_chapters", lambda *a: [(0.0, "א"), (20.0, "ב"), (40.0, "ג")])
    config = {"video": {"fps": 10}, "captions": {"enabled": True}, "publish": {}, "title": "x", "intro": {}}
    args = type("A", (), {"captions": False})()
    results = {"files_created": 1, "errors": 0}
    maker.add_captions_and_narration(str(tmp_path / "v.mp4"), config, [], "full", args, results)   # קודם: OSError החוצה
    assert results == {"files_created": 1, "errors": 0}


def test_a_failed_short_leaves_no_partial_file(maker, monkeypatch, tmp_path):
    from dataviz import render, shorts
    from utils import render_lock
    monkeypatch.setattr(shorts, "build_shorts", lambda episode, plan: [[{"k": "main"}] * 3])
    monkeypatch.setattr(render_lock, "render_lock_if_needed", lambda **k: contextlib.nullcontext())

    def broken(episode, short, path, **kwargs):
        with open(path, "wb") as f:
            f.write(b"partial")
        raise RuntimeError("ffmpeg died")
    monkeypatch.setattr(render, "render_video", broken)
    episode = type("E", (), {"config": {"video": {"fps": 10}}})()
    results = {"files_created": 0, "errors": 0}
    args = type("A", (), {"workers": 1})()
    target = str(tmp_path / "out" / "ep_shorts.mp4")
    maker.render_shorts(episode, [], "bar_race", str(tmp_path / "out"), target, args, lambda d, t: None, results, "ep")
    assert results["errors"] == 1 and not os.path.exists(str(tmp_path / "out" / "ep_shorts_1.mp4"))   # קודם: הקובץ החלקי נשאר


def test_a_stats_file_with_a_bad_shape_does_not_fail_the_render(maker, monkeypatch, tmp_path):
    from utils import data_dir as data_dir_module
    monkeypatch.setattr(data_dir_module, "DATA_DIR", str(tmp_path))
    (tmp_path / maker.STATS_FILE).write_text('{"runs": null}', encoding="utf-8")
    maker.record_render_time("full", {"frames": 10, "size": (320, 200)}, 2, 1.5)   # קודם: AttributeError
    runs = json.loads((tmp_path / maker.STATS_FILE).read_text(encoding="utf-8"))["runs"]
    assert len(runs) == 1 and runs[0]["frames"] == 10
