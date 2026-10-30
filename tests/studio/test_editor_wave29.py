# tests/studio/test_editor_wave29.py
#
# גל 29 בצד השרת: שכבה מוסתרת (👁 ברשימת השכבות) לא מרונדרת, וקובץ שנגרר מהמחשב לנגן
# או לציר-הזמן מועתק לתיקיית הנכסים של הפרויקט (ליד הפרויקטים - לא לתיקיית הקלט, שם
# הוא היה נכנס לתור ומרונדר כקלט) ומוחזר הנתיב שלו.
import os


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import editor_projects
from utils.video import video_editor_profiles as vep
from utils.video.video_editor_layers import sanitize_layers

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "data" / "video_editor_profiles.json"))
    monkeypatch.setattr(web_app.limiter, "enabled", False)


def test_a_hidden_layer_is_kept_in_the_project_but_not_rendered():
    layers = [{"type": "text", "text": "visible"}, {"type": "text", "text": "hidden", "hidden": True},
              {"type": "text", "text": "locked", "locked": True, "name": "כותרת"}]
    clean = sanitize_layers(layers)
    assert [layer["text"] for layer in clean] == ["visible", "locked"]
    # שם ונעילה הם של הממשק בלבד - לא נכנסים לשכבה שהרנדרר מקבל
    assert "name" not in clean[1] and "locked" not in clean[1]


def test_assets_live_next_to_the_projects_per_folder(tmp_path):
    folder_a, folder_b = tmp_path / "a", tmp_path / "b"
    a, b = editor_projects.assets_dir(str(folder_a)), editor_projects.assets_dir(str(folder_b))
    assert os.path.dirname(a) == os.path.join(str(tmp_path / "data"), "editor_assets")
    assert a != b and not a.startswith(str(folder_a))


def test_a_dropped_asset_is_copied_to_the_project_assets_and_never_overwrites(tmp_path):
    folder = tmp_path / "match"
    folder.mkdir()
    first = client.post("/api/video_editor/upload_asset", params={"folder": str(folder), "name": "logo.png"}, content=b"png-bytes")
    assert first.status_code == 200, first.text
    path = first.json()["path"]
    assert path.startswith(editor_projects.assets_dir(str(folder))) and open(path, "rb").read() == b"png-bytes"
    second = client.post("/api/video_editor/upload_asset", params={"folder": str(folder), "name": "logo.png"}, content=b"other")
    assert second.json()["name"] == "logo_2.png" and open(path, "rb").read() == b"png-bytes"
    for name in ("broll.mp4", "music.mp3"):
        assert client.post("/api/video_editor/upload_asset", params={"folder": str(folder), "name": name}, content=b"x").status_code == 200
    # תיקיית הקלט לא נגעה - אחרת הקבצים היו נכנסים לתור
    assert os.listdir(folder) == []


def test_upload_asset_rejects_bad_types_missing_folders_and_empty_bodies(tmp_path):
    folder = tmp_path / "match"
    folder.mkdir()
    assert client.post("/api/video_editor/upload_asset", params={"folder": str(folder), "name": "notes.txt"}, content=b"x").status_code == 400
    assert client.post("/api/video_editor/upload_asset", params={"folder": str(tmp_path / "nope"), "name": "a.png"}, content=b"x").status_code == 400
    assert client.post("/api/video_editor/upload_asset", params={"folder": str(folder), "name": "empty.png"}, content=b"").status_code == 400
    traversal = client.post("/api/video_editor/upload_asset", params={"folder": str(folder), "name": "..\\..\\escape.png"}, content=b"x")
    assert traversal.status_code == 200 and os.path.dirname(traversal.json()["path"]) == editor_projects.assets_dir(str(folder))
    assert not any(n.startswith(".upload_") for n in os.listdir(editor_projects.assets_dir(str(folder))))
