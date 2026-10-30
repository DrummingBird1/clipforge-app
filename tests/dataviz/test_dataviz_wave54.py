# tests/dataviz/test_dataviz_wave54.py - גל 54 בעורך הגרפים, "הרינדור": קידוד ב-NVENC (עם חזרה ל-x264 כשנכשל), מטמון מקטעים
# (שינוי של הפתיח או הסיום מרנדר רק אותם), ואומדן זמן שלומד מריצות אמיתיות. הפקודות נבדקות בלי ffmpeg; רינדור אמיתי
# אחד, זעיר (20 פריימים), רק כשיש ffmpeg במחשב.
import copy
from tests import PROJECT_ROOT
import importlib.util
import json
import os


import pytest

from dataviz import render
from dataviz.config import ConfigError, load_config
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from tests.dataviz_helpers import write_episode
from tests.media_support import needs_ffmpeg
from dataviz.web import preview as dataviz_preview

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 40},
         "timing": {"test_main_seconds": 1, "test_intro_seconds": 0.5, "test_outro_seconds": 0.5}}
SCRIPT = os.path.join(PROJECT_ROOT, "my_scripts", "video", "dataviz_maker.py")


# ---------- המקודד ----------
def test_cpu_encoding_is_exactly_the_old_command():
    video = {"preset": "veryfast", "crf": 18}
    cmd = render.ffmpeg_command("ffmpeg", (320, 200), 10, 2.0, "out.mp4", video)
    assert cmd == ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "320x200", "-r", "10", "-i", "-",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-t", "2.000", "out.mp4"]
    nvenc = render.ffmpeg_command("ffmpeg", (320, 200), 10, 2.0, "out.mp4", video, encoder="nvenc")
    assert nvenc[nvenc.index("-c:v"):nvenc.index("-t")] == ["-c:v", "h264_nvenc", "-preset", "p3", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"]


def test_auto_uses_nvenc_only_when_ffmpeg_can(monkeypatch):
    monkeypatch.setattr(render, "_NVENC", {})
    calls = []

    class Result:
        def __init__(self, code):
            self.returncode = code

    assert render.nvenc_available("ff-ok", runner=lambda cmd, **k: calls.append(cmd) or Result(0)) is True
    assert render.nvenc_available("ff-ok", runner=lambda cmd, **k: calls.append(cmd) or Result(1)) is True   # נשמר
    assert render.nvenc_available("ff-bad", runner=lambda cmd, **k: Result(1)) is False
    assert len(calls) == 1 and "h264_nvenc" in calls[0]
    assert render.resolve_encoder({"encoder": "auto"}, "ff-ok") == "nvenc"
    assert render.resolve_encoder({"encoder": "auto"}, "ff-bad") == "libx264"
    assert render.resolve_encoder({"encoder": "cpu"}, "ff-ok") == "libx264"
    assert render.resolve_encoder({}, "ff-ok") == "libx264"


def test_a_failed_nvenc_render_is_redone_with_x264(monkeypatch, tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides={**SMALL, "video": {**SMALL["video"], "encoder": "nvenc"}}))
    tried = []

    def fake_render(episode, plan, out_path, ffmpeg, workers, progress, chart, chunksize, segment_cache, encoder):
        tried.append(encoder)
        if encoder == "nvenc":
            raise render.FfmpegError("NVENC not available")
        with open(out_path, "wb") as f:   # 23.10.2026: render_video משנה את השם של מה שנכתב (test_dataviz_render_partial_file.py)
            f.write(b"video")
        return {"path": out_path, "frames": len(plan)}

    monkeypatch.setattr(render, "_render", fake_render)
    result = render.render_video(episode, build_plan(episode, "test"), str(tmp_path / "o.mp4"))
    assert tried == ["nvenc", "libx264"] and result["encoder"] == "libx264"
    with pytest.raises(ConfigError):
        load_config(os.path.join(write_episode(tmp_path / "b", overrides={"video": {"encoder": "gpu"}}), "config.yaml"))


# ---------- מטמון המקטעים ----------
def _ctx_and_plan(tmp_path, **extra):
    episode = load_episode(write_episode(tmp_path, overrides={**SMALL, **extra}))
    return render.chart_context(episode), build_plan(episode, "full"), episode.config["video"]


def test_segments_split_by_kind_and_keys_follow_only_what_draws_them(tmp_path):
    ctx, plan, video = _ctx_and_plan(tmp_path / "a", teaser={"enabled": True, "seconds": 1, "label": "x"})
    segments = render.plan_segments(plan)
    assert [kind for _a, _b, kind in segments] == ["teaser", "intro", "main", "outro"]
    assert segments[0][0] == 0 and segments[-1][1] == len(plan) and all(a < b for a, b, _k in segments)

    def keys(context, frames=plan):
        return {kind: render.segment_key(context, frames[a:b], kind, video, 10, "libx264") for a, b, kind in render.plan_segments(frames)}

    base = keys(ctx)
    intro_changed = keys({**ctx, "intro": {**ctx["intro"], "title": "פתיח אחר"}})
    assert intro_changed["intro"] != base["intro"] and {k: intro_changed[k] for k in ("teaser", "main", "outro")} == {k: base[k] for k in ("teaser", "main", "outro")}
    outro_changed = keys({**ctx, "credits": ["מקור חדש"]})
    assert outro_changed["outro"] != base["outro"] and outro_changed["main"] == base["main"] and outro_changed["intro"] == base["intro"]
    assert keys({**ctx, "title": "כותרת אחרת"})["main"] != base["main"]
    changed_plan = copy.deepcopy(plan)
    changed_plan[segments[2][0] + 3]["total"] += 1
    assert keys(ctx, changed_plan)["main"] != base["main"] and keys(ctx, changed_plan)["intro"] == base["intro"]
    assert render.segment_key(ctx, plan[:5], "main", video, 10, "nvenc") != render.segment_key(ctx, plan[:5], "main", video, 10, "libx264")


def test_concat_command_copies_the_video_and_fades_the_music():
    cmd = render.concat_command("ffmpeg", "list.txt", 12.0, "out.mp4", {"start": 3, "fade_in": 2, "fade_out": 6, "bitrate": "192k"}, "m.mp3")
    assert cmd[:9] == ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i"] and "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-ss") + 1] == "3" and "afade=t=out:st=6.00:d=6" in cmd[cmd.index("-af") + 1] and cmd[-1] == "out.mp4"


@needs_ffmpeg
def test_a_second_render_reuses_unchanged_segments(tmp_path):
    from utils.ffmpeg_locator import get_ffmpeg_exe
    cache = str(tmp_path / "segments")
    episode = load_episode(write_episode(tmp_path / "ep", overrides=SMALL))
    first = render.render_video(episode, build_plan(episode, "test"), str(tmp_path / "a.mp4"), ffmpeg=get_ffmpeg_exe(), workers=2, segment_cache=cache)
    assert first["cached_frames"] == 0 and os.path.getsize(tmp_path / "a.mp4") > 0 and len(os.listdir(cache)) == 3
    changed = load_episode(write_episode(tmp_path / "ep", overrides={**SMALL, "intro": {"title": "פתיח חדש"}}))
    plan = build_plan(changed, "test")
    second = render.render_video(changed, plan, str(tmp_path / "b.mp4"), ffmpeg=get_ffmpeg_exe(), workers=2, segment_cache=cache)
    intro = sum(1 for f in plan if f["k"] == "intro")
    assert second["cached_frames"] == len(plan) - intro and second["frames"] == len(plan)
    assert len(os.listdir(cache)) == 4 and not [n for n in os.listdir(tmp_path) if n.endswith(".segments.txt")]


# ---------- אומדן שלומד ----------
def test_the_estimate_learns_from_real_runs(tmp_path, monkeypatch):
    folder = write_episode(tmp_path / "ep", overrides={"video": {"width": 1000, "height": 1000, "fps": 10, "dpi": 40}})
    stats = tmp_path / "stats.json"
    guess = dataviz_preview.estimate(folder, {}, workers=4, stats_path=str(stats))
    assert guess["learned_runs"] == 0
    # שתי ריצות: 1.0 ו-1.5 שניות-תהליך למגה-פיקסל אחרי התקורה הקבועה; עם ריצה שכל הפריימים שלה מהמטמון (לא נספרת).
    # סבב הייצוב: החציון של הריצות שלא איטיות פי 2 מהמהירה - כאן שתיהן (test_dataviz_dogfood.py בודק את השאר)
    overhead = dataviz_preview.RUN_OVERHEAD_SECONDS
    stats.write_text(json.dumps({"runs": [
        {"frames": 100, "rendered_frames": 100, "pixels": 1_000_000, "workers": 2, "seconds": overhead + 50},
        {"frames": 100, "rendered_frames": 100, "pixels": 1_000_000, "workers": 3, "seconds": overhead + 50},
        {"frames": 100, "rendered_frames": 0, "pixels": 1_000_000, "workers": 2, "seconds": 3}]}), encoding="utf-8")
    assert dataviz_preview.learned_rate(str(stats)) == (1.25, 2)
    learned = dataviz_preview.estimate(folder, {}, workers=3, stats_path=str(stats))
    full = learned["modes"]["full"]
    extra = dataviz_preview.RUN_OVERHEAD_SECONDS + dataviz_preview.START_SECONDS
    assert learned["learned_runs"] == 2 and full["render_seconds"] == round(full["frames"] * 1.25 / 3 + extra, 0)


def test_the_script_records_its_render_time(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dataviz_maker_w54", SCRIPT)
    maker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maker)
    from utils import data_dir
    monkeypatch.setattr(data_dir, "DATA_DIR", str(tmp_path))
    for n in range(maker.MAX_STATS + 3):
        maker.record_render_time("full", {"frames": 100 + n, "cached_frames": 40, "size": [640, 360], "encoder": "libx264"}, 4, 12.5)
    runs = json.loads((tmp_path / maker.STATS_FILE).read_text(encoding="utf-8"))["runs"]
    assert len(runs) == maker.MAX_STATS and runs[-1] == {"mode": "full", "frames": 152, "rendered_frames": 112, "pixels": 640 * 360,
                                                         "workers": 4, "seconds": 12.5, "encoder": "libx264"}
    args = type("Args", (), {"output_dir": str(tmp_path / "out")})()
    assert maker.output_base(args) == str(tmp_path / "out")
    assert maker.segment_cache_dir(args) == os.path.join(str(tmp_path / "out"), ".cache", "dataviz_segments")   # 19.10.2026: תחת .cache
