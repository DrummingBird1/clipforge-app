# tests/web/test_web_app_video.py - REST endpoint tests for web_app.py, topic: video (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
import pytest
from tests.web_app_support import (  # noqa: F401
    _isolate_vep_paths,
    _make_test_png,
    client,
    web_app,
)


def test_api_render_stats_reports_average_durations_by_script(monkeypatch):
    monkeypatch.setattr(
        web_app.job_history, "get_average_render_durations",
        lambda: [("video_editor.py", 42.5, 10), ("story_cutter.py", 91.0, 3)],
    )

    resp = client.get("/api/render_stats")

    assert resp.status_code == 200
    assert resp.json() == [
        {"script": "video_editor.py", "avg_seconds": 42.5, "run_count": 10},
        {"script": "story_cutter.py", "avg_seconds": 91.0, "run_count": 3},
    ]


def test_api_render_stats_empty_when_no_successful_runs(monkeypatch):
    monkeypatch.setattr(web_app.job_history, "get_average_render_durations", lambda: [])

    resp = client.get("/api/render_stats")

    assert resp.status_code == 200
    assert resp.json() == []


def test_api_hwaccel_savings_returns_none_when_no_comparison(monkeypatch):
    monkeypatch.setattr(web_app.job_history, "get_hwaccel_time_comparison", lambda: None)

    resp = client.get("/api/hwaccel_savings")

    assert resp.status_code == 200
    assert resp.json() is None


def test_api_hwaccel_savings_returns_comparison_when_available(monkeypatch):
    fake_comparison = {
        "hwaccel_avg_seconds_per_file": 2.0, "hwaccel_run_count": 5,
        "no_hwaccel_avg_seconds_per_file": 4.0, "no_hwaccel_run_count": 3,
        "percent_faster": 50.0,
    }
    monkeypatch.setattr(web_app.job_history, "get_hwaccel_time_comparison", lambda: fake_comparison)

    resp = client.get("/api/hwaccel_savings")

    assert resp.status_code == 200
    assert resp.json() == fake_comparison


def test_api_video_editor_presets_matches_shared_source():
    resp = client.get("/api/video_editor_presets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for preset in data.values():
        assert set(preset.keys()) == {"vertical", "target_seconds", "keep_audio", "loudnorm", "codec"}


# --- /api/video_editor_profiles (item: פרופיל אישי ל"עורך-העל") ---

def test_api_video_editor_profiles_list_empty_by_default(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    resp = client.get("/api/video_editor_profiles")

    assert resp.status_code == 200
    assert resp.json() == {}


def test_api_video_editor_profiles_save_then_list(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    resp = client.post("/api/video_editor_profiles", json={
        "name": "Rocket League",
        "settings": {"watermark_path": "C:\\logo.png", "vertical": True, "codec": "hevc"},
    })
    assert resp.status_code == 200

    listed = client.get("/api/video_editor_profiles").json()
    assert listed["Rocket League"]["watermark_path"] == "C:\\logo.png"
    assert listed["Rocket League"]["vertical"] is True
    assert listed["Rocket League"]["codec"] == "hevc"


def test_api_video_editor_profiles_save_then_list_includes_favorite_fields(tmp_path, monkeypatch):
    # item: תיבת העדפות לכל פרופיל - favorite_fields (CSV) עובר דרך אותו
    # /api/video_editor_profiles POST כמו כל שדה אחר ב-PROFILE_FIELDS.
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    resp = client.post("/api/video_editor_profiles", json={
        "name": "WithFavorites",
        "settings": {"codec": "h264", "favorite_fields": "vertical,codec"},
    })
    assert resp.status_code == 200

    listed = client.get("/api/video_editor_profiles").json()
    assert listed["WithFavorites"]["favorite_fields"] == "vertical,codec"


def test_api_video_editor_profiles_save_same_name_twice_overwrites_not_duplicates(tmp_path, monkeypatch):
    # item: אפשרות לעדכן פרופיל קיים - אין endpoint נפרד ל-"עדכון", updateVideoEditorProfile()
    # ב-JS פשוט שולח POST שוב עם אותו שם - סומך על כך ש-save_profile דורסת.
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    client.post("/api/video_editor_profiles", json={"name": "Rocket League", "settings": {"codec": "h264", "vertical": False}})
    resp = client.post("/api/video_editor_profiles", json={"name": "Rocket League", "settings": {"codec": "av1", "vertical": True}})
    assert resp.status_code == 200

    listed = client.get("/api/video_editor_profiles").json()
    assert list(listed.keys()) == ["Rocket League"]
    assert listed["Rocket League"]["codec"] == "av1"
    assert listed["Rocket League"]["vertical"] is True


def test_api_video_editor_profiles_save_rejects_blank_name(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    resp = client.post("/api/video_editor_profiles", json={"name": "   ", "settings": {}})

    assert resp.status_code == 400
    assert client.get("/api/video_editor_profiles").json() == {}


def test_api_video_editor_profiles_delete_removes_saved_profile(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    client.post("/api/video_editor_profiles", json={"name": "ToDelete", "settings": {"codec": "h264"}})

    resp = client.delete("/api/video_editor_profiles/ToDelete")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": True}
    assert "ToDelete" not in client.get("/api/video_editor_profiles").json()


def test_api_video_editor_reset_counter_resets_to_the_given_value(monkeypatch):
    # item: מספור סרטונים - עריכת "מספר התחלתי" בממשק היא "שינוי ידני" מפורש
    # שאמור לאפס את המונה האמיתי *עכשיו* (לא רק להישלח כ---number-start
    # לריצה הבאה, שם זה מתעלם כליל אם קובץ המונה כבר קיים).
    calls = []
    monkeypatch.setattr(web_app, "save_video_editor_counter", lambda value: calls.append(value))

    resp = client.post("/api/video_editor/reset_counter", json={"value": 571})

    assert resp.status_code == 200
    assert resp.json() == {"value": 571}
    assert calls == [571]


def test_api_video_editor_reset_counter_rejects_non_numeric_value(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "save_video_editor_counter", lambda value: calls.append(value))

    resp = client.post("/api/video_editor/reset_counter", json={"value": "not-a-number"})

    assert resp.status_code == 400
    assert calls == []


def test_api_video_editor_reset_counter_clamps_below_one_to_one(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "save_video_editor_counter", lambda value: calls.append(value))

    resp = client.post("/api/video_editor/reset_counter", json={"value": -5})

    assert resp.status_code == 200
    assert calls == [1]


def test_api_video_editor_profiles_delete_missing_profile_returns_false(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    resp = client.delete("/api/video_editor_profiles/NeverExisted")

    assert resp.status_code == 200
    assert resp.json() == {"deleted": False}


# --- POST /api/video_editor_profiles/{name}/rename (item: שינוי שם לפרופיל) ---

def test_api_video_editor_profiles_rename_moves_settings_to_new_name(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    client.post("/api/video_editor_profiles", json={"name": "OldName", "settings": {"codec": "hevc", "vertical": True}})

    resp = client.post("/api/video_editor_profiles/OldName/rename", json={"new_name": "NewName"})

    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"
    listed = client.get("/api/video_editor_profiles").json()
    assert "OldName" not in listed
    assert listed["NewName"]["codec"] == "hevc"
    assert listed["NewName"]["vertical"] is True


def test_api_video_editor_profiles_rename_missing_profile_returns_400(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))

    resp = client.post("/api/video_editor_profiles/NeverExisted/rename", json={"new_name": "Whatever"})

    assert resp.status_code == 400
    assert "error" in resp.json()


def test_api_video_editor_profiles_rename_rejects_name_already_taken(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    client.post("/api/video_editor_profiles", json={"name": "First", "settings": {"codec": "h264"}})
    client.post("/api/video_editor_profiles", json={"name": "Second", "settings": {"codec": "av1"}})

    resp = client.post("/api/video_editor_profiles/First/rename", json={"new_name": "Second"})

    assert resp.status_code == 400
    listed = client.get("/api/video_editor_profiles").json()
    assert listed["First"]["codec"] == "h264"
    assert listed["Second"]["codec"] == "av1"


def test_api_video_editor_profiles_rename_rejects_blank_new_name(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    client.post("/api/video_editor_profiles", json={"name": "Original", "settings": {"codec": "h264"}})

    resp = client.post("/api/video_editor_profiles/Original/rename", json={"new_name": "   "})

    assert resp.status_code == 400


def test_api_video_editor_profiles_duplicate_creates_copy(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Original", "settings": {"codec": "hevc"}})

    resp = client.post("/api/video_editor_profiles/Original/duplicate", json={"new_name": "Copy"})

    assert resp.status_code == 200
    listed = client.get("/api/video_editor_profiles").json()
    assert listed["Original"]["codec"] == "hevc"
    assert listed["Copy"]["codec"] == "hevc"


def test_api_video_editor_profiles_duplicate_rejects_taken_name(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "A", "settings": {"codec": "h264"}})
    client.post("/api/video_editor_profiles", json={"name": "B", "settings": {"codec": "av1"}})

    resp = client.post("/api/video_editor_profiles/A/duplicate", json={"new_name": "B"})

    assert resp.status_code == 400


# --- GET/POST /api/video_editor_profiles export/import (item) ---

def test_api_video_editor_profiles_export_returns_settings(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "ToExport", "settings": {"codec": "hevc", "vertical": True}})

    resp = client.get("/api/video_editor_profiles/ToExport/export")

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "ToExport"
    assert body["settings"]["codec"] == "hevc"


def test_api_video_editor_profiles_export_missing_returns_404(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    resp = client.get("/api/video_editor_profiles/NeverExisted/export")
    assert resp.status_code == 404


def test_api_video_editor_profiles_import_creates_profile(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)

    resp = client.post("/api/video_editor_profiles/import", json={"name": "Imported", "settings": {"codec": "av1"}})

    assert resp.status_code == 200
    assert client.get("/api/video_editor_profiles").json()["Imported"]["codec"] == "av1"


def test_api_video_editor_profiles_import_rejects_existing_without_overwrite(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Existing", "settings": {"codec": "h264"}})

    resp = client.post("/api/video_editor_profiles/import", json={"name": "Existing", "settings": {"codec": "av1"}})

    assert resp.status_code == 400
    assert client.get("/api/video_editor_profiles").json()["Existing"]["codec"] == "h264"


def test_api_video_editor_profiles_import_overwrites_when_allowed(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Existing", "settings": {"codec": "h264"}})

    resp = client.post("/api/video_editor_profiles/import", json={"name": "Existing", "settings": {"codec": "av1"}, "overwrite": True})

    assert resp.status_code == 200
    assert client.get("/api/video_editor_profiles").json()["Existing"]["codec"] == "av1"


# --- GET /api/video_editor_profiles/diff (item: השוואת פרופילים) ---

def test_api_video_editor_profiles_diff_returns_only_differing_fields(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "A", "settings": {"codec": "h264", "vertical": True}})
    client.post("/api/video_editor_profiles", json={"name": "B", "settings": {"codec": "hevc", "vertical": True}})

    resp = client.get("/api/video_editor_profiles/diff", params={"a": "A", "b": "B"})

    assert resp.status_code == 200
    assert resp.json()["diff"] == {"codec": ["h264", "hevc"]}


def test_api_video_editor_profiles_diff_missing_profile_returns_404(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "A", "settings": {"codec": "h264"}})

    resp = client.get("/api/video_editor_profiles/diff", params={"a": "A", "b": "NeverExisted"})

    assert resp.status_code == 404


# --- GET /api/video_editor_profiles/{name}/meta (item: חותמת בשימוש לאחרונה) ---

def test_api_video_editor_profiles_meta_defaults_for_unused_profile(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Fresh", "settings": {"codec": "h264"}})

    resp = client.get("/api/video_editor_profiles/Fresh/meta")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_count"] == 0
    assert body["last_used_at"] is None
    assert body["schema_version"] == 1


# --- GET/POST /api/video_editor_profiles/{name}/history + /revert (item: undo לפרופיל) ---

def test_api_video_editor_profiles_history_empty_for_fresh_profile(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Fresh", "settings": {"codec": "h264"}})

    resp = client.get("/api/video_editor_profiles/Fresh/history")

    assert resp.status_code == 200
    assert resp.json()["history"] == []


def test_api_video_editor_profiles_history_populated_after_overwrite(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Evolving", "settings": {"codec": "h264"}})
    client.post("/api/video_editor_profiles", json={"name": "Evolving", "settings": {"codec": "hevc"}})

    resp = client.get("/api/video_editor_profiles/Evolving/history")

    history = resp.json()["history"]
    assert len(history) == 1
    assert history[0]["codec"] == "h264"


def test_api_video_editor_profiles_history_includes_saved_at_over_http():
    # item: רגרסיה אמיתית שנתפסה בבדיקה חיה בדפדפן - FastAPI's jsonable_encoder
    # מוחק בשקט מפתחות המתחילים ב-"_" מתוך dict מקונן (בתוך list, כאן) אבל לא
    # ברמה העליונה של ה-response - נבדק ישירות כאן דרך client.get האמיתי (לא
    # קריאה ישירה ל-get_profile_history, שהייתה עוברת מעל ה-HTTP serialization
    # ומפספסת בדיוק את הבאג הזה). "saved_at" (בלי "_") הוא התיקון בכוונה.
    import utils.video.video_editor_profiles as vep
    with pytest.MonkeyPatch.context() as mp:
        import tempfile
        tmpdir = tempfile.mkdtemp()
        mp.setattr(vep, "PROFILES_PATH", tmpdir + "/p.json")
        mp.setattr(vep, "META_PATH", tmpdir + "/m.json")
        mp.setattr(vep, "HISTORY_PATH", tmpdir + "/h.json")
        client.post("/api/video_editor_profiles", json={"name": "Y", "settings": {"codec": "h264"}})
        client.post("/api/video_editor_profiles", json={"name": "Y", "settings": {"codec": "hevc"}})
        resp = client.get("/api/video_editor_profiles/Y/history")
        assert "saved_at" in resp.text
        assert resp.json()["history"][0]["saved_at"] is not None


def test_api_video_editor_profiles_revert_restores_previous_settings(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "Reverting", "settings": {"codec": "h264"}})
    client.post("/api/video_editor_profiles", json={"name": "Reverting", "settings": {"codec": "hevc"}})

    resp = client.post("/api/video_editor_profiles/Reverting/revert", json={"index": -1})

    assert resp.status_code == 200
    assert resp.json()["settings"]["codec"] == "h264"
    assert client.get("/api/video_editor_profiles").json()["Reverting"]["codec"] == "h264"


def test_api_video_editor_profiles_revert_out_of_range_returns_400(tmp_path, monkeypatch):
    _isolate_vep_paths(tmp_path, monkeypatch)
    client.post("/api/video_editor_profiles", json={"name": "NoHistory", "settings": {"codec": "h264"}})

    resp = client.post("/api/video_editor_profiles/NoHistory/revert", json={"index": -1})

    assert resp.status_code == 400


def test_api_watermark_preview_computes_real_geometry(tmp_path):
    wm_path = _make_test_png(tmp_path, (200, 200))
    resp = client.get("/api/watermark_preview", params={"path": wm_path, "vertical": "false", "position": "bottom-right"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_width"] == 1920
    assert data["output_height"] == 1080
    assert data["target_w"] == 288  # 15% מ-1920, זהה ל-tests/studio/test_video_editor.py
    assert data["x"] == 1920 - 288 - 20
    assert data["y"] == 1080 - 288 - 20


def test_api_watermark_preview_vertical_uses_vertical_dimensions(tmp_path):
    wm_path = _make_test_png(tmp_path, (200, 200))
    resp = client.get("/api/watermark_preview", params={"path": wm_path, "vertical": "true"})
    data = resp.json()
    assert data["output_width"] == 1080
    assert data["output_height"] == 1920


def test_api_watermark_preview_missing_file_returns_400():
    resp = client.get("/api/watermark_preview", params={"path": "Z:\\not_a_real_file.png"})
    assert resp.status_code == 400


def test_api_watermark_preview_invalid_position_returns_400(tmp_path):
    wm_path = _make_test_png(tmp_path, (200, 200))
    resp = client.get("/api/watermark_preview", params={"path": wm_path, "position": "middle-ish"})
    assert resp.status_code == 400


def test_api_watermark_preview_accepts_new_center_positions(tmp_path):
    wm_path = _make_test_png(tmp_path, (200, 200))
    resp = client.get("/api/watermark_preview", params={"path": wm_path, "position": "top-center"})
    assert resp.status_code == 200


def test_api_watermark_preview_custom_xy_overrides_position(tmp_path):
    # item: גרירת watermark חופשית - custom_x/custom_y גוברים על position כליל.
    wm_path = _make_test_png(tmp_path, (200, 200))
    resp = client.get("/api/watermark_preview", params={
        "path": wm_path, "position": "bottom-right", "custom_x": "0.5", "custom_y": "0.5",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["x"] + data["target_w"] / 2 == 1920 / 2
    assert data["y"] + data["target_h"] / 2 == 1080 / 2


def test_api_watermark_preview_respects_custom_scale(tmp_path):
    wm_path = _make_test_png(tmp_path, (200, 200))
    resp = client.get("/api/watermark_preview", params={"path": wm_path, "position": "center", "scale": "0.3"})
    data = resp.json()
    assert data["target_w"] == int(1920 * 0.3)


def test_api_watermark_image_serves_the_file(tmp_path):
    wm_path = _make_test_png(tmp_path, (50, 50))
    resp = client.get("/api/watermark_image", params={"path": wm_path})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_api_watermark_image_rejects_non_image_extension(tmp_path):
    text_path = tmp_path / "not_an_image.txt"
    text_path.write_text("hello")
    resp = client.get("/api/watermark_image", params={"path": str(text_path)})
    assert resp.status_code == 400


def test_api_watermark_image_rejects_a_file_under_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))
    wm_path = _make_test_png(tmp_path, (50, 50))

    resp = client.get("/api/watermark_image", params={"path": wm_path})

    assert resp.status_code == 403
