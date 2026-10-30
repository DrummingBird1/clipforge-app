# tests/web/test_web_app_core.py - REST endpoint tests for web_app.py, topic: core (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from entrypoints.web_app import app
import os
from tests.page_source import served_page_text
from tests.web_app_support import (  # noqa: F401
    _RATE_LIMITED_ENDPOINTS,
    _drain_queue,
    client,
    web_app,
)


def test_request_without_token_is_rejected():
    anonymous_client = TestClient(app)
    resp = anonymous_client.get("/api/scripts")
    assert resp.status_code == 401


def test_health_endpoint_works_without_any_token():
    # item 28: כלי ניטור חיצוני לא יכול להזין טוקן גישה בכלל - /health חייב
    # לעבוד גם לגמרי בלי עוגייה/query param, בניגוד לכל שאר ה-routes.
    anonymous_client = TestClient(app)
    resp = anonymous_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_endpoint_does_not_set_or_require_a_cookie():
    anonymous_client = TestClient(app)
    resp = anonymous_client.get("/health")
    assert resp.status_code == 200
    assert "web_app_token" not in anonymous_client.cookies


def test_the_pwa_manifest_and_its_icons_load_without_a_token():
    """30.10.2026: הדפדפן מבקש את ה-manifest בלי עוגיות - עם 401 אי אפשר היה להתקין את האפליקציה. רק הם פתוחים."""
    anonymous_client = TestClient(app)
    manifest = anonymous_client.get("/manifest.json")
    assert manifest.status_code == 200
    for icon in manifest.json()["icons"]:
        assert anonymous_client.get(icon["src"]).status_code == 200, icon["src"]
    assert anonymous_client.get("/").status_code == 401
    assert anonymous_client.get("/sw.js").status_code == 401


def test_request_with_wrong_token_is_rejected():
    anonymous_client = TestClient(app)
    resp = anonymous_client.get("/api/scripts", params={"token": "wrong-token"})
    assert resp.status_code == 401


def test_request_with_correct_token_query_param_is_accepted_and_sets_cookie():
    anonymous_client = TestClient(app)
    resp = anonymous_client.get("/api/scripts", params={"token": web_app.ACCESS_TOKEN})
    assert resp.status_code == 200
    assert anonymous_client.cookies.get("web_app_token") == web_app.ACCESS_TOKEN
    # הבקשה הבאה לא צריכה יותר את ה-token ב-URL - העוגייה מספיקה
    resp2 = anonymous_client.get("/api/scripts")
    assert resp2.status_code == 200


def test_fresh_token_in_url_overrides_a_stale_cookie():
    # רגרסיה שנמצאה בפועל בבדיקה חיה בדפדפן: עוגייה ישנה/שגויה מריצה קודמת
    # (למשל אחרי שהשרת נוצר מחדש עם טוקן חדש) הייתה "תקועה" לצמיתות - Python's
    # `or` היה בוחר תמיד בעוגייה (truthy, גם אם שגויה) ומעולם לא בודק טוקן טרי
    # שכן הועבר מפורשות ב-URL. query param חייב לגבור על עוגייה קיימת.
    anonymous_client = TestClient(app)
    anonymous_client.cookies.set("web_app_token", "a-stale-token-from-an-old-session")
    resp = anonymous_client.get("/api/scripts", params={"token": web_app.ACCESS_TOKEN})
    assert resp.status_code == 200


def test_rotate_token_invalidates_old_token_and_issues_a_working_new_one(tmp_path, monkeypatch):
    # לא נוגעים בקובץ הטוקן האמיתי של הפרויקט - /api/rotate_token כותב
    # בפועל לדיסק (ראו _persist_token), אז מפנים אותו לקובץ זמני לטסט הזה.
    monkeypatch.setattr(web_app, "TOKEN_PATH", str(tmp_path / "web_app_token.txt"))
    original_token = web_app.ACCESS_TOKEN
    rotating_client = TestClient(app, client=("127.0.0.1", 50000))   # החלפת טוקן - רק מהמחשב עצמו (22.10.2026)
    rotating_client.cookies.set("web_app_token", original_token)
    try:
        resp = rotating_client.post("/api/rotate_token")
        assert resp.status_code == 200
        new_token = resp.json()["token"]
        assert new_token != original_token
        assert web_app.ACCESS_TOKEN == new_token

        # עוגייה/קישור ישנים עם הטוקן הקודם כבר לא תקפים
        stale_client = TestClient(app)
        stale_client.cookies.set("web_app_token", original_token)
        assert stale_client.get("/api/scripts").status_code == 401

        # אבל הטוקן החדש כן עובד, כולל דרך העוגייה המעודכנת שהוגדרה בתגובה
        assert rotating_client.get("/api/scripts").status_code == 200
    finally:
        web_app.ACCESS_TOKEN = original_token


def test_api_rotate_token_records_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "TOKEN_PATH", str(tmp_path / "web_app_token.txt"))
    original_token = web_app.ACCESS_TOKEN
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))
    rotating_client = TestClient(app, client=("127.0.0.1", 50000))   # החלפת טוקן - רק מהמחשב עצמו (22.10.2026)
    rotating_client.cookies.set("web_app_token", original_token)
    try:
        resp = rotating_client.post("/api/rotate_token")
        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0][0] == ("web", "rotate_token")
    finally:
        web_app.ACCESS_TOKEN = original_token


def test_every_sensitive_endpoint_has_the_expected_rate_limit_configured():
    for function_name, expected_limit_str in _RATE_LIMITED_ENDPOINTS.items():
        function = getattr(web_app, function_name)
        endpoint_name = f"{function.__module__}.{function.__name__}"
        assert function.__module__.startswith("entrypoints.web.routes."), endpoint_name
        limits_for_route = web_app.limiter._route_limits.get(endpoint_name)
        assert limits_for_route, f"{endpoint_name} לא רשום ב-_route_limits בכלל - חסר @limiter.limit"
        actual_limit_strs = [str(lim.limit) for lim in limits_for_route]
        assert expected_limit_str in actual_limit_strs, f"{endpoint_name}: ציפינו ל-{expected_limit_str!r}, קיבלנו {actual_limit_strs}"


def test_limits_counting_primitive_actually_blocks_after_the_limit():
    """מוודא שהמנגנון הבסיסי ש-slowapi בנוי עליו (חבילת limits, לא slowapi
    עצמה) חוסם אחרי N פעימות - קריאה ישירה ל-FixedWindowRateLimiter.hit(),
    בלי HTTP/ASGI/TestClient/thread pool בכלל.

    למה לא HTTP: הגרסה הקודמת של הבדיקה הזו שלחה 5 בקשות דרך TestClient נגד
    אפליקציית FastAPI זעירה, ונכשלה ב-CI עם [200,200,200,429,200] - קרי
    הבקשה ה-5 "שכחה" שהמונה כבר עבר את הסף. המקור: MemoryStorage.incr()
    (בחבילת limits) קורא ל-self.get(key) בלי להחזיק את ה-lock של המפתח, ו-FastAPI
    מריץ handler סינכרוני כמו זה דרך thread pool (anyio.to_thread) - שילוב
    שיוצר תנאי מרוץ אמיתי בין thread-ים תחת load, גם בלי שעברה דקה אמיתית.
    קריאה ישירה, סינכרונית, חד-thread-ית ל-hit() באותו process הראשי עוקפת
    את זה לגמרי, ועדיין בודקת קוד אמיתי של limits (לא mock)."""
    from limits import parse
    from limits.storage.memory import MemoryStorage
    from limits.strategies import FixedWindowRateLimiter

    storage = MemoryStorage()
    limiter = FixedWindowRateLimiter(storage)
    item = parse("3/minute")

    results = [limiter.hit(item, "test-key") for _ in range(5)]
    assert results == [True, True, True, False, False], f"תבנית חסימה לא צפויה: {results}"


def test_slowapi_decorator_actually_invokes_the_underlying_storage():
    """מוודא שה-*חיווט* (לא רק האלגוריתם) עובד - ש-@limiter.limit() על route
    אמיתי, דרך ה-ASGI/middleware stack המלא, באמת מפעיל את מנגנון הספירה
    (ולא, למשל, "מדלג" עליו כמו שנצפה בפועל ב-CI ב-DIAGNOSTIC קודם: 0 בקשות
    קיבלו כלל header של X-RateLimit-* למרות limiter.enabled=True). נבדק עם
    בקשה בודדת בלבד (לא סדרה) כדי לא להיות תלוי בשום תזמון בין-בקשות."""
    from fastapi import FastAPI, Request
    from slowapi import Limiter as _Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    tiny_app = FastAPI()
    tiny_limiter = _Limiter(key_func=get_remote_address)
    tiny_app.state.limiter = tiny_limiter
    tiny_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    tiny_app.add_middleware(SlowAPIMiddleware)

    @tiny_app.get("/probe")
    @tiny_limiter.limit("3/minute")
    def probe(request: Request):
        return {"ok": True}

    tiny_client = TestClient(tiny_app)
    resp = tiny_client.get("/probe")
    assert resp.status_code == 200
    assert sum(tiny_limiter._storage.storage.values()) == 1, "הבקשה הבודדת אמורה להירשם פעם אחת בדיוק במנגנון הספירה"


def test_list_drives_returns_at_least_one_real_mountpoint():
    drives = web_app._list_drives()
    assert len(drives) >= 1
    assert all(os.path.isdir(d) for d in drives)


def test_index_page_serves_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "ClipForge" in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_index_page_video_editor_settings_organized_into_collapsible_categories():
    # item: מבנה עורך-העל (סידור מחדש, גל 10): חלונית-צד קבועה (📁 קבצים +
    # 👁 תצוגה מקדימה) ליד אזורי-ההגדרות לפי זרימת-העבודה (גל 34: זמן → צבע → אפקטים →
    # שכבות → שמע וכתוביות → פלט → יצוא → ביצועים), ומגירת ריצות למטה. כל אזור הוא
    # <details class="ve-category..." data-cat> עם כותרת, תקציר, סמן ⚠️ מוסתר,
    # וכפתור איפוס רק לאזורי-הגדרות.
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    category_titles_and_keys = (
        ("📁 קבצים", "queue", '<details class="ve-category ve-side-panel" open data-cat="queue">'),
        ("👁 תצוגה מקדימה", "preview", '<details class="ve-category ve-side-panel" open data-cat="preview">'),
        ("✂️ זמן", "time", '<details class="ve-category" open data-cat="time">'),
        ("🎨 צבע", "look", '<details class="ve-category" open data-cat="look">'),  # גל 28: "מראה" התפצל לצבע ולאפקטים
        ("✨ אפקטים וניקוי", "effects", '<details class="ve-category" open data-cat="effects">'),
        ("🧩 שכבות", "layers", '<details class="ve-category" open data-cat="layers">'),
        ("🔊 שמע וכתוביות", "sound", '<details class="ve-category" open data-cat="sound">'),
        ("📐 פלט וצורה", "output", '<details class="ve-category" open data-cat="output">'),  # גל 34: הפלט אחרי השמע
        ("📦 ייצוא", "export", '<details class="ve-category" open data-cat="export">'),
        ("⚙️ ביצועים", "perf", '<details class="ve-category" data-cat="perf" data-adv>'),
        ("🕘 ריצות", "runs", '<details class="ve-category ve-drawer" data-cat="runs" id="veRunsDrawer">'),
    )
    positions = []
    for title, key, opening in category_titles_and_keys:
        assert opening in html, f"data-cat חסר: {key}"
        assert f'<summary><span class="ve-cat-title">{title}</span><span class="ve-cat-summary" id="veCatSummary-{key}"></span><span class="ve-cat-warn" id="veCatWarn-{key}" hidden>⚠️</span>' in html, f"קטגוריה חסרה: {title}"
        has_reset = f'data-cat-reset="{key}"' in html
        assert has_reset == (key not in ("queue", "preview", "runs")), key
        positions.append(html.index(opening))
    assert positions == sorted(positions), "סדר האזורים חייב להיות לפי זרימת העבודה"
    assert html.count('<details class="ve-category') == len(category_titles_and_keys)
    # שדות ישנים שהוחלפו בבוררים מאוחדים נשארים כשדות מוסתרים (פרופילים/CLI לא משתנים)
    legacy = html[html.index('id="veLegacyFields"'):]
    for field_id in ("veVertical", "veAspect", "veSmartCrop", "veBlurBackground", "veTrimSilence", "veDenoise", "veKeepAudio", "veHwaccel"):
        assert f'id="{field_id}"' in legacy, field_id


def test_index_page_has_update_profile_button():
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="veUpdateProfileBtn"' in resp.text


# --- מרקאפ/JS: שכפול/ייצוא/ייבוא/השוואה/היסטוריה לפרופיל (item) ---

def test_index_page_has_new_profile_management_buttons():
    html = served_page_text(client)
    for button_id in ("veDuplicateProfileBtn", "veHistoryProfileBtn", "veExportProfileBtn", "veProfileMetaInfo"):
        assert f'id="{button_id}"' in html


def test_index_page_has_import_and_compare_controls():
    html = served_page_text(client)
    assert 'id="veImportProfileFile"' in html
    assert "openImportProfileDialog" in html
    assert "openCompareProfilesDialog" in html


def test_index_page_has_profile_history_and_compare_dialogs():
    html = served_page_text(client)
    assert 'id="profileHistoryModalBg"' in html
    assert 'id="profileHistoryList"' in html
    assert 'id="compareProfilesModalBg"' in html
    assert 'id="compareProfileA"' in html and 'id="compareProfileB"' in html


def test_index_page_js_functions_for_new_profile_features_present():
    html = served_page_text(client)
    for fn in (
        "function duplicateVideoEditorProfile",
        "async function exportVideoEditorProfile",
        "async function _handleImportProfileFileChosen",
        "async function openCompareProfilesDialog",
        "async function _runProfileComparison",
        "async function openProfileHistoryDialog",
        "async function _revertProfileVersion",
        "async function _loadAndShowProfileMeta",
    ):
        assert fn in html, f"פונקציה חסרה: {fn}"


def test_run_payload_includes_current_profile_name():
    html = served_page_text(client)
    assert "ve_profile_name: _currentVeProfileName()" in html
    assert "function _currentVeProfileName()" in html


# --- מרקאפ: Fade-in/fade-out, כיתוב טקסט, החלפת פס קול, חיתוך כמה טווחים (item) ---

def test_index_page_has_fade_and_remove_ranges_fields():
    html = served_page_text(client)
    for field_id in ("veFadeInSeconds", "veFadeOutSeconds", "veRemoveRanges"):
        assert f'id="{field_id}"' in html


def test_index_page_has_text_overlay_fields():
    html = served_page_text(client)
    for field_id in ("veText", "veTextPosition", "veTextFont", "veTextFontSize", "veTextColor"):
        assert f'id="{field_id}"' in html


def test_index_page_has_replace_audio_field():
    html = served_page_text(client)
    assert 'id="veReplaceAudioPath"' in html


def test_collect_run_options_sends_new_fields_for_video_editor():
    html = served_page_text(client)
    for js_field in (
        "fade_in_seconds: _veTimeValue(\"veFadeInSeconds\"", "fade_out_seconds: _veTimeValue(\"veFadeOutSeconds\"", "remove_ranges: document.getElementById",
        "replace_audio_path: document.getElementById", "text: document.getElementById",
        "text_position: document.getElementById", "text_font: document.getElementById",
        "text_font_size: parseInt", "text_color: document.getElementById",
    ):
        assert js_field in html, f"חסר ב-_collectRunOptions: {js_field}"


def test_apply_video_editor_fields_restores_new_fields_from_profile():
    html = served_page_text(client)
    for js_line in (
        'document.getElementById("veFadeInSeconds").value = fields.fade_in_seconds',
        'document.getElementById("veFadeOutSeconds").value = fields.fade_out_seconds',
        'document.getElementById("veRemoveRanges").value = fields.remove_ranges',
        'document.getElementById("veReplaceAudioPath").value = fields.replace_audio_path',
        'document.getElementById("veText").value = fields.text',
        'document.getElementById("veTextPosition").value = fields.text_position',
    ):
        assert js_line in html, f"חסר ב-_applyVideoEditorFields: {js_line}"


def test_ve_favorite_fields_and_dependency_map_include_text_group():
    html = served_page_text(client)
    assert 'text_position: {id: "veTextPosition"' in html
    assert 'text_position: "veText"' in html  # VE_FAVORITE_DEPENDS_ON
    assert 'text_font: "veText"' in html
    assert 'text_color: "veText"' in html


def test_manifest_json_is_valid_pwa_manifest():
    resp = client.get("/manifest.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "ClipForge - Web"
    assert data["display"] == "standalone"
    assert len(data["icons"]) >= 1


def test_manifest_json_icons_are_real_png_files_not_placeholder_svg():
    # item: התקנת PWA - שדרוג מ-SVG-אימוג'י זמני לאייקוני מותג אמיתיים.
    data = client.get("/manifest.json").json()
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert {"192x192", "512x512"}.issubset(sizes)
    assert all(icon["type"] == "image/png" for icon in data["icons"])


def test_app_icon_192_is_served_as_real_png():
    resp = client.get("/assets/app_icon_192.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_app_icon_512_is_served_as_real_png():
    resp = client.get("/assets/app_icon.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_service_worker_is_served_as_javascript():
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers["content-type"]
    assert "addEventListener" in resp.text


def test_ws_replays_buffered_log_lines_to_a_new_connection():
    # רגרסיה: חיבור WebSocket שמתנתק ומתחבר מחדש (רשת לא יציבה, טאב נרדם) לא
    # אמור לפספס לצמיתות שורות לוג שהתרחשו בזמן שהיה מנותק. נשלח כהודעת
    # "log_batch" אחת (item: log spam) - לא הודעה נפרדת לכל שורה.
    web_app._LOG_REPLAY_BUFFER.clear()
    web_app._LOG_REPLAY_BUFFER.append(("hello from before", None))
    web_app._LOG_REPLAY_BUFFER.append(("second line", "red"))

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
    assert msg == {
        "type": "log_batch",
        "lines": [
            {"line": "hello from before", "tag": None},
            {"line": "second line", "tag": "red"},
        ],
    }
    web_app._LOG_REPLAY_BUFFER.clear()


def test_ws_caps_lines_per_batch_and_drains_the_rest_in_a_later_message():
    # item: log spam - סקריפט שמדפיס פרץ ענק של שורות אמיתיות בין iteration
    # ל-iteration (למשל אלפי "[SKIP] קובץ קיים כבר" ברצף מהיר) לא אמור לגרום
    # ל-/ws לשלוח הודעת WebSocket ענקית אחת (או מאות/אלפי הודעות נפרדות) -
    # התור מתנקז בקבוצות של עד _LOG_BATCH_SIZE, השאר ממתין וממשיך להתנקז
    # ב-iterations הבאים של אותה לולאה.
    web_app._LOG_REPLAY_BUFFER.clear()
    _drain_queue(web_app.worker.log_queue)
    _drain_queue(web_app.worker.progress_queue)
    total_lines = web_app._LOG_BATCH_SIZE + 5
    for i in range(total_lines):
        web_app.worker.log_queue.put((f"line {i}\n", None))

    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        second = ws.receive_json()

    assert first["type"] == "log_batch"
    assert len(first["lines"]) == web_app._LOG_BATCH_SIZE
    assert second["type"] == "log_batch"
    assert len(second["lines"]) == 5
    assert first["lines"][0]["line"] == "line 0\n"
    assert second["lines"][-1]["line"] == f"line {total_lines - 1}\n"
    web_app._LOG_REPLAY_BUFFER.clear()


def test_ws_sends_formatted_eta_alongside_percentage():
    # worker.progress_queue עבר מ-int גולמי ל-dict {"pct", "eta_seconds"}
    # (utils/shared/worker.py) כדי שגם הבר בדפדפן יציג הערכת-זמן-שנותר, לא רק אחוז -
    # מוודא שה-/ws endpoint מפרמט את זה (utils.shared.health_status.format_duration)
    # לפני שליחה, לא שולח eta_seconds גולמי בשניות.
    web_app._LOG_REPLAY_BUFFER.clear()
    _drain_queue(web_app.worker.log_queue)
    _drain_queue(web_app.worker.progress_queue)
    web_app.worker.progress_queue.put({"pct": 42, "eta_seconds": 125})

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()

    assert msg == {"type": "progress", "pct": 42, "eta": "2ד", "files": {}}  # files: התקדמות פר-קובץ (גל 4)


def test_ws_sends_none_eta_when_not_available(monkeypatch):
    monkeypatch.setitem(web_app._current_run, "script_name", None)  # a leaked run from an earlier test would make the ETA fall back to job_history
    monkeypatch.setitem(web_app._current_run, "started_at", None)
    web_app._LOG_REPLAY_BUFFER.clear()
    _drain_queue(web_app.worker.log_queue)
    _drain_queue(web_app.worker.progress_queue)
    web_app.worker.progress_queue.put({"pct": 10, "eta_seconds": None})

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()

    assert msg == {"type": "progress", "pct": 10, "eta": None, "files": {}}


def test_ws_fills_a_missing_eta_from_progress_and_job_history(monkeypatch):
    # סקריפט שמדווח רק PROGRESS:N (בלי ETA משלו) מקבל ETA מההתקדמות ומההיסטוריה (job_history)
    import time as _time
    web_app._LOG_REPLAY_BUFFER.clear()
    _drain_queue(web_app.worker.log_queue)
    _drain_queue(web_app.worker.progress_queue)
    monkeypatch.setattr(web_app.job_history, "get_typical_duration", lambda name: 100.0)
    monkeypatch.setitem(web_app._current_run, "script_name", "dataviz_maker.py")
    monkeypatch.setitem(web_app._current_run, "started_at", _time.time() - 30)
    web_app.worker.progress_queue.put({"pct": 50, "eta_seconds": None})

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()

    from utils.shared.health_status import format_duration
    assert msg["pct"] == 50 and msg["eta"] == format_duration(30)      # 30 שניות עברו על 50% -> עוד ~30


def test_ws_single_file_run_shows_the_file_progress_with_its_own_eta(monkeypatch):
    # סבב ייצוב: בריצה של קובץ אחד הכולל ("0/1") היה 0% עד הסוף בזמן שהקובץ ב-77% והזמן שנותר רץ - הסטודיו עצר ריצה טובה
    monkeypatch.setitem(web_app._current_run, "script_name", None)
    monkeypatch.setitem(web_app._current_run, "started_at", None)
    web_app._LOG_REPLAY_BUFFER.clear()
    _drain_queue(web_app.worker.log_queue)
    _drain_queue(web_app.worker.progress_queue)
    for item in ({"pct": 0, "eta_seconds": None}, {"pct": 0, "eta_seconds": None, "done": 0, "total": 1},
                 {"pct": 77, "eta_seconds": 40, "label": "clip.mp4"}):
        web_app.worker.progress_queue.put(item)

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()

    from utils.shared.health_status import format_duration
    assert msg == {"type": "progress", "pct": 77, "eta": format_duration(40), "files": {"clip.mp4": 77}}


def test_main_progress_bar_and_eta_come_from_the_same_source():
    from entrypoints.web.routes.runs import _main_progress, _new_progress_state

    def run(*rounds):
        state = _new_progress_state()
        return [_main_progress(state, list(items)) for items in rounds]
    total3 = {"pct": 0, "eta_seconds": None, "done": 0, "total": 3}
    # שלושה קבצים ברצף: הפס עולה בהדרגה ולא חוזר אחורה, גם כשקובץ הגיע ל-100% לפני שהכולל עודכן;
    # הזמן שנותר לא נלקח מהקובץ (None = הערכה מהאחוז) - הוא לא זמן הריצה
    assert run([total3, {"pct": 50, "eta_seconds": 9, "label": "a"}],
               [{"pct": 100, "eta_seconds": 0, "label": "a"}],
               [{"pct": 33, "eta_seconds": None, "done": 1, "total": 3}],
               [{"pct": 0, "eta_seconds": 30, "label": "b"}],
               [{"pct": 50, "eta_seconds": 15, "label": "b"}]) == [(16, None), (33, None), (33, None), (33, None), (50, None)]
    # קובץ שבוטל לפני שהתחיל (אין לו פס) נספר כשהכולל מתעדכן
    assert run([total3], [{"pct": 66, "eta_seconds": None, "done": 2, "total": 3}])[-1] == (66, None)
    # בלי k/N - כמו קודם, אבל הזמן שנותר רק מאותו מקור כמו האחוז
    assert run([{"pct": 42, "eta_seconds": 125}]) == [(42, 125)]
    assert run([{"pct": 20, "eta_seconds": None}], [{"pct": 60, "eta_seconds": 5, "label": "a"}])[-1] == (20, None)
    assert run([{"pct": 60, "eta_seconds": 5, "label": "a"}]) == [(60, 5)]


def test_ws_rejects_connection_without_valid_token():
    anonymous_client = TestClient(app)
    try:
        with anonymous_client.websocket_connect("/ws"):
            pass
        assert False, "expected the connection to be rejected"
    except Exception:
        pass  # WebSocketDisconnect (או שקילה) צפוי - החיבור נדחה לפני accept()


def test_generate_and_record_thumbnail_candidates_records_generated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "THUMBNAIL_CANDIDATES_DIR", str(tmp_path / ".thumbnail_candidates"))
    monkeypatch.setattr(web_app.youtube_thumbnail_log, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(web_app, "generate_candidates", lambda video_path, out_dir, ffmpeg, ffprobe: ["/a.jpg", "/b.jpg"])

    web_app._generate_and_record_thumbnail_candidates("vid1", "/fake/clip.mp4")

    assert web_app.youtube_thumbnail_log.get_candidates("vid1") == [(0, "/a.jpg"), (1, "/b.jpg")]


def test_generate_and_record_thumbnail_candidates_never_raises_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "generate_candidates", MagicMock(side_effect=RuntimeError("ffmpeg exploded")))

    web_app._generate_and_record_thumbnail_candidates("vid1", "/fake/clip.mp4")  # לא אמור לזרוק
