# utils/shared/job_history.py
import json
import sqlite3

from utils.shared import db
from utils.shared import data_paths

# אותו קובץ DB שהבוט משתמש בו (דרך aiosqlite) - כאן ניגשים אליו סינכרונית מה-GUI,
# באותה מוסכמה שכבר משמשת את ui/bot_tab.py לניהול RSS/Steam.
DB_PATH = data_paths.path(data_paths.BOT_DB)


def _ensure_table():
    with db.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                script_name TEXT,
                status TEXT,
                started_at TEXT,
                finished_at TEXT,
                duration_seconds REAL
            )
        """)
        # result_json: תוצאה מובנית אופציונלית שהסקריפט הדפיס ("RESULT: {...}" -
        # ראו RESULT_LINE_PREFIX ב-utils/shared/worker.py), נשמרת כטקסט JSON חד-שורתי כדי
        # שהיסטוריית ריצות תציג פירוט אמיתי ולא רק הצלחה/כישלון+משך. SQLite לא
        # תומך ב-"ADD COLUMN IF NOT EXISTS" - תופסים את השגיאה כשהעמודה כבר קיימת
        # (טבלה שנוצרה לפני שהעמודה הזו נוספה).
        try:
            conn.execute("ALTER TABLE job_history ADD COLUMN result_json TEXT")
        except sqlite3.OperationalError:
            pass


def record_job(script_name, status, started_at, finished_at, duration_seconds, result=None):
    """status: 'success' או 'failed'. result: dict אופציונלי (מ-"RESULT: {...}"
    של הסקריפט) שנשמר כ-JSON."""
    _ensure_table()
    result_json = json.dumps(result, ensure_ascii=False) if result else None
    with db.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO job_history (script_name, status, started_at, finished_at, duration_seconds, result_json) VALUES (?, ?, ?, ?, ?, ?)",
            (script_name, status, started_at, finished_at, duration_seconds, result_json)
        )


def get_recent_jobs(limit=15):
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT script_name, status, started_at, duration_seconds, result_json FROM job_history ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return rows


def get_recently_run_script_names(limit=5):
    """מחזיר עד limit שמות קבצים ייחודיים (basename, כמו שנשמרים ב-record_job),
    מהריצה האחרונה שלהם והלאה - לא שורות גולמיות (אותו סקריפט יכול להופיע
    הרבה פעמים ברצף בהיסטוריה, וזה היה חוזר על עצמו ברשימה במקום להראות
    עוד סקריפט). משמש את ui/sidebar.py לקיצור-דרך "הורצו לאחרונה"."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        # 200 שורות אחרונות (לא כל הטבלה) - מספיק בכל תרחיש סביר כדי למצוא
        # limit שמות ייחודיים, בלי לסרוק היסטוריה שיכולה לגדול לאלפי שורות.
        rows = conn.execute(
            "SELECT script_name FROM job_history ORDER BY id DESC LIMIT 200"
        ).fetchall()
    seen = []
    for (script_name,) in rows:
        if script_name not in seen:
            seen.append(script_name)
        if len(seen) >= limit:
            break
    return seen


def get_jobs_since(since_iso):
    """מחזיר את כל הריצות שהתחילו אחרי since_iso (מחרוזת ISO) - להבדיל מ-
    get_recent_jobs() (שנחתך לפי מספר שורות, לא תאריך). משמש את
    utils/bot/weekly_digest.py לסכם את השבוע האחרון."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT script_name, status, started_at, duration_seconds, result_json FROM job_history "
            "WHERE started_at >= ? ORDER BY id ASC",
            (since_iso,)
        ).fetchall()
    return rows


def get_average_render_durations():
    """ממוצע משך ריצה (שניות) לכל סקריפט, מבין ריצות מוצלחות בלבד - ריצות
    שנכשלו נעצרות בדרך כלל מוקדם (שגיאה) ולא משקפות זמן רינדור אמיתי, וכך היו
    מטות את הממוצע כלפי מטה בלי סיבה. מוחזר כרשימת (script_name, avg_seconds,
    run_count) ממוינת מהסקריפט עם הכי הרבה ריצות. משמש את /render_stats."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT script_name, AVG(duration_seconds), COUNT(*) FROM job_history "
            "WHERE status = 'success' AND duration_seconds IS NOT NULL "
            "GROUP BY script_name ORDER BY COUNT(*) DESC"
        ).fetchall()
    return rows


def get_typical_duration(script_name, sample=10):
    """חציון משכי הריצות המוצלחות האחרונות של הסקריפט (שניות), או None אם אין היסטוריה. בסיס ל-ETA גלובלי לכל הסקריפטים."""
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT duration_seconds FROM job_history WHERE script_name = ? AND status = 'success' "
            "AND duration_seconds IS NOT NULL AND duration_seconds > 0 ORDER BY id DESC LIMIT ?", (script_name, sample)).fetchall()
    durations = sorted(r[0] for r in rows)
    if not durations:
        return None
    mid = len(durations) // 2
    return durations[mid] if len(durations) % 2 else (durations[mid - 1] + durations[mid]) / 2


def estimate_remaining_seconds(elapsed, pct, typical=None):
    """הערכת זמן שנותר, לכל סקריפט (גם כאלה שמדווחים רק PROGRESS:N בלי ETA משלהם): אקסטרפולציה לינארית מההתקדמות עד כה,
    מעורבבת עם משך הריצה הטיפוסי מההיסטוריה כשההתקדמות עוד קטנה (ההיסטוריה מדויקת יותר בהתחלה, האקסטרפולציה בהמשך).
    None כשאין מספיק מידע."""
    if pct is not None and pct >= 100:
        return 0
    hist = max(typical - elapsed, 0.0) if typical else None
    linear = elapsed * (100 - pct) / pct if pct and pct >= 5 and elapsed >= 3 else None
    if linear is None:
        return None if hist is None else int(hist)
    if hist is None:
        return int(linear)
    weight = min(pct / 50.0, 1.0)
    return int(weight * linear + (1 - weight) * hist)


def search_jobs(query, limit=50):
    """מחפש בהיסטוריית הריצות (item: global search) - script_name, status,
    started_at, ו-result_json (טקסט חופשי, למשל שם קובץ שהופיע ב-RESULT: של
    הסקריפט) - לא רק שם סקריפט, כדי שאפשר יהיה למצוא "איפה הרצתי משהו על
    clip_42.mp4" בלי לזכור באיזה סקריפט/מתי. started_at הוא ISO ("2026-09-18
    T14:30:00"), אז חיפוש LIKE על תת-מחרוזת כמו "2026-09-18" או אפילו "09-18"
    עובד נכון בלי לפרש תאריך בעצמנו. LIKE עם '%query%' בכל ארבעת העמודות
    (OR), לא full-text search (מספיק לטבלה בגודל הזה, בלי תלות חדשה)."""
    _ensure_table()
    like_pattern = f"%{query}%"
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT script_name, status, started_at, duration_seconds, result_json FROM job_history "
            "WHERE script_name LIKE ? OR status LIKE ? OR started_at LIKE ? OR result_json LIKE ? "
            "ORDER BY id DESC LIMIT ?",
            (like_pattern, like_pattern, like_pattern, like_pattern, limit)
        ).fetchall()
    return rows


def get_hwaccel_time_comparison(script_name="video_editor.py"):
    """
    משווה זמן רינדור ממוצע-לקובץ (item: "time saved with --hwaccel" metric)
    בין ריצות עם --hwaccel לבין בלי, על בסיס result_json's "hwaccel"/"files_created"
    (video_editor.py כותב את שניהם ל-RESULT - ראו שם) - בלי עמודת DB חדשה,
    result_json כבר נשמר לכל ריצה. משך-לקובץ (לא משך-הריצה-כולה) כדי שהשוואה
    בין ריצה על 50 קבצים לריצה על קובץ בודד תהיה הוגנת.

    מחזיר None אם אין מספיק נתונים (חסרה קבוצה שלמה - למשל אף פעם לא הופעל
    בלי --hwaccel), אחרת dict עם ממוצע שניות-לקובץ ומספר ריצות לכל קבוצה
    ואחוז השיפור. ריצות משנים ישנים יותר (בלי "hwaccel" ב-result_json בכלל)
    מדולגות בשקט - לא שגיאה, פשוט אין להן דעה בהשוואה הזו.
    """
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT duration_seconds, result_json FROM job_history WHERE script_name = ? AND status = 'success' AND result_json IS NOT NULL",
            (script_name,)
        ).fetchall()

    hwaccel_seconds_per_file = []
    no_hwaccel_seconds_per_file = []
    for duration_seconds, result_json in rows:
        try:
            result = json.loads(result_json)
        except (ValueError, TypeError):
            continue
        if not isinstance(result, dict) or "hwaccel" not in result:
            continue
        files_created = result.get("files_created", 0)
        if not files_created or duration_seconds is None:
            continue
        seconds_per_file = duration_seconds / files_created
        (hwaccel_seconds_per_file if result["hwaccel"] else no_hwaccel_seconds_per_file).append(seconds_per_file)

    if not hwaccel_seconds_per_file or not no_hwaccel_seconds_per_file:
        return None

    hwaccel_avg = sum(hwaccel_seconds_per_file) / len(hwaccel_seconds_per_file)
    no_hwaccel_avg = sum(no_hwaccel_seconds_per_file) / len(no_hwaccel_seconds_per_file)
    percent_faster = (1 - hwaccel_avg / no_hwaccel_avg) * 100 if no_hwaccel_avg else 0.0
    return {
        "hwaccel_avg_seconds_per_file": hwaccel_avg, "hwaccel_run_count": len(hwaccel_seconds_per_file),
        "no_hwaccel_avg_seconds_per_file": no_hwaccel_avg, "no_hwaccel_run_count": len(no_hwaccel_seconds_per_file),
        "percent_faster": percent_faster,
    }


def get_video_editor_eta_estimate(codec, use_hwaccel):
    """
    הערכת זמן-ריצה משוער לפני הרצה (item) - ממוצע שניות-לקובץ מריצות
    מוצלחות קודמות של video_editor.py עם אותו codec+hwaccel בדיוק (אותה
    בקטה שכבר result_json כותב, ראו get_hwaccel_time_comparison - לא עמודת
    DB חדשה). מחזיר None אם אין אף ריצה מוצלחת בבקטה הזו - העדפה על ממוצע
    מטעה מבקטה שונה (h264 מהיר משמעותית מ-hevc/av1 ללא GPU, למשל) על פני
    הערכה בכלל.
    """
    _ensure_table()
    with db.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT duration_seconds, result_json FROM job_history "
            "WHERE script_name = 'video_editor.py' AND status = 'success' AND result_json IS NOT NULL"
        ).fetchall()

    seconds_per_file = []
    for duration_seconds, result_json in rows:
        try:
            result = json.loads(result_json)
        except (ValueError, TypeError):
            continue
        if not isinstance(result, dict):
            continue
        if result.get("codec") != codec or result.get("hwaccel") != use_hwaccel:
            continue
        files_created = result.get("files_created", 0)
        if not files_created or duration_seconds is None:
            continue
        seconds_per_file.append(duration_seconds / files_created)

    if not seconds_per_file:
        return None
    return {
        "avg_seconds_per_file": sum(seconds_per_file) / len(seconds_per_file),
        "run_count": len(seconds_per_file),
    }


def format_result_summary(result):
    """הופך dict תוצאה מובנה (או את ה-JSON השמור שלו) לשורת טקסט קריאה, גנרית
    לכל סקריפט - בלי לדעת מראש אילו מפתחות יהיו בו. משמש גם את ui/dashboard.py
    (מיד אחרי ריצה) וגם את ui/stats_tab.py (מהיסטוריה שמורה ב-DB)."""
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (ValueError, TypeError):
            return ""
    if not isinstance(result, dict) or not result:
        return ""
    return " | ".join(f"{key}: {value}" for key, value in result.items())
