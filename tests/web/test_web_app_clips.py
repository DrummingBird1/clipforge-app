# tests/web/test_web_app_clips.py - REST endpoint tests for web_app.py, topic: clips (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
from unittest.mock import MagicMock
import json
import os
import pytest
from tests.web_app_support import (  # noqa: F401
    _ImmediateThread,
    _fake_seo,
    _insert_pending_row,
    _is_ffmpeg_runnable,
    _reset_youtube_upload_state,
    client,
    web_app,
)


def test_api_clips_captured_by_day_returns_dates_and_counts_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))

    resp = client.get("/api/clips_captured_by_day", params={"days": 3})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["dates"]) == 3
    assert data["counts"] == [0, 0, 0]


def test_api_clips_captured_by_day_defaults_to_30_days(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))

    resp = client.get("/api/clips_captured_by_day")

    assert len(resp.json()["dates"]) == 30


def test_api_download_serves_the_file(tmp_path):
    file_path = tmp_path / "result.mp4"
    file_path.write_bytes(b"fake video bytes")
    resp = client.get("/api/download", params={"path": str(file_path)})
    assert resp.status_code == 200
    assert resp.content == b"fake video bytes"
    assert "result.mp4" in resp.headers["content-disposition"]


def test_api_download_missing_file_returns_400():
    resp = client.get("/api/download", params={"path": "Z:\\not_a_real_file.mp4"})
    assert resp.status_code == 400


def test_api_download_rejects_a_file_under_data_dir(tmp_path, monkeypatch):
    # item: בדיקת באגים מקיפה - /api/download לא היה מגביל בכלל איזה קובץ
    # מקומי-קיים אפשר להוריד, כולל קבצים רגישים כמו הטוקן של השרת עצמו.
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))
    sensitive = tmp_path / "web_app_token.txt"
    sensitive.write_text("super-secret-token")

    resp = client.get("/api/download", params={"path": str(sensitive)})

    assert resp.status_code == 403


# --- /api/undo/* (item: undo last file-move operation) ---

def test_api_undo_status_reports_no_pending_batch(tmp_path, monkeypatch):
    from utils.shared import move_undo_log
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))

    resp = client.get("/api/undo/status")

    assert resp.status_code == 200
    assert resp.json() == {"pending": False}


def test_api_undo_status_reports_pending_batch(tmp_path, monkeypatch):
    from utils.shared import move_undo_log
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": "a", "dst": "b"}])

    resp = client.get("/api/undo/status")

    assert resp.status_code == 200
    assert resp.json() == {"pending": True, "script_name": "cleanup_published_sources.py", "file_count": 1}


def test_api_undo_last_move_batch_restores_files(tmp_path, monkeypatch):
    from utils.shared import move_undo_log
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    src = tmp_path / "source" / "clip.mp4"
    dst = tmp_path / "archive" / "clip.mp4"
    src.parent.mkdir()
    dst.parent.mkdir()
    dst.write_bytes(b"archived content")
    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])

    resp = client.post("/api/undo/last_move_batch")

    assert resp.status_code == 200
    assert resp.json() == {"restored": 1, "skipped": 0}
    assert src.exists()
    assert not dst.exists()


def test_api_undo_last_move_batch_with_no_pending_batch_returns_400(tmp_path, monkeypatch):
    from utils.shared import move_undo_log
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))

    resp = client.post("/api/undo/last_move_batch")

    assert resp.status_code == 400


def test_api_undo_last_move_batch_rejects_mismatched_origin(tmp_path, monkeypatch):
    from utils.shared import move_undo_log
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": "a", "dst": "b"}])

    resp = client.post("/api/undo/last_move_batch", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403
    # לא אמור לבצע את הביטול בפועל - ה-batch עדיין ממתין
    assert move_undo_log.get_last_move_batch() is not None


def test_api_undo_last_move_batch_records_audit_log_entry(tmp_path, monkeypatch):
    from utils.shared import move_undo_log
    monkeypatch.setattr(move_undo_log, "UNDO_LOG_PATH", str(tmp_path / "last_move_batch.json"))
    src = tmp_path / "source" / "clip.mp4"
    dst = tmp_path / "archive" / "clip.mp4"
    src.parent.mkdir()
    dst.parent.mkdir()
    dst.write_bytes(b"archived content")
    move_undo_log.record_move_batch("cleanup_published_sources.py", [{"src": str(src), "dst": str(dst)}])
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/undo/last_move_batch")

    assert resp.status_code == 200
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "undo_last_move_batch")
    assert kwargs["details"] == "restored=1"


def test_api_clips_lists_mp4_files_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    old_clip = tmp_path / "old.mp4"
    old_clip.write_bytes(b"old")
    new_clip = tmp_path / "new.mp4"
    new_clip.write_bytes(b"newer-content")
    os.utime(old_clip, (1000, 1000))
    os.utime(new_clip, (2000, 2000))

    resp = client.get("/api/clips")

    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert names == ["new.mp4", "old.mp4"]


# --- /api/clips/thumbnail (item: gallery thumbnails) ---

def test_api_clips_thumbnail_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.get("/api/clips/thumbnail", params={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_clips_thumbnail_missing_path_returns_400():
    resp = client.get("/api/clips/thumbnail", params={"path": ""})
    assert resp.status_code == 400


@pytest.mark.skipif(not _is_ffmpeg_runnable(), reason="ffmpeg/ffprobe לא זמינים בסביבה הזו")
def test_api_clips_thumbnail_extracts_and_caches_a_real_frame(tmp_path, monkeypatch):
    import subprocess
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "THUMBNAIL_CACHE_DIR", str(tmp_path / ".thumbnail_cache"))
    clip = tmp_path / "clip.mp4"
    cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10", "-pix_fmt", "yuv420p", str(clip)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
    assert result.returncode == 0, result.stderr

    resp = client.get("/api/clips/thumbnail", params={"path": str(clip)})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert len(resp.content) > 0

    cache_files = os.listdir(tmp_path / ".thumbnail_cache")
    assert len(cache_files) == 1

    # קריאה שנייה - אותו cache_path בדיוק (אותו mtime מקור), אמורה לשרת מהמטמון
    # בלי לקרוא ל-ffmpeg שוב (לא מדיד ישירות כאן, אבל מוודא שאין קובץ מטמון נוסף/שונה).
    resp2 = client.get("/api/clips/thumbnail", params={"path": str(clip)})
    assert resp2.status_code == 200
    assert os.listdir(tmp_path / ".thumbnail_cache") == cache_files


@pytest.mark.skipif(not _is_ffmpeg_runnable(), reason="ffmpeg/ffprobe לא זמינים בסביבה הזו")
def test_api_clips_thumbnail_invalidates_cache_when_source_changes(tmp_path, monkeypatch):
    import subprocess
    import time
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "THUMBNAIL_CACHE_DIR", str(tmp_path / ".thumbnail_cache"))
    clip = tmp_path / "clip.mp4"

    def _make_clip(color):
        cmd = [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"color=c={color}:size=320x240:duration=2:rate=10", "-pix_fmt", "yuv420p", str(clip)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
        assert result.returncode == 0, result.stderr

    _make_clip("red")
    client.get("/api/clips/thumbnail", params={"path": str(clip)})
    first_cache_files = set(os.listdir(tmp_path / ".thumbnail_cache"))

    time.sleep(1.1)  # mtime ב-int שניות (int(os.path.getmtime(...))) - חייב לזוז לפחות שנייה שלמה
    _make_clip("blue")  # אותו נתיב, תוכן חדש - mtime חדש
    client.get("/api/clips/thumbnail", params={"path": str(clip)})
    second_cache_files = set(os.listdir(tmp_path / ".thumbnail_cache"))

    assert second_cache_files != first_cache_files
    assert len(second_cache_files) == 2  # שני קבצי מטמון (הישן לא נמחק, רק לא בשימוש)


# --- /api/clips/tags, /api/clips/generate_tags (item: content-based auto-tagging) ---

def test_api_clips_tags_returns_none_when_never_tagged(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "TAGS_CACHE_DIR", str(tmp_path / ".tags_cache"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")

    resp = client.get("/api/clips/tags", params={"path": str(clip)})

    assert resp.status_code == 200
    assert resp.json() == {"tags": None}


def test_api_clips_tags_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.get("/api/clips/tags", params={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_clips_generate_tags_caches_result_and_tags_endpoint_then_reads_it(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "TAGS_CACHE_DIR", str(tmp_path / ".tags_cache"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")

    # לא קוראים ל-AI אמיתי בטסט - רק בודקים את השרשור (חילוץ פריימים -> קריאה
    # ל-generate_clip_tags -> מטמון), לכן גם extract_frame_at_timestamp וגם
    # generate_clip_tags עצמו ממופתחים.
    monkeypatch.setattr(web_app, "extract_frame_at_timestamp", lambda *a, **kw: True)
    monkeypatch.setattr(web_app, "get_video_duration_via_ffprobe", lambda *a, **kw: 10.0)
    monkeypatch.setattr(web_app, "generate_clip_tags", lambda frame_paths: ["Goal", "Victory Screen"])

    resp = client.post("/api/clips/generate_tags", json={"path": str(clip)})

    assert resp.status_code == 200
    assert resp.json() == {"tags": ["Goal", "Victory Screen"]}

    # עכשיו /api/clips/tags אמור להחזיר את זה מהמטמון, בלי לקרוא ל-AI שוב
    tags_resp = client.get("/api/clips/tags", params={"path": str(clip)})
    assert tags_resp.json() == {"tags": ["Goal", "Victory Screen"]}


def test_api_clips_generate_tags_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.post("/api/clips/generate_tags", json={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_clips_generate_tags_rejects_mismatched_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")

    resp = client.post(
        "/api/clips/generate_tags", json={"path": str(clip)},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403


def test_api_clips_generate_tags_returns_500_when_no_frames_extracted(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "TAGS_CACHE_DIR", str(tmp_path / ".tags_cache"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")
    monkeypatch.setattr(web_app, "extract_frame_at_timestamp", lambda *a, **kw: False)
    monkeypatch.setattr(web_app, "get_video_duration_via_ffprobe", lambda *a, **kw: 10.0)

    resp = client.post("/api/clips/generate_tags", json={"path": str(clip)})

    assert resp.status_code == 500


# --- /api/clips/all_tags (item: clip gallery search/filter by tag) ---

def test_api_clips_all_tags_returns_empty_list_when_nothing_tagged_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "TAGS_CACHE_DIR", str(tmp_path / ".tags_cache"))

    resp = client.get("/api/clips/all_tags")

    assert resp.status_code == 200
    assert resp.json() == {"tags": []}


def test_api_clips_all_tags_returns_deduped_sorted_tags_across_clips(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app, "TAGS_CACHE_DIR", str(tmp_path / ".tags_cache"))
    monkeypatch.setattr(web_app, "extract_frame_at_timestamp", lambda *a, **kw: True)
    monkeypatch.setattr(web_app, "get_video_duration_via_ffprobe", lambda *a, **kw: 10.0)
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.write_bytes(b"fake-a")
    clip_b.write_bytes(b"fake-b")

    monkeypatch.setattr(web_app, "generate_clip_tags", lambda frame_paths: ["Goal", "Save"])
    client.post("/api/clips/generate_tags", json={"path": str(clip_a)})
    monkeypatch.setattr(web_app, "generate_clip_tags", lambda frame_paths: ["Save", "Explosion"])
    client.post("/api/clips/generate_tags", json={"path": str(clip_b)})

    resp = client.get("/api/clips/all_tags")

    assert resp.json() == {"tags": ["Explosion", "Goal", "Save"]}


# --- /api/clips/friend_tags (item: friend detection via Discord voice channel presence) ---

def test_api_clips_friend_tags_returns_none_when_never_scanned(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(web_app.approval_store, "FRIEND_TAGS_CACHE_DIR", str(tmp_path / ".friend_tags_cache"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")

    resp = client.get("/api/clips/friend_tags", params={"path": str(clip)})

    assert resp.status_code == 200
    assert resp.json() == {"friends": None}


def test_api_clips_friend_tags_returns_cached_names(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    cache_dir = tmp_path / ".friend_tags_cache"
    monkeypatch.setattr(web_app.approval_store, "FRIEND_TAGS_CACHE_DIR", str(cache_dir))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")

    os.makedirs(cache_dir, exist_ok=True)
    with open(web_app._clip_tags_cache_path(str(clip), str(cache_dir)), "w", encoding="utf-8") as f:
        json.dump({"tags": ["Alice", "Bob"]}, f)

    resp = client.get("/api/clips/friend_tags", params={"path": str(clip)})

    assert resp.json() == {"friends": ["Alice", "Bob"]}


def test_api_clips_friend_tags_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.get("/api/clips/friend_tags", params={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_approvals_list_returns_pending_clips_with_game_from_parent_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))
    game_dir = tmp_path / "clips" / "SomeGame"
    game_dir.mkdir(parents=True)
    clip = game_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    _insert_pending_row(str(tmp_path / "test.db"), str(clip))

    resp = client.get("/api/approvals")

    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "path": str(clip), "name": "clip.mp4", "game": "SomeGame", "created_at": resp.json()[0]["created_at"]}]


def test_api_approvals_list_skips_rows_whose_file_no_longer_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))
    _insert_pending_row(str(tmp_path / "test.db"), str(tmp_path / "clips" / "gone.mp4"))

    resp = client.get("/api/approvals")

    assert resp.json() == []


def test_api_approvals_list_empty_when_nothing_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))

    resp = client.get("/api/approvals")

    assert resp.json() == []


def test_api_approvals_decide_approved_moves_clip_and_updates_status(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app.approval_store, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(web_app.approval_store, "REJECTED_DIR", str(tmp_path / "rejected"))
    monkeypatch.setattr(web_app.approval_store, "get_rocket_input_dir", lambda: str(tmp_path / "rocket_input"))
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    pending_id = _insert_pending_row(str(tmp_path / "test.db"), str(clip))

    resp = client.post(f"/api/approvals/{pending_id}/decide", json={"approved": True})

    assert resp.status_code == 200
    assert not clip.exists()
    assert (tmp_path / "rocket_input" / "clip.mp4").exists()


def test_api_approvals_decide_rejected_moves_clip_to_rejected_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app.approval_store, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))
    monkeypatch.setattr(web_app.approval_store, "REJECTED_DIR", str(tmp_path / "rejected"))
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    clip = clips_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    pending_id = _insert_pending_row(str(tmp_path / "test.db"), str(clip))

    resp = client.post(f"/api/approvals/{pending_id}/decide", json={"approved": False})

    assert resp.status_code == 200
    assert not clip.exists()
    assert (tmp_path / "rejected" / "clip.mp4").exists()


def test_api_approvals_decide_rejects_unknown_pending_id(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app.approval_store, "CLIPS_REVIEW_DIR", str(tmp_path / "clips"))

    resp = client.post("/api/approvals/9999/decide", json={"approved": True})

    assert resp.status_code == 400


def test_api_approvals_decide_rejects_mismatched_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app.approval_store, "DB_PATH", str(tmp_path / "test.db"))

    resp = client.post(
        "/api/approvals/1/decide", json={"approved": True},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403


def test_api_clips_stream_serves_file_inside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake video bytes")

    resp = client.get("/api/clips/stream", params={"path": str(clip)})

    assert resp.status_code == 200
    assert resp.content == b"fake video bytes"


def test_api_clips_stream_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.get("/api/clips/stream", params={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_clips_tiktok_export_generates_metadata_and_returns_url(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    mock_seo = MagicMock(return_value=_fake_seo("fake metadata content"))
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", mock_seo)

    resp = client.post("/api/clips/tiktok_export", json={"path": str(clip)})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["tiktok_url"] == web_app.TIKTOK_UPLOAD_URL
    assert data["metadata"] == "fake metadata content"
    assert data["caption"] == "caption #tag" and data["seo_source"] == "template"
    mock_seo.assert_called_once()
    assert os.path.realpath(mock_seo.call_args[0][0]) == os.path.realpath(str(clip))


def test_api_clips_tiktok_export_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.post("/api/clips/tiktok_export", json={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_clips_tiktok_export_requires_same_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    resp = client.post(
        "/api/clips/tiktok_export", json={"path": str(clip)},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403


def test_api_clips_tiktok_export_records_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo("fake metadata")))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/clips/tiktok_export", json={"path": str(clip)})

    assert resp.status_code == 200
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "tiktok_export")
    assert kwargs["details"] == "clip.mp4"


def test_api_clips_youtube_status_reports_configured(monkeypatch):
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)

    resp = client.get("/api/clips/youtube_status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["in_progress"] is False


def test_api_clips_youtube_export_falls_back_when_not_configured(tmp_path, monkeypatch):
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo()))
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: False)
    mock_upload = MagicMock()
    monkeypatch.setattr(web_app.youtube_uploader, "upload_video", mock_upload)

    resp = client.post("/api/clips/youtube_export", json={"path": str(clip)})

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["fallback_url"] == web_app.YOUTUBE_UPLOAD_FALLBACK_URL
    mock_upload.assert_not_called()


def test_api_clips_youtube_export_starts_upload_when_configured(tmp_path, monkeypatch):
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo()))
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)

    def fake_upload(path, title, description="", tags=None, privacy_status="private", progress_callback=None):
        if progress_callback:
            progress_callback(50)
        return "fake-video-id"

    monkeypatch.setattr(web_app.youtube_uploader, "upload_video", fake_upload)
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)

    resp = client.post("/api/clips/youtube_export", json={"path": str(clip)})

    assert resp.status_code == 200
    data = resp.json()
    assert data == {"configured": True, "started": True}

    status_resp = client.get("/api/clips/youtube_status")
    status = status_resp.json()
    assert status["in_progress"] is False
    assert status["success"] is True
    assert status["video_id"] == "fake-video-id"
    assert status["percent"] == 100
    _reset_youtube_upload_state()


@pytest.mark.parametrize("source,expected", [
    ("ai", ("AI title", "one line\n\n#rl #gaming", ["rl", "gaming"])),
    ("template", ("Shorts #7", "", ["gaming", "shorts"])),
])
def test_api_clips_youtube_export_uploads_with_gemini_seo_only_when_ai(tmp_path, monkeypatch, source, expected):
    # גל 32: כותרת/תיאור/תגיות מ-Gemini כשיש; בלי - שם הקובץ (מערכת המונה) כמו קודם
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "Shorts #7.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo(source=source)))
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    uploads = []
    monkeypatch.setattr(web_app.youtube_uploader, "upload_video",
                        lambda path, title, description="", tags=None, **_kw: uploads.append((title, description, tags)) or "vid")
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)

    assert client.post("/api/clips/youtube_export", json={"path": str(clip)}).status_code == 200

    assert uploads == [expected]


def test_api_clips_tiktok_export_still_opens_tiktok_when_seo_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(side_effect=PermissionError("read-only folder")))

    resp = client.post("/api/clips/tiktok_export", json={"path": str(clip)})

    assert resp.status_code == 200
    assert resp.json()["tiktok_url"] == web_app.TIKTOK_UPLOAD_URL and resp.json()["caption"] == ""


def test_api_clips_youtube_export_records_audit_log_entry(tmp_path, monkeypatch):
    # רק כשההעלאה בפועל *מתחילה* (configured=True) - לא בנתיב ה-fallback
    # (configured=False), כי אין שום פעולה אמיתית לתעד שם.
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo()))
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    monkeypatch.setattr(web_app.youtube_uploader, "upload_video", MagicMock(return_value="fake-video-id"))
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/clips/youtube_export", json={"path": str(clip)})

    assert resp.status_code == 200
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "youtube_export")
    assert kwargs["details"] == "clip.mp4"
    _reset_youtube_upload_state()


def test_api_clips_youtube_export_reports_failure(tmp_path, monkeypatch):
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo()))
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)

    def failing_upload(path, title, description="", tags=None, privacy_status="private", progress_callback=None):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(web_app.youtube_uploader, "upload_video", failing_upload)
    monkeypatch.setattr(web_app.threading, "Thread", _ImmediateThread)

    resp = client.post("/api/clips/youtube_export", json={"path": str(clip)})

    assert resp.status_code == 200
    status = client.get("/api/clips/youtube_status").json()
    assert status["success"] is False
    assert "quota exceeded" in status["error"]
    _reset_youtube_upload_state()


def test_api_clips_youtube_export_rejects_when_already_in_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(web_app, "generate_seo_with_sheet", MagicMock(return_value=_fake_seo()))
    monkeypatch.setattr(web_app.youtube_uploader, "is_configured", lambda: True)
    with web_app._youtube_upload_lock:
        web_app._youtube_upload_state["in_progress"] = True

    try:
        resp = client.post("/api/clips/youtube_export", json={"path": str(clip)})
        assert resp.status_code == 409
    finally:
        _reset_youtube_upload_state()


def test_api_clips_youtube_export_rejects_path_outside_clips_dir(tmp_path, monkeypatch):
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path / "clips"))
    outside_file = tmp_path / "not_a_clip.mp4"
    outside_file.write_bytes(b"x")

    resp = client.post("/api/clips/youtube_export", json={"path": str(outside_file)})

    assert resp.status_code == 400


def test_api_clips_youtube_export_requires_same_origin(tmp_path, monkeypatch):
    _reset_youtube_upload_state()
    monkeypatch.setattr(web_app, "CLIPS_DIR", str(tmp_path))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    resp = client.post(
        "/api/clips/youtube_export", json={"path": str(clip)},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403


# --- Waveform viewer (12/N desktop-parity gaps): /api/waveform ---

def test_api_waveform_returns_peaks_for_real_audio_file(tmp_path):
    # קובץ WAV אמיתי (לא מוקאפ), בלי תלות בהתקנת ffmpeg בכלל - pydub קורא WAV
    # ישירות דרך wave/audioop (AudioSegment._from_safe_wav), לא דרך subprocess
    # ffmpeg, בדיוק כמו tests/studio/test_ffmpeg_progress.py שמזייף ffmpeg עם
    # sys.executable כדי לא להניח שffmpeg מותקן בסביבת ה-CI.
    import math
    import struct
    import wave

    audio_path = tmp_path / "test_tone.wav"
    sample_rate = 8000
    num_samples = sample_rate  # שנייה אחת
    with wave.open(str(audio_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        frames = [int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate)) for i in range(num_samples)]
        wav_file.writeframes(struct.pack(f"<{num_samples}h", *frames))

    resp = client.get("/api/waveform", params={"path": str(audio_path)})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["peaks"]) > 0
    assert data["max_peak"] > 0
    assert max(data["peaks"]) == data["max_peak"]


def test_api_waveform_rejects_missing_file(tmp_path):
    resp = client.get("/api/waveform", params={"path": str(tmp_path / "does_not_exist.mp4")})

    assert resp.status_code == 400


def test_api_waveform_rejects_empty_path():
    resp = client.get("/api/waveform")

    assert resp.status_code == 400


def test_api_waveform_rejects_a_file_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))
    sensitive = tmp_path / "config.json"
    sensitive.write_text("{}")

    resp = client.get("/api/waveform", params={"path": str(sensitive)})

    assert resp.status_code == 403


def test_api_waveform_reports_error_for_unreadable_file(tmp_path):
    not_audio = tmp_path / "not_audio.mp4"
    not_audio.write_text("this is plain text, not a real media file", encoding="utf-8")

    resp = client.get("/api/waveform", params={"path": str(not_audio)})

    assert resp.status_code == 500
    assert "error" in resp.json()
