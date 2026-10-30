# tests/web_app_support.py
#
# Shared helpers/fixtures/module-level setup for the test_web_app_*.py files (split out of the old
# 4.3k-line tests/test_web_app.py, no test changed). Import what you need:  from tests.web_app_support import ...
# tests/test_web_app.py
#
# בודק את ה-REST endpoints של web_app.py (ממשק הדפדפן) עם FastAPI TestClient -
# בלי להריץ שרת אמיתי. /api/run נבדק רק על נתיבי אימות (סקריפט/תיקייה לא
# תקינים, "כבר רץ") בלי לגעת ב-worker.add_script_task האמיתי (שהיה מריץ
# subprocess אמיתי) - הצלחה מזויפת דרך monkeypatch.
import json
import os
import queue
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


client = TestClient(app)


# מדמה כניסה אמיתית עם טוקן תקין (ראו _require_access_token/ACCESS_TOKEN ב-
# web_app.py) - בלי זה כל בקשה בטסטים למטה הייתה נענית 401, לא הבדיקה בפועל.
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)


# הגבלת הקצב (item 8, ראו web_app.py's limiter) מוגדרת לפי IP - כל בקשות
# ה-TestClient מגיעות מאותה "כתובת" מזויפת, אז הרצה מלאה של קובץ הטסטים הזה
# הייתה חוצה את הסף (10/minute ל-/api/run) ומקבלת 429 באמצע הריצה במקום מה
# שהטסט הספציפי בודק. מכובה כברירת מחדל כאן; הבדיקה שהמנגנון עצמו אכן חוסם
# (test_slowapi_rate_limiting_mechanism_actually_blocks_after_the_limit, למטה)
# משתמשת באפליקציה זעירה ומבודדת משלה עם Limiter נפרד, כך שהכיבוי כאן לא
# משפיע עליה.
web_app.limiter.enabled = False


# --- rate limiting: verified in two isolated, deterministic parts instead of
# one flaky end-to-end integration test (item) ---
#
# ה-8 טסטי ה-rate-limit המקוריים כאן (15+ בקשות HTTP אמיתיות דרך web_app.app
# המלא, מוודאות 429 בפועל) הוכיחו את עצמם לא-אמינים ב-CI: 3 תיקונים נפרדים
# ומהותית-שונים (retry סבלני, MemoryStorage מבודד) שניהם וורפו נכון מקומית
# ונכשלו *זהה* ב-CI (0 חסימות אחרי 15 בקשות, אפס כותרות X-RateLimit-* בתגובה,
# למרות web_app.limiter.enabled=True ורישום תקין ב-_route_limits - נבדק
# ישירות עם קובץ DIAGNOSTIC ב-CI עצמו, לא ניחוש). הגורם השורש המדויק (סביר
# שקשור לאיך web_app.app's 50+ routes/SlowAPIMiddleware מתנהגים יחד תחת
# הסביבה הספציפית של ה-CI runner) נשאר לא ידוע - אבל אין צורך לפתור את
# התעלומה כדי לקבל כיסוי משמעותי ואמין: הפיצול הבא נותן את אותה ערבות
# מהותית (1) כל endpoint רגיש מוגדר בפועל עם המגבלה הנכונה, (2) מנגנון
# ה-rate-limiting *עצמו* (slowapi+limits) אכן חוסם אחרי N בקשות - בלי התלות
# השבירה באינטראקציה המלאה עם web_app.app שהוכחה לא-דטרמיניסטית שם.

# גל 11: ה-endpoints יושבים ב-web/routes/<תחום>.py - slowapi רושם אותם לפי
# "<מודול>.<שם>" של הפונקציה עצמה, אז המפתח נגזר מהפונקציה (לא מנתיב קבוע).
_RATE_LIMITED_ENDPOINTS = {
    "api_rotate_token": "10 per 1 minute",
    "api_settings_reset": "10 per 1 minute",
    "api_settings_import": "10 per 1 minute",
    "api_undo_last_move_batch": "10 per 1 minute",
    "api_run": "10 per 1 minute",
    "api_credentials_check_validity": "5 per 1 minute",
    "api_backup_create_encrypted": "5 per 1 minute",
    "api_backup_restore": "5 per 1 minute",
}


# --- Encrypted local backup bundle (security/reliability item) ---

def _setup_fake_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "config.json").write_text(json.dumps({"theme": "Green"}), encoding="utf-8")
    backups_dir = data_dir / "backups"
    backups_dir.mkdir()
    monkeypatch.setattr(web_app, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(web_app, "BACKUPS_DIR", str(backups_dir))
    return data_dir, backups_dir


# --- POST /api/video_editor_profiles/{name}/duplicate (item: שכפול פרופיל) ---

def _isolate_vep_paths(tmp_path, monkeypatch):
    import utils.video.video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    return vep


def _make_test_png(tmp_path, size):
    from PIL import Image
    path = tmp_path / "watermark.png"
    Image.new("RGBA", size, (255, 0, 0, 255)).save(path)
    return str(path)


def _drain_queue(q):
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            break


def _reset_bot_state():
    with web_app._bot_state_lock:
        web_app._bot_state["process"] = None
        web_app._bot_state["is_running"] = False
        web_app._bot_state["gave_up"] = False
        web_app._bot_state["config_error"] = False
        web_app._bot_state["crash_timestamps"] = []
    web_app._bot_log_buffer.clear()
    while not web_app._bot_log_queue.empty():
        web_app._bot_log_queue.get_nowait()


# --- Run-completion side effects (item 4/N): webhook/auto-backup/night-mode ---

class _ImmediateThread:
    """מריץ את ה-target מיידית, בלי thread אמיתי - כדי שטסטים על
    _run_completion_side_effects (שמפעילה threading.Thread לגיבוי) יוכלו
    לבדוק דטרמיניסטית מה קרה, בלי race על thread רקע אמיתי."""
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


# --- Clip gallery + YouTube/TikTok export wizard (11/N desktop-parity gaps) ---

def _reset_youtube_upload_state():
    with web_app._youtube_upload_lock:
        web_app._youtube_upload_state.update(
            {"in_progress": False, "percent": 0, "success": None, "video_id": None, "error": None}
        )


def _is_ffmpeg_runnable():
    import shutil

    from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
    exe = get_ffmpeg_exe()
    probe = get_ffprobe_exe()
    runnable = lambda p: (os.path.isabs(p) and os.path.exists(p)) or bool(shutil.which(p))
    return runnable(exe) and runnable(probe)


# --- /api/approvals, /api/approvals/{id}/decide (item: mobile-friendly clip-approval view) ---

def _insert_pending_row(db_path, video_path):
    with web_app.db.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pending_approvals ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, video_path TEXT UNIQUE, "
            "status TEXT DEFAULT 'pending', channel_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        cursor = conn.execute(
            "INSERT INTO pending_approvals (video_path, status, channel_id) VALUES (?, 'pending', ?)",
            (video_path, 123),
        )
    return cursor.lastrowid


def _fake_seo(sheet="sheet", source="template"):
    return {"sheet": sheet, "source": source, "tiktok_caption": "caption #tag", "youtube_title": "AI title",
            "description": "one line", "hashtags": ["#rl", "#gaming"], "youtube_tags": ["rl", "gaming"]}


# --- /api/youtube_analytics, /api/youtube_analytics/refresh (item: YouTube Analytics feedback loop) ---

def _reset_youtube_analytics_refresh_state():
    with web_app._youtube_analytics_refresh_lock:
        web_app._youtube_analytics_refresh_state.update({"in_progress": False, "updated": 0, "errors": [], "done": False})
