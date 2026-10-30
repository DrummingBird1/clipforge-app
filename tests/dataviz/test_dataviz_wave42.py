# tests/dataviz/test_dataviz_wave42.py - גל 42 במנוע הגרפים: כתוביות SRT מהתכנית, קריינות (שורות, WAV מזויף, פקודת
# ffmpeg - בלי ffmpeg ובלי קול אמיתי), תמונה ו-GIF מהרגע החזק (פרק זעיר, פריימים בודדים), תרשים מפה מ-GeoJSON,
# בדיקת התאמה למפה, מדריך המנוע והנתיבים במסך. ברירות המחדל כבויות - שום פרק קיים לא משתנה.
import importlib.util
from tests import PROJECT_ROOT
import json
import os
import struct
import wave


import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image

from dataviz import captions, narration, share
from dataviz.charts import CHART_INFO, CHART_MODULES, make_chart
from dataviz.config import DEFAULTS, ConfigError, load_config
from dataviz.episode import load_episode
from dataviz.geo import load_geojson, match_report
from dataviz.help import help_sections
from dataviz.plan import build_plan
from dataviz.render import chart_context
from dataviz.schema import FIELDS
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import data as dataviz_data

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

BASE_DIR = PROJECT_ROOT
TINY_VIDEO = {"width": 320, "height": 200, "fps": 10, "dpi": 20}


def _square(x, y, size=1.0):
    return [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]


def _map_episode(root, name="cities", geo_names=("A", "B")):
    folder = os.path.join(str(root), name)
    os.makedirs(folder)
    with open(os.path.join(folder, "data.csv"), "w", encoding="utf-8") as f:
        f.write("date,city,n\n")
        for m in range(1, 7):
            f.write(f"2020-{m:02d}-01,A,{m}\n2020-{m:02d}-01,B,{10 * m}\n2020-{m:02d}-01,C,1\n")
    features = [{"type": "Feature", "properties": {"name": n}, "geometry": {"type": "Polygon", "coordinates": [_square(34 + i, 31)]}}
                for i, n in enumerate(geo_names)]
    features.append({"type": "Feature", "properties": {"name": "D"},
                     "geometry": {"type": "MultiPolygon", "coordinates": [[_square(40, 31, 0.5)], [_square(41, 31, 0.5)]]}})
    with open(os.path.join(folder, "regions.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    config = {"title": "ערים", "chart": "map_race", "video": TINY_VIDEO, "ranking": {"top_n": 3}, "map": {"geojson": "regions.geojson"},
              "timing": {"intro_seconds": 1, "outro_seconds": 1, "test_main_seconds": 2},
              "sources": [{"path": "data.csv", "time": {"column": "date"}, "value": {"column": "n"}, "entity": {"column": "city"}}]}
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    return folder


@pytest.fixture(scope="module")
def tiny(tmp_path_factory):
    folder = write_episode(tmp_path_factory.mktemp("w42"), overrides={"video": TINY_VIDEO})
    episode = load_episode(folder)
    return {"folder": folder, "episode": episode, "plan": build_plan(episode, "test")}


# ---------- ברירות מחדל ובדיקות ----------
def test_everything_new_is_off_by_default_and_validated(tiny, tmp_path):
    assert DEFAULTS["captions"]["enabled"] is False and DEFAULTS["narration"]["enabled"] is False
    assert DEFAULTS["map"]["geojson"] == "" and tiny["episode"].config["chart"] == "bar_race"
    folder = write_episode(tmp_path, overrides={"narration": {"rate": 40}, "share": {"gif_scale": 5}, "chart": "map_race"})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    text = "\n".join(e.value.errors)
    assert "narration.rate" in text and "share.gif_scale" in text and "map.geojson" in text
    assert {"captions.enabled", "narration.voice", "map.geojson", "share.gif_fps"} <= {f["path"] for f in FIELDS}


# ---------- כתוביות ----------
def test_captions_follow_the_cards_and_records_of_the_plan(tiny):
    plan, fps = tiny["plan"], tiny["episode"].config["video"]["fps"]
    spans = captions.caption_spans(plan, fps)
    events = [s for s in spans if s["kind"] == "event"]
    first_card = next(i for i, f in enumerate(plan) if f.get("card"))
    assert events and events[0]["start"] == pytest.approx(first_card / fps)
    assert events[0]["label"] == plan[first_card]["card"][0] and plan[first_card]["card"][1] in events[0]["text"]
    assert all(s["end"] > s["start"] for s in spans) and spans == sorted(spans, key=lambda s: (s["start"], s["kind"]))
    assert not [s for s in captions.caption_spans(plan, fps, events=False, records=False)]
    with_intro = captions.caption_spans(plan, fps, intro=True, intro_text="פתיח")
    assert with_intro[0]["kind"] == "intro" and with_intro[0]["start"] == 0


def test_srt_text_and_file(tiny, tmp_path):
    spans = [{"kind": "event", "start": 1.5, "end": 3.25, "text": "אירוע  גדול\n(07/10/2023)", "label": "אירוע גדול"},
             {"kind": "record", "start": 3661.0, "end": 3662.0, "text": "שיא חדש: 2023", "label": "שיא חדש: 2023"}]
    srt = captions.to_srt(spans)
    assert srt.startswith("1\n00:00:01,500 --> 00:00:03,250\nאירוע גדול (07/10/2023)\n")
    assert "2\n01:01:01,000 --> 01:01:02,000\nשיא חדש: 2023" in srt
    path = captions.write_srt(str(tmp_path / "ep.mp4"), spans)
    raw = open(path, "rb").read()
    assert path.endswith("ep.srt") and raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw


# ---------- קריינות ----------
def _fake_speak(text, path):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 800)


def test_narration_lines_wavs_and_the_mix_command(tmp_path):
    spans = [{"kind": "event", "start": 2.0, "text": "א (1)", "label": "א"}, {"kind": "record", "start": 5.0, "text": "שיא", "label": "שיא"},
             {"kind": "intro", "start": 0.0, "text": "פתיח", "label": "פתיח"}]
    assert narration.narration_lines(spans) == [(2.0, "א")]
    assert narration.narration_lines(spans, records=True) == [(2.0, "א"), (5.0, "שיא")]
    clips = narration.synthesize([(2.0, "א"), (5.0, "שיא")], str(tmp_path / "wav"), _fake_speak)
    assert [os.path.basename(p) for _, p in clips] == ["line_000.wav", "line_001.wav"] and all(os.path.isfile(p) for _, p in clips)
    cmd = narration.mix_command("ffmpeg", "v.mp4", clips, "out.mp4", has_audio=True, volume=1.5, duration=12.0)
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[1:a]adelay=2000|2000,volume=1.5[n1]" in graph and "[2:a]adelay=5000|5000" in graph
    assert "[0:a][n1][n2]amix=inputs=3:duration=first" in graph and "normalize=0" in graph
    assert cmd[cmd.index("-c:v") + 1] == "copy" and cmd[cmd.index("-t") + 1] == "12.000"
    silent = narration.mix_command("ffmpeg", "v.mp4", clips, "out.mp4", has_audio=False)
    assert "[n1][n2]amix=inputs=2:duration=longest" in silent[silent.index("-filter_complex") + 1]


def test_narration_replaces_the_video_only_when_ffmpeg_succeeds(tmp_path, monkeypatch):
    video = tmp_path / "ep.mp4"
    video.write_bytes(b"original")
    spans = [{"kind": "event", "start": 1.0, "text": "א", "label": "א"}]
    config = {"narration": {"enabled": True, "events": True, "records": False, "volume": 1.0}, "audio": {"path": ""}}

    def ok_run(cmd, **kwargs):
        open(cmd[-1], "wb").write(b"narrated")
        return type("R", (), {"returncode": 0, "stderr": b""})()

    monkeypatch.setattr(narration.subprocess, "run", ok_run)
    assert narration.narrate_video(str(video), config, spans, ffmpeg="ffmpeg", duration=5, speak=_fake_speak) == 1
    assert video.read_bytes() == b"narrated"
    monkeypatch.setattr(narration.subprocess, "run", lambda cmd, **kw: type("R", (), {"returncode": 1, "stderr": b"boom"})())
    with pytest.raises(RuntimeError):
        narration.narrate_video(str(video), config, spans, ffmpeg="ffmpeg", duration=5, speak=_fake_speak)
    assert video.read_bytes() == b"narrated" and not list(tmp_path.glob("*.tmp.mp4"))


# ---------- תמונה ו-GIF לשיתוף ----------
def test_the_strongest_moment_and_the_gif_frames(tiny):
    episode, plan = tiny["episode"], tiny["plan"]
    day = share.strongest_day(episode)
    assert day == int(episode.daily.sum(axis=1).argmax())
    index = share.strongest_frame(plan, day)
    assert plan[index]["k"] == "main"
    picks = share.gif_indices(1000, 5, video_fps=60, seconds=2, gif_fps=10)
    assert picks[0] == 0 and len(picks) == 20 and picks == sorted(picks)
    late = share.gif_indices(100, 99, video_fps=10, seconds=2, gif_fps=10)
    assert late[-1] == 99 and len(late) == 20


def test_share_writes_a_picture_and_a_short_gif(tiny, tmp_path):
    tiny["episode"].config["share"] = {"gif_seconds": 1.0, "gif_fps": 4, "gif_scale": 0.5}
    result = share.render_share(tiny["episode"], tiny["plan"], str(tmp_path / "ep_share"))
    with Image.open(result["png"]) as png:
        assert png.size == (320, 200)
    with Image.open(result["gif"]) as gif:
        assert gif.size == (160, 100) and gif.n_frames == result["frames"] >= 3


# ---------- מפה ----------
def test_geojson_regions_and_the_match_report(tmp_path):
    folder = _map_episode(tmp_path)
    geo = load_geojson(os.path.join(folder, "regions.geojson"), "name")
    assert [f["name"] for f in geo["features"]] == ["A", "B", "D"] and len(geo["features"][2]["rings"]) == 2
    assert match_report(geo, ["A", "B", "C"]) == {"found": ["A", "B"], "missing": ["C"], "unused": ["D"]}
    with pytest.raises(ValueError):
        load_geojson(os.path.join(folder, "regions.geojson"), "no_such_key")


def test_the_map_chart_colors_regions_by_value(tmp_path):
    episode = load_episode(_map_episode(tmp_path))
    plan = build_plan(episode, "test")
    chart = make_chart(chart_context(episode))
    try:
        chart.render(plan[-1])
        faces = chart._polys.get_facecolor()
        names = chart._names
        a, b, d = (faces[names.index(n)] for n in ("A", "B", "D"))
        assert tuple(a) != tuple(b) and tuple(d) != tuple(b)      # B (הגדול) כהה יותר, D בלי ישות
        assert len(chart.fig.axes) >= 2
    finally:
        chart.close()
    with pytest.raises(ValueError):
        chart_context(load_episode(write_episode(tmp_path / "plain")), "map_race")


def test_data_check_lists_entities_missing_from_the_map(tmp_path):
    folder = _map_episode(tmp_path)
    found = dataviz_data.data_check(folder, {})
    assert any(f["kind"] == "map" and "C" in f["text"] for f in found["findings"])


# ---------- מדריך, נתיבים והסקריפט ----------
def test_help_covers_every_chart_mode_and_setting():
    sections = {s["id"]: s for s in help_sections()}
    assert [i["code"] for i in sections["charts"]["items"]] == list(CHART_MODULES) and set(CHART_INFO) == set(CHART_MODULES)
    assert "share" in [i["code"] for i in sections["modes"]["items"]]
    codes = {i["code"] for s in sections.values() if s["id"].startswith("group-") for i in s["items"]}
    assert codes == {f["path"] for f in FIELDS}
    assert all("ברירת מחדל" in i["text"] for i in sections["group-captions"]["items"])


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    write_episode(data / "dataviz_episodes", name="tiny", overrides={"video": TINY_VIDEO})
    return {"data": data, "workspace": workspace}


def test_routes_captions_voices_help_and_share_outputs(env, monkeypatch):
    resp = client.get("/api/dataviz/episodes/captions?episode=tiny&mode=test&download=1")
    assert resp.status_code == 200 and resp.text.startswith("1\n") and "-->" in resp.text
    assert "attachment" in resp.headers["content-disposition"]
    assert client.get("/api/dataviz/episodes/captions?episode=ghost").status_code == 404
    assert client.get("/api/dataviz/episodes/captions?episode=tiny&mode=nope").status_code == 400
    from dataviz import narration as nar
    from entrypoints.web.routes import dataviz as routes
    routes._voices_cache.clear()
    monkeypatch.setattr(nar, "list_voices", lambda: [{"name": "Microsoft Asaf", "culture": "he-IL", "gender": "Male"}])
    assert client.get("/api/dataviz/voices").json()["voices"][0]["culture"] == "he-IL"
    routes._voices_cache.clear()
    assert [s["id"] for s in client.get("/api/dataviz/help").json()["sections"]][:2] == ["charts", "modes"]
    folder = env["workspace"] / "dataviz" / "outputs" / "horizontal" / "tiny_share"
    folder.mkdir(parents=True)
    Image.new("RGB", (4, 4)).save(folder / "share.png")
    Image.new("RGB", (4, 4)).save(folder / "share.gif")
    out = client.get("/api/dataviz/outputs?episode=tiny").json()["outputs"]
    assert out[0]["mode"] == "share" and out[0]["files"] == ["share.gif", "share.png"]
    gif = client.get("/api/dataviz/media/horizontal/tiny_share/share.gif")
    assert gif.status_code == 200 and gif.headers["content-type"] == "image/gif"
    assert client.get("/api/dataviz/media/horizontal/tiny_share/x.mp4").status_code == 404
    assert client.get("/api/dataviz/episodes").json()["episodes"][0]["has_map"] is False


def test_the_maker_writes_captions_and_names_the_share_folder(tmp_path):
    spec = importlib.util.spec_from_file_location("dataviz_maker_w42", os.path.join(BASE_DIR, "my_scripts", "video", "dataviz_maker.py"))
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    episode = load_episode(write_episode(tmp_path, overrides={"video": TINY_VIDEO, "captions": {"enabled": True}}))
    plan = build_plan(episode, "test")
    video = tmp_path / "out.mp4"
    results = {"files_created": 1}
    maker.add_captions_and_narration(str(video), episode.config, plan, "test", type("A", (), {"captions": False})(), results)
    assert (tmp_path / "out.srt").exists() and results["files_created"] == 2
    folder, target = maker.output_paths(episode.config, "share", str(tmp_path))
    assert target.endswith(os.path.join("dataviz", "outputs", "horizontal", "tiny_share"))
