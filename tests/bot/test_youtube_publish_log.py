# tests/bot/test_youtube_publish_log.py
#
# בודק utils/bot/youtube_publish_log.py (item: YouTube Analytics feedback loop) -
# DB_PATH ממופתח ל-tmp_path בכל טסט.


import utils.bot.youtube_publish_log as youtube_publish_log
from utils.bot.youtube_publish_log import get_published_videos, record_upload, update_cached_stats


def test_record_upload_creates_row_with_null_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))

    record_upload("vid1", "clip.mp4", "My Clip")

    rows = get_published_videos()
    assert len(rows) == 1
    video_id, clip_filename, title, uploaded_at, views, likes, comments, stats_updated_at = rows[0]
    assert (video_id, clip_filename, title) == ("vid1", "clip.mp4", "My Clip")
    assert views is None
    assert likes is None
    assert comments is None
    assert stats_updated_at is None
    assert uploaded_at is not None


def test_get_published_videos_ordered_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))

    record_upload("vid_old", "old.mp4", "Old")
    record_upload("vid_new", "new.mp4", "New")
    # uploaded_at נקבע לפי datetime.now() - לא שולט על הסדר בין שתי קריאות
    # מהירות, אז קובעים ידנית timestamps שונים בבירור לבדיקה דטרמיניסטית.
    with youtube_publish_log.db.connect(str(tmp_path / "test.db")) as conn:
        conn.execute("UPDATE youtube_published_videos SET uploaded_at = '2026-01-01T00:00:00' WHERE video_id = 'vid_old'")
        conn.execute("UPDATE youtube_published_videos SET uploaded_at = '2026-06-01T00:00:00' WHERE video_id = 'vid_new'")

    rows = get_published_videos()

    assert [r[0] for r in rows] == ["vid_new", "vid_old"]


def test_get_published_videos_respects_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    for i in range(5):
        record_upload(f"vid{i}", f"clip{i}.mp4", f"Clip {i}")

    assert len(get_published_videos(limit=3)) == 3


def test_update_cached_stats_sets_views_likes_comments(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    record_upload("vid1", "clip.mp4", "My Clip")

    update_cached_stats("vid1", views=100, likes=10, comments=2)

    rows = get_published_videos()
    _, _, _, _, views, likes, comments, stats_updated_at = rows[0]
    assert (views, likes, comments) == (100, 10, 2)
    assert stats_updated_at is not None


def test_update_cached_stats_does_nothing_for_unknown_video_id(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))

    update_cached_stats("nonexistent", views=1, likes=1, comments=1)

    assert get_published_videos() == []


def test_record_upload_with_same_video_id_replaces_the_row(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    record_upload("vid1", "clip.mp4", "Old Title")
    update_cached_stats("vid1", views=100, likes=10, comments=2)

    record_upload("vid1", "clip.mp4", "New Title")

    rows = get_published_videos()
    assert len(rows) == 1
    assert rows[0][2] == "New Title"
    assert rows[0][4] is None  # views resets - re-recording is treated as a fresh upload entry


def test_get_published_videos_empty_when_nothing_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))

    assert get_published_videos() == []
