# tests/dataviz/test_dataviz_annotations.py
#
# 20.10.2026: הערות על הגרף (story.annotations) - חץ וטקסט בנקודה (תאריך + ערך), עם חלון זמן (days), היסט (dx/dy) וסגנון.
# נשמרות כמו שאר רשימות הסיפור (override), מצוירות בקווים ובשטח מוערם (לא בעמודות / דירוגים / גרפים קטנים), והתצוגה
# מחזירה את הצירים של הפריים (X-Frame-Axes) כדי שלחיצה בדפדפן תהפוך לתאריך וערך.
import json
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from dataviz.web import episodes as de
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

VIDEO = {"video": {"width": 640, "height": 400, "fps": 10, "dpi": 40}}
NOTE = {"date": "2021-06-01", "value": 300, "text": "שיא", "days": 200, "dx": -30, "dy": 20, "style": "accent"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def _frames(folder):
    from dataviz.episode import load_episode
    from dataviz.plan import build_plan
    episode = load_episode(folder)
    return episode, [f for f in build_plan(episode, "full") if f["k"] == "main"]


def test_an_annotation_is_shown_only_in_its_time_window(env):
    folder = write_episode(env / "dataviz_episodes", overrides={"chart": "line_race", **VIDEO, "story": {"annotations": [NOTE]}}, name="tiny")
    episode, frames = _frames(folder)
    start = episode.dates.get_loc(__import__("pandas").Timestamp("2021-06-01"))
    inside = [f for f in frames if start + 20 <= f["x"] < start + 180]
    outside = [f for f in frames if f["x"] < start or f["x"] >= start + 200]
    assert inside and all(f["annotations"][0][1:6] == (300.0, "שיא", -30, 20, "accent") for f in inside)
    assert outside and not any(f.get("annotations") for f in outside)


@pytest.mark.parametrize("chart, drawn", [("line_race", True), ("stacked_area_race", True), ("bar_race", False), ("small_multiples", False)])
def test_annotations_are_drawn_where_y_is_a_value(env, chart, drawn):
    from dataviz.charts import make_chart
    from dataviz.render import chart_context
    folder = write_episode(env / "dataviz_episodes", overrides={"chart": chart, **VIDEO, "story": {"annotations": [{k: v for k, v in NOTE.items() if k != "days"}]}}, name=chart)
    episode, frames = _frames(folder)
    chart_obj = make_chart(chart_context(episode))
    try:
        chart_obj.render(frames[-1])
        texts = [t.get_text() for t in chart_obj.ax.texts]
        assert ("שיא" in texts) is drawn
    finally:
        chart_obj.close()


def test_annotations_are_saved_and_validated_like_the_other_story_lists(env):
    write_episode(env / "dataviz_episodes", name="tiny")
    saved = de.update_override_fields(str(env), "tiny", {"story.annotations": [{**NOTE, "value": "300.5", "dx": 900}]}, [])
    note = saved["story"]["annotations"][0]
    assert note["value"] == 300.5 and note["dx"] == 400 and note["style"] == "accent"
    with pytest.raises(de.EpisodeError):
        de.update_override_fields(str(env), "tiny", {"story.annotations": [{**NOTE, "style": "neon"}]}, [])
    with pytest.raises(de.EpisodeError):
        de.update_override_fields(str(env), "tiny", {"story.annotations": [{"date": "2021-01-01", "text": "בלי ערך"}]}, [])


def test_the_preview_frame_reports_its_axes_for_clicks(env):
    write_episode(env / "dataviz_episodes", overrides={"chart": "line_race", **VIDEO}, name="lines")
    write_episode(env / "dataviz_episodes", overrides={"chart": "bar_race", **VIDEO}, name="bars")
    resp = client.get("/api/dataviz/preview_frame", params={"episode": "lines", "pos": 0.6})
    axes = json.loads(unquote(resp.headers["X-Frame-Axes"]))
    assert len(axes["box"]) == 4 and axes["xlim"][1] > axes["xlim"][0] and axes["ylim"][1] > axes["ylim"][0] and axes["start"]
    bars = client.get("/api/dataviz/preview_frame", params={"episode": "bars", "pos": 0.6})
    assert json.loads(unquote(bars.headers["X-Frame-Axes"])) is None
