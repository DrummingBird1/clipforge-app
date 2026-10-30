# cogs/scheduler_cog.py
#
# מריץ אוטומטית, פעם ביום בשעה קבועה, שני סקריפטים שעד כה חייבו הפעלה ידנית:
# ניקוי מקורות ישנים (my_scripts/video/cleanup_published_sources.py) וריקאפ
# שבועי (my_scripts/video/weekly_compilation.py). שני הסקריפטים האלה כבר בנויים
# להיות בטוחים להרצה חוזרת בלי לפגוע בכלום - cleanup רק מזיז קבצים ישנים+שכבר
# פורסמו, ו-weekly_compilation מדלג בשקט אם אין קליפים חדשים. מה שהיה חסר זה
# רק "מישהו שיריץ אותם" בלי שהמשתמש יזכור לעשות את זה ידנית.

import datetime
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time as time_module
import zipfile

from utils.media.compilation import should_run_recap_today
from utils.shared.ffmpeg_locator import get_ffmpeg_exe
from utils.shared.render_lock import get_status as get_render_lock_status
from utils.shared.render_lock import render_lock
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

from discord.ext import commands, tasks

from utils.shared import job_history
from utils.shared.data_dir import DATA_DIR
from utils.shared.log_cleanup import purge_old_log_backups
from utils.shared import data_paths

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(BASE_DIR, "my_scripts")
SETTINGS_PATH = data_paths.path(data_paths.ROCKET_SETTINGS)
SCHEDULER_STATE_PATH = data_paths.path(data_paths.SCHEDULER_STATE)
DB_PATH = data_paths.path(data_paths.BOT_DB)
BACKUPS_DIR = data_paths.path(data_paths.BACKUPS)
DB_BACKUPS_TO_KEEP = 7
DATA_SNAPSHOTS_TO_KEEP = 7
# מוחרגים מגיבוי ה-zip הכללי: backups/logs (רקורסיה על הגיבויים עצמם / קבצי לוג
# שאינם קריטיים לשחזור מצב), ו-render.lock (מנעול ריצה זמני - ראו utils/shared/render_lock.py)
_DATA_BACKUP_EXCLUDE_DIRNAMES = data_paths.BACKUP_SKIP_DIRS      # לפי שם, בכל עומק (utils/shared/data_paths.py)
_DATA_BACKUP_EXCLUDE_FILENAMES = data_paths.BACKUP_SKIP_FILES

# שעה שקטה - מחוץ לשעות עבודה טיפוסיות. 30.10.2026: בשעון המקומי של המחשב - discord.py מתייחס לשעה בלי אזור זמן כ-UTC,
# כך שבאמריקה התחזוקה רצה בערב. ההיסט נקבע בהפעלת הבוט (מעבר שעון קיץ נכנס בהפעלה הבאה)
DAILY_RUN_TIME = datetime.time(hour=4, minute=0, tzinfo=datetime.datetime.now().astimezone().tzinfo)

# סף גבוה בהרבה מהסף הקשיח ב-utils/shared/disk_space.py (2GB) - זו התרעה מוקדמת,
# יזומה, כדי לתת התראה לפני שרינדורים בכלל מתחילים להיכשל.
LOW_DISK_SPACE_WARNING_GB = 10

# item: התראה יזומה אם render_lock נשאר תפוס מעבר לזמן סביר - נמוך בהרבה
# מ-MAX_LOCK_AGE_SECONDS (4 שעות, utils/shared/render_lock.py) שבו המנעול מתאושש
# אוטומטית: זו התרעה *מוקדמת*, לא רק הד לאותו סף - נותנת סיכוי אמיתי לבדוק
# מה קורה לפני שהמערכת בכלל מגיעה לנקודת ההתאוששות האוטומטית.
RENDER_LOCK_STUCK_WARNING_SECONDS = 45 * 60


def _load_settings():
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _load_scheduler_state():
    if os.path.exists(SCHEDULER_STATE_PATH):
        try:
            with open(SCHEDULER_STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_scheduler_state(state):
    try:
        with open(SCHEDULER_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[scheduler] שגיאה בשמירת מצב התזמון: {e}")


def _run_script_blocking(script_relpath, extra_args=None, timeout=3600, record_history=True):
    """מריץ סקריפט כתת-תהליך חוסם - נקרא דרך run_in_executor כדי לא לתקוע את
    לולאת האירועים של הבוט (רינדור/דחיסה יכולים לקחת דקות ארוכות). extra_args
    (item: ריקאפ תקופתי) מתווסף לשורת הפקודה - ברירת מחדל None (=[]) זהה
    להתנהגות הקודמת בדיוק. timeout/record_history (item: רינדור-קנרית מתוזמן) -
    קליפ בדיקה סינתטי זעיר אמור להיכשל/להצליח תוך שניות, לא לחכות עד שעה
    שלמה כמו רינדור אמיתי; וגם לא אמור להיספר ב-job_history (סטטיסטיקות זמן-
    רינדור אמיתיות, לא קליפ סינתטי בן 2 שניות שירוץ כל לילה)."""
    script_path = os.path.join(SCRIPTS_DIR, script_relpath)
    script_name = os.path.basename(script_relpath)
    started_at = datetime.datetime.now().isoformat()
    t0 = time_module.time()
    try:
        # מנעול חוצה-תהליכים משותף עם ה-GUI (utils/shared/render_lock.py) - מונע
        # מהתחזוקה האוטומטית הזו להתנגש עם רינדור כבד שרץ באותו רגע דרך ה-GUI.
        with render_lock():
            # encoding="utf-8" מפורש (לא ברירת המחדל של text=True - קידוד
            # ה-locale של המערכת, למשל cp1255 בווינדוס עברי) - תת-התהליך
            # (video_editor.py וכו') כבר עושה sys.stdout.reconfigure(encoding=
            # "utf-8") בעצמו; בלי זה, תו כלשהו ב-stdout/stderr שלו שלא קיים
            # ב-cp1255 מפיל UnicodeDecodeError ב-thread-הקורא הפנימי של
            # subprocess (נמצא תוך כדי בדיקה אמיתית של רינדור-הקנרית).
            # errors="replace" - עדיף tail עם תו-שגיאה בודד מאשר קריסה על עצם
            # קריאת הפלט, כשהמטרה כאן היא רק log tail לאבחון, לא פלט מדויק.
            result = subprocess.run(
                [sys.executable, "-u", script_path, *(extra_args or [])],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, creationflags=NO_WINDOW_FLAGS
            )
        status = "success" if result.returncode == 0 else "failed"
        tail = ((result.stdout or "") + (result.stderr or ""))[-1500:]
    except Exception as e:
        status = "failed"
        tail = str(e)
    duration = time_module.time() - t0
    finished_at = datetime.datetime.now().isoformat()

    if record_history:
        try:
            job_history.record_job(f"[תזמון אוטומטי] {script_name}", status, started_at, finished_at, duration)
        except Exception as e:
            print(f"[scheduler] שגיאה ברישום job_history: {e}")

    return status, tail


def _get_free_disk_gb():
    """שטח פנוי בכונן הפרויקט (GB) - פונקציה נפרדת כדי שאפשר יהיה לבודד אותה
    בטסט (monkeypatch) בלי תלות אמיתית בכמות השטח הפנוי בפועל על המכונה."""
    _total, _used, free = shutil.disk_usage(BASE_DIR)
    return free / (1024 ** 3)


def _make_canary_clip(path):
    """קליפ סינתטי זעיר (ffmpeg lavfi testsrc, 2 שניות, 320x240) - אותו דפוס
    בדיוק כמו tests/*_e2e.py's _make_synthetic_video, אבל כאן לא לצורך טסט
    אלא לבדיקת-אמת יומית שה-ffmpeg/תלויות האמיתיים על המכונה הזאת עדיין
    עובדים. מחזיר True/False - לא זורק, קורא אחראי לפרש כישלון."""
    cmd = [
        get_ffmpeg_exe(), "-y", "-f", "lavfi",
        "-i", "testsrc=duration=2:size=320x240:rate=10",
        "-pix_fmt", "yuv420p", path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW_FLAGS)
        return result.returncode == 0
    except Exception:
        return False


def _run_canary_render():
    """item: "רינדור-קנרית" מתוזמן - יוצר קליפ סינתטי זעיר ומריץ אותו דרך
    video_editor.py האמיתי (--codec h264, לא NVENC - נבדק על כל מכונה בלי
    תלות בכרטיס מסך זמין), כדי לתפוס תקלת ffmpeg/תלות (עדכון שבר משהו, קובץ
    חסר וכו') לפני שמישהו מנסה רינדור אמיתי ומגלה שזה שבור. מחזיר (success,
    error_tail); תיקיית הבדיקה הזמנית תמיד מנוקה, בהצלחה ובכישלון כאחד."""
    with tempfile.TemporaryDirectory(prefix="clipforge_canary_") as tmp_dir:
        clip_path = os.path.join(tmp_dir, "canary.mp4")
        if not _make_canary_clip(clip_path):
            return False, "יצירת קליפ הבדיקה הסינתטי נכשלה (ffmpeg testsrc)."

        status, tail = _run_script_blocking(
            os.path.join("video", "video_editor.py"),
            ["--input_dir", tmp_dir, "--codec", "h264", "--no-suffix"],
            timeout=120, record_history=False,
        )
        return status == "success", tail


# גיבויים יומיים בשם <שם ה-DB>_<תאריך>.db. גיבויים בשם הקודם (לפני 30.10.2026) נשארים ולא נמחקים בסבב
_DB_BACKUP_STEM = os.path.splitext(data_paths.BOT_DB)[0]


def _backup_database():
    """גיבוי בטוח של ה-DB המשותף (data_paths.BOT_DB) דרך ה-Backup API המובנה של sqlite3 (לא סתם
    העתקת קובץ - ככה גם קובץ שנפתח כרגע לכתיבה מגובה בעקביות, בלי לסכן קובץ חצי-כתוב).
    utils/shared/backup_sync.py הקיים מגבה רק את תיקיית ה-exports (מדיה) - את ה-DB עצמו
    (היסטוריית ריצות, פידי RSS, מעקב Steam) לא גיבה עד כה אף מנגנון.
    מחזיר (success, error_message) - כדי שהקורא יוכל להתריע לבעל הבוט על כישלון
    במקום רק להדפיס ללוג (ראו _notify_owner)."""
    if not os.path.exists(DB_PATH):
        return True, None
    try:
        os.makedirs(BACKUPS_DIR, exist_ok=True)
        dest_path = os.path.join(BACKUPS_DIR, f"{_DB_BACKUP_STEM}_{datetime.date.today().isoformat()}.db")
        src_conn = sqlite3.connect(DB_PATH)
        dest_conn = sqlite3.connect(dest_path)
        with dest_conn:
            src_conn.backup(dest_conn)
        src_conn.close()
        dest_conn.close()

        old_backups = sorted(glob.glob(os.path.join(BACKUPS_DIR, f"{_DB_BACKUP_STEM}_*.db")))
        for old_path in old_backups[:-DB_BACKUPS_TO_KEEP]:
            try:
                os.remove(old_path)
            except Exception:
                pass
        return True, None
    except Exception as e:
        print(f"[scheduler] גיבוי בסיס הנתונים נכשל: {e}")
        return False, str(e)


def _backup_data_directory():
    """מגבה zip של כל תיקיית data/ (הגדרות, מונים, מצב תזמון וכו') - לא רק ה-DB
    (שכבר מגובה בנפרד ב-_backup_database, ולכן מוחרג כאן כדי לא לכפול). לפני
    התוספת הזו רק ה-DB היה מגובה אוטומטית - קובצי הגדרות/מצב אחרים היו אובדים
    לגמרי בתקלת דיסק. מחזיר (success, error_message) כמו _backup_database."""
    if not os.path.isdir(DATA_DIR):
        return True, None
    try:
        os.makedirs(BACKUPS_DIR, exist_ok=True)
        dest_path = os.path.join(BACKUPS_DIR, f"data_snapshot_{datetime.date.today().isoformat()}.zip")
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(DATA_DIR):
                dirs[:] = [d for d in dirs if d not in _DATA_BACKUP_EXCLUDE_DIRNAMES]
                for filename in files:
                    if filename in _DATA_BACKUP_EXCLUDE_FILENAMES:
                        continue
                    full_path = os.path.join(root, filename)
                    zf.write(full_path, os.path.relpath(full_path, DATA_DIR))

        old_snapshots = sorted(glob.glob(os.path.join(BACKUPS_DIR, "data_snapshot_*.zip")))
        for old_path in old_snapshots[:-DATA_SNAPSHOTS_TO_KEEP]:
            try:
                os.remove(old_path)
            except Exception:
                pass
        return True, None
    except Exception as e:
        print(f"[scheduler] גיבוי תיקיית data/ נכשל: {e}")
        return False, str(e)


async def _notify_owner(bot, message):
    """שולח הודעה פרטית (DM) לבעל הבוט - כדי שכישלון בתחזוקה אוטומטית (גיבוי/ניקוי/
    ריקאפ) לא יישאר "שקט" (רק שורה בלוג שאף אחד לא בהכרח קורא) אלא יגיע בפועל
    למישהו. DM ולא ערוץ ייעודי - כדי לא לדרוש הגדרה נוספת (channel ID) שאין לה
    היום מקום טבעי בהגדרות; הבוט כבר owner-only בכל הפקודות הרגישות."""
    try:
        app_info = await bot.application_info()
        if app_info.owner:
            await app_info.owner.send(message)
    except Exception as e:
        print(f"[scheduler] שגיאה בשליחת התראה לבעל הבוט: {e}")


class SchedulerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_maintenance.start()
        self.check_stuck_render_lock.start()

    def cog_unload(self):
        self.daily_maintenance.cancel()
        self.check_stuck_render_lock.cancel()

    @tasks.loop(minutes=15)
    async def check_stuck_render_lock(self):
        """item: התראה יזומה אם render_lock נשאר תפוס מעבר לזמן סביר - בדיקה
        תכופה בהרבה מ-daily_maintenance (שרצה פעם ביום בלבד, לא מתאים לתפוס
        מנעול שנתקע באמצע היום). דה-דופ לפי acquired_at של המנעול עצמו (לא
        תאריך, כמו שאר ההתראות כאן) - כך שכל תפיסת-מנעול חדשה (acquired_at
        שונה) יכולה להתריע מחדש, אבל אותה תפיסה תקועה לא מציפה בהודעות חוזרות
        כל 15 דקות."""
        status = get_render_lock_status()
        if status is None or status["age_seconds"] is None or status["age_seconds"] < RENDER_LOCK_STUCK_WARNING_SECONDS:
            return
        state = _load_scheduler_state()
        acquired_at_key = str(status["acquired_at"])
        if state.get("last_render_lock_warning_acquired_at") == acquired_at_key:
            return
        state["last_render_lock_warning_acquired_at"] = acquired_at_key
        _save_scheduler_state(state)
        age_minutes = status["age_seconds"] / 60
        await _notify_owner(
            self.bot,
            f"⚠️ **מנעול הרינדור תפוס כבר {age_minutes:.0f} דקות** (PID {status['pid']}). "
            "יכול להיות רינדור ארוך לגיטימי - או תהליך שנתקע. שווה לבדוק."
        )

    @tasks.loop(time=DAILY_RUN_TIME)
    async def daily_maintenance(self):
        settings = _load_settings()
        state = _load_scheduler_state()
        today_str = datetime.date.today().isoformat()

        # התראה מוקדמת על שטח דיסק נמוך - נפרד מ-utils/shared/disk_space.py (שחוסם
        # רינדור ספציפי לפני שהוא מתחיל); זו התרעה יזומה, פעם ביום, לפני
        # שהמצב בכלל מגיע לנקודה שרינדורים מתחילים להיכשל.
        try:
            free_gb = _get_free_disk_gb()
            if free_gb < LOW_DISK_SPACE_WARNING_GB and state.get("last_low_disk_warning_date") != today_str:
                state["last_low_disk_warning_date"] = today_str
                _save_scheduler_state(state)
                await _notify_owner(
                    self.bot,
                    f"⚠️ **שטח דיסק נמוך** - נשארו רק {free_gb:.1f}GB פנויים בכונן הפרויקט. "
                    "רינדורים ארוכים עלולים להיכשל בקרוב."
                )
        except OSError as e:
            print(f"[scheduler] בדיקת שטח דיסק נכשלה: {e}")

        # "רינדור-קנרית" מתוזמן (item) - מחולץ לפונקציה נפרדת (אותו עיקרון כמו
        # _maybe_run_recap) כדי שאפשר יהיה לבדוק אותה ישירות בלי לעבור על שאר
        # שלבי daily_maintenance.
        await self._maybe_run_canary_render(state, today_str)

        # 0. גיבוי בסיס הנתונים - כל יום, תמיד (לא תלוי בהגדרות המשתמש)
        if state.get("last_db_backup_date") != today_str:
            backup_ok, backup_error = await self.bot.loop.run_in_executor(None, _backup_database)
            state["last_db_backup_date"] = today_str
            _save_scheduler_state(state)
            if backup_ok:
                print("[scheduler] גיבוי בסיס הנתונים הושלם.")
            else:
                print(f"[scheduler] גיבוי בסיס הנתונים נכשל: {backup_error}")
                await _notify_owner(self.bot, f"⚠️ **גיבוי בסיס הנתונים האוטומטי נכשל** ({today_str})\n```\n{backup_error}\n```")

            data_backup_ok, data_backup_error = await self.bot.loop.run_in_executor(None, _backup_data_directory)
            if data_backup_ok:
                print("[scheduler] גיבוי תיקיית data/ הושלם.")
            else:
                print(f"[scheduler] גיבוי תיקיית data/ נכשל: {data_backup_error}")
                await _notify_owner(self.bot, f"⚠️ **גיבוי תיקיית data/ האוטומטי נכשל** ({today_str})\n```\n{data_backup_error}\n```")

        # 0.5. ניקוי גיבויי-לוג ישנים (item 26) - כל יום, תמיד. utils/shared/logging_setup.py
        # כבר מגביל כל קובץ לוג בודד לפי גודל (RotatingFileHandler); זו הגנה
        # משלימה מבוססת-זמן, כדי שגיבוי קטן אבל ישן (תהליך שרץ לעיתים רחוקות)
        # לא יישאר לצמיתות בלי סיבה.
        if state.get("last_log_cleanup_date") != today_str:
            deleted = await self.bot.loop.run_in_executor(None, purge_old_log_backups)
            state["last_log_cleanup_date"] = today_str
            _save_scheduler_state(state)
            if deleted:
                print(f"[scheduler] נוקו {len(deleted)} קבצי גיבוי-לוג ישנים: {', '.join(deleted)}")

        # 1. ניקוי מקורות ישנים - כל יום, אם cleanup_retention_days מוגדר (>0).
        # הסקריפט עצמו כבר בודק את ההגדרה הזו ויוצא בשקט אם היא 0, אבל בודקים גם
        # כאן כדי לא להריץ תת-תהליך מיותר כשהתכונה כבויה.
        retention_days = int(settings.get("cleanup_retention_days", 0) or 0)
        if retention_days > 0 and state.get("last_cleanup_date") != today_str:
            status, tail = await self.bot.loop.run_in_executor(
                None, _run_script_blocking, os.path.join("video", "cleanup_published_sources.py")
            )
            state["last_cleanup_date"] = today_str
            _save_scheduler_state(state)
            print(f"[scheduler] ניקוי מקורות אוטומטי הסתיים: {status}")
            if status != "success":
                await _notify_owner(self.bot, f"⚠️ **ניקוי מקורות אוטומטי נכשל** ({today_str})\n```\n{tail[-500:] if tail else 'אין פרטים'}\n```")

        # 2. ריקאפ תקופתי - week/month/year (item: ריקאפ חודשי/שנתי, לא רק
        # שבועי) - מחולץ לפונקציה נפרדת (לא inline כאן) כדי שאפשר יהיה לבדוק
        # אותה ישירות בלי לעבור על שאר שלבי daily_maintenance (גיבוי DB וכו').
        await self._maybe_run_recap(settings, state, today_str)

    async def _maybe_run_recap(self, settings, state, today_str):
        """מריץ ריקאפ (week/month/year) אם המשתמש הפעיל את זה (הגדרות Rocket
        ב-GUI/ווב) ורק ביום הנכון לתקופה. month/year רצים בתאריך קבוע (1
        לחודש/1 בינואר), לא תלויים ב-weekly_recap_day (רלוונטי רק ל-week)."""
        if not settings.get("enable_weekly_recap", False):
            return
        recap_period = settings.get("weekly_recap_period", "week")
        recap_day = int(settings.get("weekly_recap_day", 6))  # date.weekday(): שני=0 ... ראשון=6, רלוונטי רק ל-week
        if not should_run_recap_today(recap_period, recap_day, datetime.date.today()) or state.get("last_weekly_recap_date") == today_str:
            return
        status, tail = await self.bot.loop.run_in_executor(
            None, _run_script_blocking, os.path.join("video", "weekly_compilation.py"), ["--period", recap_period]
        )
        state["last_weekly_recap_date"] = today_str
        _save_scheduler_state(state)
        print(f"[scheduler] ריקאפ אוטומטי ({recap_period}) הסתיים: {status}")
        if status != "success":
            await _notify_owner(self.bot, f"⚠️ **ריקאפ אוטומטי נכשל** ({today_str})\n```\n{tail[-500:] if tail else 'אין פרטים'}\n```")

    async def _maybe_run_canary_render(self, state, today_str):
        """item: "רינדור-קנרית" מתוזמן - קליפ סינתטי זעיר דרך video_editor.py
        האמיתי, פעם ביום, כדי לתפוס תקלת ffmpeg/תלות מוקדם - לפני שמישהו מנסה
        רינדור אמיתי ומגלה שזה שבור. תמיד רץ (לא תלוי בהגדרות משתמש, כמו גיבוי
        ה-DB) - זו בדיקת-בריאות תשתית, לא פיצ'ר להדלקה/כיבוי."""
        if state.get("last_canary_render_date") == today_str:
            return
        canary_ok, canary_error = await self.bot.loop.run_in_executor(None, _run_canary_render)
        state["last_canary_render_date"] = today_str
        _save_scheduler_state(state)
        if canary_ok:
            print("[scheduler] רינדור-קנרית עבר בהצלחה.")
        else:
            print(f"[scheduler] רינדור-קנרית נכשל: {canary_error}")
            await _notify_owner(
                self.bot,
                f"🚨 **רינדור-קנרית נכשל** ({today_str}) - ייתכן שיש בעיה ב-ffmpeg/תלות שתשפיע על רינדורים אמיתיים.\n```\n{canary_error}\n```"
            )

    @daily_maintenance.before_loop
    async def before_daily_maintenance(self):
        await self.bot.wait_until_ready()

    @check_stuck_render_lock.before_loop
    async def before_check_stuck_render_lock(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(SchedulerCog(bot))
