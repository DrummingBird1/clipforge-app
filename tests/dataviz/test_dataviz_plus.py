# tests/dataviz/test_dataviz_plus.py - 25 ההצעות לעורך הגרפים מהבדיקה הטכנית (27.10.2026), הצד של המנוע והשרת: אזורי לחיצה
# בפריים, מיקום תיבת הסיום והערות שנגררו, מעברי פרק, רינדור טווח, NVENC ועדיפות נמוכה כברירת מחדל, דגלים, תבניות,
# התצוגה לאורך, תאריך לכל מקום בסליידר, sparklines, וידאו קצר לתצוגה, מצב כרטיס המסך, שימור צופים והקלטה רציפה.
# בלי רשת (הורדת הדגלים ויוטיוב מזויפים) ובלי ffmpeg, חוץ מטסט אחד שמסומן needs_ffmpeg.
import base64
import json
import os

import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz.charts import make_chart
from dataviz.config import ConfigError, load_config
from dataviz.episode import load_episode
from dataviz.plan import build_plan, clip_range
from dataviz.render import chart_context
from entrypoints import web_app
from tests.dataviz_helpers import write_episode
from tests.media_support import needs_ffmpeg

client = TestClient(web_app.app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
COUNTRIES = [("2024-01-%02d" % d, e, v) for d in range(1, 31) for e, v in (("ישראל", 3), ("USA", 5), ("France", 2))]


def episode_from_rows(root, rows, extra=None, name="ep"):
    folder = os.path.join(str(root), name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "d.csv"), "w", encoding="utf-8") as f:
        f.write("date,entity,v\n" + "".join(f'{d},"{e}",{v}\n' for d, e, v in rows))
    config = {"title": "בדיקה", "subtitle": "תת", "ranking": {"top_n": 5}, **SMALL,
              "sources": [{"path": "d.csv", "time": {"column": "date"}, "entity": {"column": "entity"}, "value": {"column": "v"}}],
              **(extra or {})}
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
    return folder


def rendered(folder, kind="main", chart=None, at=0.5, overrides=None):
    episode = load_episode(folder, overrides or {})
    plan = build_plan(episode, "test")
    frames = [f for f in plan if f["k"] == kind]
    chart_obj = make_chart(chart_context(episode, chart))
    frame = frames[min(int(len(frames) * at), len(frames) - 1)]
    pixels = chart_obj.render(frame)
    return chart_obj, frame, pixels


# ---------- 1-3, 15: אזורי לחיצה ----------
def test_main_frame_has_hit_regions_for_texts_and_entities(tmp_path):
    chart_obj, _frame, _px = rendered(episode_from_rows(tmp_path, COUNTRIES))
    try:
        targets = {h["target"] for h in chart_obj.hit_regions()}
        assert {"path:title", "path:subtitle", "entity:ישראל", "entity:USA"} <= targets
        for hit in chart_obj.hit_regions():
            x0, y0, x1, y1 = hit["box"]
            assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
        title = next(h for h in chart_obj.hit_regions() if h["target"] == "path:title")
        assert title["box"][1] < 0.2   # הכותרת למעלה (0 = ראש התמונה)
    finally:
        chart_obj.close()


def test_intro_and_outro_frames_have_their_own_targets(tmp_path):
    folder = episode_from_rows(tmp_path, COUNTRIES, {"intro": {"subtitle": "שאלה", "question": "מי?"}})
    for kind, wanted in (("intro", {"path:intro.title", "path:intro.subtitle", "path:intro.question"}), ("outro", {"outro"})):
        chart_obj, _f, _p = rendered(folder, kind=kind, at=0.5 if kind == "intro" else 0.99)   # באמצע הפתיח (בסופו הוא דוהה)
        try:
            assert wanted <= {h["target"] for h in chart_obj.hit_regions()}, kind
        finally:
            chart_obj.close()


def test_hit_regions_do_not_change_pixels(tmp_path):
    """הסימון (gid) לא משנה אף פיקסל - אותו פריים עם ובלי לקרוא ל-hit_regions."""
    folder = episode_from_rows(tmp_path, COUNTRIES)
    chart_obj, frame, before = rendered(folder)
    try:
        chart_obj.hit_regions()
        assert chart_obj.render(frame) == before
    finally:
        chart_obj.close()


# ---------- 2: תיבת הסיום והערות שנגררו ----------
def test_outro_position_places_the_box_center(tmp_path):
    folder = episode_from_rows(tmp_path, COUNTRIES, {"outro": {"title": "המובילות", "places": ["ראשון", "שני"], "position": [0.3, 0.7]}})
    chart_obj, _f, _p = rendered(folder, kind="outro", at=0.99)
    try:
        box = next(h for h in chart_obj.hit_regions() if h["target"] == "outro")["box"]
        ax = chart_obj.ax.get_position()
        cx, cy = (box[0] + box[2]) / 2, 1 - (box[1] + box[3]) / 2
        assert cx == pytest.approx(ax.x0 + 0.3 * (ax.x1 - ax.x0), abs=0.02)
        assert cy == pytest.approx(ax.y0 + 0.7 * (ax.y1 - ax.y0), abs=0.02)
    finally:
        chart_obj.close()


@pytest.mark.parametrize("bad", [[0.5], [2.0, 0.5], ["a", 1], 5])
def test_outro_position_is_validated(tmp_path, bad):
    folder = episode_from_rows(tmp_path, COUNTRIES)
    with pytest.raises(ConfigError, match="outro.position"):
        load_config(os.path.join(folder, "config.yaml"), {"outro": {"position": bad}})


def test_a_dragged_callout_keeps_its_offset(tmp_path):
    story = {"callouts": [{"date": "2024-01-05", "entity": "USA", "text": "עוקפת", "days": 20, "dx": -80, "dy": 60}]}
    folder = episode_from_rows(tmp_path, COUNTRIES, {"story": story})
    episode = load_episode(folder)
    marked = [f for f in build_plan(episode, "test") if f.get("callouts")]
    assert marked and marked[0]["callouts"][0][:2] == ("USA", "עוקפת") and marked[0]["callouts"][0][3:] == (0, -80, 60)
    chart_obj = make_chart(chart_context(episode))
    try:
        chart_obj.render(marked[len(marked) // 2])
        target = next(h["target"] for h in chart_obj.hit_regions() if h["target"].startswith("callout:"))
        assert target == "callout:0:-80:60"
    finally:
        chart_obj.close()


def test_callout_offsets_are_cleaned_from_the_browser():
    from dataviz.web.episodes import draft_overrides
    out = draft_overrides({}, {"story.callouts": [{"date": "2024-01-05", "entity": "USA", "text": "x", "dx": 999, "dy": "-12"}]})
    assert out["story"]["callouts"][0]["dx"] == 400 and out["story"]["callouts"][0]["dy"] == -12
    assert draft_overrides({}, {"outro.position": [0.25, 1.2]})["outro"]["position"] == [0.25, 1.2]
    assert draft_overrides({}, {"outro.position": []})["outro"]["position"] == []


# ---------- 8: מעברי פרק ----------
def test_chapter_transitions_draw_differently_mid_way(tmp_path):
    frames = {}
    for style in ("fade", "slide", "zoom", "wipe"):
        story = {"chapters": [{"date": "2024-01-10", "title": "פרק חדש"}], "chapter_transition": style}
        folder = episode_from_rows(tmp_path / style, COUNTRIES, {"story": story})
        episode = load_episode(folder)
        held = [f for f in build_plan(episode, "test") if (f.get("hold") or {}).get("kind") == "chapter"]
        frame = min(held, key=lambda f: abs(float(f["hold"]["t"]) - 0.07))   # באמצע הכניסה
        chart_obj = make_chart(chart_context(episode))
        try:
            frames[style] = np.frombuffer(chart_obj.render(frame), dtype=np.uint8)
        finally:
            chart_obj.close()
    assert len({frames[s].tobytes() for s in frames}) == 4


def test_fade_is_the_default_and_unknown_transitions_are_rejected(tmp_path):
    folder = episode_from_rows(tmp_path, COUNTRIES)
    assert load_config(os.path.join(folder, "config.yaml"))["story"]["chapter_transition"] == "fade"
    with pytest.raises(ConfigError, match="chapter_transition"):
        load_config(os.path.join(folder, "config.yaml"), {"story": {"chapter_transition": "spin"}})


# ---------- 10: רינדור טווח ----------
def test_clip_range_keeps_only_the_main_part_between_the_dates(tmp_path):
    episode = load_episode(episode_from_rows(tmp_path, COUNTRIES))
    plan = build_plan(episode, "full")
    part = clip_range(plan, episode, "2024-01-10", "2024-01-15")
    assert part and all(f["k"] == "main" for f in part)
    days = {episode.dates[int(f["x"])].strftime("%Y-%m-%d") for f in part}
    assert min(days) >= "2024-01-10" and max(days) <= "2024-01-15"
    assert clip_range(plan, episode, "2024-01-15", "2024-01-10") == part   # סדר הפוך - אותו טווח
    with pytest.raises(ValueError):
        clip_range(plan, episode, "2030-01-01", "2030-02-01")


# ---------- 12-13: NVENC אוטומטי ועדיפות נמוכה ----------
def test_auto_encoder_and_low_priority_are_the_defaults(tmp_path):
    config = load_config(os.path.join(episode_from_rows(tmp_path, COUNTRIES), "config.yaml"))
    assert config["video"]["encoder"] == "auto" and config["video"]["priority"] == "low"
    with pytest.raises(ConfigError, match="video.priority"):
        load_config(os.path.join(episode_from_rows(tmp_path / "b", COUNTRIES), "config.yaml"), {"video": {"priority": "high"}})


def test_lower_priority(monkeypatch):
    from dataviz import render
    calls = []

    class FakeProcess:
        def nice(self, value=None):
            calls.append(value)
            return 0

    import psutil
    monkeypatch.setattr(psutil, "Process", FakeProcess)
    assert render.lower_priority("normal") is False and calls == []
    assert render.lower_priority("low") is True
    assert calls[-1] == (psutil.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 10)


# ---------- 9: דגלים ----------
def test_country_codes_from_hebrew_english_and_emoji():
    from dataviz.countries import codes_for, country_code
    assert country_code("ישראל") == "il" and country_code("ארה\"ב") == "us" and country_code("United States") == "us"
    assert country_code("USA 🇺🇸") == "us" and country_code("🇫🇷") == "fr" and country_code("côte d'ivoire") == "ci"
    assert country_code("2019") is None and country_code("תל אביב") is None
    assert codes_for(["ישראל", "x", "France"]) == {"ישראל": "il", "France": "fr"}


def _png(path, color=(255, 0, 0, 255)):
    from PIL import Image
    Image.new("RGBA", (40, 24), color).save(path)


def test_flags_fill_entities_without_their_own_image(tmp_path, monkeypatch):
    from dataviz.charts.base import load_entity_images
    flags, own = tmp_path / "flags", tmp_path / "images"
    flags.mkdir()
    own.mkdir()
    _png(flags / "il.png")
    _png(flags / "us.png")
    _png(own / "USA.png", (0, 0, 255, 255))   # תמונה של המשתמש גוברת על הדגל
    images = load_entity_images({"folder": str(own), "flags": True, "flags_dir": str(flags), "shape": "square"}, ["ישראל", "USA", "France"])
    assert set(images) == {"ישראל", "USA"}
    assert tuple(images["USA"][80, 80][:3]) == (0, 0, 255)
    assert load_entity_images({"folder": "", "flags": False, "flags_dir": str(flags)}, ["ישראל"]) == {}


def test_download_flags_only_known_codes_and_only_png(tmp_path):
    from dataviz.web import plus
    fetched = []

    def fake(url):
        fetched.append(url)
        return b"\x89PNG fake" if "/il.png" in url else b"<html>nope</html>"

    result = plus.download_flags(str(tmp_path), ["il", "fr", "zz", "IL"], fetch=fake)
    assert result == {"saved": ["il"], "failed": ["fr"]}
    assert all(u.startswith("https://flagcdn.com/") for u in fetched) and len(fetched) == 2   # zz לא בטבלה
    assert os.path.isfile(os.path.join(plus.flags_dir(str(tmp_path)), "il.png"))
    status = plus.flags_status(str(tmp_path), ["ישראל", "France", "2019"])
    assert status["missing"] == ["fr"] and {c["entity"]: c["have"] for c in status["countries"]} == {"France": False, "ישראל": True}


# ---------- 11: תבניות ----------
def _data_dir(tmp_path):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    return data


def test_save_a_template_and_start_a_new_episode_from_it(tmp_path):
    from dataviz.web import episodes as de
    from dataviz.web import plus
    data = _data_dir(tmp_path)
    write_episode(data / "dataviz_episodes", overrides={"title": "מקור", "style": {"bar_height": 0.5, "grid": False, "title_size": 30, "year_mark": False}},
                  name="source")
    saved = plus.save_template(str(data), "source", "חדשותי שלי")
    assert saved["id"].startswith("tpl:") and [t["title"] for t in plus.list_templates(str(data))] == ["חדשותי שלי"]
    config = de._inherit_template(str(data), saved["id"], {"title": "חדש"})
    assert config["title"] == "חדש" and config["style"]["bar_height"] == 0.5 and config["style"]["title_size"] == 30
    assert plus.delete_template(str(data), saved["id"]) and plus.list_templates(str(data)) == []
    with pytest.raises(de.EpisodeError):
        plus.save_template(str(data), "source", "../bad/name")


# ---------- 4, 7, 6: התצוגה לאורך, תאריך לכל מקום, sparkline ----------
def test_preview_meta_and_vertical_target(tmp_path):
    from dataviz.web import preview
    folder = episode_from_rows(tmp_path, COUNTRIES)
    frame = preview.preview_frame(folder, {}, str(tmp_path / "cache"), 0.5, scale=0.35)
    assert frame["iso_date"].startswith("2024-01") and frame["hits"] and len(frame["axes_box"]) == 4 and frame["fig_pt"][0] > 0
    vertical = preview.preview_frame(folder, {}, str(tmp_path / "cache"), 0.5, scale=0.35, target="shorts")
    from PIL import Image
    with Image.open(vertical["path"]) as image:
        assert image.height > image.width
    cached = preview.preview_frame(folder, {}, str(tmp_path / "cache"), 0.5, scale=0.35)   # מהמטמון - עם אותו מידע
    assert cached["hits"] == frame["hits"]


def test_timeline_maps_slider_positions_to_dates(tmp_path):
    from dataviz.web import preview
    data = preview.timeline(episode_from_rows(tmp_path, COUNTRIES), {})
    points = data["points"]
    assert points and data["start"] == "2024-01-01" and data["end"] == "2024-01-30"
    assert [p[0] for p in points] == sorted(p[0] for p in points) and [p[1] for p in points] == sorted(p[1] for p in points)
    assert 0 < points[0][0] < points[-1][0] < 1   # הפתיח לפני, הסיום אחרי


def test_sparklines_and_their_jumps(tmp_path):
    from dataviz.web import preview
    rows = [("2024-01-%02d" % d, e, 300 if (e == "USA" and d == 20) else 2) for d in range(1, 31) for e in ("ישראל", "USA")]
    data = preview.sparklines(episode_from_rows(tmp_path, rows), {})
    usa = data["entities"]["USA"]
    assert len(usa["values"]) == data["buckets"] and usa["jumps"] and max(usa["values"]) >= 300
    assert data["entities"]["ישראל"]["jumps"] == []


# ---------- 18: וידאו קצר לתצוגה ----------
@needs_ffmpeg
def test_preview_clip_as_mp4(tmp_path):
    from dataviz.web import preview
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    folder = episode_from_rows(tmp_path, COUNTRIES)
    clip = preview.preview_clip(folder, {}, str(tmp_path / "cache"), 0.5, seconds=1.0, fps=6, fmt="mp4", ffmpeg=get_ffmpeg_exe())
    assert clip["format"] == "mp4" and clip["path"].endswith(".mp4")
    with open(clip["path"], "rb") as f:
        assert b"ftyp" in f.read(64)
    gif = preview.preview_clip(folder, {}, str(tmp_path / "cache"), 0.5, seconds=1.0, fps=6)
    assert gif["format"] == "gif" and gif["path"].endswith(".gif")


def test_mp4_falls_back_to_gif_when_ffmpeg_fails(tmp_path):
    from dataviz.web import preview
    clip = preview.preview_clip(episode_from_rows(tmp_path, COUNTRIES), {}, str(tmp_path / "cache"), 0.5, seconds=1.0, fps=6,
                                fmt="mp4", ffmpeg=str(tmp_path / "no-ffmpeg.exe"))
    assert clip["format"] == "gif" and os.path.isfile(clip["path"])


# ---------- 13: כרטיס המסך ----------
def test_gpu_status_parses_nvidia_smi_and_handles_no_card(monkeypatch):
    from dataviz.web import plus

    class Result:
        def __init__(self, code, out):
            self.returncode, self.stdout = code, out

    plus._GPU.update({"at": 0.0, "data": None})
    data = plus.gpu_status(lambda *a, **k: Result(0, "NVIDIA GeForce RTX 4070 SUPER, 37, [N/A], 2100, 12282, 51\n"))
    assert data == {"available": True, "name": "NVIDIA GeForce RTX 4070 SUPER", "gpu": 37, "encoder": None, "memory_used": 2100,
                    "memory_total": 12282, "temperature": 51}
    plus._GPU.update({"at": 0.0, "data": None})

    def missing(*a, **k):
        raise FileNotFoundError("nvidia-smi")

    assert plus.gpu_status(missing) == {"available": False}
    plus._GPU.update({"at": 0.0, "data": None})


# ---------- 14: שימור צופים ----------
def test_retention_points_are_sorted_and_tolerant():
    from dataviz.web.plus import retention_points
    rows = [[0.5, 0.6, 0.48], [0.01, 1.2, 0.5], ["x", 1, 1], [1.0, 0.3]]
    assert retention_points(rows) == [{"at": 0.01, "watch": 1.2, "relative": 0.5}, {"at": 0.5, "watch": 0.6, "relative": 0.48},
                                      {"at": 1.0, "watch": 0.3, "relative": None}]


def test_retention_asks_the_analytics_api_with_the_new_scope(monkeypatch):
    from utils.bot import youtube_analytics, youtube_uploader
    assert youtube_uploader.ANALYTICS_SCOPE in youtube_uploader.SCOPES
    seen = {}

    class Query:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def execute(self):
            return {"rows": [[0.01, 1.0, 0.5]]}

    class Reports:
        def query(self, **kwargs):
            return Query(**kwargs)

    class Service:
        def reports(self):
            return Reports()

    import googleapiclient.discovery
    monkeypatch.setattr(youtube_analytics, "_get_credentials", lambda: "creds")
    monkeypatch.setattr(googleapiclient.discovery, "build", lambda name, version, credentials=None: Service())
    assert youtube_analytics.get_audience_retention("abc123") == [[0.01, 1.0, 0.5]]
    assert seen["filters"] == "video==abc123" and seen["dimensions"] == "elapsedVideoTimeRatio" and "audienceWatchRatio" in seen["metrics"]


# ---------- 20: הקלטה רציפה ----------
def test_save_track_points_the_episode_at_the_recording(tmp_path):
    from dataviz.narration import track_path
    from dataviz.web import episodes as de
    from dataviz.web import plus
    data = _data_dir(tmp_path)
    write_episode(data / "dataviz_episodes", name="ep")
    saved = plus.save_track(str(data), "ep", "webm", base64.b64encode(b"\x1aE\xdf\xa3fake").decode(), 12.5)
    assert saved["name"].startswith("track_") and saved["start"] == 12.5
    folder = de.episode_folder(str(data), "ep")
    config = load_config(os.path.join(folder, "config.yaml"), de.load_overrides_for_path(folder))
    assert config["narration"]["track"] == saved["name"] and config["narration"]["track_start"] == 12.5
    assert track_path(config).endswith(saved["name"])
    with pytest.raises(de.EpisodeError):
        plus.save_track(str(data), "ep", "exe", base64.b64encode(b"x").decode(), 0)


def test_narrate_track_mixes_at_its_start(tmp_path, monkeypatch):
    from dataviz import narration
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "track_1.webm").write_bytes(b"x")
    config = {"base_dir": str(tmp_path), "narration": {"folder": "rec", "track": "track_1.webm", "track_start": 4.0, "volume": 1.0},
              "audio": {}}
    calls = []
    monkeypatch.setattr(narration, "add_narration", lambda video, clips, **kw: calls.append((clips, kw["has_audio"])))
    assert narration.narrate_track("v.mp4", config, ffmpeg="ffmpeg", duration=10.0, has_audio=False) is True
    assert calls == [([(4.0, str(tmp_path / "rec" / "track_1.webm"))], False)]
    assert narration.narrate_track("v.mp4", {**config, "narration": {**config["narration"], "track": ""}}, ffmpeg="ffmpeg", duration=10.0) is False


# ---------- הנתיבים ----------
@pytest.fixture
def server(tmp_path, monkeypatch):
    data, workspace = _data_dir(tmp_path), tmp_path / "workspace"
    workspace.mkdir()
    episode_from_rows(data / "dataviz_episodes", COUNTRIES, name="countries")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def test_routes_for_meta_timeline_sparklines_flags_and_gpu(server, monkeypatch):
    meta = client.get("/api/dataviz/preview_frame", params={"episode": "countries", "pos": 0.5, "meta": 1}).json()
    assert meta["iso_date"] and any(h["target"] == "entity:USA" for h in meta["hits"])
    vertical = client.get("/api/dataviz/preview_frame", params={"episode": "countries", "pos": 0.5, "target": "shorts"})
    assert vertical.status_code == 200 and vertical.headers["content-type"] == "image/png"
    assert client.get("/api/dataviz/preview_frame", params={"episode": "countries", "target": "tv"}).status_code == 400
    assert client.get("/api/dataviz/timeline", params={"episode": "countries"}).json()["points"]
    assert "USA" in client.get("/api/dataviz/episodes/sparklines", params={"episode": "countries"}).json()["entities"]
    flags = client.get("/api/dataviz/flags", params={"episode": "countries"}).json()
    assert {c["code"] for c in flags["countries"]} == {"il", "us", "fr"} and flags["missing"] == ["fr", "il", "us"]
    from dataviz.web import plus
    monkeypatch.setattr(plus, "gpu_status", lambda: {"available": False})
    assert client.get("/api/dataviz/gpu").json() == {"available": False}
    assert client.get("/api/dataviz/flags", params={"episode": "nope"}).status_code == 404


def test_routes_for_templates_and_versions(server):
    saved = client.post("/api/dataviz/templates", json={"episode": "countries", "title": "שלי"}).json()
    assert [t["id"] for t in client.get("/api/dataviz/templates").json()["templates"]] == [saved["id"]]
    assert client.post("/api/dataviz/templates/delete", json={"id": saved["id"]}).json() == {"ok": True}
    assert client.post("/api/dataviz/templates/delete", json={"id": saved["id"]}).status_code == 404
    # גרסה מההיסטוריה - תמונה משלה
    assert client.post("/api/dataviz/episodes/override", json={"episode": "countries", "set": {"title": "גרסה"}, "unset": []}).status_code == 200
    version = client.get("/api/dataviz/history", params={"episode": "countries"}).json()["versions"][0]["id"]
    image = client.get("/api/dataviz/preview_frame", params={"episode": "countries", "pos": 0.5, "version": version})
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert client.get("/api/dataviz/preview_frame", params={"episode": "countries", "version": "../x"}).status_code == 400


def test_retention_routes_without_an_uploaded_video(server):
    assert client.get("/api/dataviz/retention", params={"episode": "countries"}).json() == {"points": [], "uploaded": False}
    assert client.post("/api/dataviz/retention", json={"episode": "countries"}).status_code == 400


def test_run_route_accepts_a_range_only_in_full_or_test(server, monkeypatch):
    seen = {}
    monkeypatch.setattr(web_app, "_start_script_run", lambda path, folder, payload, host: seen.update(payload) or {"ok": True})
    ok = client.post("/api/dataviz/run", json={"episode": "countries", "mode": "test", "range": "2024-01-05,2024-01-12"})
    assert ok.status_code == 200 and seen["dv_range"] == "2024-01-05,2024-01-12"
    for bad in ({"mode": "preview", "range": "2024-01-05,2024-01-12"}, {"mode": "full", "range": "yesterday"}):
        assert client.post("/api/dataviz/run", json={"episode": "countries", **bad}).status_code == 400
    from entrypoints.web.script_args import _args_dataviz
    args = _args_dataviz({"dv_mode": "test", "dv_range": "2024-01-05,2024-01-12"})
    assert args[args.index("--range") + 1] == "2024-01-05,2024-01-12"
    assert "--range" not in _args_dataviz({"dv_mode": "test", "dv_range": "2024-01-05; rm -rf"})


def test_narration_track_route(server):
    data = base64.b64encode(b"\x1aE\xdf\xa3fake").decode()
    ok = client.post("/api/dataviz/narration_track", json={"episode": "countries", "ext": "webm", "data": data, "start": 3})
    assert ok.status_code == 200 and ok.json()["start"] == 3
    assert client.post("/api/dataviz/narration_track", json={"episode": "countries", "ext": "webm", "data": "!!", "start": 3}).status_code == 400


def test_new_settings_have_english_labels():
    from dataviz.i18n_en import tr
    from dataviz.schema import FIELD_BY_PATH
    for path in ("video.priority", "images.flags", "story.chapter_transition", "narration.track", "narration.track_start"):
        field = FIELD_BY_PATH[path]
        assert tr(field["label"], "en") != field["label"], path
        for label in (field.get("choice_labels") or {}).values():
            assert tr(label, "en") != label, label


def test_json_dump_of_new_defaults_is_stable(tmp_path):
    config = load_config(os.path.join(episode_from_rows(tmp_path, COUNTRIES), "config.yaml"))
    assert json.loads(json.dumps(config["outro"]["position"])) == [] and config["images"]["flags"] is False
