# tests/web/test_web_path_aliases.py
#
# 16.11.2026 (סריקת באגים ל-2.0): בדיקות הנתיבים (entrypoints/web/path_checks.py) מול כינויים של Windows לאותו קובץ -
# \\?\E:\..., \\localhost\E$\... - ומול תיקייה שהיא שורש כונן. קודם realpath+startswith פספס את הכינויים, ו-/api/download
# הגיש את data/web_app_token.txt.
import os
import sys

import pytest

from entrypoints import web_app
from utils.shared import path_safety
from tests.web_app_support import client

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="כינויי נתיב של Windows")


@pytest.fixture
def secret(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    token = data / "web_app_token.txt"
    token.write_text("s3cret", encoding="utf-8")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return str(token)


def test_a_long_path_prefix_does_not_reach_data(secret):
    alias = "\\\\?\\" + secret
    assert os.path.isfile(alias)
    assert web_app._is_under_data_dir(alias)
    assert client.get("/api/download", params={"path": alias}).status_code == 403


def test_the_local_admin_share_does_not_reach_data(secret):
    drive, rest = os.path.splitdrive(secret)
    alias = f"\\\\localhost\\{drive[0]}$" + rest
    if not os.path.isfile(alias):
        pytest.skip("אין שיתוף admin מקומי במחשב הזה")
    assert web_app._is_under_data_dir(alias)
    assert client.get("/api/download", params={"path": alias}).status_code == 403


def test_a_normal_file_outside_data_still_downloads(secret, tmp_path):
    other = tmp_path / "out.mp4"
    other.write_bytes(b"x")
    assert client.get("/api/download", params={"path": str(other)}).status_code == 200


def test_a_drive_root_is_a_valid_root_and_a_sibling_prefix_is_not(tmp_path):
    drive = os.path.splitdrive(str(tmp_path))[0] + "\\"
    assert path_safety.is_within(str(tmp_path / "a.mp4"), drive)
    assert not path_safety.is_within(str(tmp_path) + "2\\a.mp4", str(tmp_path))


@pytest.mark.parametrize("name", [".env", ".ENV", ".env.local", "client_secret.json", "youtube_token.json", "tiktok_cookies.txt",
                                  "YouTube_Token.JSON"])
def test_secret_files_in_the_install_folder_are_not_served(secret, tmp_path, name):
    # 2.0.0 חסם רק את data/. הטוקן של הבוט (.env) והטוקן של יוטיוב יושבים בתיקיית ההתקנה, ומכשיר מצומד יכול היה להוריד אותם.
    path = tmp_path / name
    path.write_text("TOKEN=abc", encoding="utf-8")
    assert client.get("/api/download", params={"path": str(path)}).status_code == 403
    assert client.get("/api/download", params={"path": "\\\\?\\" + str(path)}).status_code == 403


def test_secret_names_are_matched_exactly(tmp_path):
    assert path_safety.is_secret_name("C:/app/.env") and path_safety.is_secret_name("C:/app/.env::$DATA")
    assert path_safety.is_secret_name("C:/app/youtube_token.json. ")
    for ordinary in ("C:/clips/env.mp4", "C:/app/.env.example", "C:/clips/my_youtube_token.json.mp4", "C:/clips/token.json"):
        assert not path_safety.is_secret_name(ordinary), ordinary
