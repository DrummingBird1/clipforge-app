# utils/shared/install_files.py
#
# 17.11.2026 (ClipForge 2.0.1): הקבצים שהמשתמש שם בתיקיית ההתקנה שורדים עדכון.
# .env (הטוקן של הבוט והמפתחות), client_secret.json ו-youtube_token.json (החיבור ליוטיוב) ו-tiktok_cookies.txt יושבים
# בתיקיית ההתקנה. Scoop ו-winget מחליפים את כל התיקייה בכל עדכון ושומרים רק את data/ ו-workspace/, ומי שמעדכן zip פורס
# תיקייה חדשה - כך שכל עדכון מחק את החיבור ליוטיוב ולדיסקורד.
#
# sync רץ בכל הפעלה של חבילה מותקנת (launcher.pyw), ואחרי שנכתב טוקן חדש של יוטיוב:
#   - קובץ שקיים בתיקיית ההתקנה נשמר בעותק ב-data/security/install_files (data/ שורדת עדכונים, ומוגנת מהורדה).
#   - התקנה חדשה (תיקייה אחרת או גרסה אחרת מהפעם הקודמת) שחסר בה קובץ - מקבלת אותו מהעותק.
#   - קובץ שהמשתמש מחק מתיקיית ההתקנה באותה התקנה - העותק שלו נמחק גם (לא מחזירים סוד שהמשתמש הסיר).
# בשכפול git (בלי portable.json) לא נוגעים בכלום.
import json
import os
import shutil
from typing import Dict, Optional

from utils.shared.release_info import PORTABLE_MARKER

KEPT_FILES = (".env", "client_secret.json", "youtube_token.json", "tiktok_cookies.txt")
KEEP_DIR = os.path.join("security", "install_files")
STATE_FILE = "install.json"


def _same(a: str, b: str) -> bool:
    try:
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime)


def _install_id(root: str) -> Dict[str, str]:
    version = ""
    try:
        with open(os.path.join(root, PORTABLE_MARKER), encoding="utf-8") as f:
            version = str(json.load(f).get("version") or "")
    except (OSError, ValueError, AttributeError):
        pass
    return {"root": os.path.normcase(os.path.abspath(root)), "version": version}


def sync(root: str, data_dir: str) -> Dict[str, str]:
    """{שם קובץ: "saved" / "restored" / "dropped"} למה שהשתנה. לא זורק - כשל בקובץ אחד לא עוצר את ההפעלה."""
    if not os.path.isfile(os.path.join(root, PORTABLE_MARKER)):
        return {}
    keep = os.path.join(data_dir, KEEP_DIR)
    state_path = os.path.join(keep, STATE_FILE)
    current = _install_id(root)
    try:
        with open(state_path, encoding="utf-8") as f:
            previous: Optional[Dict[str, str]] = json.load(f)
    except (OSError, ValueError):
        previous = None
    new_install = previous != current
    changed: Dict[str, str] = {}
    for name in KEPT_FILES:
        here, saved = os.path.join(root, name), os.path.join(keep, name)
        try:
            if os.path.isfile(here):
                if not _same(here, saved):
                    os.makedirs(keep, exist_ok=True)
                    shutil.copy2(here, saved)
                    changed[name] = "saved"
            elif os.path.isfile(saved):
                if new_install:
                    shutil.copy2(saved, here)
                    changed[name] = "restored"
                else:
                    os.remove(saved)
                    changed[name] = "dropped"
        except OSError:
            continue
    if new_install and (previous is not None or os.path.isdir(keep)):
        try:
            os.makedirs(keep, exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(current, f)
        except OSError:
            pass
    return changed


def sync_default() -> Dict[str, str]:
    """sync לתיקיית ההתקנה ולתיקיית הנתונים של התהליך הזה."""
    from utils.shared.data_dir import DATA_DIR, PROJECT_ROOT
    try:
        return sync(PROJECT_ROOT, DATA_DIR)
    except Exception:
        return {}
