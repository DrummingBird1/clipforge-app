# tests/dataviz/test_dataviz_wave51.py - גל 51 בעורך הגרפים, "המראה": תמונה לכל ישות (חיתוך עגול / ריבוע / כמו שהיא, החדשה
# ביותר גוברת), תרשים עוגה, מקרא ושמות על המפה, סגנון (עובי עמודות, רשת, כותרת, שנה ברקע) ו"מראות מוכנים", ושמירת
# תמונות מהמסך (קובץ חדש בלבד, מחוץ לתיקיית הפרק). בלי ffmpeg - פריימים קטנים; config.yaml של הפרק לא משתנה.
import base64
import hashlib
import io
import json
import os
import time


import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dataviz.charts import CHART_INFO, make_chart
from dataviz.charts.base import IMAGE_PX, image_name, load_entity_images
from dataviz.config import ConfigError, load_config
from dataviz.episode import load_episode
from dataviz.looks import LOOKS, all_paths
from dataviz.plan import build_plan
from dataviz.render import chart_context
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web import preview as dataviz_preview

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 20}}


def _png(color=(200, 30, 30, 255), size=(40, 20)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, "PNG")
    return buffer.getvalue()


# ---------- תמונות לישויות ----------
def test_entity_images_are_matched_by_name_cropped_and_the_newest_wins(tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    (folder / "2023.png").write_bytes(_png((255, 0, 0, 255)))
    (folder / "2023@20260101.png").write_bytes(_png((0, 0, 255, 255)))
    os.utime(folder / "2023.png", (time.time() - 100, time.time() - 100))
    (folder / "תל אביב-יפו.jpg").write_bytes(_png())   # "/" בשם הישות הופך ל-"-" בשם הקובץ
    (folder / "zzz.png").write_bytes(_png())            # ישות שלא בפרק
    (folder / "2022.png").write_bytes(b"not an image")  # פגום - מדולג
    images = load_entity_images({"folder": str(folder), "shape": "circle"}, [2023, 2022, "תל אביב/יפו"])
    assert set(images) == {"2023", "תל אביב/יפו"}
    red, green, blue, alpha = images["2023"][IMAGE_PX // 2, IMAGE_PX // 2]
    assert (red, blue) == (0, 255) and images["2023"].shape == (IMAGE_PX, IMAGE_PX, 4)
    assert images["2023"][0, 0][3] == 0 and alpha == 255                 # עיגול: הפינה שקופה
    square = load_entity_images({"folder": str(folder), "shape": "square"}, [2023])
    assert square["2023"][0, 0][3] == 255
    original = load_entity_images({"folder": str(folder), "shape": "original"}, [2023])
    assert original["2023"][0, 0][3] == 0 and original["2023"][IMAGE_PX // 2, 2][3] == 255   # 2:1 - שוליים למעלה
    assert image_name("a/b:c") == "a-b-c"
    assert load_entity_images({"folder": str(tmp_path / "missing")}, [2023]) == {}


@pytest.mark.parametrize("chart", ["bar_race", "line_race", "bump_race", "pie_race"])
def test_charts_draw_entity_images(tmp_path, chart):
    images = tmp_path / "ep" / "pics"
    folder = write_episode(tmp_path, name="ep", overrides={**SMALL, "chart": chart, "images": {"folder": "pics", "shape": "circle", "size": 1.2}})
    images.mkdir()
    for year in (2019, 2020, 2021, 2023):
        (images / f"{year}.png").write_bytes(_png())
    episode = load_episode(folder)
    plan = build_plan(episode, "test")
    with_images = make_chart(chart_context(episode))
    without = make_chart({**chart_context(episode), "images": {}})
    try:
        frame = plan[len(plan) // 2]
        assert len(with_images._images) == 4 and with_images.render(frame) != without.render(frame)
    finally:
        with_images.close()
        without.close()


# ---------- תרשים עוגה ----------
def test_the_pie_chart_shows_shares_and_others(tmp_path):
    episode = load_episode(write_episode(tmp_path, overrides={**SMALL, "chart": "pie_race", "ranking": {"top_n": 2}, "labels": {"others": "השאר"}}))
    plan = build_plan(episode, "full")
    chart = make_chart(chart_context(episode))
    try:
        frame = plan[-1]
        chart.render(frame)
        texts = [t.get_text() for t in chart.ax.texts]
        assert any(t.startswith("השאר\n") for t in texts) and any("%" in t for t in texts)
        assert chart.fmt(frame["total"]) in texts
    finally:
        chart.close()
    assert "pie_race" in CHART_INFO


# ---------- מפה: סקאלת צבעים ושמות ----------
GEO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": str(y)}, "geometry": {"type": "Polygon", "coordinates": [[[34 + i, 31], [35 + i, 31], [35 + i, 32], [34 + i, 32], [34 + i, 31]]]}}
    for i, y in enumerate((2019, 2020, 2021, 2023))]}


@pytest.mark.parametrize("labels,expected", [("none", 0), ("top", 3), ("all", 4)])
def test_the_map_legend_and_region_names(tmp_path, labels, expected):
    folder = write_episode(tmp_path, overrides={**SMALL, "chart": "map_race", "ranking": {"top_n": 3},
                                                "map": {"geojson": "regions.geojson", "legend": True, "labels": labels}})
    with open(os.path.join(folder, "regions.geojson"), "w", encoding="utf-8") as f:
        json.dump(GEO, f)
    episode = load_episode(folder)
    chart = make_chart(chart_context(episode))
    try:
        chart.render(build_plan(episode, "full")[-1])
        on_map = [t for t in chart.ax.texts if t.get_text() in {"2019", "2020", "2021", "2023"} and t.get_transform() == chart.ax.transData]
        assert len(on_map) == expected
        assert chart._legend_ax is not None and chart._legend_ax.get_visible()
        x, y = chart._label_at["2020"]
        assert (x, y) != (0, 0)
    finally:
        chart.close()


# ---------- סגנון ומראות מוכנים ----------
def test_style_settings_change_the_frame_and_are_validated(tmp_path):
    base = load_episode(write_episode(tmp_path / "a", overrides=SMALL))
    styled = load_episode(write_episode(tmp_path / "b", overrides={**SMALL, "style": {"bar_height": 0.4, "grid": False, "title_size": 30, "year_mark": False}}))
    frame = build_plan(base, "test")[30]
    images = []
    for episode in (base, styled):
        chart = make_chart(chart_context(episode))
        try:
            images.append(chart.render(frame))
            if episode is styled:
                assert not any(line.get_visible() for line in chart.ax.get_xgridlines())
        finally:
            chart.close()
    assert images[0] != images[1]
    folder = write_episode(tmp_path / "c", overrides={"style": {"bar_height": 2, "grid": "x", "title_size": 99},
                                                      "images": {"folder": "nope", "shape": "star", "size": 9},
                                                      "map": {"legend": 1, "labels": "some"}, "labels": {"others": 5}})
    with pytest.raises(ConfigError) as e:
        load_config(os.path.join(folder, "config.yaml"))
    text = "\n".join(e.value.errors)
    for part in ("style.bar_height", "style.grid", "style.title_size", "תיקיית התמונות", "images.shape", "images.size", "map.legend", "map.labels", "labels.others"):
        assert part in text, part


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides=SMALL)
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": str(data), "folder": folder, "md5": md5}


def _unchanged(env):
    return {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == env["md5"]


def test_every_ready_look_is_a_valid_set_of_settings(env):
    editor = client.get("/api/dataviz/episodes/editor", params={"episode": "tiny", "lang": "en"}).json()
    assert [look["id"] for look in editor["looks"]] == ["minimal", "news", "bold"] and editor["looks"][0]["title"] == "Minimal"
    assert editor["look_paths"] == all_paths()
    for look in LOOKS:
        resp = client.post("/api/dataviz/episodes/override", json={"episode": "tiny", "set": look["set"], "unset": [p for p in all_paths() if p not in look["set"]]})
        assert resp.status_code == 200, (look["id"], resp.text)
    saved = de.load_overrides_for_path(env["folder"])
    assert saved["theme"] == "dark" and saved["style"]["bar_height"] == 0.86 and "numbers" not in saved   # האחרון (בולט) - בלי שאריות של מינימלי
    assert _unchanged(env)


# ---------- תמונות מהמסך ----------
def test_images_are_uploaded_listed_served_and_trashed(env, monkeypatch):
    data = env["data"]
    resp = client.post("/api/dataviz/episodes/images", json={"episode": "tiny", "entity": "2023", "ext": "png", "data_base64": base64.b64encode(_png()).decode()})
    assert resp.status_code == 200, resp.text
    name = resp.json()["name"]
    assert name.startswith("2023@") and name.endswith(".png")
    folder = os.path.join(data, "dataviz_overrides", "tiny", "images")
    assert de.load_overrides_for_path(env["folder"])["images"]["folder"] == os.path.abspath(folder)
    assert client.get("/api/dataviz/episodes/images", params={"episode": "tiny"}).json()["images"] == {"2023": name}
    served = client.get("/api/dataviz/episodes/image", params={"episode": "tiny", "name": name})
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert client.get("/api/dataviz/episodes/image", params={"episode": "tiny", "name": "../../tiny/config.yaml"}).status_code == 404
    episode = load_episode(env["folder"], de.load_overrides_for_path(env["folder"]))
    assert set(make_chart(chart_context(episode))._images) == {"2023"}
    trashed = []
    monkeypatch.setattr("send2trash.send2trash", lambda path: trashed.append(path))
    assert client.post("/api/dataviz/episodes/images/trash", json={"episode": "tiny", "name": name}).status_code == 200
    assert trashed == [os.path.join(os.path.realpath(folder), name)]
    assert _unchanged(env)


@pytest.mark.parametrize("payload", [
    {"entity": "2023", "ext": "gif", "data_base64": base64.b64encode(_png()).decode()},
    {"entity": "2023", "ext": "png", "data_base64": base64.b64encode(b"not a picture").decode()},
    {"entity": "", "ext": "png", "data_base64": base64.b64encode(_png()).decode()},
    {"entity": "2023", "ext": "png", "data_base64": "%%%"},
])
def test_bad_images_are_refused(env, payload):
    assert client.post("/api/dataviz/episodes/images", json={"episode": "tiny", **payload}).status_code == 400
    assert not os.path.isdir(os.path.join(env["data"], "dataviz_overrides", "tiny", "images")) or not os.listdir(os.path.join(env["data"], "dataviz_overrides", "tiny", "images"))


def test_a_new_image_changes_the_live_preview_fingerprint(env):
    client.post("/api/dataviz/episodes/images", json={"episode": "tiny", "entity": "2023", "ext": "png", "data_base64": base64.b64encode(_png()).decode()})
    overrides = de.load_overrides_for_path(env["folder"])
    before = dataviz_preview._fingerprint(env["folder"], overrides)
    time.sleep(1.1)   # שם הקובץ כולל את השנייה
    client.post("/api/dataviz/episodes/images", json={"episode": "tiny", "entity": "2021", "ext": "png", "data_base64": base64.b64encode(_png()).decode()})
    assert dataviz_preview._fingerprint(env["folder"], de.load_overrides_for_path(env["folder"])) != before
    assert np.asarray(Image.open(io.BytesIO(_png()))).shape == (20, 40, 4)
