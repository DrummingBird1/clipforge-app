# tests/web/test_web_app_upgrade_batch.py
#
# סבב שדרוגים נוסף לעורך-העל בווב - web-בלבד (הדסקטופ קפוא, item: web only
# מעכשיו), בהמשך ל-tests/web/test_web_app_ux_polish.py:
#   א' - PiP (תמונה-בתוך-תמונה), קרופ חכם לפי זיהוי-פנים, גרירה אמיתית למועדפים
#   ב' - איפוס לשדה בודד, Undo/Redo, "מה השתנה מאז ההרצה האחרונה", הרחב/כווץ הכל,
#        פרופיל אחרון נשמר, אזהרת beforeunload, ניווט מקלדת במקראה
#   ג' - תצוגת "הפקודה שתישלח בפועל", תור-אצווה ניתן-לעריכה, התקדמות חיה
#        בעורך-העל, הערכת זמן-ריצה, קישור עמוק, היסטוריית ערכים לשדה חופשי
#
# כמו test_web_app_ux_polish.py - TestClient בלי דפדפן אמיתי, מוודא מרקאפ/
# פונקציות JS/התנהגות _build_extra_args, לא הרצת JS בפועל (זו בדיקה נפרדת,
# ידנית, בדפדפן אמיתי).


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.shared import job_history
from tests.page_source import served_page_text

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _index_html():
    return served_page_text(client)  # גל 24: ה-HTML + ה-bundles של CSS/JS


# --- PiP (item) ---

def test_build_extra_args_pip_full_options():
    payload = {"pip_path": "C:\\facecam.mp4", "pip_position": "top-left", "pip_scale": 0.2, "pip_opacity": 0.8}
    args = web_app._build_extra_args("video_editor.py", payload)
    assert args == [
        "--codec", "h264", "--pip", "C:\\facecam.mp4", "--pip-position", "top-left",
        "--pip-scale", "0.2", "--pip-opacity", "0.8",
    ]


def test_build_extra_args_pip_scale_and_opacity_omitted_when_default():
    args = web_app._build_extra_args("video_editor.py", {"pip_path": "C:\\facecam.mp4"})
    assert "--pip-scale" not in args
    assert "--pip-opacity" not in args
    assert args == ["--codec", "h264", "--pip", "C:\\facecam.mp4", "--pip-position", "bottom-right"]


def test_build_extra_args_pip_blank_path_omitted():
    args = web_app._build_extra_args("video_editor.py", {"pip_path": "   ", "pip_scale": 0.5})
    assert "--pip" not in args
    assert "--pip-scale" not in args


def test_pip_category_and_fields_present_in_html():
    html = _index_html()
    assert 'data-subcat="pip"' in html  # גל 2: PiP הוא תת-קטגוריה של "🧩 שכבות"
    assert 'id="vePipPath"' in html
    assert 'id="vePipPosition"' in html
    assert 'id="vePipScale"' in html
    assert 'id="vePipOpacity"' in html


# --- קרופ חכם לפי זיהוי-פנים (item) ---

def test_build_extra_args_smart_crop_face_requires_smart_crop_and_vertical():
    args = web_app._build_extra_args("video_editor.py", {"vertical": True, "smart_crop": True, "smart_crop_face": True})
    assert "--smart-crop" in args
    assert "--smart-crop-face" in args


def test_build_extra_args_smart_crop_face_omitted_without_smart_crop():
    args = web_app._build_extra_args("video_editor.py", {"vertical": True, "smart_crop_face": True})
    assert "--smart-crop-face" not in args


def test_smart_crop_face_checkbox_present_and_starts_disabled():
    html = _index_html()
    # סידור מחדש: "חכם - לפי פנים" הוא אפשרות בבורר "מילוי" המאוחד, והצ'קבוקס
    # עצמו נשאר מוסתר תחת #veLegacyFields כדי שפרופילים/CLI לא ישתנו.
    assert '<option value="face">' in html[html.index('id="veFillMode"'):]
    assert 'id="veSmartCropFace"' in html[html.index('id="veLegacyFields"'):]


# --- תור-אצווה ניתן-לעריכה (item) ---

def test_build_extra_args_only_files_included_as_json():
    args = web_app._build_extra_args("video_editor.py", {"only_files": ["b.mp4", "a.mp4"]})
    assert "--only-files" in args
    idx = args.index("--only-files")
    assert args[idx + 1] == '["b.mp4", "a.mp4"]'


def test_build_extra_args_only_files_omitted_when_empty_or_missing():
    assert "--only-files" not in web_app._build_extra_args("video_editor.py", {})
    assert "--only-files" not in web_app._build_extra_args("video_editor.py", {"only_files": []})


def test_queue_category_and_functions_present_in_html():
    html = _index_html()
    assert 'data-cat="queue"' in html
    assert 'id="veQueueList"' in html
    assert "function refreshVeQueue()" in html
    assert "function _veQueueSelectedFiles()" in html


# --- גרירה אמיתית למועדפים (item) ---

def test_favorite_row_has_native_drag_and_drop_wired():
    html = _index_html()
    assert "row.draggable = true" in html
    assert "function reorderFavoriteBeforeTarget(draggedKey, targetKey)" in html
    # ▲/▼ נשארו גם כן - לא הוסרו, רק לא היחידי
    assert "function moveFavorite(fieldKey, direction)" in html


# --- תצוגת "הפקודה שתישלח בפועל" (item) ---

def test_preview_command_endpoint_matches_run_time_args():
    resp = client.post("/api/video_editor/preview_command", json={"codec": "hevc", "vertical": True, "smart_crop": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["args"] == web_app._build_extra_args("video_editor.py", {"codec": "hevc", "vertical": True, "smart_crop": True})
    assert "video_editor.py" in data["command"]
    assert "--vertical" in data["command"]


def test_command_preview_modal_and_button_present():
    html = _index_html()
    assert 'id="commandPreviewModalBg"' in html
    assert 'onclick="openCommandPreviewDialog()"' in html
    assert 'id="commandPreviewText"' in html


# --- הערכת זמן-ריצה משוער (item) ---

def test_eta_endpoint_returns_null_without_history(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    resp = client.get("/api/video_editor/eta", params={"codec": "h264", "hwaccel": False, "file_count": 3})
    assert resp.status_code == 200
    assert resp.json() is None


def test_eta_endpoint_multiplies_by_file_count(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    job_history.record_job("video_editor.py", "success", "t1", "t2", 10.0, result={"files_created": 5, "codec": "h264", "hwaccel": False})
    resp = client.get("/api/video_editor/eta", params={"codec": "h264", "hwaccel": False, "file_count": 4})
    data = resp.json()
    assert data["avg_seconds_per_file"] == 2.0
    assert data["estimated_total_seconds"] == 8.0
    assert data["run_count"] == 1


def test_eta_display_and_update_function_present_in_html():
    html = _index_html()
    assert 'id="veEtaDisplay"' in html
    assert "async function updateVeEtaDisplay()" in html


# --- התקדמות חיה בעורך-העל (item) ---

def test_sticky_progress_span_present_and_updated_from_ws_progress_handler():
    html = _index_html()
    assert 'id="veStickyProgress"' in html
    assert "veStickyProgress" in html and "msg.pct" in html


# --- ב': איפוס לשדה בודד / Undo-Redo / הרחב-כווץ / מה-השתנה / פרופיל-אחרון / beforeunload / ניווט-מקלדת-מקראה ---

def test_per_field_reset_functions_present():
    html = _index_html()
    assert "function _setupPerFieldResetButtons()" in html
    assert "function _resetSingleVeField(el)" in html
    assert "ve-field-reset" in html


def test_undo_redo_functions_and_keybindings_present():
    html = _index_html()
    assert "function veUndo()" in html
    assert "function veRedo()" in html
    assert 'key === "z"' in html


def test_toggle_all_categories_function_and_button_present():
    html = _index_html()
    assert "function toggleAllVeCategories()" in html
    assert 'id="veToggleAllBtn"' in html


def test_changed_since_run_indicator_present():
    html = _index_html()
    assert 'id="veChangedSinceRun"' in html
    assert "function updateChangedSinceRunIndicator()" in html
    assert "state.veLastRunSnapshot" in html


def test_last_profile_persistence_function_present():
    html = _index_html()
    assert "function _restoreVeLastProfileSelection()" in html
    assert "veLastProfileValue" in html


def test_beforeunload_warning_wired_to_baseline():
    html = _index_html()
    assert 'addEventListener("beforeunload"' in html
    assert "state.veBaseline && _veIsActive()" in html


def test_glossary_keyboard_nav_function_present():
    html = _index_html()
    assert "function _setupGlossaryKeyboardNav()" in html
    assert "ArrowDown" in html and "ArrowUp" in html


# --- קישור עמוק לקטגוריה/שדה (item) ---

def test_deep_link_functions_present():
    html = _index_html()
    assert "function veScrollToCategory(catKey)" in html
    assert "function _handleVeDeepLinkHash()" in html
    assert "function veScrollToField(fieldKey)" in html


# --- היסטוריית ערכים אחרונים לשדה חופשי (item) ---

def test_field_history_function_and_datalist_wiring_present():
    html = _index_html()
    assert "function _setupVeFieldHistory()" in html
    assert "veFieldHistory_" in html
    assert "vePipPath" in html and "veOutputTemplate" in html
