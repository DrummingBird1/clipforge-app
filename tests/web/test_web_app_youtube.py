# tests/web/test_web_app_youtube.py - REST endpoint tests for web_app.py, topic: youtube (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
from unittest.mock import MagicMock
from tests.web_app_support import (  # noqa: F401
    _ImmediateThread,
    _reset_youtube_analytics_refresh_state,
    client,
    web_app,
)


def test_api_youtube_analytics_list_returns_recorded_videos(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")

    resp = client.get("/api/youtube_analytics")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["video_id"] == "vid1"
    assert data[0]["views"] is None


def test_api_youtube_analytics_list_empty_when_nothing_uploaded(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))

    resp = client.get("/api/youtube_analytics")

    assert resp.json() == []


def test_api_youtube_analytics_refresh_rejects_when_not_configured(monkeypatch):
    _reset_youtube_analytics_refresh_state()
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: False)

    resp = client.post("/api/youtube_analytics/refresh")

    assert resp.status_code == 400


def test_api_youtube_analytics_refresh_requires_same_origin(monkeypatch):
    _reset_youtube_analytics_refresh_state()
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)

    resp = client.post("/api/youtube_analytics/refresh", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403


def test_api_youtube_analytics_refresh_updates_cached_stats_for_each_video(tmp_path, monkeypatch):
    _reset_youtube_analytics_refresh_state()
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    monkeypatch.setattr(web_app.youtube_analytics, "get_video_stats", lambda video_id: {"views": 10, "likes": 2, "comments": 1})
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)

    resp = client.post("/api/youtube_analytics/refresh")

    assert resp.status_code == 200
    assert resp.json() == {"started": True}
    status = client.get("/api/youtube_analytics/refresh_status").json()
    assert status == {"in_progress": False, "updated": 1, "errors": [], "done": True}
    rows = client.get("/api/youtube_analytics").json()
    assert rows[0]["views"] == 10
    _reset_youtube_analytics_refresh_state()


def test_api_youtube_analytics_refresh_skips_videos_that_no_longer_exist(tmp_path, monkeypatch):
    _reset_youtube_analytics_refresh_state()
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    monkeypatch.setattr(web_app.youtube_analytics, "get_video_stats", lambda video_id: None)
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)

    client.post("/api/youtube_analytics/refresh")

    status = client.get("/api/youtube_analytics/refresh_status").json()
    assert status["updated"] == 0
    _reset_youtube_analytics_refresh_state()


def test_api_youtube_analytics_refresh_collects_errors_without_stopping(tmp_path, monkeypatch):
    _reset_youtube_analytics_refresh_state()
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "Clip 1")
    web_app.youtube_publish_log.record_upload("vid2", "clip2.mp4", "Clip 2")
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)

    def fake_get_stats(video_id):
        if video_id == "vid2":
            raise RuntimeError("insufficient scope")
        return {"views": 5, "likes": 1, "comments": 0}

    monkeypatch.setattr(web_app.youtube_analytics, "get_video_stats", fake_get_stats)
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)

    client.post("/api/youtube_analytics/refresh")

    status = client.get("/api/youtube_analytics/refresh_status").json()
    assert status["updated"] == 1
    assert len(status["errors"]) == 1
    assert "insufficient scope" in status["errors"][0]
    _reset_youtube_analytics_refresh_state()


def test_api_youtube_analytics_refresh_rejects_when_already_in_progress(monkeypatch):
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    with web_app._youtube_analytics_refresh_lock:
        web_app._youtube_analytics_refresh_state["in_progress"] = True

    try:
        resp = client.post("/api/youtube_analytics/refresh")
        assert resp.status_code == 409
    finally:
        _reset_youtube_analytics_refresh_state()


# --- A/B thumbnail testing (item: A/B thumbnail testing) ---

def test_api_youtube_analytics_list_includes_null_thumbnail_switch_when_never_switched(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")

    resp = client.get("/api/youtube_analytics")

    assert resp.json()[0]["thumbnail_switch"] is None


def test_api_youtube_analytics_list_includes_views_gained_since_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    web_app.youtube_publish_log.update_cached_stats("vid1", views=150, likes=10, comments=1)
    web_app.youtube_thumbnail_log.record_switch("vid1", candidate_index=1, views_at_switch=100)

    resp = client.get("/api/youtube_analytics")

    switch = resp.json()[0]["thumbnail_switch"]
    assert switch["candidate_index"] == 1
    assert switch["views_at_switch"] == 100
    assert switch["views_gained_since_switch"] == 50


def test_api_youtube_thumbnail_candidates_list_returns_indices(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_thumbnail_log.record_candidates("vid1", ["/a.jpg", "/b.jpg", "/c.jpg"])

    resp = client.get("/api/youtube_analytics/vid1/thumbnail_candidates")

    assert resp.json() == [{"index": 0}, {"index": 1}, {"index": 2}]


def test_api_youtube_thumbnail_candidate_image_serves_the_real_file(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    image_path = tmp_path / "candidate_0.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    web_app.youtube_thumbnail_log.record_candidates("vid1", [str(image_path)])

    resp = client.get("/api/youtube_analytics/vid1/thumbnail_candidates/0/image")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == b"fake-jpeg-bytes"


def test_api_youtube_thumbnail_candidate_image_404_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    resp = client.get("/api/youtube_analytics/vid1/thumbnail_candidates/0/image")

    assert resp.status_code == 404


def test_api_youtube_set_thumbnail_success_records_switch_with_current_views(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_publish_log, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    web_app.youtube_publish_log.record_upload("vid1", "clip.mp4", "My Clip")
    web_app.youtube_publish_log.update_cached_stats("vid1", views=77, likes=5, comments=1)
    image_path = tmp_path / "candidate_0.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    web_app.youtube_thumbnail_log.record_candidates("vid1", [str(image_path)])
    mock_set = MagicMock()
    monkeypatch.setattr(web_app.youtube_analytics, "set_video_thumbnail", mock_set)

    resp = client.post("/api/youtube_analytics/vid1/set_thumbnail", json={"candidate_index": 0})

    assert resp.status_code == 200
    mock_set.assert_called_once_with("vid1", str(image_path))
    latest = web_app.youtube_thumbnail_log.get_latest_switch("vid1")
    assert latest == (0, latest[1], 77)


def test_api_youtube_set_thumbnail_404_when_candidate_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    resp = client.post("/api/youtube_analytics/vid1/set_thumbnail", json={"candidate_index": 0})

    assert resp.status_code == 400


def test_api_youtube_set_thumbnail_returns_500_when_api_call_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    image_path = tmp_path / "candidate_0.jpg"
    image_path.write_bytes(b"fake-jpeg-bytes")
    web_app.youtube_thumbnail_log.record_candidates("vid1", [str(image_path)])
    monkeypatch.setattr(web_app.youtube_analytics, "set_video_thumbnail", MagicMock(side_effect=RuntimeError("quota exceeded")))

    resp = client.post("/api/youtube_analytics/vid1/set_thumbnail", json={"candidate_index": 0})

    assert resp.status_code == 500


def test_api_youtube_set_thumbnail_requires_same_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))

    resp = client.post(
        "/api/youtube_analytics/vid1/set_thumbnail", json={"candidate_index": 0},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403
