# utils/capture/import_presets.py
#
# 16.11.2026 (2.0): איפה תוכנות ההקלטה והקונסולות שומרות קליפים - כדי לייבא מהם בלחיצה (importer.py) במקום לחפש תיקייה.
#   NVIDIA App / ShadowPlay  - Videos\<משחק>\                        (תת-תיקייה לכל משחק)
#   AMD ReLive / Adrenalin   - Videos\Radeon ReLive\
#   Xbox Game Bar            - תיקיית "לכידות" של Windows (הרישום, User Shell Folders), ברירת מחדל Videos\Captures
#   Steam                    - <Steam>\userdata\<id>\gamerecordings\  (DASH: session.mpd + m4s - remux ל-MP4 בייבוא)
#   OBS                      - הנתיב מהפרופיל הפעיל (basic.ini: RecFilePath / FilePath)
#   Elgato 4K Capture        - Videos\4K Capture Utility\
#   PS5 (USB)                - <כונן>:\PS5\CREATE\Video Clips\<משחק>\
#   PS4 (USB)                - <כונן>:\PS4\SHARE\Video Clips\<משחק>\
#   Switch / Switch 2 (SD)   - <כונן>:\Nintendo\Album\YYYY\MM\DD\
#   Xbox (קונסולה)           - OneDrive\Videos\Xbox Game DVR, או מה שאפליקציית Xbox הורידה ל-Videos\Captures
# הקריאה מהרישום והקבצים - קריאה בלבד. הכול מוזרק (env, reader, drives) כדי שהטסטים יבנו עץ מזויף.
import configparser
import os
from typing import Callable, Dict, List, NamedTuple, Optional

_CAPTURES_GUID = "{EDC0FE71-98D8-4F4A-B920-C8DC133CB165}"
# NVIDIA App / ShadowPlay: "<משחק> 2026.11.16 - 14.03.22.01.DVR.mp4" (Instant Replay) או בלי ".DVR" (הקלטה)
NVIDIA_NAME = r"\d{4}\.\d{2}\.\d{2} - \d{2}\.\d{2}\.\d{2}\.\d{2}(\.DVR)?\.mp4$"


class Preset(NamedTuple):
    id: str
    label: str
    path: str
    kind: str          # folder / steam
    recursive: bool
    console: bool      # כונן נשלף / כרטיס זיכרון
    pattern: str = ""  # regex על שם הקובץ - רק קבצים של התוכנה הזו (NVIDIA שומרת בתוך Videos הכללית, לצד הסרטונים של המשתמש)


def _videos(env: Dict[str, str]) -> str:
    return os.path.join(env.get("USERPROFILE", ""), "Videos")


def read_registry(key_path: str, value: str, hive: str = "HKCU") -> Optional[str]:
    try:
        import winreg
    except ImportError:
        return None
    root = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    try:
        with winreg.OpenKey(root, key_path) as key:
            data, _kind = winreg.QueryValueEx(key, value)
            return os.path.expandvars(str(data))
    except OSError:
        return None


def obs_record_path(appdata: str) -> Optional[str]:
    """הנתיב של ההקלטות בפרופיל הפעיל של OBS (global.ini -> [Basic] Profile, ואז basic.ini של הפרופיל)."""
    root = os.path.join(appdata, "obs-studio")
    profile = None
    global_ini = configparser.RawConfigParser(strict=False)
    try:
        global_ini.read(os.path.join(root, "global.ini"), encoding="utf-8-sig")
        profile = global_ini.get("Basic", "ProfileDir", fallback=None) or global_ini.get("Basic", "Profile", fallback=None)
    except (configparser.Error, OSError):
        pass
    profiles = os.path.join(root, "basic", "profiles")
    candidates = [profile] if profile else []
    try:
        candidates += sorted(os.listdir(profiles))
    except OSError:
        pass
    for name in candidates:
        ini = configparser.RawConfigParser(strict=False)
        try:
            ini.read(os.path.join(profiles, name, "basic.ini"), encoding="utf-8-sig")
        except (configparser.Error, OSError):
            continue
        mode = ini.get("Output", "Mode", fallback="Simple")
        section, key = ("AdvOut", "RecFilePath") if mode == "Advanced" else ("SimpleOutput", "FilePath")
        path = ini.get(section, key, fallback="")
        if path:
            return os.path.normpath(path)
    return None


def steam_recording_dirs(steam_path: Optional[str]) -> List[str]:
    if not steam_path:
        return []
    userdata = os.path.join(steam_path, "userdata")
    try:
        users = sorted(os.listdir(userdata))
    except OSError:
        return []
    return [os.path.join(userdata, u, "gamerecordings") for u in users if os.path.isdir(os.path.join(userdata, u, "gamerecordings"))]


def removable_drives() -> List[str]:
    """כוננים נשלפים (USB, כרטיס SD) - שם PS5/PS4/Switch שומרים."""
    try:
        import psutil
        return [p.mountpoint for p in psutil.disk_partitions(all=False) if "removable" in (p.opts or "")]
    except Exception:
        return []


def presets(env: Optional[Dict[str, str]] = None, registry: Callable[..., Optional[str]] = read_registry,
            drives: Optional[List[str]] = None) -> List[Preset]:
    env = dict(os.environ) if env is None else env
    videos = _videos(env)
    captures = registry(r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", _CAPTURES_GUID) \
        or os.path.join(videos, "Captures")
    found = [
        Preset("nvidia", "NVIDIA App / ShadowPlay", videos, "folder", True, False, NVIDIA_NAME),
        Preset("amd", "AMD ReLive", os.path.join(videos, "Radeon ReLive"), "folder", True, False),
        Preset("gamebar", "Xbox Game Bar", captures, "folder", False, False),
        Preset("elgato", "Elgato 4K Capture", os.path.join(videos, "4K Capture Utility"), "folder", True, False),
    ]
    obs = obs_record_path(env.get("APPDATA", ""))
    if obs:
        found.append(Preset("obs", "OBS", obs, "folder", False, False))
    steam = registry(r"Software\Valve\Steam", "SteamPath")
    if steam_recording_dirs(steam):
        # מקור אחד לכל חשבונות Steam במחשב (userdata\<id>\gamerecordings) - קודם כל חשבון היה שורה נפרדת בשם "Steam"
        found.append(Preset("steam", "Steam", os.path.join(steam, "userdata"), "steam", True, False))
    onedrive = env.get("OneDrive") or env.get("ONEDRIVE") or ""
    if onedrive:
        found.append(Preset("xbox", "Xbox (OneDrive)", os.path.join(onedrive, "Videos", "Xbox Game DVR"), "folder", True, False))
    for drive in (removable_drives() if drives is None else drives):
        letter = drive.rstrip("\\/")
        found += [
            Preset(f"ps5:{letter}", f"PlayStation 5 ({letter})", os.path.join(drive, "PS5", "CREATE", "Video Clips"), "folder", True, True),
            Preset(f"ps4:{letter}", f"PlayStation 4 ({letter})", os.path.join(drive, "PS4", "SHARE", "Video Clips"), "folder", True, True),
            Preset(f"switch:{letter}", f"Nintendo Switch ({letter})", os.path.join(drive, "Nintendo", "Album"), "folder", True, True),
        ]
    return found


def available(found: List[Preset]) -> List[Preset]:
    return [p for p in found if os.path.isdir(p.path)]
