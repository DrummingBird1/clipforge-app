# entrypoints/web/path_checks.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 4): בדיקות הנתיבים - מה מותר להגיש, לפתוח, לפרסם ולשחזר. עבר מ-web_app.py בלי שינוי
# התנהגות. web_app מייבא את השמות האלה בחזרה (web_app.<שם> נשאר), וה-routes ממשיכים לקרוא W.<שם>.
# כל שם שקיים גם ב-web_app נקרא דרך W. - טסטים מחליפים את web_app.<שם> (DATA_DIR, CLIPS_DIR, WORKSPACE_DIR...), והקוד כאן
# צריך לראות את ההחלפה (tests/web/test_web_app_split.py בודק את זה).
import os

from entrypoints import web_app as W

PUBLISHABLE_VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm")


def _is_under_data_dir(path):
    """True אם path נמצא בתוך DATA_DIR (data/) - שם יושבים קבצים רגישים כמו
    הטוקן של השרת עצמו (web_app_token.txt) ו-config.json. /api/watermark_image
    ו-/api/download משרתים כל קובץ מקומי קיים שהמשתמש הצביע עליו (item: בדיקת
    באגים מקיפה - זו כוונה מקורית, לא פירצה חדשה: /api/browse כבר חושף גישה
    מלאה לדיסק המקומי מאחורי אותו טוקן), אבל watermark ותוצרי-רינדור אף פעם
    לא יושבים תחת data/ - אין שום סיבה לגיטימית לאפשר להוריד/להציג משם דרך
    ה-endpoints האלה, אז זה נחסם באופן ספציפי."""
    real_path = os.path.realpath(path)
    real_data_dir = os.path.realpath(W.DATA_DIR)
    return real_path == real_data_dir or real_path.startswith(real_data_dir + os.sep)


def _validate_clip_path(path):
    """מוודא שהנתיב הוא קובץ אמיתי בתוך CLIPS_DIR בדיוק - זהה לוולידציית
    SCRIPTS_DIR ב-/api/scheduler/tasks, כדי שה-endpoints הייעודיים האלה
    (סטרימינג/יצוא) לא יהפכו לשרת-קבצים כללי לכל נתיב שרירותי."""
    if not path:
        return None
    real_path = os.path.realpath(path)
    real_clips_dir = os.path.realpath(W.CLIPS_DIR)
    if not (real_path == real_clips_dir or real_path.startswith(real_clips_dir + os.sep)):
        return None
    if not os.path.isfile(real_path):
        return None
    return real_path


def _rocket_output_root():
    """<output_dir של Rocket>/rocket_shorts כשהוגדרה לו תיקייה משלו - ריק או workspace הם תיקיית הייצוא, שכבר בשורשים."""
    settings = W._load_rocket_settings()
    configured = settings.get("output_dir") or settings.get("input_dir") or ""
    if not isinstance(configured, str) or not configured.strip() or W.export_dir.is_workspace(configured.strip()):
        return ""
    return W._workspace_layout.tool_output_dir(W._workspace_layout.ROCKET_SHORTS, base=configured.strip())


def _validate_publishable_path(path):
    """לפרסום ביוטיוב וב-TikTok (23.10.2026, באישור המפנה - מסך "תוצרים"): כל תוצר, לא רק קליפ מ-CLIPS_DIR - workspace,
    תיקיות הייצוא ותיקיית Rocket. רק סרטון קיים, הבדיקה אחרי realpath (junction או symlink לא יוצאים מהשורש), ואף פעם
    לא מ-data/ - גם כשתיקיית ייצוא הוגדרה שם. _validate_clip_path לא משתנה (שאר ה-routes של הקליפים)."""
    if not path:
        return None
    real_path = os.path.realpath(path)
    if not real_path.lower().endswith(W.PUBLISHABLE_VIDEO_EXTENSIONS) or not os.path.isfile(real_path) or W._is_under_data_dir(real_path):
        return None
    rocket = W._rocket_output_root()
    if W._validate_clip_path(real_path) or W._is_under_workspace(real_path) or (
            rocket and real_path.startswith(os.path.realpath(rocket) + os.sep)):
        return real_path
    return None


def _validated_caption_source(path):
    path = str(path or "").strip()
    if not path or not os.path.isfile(path):
        return None, W.JSONResponse({"error": "קובץ המקור לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return None, W.JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    return path, None


def _is_under_workspace(path):
    """בתוך workspace/ - או בתוך תיקיות הייצוא שבחר המשתמש (23.10.2026: שם התוצרים - הכללית ושל כל כלי): open_folder,
    output_thumbnail ו-stream של הסטודיו מגישים ופותחים רק מכאן - לא כל נתיב."""
    real_path = os.path.realpath(path)
    for root in (W.WORKSPACE_DIR, W.export_dir.configured_root(), *(folder for _tool, folder in W.export_dir.configured_folders())):
        if not root:
            continue
        real_root = os.path.realpath(root)
        if real_path == real_root or real_path.startswith(real_root + os.sep):
            return True
    return False


def _validate_backup_filename(filename):
    """basename בלבד + חייב להישאר בתוך BACKUPS_DIR + סיומת .ibkp - אותו עיקרון
    בדיוק כמו _validate_clip_path, מונע path traversal דרך שם קובץ שמגיע מבקשה."""
    safe_name = os.path.basename(filename or "")
    if not safe_name.endswith(".ibkp"):
        return None
    full_path = os.path.realpath(os.path.join(W.BACKUPS_DIR, safe_name))
    backups_dir_real = os.path.realpath(W.BACKUPS_DIR)
    if full_path != backups_dir_real and not full_path.startswith(backups_dir_real + os.sep):
        return None
    if not os.path.isfile(full_path):
        return None
    return full_path
