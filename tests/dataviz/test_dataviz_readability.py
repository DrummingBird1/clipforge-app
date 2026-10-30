# tests/dataviz/test_dataviz_readability.py
#
# 20.10.2026: בדיקת קריאות לפי יעד - טקסט קטן (והתיקון מעלה את video.dpi עד שאין אזהרה), ניגודיות חלשה מול מה שבאמת
# מאחורי הטקסט (עם דריסת צבע בערכה), יותר מדי ישויות ל-Shorts, תוויות חופפות. לא נכתב כלום.
import pytest
from fastapi.testclient import TestClient
from matplotlib.transforms import Bbox

from dataviz.web import episodes as de
from dataviz.web import readability
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return {"data": data, "folder": write_episode(data / "dataviz_episodes", name="tiny")}


def _kinds(result):
    return {w["kind"]: w for w in result["warnings"]}


def test_contrast_math():
    assert readability.contrast((1, 1, 1), (0, 0, 0)) == pytest.approx(21.0)
    fixed = readability.readable_color((0.9, 0.9, 0.5), (0.98, 0.98, 0.96))
    assert readability.contrast(fixed, (0.98, 0.98, 0.96)) >= readability.MIN_CONTRAST
    assert readability._overlap(Bbox([[0, 0], [10, 10]]), Bbox([[5, 0], [15, 10]])) == pytest.approx(0.5)
    assert readability._overlap(Bbox([[0, 0], [10, 10]]), Bbox([[20, 0], [30, 10]])) == 0


def test_small_text_fix_raises_the_dpi_until_it_is_readable(env):
    small = _kinds(readability.check(env["folder"], {"video": {"dpi": 60}}, "youtube"))["small"]
    fix = small["fix"]
    assert fix["path"] == "video.dpi" and fix["value"] > 60
    after = readability.check(env["folder"], {"video": {"dpi": fix["value"]}}, "youtube")
    assert "small" not in _kinds(after)


def test_weak_contrast_is_measured_against_what_is_behind_the_text(env):
    assert "contrast" not in _kinds(readability.check(env["folder"], {}, "youtube"))   # "מוביל" על העמודה - בסדר
    weak = _kinds(readability.check(env["folder"], {"theme_overrides": {"ink": "#e0e0e0"}}, "youtube"))["contrast"]
    assert weak["fix"]["path"] == "theme_overrides.ink"
    after = readability.check(env["folder"], {"theme_overrides": {"ink": weak["fix"]["value"]}}, "youtube")
    assert "contrast" not in _kinds(after)


def test_too_many_entities_depends_on_the_target(env, monkeypatch):
    monkeypatch.setattr(readability, "MAX_ENTITIES", {False: 3, True: 2})
    assert "crowded" not in _kinds(readability.check(env["folder"], {}, "youtube"))
    crowded = _kinds(readability.check(env["folder"], {}, "shorts"))["crowded"]
    assert crowded["fix"] == {"path": "ranking.top_n", "value": 2, "label": "להציג 2"}


def test_route_uses_the_draft_and_writes_nothing(env):
    resp = client.post("/api/dataviz/readability", json={"episode": "tiny", "target": "shorts", "draft": {"video.dpi": 60}})
    assert resp.status_code == 200 and resp.json()["size"] == [1080, 1920] and "small" in _kinds(resp.json())
    assert de.load_overrides_for_path(env["folder"]) == {}
    assert client.post("/api/dataviz/readability", json={"episode": "tiny", "target": "fax"}).status_code == 400
    assert client.post("/api/dataviz/readability", json={"episode": "nope"}).status_code == 404
    assert [t["id"] for t in client.get("/api/dataviz/readability/targets").json()["targets"]] == ["youtube", "shorts", "tiktok"]
