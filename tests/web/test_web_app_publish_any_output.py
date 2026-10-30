# tests/web/test_web_app_publish_any_output.py
#
# 23.10.2026 (באישור המפנה, למסך "תוצרים"): /api/clips/tiktok_export ו-/api/clips/youtube_export מקבלים כל תוצר - לא רק
# קליפ מ-CLIPS_DIR - דרך _validate_publishable_path. רק סרטון קיים בתוך workspace, תיקיות הייצוא או תיקיית Rocket, אחרי
# realpath, ואף פעם לא מ-data/. בלי העלאה אמיתית: ה-SEO מזויף, וביוטיוב is_configured=False (קישור להעלאה ידנית).
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

from tests.web_app_support import _fake_seo, _reset_youtube_upload_state, client, web_app
from utils.shared import export_dir


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(tmp_path / "rocket_settings.json"))
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo()))


@pytest.fixture
def exports(tmp_path):
    folder = tmp_path / "exports"
    (folder / "studio" / "horizontal").mkdir(parents=True)
    export_dir.save_root(str(folder))
    return folder


def _video(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _link_dir(link, target):
    """junction ב-Windows (לא צריך הרשאת מנהל), symlink בשאר."""
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_an_output_in_the_export_folder_can_be_published(exports, monkeypatch):
    video = _video(exports / "studio" / "horizontal" / "a.mp4")
    tiktok = client.post("/api/clips/tiktok_export", json={"path": str(video)})
    assert tiktok.status_code == 200 and tiktok.json()["ok"] is True
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: False)
    youtube = client.post("/api/clips/youtube_export", json={"path": str(video)})
    assert youtube.status_code == 200 and youtube.json()["configured"] is False


def test_an_output_in_rockets_own_folder_can_be_published_but_not_its_raw_videos(tmp_path):
    rocket = tmp_path / "rocket_out"
    (tmp_path / "rocket_settings.json").write_text(json.dumps({"output_dir": str(rocket)}), encoding="utf-8")
    short = _video(rocket / "rocket_shorts" / "TikTok" / "a.mp4")
    raw = _video(rocket / "raw.mp4")
    assert web_app._validate_publishable_path(str(short)) == os.path.realpath(short)
    assert client.post("/api/clips/tiktok_export", json={"path": str(short)}).status_code == 200
    assert web_app._validate_publishable_path(str(raw)) is None


def test_a_path_with_dot_dot_out_of_the_root_is_refused(exports, tmp_path):
    _video(tmp_path / "outside.mp4")
    sneaky = os.path.join(str(exports), "studio", "horizontal", "..", "..", "..", "outside.mp4")
    assert os.path.isfile(sneaky)
    assert web_app._validate_publishable_path(sneaky) is None
    assert client.post("/api/clips/tiktok_export", json={"path": sneaky}).status_code == 400


def test_a_junction_out_of_the_root_is_refused(exports, tmp_path):
    outside = tmp_path / "outside"
    _video(outside / "a.mp4")
    link = exports / "studio" / "link"
    _link_dir(link, outside)
    through_link = link / "a.mp4"
    assert through_link.is_file()
    assert web_app._validate_publishable_path(str(through_link)) is None


def test_never_from_data_even_when_the_export_folder_is_there(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setenv(export_dir.ENV_VAR, str(data))     # הגדרה ידנית שעוקפת את הבדיקה של מסך ההגדרות
    video = _video(data / "studio" / "horizontal" / "a.mp4")
    assert web_app._is_under_workspace(str(video))        # התיקייה כן נחשבת תיקיית ייצוא
    assert web_app._validate_publishable_path(str(video)) is None


def test_only_existing_video_files(exports):
    folder = exports / "studio" / "horizontal"
    for name in ("notes.txt", "a.mp4.json", "frame.png"):
        assert web_app._validate_publishable_path(str(_video(folder / name))) is None, name
    assert web_app._validate_publishable_path(str(folder / "missing.mp4")) is None
    assert web_app._validate_publishable_path(str(folder)) is None
    assert web_app._validate_publishable_path("") is None
    for name in ("a.mp4", "b.MOV", "c.mkv", "d.webm"):
        assert web_app._validate_publishable_path(str(_video(folder / name))), name


def test_clips_keep_working_and_their_check_is_unchanged(tmp_path, monkeypatch, exports):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    clip = _video(tmp_path / "clips" / "clip.mp4")
    output = _video(exports / "studio" / "horizontal" / "a.mp4")
    assert web_app._validate_publishable_path(str(clip)) == os.path.realpath(clip)
    assert web_app._validate_clip_path(str(output)) is None      # שאר ה-routes של הקליפים - רק CLIPS_DIR, כמו קודם
