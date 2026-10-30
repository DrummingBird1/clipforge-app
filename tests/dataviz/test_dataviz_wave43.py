# tests/dataviz/test_dataviz_wave43.py - גל 43 בעורך הגרפים: אינטרו / אאוטרו מקליפ (פקודת ffmpeg, החלפה רק אחרי הצלחה,
# הזזת הכתוביות), גופן לפרק ולערכה, ערכה ממיתוג עם גופן וקליפים, עדכון נתונים למקור Excel, רשימת הגופנים, וסל
# המיחזור לתיקיית שיתוף ולקבצים הנלווים. בלי ffmpeg אמיתי ובלי רינדור - הכל מוחלף; פרקים קיימים לא משתנים.
import hashlib
from tests import PROJECT_ROOT
import importlib.util
import json
import os


import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from dataviz import bumpers
from dataviz.config import DEFAULTS, ConfigError, load_config
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import data as dd
from dataviz.web import episodes as de
from dataviz.web import kits as dk

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False
BASE_DIR = PROJECT_ROOT
TINY = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides=TINY)
    (tmp_path / "intro.mp4").write_bytes(b"i")
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": str(data), "folder": folder, "workspace": workspace, "intro": str(tmp_path / "intro.mp4"), "md5": md5}


def _unchanged(env):
    return {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == env["md5"]


# ---------- אינטרו / אאוטרו ----------
def test_bumpers_are_off_by_default_and_a_missing_clip_is_an_error(env, tmp_path):
    assert DEFAULTS["bumpers"] == {"intro": "", "outro": ""}
    folder = write_episode(tmp_path / "x", overrides={"bumpers": {"intro": "nope.mp4", "outro": ""}})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    assert any("nope.mp4" in err for err in e.value.errors)
    config = load_config(os.path.join(env["folder"], "config.yaml"), {"bumpers": {"intro": env["intro"]}})
    assert config["bumpers"]["intro"] == env["intro"]


def test_the_concat_command_scales_pads_and_fills_silence():
    segments = [{"path": "intro.mp4", "duration": 2.5, "has_audio": False}, {"path": "main.mp4", "duration": 30, "has_audio": True}]
    cmd = bumpers.concat_command("ffmpeg", segments, "out.mp4", size=(1080, 1920), fps=30, video={"crf": 20, "preset": "fast"})
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920" in graph and "fps=30" in graph
    assert "anullsrc=r=48000:cl=stereo,atrim=0:2.500[a0]" in graph and "[1:a]aresample=48000" in graph
    assert graph.endswith("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]") and cmd[cmd.index("-crf") + 1] == "20"


def test_bumpers_replace_the_video_only_after_success(tmp_path):
    video = tmp_path / "ep.mp4"
    video.write_bytes(b"main")
    config = {"base_dir": str(tmp_path), "bumpers": {"intro": "intro.mp4", "outro": "outro.mp4"}, "video": {"width": 320, "height": 200, "fps": 10}}
    probe = lambda path: {"duration": 2.0 if "intro" in path else 9.0, "has_audio": True}  # noqa: E731
    seen = []

    def ok(cmd):
        seen.append(cmd)
        open(cmd[-1], "wb").write(b"joined")
        return type("R", (), {"returncode": 0, "stderr": b""})()

    assert bumpers.add_bumpers(str(video), config, ffmpeg="ffmpeg", ffprobe="ffprobe", probe_fn=probe, run=ok) == 2.0
    assert video.read_bytes() == b"joined" and [seen[0][i + 1] for i, a in enumerate(seen[0]) if a == "-i"][1] == str(video)
    fail = lambda cmd: type("R", (), {"returncode": 1, "stderr": b"bad"})()  # noqa: E731
    with pytest.raises(RuntimeError):
        bumpers.add_bumpers(str(video), config, ffmpeg="ffmpeg", ffprobe="ffprobe", probe_fn=probe, run=fail)
    assert video.read_bytes() == b"joined" and not list(tmp_path.glob("*.tmp.mp4"))
    assert bumpers.add_bumpers(str(video), {"bumpers": {"intro": "", "outro": ""}}, ffmpeg="f", ffprobe="p") == 0.0
    shifted = bumpers.shift_spans([{"start": 1.0, "end": 2.0, "text": "x"}], 2.0)
    assert shifted == [{"start": 3.0, "end": 4.0, "text": "x"}]


def test_captions_move_by_the_intro_length(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dataviz_maker_w43", os.path.join(BASE_DIR, "my_scripts", "video", "dataviz_maker.py"))
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    (tmp_path / "intro.mp4").write_bytes(b"i")
    episode = load_episode(write_episode(tmp_path, overrides={**TINY, "captions": {"enabled": True}, "bumpers": {"intro": str(tmp_path / "intro.mp4")}}))
    plan = build_plan(episode, "test")
    monkeypatch.setattr(bumpers, "add_bumpers", lambda *a, **k: 2.0)
    results = {"files_created": 1}
    maker.add_captions_and_narration(str(tmp_path / "out.mp4"), episode.config, plan, "test", type("A", (), {"captions": False})(), results)
    first_card = next(i for i, f in enumerate(plan) if f.get("card"))
    srt = (tmp_path / "out.srt").read_text(encoding="utf-8-sig")
    seconds = first_card / 10 + 2.0
    assert f"00:00:{int(seconds):02d},{int(round((seconds % 1) * 1000)):03d} -->" in srt


# ---------- גופן וערכות ----------
def test_fonts_are_names_not_paths(env):
    assert de.clean_fonts(["Rubik", "Segoe UI"]) == ["Rubik", "Segoe UI"]
    for bad in ([], ["C:\\Windows\\Fonts\\x.ttf"], ["a"] * 7, "Rubik"):
        with pytest.raises(de.EpisodeError):
            de.clean_fonts(bad)
    de.update_override_fields(env["data"], "tiny", {"theme_overrides.fonts": ["Rubik", "Arial"]}, [])
    assert de.editor_data(env["data"], "tiny")["theme"]["fonts"] == ["Rubik", "Arial"]
    assert _unchanged(env)


def test_kits_carry_the_font_and_the_clips(env):
    de.update_override_fields(env["data"], "tiny", {"theme_overrides.fonts": ["Rubik", "Arial"], "bumpers.intro": env["intro"]}, [])
    dk.save_kit(env["data"], "ערוץ", dk.kit_from_episode(env["data"], "tiny"))
    kit = dk.load_kits(env["data"])["ערוץ"]
    assert kit["theme_overrides"]["fonts"] == ["Rubik", "Arial"] and kit["bumpers"] == {"intro": os.path.abspath(env["intro"])}
    summary = dk.kits_summary(env["data"])[0]
    assert summary["font"] == "Rubik" and summary["bumpers"] == ["intro.mp4"]
    write_episode(os.path.dirname(env["folder"]), name="other", overrides=TINY)
    dk.apply_kit(env["data"], "other", "ערוץ")
    over = de.load_overrides_for_path(os.path.join(os.path.dirname(env["folder"]), "other"))
    assert over["bumpers"]["intro"] == os.path.abspath(env["intro"]) and over["theme_overrides"]["fonts"][0] == "Rubik"
    brand = dk.kit_from_brand({"fields": {"caption_font": "Rubik", "intro_path": env["intro"], "outro_path": ""}})
    assert brand["theme_overrides"]["fonts"][0] == "Rubik" and brand["bumpers"] == {"intro": env["intro"]}
    assert "fonts" not in dk.kit_from_brand({"fields": {"caption_font": "C:/x/font.ttf"}}).get("theme_overrides", {})


def test_the_fonts_route_lists_installed_fonts(env, monkeypatch):
    from entrypoints.web.routes import dataviz as routes
    monkeypatch.setitem(routes._fonts_cache, "fonts", ["Arial", "Rubik"])
    assert client.get("/api/dataviz/fonts").json() == {"fonts": ["Arial", "Rubik"]}


# ---------- עדכון נתונים למקור Excel ----------
def test_update_data_for_an_excel_source_saves_a_csv(env, tmp_path):
    folder = os.path.join(env["data"], "dataviz_episodes", "xl")
    os.makedirs(folder)
    pd.DataFrame({"date": ["2020-01-01", "2020-01-02", "2020-01-03"], "city": ["A", "B", "A"], "n": [1, 2, 3]}).to_excel(
        os.path.join(folder, "data.xlsx"), index=False)
    with open(os.path.join(folder, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"title": "אקסל", "sources": [{"path": "data.xlsx", "sheet": 0, "time": {"column": "date"},
                                                    "value": {"column": "n"}, "entity": {"column": "city"}}]}, f, allow_unicode=True)
    before = open(os.path.join(folder, "data.xlsx"), "rb").read()
    csv = "date,city,n\n2020-01-01,A,5\n2020-01-02,B,5\n2020-01-04,C,1\n"
    preview = dd.update_data(env["data"], "xl", 0, csv, confirm=False)
    assert preview["total_after"] == 11 and preview["new"] == ["C"]
    saved = dd.update_data(env["data"], "xl", 0, csv, confirm=True)
    source = de.load_overrides_for_path(folder)["sources"][0]
    assert saved["saved"] and source["type"] == "csv" and "sheet" not in source and source["path"].endswith(".csv")
    assert open(os.path.join(folder, "data.xlsx"), "rb").read() == before


# ---------- סל המיחזור ----------
def test_trash_takes_a_share_folder_and_the_new_companions(env, monkeypatch):
    out = env["workspace"] / "dataviz" / "outputs" / "horizontal"
    (out / "tiny_share").mkdir(parents=True)
    for name in ("tiny.mp4", "tiny.srt", "tiny_thumb_c1.jpg", "tiny_thumb_original.jpg", "tiny_other.mp4"):
        (out / name).write_bytes(b"x")
    trashed = []
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(os.path.basename(p)))
    assert client.post("/api/dataviz/outputs/trash", json={"orientation": "horizontal", "name": "tiny_share"}).status_code == 200
    assert client.post("/api/dataviz/outputs/trash", json={"orientation": "horizontal", "name": "tiny.mp4"}).status_code == 200
    assert sorted(trashed) == ["tiny.mp4", "tiny.srt", "tiny_share", "tiny_thumb_c1.jpg", "tiny_thumb_original.jpg"]
    assert json.dumps(trashed).count("tiny_other") == 0
