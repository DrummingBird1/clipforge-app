# utils/shared/install_where.py
#
# 17.11.2026 (ClipForge 2.0.1): איך ClipForge הותקן, לפי מה שבאמת יש במחשב ולא רק לפי מחרוזת בנתיב.
# ב-2.0.0 הזיהוי היה "\winget\packages\" או "\scoop\apps\" בנתיב. התקנת winget לתיקייה אחרת (winget install --location, או
# שורש אחר ל-portable packages) זוהתה כ-zip רגיל: הנתונים נשארו בתוך התיקייה של הגרסה, והגרסה הבאה עלתה ריקה.
#   - winget: גם לפי הרישום - winget רושם כל חבילה ב-Uninstall עם InstallLocation ו-WinGetPackageIdentifier.
#   - Scoop: גם בשורש אחר - <שורש>\apps\<אפליקציה>\<גרסה>, כשלצד apps יש shims ו-buckets.
# בלי ייבוא של data_paths: ה-launcher קורא לזה לפני שהוא קובע איפה תיקיית הנתונים.
import os
from typing import List, Optional

WINGET_ID = "DrummingBird1.ClipForge"
_UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall"


def winget_locations() -> List[str]:
    """InstallLocation של כל רישום ש-winget כתב לחבילה הזו (למשתמש ולמחשב). רשימה ריקה בלי Windows או בלי רישום."""
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, _UNINSTALL_KEY) as root:
                for index in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        name = winreg.EnumKey(root, index)
                        with winreg.OpenKey(root, name) as key:
                            package = _value(winreg, key, "WinGetPackageIdentifier")
                            if package != WINGET_ID and not name.startswith(WINGET_ID + "_"):
                                continue
                            location = _value(winreg, key, "InstallLocation")
                            if location:
                                found.append(location)
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def _value(winreg, key, name: str) -> str:
    try:
        return str(winreg.QueryValueEx(key, name)[0] or "")
    except OSError:
        return ""


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path)).rstrip("\\/") + os.sep


def is_winget(root: str, locations: Optional[List[str]] = None) -> bool:
    path = _norm(root)
    if os.sep + "winget" + os.sep + "packages" + os.sep in path:
        return True
    for location in (winget_locations() if locations is None else locations):
        if location and path.startswith(_norm(location)):
            return True
    return False


def is_scoop(root: str) -> bool:
    path = _norm(root)
    if os.sep + "scoop" + os.sep + "apps" + os.sep in path:
        return True
    version_dir = os.path.abspath(root)
    apps = os.path.dirname(os.path.dirname(version_dir))            # <שורש>\apps\<אפליקציה>\<גרסה>
    scoop_root = os.path.dirname(apps)
    return (os.path.basename(apps).lower() == "apps"
            and os.path.isdir(os.path.join(scoop_root, "shims")) and os.path.isdir(os.path.join(scoop_root, "buckets")))
