# tests/dataviz/test_dataviz_live_preview.py
#
# 20.10.2026: התצוגה החיה בזמן עריכה - live=1 מחזיר GIF חד יותר (כ-500 פיקסלים, 12 פריימים לשנייה) מאותה תכנית בלי לרנדר
# סרטון, ובקשה שהוחלפה בבקשה חדשה יותר לאותו פרק נעצרת באמצע (409 superseded) במקום להחזיק את המנעול עד הסוף.
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dataviz.web import preview as dp
from entrypoints import web_app
from entrypoints.web.routes import dataviz as routes
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

VIDEO = {"video": {"width": 640, "height": 400, "fps": 24, "dpi": 40}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    folder = write_episode(data / "dataviz_episodes", overrides=VIDEO, name="tiny")
    return {"folder": folder, "cache": str(workspace / ".cache" / "dataviz_previews")}


def test_a_cancelled_clip_stops_between_frames_and_writes_nothing(env):
    calls = []

    def cancel():
        calls.append(1)
        return len(calls) > 3
    with pytest.raises(dp.PreviewCancelled):
        dp.preview_clip(env["folder"], {}, env["cache"], 0.5, cancel=cancel)
    assert len(calls) == 4                                              # עצר אחרי 3 פריימים, לא אחרי 30
    assert not os.path.isdir(env["cache"]) or not [n for n in os.listdir(env["cache"]) if n.endswith(".gif")]


def test_the_live_clip_is_sharper_and_smoother(env):
    plain = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.5})
    live = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.5, "live": 1})
    assert plain.status_code == 200 and live.status_code == 200 and live.headers["content-type"] == "image/gif"
    with Image.open(io.BytesIO(plain.content)) as a, Image.open(io.BytesIO(live.content)) as b:
        assert b.size[0] > a.size[0] * 1.5                               # 0.35 מול 0.2 מהגודל
        assert b.n_frames == 36 and 80 <= b.info["duration"] <= 90   # 3 שניות ב-12 פריימים לשנייה (GIF מעגל ל-10ms)


def test_an_older_live_request_is_superseded_by_a_newer_one(env, monkeypatch):
    real = dp.preview_clip
    answers = {}

    def first_then_second(*args, **kwargs):
        if "first" not in answers:
            answers["first"] = "started"
            answers["second"] = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.6, "live": 1})   # בזמן שהראשונה מרנדרת
        return real(*args, **kwargs)
    monkeypatch.setattr(routes.dataviz_preview, "preview_clip", first_then_second)
    first = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.4, "live": 1})
    assert answers["second"].status_code == 200
    assert first.status_code == 409 and first.json()["superseded"] is True
    plain = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.4})   # בלי live - אין ביטול
    assert plain.status_code == 200
