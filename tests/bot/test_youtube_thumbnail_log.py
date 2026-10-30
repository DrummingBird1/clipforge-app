# tests/bot/test_youtube_thumbnail_log.py
#
# בודק utils/bot/youtube_thumbnail_log.py (item: A/B thumbnail testing) - DB_PATH
# ממופתח ל-tmp_path בכל טסט.


import utils.bot.youtube_thumbnail_log as youtube_thumbnail_log
from utils.bot.youtube_thumbnail_log import get_candidates, get_latest_switch, record_candidates, record_switch


def test_record_candidates_stores_paths_in_index_order(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    record_candidates("vid1", ["/a.jpg", "/b.jpg", "/c.jpg"])

    assert get_candidates("vid1") == [(0, "/a.jpg"), (1, "/b.jpg"), (2, "/c.jpg")]


def test_get_candidates_empty_when_none_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    assert get_candidates("vid1") == []


def test_get_candidates_scoped_to_video_id(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    record_candidates("vid1", ["/a.jpg"])
    record_candidates("vid2", ["/x.jpg"])

    assert get_candidates("vid1") == [(0, "/a.jpg")]
    assert get_candidates("vid2") == [(0, "/x.jpg")]


def test_record_candidates_replaces_existing_entries_for_same_video(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    record_candidates("vid1", ["/old_a.jpg", "/old_b.jpg"])

    record_candidates("vid1", ["/new_a.jpg"])

    assert get_candidates("vid1") == [(0, "/new_a.jpg")]


def test_get_latest_switch_none_when_never_switched(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    assert get_latest_switch("vid1") is None


def test_record_switch_then_get_latest_switch_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    record_switch("vid1", candidate_index=1, views_at_switch=250)

    candidate_index, set_at, views_at_switch = get_latest_switch("vid1")
    assert candidate_index == 1
    assert views_at_switch == 250
    assert set_at is not None


def test_get_latest_switch_returns_the_most_recent_one(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    record_switch("vid1", candidate_index=0, views_at_switch=10)
    record_switch("vid1", candidate_index=2, views_at_switch=50)

    candidate_index, _set_at, views_at_switch = get_latest_switch("vid1")

    assert candidate_index == 2
    assert views_at_switch == 50


def test_get_latest_switch_scoped_to_video_id(tmp_path, monkeypatch):
    monkeypatch.setattr(youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    record_switch("vid1", candidate_index=0, views_at_switch=10)

    assert get_latest_switch("vid2") is None
