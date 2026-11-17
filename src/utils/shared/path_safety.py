# utils/shared/path_safety.py
#
# 16.11.2026 (סריקת באגים ל-2.0): "הנתיב הזה בתוך התיקייה הזו?" - בצורה שעומדת מול הכינויים של Windows לאותו קובץ.
# realpath משאיר את הקידומת \\?\ ואת צורת ה-UNC (\\localhost\E$\...), אז בדיקת realpath+startswith פספסה אותם, ו-/api/download
# הגיש את data/web_app_token.txt. ובנוסף: startswith(root + sep) נכשל כש-root הוא שורש כונן (E:\), ו-E:\clips2 עבר כ"בתוך"
# E:\clips כשלא הוסיפו sep.
import os
import re

_LOCAL_ADMIN_SHARE = re.compile(r"^\\\\(?:localhost|127\.0\.0\.1|\[?::1\]?)\\([A-Za-z])\$(\\.*)?$", re.IGNORECASE)
_LONG_PREFIX = "\\\\?\\"            # \\?\
_LONG_UNC_PREFIX = "\\\\?\\UNC\\"   # \\?\UNC\


def canonical(path: str) -> str:
    r"""realpath בצורה אחת: בלי \\?\, שיתוף admin מקומי (\\localhost\E$) חוזר לאות כונן, ו-normcase."""
    real = os.path.realpath(path)
    if real.startswith(_LONG_UNC_PREFIX):
        real = "\\\\" + real[len(_LONG_UNC_PREFIX):]
    elif real.startswith(_LONG_PREFIX):
        real = real[len(_LONG_PREFIX):]
    match = _LOCAL_ADMIN_SHARE.match(real)
    if match:
        real = match.group(1) + ":" + (match.group(2) or "\\")
    return os.path.normcase(real)


def is_within(path: str, root: str) -> bool:
    """path הוא root או בתוכו (commonpath על הצורה הקנונית)."""
    p, r = canonical(path), canonical(root)
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:   # כוננים שונים / יחסי מול מוחלט
        return False


def same_file_ancestor(path: str, root: str) -> bool:
    """אחד מההורים של path (או path עצמו) הוא *אותה תיקייה* כמו root לפי זהות הקובץ (volume + index) - רשת ביטחון שתופסת
    כל כינוי ש-canonical לא מכיר (UNC בשם המחשב, junction, שם 8.3)."""
    try:
        root_stat = os.stat(root)
    except OSError:
        return False
    current = os.path.abspath(path)
    while True:
        try:
            if os.path.samestat(os.stat(current), root_stat):
                return True
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def is_inside_protected(path: str, root: str) -> bool:
    """לתיקייה שאסור להגיש ממנה (data/): גם לפי הנתיב וגם לפי זהות הקובץ."""
    return is_within(path, root) or same_file_ancestor(path, root)


# --- 17.11.2026 (2.0.1), מהבדיקה המעמיקה ---

SECRET_FILE_NAMES = ("client_secret.json", "youtube_token.json", "tiktok_cookies.txt")


def is_secret_name(path: str) -> bool:
    """קובץ סודות לפי השם שלו, בכל תיקייה: .env (וגם .env.local וכו'), ההרשאות והטוקן של יוטיוב, והעוגיות של TikTok.
    הם יושבים בתיקיית ההתקנה, מחוץ ל-data/, ולכן הבדיקה של data/ לא כיסתה אותם. השם נלקח אחרי realpath (שם קצר 8.3
    וקישורים נפתרים), בלי זרם נתונים חלופי (file::$DATA) ובלי נקודות ורווחים בסוף."""
    try:
        name = os.path.basename(os.path.realpath(path))
    except (OSError, ValueError):
        name = os.path.basename(str(path))
    name = name.split(":")[0].rstrip(" .").lower()
    return name in SECRET_FILE_NAMES or name == ".env" or (name.startswith(".env.") and not name.endswith(".example"))


def free_destination(dst: str) -> str:
    """dst אם הוא פנוי, אחרת name_2.ext, name_3.ext..."""
    stem, ext = os.path.splitext(dst)
    candidate, n = dst, 2
    while os.path.lexists(candidate):
        candidate, n = f"{stem}_{n}{ext}", n + 1
    return candidate


def link_or_copy_new(src: str, dst: str) -> str:
    """קישור קשיח של src ב-dst (או העתקה כשאי אפשר לקשר - כונן אחר), תמיד בשם פנוי. מחזיר את הנתיב שנוצר.
    ב-2.0.0 שם תפוס גרם לנפילה ל-copy2 על הקובץ הקיים - שהוא קישור קשיח למקור אחר - והתוכן של המקור ההוא נדרס."""
    import shutil
    target = free_destination(dst)
    try:
        os.link(src, target)
    except OSError:
        if os.path.lexists(target):          # מישהו יצר אותו בינתיים: לא כותבים עליו
            target = free_destination(dst)
        shutil.copy2(src, target)
    return target
