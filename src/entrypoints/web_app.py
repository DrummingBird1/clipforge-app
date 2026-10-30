# web_app.py
#
# ממשק דפדפן מקומי - מריץ בפועל את אותם סקריפטי אוטומציה (דרך אותו
# utils/shared/worker.py, בדיוק כמו gui_manager.pyw) אבל מתוך טאב דפדפן במקום חלון
# Windows נפרד. הכל (רינדור ffmpeg, גישה לדיסק) עדיין קורה מקומית על אותו
# מחשב - השרת הזה עצמו מאזין רק ל-127.0.0.1 (לא נגיש מבחוץ), בדיוק כמו
# web_dashboard.py הקיים.
#
# עמוד HTML יחיד עם JS רגיל (בלי build step/React/npm) - כולל טאבים לניהול
# הבוט ועוד, לא רק הזרימה המרכזית של הרצת סקריפט (בחר סקריפט, בחר תיקייה,
# הרץ, צפה בלוג חי). הורחב הדרגתית ממקור פשוט יותר; עדיין בלי תלות ב-Tkinter.
#
# תיאום עם ה-GUI/הבוט: worker.add_script_task משתמש כבר ב-utils/shared/render_lock.py
# (מנעול חוצה-תהליכים) עבור סקריפטים "כבדים" - כך שהרצה מכאן לא תתנגש על ה-GPU
# עם רינדור שרץ במקביל מה-GUI השולחני או מהבוט.
#
# הרצה: python web_app.py (או uv run python web_app.py), ואז פתיחת
# http://127.0.0.1:8878 בדפדפן.
#
# הערת scope: תומך במשתמש אחד/טאב אחד בו-זמנית (בדיוק כמו חלון ה-GUI היחיד) -
# פתיחת כמה טאבים בו-זמנית תתחרה על אותה תור לוג (queue.Queue נשלף unicast,
# לא broadcast), לא תקרוס אבל רק אחד יראה כל שורה.

import ast
import collections
import glob
import gzip
import tempfile
import json
import os
import queue
import re  # noqa: F401
import secrets
import shutil
import string
import subprocess
import sys
import threading
import time
import webbrowser  # noqa: F401 - טסטים מחליפים את web_app.webbrowser.open (אותו מודול ש-web/server_startup.py קורא לו)
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# src/entrypoints/ תחת שורש הפרויקט - כל קוד המקור הראשוני (utils/וכו') יושב
# תחת src/, לא בשורש עצמו, אז זה מה שצריך להיות ב-sys.path כדי ש-"utils.*"
# למטה ייובא בהצלחה - לא BASE_DIR (שורש הפרויקט) עצמו.
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.data_dir import DATA_DIR  # data/ האמיתית, או תיקייה זמנית בטסטים (CLIPFORGE_DATA_DIR)
from utils.shared import data_paths  # שמות הקבצים ב-data/ (23.10.2026)

SCRIPTS_DIR = os.path.join(BASE_DIR, "my_scripts")
TOKEN_PATH = data_paths.path(data_paths.WEB_TOKEN)
BACKUPS_DIR = data_paths.path(data_paths.BACKUPS)
TLS_CERT_PATH = data_paths.path(data_paths.TLS_CERT)
TLS_KEY_PATH = data_paths.path(data_paths.TLS_KEY)
APP_ICON_PNG = os.path.join(BASE_DIR, "assets", "app_icon.png")
APP_ICON_192_PNG = os.path.join(BASE_DIR, "assets", "app_icon_192.png")
MAIN_PY_PATH = os.path.join(BASE_DIR, "src", "entrypoints", "main.py")
BOT_DB_PATH = data_paths.path(data_paths.BOT_DB)

# ראו ui/bot_tab.py - אותם ערכים בדיוק (כמה קריסות בלתי-צפויות ב-5 הדקות
# האחרונות מותר לספוג לפני שמפסיקים לנסות להפעיל מחדש אוטומטית).
BOT_MAX_AUTO_RESTARTS = 5
BOT_AUTO_RESTART_WINDOW_SECONDS = 300


def _read_bot_config_error_exit_code():
    """CONFIG_ERROR_EXIT_CODE של main.py (אין טוקן / Discord דחה אותו / חסר Intent) - נקרא מהקוד שלו (ast) ולא
    בייבוא: הייבוא של main.py עוטף את stdout ובודק טוקן. None אם השם נעלם - אז כל יציאה היא קריסה, כמו קודם."""
    try:
        with open(MAIN_PY_PATH, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONFIG_ERROR_EXIT_CODE" for t in node.targets):
            return ast.literal_eval(node.value)
    return None


BOT_CONFIG_ERROR_EXIT_CODE = _read_bot_config_error_exit_code()

# ראו ui/rocket_settings_tab.py - אותם נתיבים/פרופילים בדיוק, כדי ש-
# rocket_shorts_publisher.py (שקורא את אותם קבצים) יתנהג זהה בין דסקטופ לווב.
ROCKET_SETTINGS_PATH = data_paths.path(data_paths.ROCKET_SETTINGS)
ROCKET_COUNTER_PATH = data_paths.path(data_paths.ROCKET_COUNTER)
ROCKET_QUALITY_PRESETS = {
    "🚀 Max Quality (HEVC NVENC, P7)": {"encoder": "hevc_nvenc", "ffmpeg_preset": "p7", "quality_cq": 17},
    "📱 Balanced (HEVC NVENC, P5)": {"encoder": "hevc_nvenc", "ffmpeg_preset": "p5", "quality_cq": 19},
    "⚡ Fast Render (HEVC NVENC, P1)": {"encoder": "hevc_nvenc", "ffmpeg_preset": "p1", "quality_cq": 23},
    "🧪 AV1 Next-Gen (NVENC, P5)": {"encoder": "av1_nvenc", "ffmpeg_preset": "p5", "quality_cq": 24},
    "💻 CPU Fallback (H.264, Medium)": {"encoder": "libx264", "ffmpeg_preset": "medium", "quality_cq": 22},
}
ROCKET_RECAP_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

from utils.shared import workspace_dir as _workspace_layout  # noqa: E402 - קבועי מבנה התוצרים
from utils.shared import export_dir  # noqa: E402,F401 - תיקיית הייצוא שבחר המשתמש (23.10.2026); ה-routers ו-web/run_lifecycle.py ניגשים דרך W.<שם>
from utils.shared import notification_log  # noqa: E402,F401 - מרכז ההתראות (23.10.2026); ה-routers ו-web/run_lifecycle.py ניגשים דרך W.<שם>
# CLIPFORGE_WORKSPACE_DIR: תיקיית פלט חלופית (בדיקות והרצות ניסיון בלי לגעת ב-workspace/ האמיתית); dataviz_maker.py קורא אותה גם הוא
WORKSPACE_DIR = os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(BASE_DIR, "workspace")
# סבב ייצוב: כל תיקייה של השרת תחת ה-workspace נגזרת ממנו. קודם עשר מהן היו קבועות ל-<שורש>/workspace, ושרת עם
# CLIPFORGE_WORKSPACE_DIR אחר עדיין כתב חלק מהקבצים ל-workspace הראשי. use_workspace_dir מחליף את כולן יחד.
# מטמונים (נוצרים מחדש לבד) - תחת workspace/.cache/ ולא כתיקיות נקודה פזורות בשורש ה-workspace (19.10.2026). התיקיות
# הישנות (workspace/.previews וכו') כבר לא נקראות; הן נשארות במקומן עד שהמשתמש מחליט.
WORKSPACE_CACHE_DIRNAME = ".cache"
WORKSPACE_SUBDIRS = {
    "CLIPS_DIR": "clips", "THUMBNAIL_CACHE_DIR": os.path.join(WORKSPACE_CACHE_DIRNAME, "thumbnail_cache"), "TAGS_CACHE_DIR": ".tags_cache",
    "THUMBNAIL_CANDIDATES_DIR": os.path.join(WORKSPACE_CACHE_DIRNAME, "thumbnail_candidates"), "BATCH_OVERRIDES_DIR": ".batch_overrides",
    "CAPTIONS_EDITS_DIR": ".captions_edits", "LAYERS_DIR": os.path.join(WORKSPACE_CACHE_DIRNAME, "layers"),
    "PREVIEWS_DIR": os.path.join(WORKSPACE_CACHE_DIRNAME, "previews"),
    "RUN_MANIFESTS_DIR": os.path.join(WORKSPACE_CACHE_DIRNAME, "run_manifests"),
    "RUN_CONTROL_DIR": os.path.join(WORKSPACE_CACHE_DIRNAME, "run_control"), "PUBLISH_BATCHES_DIR": ".publish_batches",
}
# תיקיות התוצרים לגיבוי: לפי כלי (19.10.2026 - studio/, timelapses/, dataviz/, rocket_shorts/...), ותיקיות הכיוון הישנות
# כל עוד הן קיימות (לפני סקריפט ההעברה). כל אחת מגובה ל-<יעד>/<שמה>; תיקייה שלא קיימת מדולגת.
WORKSPACE_EXPORT_NAMES = _workspace_layout.TOOLS + _workspace_layout.ORIENTATIONS


def use_workspace_dir(path):
    """מפנה בזמן ריצה את ה-workspace ואת כל התיקיות שתחתיו (שרת בדיקה) - קריאה אחת במקום להפנות קבוע-קבוע.
    הסקריפטים שהשרת מריץ קוראים את CLIPFORGE_WORKSPACE_DIR - את זה מגדיר מי שקורא (למשל monkeypatch.setenv)."""
    global WORKSPACE_DIR, WEB_APP_EXPORT_DIRS
    WORKSPACE_DIR = path
    for name, sub in WORKSPACE_SUBDIRS.items():
        globals()[name] = os.path.join(path, sub)
    WEB_APP_EXPORT_DIRS = [os.path.join(path, name) for name in WORKSPACE_EXPORT_NAMES]
    # וגם המקור המשותף (utils/workspace_dir) ותיקיות אישור הקליפים שנגזרות ממנו בייבוא
    from utils.bot import approval_store as _approval_store
    from utils.shared import workspace_dir as _workspace_dir
    _workspace_dir.WORKSPACE_DIR = path
    _approval_store.use_workspace_dir(path)


# ראו ui/stats_tab.py - אותה תיקייה וקישורי יעד בדיוק, כדי שגלריית הקליפים כאן
# והוויזארד שלה יתנהגו זהה בין דסקטופ לווב.
CLIPS_DIR = os.path.join(WORKSPACE_DIR, "clips")
# .cache/thumbnail_cache/ - נפרד מ-CLIPS_DIR עצמו (לא thumbnails ליד כל קליפ) כדי
# שקבצי מטמון לא יתערבבו עם קבצי מדיה אמיתיים בגלריה (item: gallery thumbnails).
THUMBNAIL_CACHE_DIR = os.path.join(WORKSPACE_DIR, WORKSPACE_SUBDIRS["THUMBNAIL_CACHE_DIR"])
# תגיות תוכן שנוצרו על-פי-בקשה (item: content-based auto-tagging) - נפרד
# מ-THUMBNAIL_CACHE_DIR כי אלה שני קבצי מטמון בפורמטים שונים לגמרי (JSON מול JPEG).
TAGS_CACHE_DIR = os.path.join(WORKSPACE_DIR, ".tags_cache")
# item: A/B thumbnail testing - keyed by video_id (not filename+mtime like the
# caches above), כדי שהמועמדות יישארו זמינות גם אם קובץ הקליפ המקורי כבר הוזז/נמחק.
THUMBNAIL_CANDIDATES_DIR = os.path.join(WORKSPACE_DIR, WORKSPACE_SUBDIRS["THUMBNAIL_CANDIDATES_DIR"])
TIKTOK_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
YOUTUBE_UPLOAD_FALLBACK_URL = "https://youtube.com/upload"

_youtube_upload_state = {"in_progress": False, "percent": 0, "success": None, "video_id": None, "error": None}
_youtube_upload_lock = threading.Lock()

# item: YouTube Analytics feedback loop - רץ ב-thread רקע (לא חוסם את
# event loop של FastAPI) בדיוק כמו העלאת YouTube למעלה, מאותה סיבה: הפעם
# הראשונה שנדרש scope חדש (youtube.readonly) פותחת דפדפן אמיתי להסכמה על
# המחשב שמריץ את השרת (utils/youtube_uploader._get_credentials) - זו יכולה
# לקחת זמן בלתי-חסום עד שהמשתמש בפועל מאשר, ואסור שתחסום את הבקשה עצמה.
_youtube_analytics_refresh_state = {"in_progress": False, "updated": 0, "errors": [], "done": False}
_youtube_analytics_refresh_lock = threading.Lock()

# ראו ui/dashboard.py's _record_and_notify/_run_backup_mirror/_start_shutdown_countdown -
# אותה התנהגות בדיוק בסיום ריצה מוצלחת (webhook/גיבוי/כיבוי לילה), רק שכאן
# הריצה הופעלה מהדפדפן. שלוש תיקיות (לא אחת) כי תוצרי הרינדור פזורים עכשיו
# אותם נתיבי יצוא משותפים לכל surface (ראו WORKSPACE_EXPORT_NAMES)
WEB_APP_EXPORT_DIRS = [os.path.join(WORKSPACE_DIR, name) for name in WORKSPACE_EXPORT_NAMES]
SHUTDOWN_COUNTDOWN_SECONDS = 60

# ראו ui/soundboard_tab.py - אותם צלילים בדיוק (winsound.Beep מנגן דרך
# הרמקולים של המחשב שמריץ את השרת, לא דרך הדפדפן - נכון גם כשגולשים
# מטלפון במצב --lan, זה בדיוק הרצוי לפאנל אפקטים לסטרימינג).
SOUNDBOARD_SOUNDS = {"airhorn": (880, 400), "boom": (150, 600), "game_over": (293, 500)}

from utils.shared.logging_setup import setup_persistent_logging
setup_persistent_logging("web_app")

if __name__ == "__main__":
    # ה-routers (web/routes/) מייבאים את המודול הזה בשם entrypoints.web_app - בהרצה
    # ישירה הוא __main__, אז השם מופנה אליו עצמו ולא נטען עותק שני עם מצב נפרד.
    sys.modules.setdefault("entrypoints.web_app", sys.modules[__name__])
from entrypoints.web.frontend_assembly import assemble_page, build_assets
from utils.shared import db  # noqa: F401 - web/config_files.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.shared.backup_sync import mirror_folder  # noqa: F401 - web/run_lifecycle.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.shared.crash_supervisor import record_crash_and_check_giveup  # noqa: F401 - web/bot_process.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.bot import approval_store  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.media.clip_tagger import generate_clip_tags, tags_cache_path as _clip_tags_cache_path  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.credential_health import check_validity as check_credential_validity, get_rotation_status  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.secrets_vault import is_vault_available, set_secret as set_vault_secret  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.media.nvenc_probe import probe_max_concurrent_nvenc_sessions  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.media import game_playtime  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.hardware import get_system_stats, get_gpu_stats  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared import hardware_history  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.video import editor_runs
from utils.video import run_control
from utils.video import video_editor_profiles
from utils.media import auto_chain
from utils.video import brand_kits, editor_model
from utils.shared.notifications import send_webhook_notification  # noqa: F401 - web/run_lifecycle.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.shared.python_locator import get_python_executable
from utils.shared.render_lock import get_status as get_render_lock_status  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.atomic_write import atomic_write_json  # noqa: F401 - web/config_files.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.bot import scheduler_store  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.script_metadata import get_script_metadata
from utils.shared.diagnostics import run_diagnostics  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.bot.seo_generator import generate_seo_metadata, generate_seo_with_sheet  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.sound import play_board_sound  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.media.thumbnail_generator import extract_frame_at_timestamp, get_video_duration_via_ffprobe  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.update_checker import apply_update, check_for_update, is_portable, PORTABLE_UPDATE_REFUSAL, RELEASES_PAGE_URL  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.version import APP_VERSION  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.media.thumbnail_candidates import generate_candidates
from utils.bot import youtube_analytics  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.bot import youtube_publish_log  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.bot import youtube_thumbnail_log
from utils.bot import youtube_uploader  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.shared.state import CONFIG_FILE, CONFIG_SCHEMA, DEFAULT_UI_SETTINGS  # noqa: F401 - web/config_files.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared.tls_cert import ensure_self_signed_cert
from utils.shared import device_pairing
from utils.shared.worker import worker
from utils.bot import audit_log
from utils.shared import job_history  # noqa: F401 - ה-routers ו-web/run_lifecycle.py קורא W.<שם>, וטסטים מחליפים את web_app.<שם>
from utils.video.video_editor import (
    EFFORT_LEVELS,  # noqa: F401
    SUPPORTED_CONTAINERS,  # noqa: F401
    WATERMARK_POSITIONS,  # noqa: F401
    parse_fps_value,  # noqa: F401
    parse_region_fractions,  # noqa: F401
    parse_time_seconds,  # noqa: F401
    sanitize_batch_overrides,
    validate_output_template,  # noqa: F401
)
from utils.video.video_editor_counter import save_number as save_video_editor_counter  # noqa: F401 - ה-routers ניגשים דרך W.<שם> (וטסטים עושים לו monkeypatch כאן)
from utils.video.video_editor_profiles import backup_profiles_now as backup_video_editor_profiles_now


def _generate_token():
    return secrets.token_urlsafe(24)


def _persist_token(token):
    """שומר טוקן גישה לקובץ מקומי (data/web_app_token.txt, ב-.gitignore) -
    כדי ש-WebLauncher.vbs/_web_launcher_impl.bat יוכלו לקרוא את הטוקן
    הנוכחי ולפתוח את הדפדפן ישירות אליו, בלי טרמינל. נקרא רק כשהשרת באמת
    רץ (__main__ למטה) או ברוטציה בפועל (/api/rotate_token) - בכוונה *לא*
    בעצם ה-import של המודול הזה, כדי שייבוא web_app.py (למשל ע"י קובצי
    טסטים) לא ידרוס בטעות את קובץ הטוקן האמיתי של שרת שכבר רץ במקביל על
    אותו מחשב."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(token)


# טוקן חדש בכל הפעלה של תהליך השרת - בכוונה לא נקרא מקובץ קיים, כדי שקישור
# שדלף (לוג ישן, צילום מסך, מצב --lan) לא יישאר תקף לצמיתות; הפעלה מחדש של
# השרת כבר מספיקה כדי לבטל אותו. מי שרוצה לבטל קישור דלוף בלי לסגור את השרת
# בכלל יכול ללחוץ "🔄 החלף טוקן" בכותרת העמוד (ראו /api/rotate_token למטה).
ACCESS_TOKEN = _generate_token()
_AUTH_COOKIE_NAME = "web_app_token"

# 22.10.2026 צימוד מכשיר (utils/shared/device_pairing.py): טלפון / ZimaOS מקבלים טוקן משלהם שנשאר בין הפעלות, בעוגייה
# clipforge_device או ב-Authorization: Bearer. טוקן המחשב למעלה נשאר כמו שהוא - חדש בכל הפעלה.
device_store = device_pairing.DeviceStore()
# בלי טוקן - הקוד החד-פעמי הוא האימות (routes/devices.py)
_PAIRING_PATHS = frozenset({"/pair", "/api/pair/token"})
# 30.10.2026: הדפדפן מבקש את ה-manifest (ואת האייקונים שבו) בלי עוגיות - <link rel="manifest"> בלי crossorigin. עם טוקן
# הוא קיבל 401, ואי אפשר היה להתקין את האפליקציה (PWA). קבצים קבועים, בלי שום מידע על המחשב או על המשתמש
_PWA_PUBLIC_PATHS = frozenset({"/manifest.json", "/assets/app_icon_192.png", "/assets/app_icon.png"})
# מחזירים את טוקן המחשב - מכשיר מצומד לא מקבל אותו (ה-route של /api/access_token ב-routes/editor_profiles.py)
_COMPUTER_TOKEN_PATHS = frozenset({"/api/access_token"})
# רק מהמחשב עצמו: טוקן המחשב וגם בקשה מ-loopback (טלפון עם קישור הטוקן דרך Tailscale לא מצמד ולא מחליף טוקן)
_LOCAL_ONLY_PATHS = frozenset({"/api/rotate_token"})
_LOCAL_ONLY_PREFIX = "/api/devices"
_WS_REVOKE_CHECK_SECONDS = 1.0


# אותם תוויות/מיפוי תיקייה->קטגוריה כמו ui/sidebar.py - לא משותף איתו במודול
# נפרד כי sidebar.py כורך את זה יחד עם t()/אימוג'י-לפי-שפה של ה-GUI; כאן מספיק
# עברית קבועה, בלי לגרור תלות ב-Tkinter/i18n לתוך שרת ה-web.
CATEGORY_LABELS = {"video": "🎬 פייפליין וידאו", "stream": "📡 סטרימינג", "steam": "🎮 Steam", "tools": "🛠️ כלי עזר"}
DEFAULT_CATEGORY = "🛠️ כלי עזר"

# item: ארכיון - סקריפטים שנבדקו ידנית מול "סקריפט-על" קיים (video_editor.py /
# super_manager.py / super_streamer.py) ונמצאו מיותרים *לגמרי* (לא רק חופפים
# חלקית) - הסקריפט-העל כבר עושה כל מה שהם עושים. רשימה קבועה קטנה, לא מנגנון-
# סימון גנרי. עדיין ניתנים להרצה מהארכיון - "מיותר" לא אומר "שבור", רק שיש
# דרך עדיפה לעשות את אותו הדבר:
#   - timelapse_maker.py: --target-seconds ב-video_editor.py משתמש באותה בדיוק
#     לוגיקת מהירות/atempo מ-utils/media/timelapse.py, בתוספת watermark/captions/LUT/
#     וכו' ש-timelapse_maker.py לא מציע בכלל.
#   - disk_scanner.py/report_to_excel.py/duplicate_cleaner.py: שלושת המצבים
#     (scan/report/clean) של super_manager.py הם קריאה ישירה ל-main() של אותם
#     שלושה קבצים בדיוק, בלי שינוי התנהגות - super_manager.py הוא רק בורר-מצב.
#   - twitch_clip_import.py/obs_replay_watcher.py/capture_folder_watcher.py:
#     אותו עיקרון, שלושת המצבים (twitch/obs/folder) של super_streamer.py.
#   - migrate_secrets_to_vault.py: סקריפט הגירה חד-פעמית (מ-.env ל-Windows
#     Credential Manager) - לא "מיותר בגלל סקריפט-על", אלא כי מטרתו כבר מוצתה
#     (מי שהריץ אותו פעם לא צריך להריץ שוב); נשאר ניתן להרצה למי שעוד לא.
#
# סקריפטים שרק *חופפים חלקית* (rocket_shorts_publisher.py, story_cutter.py,
# duplicate_scene_detector.py, file_renamer.py, audio_converter.py)
# נשארים ברשימה הרגילה בכוונה - יש להם ייעוד ייחודי אמיתי
# שאף סקריפט-על קיים לא מכסה, או שאין להם קשר תוכני לשרשרת שמוזגה.
ARCHIVED_SCRIPTS = {
    "timelapse_maker.py",
    "disk_scanner.py", "report_to_excel.py", "duplicate_cleaner.py",
    "twitch_clip_import.py", "obs_replay_watcher.py", "capture_folder_watcher.py",
    "migrate_secrets_to_vault.py",
}

app = FastAPI(title="ClipForge - Web")

# הגנה מפני הצפת בקשות - עד כה שום endpoint לא היה מוגבל בקצב בכלל, אז מי
# שכבר יש לו טוקן תקין (או --lan, שהוא ברירת מחדל פתוחה יותר) יכול היה לשלוח
# מאות בקשות /api/run לשנייה בלי שום הגבלה. get_remote_address (לא הטוקן עצמו)
# כמפתח ההגבלה - כל כתובת IP מוגבלת בנפרד, גם אם כולן חולקות את אותו טוקן.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def _require_access_token(request: Request, call_next):
    """דורש טוקן גישה תקין (עוגייה, או ?token=... בפעם הראשונה - ראו
    ACCESS_TOKEN) לפני שמגיעים לכל route. בלי זה כל תוכנה אחרת על אותו מחשב
    יכולה לגשת לשרת הזה ולהריץ סקריפטים, גם בלי לדעת שהוא בכלל קיים.

    query param נבדק *לפני* העוגייה בכוונה - לא רק אחריה: בלי הסדר הזה, עוגייה
    ישנה/לא תקינה מריצה קודמת (השרת נוצר מחדש עם טוקן חדש, למשל) הייתה "תקועה"
    לצמיתות - Python's `or` היה בוחר בעוגייה (truthy, גם אם שגויה) ומעולם לא
    בודק את הטוקן הטרי שכן הועבר מפורשות ב-URL. נמצא בפועל תוך כדי בדיקה חיה."""
    # /health יוצא מן הכלל בכוונה (item 28) - כלי ניטור זמינות חיצוני
    # (UptimeRobot/Healthchecks.io וכו') לא יכול להזין טוקן גישה בכלל, ולא
    # אמור לצטרך אחד רק כדי לדעת שהשרת עדיין מגיב. חושף רק "חי/לא חי", בלי
    # שום מידע על מה שרץ בפועל על המחשב הזה.
    path = request.url.path
    if path == "/health" or path in _PAIRING_PATHS or path in _PWA_PUBLIC_PATHS:
        return await call_next(request)

    auth = _authenticate(request)
    if auth is None:
        if request.cookies.get(device_pairing.COOKIE_NAME):
            message = "המכשיר הזה כבר לא מצומד (בוטל, או לא היה בשימוש 90 יום) - צמד אותו מחדש מהמחשב."
        else:
            message = "נדרש טוקן גישה תקין - השתמש בקישור המלא שהודפס בקונסולה בהפעלת השרת."
        return JSONResponse({"error": message}, status_code=401)
    request.state.auth_kind, request.state.device_id = auth
    if auth[0] == "device" and path in _COMPUTER_TOKEN_PATHS:
        return JSONResponse({"error": "לא זמין ממכשיר מצומד - רק עם טוקן המחשב."}, status_code=403)
    if (path in _LOCAL_ONLY_PATHS or path.startswith(_LOCAL_ONLY_PREFIX)) and not _is_local_computer(request):
        return JSONResponse({"error": "זמין רק מהמחשב עצמו (127.0.0.1)."}, status_code=403)

    response = await call_next(request)
    if _same_token(request.query_params.get("token"), ACCESS_TOKEN) and not _same_token(request.cookies.get(_AUTH_COOKIE_NAME), ACCESS_TOKEN):
        # קישור ה-URL עם ?token=... שימש רק כדי להיכנס בפעם הראשונה - מעכשיו
        # עוגייה דואגת להמשך, כדי שה-URL הנקי (בלי הטוקן בטקסט גלוי) יעבוד.
        response.set_cookie(_AUTH_COOKIE_NAME, ACCESS_TOKEN, httponly=True, samesite="lax")
    return response


# מצב הריצה הנוכחית - גלובלי-לתהליך בכוונה (לא per-connection): יש רק "הרצה
# פעילה" אחת בכל רגע נתון, בדיוק כמו שיש רק חלון GUI אחד עם כפתור "הרץ" אחד.
_current_run = {"script_name": None, "started_at": None}
_finished_queue = queue.Queue()

# באפר טבעתי של שורות הלוג האחרונות - queue.Queue.get_nowait() הרסני (מי
# שקורא ראשון "לוקח" את השורה), אז חיבור WebSocket שהתנתק ומתחבר מחדש (רשת לא
# יציבה, טאב שנרדם) היה מפספס לצמיתות כל מה שקרה בזמן שהיה מנותק. נוקה בתחילת
# כל הרצה חדשה (api_run) כדי לא לשחזר לוג של ריצה ישנה/לא קשורה.
_LOG_REPLAY_BUFFER = collections.deque(maxlen=500)

# item: log spam - תקרה גלובלית (לא תלוית-סקריפט) על כמה שורות נשלחות ב-
# הודעת WebSocket אחת. בלי זה, סקריפט שמדפיס פרץ גדול של שורות *אמיתיות* בין
# tick ל-tick (למשל אלפי "[SKIP] קובץ קיים כבר" ברצף מהיר על ספריית-וידאו
# ענקית - לא רק עדכוני tqdm, שכבר סוננו ב-utils/shared/worker.py) היה גורם לשליחת
# מאות/אלפי הודעות WebSocket נפרדות ולביצוע מאות/אלפי פעולות DOM נפרדות
# בדפדפן - שתי אלה עצמן, לא רק כמות הטקסט, הן מה שבפועל תוקע/מכביד. העודף
# פשוט ממתין בתור וממשיך להישלח ב-iterations הבאות של הלולאה (כל 50-200ms) -
# שום דבר לא הולך לאיבוד, רק נפרש על פני זמן.
_LOG_BATCH_SIZE = 300

# --- ניהול תהליך הבוט (Discord) - זהה בעיקרון ל-ui/bot_tab.py, רק בלי Tkinter.
# תהליך נפרד לגמרי מ-worker.py (שמריץ סקריפטי אוטומציה) - main.py הוא תהליך
# ארוך-טווח (רץ עד שנעצר במפורש), לא "משימה שמסתיימת".
_bot_state = {"process": None, "is_running": False, "gave_up": False, "config_error": False, "crash_timestamps": []}
_bot_state_lock = threading.Lock()
_bot_log_buffer = collections.deque(maxlen=500)
_bot_log_queue = queue.Queue()


# הסקריפטים שכותבים לתיקייה של כלי (export_dir.output_dir) - ההודעה נבדקת לפי התיקייה שלהם; כל השאר לפי הכללית
_SCRIPT_EXPORT_TOOLS = {"video_editor.py": _workspace_layout.STUDIO, "timelapse_maker.py": _workspace_layout.TIMELAPSES,
                        "highlight_reel_maker.py": _workspace_layout.HIGHLIGHT_REELS, "dataviz_maker.py": _workspace_layout.DATAVIZ}


_night_shutdown_waiting = False   # מצב לילה: ריצה הצליחה כשעוד היו משימות בתור - הכיבוי מחכה לסוף התור


def _find_scripts():
    return sorted(glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.py"), recursive=True))


def _category_for(script_path):
    folder_name = os.path.basename(os.path.dirname(script_path))
    return CATEGORY_LABELS.get(folder_name, DEFAULT_CATEGORY)


def _tags_cache_path(validated_path):
    return _clip_tags_cache_path(validated_path, TAGS_CACHE_DIR)


def _generate_and_record_thumbnail_candidates(video_id, clip_path):
    """נקרא מיד אחרי העלאה מוצלחת, בזמן שקובץ הקליפ המקורי עדיין ודאי קיים
    (item: A/B thumbnail testing) - נשמר תחת THUMBNAIL_CANDIDATES_DIR/<video_id>,
    לא לפי נתיב הקליפ, כדי שהמועמדות יישארו נגישות גם אם הקליפ המקורי יוזז/יימחק
    בהמשך. כשל כאן (ffmpeg נכשל וכו') לא אמור להפיל את ההעלאה שכבר הצליחה בפועל -
    תמונות מועמדות הן שיפור-חוויה אופציונלי, לא חלק מהעלאה עצמה."""
    try:
        out_dir = os.path.join(THUMBNAIL_CANDIDATES_DIR, video_id)
        candidate_paths = generate_candidates(clip_path, out_dir, get_ffmpeg_exe(), get_ffprobe_exe())
        youtube_thumbnail_log.record_candidates(video_id, candidate_paths)
    except Exception as e:
        print(f"[web_app] שגיאה ביצירת תמונות ממוזערות מועמדות: {e}")


# --- אנליטיקס YouTube (item: YouTube Analytics feedback loop) ---


# --- אישור קליפים (item: mobile-friendly clip-approval view) - CLIPS_REVIEW_DIR
# ב-utils/bot/approval_store.py הוא בדיוק אותה תיקייה כמו CLIPS_DIR למעלה
# (workspace/clips), אז /api/clips/thumbnail ו-/api/clips/stream הקיימים כבר
# עובדים על הנתיבים האלה כמות שהם - אין צורך בעוד endpoint לתמונה ממוזערת/סטרימינג. ---


# ============================================================================
# גל 6 של 102-ההצעות: פרופילים - השלב הבא (items 60-68)
# ============================================================================


# item 67: שיתוף בקישור/QR - QR כ-SVG (ספריית qrcode, בלי תלות ב-PIL), וכתובת
# הרשת המקומית כשהשרת רץ במצב --lan (כדי שהקישור ייפתח מהטלפון, לא רק מכאן).
LAN_BASE_URL: Optional[str] = None
# גישה דרך Tailscale (19.10.2026, utils/shared/tailscale.py): הכתובת לפתיחה מהטלפון, והמארחים שבדיקת ה-Origin מקבלת.
# None = כמו קודם (רק Origin == Host); מוגדר = גם המארח חייב להיות loopback, כתובת ה-Tailscale או שם ה-MagicDNS שלה -
# כך שאתר זר שהשם שלו מצביע על כתובת המחשב (DNS rebinding) לא עובר.
TAILSCALE_BASE_URL: Optional[str] = None
TRUSTED_HOSTS: Optional[set] = None
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
QR_MAX_DATA_LENGTH = 2800


def _get_favorite_script_names(config):
    """זהה ל-state.get_favorite_scripts() - CSV ב-config.json's favorite_scripts,
    כדי שסקריפט שסומן מועדף בדסקטופ יופיע מסומן גם בדפדפן (ולהפך)."""
    csv = str(config.get("favorite_scripts", ""))
    return {name for name in csv.split(",") if name}


def _list_drives():
    """מחזיר את כל נקודות העיגון הזמינות (C:\\, D:\\ וכו' בווינדוס; / וכו' בלינוקס/מק) -
    בלי זה אין שום דרך להגיע לכונן אחר מלבד זה שבו נמצא נתיב הבית של המשתמש
    (C:\\ בדרך כלל), כי "עלייה לתיקיית אב" מ-C:\\ עצמה חוזרת ל-C:\\ (dirname של
    שורש כונן מחזיר את עצמו) - מבוי סתום בלי רשימת כוננים מפורשת."""
    if psutil:
        try:
            drives = {p.mountpoint for p in psutil.disk_partitions(all=False) if p.mountpoint}
            if drives:
                return sorted(drives)
        except Exception:
            pass
    if sys.platform == "win32":
        return [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]
    return ["/"]


from entrypoints.web.script_args import (  # noqa: F401
    NVENC_PRESETS,
    _clamped_float,
    _fmt_num,
    _ASPECTS,
    _CHOICES,
    _CHOICE_DEFAULTS,
    _COLOR_TEXT_RE,
    _build_wave7_args,
    _GRADE_TRIPLET_RE,
    _CURVE_POINTS_RE,
    _build_wave25_args,
    _HEX6_RE,
    _hex_or_none,
    _int_in,
    _build_wave7b_args,
    DATAVIZ_MODES,
    _args_dataviz,
    _args_story_cutter,
    _ve_args_watermark,
    _ve_args_remove_watermark_and_pip,
    _ve_args_trim,
    _ve_args_captions,
    _ve_args_fps_loudnorm_lut,
    _ve_args_fades_text_audio_parallel,
    _ve_args_output,
    _ve_args_detect_and_nvenc,
    _ve_args_concat_and_transition,
    _args_video_editor,
    _args_rocket_shorts,
    _args_super_manager,
    _args_super_streamer,
    _SCRIPT_ARG_BUILDERS,
    _build_extra_args,
)

# item: דריסות פר-קובץ - קבצי ה-JSON הזמניים ש-api_run כותב ל---batch-overrides
# (הסקריפט מקבל נתיב לקובץ, לא JSON גולמי). תיקייה ייעודית תחת workspace/ (לא
# data/ - אלה לא נתוני-משתמש, רק קלט חד-פעמי לריצה), קבצים ישנים מ-7 ימים
# מנוקים בכל כתיבה חדשה.
BATCH_OVERRIDES_DIR = os.path.join(WORKSPACE_DIR, ".batch_overrides")
BATCH_OVERRIDES_MAX_AGE_SECONDS = 7 * 86400


def _write_batch_overrides_file(overrides):
    os.makedirs(BATCH_OVERRIDES_DIR, exist_ok=True)
    now = time.time()
    for old in glob.glob(os.path.join(BATCH_OVERRIDES_DIR, "overrides_*.json")):
        try:
            if now - os.path.getmtime(old) > BATCH_OVERRIDES_MAX_AGE_SECONDS:
                os.remove(old)  # safe: this app's own expired single-run overrides input under workspace/.batch_overrides/, never user data
        except OSError:
            pass
    fd, path = tempfile.mkstemp(prefix="overrides_", suffix=".json", dir=BATCH_OVERRIDES_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
    return path


# גל 7 של 102-ההצעות (items 69-89): עריכה ותוכן - דגלי הרינדור החדשים. כל דגל
# נשלח רק כשהוא שונה מברירת המחדל של הסקריפט, כדי שהפקודה תישאר קריאה.
CAPTIONS_EDITS_DIR = os.path.join(WORKSPACE_DIR, ".captions_edits")


# item 70: עורך תמלול לפני שריפה - Whisper רץ ברקע (job), הטקסט נערך בדפדפן
# ונשמר כ-SRT תחת CAPTIONS_EDITS_DIR (לפי sha1 של נתיב המקור, ראו
# captions.edited_captions_path). בריצה, video_editor.py שורף את הערוך במקום
# לתמלל מחדש - אותה פונקציית-נתיב בדיוק בשני הצדדים.
_transcribe_jobs: dict = {}
_transcribe_jobs_lock = threading.Lock()
_TRANSCRIBE_JOBS_MAX = 20
_CAPTION_SEGMENTS_MAX = 5000


def _transcribe_video_segments(path, language, model_size):
    from utils.media.captions import transcribe_segments
    return transcribe_segments(path, language=language, model_size=model_size)


def _run_transcribe_job(job_id, path, language, model_size):
    try:
        segments = _transcribe_video_segments(path, language, model_size)
        result = {"status": "done", "segments": [
            {"start": round(float(seg["start"]), 3), "end": round(float(seg["end"]), 3), "text": str(seg["text"])}
            for seg in segments
        ]}
    except Exception as e:  # faster-whisper חסר/קובץ פגום - מוצג למשתמש, לא מפיל את השרת
        result = {"status": "error", "error": str(e) or e.__class__.__name__}
    with _transcribe_jobs_lock:
        if job_id in _transcribe_jobs:
            _transcribe_jobs[job_id].update(result)


def _sanitize_caption_segments(raw_segments):
    if not isinstance(raw_segments, list) or len(raw_segments) > _CAPTION_SEGMENTS_MAX:
        return None
    clean = []
    for seg in raw_segments:
        if not isinstance(seg, dict):
            return None
        try:
            start, end = float(seg.get("start")), float(seg.get("end"))
        except (TypeError, ValueError):
            return None
        text = str(seg.get("text") or "").replace("\r", "").strip()
        if not text:
            continue
        if start < 0 or end <= start or len(text) > 2000:
            return None
        clean.append({"start": start, "end": end, "text": text})
    clean.sort(key=lambda seg: seg["start"])
    return clean


# גל 7ב של 102-ההצעות (items 79-89): שכבות מתוזמנות, קישוטים ועיבוד-אחרי. השכבות
# נשלחות לסקריפט כקובץ JSON (כמו --batch-overrides) - תחת workspace/.cache/layers, קבצים
# ישנים מ-7 ימים מנוקים בכל כתיבה.
LAYERS_DIR = os.path.join(WORKSPACE_DIR, WORKSPACE_SUBDIRS["LAYERS_DIR"])


def _write_layers_file(payload):
    from utils.video.video_editor_layers import sanitize_layers
    layers = sanitize_layers(payload.get("layers"))
    if not layers:
        return None
    os.makedirs(LAYERS_DIR, exist_ok=True)
    now = time.time()
    for name in os.listdir(LAYERS_DIR):
        old = os.path.join(LAYERS_DIR, name)
        try:
            if name.startswith("layers_") and now - os.path.getmtime(old) > BATCH_OVERRIDES_MAX_AGE_SECONDS:
                os.remove(old)
        except OSError:
            pass
    fd, path = tempfile.mkstemp(prefix="layers_", suffix=".json", dir=LAYERS_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(layers, f, ensure_ascii=False, indent=2)
    return path


# item: בורר גופנים מהגופנים המותקנים - שמות משפחה אמיתיים (לא שמות-קובץ),
# נקראים מתוך קובצי הגופן עצמם (PIL getname) - אותו שם ש-libass/fontconfig
# של ffmpeg מחפש ב-font=/FontName=. נסרק פעם אחת ונשמר בזיכרון לכל חיי השרת.
SYSTEM_FONT_DIRS = [
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
]
_system_fonts_cache: Optional[list] = None


def list_system_font_families(font_dirs=None):
    from PIL import ImageFont
    families = set()
    for font_dir in (font_dirs if font_dirs is not None else SYSTEM_FONT_DIRS):
        if not font_dir or not os.path.isdir(font_dir):
            continue
        for name in os.listdir(font_dir):
            if os.path.splitext(name)[1].lower() not in (".ttf", ".otf", ".ttc"):
                continue
            try:
                family, _style = ImageFont.truetype(os.path.join(font_dir, name), size=12).getname()
            except Exception:
                continue
            if family:
                families.add(family.strip())
    return sorted(families, key=str.lower)


_system_fonts_lock = threading.Lock()


# ============================================================================
# גל 4 של 102-ההצעות: תצוגה מקדימה ומשוב (items 40-50)
# ============================================================================

VIDEO_EDITOR_SCRIPT_PATH = os.path.join(SCRIPTS_DIR, "video", "video_editor.py")
PREVIEWS_DIR = os.path.join(WORKSPACE_DIR, WORKSPACE_SUBDIRS["PREVIEWS_DIR"])
# חייב להיות אותו נתיב כמו RUN_MANIFESTS_DIR ב-my_scripts/video/video_editor.py (הסקריפט כותב, השרת קורא)
RUN_MANIFESTS_DIR = os.path.join(WORKSPACE_DIR, WORKSPACE_SUBDIRS["RUN_MANIFESTS_DIR"])
PREVIEW_MAX_AGE_SECONDS = 86400
EDITOR_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm")

# דגלי "מצב-ריצה" שלא רלוונטיים לתצוגה מקדימה/בדיקה של פריים בודד (רינדור
# מחדש/קונטקט-שיט/מקבילות/דוחות/מספור/GPU/יעד-גודל) - מוסרים מה-payload לפני
# בניית הארגומנטים, כדי שהתצוגה המקדימה תמיד תרוץ מהר ב-CPU ולא תקצה מספר.
_PREVIEW_IRRELEVANT_KEYS = (
    "force", "preview_only", "validate_only", "parallel", "max_concurrent_nvenc", "export_report",
    "notify_per_file", "number_videos", "thumbnail", "only_files", "concat_mode", "concat_files",
    "hwaccel", "hwaccel_decode", "target_size_mb", "effort", "priority",
    # גל 7ב: שלבי עיבוד-אחרי רצים רק על פלט גמור - לא רלוונטיים לפריים/בדיקה
    "intro_path", "outro_path", "boomerang", "loop_count", "meta_title", "meta_comment", "chapters", "export_gif", "export_audio",
)


def _cleanup_old_previews():
    now = time.time()
    for old in glob.glob(os.path.join(PREVIEWS_DIR, "*")):
        try:
            if os.path.isfile(old) and now - os.path.getmtime(old) > PREVIEW_MAX_AGE_SECONDS:
                os.remove(old)  # safe: this app's own expired preview images under workspace/.cache/previews/, never user data
        except OSError:
            pass


def _editor_root_videos(folder):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [n for n in names if n.lower().endswith(EDITOR_VIDEO_EXTENSIONS) and os.path.isfile(os.path.join(folder, n))]


def _pick_editor_file(folder, requested=None):
    """הקובץ שעליו רצים תצוגה-מקדימה/בדיקה: requested (שם-קובץ בתוך folder
    בלבד, לא נתיב חופשי) אם קיים, אחרת הראשון בסדר האלפביתי."""
    videos = _editor_root_videos(folder)
    if requested:
        name = os.path.basename(str(requested))
        return name if name in videos else None
    return videos[0] if videos else None


def _run_editor_subprocess(folder, args, timeout):
    # גל 24: תצוגה מקדימה/בדיקת הגדרות - נתיב interactive, לא נחסם מאחורי הצפת thumbnails
    from utils.video import media_pool
    cmd = [get_python_executable() or sys.executable, "-u", VIDEO_EDITOR_SCRIPT_PATH, "--input_dir", folder, *args]
    return media_pool.run(
        cmd, lane="interactive", cwd=BASE_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=NO_WINDOW_FLAGS,
    )


def _routes_pro_busy_guard():
    from entrypoints.web.routes.pro import busy_guard_for_run
    return busy_guard_for_run()


def _preview_payload(payload):
    return {k: v for k, v in payload.items() if k not in _PREVIEW_IRRELEVANT_KEYS}


def _effective_editor_payload(payload, preview_target=None, pick_one_target=False):
    """גל 12: מה שהרנדרר באמת יקבל - ערכת המותג המקושרת (הגרסה העדכנית), שכבות-קליפ
    שעוברות לעריכת הקליפ שלהן, ועריכות-הקליפ מתורגמות לדריסות פר-קובץ. בתצוגה
    מקדימה/בדיקה/הערכה גם נבחר יעד אחד (המבוקש או הראשון)."""
    payload = editor_model.with_clip_layers(brand_kits.apply_brand_kit(dict(payload)))
    if pick_one_target:
        payload = editor_model.pick_target(payload, preview_target)
    raw_overrides = payload.get("batch_overrides") if isinstance(payload.get("batch_overrides"), dict) else {}
    payload["batch_overrides"] = sanitize_batch_overrides(editor_model.merge_clip_edits_into_overrides(raw_overrides, payload.get("clip_edits")))
    return payload


# item 42: ציר-זמן עם תמונות ממוזערות - N פריימים בחיפוש-קלט מהיר (-ss לפני -i,
# לא fps= על כל הקובץ - מהיר גם על הקלטה של שעות), מורכבים לפס אחד עם PIL,
# ממוטמן לפי נתיב+גודל+mtime+N.
TIMELINE_THUMB_WIDTH = 160


# ============================================================================
# גל 5 של 102-ההצעות: תור העיבוד (items 51-57)
# ============================================================================


# ============================================================================
# גל 8 של 102-ההצעות: ריצה, אוטומציה ואינטגרציה (items 90-96)
# ============================================================================

EDITOR_RUNS_FILENAME = data_paths.EDITOR_RUNS
RUN_CONTROL_DIR = os.path.join(WORKSPACE_DIR, WORKSPACE_SUBDIRS["RUN_CONTROL_DIR"])
PUBLISH_BATCHES_DIR = os.path.join(WORKSPACE_DIR, ".publish_batches")
PUBLISHER_SCRIPT_PATH = os.path.join(SCRIPTS_DIR, "video", "rocket_shorts_publisher.py")
SLEEP_COUNTDOWN_SECONDS = 60
_pending_sleep: dict = {"timer": None, "due_at": None}


def _editor_runs_path():
    # ליד קובץ הפרופילים (data/) - נגזר בזמן הקריאה, כך שטסטים שמפנים את
    # PROFILES_PATH ל-tmp לא נוגעים בהיסטוריה האמיתית של המשתמש.
    return os.path.join(os.path.dirname(video_editor_profiles.PROFILES_PATH), EDITOR_RUNS_FILENAME)


def _create_run_control_file():
    os.makedirs(RUN_CONTROL_DIR, exist_ok=True)
    now = time.time()
    for name in os.listdir(RUN_CONTROL_DIR):
        old = os.path.join(RUN_CONTROL_DIR, name)
        try:
            if name.startswith("run_") and now - os.path.getmtime(old) > BATCH_OVERRIDES_MAX_AGE_SECONDS:
                os.remove(old)
        except OSError:
            pass
    path = os.path.join(RUN_CONTROL_DIR, f"run_{int(now * 1000)}_{secrets.token_hex(3)}.json")
    run_control.write_state(path, run_control.EMPTY_STATE)
    return path


def _sanitize_finish_actions(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {key: bool(raw.get(key)) for key in ("open_folder", "sound", "sleep")}


def _manifest_created_outputs(manifest_path):
    """נתיבי הפלטים שנוצרו בפועל בריצה (מה-run manifest שהסקריפט כתב)."""
    real = os.path.realpath(str(manifest_path or ""))
    if not manifest_path or not real.startswith(os.path.realpath(RUN_MANIFESTS_DIR) + os.sep) or not os.path.isfile(real):
        return []
    try:
        with open(real, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [r["output"] for r in data.get("files", []) if r.get("status") == "created" and r.get("output") and os.path.isfile(r["output"])]


def _prepare_publish_batch(outputs):
    """item 90: תיקיית-אצווה חדשה עם *רק* הפלטים של הריצה הזו (hardlink, או העתקה
    בין כוננים) - Rocket Shorts מעבד את כל התיקייה, ותיקיית edited_videos מכילה גם
    פלטים ישנים שכבר פורסמו."""
    batch = os.path.join(PUBLISH_BATCHES_DIR, time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(2))
    os.makedirs(batch, exist_ok=True)
    for src in outputs:
        dst = os.path.join(batch, os.path.basename(src))
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return batch


def _open_folder_on_host(path):
    os.startfile(path)  # type: ignore[attr-defined]  # Windows בלבד - בדיוק כמו /api/open_folder


def _play_finish_sound():
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


def _put_computer_to_sleep():
    # מצב שינה אמיתי (לא hibernate) - SetSuspendState של .NET, בלי חלון
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)"],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
    )


def _schedule_sleep(seconds):
    _cancel_pending_sleep()
    timer = threading.Timer(seconds, _run_pending_sleep)
    timer.daemon = True
    _pending_sleep.update(timer=timer, due_at=time.time() + seconds)
    timer.start()


def _run_pending_sleep():
    _pending_sleep.update(timer=None, due_at=None)
    _put_computer_to_sleep()


def _cancel_pending_sleep():
    timer = _pending_sleep.get("timer")
    if timer is not None:
        timer.cancel()
    was_pending = timer is not None
    _pending_sleep.update(timer=None, due_at=None)
    return was_pending


def _handle_editor_run_finished(run_id, folder, payload, started_at, outcome):
    success = outcome.get("returncode") == 0
    result = outcome.get("result") if isinstance(outcome.get("result"), dict) else {}
    editor_runs.record_finish(_editor_runs_path(), run_id, success, result, time.time() - started_at)
    outcome["editor_run_id"] = run_id
    outputs = _manifest_created_outputs(result.get("manifest_path"))
    actions = _sanitize_finish_actions(payload.get("finish_actions"))
    if actions["sound"]:
        outcome["finish_sound"] = True
        _play_finish_sound()
    if actions["open_folder"] and outputs:
        try:
            _open_folder_on_host(os.path.dirname(outputs[0]))
        except (AttributeError, OSError):
            pass
    if success and payload.get("publish_after") and outputs and os.path.isfile(PUBLISHER_SCRIPT_PATH):
        batch = _prepare_publish_batch(outputs)
        extra = ["--dry-run"] if payload.get("publish_dry_run") else []
        worker.log_queue.put((f"🚀 משרשר פרסום Shorts ל-{len(outputs)} פלטים ({batch})\n", None))
        concurrency = get_script_metadata(PUBLISHER_SCRIPT_PATH).get("concurrency", "heavy")
        worker.add_script_task(PUBLISHER_SCRIPT_PATH, batch, _on_publisher_finished, concurrency=concurrency, extra_args=extra)
        outcome["publish_started"] = True
    if success and actions["sleep"]:
        _schedule_sleep(SLEEP_COUNTDOWN_SECONDS)
        outcome["sleep_seconds"] = SLEEP_COUNTDOWN_SECONDS


def _make_editor_finish_callback(run_id, folder, payload, started_at):
    def _callback(outcome):
        outcome = dict(outcome or {})
        try:
            _handle_editor_run_finished(run_id, folder, payload, started_at, outcome)
        except Exception as e:  # פעולת סוף-ריצה שנכשלה לא אמורה לבלוע את הודעת הסיום
            worker.log_queue.put((f"⚠️ פעולת סוף-ריצה נכשלה: {e}\n", "red"))
        finally:
            _on_task_finished(outcome)
    return _callback


# ============================================================================
# גל 32: שרשור מלא מ-OBS/תיקיית לכידה ועד פרסום (utils/media/auto_chain.py)
# ============================================================================

AUTO_CHAIN_RECENT_MAX = 8
_auto_chain_recent: list = []  # האחרון ראשון: {"at", "file", "source", "action", "text"}
_auto_chain_lock = threading.Lock()


def _auto_chain_note(event, plan, text):
    path = str(event.get("path") or "")
    entry = {"at": time.time(), "file": os.path.basename(path), "source": str(event.get("source") or ""),
             "action": plan.get("action") or plan.get("reason"), "text": text}
    with _auto_chain_lock:
        _auto_chain_recent.insert(0, entry)
        del _auto_chain_recent[AUTO_CHAIN_RECENT_MAX:]
    worker.log_queue.put((f"🔗 {text}\n", None))
    audit_log.record_action("web", "auto_chain", details=f"{entry['file']} -> {entry['action']}", username="auto_chain")


def _on_clip_ready(event):
    """קליפ חדש נכנס ל-Import (שורת EVENT מהמאזין) - מתכנן לפי ההגדרות ומכניס לתור הרינדור.
    נקרא מ-thread הקריאה של המאזין: רק מכניס לתור, לא מחכה לעריכה/לפרסום עצמם."""
    if event.get("script") not in auto_chain.SOURCE_SCRIPTS:
        return
    path = str(event.get("path") or "")
    profiles = {name: editor_model.migrate_profile(settings) for name, settings in video_editor_profiles.load_profiles().items()}
    plan = auto_chain.plan(_load_rocket_settings(), path, profiles)
    name = os.path.basename(path)
    if plan["action"] == "publish":
        if not os.path.isfile(PUBLISHER_SCRIPT_PATH):
            return
        batch = _prepare_publish_batch([path])
        concurrency = get_script_metadata(PUBLISHER_SCRIPT_PATH).get("concurrency", "heavy")
        worker.add_script_task(PUBLISHER_SCRIPT_PATH, batch, _on_publisher_finished, concurrency=concurrency,
                               extra_args=["--dry-run"] if plan["dry_run"] else [], label=f"📼 {name}")
    elif plan["action"] == "edit":
        response = _start_script_run(VIDEO_EDITOR_SCRIPT_PATH, plan["folder"], plan["payload"], "auto_chain")
        if isinstance(response, JSONResponse):
            error = json.loads(response.body).get("error", "")
            _auto_chain_note(event, {"action": None, "reason": "error"}, f"{name} - העריכה האוטומטית לא התחילה: {error}")
            return
    text = auto_chain.describe(plan, name)
    if text:
        _auto_chain_note(event, plan, text)


worker.on_event("clip_ready", _on_clip_ready)


def _watch_ws_disconnect(websocket):
    """מחזיר (event, task): ה-event נדלק ברגע שהלקוח מתנתק. בלי זה handler של
    טאב שנסגר ממשיך לרוץ ברקע עד שהוא מנסה *לשלוח* משהו - ובינתיים הוא "גונב"
    מתורי הלוג/התקדמות המשותפים (queue.Queue נשלף unicast) את השורות של הריצה
    הבאה, והטאב החי מפספס אותן. נמצא כשטסט WebSocket נתקע ב-CI: handlers
    יתומים מטסטי-דפדפן קודמים רוקנו את התור לפניו."""
    import asyncio

    disconnected = asyncio.Event()
    # 22.10.2026: חיבור של מכשיר מצומד (_authorize_websocket) נסגר עם 4401 כשמבטלים את המכשיר - כמו בקשות HTTP שלו
    device_id = getattr(websocket.state, "device_id", None)

    async def _close_when_revoked():
        while True:
            await asyncio.sleep(_WS_REVOKE_CHECK_SECONDS)
            if not device_store.is_active(device_id):
                disconnected.set()
                try:
                    await websocket.close(code=4401)
                except Exception:
                    pass
                return

    async def _watch():
        revoked = asyncio.create_task(_close_when_revoked()) if device_id else None
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
        except Exception:
            pass
        finally:
            if revoked:
                revoked.cancel()
            disconnected.set()

    return disconnected, asyncio.create_task(_watch())


# גל 11: הדף עצמו (HTML/CSS/JS) יושב בקבצים נפרדים תחת web/frontend/ ומורכב פעם אחת
# בטעינה - ראו web/frontend_assembly.py. התוצאה זהה לדף שהיה כאן כמחרוזת אחת.
_PAGE_HTML = assemble_page()
# גל 24: ה-CSS/JS כקבצים סטטיים עם hash בשם (routes/page.py), דחוסים מראש; גם ה-HTML
_PAGE_ASSETS = build_assets()
_PAGE_HTML_GZIP = gzip.compress(_PAGE_HTML.encode("utf-8"), 9, mtime=0)


# גל 11: ה-endpoints עצמם יושבים ב-web/routes/ (router לכל תחום); הקובץ הזה נשאר
# נקודת ההרכבה - מצב משותף, middleware, helpers - והם ניגשים אליו כ-W.<שם>.
import inspect  # noqa: E402
from entrypoints.web.routes import (  # noqa: E402 - חייב לבוא אחרי כל המצב המשותף שה-routers מפנים אליו
    editor_profiles as _routes_editor_profiles,
    workspace as _routes_workspace,
    player as _routes_player,
    pro as _routes_pro,
    editor as _routes_editor,
    clips as _routes_clips,
    dataviz as _routes_dataviz,
    dataviz_plus as _routes_dataviz_plus,
    runs as _routes_runs,
    bot as _routes_bot,
    automation as _routes_automation,
    system as _routes_system,
    devices as _routes_devices,
    outputs as _routes_outputs,
    notifications as _routes_notifications,
    page as _routes_page,
)

ROUTE_MODULES = (_routes_workspace, _routes_player, _routes_pro, _routes_editor_profiles, _routes_editor, _routes_clips, _routes_dataviz, _routes_dataviz_plus, _routes_runs, _routes_bot, _routes_automation, _routes_system, _routes_devices, _routes_outputs, _routes_notifications, _routes_page)
for _routes_module in ROUTE_MODULES:
    app.include_router(_routes_module.router)
    # תאימות: פונקציות ה-endpoint נשארות נגישות גם כ-web_app.<שם> (טסטים/קוד ישן)
    for _name, _value in vars(_routes_module).items():
        if inspect.isfunction(_value) and _value.__module__ == _routes_module.__name__:
            globals().setdefault(_name, _value)


# 24.10.2026: עליית השרת (פורט, מגש המערכת, כתובת LAN) - ב-web/server_startup.py; השמות נשארים גם כאן (__main__ למטה, טסטים)
from entrypoints.web.server_startup import (  # noqa: E402,F401 - אחרי המצב המשותף, כמו ה-routes
    DEFAULT_PORT, PORT_IN_USE_EXIT_CODE, _bind_server_socket, _bind_server_sockets, _get_lan_ip, _run_tray_icon,
)
# 24.10.2026: בדיקות הנתיבים (מה מותר להגיש, לפתוח, לפרסם ולשחזר) - ב-web/path_checks.py; השמות נשארים גם כאן
from entrypoints.web.path_checks import (  # noqa: E402,F401 - אחרי המצב המשותף, כמו ה-routes
    PUBLISHABLE_VIDEO_EXTENSIONS,
    _is_under_data_dir,
    _validate_clip_path,
    _rocket_output_root,
    _validate_publishable_path,
    _validated_caption_source,
    _is_under_workspace,
    _validate_backup_filename,
)
# 24.10.2026: קובצי ההגדרות (config.json, Rocket והמונה שלו, טבלאות הבוט) - ב-web/config_files.py; השמות נשארים גם כאן
from entrypoints.web.config_files import (  # noqa: E402,F401 - אחרי המצב המשותף, כמו ה-routes
    _ensure_bot_tables,
    _load_raw_config,
    _save_raw_config,
    _default_config_dict,
    _load_rocket_settings,
    _save_rocket_settings,
    _get_rocket_counter,
)
# 24.10.2026: מי רשאי (טוקן המחשב, מכשירים מצומדים, loopback, בדיקת ה-Origin) - ב-web/auth.py; השמות נשארים גם כאן
from entrypoints.web.auth import (  # noqa: E402,F401 - אחרי המצב המשותף, כמו ה-routes
    _same_token,
    _bearer_token,
    _authenticate,
    _is_loopback_client,
    _is_local_computer,
    _authorize_websocket,
    _is_same_origin,
    _host_name,
    trust_tailscale_hosts,
)
# 24.10.2026: תהליך הבוט (הלולאה שמריצה את main.py, הלוג וההתראה) - ב-web/bot_process.py; המצב והשמות נשארים גם כאן
from entrypoints.web.bot_process import (  # noqa: E402,F401 - אחרי המצב המשותף, כמו ה-routes
    _bot_write_to_log,
    _notify_bot,
    _run_bot_process_loop,
)
# 24.10.2026: מחזור החיים של ריצה (התחלה, סוף, מצב לילה, המשימות המתוזמנות) - ב-web/run_lifecycle.py; המצב והשמות נשארים גם כאן
from entrypoints.web.run_lifecycle import (  # noqa: E402,F401 - אחרי המצב המשותף, כמו ה-routes
    _export_fallback_note,
    _on_task_finished,
    _record_run_end,
    _on_publisher_finished,
    _notify_run_finished,
    _mirror_export_dirs,
    _work_still_queued,
    _finish_waiting_night_shutdown,
    _run_completion_side_effects,
    _start_script_run,
    _start_target_runs,
    _start_single_run,
    _run_scheduler_loop,
)


if __name__ == "__main__":
    import argparse
    cli_parser = argparse.ArgumentParser()
    cli_parser.add_argument(
        "--lan", action="store_true",
        help="חושף את השרת גם לרשת המקומית (LAN) - נגיש ממכשירים אחרים (נייד/טאבלט), לא רק מהמחשב הזה. "
             "כבוי כברירת מחדל (127.0.0.1 בלבד). השתמש בזהירות: מי שמקבל את קישור הטוקן יכול להריץ סקריפטים.",
    )
    cli_parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"פורט השרת (ברירת מחדל: {DEFAULT_PORT})")
    cli_parser.add_argument(
        "--tailscale", action="store_true",
        help="מאזין גם על כתובת ה-Tailscale של המחשב (100.x, לא 0.0.0.0) - לפתיחה מהטלפון דרך Tailscale. "
             "גם בלי הדגל: כשההגדרה פעילה ב-data/remote_access.json (כך ה-launcher מפעיל את המצב הזה).",
    )
    cli_args = cli_parser.parse_args()
    port = cli_args.port
    from utils.shared import tailscale as _tailscale
    bind_hosts, tailscale_ip, tailscale_note = _tailscale.bind_hosts(cli_args.tailscale or _tailscale.load_enabled(), lan=cli_args.lan)
    if tailscale_note:
        print(tailscale_note, flush=True)

    # קודם הפורט, אחר כך הטוקן: הפעלה שנייה (לחיצה כפולה על ה-launcher, שרת שכבר רץ) יוצאת כאן בלי לדרוס את
    # data/web_app_token.txt של השרת שרץ. הטוקן נכתב רק אחרי שכל ה-sockets שלנו (loopback, ובמצב Tailscale גם כתובת
    # ה-Tailscale), ולפני ש-uvicorn מאזין עליהם - מי שמחכה שהפורט יענה (_web_launcher_impl.bat) קורא כבר את הטוקן
    # החדש. טוקן חדש בכל הפעלה (fb3365d) - כמו קודם.
    try:
        server_sockets = _bind_server_sockets(bind_hosts, port)
    except OSError as e:
        print(f"⚠️  פורט {port} כבר תפוס ({e}) - כנראה ממשק הדפדפן כבר רץ. לא מפעילים עותק נוסף, והקישור הקיים "
              f"ממשיך לעבוד (הטוקן ב-{TOKEN_PATH} לא השתנה).", flush=True)
        sys.exit(PORT_IN_USE_EXIT_CODE)
    _persist_token(ACCESS_TOKEN)
    if tailscale_ip:
        tailscale_dns = _tailscale.magicdns_name(tailscale_ip)
        trust_tailscale_hosts(tailscale_ip, tailscale_dns)
        TAILSCALE_BASE_URL = f"http://{tailscale_dns or tailscale_ip}:{port}"
    # item: גיבוי אוטומטי מסתובב - גם גיבוי אחד בכל הפעלה, לא רק לפני כתיבה:
    # כך קיים עותק של המצב "כפי שהיה כשהשרת עלה" גם אם הקובץ ייפגע מחוץ לאפליקציה.
    backup_video_editor_profiles_now()

    # בדיקת תקינות מהירה (ffmpeg, מפתח Gemini, data/) עם הודעות ברורות - כשל בה אף פעם לא מונע הפעלה
    try:
        from utils.shared.diagnostics import print_startup_health
        from utils.shared.secrets_vault import load_project_env
        load_project_env()   # כמו שסקריפטים עושים - אחרת מפתחות שרק ב-.env נראים "חסרים" בבדיקה ובדף ה-credentials
        print_startup_health()
    except Exception as e:
        print(f"⚠️  בדיקת התקינות בהפעלה נכשלה: {e}")

    if cli_args.lan:
        lan_ip = _get_lan_ip()
        # HTTPS (תעודה עצמית-חתומה) ולא HTTP רגיל - במצב --lan התעבורה (כולל
        # הטוקן עצמו) עוברת בפועל ברשת המקומית, לא רק בתוך המחשב עצמו
        # (127.0.0.1), אז מי שמריח תעבורה ברשת יכול היה עד כה לגנוב את הטוקן
        # בטקסט גלוי. ensure_self_signed_cert כולל את ה-IP הנוכחי ברשת
        # כ-SAN - הדפדפן עדיין יציג אזהרת אמון פעם ראשונה (תעודה לא חתומה
        # ע"י CA אמיתי), אבל התעבורה עצמה מוצפנת.
        ensure_self_signed_cert(TLS_CERT_PATH, TLS_KEY_PATH, extra_hosts=[lan_ip])
        print("⚠️  מצב LAN מופעל - השרת נגיש מכל מכשיר באותה רשת מקומית, לא רק מהמחשב הזה.")
        print("    שתף את הקישור רק עם מי שאתה סומך עליו - כל מי שמקבל אותו יכול להריץ סקריפטים על המחשב הזה.")
        print("    הדפדפן עשוי להזהיר 'החיבור אינו פרטי' (תעודה עצמית-חתומה, לא CA מוכר) - זה צפוי, לחצו המשך/Advanced.")
        print("🚀 ממשק הדפדפן עולה (HTTPS) - קישורים זמינים:")
        print(f"   מהמחשב הזה:        https://127.0.0.1:{port}/?token={ACCESS_TOKEN}")
        print(f"   מהרשת המקומית: https://{lan_ip}:{port}/?token={ACCESS_TOKEN}")
        LAN_BASE_URL = f"https://{lan_ip}:{port}"  # item 67: קישורי שיתוף פרופיל שנפתחים גם מהטלפון
        open_url = f"https://127.0.0.1:{port}/?token={ACCESS_TOKEN}"
        uvicorn_config = uvicorn.Config(app, host="0.0.0.0", port=port, ssl_certfile=TLS_CERT_PATH, ssl_keyfile=TLS_KEY_PATH)
    else:
        print("🚀 ממשק הדפדפן עולה - פתח את הקישור הבא (כולל טוקן הגישה, מקומי בלבד):")
        print(f"   http://127.0.0.1:{port}/?token={ACCESS_TOKEN}")
        if TAILSCALE_BASE_URL:
            print("📱 מהטלפון (דרך Tailscale - רק מכשירים ב-tailnet שלך, מוצפן ע\"י Tailscale):")
            print(f"   {TAILSCALE_BASE_URL}/?token={ACCESS_TOKEN}")
            if tailscale_dns:
                print(f"   (או לפי כתובת: http://{tailscale_ip}:{port}/?token={ACCESS_TOKEN})")
        open_url = f"http://127.0.0.1:{port}/?token={ACCESS_TOKEN}"
        uvicorn_config = uvicorn.Config(app, host="127.0.0.1", port=port)

    # uvicorn.Config+Server מפורשים (לא uvicorn.run() הנוח) כדי שאייקון מגש
    # המערכת (thread נפרד) יוכל לעצור את השרת בעדינות דרך server.should_exit -
    # ראו _run_tray_icon. open_url מועבר אליו רק בשביל פריט התפריט "פתח
    # בדפדפן" (לחיצה ידנית) - לא נפתח אוטומטית כאן, כדי לא לפתוח פעמיים
    # כשההפעלה כן דרך WebLauncher.vbs (שכבר פותח דפדפן בעצמו).
    uvicorn_server = uvicorn.Server(uvicorn_config)
    threading.Thread(target=_run_tray_icon, args=(uvicorn_server, open_url), daemon=True).start()
    # גל 8 (item 91): המשימות המתוזמנות (כולל אלה שנוצרו מעורך-העל) רצות גם כשרק
    # ממשק הדפדפן פתוח - עד עכשיו רק ה-GUI השולחני (הקפוא) הפעיל את ה-Scheduler.
    threading.Thread(target=_run_scheduler_loop, daemon=True).start()
    uvicorn_server.run(sockets=server_sockets)   # הפורט שכבר תפסנו למעלה - uvicorn לא נקשר שוב
