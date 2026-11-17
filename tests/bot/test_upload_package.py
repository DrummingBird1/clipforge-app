# tests/bot/test_upload_package.py
#
# 16.11.2026 (2.0): utils/bot/platforms.py + upload_package.py - הבדיקות מול כל פלטפורמה, הכיתוב בגבולות התווים,
# והתיקייה של חבילת ההעלאה. בלי שום העלאה ובלי רשת.
import json
import os

import pytest

from utils.bot import platforms, upload_package
from utils.video.editor_model import TARGET_PRESETS


def test_every_platform_has_a_studio_target():
    for platform in platforms.PLATFORMS.values():
        assert platform.target in TARGET_PRESETS, platform.id
    assert {"tiktok", "reels", "twitch", "kick", "discord_50"} <= set(platforms.PLATFORMS)


def test_checks_catch_the_wrong_shape_length_and_size():
    tiktok = platforms.get("tiktok")
    assert platforms.check(tiktok, {"width": 1080, "height": 1920, "duration": 30}, 10_000_000) == []
    wrong = platforms.check(tiktok, {"width": 1920, "height": 1080, "duration": 4000}, 5 * 1024 ** 3)
    assert len(wrong) == 3
    assert platforms.check(platforms.get("discord"), {}, 11 * 1024 * 1024)[0].startswith("גדול מדי")
    assert platforms.check(platforms.get("twitch"), {"width": 1080, "height": 1920}, 1)   # אנכי ל-Twitch


def test_tags_become_clean_unique_hashtags():
    assert upload_package.hashtags(["rocket league", "#RL", "RL", ""]) == "#rocketleague #RL"


def test_a_long_caption_is_cut_from_the_description_and_keeps_title_and_tags():
    reels = platforms.get("reels")
    text = upload_package.caption(reels, "גול מטורף", "x" * 5000, ["RL", "goal"])
    assert len(text["caption"]) <= reels.caption_limit
    assert text["caption"].startswith("גול מטורף") and text["caption"].endswith("#RL #goal") and "…" in text["caption"]
    assert text["title"] == ""                                   # ל-Reels אין שדה כותרת


def test_twitch_keeps_a_separate_title_within_its_limit():
    text = upload_package.caption(platforms.get("twitch"), "t" * 300, "desc", [])
    assert len(text["title"]) == 140 and text["caption"] == "desc"


def test_a_package_folder_has_the_video_caption_thumbnail_and_checks(tmp_path):
    video = tmp_path / "goal.mp4"
    video.write_bytes(b"v" * 1000)
    thumb = tmp_path / "goal.jpg"
    thumb.write_bytes(b"j")
    info = upload_package.build(str(video), "tiktok", str(tmp_path / "packages"), title="גול", description="מהמשחק",
                                tags=["RL"], thumbnail=str(thumb), probe={"width": 1920, "height": 1080, "duration": 20})
    folder = info["folder"]
    assert sorted(os.listdir(folder)) == ["caption.txt", "goal.mp4", "package.json", "thumbnail.jpg"]
    assert open(os.path.join(folder, "caption.txt"), encoding="utf-8").read() == "גול\n\nמהמשחק\n\n#RL\n"
    assert info["upload_url"].startswith("https://www.tiktok.com/") and len(info["warnings"]) == 1   # אופקי ל-TikTok
    assert json.load(open(os.path.join(folder, "package.json"), encoding="utf-8"))["platform"] == "tiktok"
    assert video.read_bytes() == b"v" * 1000


@pytest.mark.parametrize("platform_id", ["youtube", "discord", "nope"])
def test_platforms_without_a_package_are_refused(tmp_path, platform_id):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"v")
    with pytest.raises(ValueError):
        upload_package.build(str(video), platform_id, str(tmp_path / "p"))
