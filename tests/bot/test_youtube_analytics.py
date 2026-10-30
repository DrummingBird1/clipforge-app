# tests/bot/test_youtube_analytics.py
#
# בודק utils/bot/youtube_analytics.py (item: YouTube Analytics feedback loop) -
# googleapiclient.discovery.build ו-_get_credentials ממופתחים, בלי קריאת
# רשת אמיתית ל-YouTube.
from unittest.mock import MagicMock


import pytest

import utils.bot.youtube_analytics as youtube_analytics
from utils.bot.youtube_analytics import get_video_stats, set_video_thumbnail


def _patch_youtube_response(monkeypatch, response):
    monkeypatch.setattr(youtube_analytics, "_get_credentials", lambda: "fake-creds")
    fake_youtube = MagicMock()
    fake_youtube.videos.return_value.list.return_value.execute.return_value = response
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: fake_youtube)
    return fake_youtube


def test_get_video_stats_returns_counts_for_existing_video(monkeypatch):
    _patch_youtube_response(monkeypatch, {
        "items": [{"statistics": {"viewCount": "150", "likeCount": "12", "commentCount": "3"}}],
    })

    assert get_video_stats("abc123") == {"views": 150, "likes": 12, "comments": 3}


def test_get_video_stats_returns_none_when_video_not_found(monkeypatch):
    _patch_youtube_response(monkeypatch, {"items": []})

    assert get_video_stats("nonexistent") is None


def test_get_video_stats_defaults_missing_fields_to_zero(monkeypatch):
    # לייקים ציבוריים מוסתרים (הבעלים כיבה את זה) - likeCount לגמרי חסר, לא "0"
    _patch_youtube_response(monkeypatch, {
        "items": [{"statistics": {"viewCount": "10"}}],
    })

    assert get_video_stats("abc123") == {"views": 10, "likes": 0, "comments": 0}


def test_get_video_stats_calls_videos_list_with_correct_id(monkeypatch):
    fake_youtube = _patch_youtube_response(monkeypatch, {"items": [{"statistics": {}}]})

    get_video_stats("my-video-id")

    fake_youtube.videos.return_value.list.assert_called_once_with(part="statistics", id="my-video-id")


# --- set_video_thumbnail (item: A/B thumbnail testing) ---

def test_set_video_thumbnail_calls_thumbnails_set_with_video_id(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_analytics, "_get_credentials", lambda: "fake-creds")
    image_path = tmp_path / "candidate_0.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    fake_youtube = MagicMock()
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: fake_youtube)

    set_video_thumbnail("my-video-id", str(image_path))

    fake_youtube.thumbnails.return_value.set.assert_called_once()
    _args, kwargs = fake_youtube.thumbnails.return_value.set.call_args
    assert kwargs["videoId"] == "my-video-id"
    fake_youtube.thumbnails.return_value.set.return_value.execute.assert_called_once()


def test_set_video_thumbnail_propagates_api_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(youtube_analytics, "_get_credentials", lambda: "fake-creds")
    image_path = tmp_path / "candidate_0.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    fake_youtube = MagicMock()
    fake_youtube.thumbnails.return_value.set.return_value.execute.side_effect = RuntimeError("quota exceeded")
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: fake_youtube)

    with pytest.raises(RuntimeError, match="quota exceeded"):
        set_video_thumbnail("my-video-id", str(image_path))
