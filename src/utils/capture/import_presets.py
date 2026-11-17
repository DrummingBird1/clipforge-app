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
#
# 17.11.2026 (2.0.1), מהבדיקה המעמיקה:
#   - OBS: רק קבצים בשם ש-OBS נותן (תבנית השם מהפרופיל). תיקיית ההקלטות של OBS היא בדרך כלל Videos כולה, ובלי תבנית
#     "ייבוא מ-OBS" העתיק כל סרטון שיש שם. הפרופיל הפעיל נקרא מ-user.ini (OBS חדש) ואז מ-global.ini.
#   - תיקיית הסרטונים נקראת מהרישום (מי שהעביר את Videos לכונן אחר לא ראה את NVIDIA / AMD / Elgato).
#   - קונסולות: כל כונן שיש בו תיקיית הקליפים של הקונסולה, לא רק כונן "נשלף" - דיסק USB חיצוני של PS5 הוא כונן רגיל.
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


_SHELL_FOLDERS = "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders"
# ברירת המחדל של OBS: "%CCYY-%MM-%DD %hh-%mm-%ss", ו-replay עם התחילית "Replay"
OBS_DEFAULT_FORMAT = "%CCYY-%MM-%DD %hh-%mm-%ss"
_OBS_FIELDS = {"CCYY": r"\d{4}", "YY": r"\d{2}", "MM": r"\d{2}", "DD": r"\d{2}", "hh": r"\d{2}", "mm": r"\d{2}", "ss": r"\d{2}"}


def _videos(env: Dict[str, str], registry: Optional[Callable[..., Optional[str]]] = None) -> str:
    moved = registry(_SHELL_FOLDERS, "My Video") if registry else None
    return moved if moved and os.path.isdir(moved) else os.path.join(env.get("USERPROFILE", ""), "Videos")


def obs_name_pattern(formatting: str = "", replay_prefix: str = "Replay") -> str:
    """regex לשם קובץ ש-OBS יצר, מתוך FilenameFormatting של הפרופיל. שדה לא מוכר (%A, %p...) הופך ל"משהו"."""
    import re
    formatting = formatting or OBS_DEFAULT_FORMAT
    out, i = "", 0
    while i < len(formatting):
        if formatting[i] == "%":
            field = next((name for name in _OBS_FIELDS if formatting.startswith(name, i + 1)), None)
            if field:
                out, i = out + _OBS_FIELDS[field], i + 1 + len(field)
            else:
                out, i = out + ".+?", i + 2
            continue
        out, i = out + re.escape(formatting[i]), i + 1
    prefix = f"(?:{re.escape(replay_prefix)} ?)?" if replay_prefix else ""
    return f"^{prefix}{out}"


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


def _obs_profile_names(root: str) -> List[str]:
    """הפרופיל הפעיל (user.ini ב-OBS חדש, global.ini בישן) ואחריו כל השאר."""
    names: List[str] = []
    for ini_name in ("user.ini", "global.ini"):
        ini = configparser.RawConfigParser(strict=False)
        try:
            ini.read(os.path.join(root, ini_name), encoding="utf-8-sig")
            active = ini.get("Basic", "ProfileDir", fallback=None) or ini.get("Basic", "Profile", fallback=None)
        except (configparser.Error, OSError):
            active = None
        if active and active not in names:
            names.append(active)
    try:
        names += [name for name in sorted(os.listdir(os.path.join(root, "basic", "profiles"))) if name not in names]
    except OSError:
        pass
    return names


def obs_recording(appdata: str) -> Optional[tuple]:
    """(תיקיית ההקלטות, regex לשמות הקבצים) של הפרופיל הפעיל של OBS, או None."""
    root = os.path.join(appdata, "obs-studio")
    profiles = os.path.join(root, "basic", "profiles")
    for name in _obs_profile_names(root):
        ini = configparser.RawConfigParser(strict=False)
        try:
            ini.read(os.path.join(profiles, name, "basic.ini"), encoding="utf-8-sig")
        except (configparser.Error, OSError):
            continue
        mode = ini.get("Output", "Mode", fallback="Simple")
        section, key = ("AdvOut", "RecFilePath") if mode == "Advanced" else ("SimpleOutput", "FilePath")
        path = ini.get(section, key, fallback="")
        if path:
            prefix = ini.get("AdvOut" if mode == "Advanced" else "SimpleOutput", "RecRBPrefix", fallback="Replay")
            return os.path.normpath(path), obs_name_pattern(ini.get("Output", "FilenameFormatting", fallback=""), prefix)
    return None


def obs_record_path(appdata: str) -> Optional[str]:
    found = obs_recording(appdata)
    return found[0] if found else None


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
    """כל הכוננים המחוברים (USB, כרטיס SD, דיסק חיצוני) - PS5/PS4/Switch שומרים באחד מהם. רק כונן שיש בו תיקיית הקליפים
    של קונסולה יוצג (available)."""
    try:
        import psutil
        return [p.mountpoint for p in psutil.disk_partitions(all=False) if "cdrom" not in (p.opts or "")]
    except Exception:
        return []


def presets(env: Optional[Dict[str, str]] = None, registry: Callable[..., Optional[str]] = read_registry,
            drives: Optional[List[str]] = None) -> List[Preset]:
    env = dict(os.environ) if env is None else env
    videos = _videos(env, registry)
    captures = registry(r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", _CAPTURES_GUID) \
        or os.path.join(videos, "Captures")
    found = [
        Preset("nvidia", "NVIDIA App / ShadowPlay", videos, "folder", True, False, NVIDIA_NAME),
        Preset("amd", "AMD ReLive", os.path.join(videos, "Radeon ReLive"), "folder", True, False),
        Preset("gamebar", "Xbox Game Bar", captures, "folder", False, False),
        Preset("elgato", "Elgato 4K Capture", os.path.join(videos, "4K Capture Utility"), "folder", True, False),
    ]
    obs = obs_recording(env.get("APPDATA", ""))
    if obs:
        found.append(Preset("obs", "OBS", obs[0], "folder", False, False, obs[1]))
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
