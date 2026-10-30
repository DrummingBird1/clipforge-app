# tests/dataviz/test_dataviz_series_publish.py - גל 41: יעדים (Shorts/TikTok לאורך), תור של כמה פרקים, שכפול והפרק הבא
# בסדרה, פרק חדש מתבנית, ערכות ערוץ (מפרק / ממיתוג של עורך-העל), סל מיחזור לתוצרים, עריכת טקסטים של חבילה
# ותזמון פרסום. שום פרק קיים לא משתנה; send2trash מוחלף - שום קובץ לא עובר לסל המיחזור האמיתי.
import hashlib
import json
import os
from datetime import datetime, timedelta


import pytest
from fastapi.testclient import TestClient

from dataviz.config import load_config
from dataviz.targets import apply_target
from entrypoints import web_app
from entrypoints.web.script_args import _args_dataviz
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web import kits as dk
from dataviz.web import publish as dpub

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

CSV = "date,city,n\n" + "".join(f"2020-0{m}-{d:02d},{city},{m * d}\n" for m in (1, 2, 3) for d in (1, 15) for city in ("A", "B"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides={"series": {"name": "שנים", "number": 3}})
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": str(data), "folder": folder, "workspace": workspace, "md5": md5}


def _unchanged(env):
    return {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == env["md5"]


def test_targets_make_a_vertical_copy_with_its_own_name(env):
    config = load_config(os.path.join(env["folder"], "config.yaml"))
    assert apply_target(config, "youtube")["video"] == config["video"]
    shorts = apply_target(config, "shorts")
    assert (shorts["video"]["width"], shorts["video"]["height"]) == (1080, 1920)
    assert shorts["video"]["output_name"] == "tiny_shorts" and config["video"]["width"] == 1440
    with pytest.raises(ValueError):
        apply_target(config, "vimeo")


def test_run_args_for_target_and_several_episodes():
    assert _args_dataviz({"dv_mode": "full", "dv_target": "tiktok", "dv_episodes": ["a", "b-2", "../x"]}) == [
        "--mode", "full", "--target", "tiktok", "--episodes", "a,b-2"]
    assert _args_dataviz({"dv_mode": "full", "dv_target": "nope"}) == ["--mode", "full"]


def test_run_route_accepts_episodes_and_target(env, monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: calls.append((folder, payload)) or {"ok": True})
    write_episode(os.path.dirname(env["folder"]), name="other")
    resp = client.post("/api/dataviz/run", json={"episodes": ["tiny", "other"], "mode": "test", "target": "shorts"})
    assert resp.status_code == 200
    folder, payload = calls[0]
    assert folder.endswith("dataviz_episodes") and payload["dv_episodes"] == ["tiny", "other"] and payload["dv_target"] == "shorts"
    assert client.post("/api/dataviz/run", json={"episodes": ["tiny", "ghost"], "mode": "test"}).status_code == 400
    assert client.post("/api/dataviz/run", json={"episode": "tiny", "mode": "test", "target": "vimeo"}).status_code == 400


def test_duplicate_and_next_in_series(env):
    de.update_override_fields(env["data"], "tiny", {"intro.title": "פתיח"}, [])
    copy = de.duplicate_episode(env["data"], "tiny", "tiny-copy")
    assert copy["valid"] and de.load_overrides_for_path(os.path.join(os.path.dirname(env["folder"]), "tiny-copy")) == {"intro": {"title": "פתיח"}}
    nxt = de.duplicate_episode(env["data"], "tiny", "tiny-4", next_in_series=True)
    over = de.load_overrides_for_path(os.path.join(os.path.dirname(env["folder"]), "tiny-4"))
    assert nxt["valid"] and over["series"] == {"name": "שנים", "number": 4}
    with pytest.raises(de.EpisodeError) as e:
        de.duplicate_episode(env["data"], "tiny", "tiny-copy")
    assert e.value.status == 409
    with pytest.raises(de.EpisodeError):
        de.duplicate_episode(env["data"], "tiny", "../bad")
    assert _unchanged(env)


def test_new_episode_from_a_template_inherits_the_design(env):
    de.update_override_fields(env["data"], "tiny", {"timing.step": 0.004, "theme_overrides.accent": "#112233"}, [])
    form = {"name": "from-tpl", "title": "חדש", "subtitle": "", "chart": "line_race", "theme": "dark", "time_column": "date",
            "value_column": "n", "group_column": "city", "period": "day", "csv_text": CSV, "template": "tiny"}
    summary = de.create_episode(env["data"], form)
    config = load_config(os.path.join(os.path.dirname(env["folder"]), "from-tpl", "config.yaml"))
    assert summary["valid"] and config["title"] == "חדש" and config["chart"] == "line_race"
    assert config["timing"]["step"] == 0.004 and config["theme_overrides"]["accent"] == "#112233"
    assert config["series"] == {"name": "שנים", "number": 4}
    assert _unchanged(env)


def test_channel_kits_from_episode_and_brand_and_apply(env, tmp_path):
    logo = tmp_path / "logo.png"
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(1, 1))
    fig.savefig(logo)
    plt.close(fig)
    de.update_override_fields(env["data"], "tiny", {"theme_overrides.accent": "#aa0000", "logo.path": str(logo)}, [])
    dk.save_kit(env["data"], "הערוץ", dk.kit_from_episode(env["data"], "tiny"))
    kits = dk.load_kits(env["data"])
    assert kits["הערוץ"]["theme_overrides"]["accent"] == "#aa0000" and kits["הערוץ"]["logo"]["path"] == str(logo)
    write_episode(os.path.dirname(env["folder"]), name="other")
    dk.apply_kit(env["data"], "other", "הערוץ")
    over = de.load_overrides_for_path(os.path.join(os.path.dirname(env["folder"]), "other"))
    assert over["theme_overrides"]["accent"] == "#aa0000" and over["logo"]["path"] == str(logo)
    brand = dk.kit_from_brand({"fields": {"watermark_path": str(logo), "watermark_position": "top-left", "progress_bar_color": "#00FF00"}})
    assert brand["logo"]["position"] == "top-left" and brand["theme_overrides"] == {"accent": "#00ff00"}
    with pytest.raises(de.EpisodeError):
        dk.save_kit(env["data"], "ריק", {})
    assert dk.delete_kit(env["data"], "הערוץ") and not dk.delete_kit(env["data"], "הערוץ")


def test_trash_moves_the_video_with_its_package_files(env, monkeypatch):
    out = env["workspace"] / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    for name in ("tiny.mp4", "tiny.publish.json", "tiny_thumb.jpg", "tiny_metadata_seo.txt", "tiny.chapters.txt", "other.mp4"):
        (out / name).write_bytes(b"x")
    trashed = []
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(os.path.basename(p)) or os.remove(p))
    resp = client.post("/api/dataviz/outputs/trash", json={"orientation": "horizontal", "name": "tiny.mp4"})
    assert resp.status_code == 200 and sorted(trashed) == ["tiny.chapters.txt", "tiny.mp4", "tiny.publish.json",   # גל 56: גם פרקי יוטיוב (גל 55)
                                                                 "tiny_metadata_seo.txt", "tiny_thumb.jpg"]
    assert (out / "other.mp4").exists()
    assert client.post("/api/dataviz/outputs/trash", json={"orientation": "horizontal", "name": "../x.mp4"}).status_code in (400, 404)
    assert client.post("/api/dataviz/outputs/trash", json={"orientation": "nope", "name": "other.mp4"}).status_code == 400


def _package(env):
    out = env["workspace"] / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True, exist_ok=True)
    (out / "tiny.mp4").write_bytes(b"x")
    sidecar = out / "tiny.publish.json"
    sidecar.write_text(json.dumps({"status": "approved", "video": "tiny.mp4", "metadata": {"title": "ישן", "hashtags": ["#a"]}}), encoding="utf-8")
    return sidecar


def test_package_metadata_and_scheduled_send_validation(env):
    sidecar = _package(env)
    resp = client.post("/api/dataviz/packages/horizontal/tiny/metadata", json={"youtube_title": "כותרת חדשה", "hashtags": ["שנים", "#נתונים"]})
    assert resp.status_code == 200
    meta = json.loads(sidecar.read_text(encoding="utf-8"))["metadata"]
    assert meta["youtube_title"] == "כותרת חדשה" and meta["hashtags"][:2] == ["#שנים", "#נתונים"]
    assert client.post("/api/dataviz/packages/horizontal/tiny/metadata", json={"youtube_title": "x" * 200}).status_code == 400
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes")
    future = (datetime.now() + timedelta(days=1)).isoformat(timespec="minutes")
    assert client.post("/api/dataviz/packages/horizontal/tiny/send", json={"target": "youtube", "confirm": True, "publish_at": past}).status_code == 400
    assert client.post("/api/dataviz/packages/horizontal/tiny/send", json={"target": "rocket", "confirm": True, "publish_at": future}).status_code == 400
    dpub.record_send(str(sidecar), "youtube", {"video_id": "abc123", "publish_at": "2030-01-01T10:00:00Z"})
    listed = next(p for p in client.get("/api/dataviz/packages").json() if p["name"] == "tiny")
    assert listed["sent_info"]["youtube"]["video_id"] == "abc123" and listed["sent_info"]["youtube"]["publish_at"]
    with pytest.raises(ValueError):
        dpub.update_metadata(str(sidecar), {"title": "אחרי שליחה"})
