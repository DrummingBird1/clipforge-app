# utils/shared/diagnostics.py
#
# בדיקת תקינות מרוכזת - כמעט כל באג אמיתי שנתקלנו בו החודש היה כשל שקט
# (פרשן Python לא נמצא, ffprobe חסר, תיקייה לא נבחרה) שהתגלה רק אחרי שמישהו
# לחץ הרץ וקיבל תוצאה מבלבלת בלי הסבר. כאן אפשר לבדוק הכל מראש ולקבל רשימה
# ברורה של מה תקין ומה לא - נפרד מה-GUI (בלי תלות ב-tkinter) כדי שיהיה קל
# לבדוק את הלוגיקה עצמה.
import glob
import json
import os
import py_compile
import shutil
import tempfile

try:
    import psutil
except ImportError:
    psutil = None

from utils.shared import db
from utils.shared.data_dir import DATA_DIR
from utils.shared.credential_health import check_configured as check_credentials_configured
from utils.shared.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
from utils.shared.python_locator import get_python_executable
from utils.shared.render_lock import get_status as get_render_lock_status
from utils.shared.i18n import t
from utils.shared import data_paths

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DB_PATH = data_paths.path(data_paths.BOT_DB)
SCRIPTS_DIR = os.path.join(BASE_DIR, "my_scripts")
# סבב ייצוב: אותו workspace שהשרת כותב אליו (CLIPFORGE_WORKSPACE_DIR, כמו web_app.WORKSPACE_DIR)
WORKSPACE_DIR = os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(BASE_DIR, "workspace")


def _is_runnable(exe_path):
    """exe_path יכול להיות נתיב מוחלט קיים (הגרסה המצורפת) או שם פקודה גולמי
    שתלוי ב-PATH (fallback) - ראו utils/shared/ffmpeg_locator.py."""
    return os.path.isabs(exe_path) and os.path.exists(exe_path) or bool(shutil.which(exe_path))


def _check_ffmpeg():
    exe = get_ffmpeg_exe()
    ok = _is_runnable(exe)
    return ("FFmpeg", ok, exe if ok else t("לא נמצא (חיפש: {exe})", exe=exe))


def _check_ffprobe():
    exe = get_ffprobe_exe()
    ok = _is_runnable(exe)
    return ("FFprobe", ok, exe if ok else t("לא נמצא (חיפש: {exe})", exe=exe))


def _check_python_interpreter():
    exe = get_python_executable()
    ok = bool(exe)
    detail = exe if ok else t("לא נמצא Python גלובלי - הרצת סקריפטים תיכשל (רלוונטי בעיקר לגרסה הארוזה/exe)")
    # _fix_word_order=False על ה"שם" (לא על detail) - השם הזה מוצג תמיד ביחד
    # עם אייקון ✅/❌ (ב-gui_manager.pyw), לא לבד. אם היה מתוקן כאן וגם על
    # המחרוזת המשולבת שם, זה הופך פעמיים ולא מתקן שום דבר.
    return (t("פרשן Python להרצת סקריפטים", _fix_word_order=False), ok, detail)


def _check_database():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with db.connect(DB_PATH) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _diagnostics_check (id INTEGER PRIMARY KEY)")
        return (t("מסד נתונים (clipforge_data.db)", _fix_word_order=False), True, DB_PATH)
    except Exception as e:
        return (t("מסד נתונים (clipforge_data.db)", _fix_word_order=False), False, str(e))


def _check_scripts_syntax():
    scripts = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "**", "*.py"), recursive=True))
    broken = []
    with tempfile.TemporaryDirectory() as tmp_cache:
        for path in scripts:
            cache_path = os.path.join(tmp_cache, os.path.basename(path) + ".pyc")
            try:
                py_compile.compile(path, cfile=cache_path, doraise=True)
            except py_compile.PyCompileError as e:
                broken.append(f"{os.path.relpath(path, BASE_DIR)}: {e.msg}")
    ok = not broken
    detail = t("{n} סקריפטים נבדקו", n=len(scripts)) if ok else "; ".join(broken)
    return (t("תקינות תחבירית של my_scripts ({n} קבצים)", n=len(scripts), _fix_word_order=False), ok, detail)


def _check_disk_space():
    try:
        _, _, free = shutil.disk_usage(BASE_DIR)
        free_gb = free / (1024**3)
        ok = free_gb > 2
        return (t("שטח פנוי בכונן הפרויקט", _fix_word_order=False), ok, t("{gb} GB פנויים", gb=f"{free_gb:.1f}"))
    except Exception as e:
        return (t("שטח פנוי בכונן הפרויקט", _fix_word_order=False), False, str(e))


def _check_workspace():
    """workspace/ (vertical/horizontal/square/clips/imports וכו', ראו README) -
    נוצר אוטומטית ע"י כל סקריפט בהרצה הראשונה שלו, אבל אם הוא כבר קיים עם
    הרשאות שגויות (למשל תיקייה לקריאה-בלבד) עדיף לגלות את זה כאן, לא באמצע רינדור."""
    try:
        os.makedirs(WORKSPACE_DIR, exist_ok=True)
        probe_path = os.path.join(WORKSPACE_DIR, ".diagnostics_write_probe")
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe_path)
        return (t("תיקיית workspace/ (קליפים/תוצרים)", _fix_word_order=False), True, WORKSPACE_DIR)
    except Exception as e:
        return (t("תיקיית workspace/ (קליפים/תוצרים)", _fix_word_order=False), False, str(e))


def _check_render_lock():
    """מנעול הרינדור החוצה-תהליכים (utils/shared/render_lock.py) - תפוס-אבל-בריא הוא
    מצב תקין לגמרי (רינדור אמיתי רץ כרגע), רק "תקוע" (is_stale) נחשב כשל -
    ראו ui/dashboard.py/status_cog.py/web_app.py לאותו מידע בדיוק במקומות אחרים."""
    status = get_render_lock_status()
    name = t("מנעול רינדור חוצה-תהליכים", _fix_word_order=False)
    if status is None:
        return (name, True, t("פנוי"))
    if status["is_stale"]:
        return (name, False, t("תקוע (PID {pid}) - ישוחרר אוטומטית בניסיון התפיסה הבא", pid=status["pid"]))
    return (name, True, t("תפוס כרגע (PID {pid}) - רינדור אחר פעיל", pid=status["pid"]))


def _check_orphaned_ffmpeg_processes():
    """מאתר תהליכי ffmpeg/ffprobe שההורה שלהם כבר לא רץ (item: system health
    dashboard) - קרה בפועל בסשן הזה: תהליך הורה שנהרג בטעות, וה-ffmpeg שלו
    נשאר רץ ומקודד לבד, בלי ששום כלי בפרויקט מודע אליו יותר (render_lock
    כבר לא שומר עליו). לא בהכרח תקלה - יכול להיות רינדור לגיטימי ממשיך
    לעבוד - אבל בדיוק המצב הזה גרם לבלבול אמיתי פעם, אז שווה להראות במפורש
    במקום להשאיר אותו שקוף."""
    name = t("תהליכי ffmpeg/ffprobe יתומים", _fix_word_order=False)
    if psutil is None:
        return (name, True, t("psutil לא מותקן - הבדיקה מדולגת"))
    orphaned = []
    try:
        # סבב ייצוב: קודם השם (כמעט חינם), ו-ppid רק ל-ffmpeg/ffprobe. ב-Windows כל ppid() בונה מפה של כל התהליכים
        # (~16ms) - process_iter עם "ppid" לכל ~700 התהליכים לקח 11-17 שניות, וחלון הבדיקה חיכה להם
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() not in ("ffmpeg.exe", "ffprobe.exe"):
                continue
            try:
                ppid = proc.ppid()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if not ppid or not psutil.pid_exists(ppid):
                orphaned.append(proc.pid)
    except Exception as e:
        return (name, False, t("הבדיקה נכשלה: {error}", error=e))
    if not orphaned:
        return (name, True, t("אין תהליכי ffmpeg/ffprobe יתומים"))
    pids_text = ", ".join(str(p) for p in orphaned)
    return (
        name, False,
        t("{n} תהליכים יתומים רצים (PIDs: {pids}) - כנראה תהליך הורה שנסגר/קרס בזמן שה-ffmpeg עדיין רץ", n=len(orphaned), pids=pids_text),
    )


def _check_credentials_configured():
    """נוכחות בלבד (item: credential vault health-check) - לא תוקף בפועל
    (זה דורש קריאות רשת אמיתיות ל-API חיצוני, ראו utils/shared/credential_health.py's
    check_validity() - מופעל רק על-פי-בקשה מפורשת, לא כאן). "לא מוגדר" הוא
    מצב לגיטימי (למשל אין צורך ב-GEMINI_API_KEY אם לא משתמשים בזיהוי AI
    בכלל) ולא נחשב כשל - ok=True תמיד, זו תצוגה בלבד."""
    name = t("Credentials מוגדרים (Gemini/Twitch/Discord)", _fix_word_order=False)
    configured = check_credentials_configured()
    parts = []
    for key, is_set in configured.items():
        icon = "✅" if is_set else "➖"
        parts.append(f"{icon} {key}")
    return (name, True, " · ".join(parts))


def _check_gemini_key():
    """מפתח Gemini חסר אינו שגיאה קטלנית (הכל ממשיך לעבוד עם נפילה לתבנית/שיפוט מקומי), אבל זה
    בדיוק מה שגורם ל"למה אין כותרות AI?" - לכן כאן זה מוצג בבירור כאזהרה, לא רק כ-➖ בשורת ה-credentials."""
    name = t("מפתח Gemini API", _fix_word_order=False)
    if check_credentials_configured().get("GEMINI_API_KEY"):
        return (name, True, t("מוגדר"))
    return (name, False, t("חסר - זיהוי AI של קליפים, כותרות ו-SEO יעבדו רק בתבנית/שיפוט מקומי. הגדר GEMINI_API_KEY ב-.env או ב-Credential Manager"))


def _check_data_json_files():
    """קורא (לקריאה בלבד - אף פעם לא כותב/מתקן ב-data/) כל קובץ JSON ישיר ב-data/ ומוודא שהוא JSON תקין
    עם מילון/רשימה ברמה העליונה. קובץ פגום הוא הסיבה הנפוצה ל"ההגדרות שלי נעלמו" אחרי כיבוי באמצע כתיבה.
    23.10.2026: גם קובצי ההגדרות המוכרים (data_paths.CHECKED_JSON) איפה שהם - כשיעברו לתיקיות לפי נושא, הבדיקה לא
    תהפוך ל"0 קבצים, תקין"."""
    name = t("קובצי הנתונים ב-data/ (JSON)", _fix_word_order=False)
    if not os.path.isdir(DATA_DIR):
        return (name, True, t("תיקיית data/ עוד לא נוצרה - תיווצר בהרצה הראשונה"))
    broken, checked = [], 0
    known = [data_paths.path(json_name, DATA_DIR) for json_name in data_paths.CHECKED_JSON]
    paths = {os.path.normcase(p): p for p in glob.glob(os.path.join(DATA_DIR, "*.json")) + [p for p in known if os.path.isfile(p)]}
    for path in sorted(paths.values()):
        checked += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, (dict, list)):
                broken.append(f"{os.path.basename(path)}: {t('מבנה לא צפוי')}")
        except (OSError, ValueError) as e:
            broken.append(f"{os.path.basename(path)}: {e}")
    if broken:
        return (name, False, t("קבצים פגומים (לא שונו): {files}", files="; ".join(broken)))
    return (name, True, t("{n} קבצים תקינים", n=checked))


STARTUP_CHECKS = (
    "_check_ffmpeg", "_check_ffprobe", "_check_disk_space", "_check_workspace",
    "_check_data_json_files", "_check_gemini_key",
)


def startup_problems():
    """בדיקות מהירות להפעלת השרת (בלי py_compile של כל הסקריפטים, בלי רשת ובלי כתיבה ל-data/ - לכן גם בלי _check_database): רשימת שורות אזהרה בעברית,
    ריקה = הכל תקין. כשל בבדיקה עצמה נספר כבעיה ולא מפיל את ההפעלה."""
    problems = []
    for check_name in STARTUP_CHECKS:
        check = globals()[check_name]
        try:
            name, ok, detail = check()
        except Exception as e:
            problems.append(f"⚠️ {check_name}: {t('הבדיקה עצמה נכשלה: {error}', error=e)}")
            continue
        if not ok:
            problems.append(f"⚠️ {name}: {detail}")
    return problems


def print_startup_health(print_fn=print):
    """מדפיס את תוצאות startup_problems() - שורה ירוקה אחת כשהכל תקין, אחרת שורה לכל בעיה. מחזיר את הרשימה."""
    problems = startup_problems()
    if not problems:
        print_fn(t("✅ בדיקת תקינות בהפעלה: ffmpeg, מפתח Gemini, שטח בדיסק וקובצי data/ תקינים"))
    else:
        print_fn(t("בדיקת תקינות בהפעלה - נמצאו {n} בעיות:", n=len(problems)))
        for line in problems:
            print_fn("   " + line)
    return problems


def _check_wake_timers():
    """הערת המחשב למשימות מתוזמנות (utils/bot/wake_timer.py): מצב ההגדרה, המועד הרשום, ו-'Allow wake timers' בתוכנית
    החשמל של Windows (powercfg /query - קריאה בלבד). כבוי = תקין. powercfg /waketimers דורש הרשאות מנהל - מוזכר רק כשזמין."""
    from utils.bot import wake_timer
    name = t("הערת המחשב למשימות מתוזמנות", _fix_word_order=False)
    state = wake_timer.load_state()
    if not state["enabled"]:
        return (name, True, t("כבוי (מופעל במסך המשימות המתוזמנות)"))
    allows = wake_timer.windows_allows_wake_timers()
    if allows is False:
        return (name, False, t("מופעל, אבל 'Allow wake timers' כבוי בתוכנית החשמל של Windows - המחשב לא יתעורר"))
    if state["error"]:
        return (name, False, t("הרישום ב-Task Scheduler נכשל: {error}", error=state["error"]))
    timers = wake_timer.current_wake_timers()
    windows_view = "" if "administrator" in timers.lower() or not timers else " | powercfg /waketimers: " + " ".join(timers.split())[:200]
    if state["wake_at"]:
        return (name, True, t("מעיר ב-{time} ({task})", time=state["wake_at"].replace("T", " "), task=wake_timer.TASK_NAME) + windows_view)
    return (name, True, t("מופעל - אין כרגע משימה קרובה") + windows_view)


def run_diagnostics():
    """מריץ את כל הבדיקות ומחזיר רשימת (שם_בדיקה, תקין: bool, פרטים)."""
    checks = [
        _check_ffmpeg,
        _check_ffprobe,
        _check_python_interpreter,
        _check_database,
        _check_scripts_syntax,
        _check_disk_space,
        _check_workspace,
        _check_render_lock,
        _check_orphaned_ffmpeg_processes,
        _check_credentials_configured,
        _check_gemini_key,
        _check_data_json_files,
        _check_wake_timers,
    ]
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            results.append((check.__name__, False, t("הבדיקה עצמה נכשלה: {error}", error=e)))
    return results
