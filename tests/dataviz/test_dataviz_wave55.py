# tests/dataviz/test_dataviz_wave55.py - גל 55 בעורך הגרפים, "הפרסום": פרקים ביוטיוב מהתכנית (0:00, לפחות 3, כל אחד 10
# שניות), גרסה באנגלית (translations.en), Shorts אוטומטיים מהרגעים הדרמטיים, התמונה הממוזערת שעולה עם הסרטון
# ולוח צפיות לסדרה. בלי ffmpeg ובלי יוטיוב אמיתי (מעלה מזויף); config.yaml של הפרקים לא משתנה.
import hashlib
from tests import PROJECT_ROOT
import importlib.util
import json
import os
import time


import pytest
from fastapi.testclient import TestClient

from dataviz.captions import chapter_stamp, write_chapters, youtube_chapters
from dataviz.charts.base import format_number
from dataviz.config import ConfigError
from dataviz.episode import build_episode, load_episode
from dataviz.languages import apply_language, clean_translation
from dataviz.plan import build_plan
from dataviz.shorts import build_shorts, dramatic_days
from dataviz.targets import apply_target
from entrypoints import web_app
from entrypoints.web.script_args import _args_dataviz
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web import publish as dp

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 40}}
SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py")
STORY = {"chapters": [{"date": "2022-01-01", "title": "פרק שני"}]}
EN = {"title": "Test episode", "intro": {"question": "Who wins?"}, "outro": {"places": ["First", "Second", "Third"]},
      "labels": {"total": "Total"}, "events": {"2023-10-07": "The big event"}, "entities": {"2023": "Year 2023"},
      "publish": {"title": "English title"}}


# ---------- פרקים ביוטיוב ----------
def test_youtube_chapters_follow_the_rules(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides={**SMALL, "story": STORY}))
    plan = build_plan(episode, "full")
    chapters = youtube_chapters(episode.config, plan)
    assert chapters[0] == (0.0, "פרק בדיקה") and len(chapters) >= 3
    assert all(b[0] - a[0] >= 10 for a, b in zip(chapters, chapters[1:]))
    assert len(plan) / 10 - chapters[-1][0] >= 10
    assert {label for _t, label in chapters} >= {"פרק שני", "אירוע גדול"}
    shifted = youtube_chapters(episode.config, plan, offset=4.0)
    assert shifted[0][0] == 0 and [round(t - 4, 6) for t, _ in shifted[1:]] == [round(t, 6) for t, _ in chapters[1:]]
    assert youtube_chapters(episode.config, plan[:120]) == []                          # פחות מ-3 פרקים אפשריים
    assert [chapter_stamp(s) for s in (0, 65.9, 3725)] == ["0:00", "1:05", "1:02:05"]


def test_chapters_go_into_the_description_before_the_credits(tmp_path):
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "v.mp4").write_bytes(b"x")
    write_chapters(str(folder / "v.mp4"), [(0.0, "פתיח"), (12.0, "אירוע"), (40.0, "סוף")])
    assert dp.read_chapters(str(folder / "v.mp4")) == ["0:00 פתיח", "0:12 אירוע", "0:40 סוף"]
    meta = {**dp.build_metadata({"title": "פרק", "outro": {"credits": ["מקור"]}, "publish": {"description": "תיאור"}}),
            "chapters": dp.read_chapters(str(folder / "v.mp4"))}
    plan = dp.send_plan({"status": "approved", "video": "v.mp4", "metadata": meta}, str(folder), "dry_run")
    assert plan["description"].startswith("תיאור\n\n0:00 פתיח\n0:12 אירוע\n0:40 סוף\n\nמקורות הנתונים:")
    assert plan["thumbnail"] == ""


# ---------- גרסה באנגלית ----------
def test_the_english_version_translates_texts_events_and_entities(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides={**SMALL, "translations": {"en": EN}, "numbers": {"style": "words", "decimals": 1}}))
    config = apply_language(episode.config, "en")
    assert config["title"] == "Test episode" and config["intro"]["question"] == "Who wins?" and config["intro"]["subtitle"] == "שנה מול שנה"
    assert config["video"]["output_name"] == f"{episode.config['name']}_en" and config["language"] == "en"
    assert config["publish"]["title"] == "English title"
    english = build_episode(config)
    assert "Year 2023" in english.entities and 2023 not in english.entities
    assert dict((date, label) for date, label, _ in english.events)["2023-10-07"] == "The big event"
    assert format_number(1_500_000, config["numbers"]) == "1.5 million"
    assert format_number(1_500_000, episode.config["numbers"]) == "1.5 מיליון"
    with pytest.raises(ValueError, match="אין תרגום"):
        apply_language(load_episode(write_episode(tmp_path / "b", overrides=SMALL)).config, "en")
    with pytest.raises(ValueError, match="לא נתמכת"):
        apply_language(episode.config, "fr")
    bad = load_episode(write_episode(tmp_path / "c", overrides={**SMALL, "translations": {"en": {"story": {"chapters": [{"date": "x", "title": "y"}]}}}}))
    with pytest.raises(ConfigError, match="התרגום ל-en"):
        apply_language(bad.config, "en")


def test_translations_from_the_screen_are_cleaned(tmp_path, monkeypatch):
    cleaned = clean_translation({"title": " T ", "evil": "x", "intro": {"title": "I", "bad": 1}, "notes": ["a", " ", "b"],
                                 "events": {"2023-10-07": "E", "2021-05-10": " "}, "publish": {"description": "D" * 100}})
    assert cleaned == {"title": "T", "intro": {"title": "I"}, "notes": ["a", "b"], "events": {"2023-10-07": "E"}, "publish": {"description": "D" * 100}}
    with pytest.raises(ValueError):
        clean_translation({"title": "x" * 300})
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides=SMALL)
    md5 = hashlib.md5(open(os.path.join(folder, "config.yaml"), "rb").read()).hexdigest()
    assert client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {"translations.en": EN}}).status_code == 200
    saved = de.load_overrides_for_path(folder)["translations"]["en"]
    assert saved["title"] == "Test episode" and saved["entities"] == {"2023": "Year 2023"}
    assert [e["languages"] for e in client.get("/api/dataviz/episodes").json()["episodes"]] == [["en"]]
    editor = client.get("/api/dataviz/episodes/editor", params={"episode": "tiny"}).json()
    assert editor["translations"]["en"]["intro"]["question"] == "Who wins?"
    assert client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {"translations.fr": EN}}).status_code == 400
    assert client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": {"translations.en": {"title": 5}}}).status_code == 400
    assert hashlib.md5(open(os.path.join(folder, "config.yaml"), "rb").read()).hexdigest() == md5


def test_run_arguments_for_languages_and_shorts():
    assert _args_dataviz({"dv_mode": "shorts", "dv_lang": "both"}) == ["--mode", "shorts", "--lang", "both"]
    assert _args_dataviz({"dv_mode": "full", "dv_lang": "fr"}) == ["--mode", "full"]


# ---------- Shorts אוטומטיים ----------
def test_dramatic_days_prefer_the_big_jump_and_stay_apart(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides=SMALL))
    days = dramatic_days(episode, 3)
    assert episode.dates[days[0]].strftime("%Y-%m-%d") == "2023-10-07"
    assert len(days) == len(set(days)) and all(abs(a - b) >= 7 for i, a in enumerate(days) for b in days[i + 1:])


def test_shorts_are_vertical_clips_around_each_moment(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides={**SMALL, "shorts": {"count": 2, "seconds": 8, "cta": "לסרטון המלא"}}))
    episode.config = apply_target(episode.config, "shorts")
    shorts = build_shorts(episode, build_plan(episode, "full"))
    assert len(shorts) == 2 and episode.config["video"]["height"] > episode.config["video"]["width"]
    for short in shorts:
        kinds = [f["k"] for f in short]
        assert kinds[:15] == ["intro"] * 15 and len([k for k in kinds if k == "main"]) == 80 + 15
        assert short[-1]["hold"] == {"kind": "invite", "text": "לסרטון המלא", "t": 1.0}   # סבב הייצוב: כרטיס סיום במרכז
    assert any(f["date"] == "07/10/2023" for f in shorts[0] if f["k"] == "main")


def test_the_script_renders_shorts_and_english_versions(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dataviz_maker_w55", SCRIPT)
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    from dataviz import render
    rendered = []
    monkeypatch.setattr(render, "render_video", lambda episode, plan, path, **k: rendered.append((os.path.basename(path), len(plan), episode.config["title"])) or {"path": path})
    folder = write_episode(tmp_path / "eps", overrides={**SMALL, "translations": {"en": EN}, "shorts": {"count": 2, "seconds": 8, "cta": "x"}}, name="ep")
    args = type("Args", (), {"output_dir": str(tmp_path / "out"), "target": "", "chart": None, "workers": 1, "captions": False,
                             "publish": False, "no_publish": True})()
    results = {"files_created": 0, "errors": 0}
    maker.render_episode(folder, "shorts", args, lambda d, t: None, results)
    assert [name for name, _n, _t in rendered] == ["ep_shorts_1.mp4", "ep_shorts_2.mp4"] and results["files_created"] == 2
    assert os.path.isdir(tmp_path / "out" / "dataviz" / "outputs" / "vertical")
    rendered.clear()
    maker.render_episode(folder, "stills", args, lambda d, t: None, results, lang="en")
    stills = tmp_path / "out" / "dataviz" / "outputs" / "horizontal" / "ep_en_stills"
    assert stills.is_dir() and len(os.listdir(stills)) >= 5 and results["errors"] == 0


# ---------- התמונה עם הסרטון, והיסטוריית הצפיות ----------
def test_the_chosen_thumbnail_is_uploaded_with_the_video(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(tmp_path))
    folder = tmp_path / "dataviz" / "outputs" / "horizontal"
    folder.mkdir(parents=True)
    (folder / "ep.mp4").write_bytes(b"video")
    (folder / "ep_thumb.jpg").write_bytes(b"\xff\xd8\xff")
    dp._write_json(dp.sidecar_path(str(folder / "ep.mp4")), {"status": dp.APPROVED, "video": "ep.mp4", "thumbnail": "ep_thumb.jpg",
                                                              "metadata": {"title": "T", "description": "", "hashtags": []}})
    thumbs = []
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    monkeypatch.setattr(web_app.youtube_uploader, "upload_video", lambda *a, **k: "VID")
    monkeypatch.setattr(web_app.youtube_uploader, "set_thumbnail", lambda video_id, path: thumbs.append((video_id, os.path.basename(path))))
    monkeypatch.setattr(web_app.youtube_publish_log, "record_upload", lambda *a, **k: None)
    plan = client.post("/api/dataviz/packages/horizontal/ep/send", json={}).json()["plan"]
    assert plan["thumbnail"] == "ep_thumb.jpg"
    assert client.post("/api/dataviz/packages/horizontal/ep/send", json={"target": "youtube", "confirm": True}).status_code == 200
    deadline = time.time() + 5
    while "youtube" not in (dp.load_package(dp.sidecar_path(str(folder / "ep.mp4"))).get("sent") or {}) and time.time() < deadline:
        time.sleep(0.05)
    assert thumbs == [("VID", "ep_thumb.jpg")]
    assert dp.load_package(dp.sidecar_path(str(folder / "ep.mp4")))["sent"]["youtube"]["thumbnail"] == "set"


def test_views_history_and_the_series_board(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    for number, name in ((1, "ep_a"), (2, "ep_b")):
        write_episode(data / "dataviz_episodes", name=name, overrides={**SMALL, "series": {"name": "אזעקות", "number": number}})
    write_episode(data / "dataviz_episodes", name="lonely", overrides=SMALL)
    folder = workspace / "dataviz" / "outputs" / "horizontal"
    folder.mkdir(parents=True)
    for name in ("ep_a", "ep_b"):
        (folder / f"{name}.mp4").write_bytes(b"v")
        dp._write_json(dp.sidecar_path(str(folder / f"{name}.mp4")), {"status": dp.APPROVED, "video": f"{name}.mp4", "metadata": {},
                                                                     "sent": {"youtube": {"video_id": name.upper()}}})
    sidecar = dp.sidecar_path(str(folder / "ep_a.mp4"))
    dp.record_stats(sidecar, {"views": 10, "likes": 1, "comments": 0})
    dp.record_stats(sidecar, {"views": 25, "likes": 3, "comments": 2})
    assert [h["views"] for h in dp.load_package(sidecar)["stats_history"]] == [10, 25]
    board = client.get("/api/dataviz/series_board").json()
    series, = board["series"]
    assert series["name"] == "אזעקות" and [e["episode"] for e in series["episodes"]] == ["ep_a", "ep_b"]
    first = series["episodes"][0]
    assert first["stats"]["views"] == 25 and [v for _at, v in first["history"]] == [10, 25] and first["package"] == {"orientation": "horizontal", "name": "ep_a"}
    assert series["episodes"][1]["stats"] == {} and series["episodes"][1]["history"] == []      # הועלה, עוד בלי צפיות
    json.dumps(board, ensure_ascii=False)
