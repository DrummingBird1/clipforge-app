# tests/dataviz/test_dataviz_wave50.py - גל 50 בעורך הגרפים, "הסיפור": פרקים בתוך הסרטון (כרטיס כותרת על פריים קפוא),
# עצירות עם הסבר, הערה לישות, תקופות מוצללות, קטעי מהירות, פתיח "טיזר", מסך סיום ליוטיוב ומקורות הנתונים (בסיום
# ובתיאור). בלי ffmpeg - תכנית, כתוביות ופריימים קטנים; עריכת הרשימות דרך השרת, ו-config.yaml של הפרק לא משתנה.
import hashlib
import os


import pytest
from fastapi.testclient import TestClient

from dataviz.captions import caption_spans
from dataviz.charts import CHART_MODULES, make_chart
from dataviz.config import ConfigError, load_config, mode_timing
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.render import chart_context, still_indices
from dataviz.share import strongest_frame
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web.publish import build_metadata, send_plan

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}
STORY = {"chapters": [{"date": "2022-01-01", "title": "פרק שני", "subtitle": "השנים השקטות"}],
         "pauses": [{"date": "2023-10-07", "text": "הקפיצה הגדולה", "seconds": 2}],
         "callouts": [{"date": "2023-10-01", "entity": 2023, "text": "השנה הזו עוקפת", "days": 60}],
         "periods": [{"start": "2023-10-07", "end": "2023-12-31", "label": "מלחמה", "color": "#aa3355"}],
         "speed": [{"start": "2019-01-01", "end": "2021-12-31", "speed": 4}]}


def _episode(tmp_path, **extra):
    return load_episode(write_episode(tmp_path, overrides={**SMALL, **extra}))


def test_chapters_and_pauses_freeze_the_frame_for_their_seconds(tmp_path):
    plain = build_plan(_episode(tmp_path / "a"), "full")
    plan = build_plan(_episode(tmp_path / "b", story=STORY), "full")
    holds = [f for f in plan if "hold" in f]
    chapter = [f for f in holds if f["hold"]["kind"] == "chapter"]
    pause = [f for f in holds if f["hold"]["kind"] == "pause"]
    assert len(chapter) == 25 and len(pause) == 20                  # 2.5 שניות (ברירת המחדל) ו-2 שניות, ב-10 פריימים לשנייה
    assert {f["x"] for f in chapter} == {chapter[0]["x"]} and chapter[0]["hold"]["t"] == 0 and chapter[-1]["hold"]["t"] == 1
    assert chapter[0]["date"] == "01/01/2022" and pause[0]["date"] == "07/10/2023"
    assert chapter[0]["hold"]["subtitle"] == "השנים השקטות"
    # קטע המהירות (פי 4 ב-2019-2021) מקצר את הקטע הראשי
    moving = [f for f in plan if f["k"] == "main" and "hold" not in f]
    assert len(moving) < len([f for f in plain if f["k"] == "main"])


def test_holds_outside_the_episode_are_ignored(tmp_path):
    story = {"chapters": [{"date": "1990-01-01", "title": "לפני הכל"}], "pauses": [{"date": "2030-01-01", "text": "אחרי הכל"}]}
    assert not any("hold" in f for f in build_plan(_episode(tmp_path, story=story), "full"))


def test_callouts_follow_their_entity_for_the_days_given(tmp_path):
    plan = build_plan(_episode(tmp_path, story=STORY), "full")
    marked = [f for f in plan if f.get("callouts")]
    assert marked and all(f["callouts"][0][:2] == (2023, "השנה הזו עוקפת") for f in marked)
    assert all(2023 in [b[0] for b in f["bars"]] for f in marked)
    days = sorted({int(f["x"]) for f in marked})
    assert days[-1] - days[0] < 60 and max(f["callouts"][0][2] for f in marked) == pytest.approx(1.0)


def test_teaser_comes_first_from_the_strongest_moment(tmp_path):
    plan = build_plan(_episode(tmp_path, teaser={"enabled": True, "seconds": 2, "label": "בהמשך"}), "full")
    teaser = [f for f in plan[:20]]
    assert all(f.get("teaser") == "בהמשך" and f["k"] == "main" for f in teaser) and plan[20]["k"] == "intro"
    assert any(f["date"] == "07/10/2023" for f in teaser)           # היום עם הקפיצה הגדולה
    picks = still_indices(plan)
    assert all("teaser" not in plan[i] for i in picks) and plan[picks[0]]["k"] == "intro"
    assert "teaser" not in plan[strongest_frame(plan, 1000)] and "hold" not in plan[strongest_frame(plan, 1000)]


def test_end_screen_extends_the_outro_and_marks_its_seconds(tmp_path):
    episode = _episode(tmp_path, end_screen={"enabled": True, "seconds": 12, "text": "צפו גם", "guides": True})
    assert mode_timing(episode.config, "full")["outro"] == 120          # 12 שניות במקום 10
    plan = build_plan(episode, "full")
    outro = [f for f in plan if f["k"] == "outro"]
    assert len(outro) == 120 and all("end_screen" in f for f in outro)
    assert outro[0]["end_screen"] == 0 and outro[-1]["end_screen"] == 1


def test_captions_include_the_chapters_and_the_intro_after_a_teaser(tmp_path):
    episode = _episode(tmp_path, story=STORY, teaser={"enabled": True, "seconds": 2, "label": "x"})
    spans = caption_spans(build_plan(episode, "full"), 10, intro=True, intro_text="פרק בדיקה")
    chapter = [s for s in spans if s["kind"] == "chapter"]
    assert len(chapter) == 1 and chapter[0]["text"] == "פרק שני - השנים השקטות" and chapter[0]["end"] - chapter[0]["start"] == pytest.approx(2.5)
    intro = [s for s in spans if s["kind"] == "intro"][0]
    assert intro["start"] == pytest.approx(2.0)                        # אחרי שתי שניות של טיזר


def test_periods_reach_the_charts_in_episode_days(tmp_path):
    episode = _episode(tmp_path, story=STORY)
    (start, end, label, color), = chart_context(episode)["periods"]
    assert episode.dates[int(start)].strftime("%Y-%m-%d") == "2023-10-07" and episode.dates[int(end)].strftime("%Y-%m-%d") == "2023-11-01"
    assert (label, color) == ("מלחמה", "#aa3355")                      # הנתונים נגמרים ב-1.11 - התקופה נחתכת שם


@pytest.mark.parametrize("chart", [c for c in CHART_MODULES if c != "map_race"])
def test_every_chart_draws_every_story_element(tmp_path, chart):
    episode = _episode(tmp_path, chart=chart, story=STORY, teaser={"enabled": True, "seconds": 1, "label": "בהמשך"},
                       end_screen={"enabled": True, "seconds": 5, "text": "צפו גם", "guides": True},
                       outro={"title": "המובילות", "places": ["ראשון", "שני"], "credits": ["מקור: פיקוד העורף", "עיבוד: ClipForge"]})
    plan = build_plan(episode, "full")
    picks = [next(i for i, f in enumerate(plan) if key(f)) for key in (
        lambda f: f.get("teaser"), lambda f: (f.get("hold") or {}).get("kind") == "chapter",
        lambda f: (f.get("hold") or {}).get("kind") == "pause", lambda f: f.get("callouts"), lambda f: f.get("end_screen") is not None)]
    chart_obj = make_chart(chart_context(episode))
    try:
        for i in picks:
            assert len(chart_obj.render(plan[i])) == 320 * 200 * 4
    finally:
        chart_obj.close()


def test_bad_story_settings_are_reported_together(tmp_path):
    folder = write_episode(tmp_path, overrides={"story": {"chapters": [{"date": "not a date", "title": "x"}], "pauses": [{"date": "2022-01-01"}],
                                                          "speed": [{"start": "2022-01-01", "end": "2022-02-01", "speed": 50}],
                                                          "periods": [{"start": "2022-01-01", "end": "2022-02-01", "label": "x", "color": "red"}]},
                                                "teaser": {"enabled": "yes"}, "end_screen": {"enabled": True, "seconds": 40}})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    text = "\n".join(e.value.errors)
    for part in ("story.chapters[0]: תאריך לא תקין", "story.pauses[0] צריך date, text", "story.speed[0].speed", "story.periods[0].color", "teaser", "end_screen"):
        assert part in text, part


def test_credits_go_to_the_description_as_their_own_block(tmp_path):
    config = {"title": "פרק", "outro": {"credits": ["מקור: פיקוד העורף", " "]}, "publish": {"description": "תיאור"}}
    meta = build_metadata(config)
    assert meta["credits"] == ["מקור: פיקוד העורף"]
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "v.mp4").write_bytes(b"x")
    plan = send_plan({"status": "approved", "video": "v.mp4", "metadata": {**meta, "description": "תיאור שנערך"}}, str(folder), "dry_run")
    assert plan["description"].startswith("תיאור שנערך\n\nמקורות הנתונים:\n- מקור: פיקוד העורף\n\n#")


# ---------- עריכת הרשימות דרך השרת ----------
@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides=SMALL)
    config = os.path.join(folder, "config.yaml")
    return {"data": str(data), "config": config, "md5": hashlib.md5(open(config, "rb").read()).hexdigest()}


def test_story_lists_are_cleaned_sorted_and_saved_in_the_override(env):
    resp = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {
        "story.chapters": [{"date": "2023-01-01", "title": " שנייה ", "seconds": "3"}, {"date": "2022-1-5", "title": "ראשונה", "extra": "x"}],
        "story.periods": [{"start": "2023-10-07", "end": "2023-12-31", "label": "מלחמה", "color": "#AA3355"}],
        "teaser.enabled": True, "end_screen.enabled": True, "outro.credits": ["מקור א", ""]}})
    assert resp.status_code == 200, resp.text
    saved = de.load_overrides_for_path(os.path.join(env["data"], "dataviz_episodes", "tiny"))
    assert saved["story"]["chapters"] == [{"date": "2022-01-05", "title": "ראשונה"}, {"date": "2023-01-01", "title": "שנייה", "seconds": 3.0}]
    assert saved["story"]["periods"][0]["color"] == "#aa3355" and saved["outro"]["credits"] == ["מקור א"]
    editor = client.get("/api/dataviz/episodes/editor", params={"episode": "tiny"}).json()
    assert [c["title"] for c in editor["story"]["chapters"]] == ["ראשונה", "שנייה"] and editor["story"]["speed"] == []
    assert hashlib.md5(open(env["config"], "rb").read()).hexdigest() == env["md5"]


@pytest.mark.parametrize("change", [
    {"story.chapters": [{"date": "2023-01-01"}]},
    {"story.speed": [{"start": "2023-01-01", "end": "2023-02-01", "speed": 99}]},
    {"story.periods": [{"start": "2023-01-01", "end": "2023-02-01", "label": "x", "color": "red"}]},
    {"story.callouts": "not a list"},
])
def test_bad_story_lists_are_refused(env, change):
    resp = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": change})
    assert resp.status_code == 400
    assert hashlib.md5(open(env["config"], "rb").read()).hexdigest() == env["md5"]
