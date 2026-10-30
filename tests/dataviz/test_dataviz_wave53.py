# tests/dataviz/test_dataviz_wave53.py - גל 53 בעורך הגרפים, "העורך": סימני הסליידר (אירועים, פרקים, עצירות, תחילת המרוץ
# והסיום) מאותה תכנית של התצוגה החיה, תצוגה מונפשת (GIF קצר סביב הרגע, נשמר במטמון), ותגיות ותיקיות לפרקים
# (קובץ של האפליקציה - תיקיות הפרקים לא משתנות). בלי ffmpeg; פריימים קטנים בלבד.
import hashlib
import os


import pytest
from fastapi.testclient import TestClient
from PIL import Image

from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de
from dataviz.web import preview as dataviz_preview

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 640, "height": 400, "fps": 10, "dpi": 60}}   # בחמישית מהגודל (ה-GIF) עדיין יש מקום לטקסט
STORY = {"chapters": [{"date": "2022-01-01", "title": "פרק שני"}], "pauses": [{"date": "2023-10-07", "text": "הקפיצה"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    folder = write_episode(data / "dataviz_episodes", name="tiny", overrides={**SMALL, "story": STORY})
    write_episode(data / "dataviz_episodes", name="other", overrides=SMALL)
    md5 = {n: hashlib.md5(open(os.path.join(folder, n), "rb").read()).hexdigest() for n in os.listdir(folder)}
    return {"data": str(data), "workspace": str(workspace), "folder": folder, "md5": md5}


def test_markers_come_from_the_plan(env):
    data = client.get("/api/dataviz/preview_markers", params={"episode": "tiny"}).json()
    kinds = [m["kind"] for m in data["markers"]]
    assert kinds.count("event") == 2 and kinds.count("chapter") == 1 and kinds.count("pause") == 1
    assert kinds.count("start") == 1 and kinds.count("outro") == 1
    positions = [m["pos"] for m in data["markers"]]
    assert positions == sorted(positions) and 0 < positions[0] < positions[-1] < 1
    assert {m["label"] for m in data["markers"] if m["kind"] == "event"} == {"אירוע גדול", "אירוע קטן"}
    # טיוטה שעוד לא נשמרה (פרק נוסף) כבר מופיעה בסימנים
    draft = '{"story.chapters": [{"date": "2021-06-01", "title": "חדש"}, {"date": "2022-01-01", "title": "פרק שני"}]}'
    drafted = client.get("/api/dataviz/preview_markers", params={"episode": "tiny", "draft": draft}).json()
    assert [m["label"] for m in drafted["markers"] if m["kind"] == "chapter"] == ["חדש", "פרק שני"]
    assert client.get("/api/dataviz/preview_markers", params={"episode": "nope"}).status_code == 404


def test_the_animated_preview_is_a_short_cached_gif(env):
    resp = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.5})
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/gif"
    gif = os.path.join(env["workspace"], "gif.gif")
    with open(gif, "wb") as f:
        f.write(resp.content)
    with Image.open(gif) as image:
        assert image.size == (128, 80)                                   # חמישית מהגודל
        total = 0
        for k in range(image.n_frames):                                   # פריימים זהים ברצף מתאחדים - האורך נשמר
            image.seek(k)
            total += image.info["duration"]
        assert total == 3000
    cached = [n for n in os.listdir(os.path.join(env["workspace"], ".cache", "dataviz_previews")) if n.endswith(".gif")]
    assert len(cached) == 1 and not os.path.exists(os.path.join(env["workspace"], ".dataviz_previews"))   # 19.10.2026: תחת .cache
    again = client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "pos": 0.5})
    assert again.content == resp.content
    assert client.get("/api/dataviz/preview_clip", params={"episode": "tiny", "chart": "nope"}).status_code == 400
    assert {n for n in os.listdir(env["folder"])} == set(env["md5"])


def test_clip_frames_stay_inside_the_plan_at_the_edges(env):
    folder = env["folder"]
    overrides = de.load_overrides_for_path(folder)
    cache = os.path.join(env["workspace"], "cache")
    for pos in (0.0, 1.0):
        clip = dataviz_preview.preview_clip(folder, overrides, cache, pos, seconds=2, fps=5)
        assert clip["frames"] == 10 and clip["start"] >= 0


def test_tags_and_folders_are_saved_outside_the_episode(env):
    resp = client.post("/api/dataviz/episodes/tags", json={"episode": "tiny", "tags": [" מלחמה ", "#x"[1:], "מלחמה", ""], "folder": "עונה 2"})
    assert resp.status_code == 200 and resp.json()["tags"] == ["x", "מלחמה"]
    rows = {e["name"]: e for e in client.get("/api/dataviz/episodes").json()["episodes"]}
    assert rows["tiny"]["tags"] == ["x", "מלחמה"] and rows["tiny"]["folder"] == "עונה 2"
    assert rows["other"]["tags"] == [] and rows["other"]["folder"] == ""
    assert os.path.isfile(os.path.join(env["data"], de.TAGS_FILENAME))
    # ריק = הפרק יוצא מהקובץ
    client.post("/api/dataviz/episodes/tags", json={"episode": "tiny", "tags": [], "folder": ""})
    assert de.load_tags(env["data"]) == {}
    for bad in ({"tags": ["x" * 31]}, {"tags": "x"}, {"folder": "a/b"}, {"tags": [str(i) for i in range(13)]}):
        assert client.post("/api/dataviz/episodes/tags", json={"episode": "tiny", **bad}).status_code == 400
    assert client.post("/api/dataviz/episodes/tags", json={"episode": "nope", "tags": []}).status_code == 404
    assert {n: hashlib.md5(open(os.path.join(env["folder"], n), "rb").read()).hexdigest() for n in os.listdir(env["folder"])} == env["md5"]
