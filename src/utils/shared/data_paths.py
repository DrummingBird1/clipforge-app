# utils/shared/data_paths.py
#
# 23.10.2026 (פריט 19, שלב א' - קוד בלבד, שום קובץ לא זז): כל השמות ב-data/ במקום אחד. עד עכשיו כל מודול הדביק את השם
# בעצמו על DATA_DIR (ה-DB - 15 פעם, rocket_settings.json - 12). השמות כאן יחסיים ל-data/; כשהקבצים יעברו
# לתיקיות לפי נושא (שלב ב'), משנים רק כאן - ואת שלושת המקומות שסורקים את data/ כולה: הגיבוי היומי (cogs/scheduler_cog.py),
# הגיבוי המוצפן (encrypted_backup.py) והאבחון (diagnostics.py), שקוראים מכאן מה לדלג עליו ומה לבדוק.
# כל מודול שומר את הקבוע שלו (DB_PATH וכו'), כי טסטים מחליפים אותו - הערך רק מגיע מכאן.
# עורך הגרפים מקבל data_dir כפרמטר (טסטים מעבירים תיקייה זמנית), לכן לו השם (DATAVIZ_*), לא נתיב.
#
# 24.10.2026 (שלב ג'): התיקייה של כל שם - FOLDERS. ‏path() מחזיר <תיקייה>/<שם> רק אחרי ש-dev/migrate_data_layout.py --apply
# הזיז את הקבצים וכתב את LAYOUT_MARKER ב-data/. עד אז הכל שטוח - קריאה וכתיבה למקום הישן, בלי מצב ביניים. אחרי ההעברה,
# שם שקיים רק במקום השטוח (שחזור ידני, תהליך ישן) נקרא משם. עורך הגרפים מקבל dataviz_root() כ-data_dir שלו.
#
# 30.10.2026: ה-DB נקרא clipforge_data.db. השם הקודם כלל את שם הבעלים, ולכן הוא לא כתוב כאן (הריפו יוצא לציבור) - רק ה-SHA-256
# שלו, LEGACY_BOT_DB_SHA256. ‏migrate_bot_db() מעביר את הקובץ הישן פעם אחת, בייבוא הראשון של המודול - לפני שמודול כלשהו מחשב
# את DB_PATH שלו. עד שההעברה מצליחה (קובץ פתוח בתהליך אחר = מנסים שוב בהפעלה הבאה), path(BOT_DB) מחזיר את הקובץ הישן.
import hashlib
import os
import sqlite3
from typing import Iterable, Optional

from utils.shared.data_dir import DATA_DIR

# --- הגדרות ---
CONFIG = "config.json"
ROCKET_SETTINGS = "rocket_settings.json"
EXPORT_SETTINGS = "export_settings.json"
REMOTE_ACCESS = "remote_access.json"
SCHEDULED_TASKS = "scheduled_tasks.json"
# --- אבטחה (ב-.gitignore בכל עומק תחת data/) ---
WEB_TOKEN = "web_app_token.txt"
TLS_CERT = "web_app_tls_cert.pem"
TLS_KEY = "web_app_tls_key.pem"
PAIRED_DEVICES = "paired_devices.json"
CREDENTIAL_ROTATION = "credential_rotation.json"
# --- הבוט וה-DB המשותף ---
BOT_DB = "clipforge_data.db"
LEGACY_BOT_DB_SHA256 = bytes.fromhex("bb321514e185df7079f5a6cc7d0761cb89ce9c6c3a6c7cf4fb30edf77d9400ef")   # השם עד 1.1.0 (ראו למעלה)
SCHEDULER_STATE = "scheduler_state.json"
WAKE_TIMER = "wake_timer.json"
ROCKET_COUNTER = "counter.txt"
# --- הסטודיו ---
EDITOR_PROFILES = "video_editor_profiles.json"
EDITOR_PROFILE_META = "video_editor_profile_meta.json"
EDITOR_PROFILE_HISTORY = "video_editor_profile_history.json"
EDITOR_COUNTER = "video_editor_counter.txt"
EDITOR_RUNS = "video_editor_runs.json"        # ליד הפרופילים (web_app._editor_runs_path)
EDITOR_PROJECTS = "editor_projects"           # utils/video/editor_projects.py, ליד הפרופילים
EDITOR_ASSETS = "editor_assets"
# --- עורך הגרפים (שמות יחסיים ל-data_dir שהוא מקבל) ---
DATAVIZ_EPISODES = "dataviz_episodes"
DATAVIZ_OVERRIDES = "dataviz_overrides"
DATAVIZ_HIDDEN = "dataviz_hidden.json"
DATAVIZ_TAGS = "dataviz_tags.json"
DATAVIZ_HISTORY = "dataviz_history"
DATAVIZ_SMART = "dataviz_smart"
DATAVIZ_TRASH = "dataviz_trash"
DATAVIZ_VARIANTS = "dataviz_variants"
DATAVIZ_CACHE = "dataviz_cache"
DATAVIZ_MAPS = "dataviz_maps"
DATAVIZ_KITS = "dataviz_kits.json"
DATAVIZ_QUEUE = "dataviz_queue.json"
DATAVIZ_RENDER_STATS = "dataviz_render_stats.json"
DATAVIZ_TEMPLATES = "dataviz_templates"   # 27.10.2026: "שמור כתבנית" מפרק קיים
DATAVIZ_FLAGS = "dataviz_flags"           # 27.10.2026: דגלים למדינות (images.flags) - יורדים בלחיצה בעורך
# --- מטמונים ומצב ריצה ---
FFPROBE_CACHE = "ffprobe_cache.json"
RENDER_LOCK = "render.lock"
RENDER_WAITERS = "render_waiters.json"
MOVE_UNDO_LOG = "last_move_batch.json"
LEGACY_DISK_REPORT = "report.json"
# --- תיקיות ---
LOGS = "logs"
BACKUPS = "backups"
SEO_HISTORY_LOG = LOGS + "/seo_history_log.txt"
DB_RENAME_BACKUP = BACKUPS + "/bot_db_before_rename.db"   # עותק של ה-DB הישן, מרגע לפני ההעברה לשם החדש
# הסימן ש-dev/migrate_data_layout.py --apply סיים (data/<הסימן>). בלעדיו - מבנה שטוח
LAYOUT_MARKER = ".data_layout"

# שם בשורש data/ -> התיקייה שלו אחרי ההעברה. logs/, ‏backups/ ו-render.lock נשארים בשורש.
FOLDERS = {
    **dict.fromkeys((CONFIG, ROCKET_SETTINGS, EXPORT_SETTINGS, REMOTE_ACCESS, SCHEDULED_TASKS), "settings"),
    **dict.fromkeys((WEB_TOKEN, TLS_CERT, TLS_KEY, PAIRED_DEVICES, CREDENTIAL_ROTATION), "security"),
    **dict.fromkeys((BOT_DB, SCHEDULER_STATE, WAKE_TIMER, ROCKET_COUNTER), "bot"),
    **dict.fromkeys((EDITOR_PROFILES, EDITOR_PROFILE_META, EDITOR_PROFILE_HISTORY, EDITOR_COUNTER, EDITOR_RUNS, EDITOR_PROJECTS,
                     EDITOR_ASSETS), "studio"),
    **dict.fromkeys((DATAVIZ_EPISODES, DATAVIZ_OVERRIDES, DATAVIZ_HIDDEN, DATAVIZ_TAGS, DATAVIZ_HISTORY, DATAVIZ_SMART, DATAVIZ_TRASH,
                     DATAVIZ_VARIANTS, DATAVIZ_CACHE, DATAVIZ_MAPS, DATAVIZ_KITS, DATAVIZ_QUEUE, DATAVIZ_RENDER_STATS,
                     DATAVIZ_TEMPLATES, DATAVIZ_FLAGS), "dataviz"),
    **dict.fromkeys((FFPROBE_CACHE, RENDER_WAITERS, MOVE_UNDO_LOG, LEGACY_DISK_REPORT), "cache"),
}
DATAVIZ_FOLDER = "dataviz"
# קבצים שנוצרים ליד שם מהמיפוי ועוברים איתו: גיבוי של "אפס הגדרות"/ייבוא, וקובצי הצד של SQLite
_COMPANION_SUFFIXES = (".bak", "-wal", "-shm", "-journal")

# מה שהגיבויים מדלגים עליו - לפי שם, בכל עומק, כך שזה נשאר נכון גם אחרי שהקבצים יעברו לתיקיות לפי נושא: הגיבויים
# עצמם, הלוגים, מנעול הרינדור - וה-DB, שמצולם בנפרד (snapshot עקבי מ-path(BOT_DB), ונשמר בגיבוי בשם BOT_DB)
BACKUP_SKIP_DIRS = frozenset(name.rsplit("/", 1)[-1] for name in (BACKUPS, LOGS))
BACKUP_SKIP_FILES = frozenset(name.rsplit("/", 1)[-1] for name in (BOT_DB, RENDER_LOCK))
# קובצי ה-JSON שהאבחון בודק, איפה שהם נמצאים (בנוסף לכל *.json בשורש data/)
CHECKED_JSON = (CONFIG, ROCKET_SETTINGS, EXPORT_SETTINGS, REMOTE_ACCESS, SCHEDULED_TASKS, PAIRED_DEVICES, SCHEDULER_STATE,
                EDITOR_PROFILES, EDITOR_PROFILE_META, EDITOR_PROFILE_HISTORY, DATAVIZ_HIDDEN, DATAVIZ_TAGS, DATAVIZ_KITS)


def folder_of(name: str) -> Optional[str]:
    """התיקייה ששם בשורש data/ עובר אליה (גם <שם>.bak ו-<db>-wal), או None - נשאר בשורש."""
    if name in FOLDERS:
        return FOLDERS[name]
    for suffix in _COMPANION_SUFFIXES:
        if name.endswith(suffix) and name[:-len(suffix)] in FOLDERS:
            return FOLDERS[name[:-len(suffix)]]
    return None


def migrated(data_dir: Optional[str] = None) -> bool:
    """האם הקבצים ב-data_dir כבר הועברו לתיקיות לפי נושא (dev/migrate_data_layout.py --apply כתב את הסימן)."""
    return os.path.isfile(os.path.join(data_dir or DATA_DIR, LAYOUT_MARKER))


def path(name: str, data_dir: Optional[str] = None) -> str:
    """הנתיב המלא של שם מכאן, תחת data/ (או תחת data_dir אחר - טסטים, עורך הגרפים). אחרי ההעברה: <תיקייה>/<שם>,
    אלא אם השם קיים רק במקום השטוח. BOT_DB שעוד לא הועבר מהשם הישן = הקובץ הישן."""
    base = data_dir or DATA_DIR
    full = _layout_path(name, base)
    if name == BOT_DB and not os.path.exists(full):
        return _legacy_bot_db((os.path.dirname(full), base)) or full
    return full


def is_legacy_bot_db(name: str) -> bool:
    """האם name (שם קובץ, בלי תיקייה) הוא השם הישן של ה-DB."""
    return hashlib.sha256(name.encode("utf-8")).digest() == LEGACY_BOT_DB_SHA256


def _legacy_bot_db(folders: Iterable[str]) -> Optional[str]:
    for folder in folders:
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            if name.endswith(".db") and is_legacy_bot_db(name):
                return os.path.join(folder, name)
    return None


def migrate_bot_db(data_dir: Optional[str] = None) -> Optional[str]:
    """מעביר את ה-DB מהשם הישן ל-BOT_DB, פעם אחת: גיבוי ל-DB_RENAME_BACKUP, checkpoint של ה-WAL, ואז rename - אטומי,
    כך שהשם הישן נעלם רק כשההעברה הצליחה. כל כישלון (הקובץ פתוח בתהליך אחר, הגיבוי נכשל) משאיר את הישן כמו שהוא, וההפעלה
    הבאה מנסה שוב. מחזיר את הנתיב החדש אם הועבר עכשיו, אחרת None."""
    base = data_dir or DATA_DIR
    target = _layout_path(BOT_DB, base)
    if os.path.exists(target):
        return None
    legacy = _legacy_bot_db((os.path.dirname(target), base))
    if not legacy:
        return None
    try:
        backup = os.path.join(base, *DB_RENAME_BACKUP.split("/"))
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        src = sqlite3.connect(legacy)
        try:
            dest = sqlite3.connect(backup)
            with dest:
                src.backup(dest)
            dest.close()
            src.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            src.close()
        # אחרי checkpoint וסגירת החיבור האחרון SQLite מוחק את ה-WAL. אם הוא עוד שם עם תוכן - תהליך אחר פתוח עליו
        if os.path.exists(legacy + "-wal") and os.path.getsize(legacy + "-wal"):
            return None
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.rename(legacy, target)
    except (OSError, sqlite3.Error):
        return None
    for suffix in ("-wal", "-shm"):   # ריקים בשלב הזה - רק כדי שלא יישארו ליד השם הישן
        if os.path.exists(legacy + suffix):
            try:
                os.remove(legacy + suffix)  # safe: an empty SQLite side file of the old name, after its DB moved to BOT_DB
            except OSError:
                pass
    return target


def _layout_path(name: str, base: str) -> str:
    parts = name.split("/")
    flat = os.path.join(base, *parts)
    folder = folder_of(parts[0])
    if not folder or not migrated(base):
        return flat
    moved = os.path.join(base, folder, *parts)
    return flat if os.path.exists(flat) and not os.path.exists(moved) else moved


def adopt_layout_if_new(data_dir: Optional[str] = None) -> bool:
    """30.10.2026: התקנה חדשה מתחילה ישר בתיקיות לפי נושא. אם אין ב-data_dir שום שם שעובר לתיקייה (גם לא <שם>.bak,
    ‏-wal וכו', וגם לא ה-DB בשם הישן) - אין מה להעביר, וכותבים את LAYOUT_MARKER. מחזיר True אם נכתב עכשיו."""
    base = data_dir or DATA_DIR
    if migrated(base):
        return False
    try:
        names = os.listdir(base)
    except FileNotFoundError:
        names = []
    if any(folder_of(name) for name in names) or _legacy_bot_db((base,)):
        return False
    ensure_folders(base)
    with open(os.path.join(base, LAYOUT_MARKER), "w", encoding="utf-8") as f:
        f.write("2\n")   # כמו dev/migrate_data_layout.py --apply
    return True


def ensure_folders(data_dir: Optional[str] = None) -> None:
    """כל תיקיות הנושא (FOLDERS) קיימות. path() לא יוצר תיקיות, והכותבים פותחים את הקובץ ישירות - בלי זה התקנה חדשה
    קרסה על data/security/web_app_token.txt (30.10.2026)."""
    base = data_dir or DATA_DIR
    for folder in sorted(set(FOLDERS.values())):
        os.makedirs(os.path.join(base, folder), exist_ok=True)


def dataviz_root(data_dir: Optional[str] = None) -> str:
    """ה-data_dir של עורך הגרפים: data/ במבנה השטוח, data/dataviz/ אחרי ההעברה. השמות DATAVIZ_* יחסיים אליו, כמו קודם -
    וגם "שתי רמות מעל תיקיית הפרק" (dataviz_episodes/<פרק>) מגיע אליו בשני המבנים."""
    base = data_dir or DATA_DIR
    return os.path.join(base, DATAVIZ_FOLDER) if migrated(base) else base


def localize(rel: str, data_dir: Optional[str] = None) -> str:
    """שם יחסי מגיבוי (שטוח או לפי נושא, עם "/" או "\\") -> השם היחסי שלו במבנה של data_dir עכשיו. ככה גיבוי ישן משוחזר
    לתיקיות אחרי ההעברה, וגיבוי חדש משוחזר שטוח לפניה."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if parts and is_legacy_bot_db(parts[-1]):
        parts[-1] = BOT_DB   # גיבוי מלפני שינוי השם של ה-DB - משוחזר בשם החדש
    if len(parts) > 1 and folder_of(parts[1]) == parts[0]:
        parts = parts[1:]
    folder = folder_of(parts[0]) if parts else None
    if folder and migrated(data_dir):
        parts = [folder] + parts
    return "/".join(parts)


def relative(full_path: str, data_dir: Optional[str] = None) -> str:
    """ההפך: הנתיב יחסית ל-data/, עם "/" - כדי להשוות לשמות כאן."""
    return os.path.relpath(full_path, data_dir or DATA_DIR).replace(os.sep, "/")


# ההעברה מהשם הישן של ה-DB - בייבוא הראשון בכל תהליך, לפני שמודול כלשהו מחשב DB_PATH מ-path(BOT_DB). כישלון לא עוצר ייבוא
try:
    migrate_bot_db()
except Exception as _e:   # noqa: BLE001 - ייבוא של data_paths לעולם לא נכשל בגלל ההעברה; path() ממשיך לקרוא את הקובץ הישן
    print(f"[data_paths] העברת ה-DB לשם {BOT_DB} נכשלה, ממשיכים עם השם הישן: {_e}")

# data/ חדשה (החבילה הניידת בהפעלה הראשונה, clone טרי) - ישר בתיקיות לפי נושא, באותו רגע שבו נקבע המבנה לכל המודולים.
# CLIPFORGE_DATA_DIR (טסטים, שרת בדיקה) נשאר במבנה שהקורא בחר
if not os.environ.get("CLIPFORGE_DATA_DIR"):
    try:
        adopt_layout_if_new()
    except OSError as _e:
        print(f"[data_paths] לא הצלחתי לסמן את {DATA_DIR} כמבנה לפי נושא, ממשיכים במבנה השטוח: {_e}")
# במבנה לפי נושא - כל התיקיות קיימות (גם אחרי dev/migrate_data_layout.py, שיוצר רק תיקיות שעבר אליהן קובץ, או תיקייה שנמחקה)
if migrated():
    try:
        ensure_folders()
    except OSError as _e:
        print(f"[data_paths] לא הצלחתי ליצור את תיקיות הנושא תחת {DATA_DIR}: {_e}")
