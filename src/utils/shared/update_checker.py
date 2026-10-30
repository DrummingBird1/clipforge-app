# utils/shared/update_checker.py
#
# בודק אם יש גרסה חדשה יותר ב-GitHub Releases של הפרויקט - עד כה לא הייתה שום
# דרך לדעת שיצאה גרסה חדשה חוץ מלבדוק ידנית באתר GitHub.
#
# item: true auto-update - apply_update() למטה. הפרויקט הזה אינו מפרסם בפועל
# שום קובץ הרצה בנוי (exe/zip) דרך GitHub Releases (אין workflow כזה ב-CI,
# ראו .github/workflows/ci.yml) - ההפצה האמיתית היחידה היא שכפול git + `uv
# sync` (כך ש-Launcher.vbs עצמו כבר עובד). "הורדה והתקנה" שמנסה למשוך asset
# בינארי שלא בטוח בכלל שקיים הייתה שברירית ומטעה; העדכון האמיתי והבטוח כאן
# הוא `git pull --ff-only` (לעולם לא מיזוג/רזולוציית קונפליקטים אוטומטית,
# ומסרב מראש אם יש שינויים מקומיים לא-שמורים) ואז `uv sync` - בדיוק אותה
# שיטת עדכון שהמשתמש היה עושה ידנית, רק בלחיצת כפתור אחת עם אישור מפורש.
import os
import re
import subprocess

import requests

# 30.10.2026: הגרסאות יוצאות בריפו הציבורי (dev/export_public.py מכין אותו, release.yml בונה בו את ה-zip). הריפו
# הפרטי DrummingBird1/clipforge נשאר לפיתוח, ו-apply_update מושך מה-origin של העותק עצמו, לא מכאן
REPO = "DrummingBird1/clipforge-app"
_RELEASES_API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{REPO}/releases/latest"

_REQUEST_TIMEOUT_SECONDS = 5

# 30.10.2026: החבילה הניידת (dev/build_portable.py) כותבת את הקובץ הזה בשורש שלה. שם אין git ואין uv - מעדכנים בהורדת
# הגרסה החדשה מעמוד ה-Release, לא ב-apply_update.
PORTABLE_MARKER = "portable.json"
PORTABLE_UPDATE_REFUSAL = "בחבילה הניידת מעדכנים בהורדת הגרסה החדשה מעמוד ההורדה."


def is_portable(base_dir):
    """True כשהאפליקציה רצה מתוך החבילה הניידת (zip), לא משכפול git."""
    return os.path.isfile(os.path.join(base_dir, PORTABLE_MARKER))


def _version_tuple(version_string):
    """הופך "v1.2.10"/"1.2.10" ל-(1, 2, 10) להשוואה מספרית נכונה - השוואת
    מחרוזות רגילה הייתה שוברת בין "1.9.0" ל-"1.10.0" (מחרוזתית, "1.9.0" > "1.10.0")."""
    digits_only_parts = re.findall(r"\d+", version_string)
    return tuple(int(part) for part in digits_only_parts) if digits_only_parts else (0,)


def check_for_update(current_version, timeout=_REQUEST_TIMEOUT_SECONDS):
    """בודק מול GitHub Releases API אם קיימת גרסה חדשה יותר מ-current_version.

    מחזיר את tag_name של הגרסה החדשה אם כן, אחרת None - גם כשאין עדכון, גם
    כשעדיין לא פורסם אף release בכלל (404, פרויקט חדש), וגם בכל כשל רשת/timeout.
    בכוונה לא מבדיל בין המקרים האלה כלפי הקורא (utils/update_checker אחראי
    לשקוף פשוט "יש/אין עדכון זמין להצגה") - כל השגיאות שקטות כי זו בדיקה
    לא-קריטית שרצה ברקע; היא לעולם לא אמורה להפיל את ה-GUI או להציג שגיאה
    מפחידה על משהו שהוא בסך הכל "לא הצלחתי לבדוק עדכונים כרגע"."""
    try:
        response = requests.get(
            _RELEASES_API_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        latest_tag = response.json().get("tag_name", "")
        if not latest_tag:
            return None
        if _version_tuple(latest_tag) > _version_tuple(current_version):
            return latest_tag
    except Exception:
        pass
    return None


def apply_update(repo_dir, timeout=300):
    """מעדכן את הקוד בפועל (item: true auto-update) - `git pull --ff-only` ואז
    `uv sync`, אותה שיטת עדכון שהמשתמש כבר היה עושה ידנית. לעולם לא רץ
    אוטומטית - רק על-פי לחיצה מפורשת של המשתמש על "עדכן עכשיו" (שני ה-UIs).

    מסרב מראש אם יש שינויים מקומיים לא-שמורים (git status --porcelain לא
    ריק) - עדכון על עץ מלוכלך עלול לגרום לקונפליקטים/לאבד עבודה, עדיף
    להיכשל בבירור מראש מאשר לנסות ולסבך. --ff-only (לא merge/rebase רגיל) -
    מסרב בעדינות אם ההיסטוריה המקומית התפצלה מ-origin במקום לנסות למזג/
    לפתור קונפליקטים בעצמו; אין כאן שום --force בשום שלב.

    מחזיר (ok: bool, message: str) - message מיועד להצגה ישירה למשתמש."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True, timeout=15
        )
    except Exception as e:
        return False, f"בדיקת מצב ה-git נכשלה: {e}"
    if status.returncode != 0:
        return False, f"בדיקת מצב ה-git נכשלה: {status.stderr.strip() or status.stdout.strip()}"
    if status.stdout.strip():
        return False, "יש שינויים מקומיים לא-שמורים (git status) - שמור/בטל אותם קודם. עדכון אוטומטי מסרב לגעת בעץ מלוכלך."

    try:
        pull = subprocess.run(
            ["git", "pull", "--ff-only"], cwd=repo_dir, capture_output=True, text=True, timeout=timeout
        )
    except Exception as e:
        return False, f"git pull נכשל: {e}"
    if pull.returncode != 0:
        return False, f"git pull נכשל: {pull.stderr.strip() or pull.stdout.strip()}"

    try:
        sync = subprocess.run(["uv", "sync"], cwd=repo_dir, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return False, f"קוד המקור עודכן (git pull הצליח), אבל uv sync נכשל להרצה: {e}. הרץ 'uv sync' ידנית."
    if sync.returncode != 0:
        return False, f"קוד המקור עודכן (git pull הצליח), אבל uv sync נכשל: {sync.stderr.strip() or sync.stdout.strip()}. הרץ 'uv sync' ידנית."

    return True, "העדכון הותקן בהצלחה. הפעל מחדש את האפליקציה כדי שהשינויים ייכנסו לתוקף."
