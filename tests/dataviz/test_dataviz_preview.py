# tests/dataviz/test_dataviz_preview.py - גל 38: פריים בודד לתצוגה חיה ואומדן אורך/זמן (utils/dataviz_preview.py + routes)
#
# פריים אחד של matplotlib בגודל קטן - בלי ffmpeg ובלי רינדור סרטון. הפרק סינתטי (tests/dataviz_helpers.py).
import os


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import preview as dataviz_preview

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    folder = write_episode(data / "dataviz_episodes", name="tiny")
    return {"folder": folder, "cache": str(workspace / ".cache" / "dataviz_previews")}


def test_a_frame_is_a_png_and_cached(env):
    first = dataviz_preview.preview_frame(env["folder"], {}, env["cache"], 0.6, scale=0.2)
    assert first["frames"] > 10 and 0 < first["index"] < first["frames"]
    with open(first["path"], "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    again = dataviz_preview.preview_frame(env["folder"], {}, env["cache"], 0.6, scale=0.2)
    assert again["path"] == first["path"]          # אותו פריים - מהמטמון
    other = dataviz_preview.preview_frame(env["folder"], {}, env["cache"], 0.6, scale=0.2, theme="dark")
    assert other["path"] != first["path"]          # ערכת צבעים אחרת - תמונה אחרת


def test_position_maps_to_the_start_and_the_end(env):
    start = dataviz_preview.preview_frame(env["folder"], {}, env["cache"], 0.0, scale=0.2)
    end = dataviz_preview.preview_frame(env["folder"], {}, env["cache"], 1.0, scale=0.2)
    assert start["index"] == 0 and start["kind"] == "intro"
    assert end["index"] == end["frames"] - 1 and end["kind"] == "outro"


def test_estimate_lists_every_mode(env):
    est = dataviz_preview.estimate(env["folder"], {}, workers=2)
    assert set(est["modes"]) == {"full", "test", "preview", "shorts"}   # 23.10.2026 (המלצה 10): גם Shorts
    assert est["modes"]["full"]["frames"] > est["modes"]["preview"]["frames"]
    assert est["modes"]["full"]["seconds"] > 0 and est["modes"]["full"]["render_seconds"] > 0


def test_routes_validate_and_serve(env):
    resp = client.get("/api/dataviz/preview_frame", params={"episode": "tiny", "pos": 0.5, "scale": 0.2, "chart": "line_race"})
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/png"
    assert int(resp.headers["x-frame-count"]) > 10
    assert client.get("/api/dataviz/preview_frame", params={"episode": "nope"}).status_code == 404
    assert client.get("/api/dataviz/preview_frame", params={"episode": "tiny", "chart": "pie"}).status_code == 400
    assert client.get("/api/dataviz/preview_frame", params={"episode": "../x"}).status_code == 404
    assert set(client.get("/api/dataviz/estimate", params={"episode": "tiny"}).json()["modes"]) == {"full", "test", "preview", "shorts"}


def test_unsaved_settings_change_the_frame_but_not_the_episode(env):
    base = {"episode": "tiny", "pos": 0.5, "scale": 0.2}
    plain = client.get("/api/dataviz/preview_frame", params=base).content
    titled = client.get("/api/dataviz/preview_frame", params={**base, "title": "כותרת אחרת", "top_n": 5})
    assert titled.status_code == 200 and titled.content != plain
    assert client.get("/api/dataviz/preview_frame", params={**base, "top_n": 99}).status_code == 400
    assert not os.path.exists(os.path.join(os.path.dirname(env["folder"]), "..", "dataviz_overrides", "tiny.json"))
