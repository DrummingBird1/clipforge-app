# tests/dataviz/test_dataviz_wave44.py - גל 44 בעורך הגרפים: שלוש תמונות ממוזערות לבחירה (המקורית נשמרת בצד), הצעת טקסטים
# מ-Gemini (לא נשמרת), צפיות מיוטיוב שנשמרות בחבילה, ותור פרקים עם מצב לכל פרק ודילוג - גם לפרק שרץ. ffmpeg,
# Gemini, יוטיוב והרינדור מוחלפים; שום דבר לא נשלח ושום פרק קיים לא משתנה.
import importlib.util
from tests import PROJECT_ROOT
import json
import os
import sys


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web.script_args import _args_dataviz
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import publish as dpub

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False
BASE_DIR = PROJECT_ROOT


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    out = workspace / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    (out / "tiny.mp4").write_bytes(b"video")
    (out / "tiny_thumb.jpg").write_bytes(b"first")
    sidecar = out / "tiny.publish.json"
    sidecar.write_text(json.dumps({"status": "approved", "video": "tiny.mp4", "thumbnail": "tiny_thumb.jpg",
                                   "metadata": {"title": "ישן", "youtube_title": "כותרת"}}), encoding="utf-8")
    return {"data": data, "out": out, "sidecar": sidecar}


def _fake_extract(video, ts, out, ffmpeg):
    open(out, "w").write(f"{ts:.1f}")
    return True


def _fake_draw(frame, title, out):
    open(out, "w", encoding="utf-8").write(open(frame).read() + "|" + title)


# ---------- תמונות ממוזערות ----------
def test_three_candidates_and_choosing_keeps_the_original(env):
    names = dpub.thumbnail_candidates(str(env["sidecar"]), extract=_fake_extract, draw=_fake_draw, duration=10)
    assert names == ["tiny_thumb_c1.jpg", "tiny_thumb_c2.jpg", "tiny_thumb_c3.jpg"]
    assert (env["out"] / "tiny_thumb_c2.jpg").read_text(encoding="utf-8") == "6.0|כותרת"
    dpub.choose_thumbnail(str(env["sidecar"]), 2)
    dpub.choose_thumbnail(str(env["sidecar"]), 3)
    assert (env["out"] / "tiny_thumb.jpg").read_text(encoding="utf-8") == "9.0|כותרת"
    assert (env["out"] / "tiny_thumb_original.jpg").read_bytes() == b"first"     # רק המקורית הראשונה
    with pytest.raises(ValueError):
        dpub.choose_thumbnail(str(env["sidecar"]), 7)
    dpub.record_send(str(env["sidecar"]), "rocket", {})
    with pytest.raises(ValueError):
        dpub.choose_thumbnail(str(env["sidecar"]), 1)


def test_candidate_routes(env, monkeypatch):
    real = dpub.thumbnail_candidates

    def fake(path, **kw):
        return real(path, extract=_fake_extract, draw=_fake_draw, duration=10)

    monkeypatch.setattr(dpub, "thumbnail_candidates", fake)
    resp = client.post("/api/dataviz/packages/horizontal/tiny/thumbnail_candidates", json={})
    assert resp.status_code == 200 and resp.json()["candidates"] == [1, 2, 3]
    assert client.get("/api/dataviz/packages/horizontal/tiny/thumbnail_candidate/2").status_code == 200
    assert client.get("/api/dataviz/packages/horizontal/tiny/thumbnail_candidate/9").status_code == 404
    assert client.post("/api/dataviz/packages/horizontal/tiny/thumbnail_choose", json={"candidate": 1}).status_code == 200
    assert client.post("/api/dataviz/packages/horizontal/tiny/thumbnail_choose", json={"candidate": "x"}).status_code == 400


# ---------- הצעה מ-Gemini וצפיות ----------
def test_gemini_suggestion_is_cleaned_and_not_saved(env, monkeypatch):
    s = dpub.suggest_metadata(str(env["sidecar"]), generate=lambda v: {"title": "x" * 300, "description": "תיאור", "hashtags": ["נתונים", "#a"]})
    assert len(s["title"]) == dpub.METADATA_LIMITS["youtube_title"] and s["hashtags"][:2] == ["#נתונים", "#a"]
    assert dpub.load_package(str(env["sidecar"]))["metadata"]["youtube_title"] == "כותרת"
    monkeypatch.setattr(dpub, "suggest_metadata", lambda path: (_ for _ in ()).throw(RuntimeError("GEMINI_API_KEY לא מוגדר")))
    resp = client.post("/api/dataviz/packages/horizontal/tiny/suggest", json={})
    assert resp.status_code == 400 and "GEMINI_API_KEY" in resp.json()["error"]


def test_stats_need_an_upload_and_are_kept_in_the_package(env, monkeypatch, tmp_path):
    assert client.post("/api/dataviz/packages/horizontal/tiny/stats", json={}).status_code == 400   # עוד לא הועלה
    dpub.record_send(str(env["sidecar"]), "youtube", {"video_id": "abc"})
    from utils import youtube_analytics, youtube_uploader
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(tmp_path / "missing.json"))
    assert "חיבור" in client.post("/api/dataviz/packages/horizontal/tiny/stats", json={}).json()["error"]
    (tmp_path / "token.json").write_text("{}")
    monkeypatch.setattr(youtube_uploader, "TOKEN_FILE", str(tmp_path / "token.json"))
    monkeypatch.setattr(youtube_analytics, "get_video_stats", lambda vid: {"views": 1234, "likes": 56, "comments": 7})
    resp = client.post("/api/dataviz/packages/horizontal/tiny/stats", json={})
    assert resp.status_code == 200 and resp.json()["stats"]["views"] == 1234
    listed = next(p for p in client.get("/api/dataviz/packages").json() if p["name"] == "tiny")
    assert listed["stats"]["likes"] == 56


# ---------- תור הפרקים ----------
def test_queue_files_are_written_by_the_run_route_and_skips_by_the_screen(env, monkeypatch):
    for name in ("a", "b"):
        write_episode(env["data"] / "dataviz_episodes", name=name)
    calls = []
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: calls.append(payload) or {"ok": True})
    assert client.post("/api/dataviz/run", json={"episodes": ["a", "b"], "mode": "test"}).status_code == 200
    queue_file = calls[0]["dv_queue_file"]
    assert os.path.basename(queue_file) == "dataviz_queue.json" and os.path.isfile(queue_file)
    assert _args_dataviz(calls[0])[-2:] == ["--queue-file", queue_file]
    assert "--queue-file" not in _args_dataviz({**calls[0], "dv_queue_file": "C:/x/other.json"})
    assert [e["state"] for e in client.get("/api/dataviz/queue").json()["episodes"]] == ["pending", "pending"]
    assert client.post("/api/dataviz/queue/skip", json={"episode": "b"}).json()["skip"] == ["b"]
    assert client.post("/api/dataviz/queue/skip", json={"episode": "zzz"}).status_code == 404
    assert client.get("/api/dataviz/queue").json()["skip"] == ["b"]


@pytest.fixture
def maker():
    spec = importlib.util.spec_from_file_location("dataviz_maker_w44", os.path.join(BASE_DIR, "my_scripts", "video", "dataviz_maker.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_skips_queued_episodes_and_stops_a_running_one(maker, tmp_path, monkeypatch, capsys):
    queue_file = str(tmp_path / "dataviz_queue.json")
    (tmp_path / "dataviz_queue.control.json").write_text(json.dumps({"skip": ["b"]}), encoding="utf-8")
    paths = [str(tmp_path / n) for n in ("a", "b", "c")]
    monkeypatch.setattr(maker, "find_episodes", lambda input_dir, name, root: [p for p in paths if p.endswith(name)])
    rendered = []

    def fake_render(path, mode, args, progress, results, queue=None, **_kw):   # גל 55: גם lang
        name = os.path.basename(path)
        rendered.append(name)
        if name == "c":
            raise maker.QueueSkip()
        results["files_created"] += 1

    monkeypatch.setattr(maker, "render_episode", fake_render)
    monkeypatch.setattr(sys, "argv", ["dataviz_maker.py", "--episodes", "a,b,c", "--mode", "test", "--queue-file", queue_file])
    maker.main()
    states = {e["name"]: e["state"] for e in json.load(open(queue_file, encoding="utf-8"))["episodes"]}
    assert rendered == ["a", "c"] and states == {"a": "done", "b": "skipped", "c": "skipped"}
    result = json.loads([line for line in capsys.readouterr().out.splitlines() if line.startswith("RESULT:")][-1][7:])
    assert result["skipped"] == 2 and result["files_created"] == 1


def test_the_progress_hook_raises_when_the_running_episode_is_skipped(maker, tmp_path, monkeypatch):
    folder = write_episode(tmp_path, name="tiny", overrides={"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}})
    queue = maker.QueueTracker(str(tmp_path / "dataviz_queue.json"), ["tiny"])
    (tmp_path / "dataviz_queue.control.json").write_text(json.dumps({"skip": ["tiny"]}), encoding="utf-8")
    import dataviz

    def fake_stills(episode, plan, target, chart=None, progress=None):
        progress(1, 4)
        return []

    monkeypatch.setattr(dataviz, "render_stills", fake_stills)
    args = type("A", (), {"target": "", "chart": None, "output_dir": str(tmp_path / "out"), "workers": 1})()
    with pytest.raises(maker.QueueSkip):
        maker.render_episode(folder, "stills", args, lambda done, total: None, {"errors": 0, "files_created": 0}, queue=queue)
    assert queue.episodes[0]["pct"] == 25
