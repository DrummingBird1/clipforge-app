# entrypoints/web/path_checks.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 4): בדיקות הנתיבים - מה מותר להגיש, לפתוח, לפרסם ולשחזר. עבר מ-web_app.py בלי שינוי
# התנהגות. web_app מייבא את השמות האלה בחזרה (web_app.<שם> נשאר), וה-routes ממשיכים לקרוא W.<שם>.
# כל שם שקיים גם ב-web_app נקרא דרך W. - טסטים מחליפים את web_app.<שם> (DATA_DIR, CLIPS_DIR, WORKSPACE_DIR...), והקוד כאן
# צריך לראות את ההחלפה (tests/web/test_web_app_split.py בודק את זה).
import os

from entrypoints import web_app as W
from utils.shared import path_safety

PUBLISHABLE_VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm")
def _is_under_data_dir(path):
    """True אם path נמצא בתוך DATA_DIR (data/) - שם יושבים קבצים רגישים כמו
    הטוקן של השרת עצמו (web_app_token.txt) ו-config.json. /api/watermark_image
    ו-/api/download משרתים כל קובץ מקומי קיים שהמשתמש הצביע עליו (item: בדיקת
    באגים מקיפה - זו כוונה מקורית, לא פירצה חדשה: /api/browse כבר חושף גישה
    מלאה לדיסק המקומי מאחורי אותו טוקן), אבל watermark ותוצרי-רינדור אף פעם
    לא יושבים תחת data/ - אין שום סיבה לגיטימית לאפשר להוריד/להציג משם דרך
    ה-endpoints האלה, אז זה נחסם באופן ספציפי."""
    # 17.11.2026: גם קובצי הסודות שיושבים בתיקיית ההתקנה (.env, הטוקן וההרשאות של יוטיוב, העוגיות של TikTok) - לפי השם
    return path_safety.is_inside_protected(path, W.DATA_DIR) or path_safety.is_secret_name(path)   # 16.11.2026: גם \?\ ו-\localhost\E$


def _validate_clip_path(path):
    """מוודא שהנתיב הוא קובץ אמיתי בתוך CLIPS_DIR בדיוק - זהה לוולידציית
    SCRIPTS_DIR ב-/api/scheduler/tasks, כדי שה-endpoints הייעודיים האלה
    (סטרימינג/יצוא) לא יהפכו לשרת-קבצים כללי לכל נתיב שרירותי."""
    if not path:
        return None
    real_path = os.path.realpath(path)
    if not path_safety.is_within(real_path, W.CLIPS_DIR):
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
            rocket and path_safety.is_within(real_path, rocket)):
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
    for root in (W.WORKSPACE_DIR, W.export_dir.configured_root(), *(folder for _tool, folder in W.export_dir.configured_folders())):
        if root and path_safety.is_within(path, root):
            return True
    return False


def _validate_backup_filename(filename):
    """basename בלבד + חייב להישאר בתוך BACKUPS_DIR + סיומת .ibkp - אותו עיקרון
    בדיוק כמו _validate_clip_path, מונע path traversal דרך שם קובץ שמגיע מבקשה."""
    safe_name = os.path.basename(filename or "")
    if not safe_name.endswith(".ibkp"):
        return None
    full_path = os.path.realpath(os.path.join(W.BACKUPS_DIR, safe_name))
    if not path_safety.is_within(full_path, W.BACKUPS_DIR):
        return None
    if not os.path.isfile(full_path):
        return None
    return full_path
