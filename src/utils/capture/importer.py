# utils/capture/importer.py
#
# 16.11.2026 (2.0): ייבוא קליפים מתוכנות הקלטה וקונסולות (import_presets.py) לתיקיית ה-Import - בלחיצה.
# - רק קבצים חדשים: manifest (workspace/.cache/import_manifest.json) לפי נתיב + גודל + זמן שינוי, כך שייבוא חוזר מאותו
#   כונן USB לא מעתיק שוב. קובץ ששונה לפני פחות מ-STABLE_SECONDS - עוד נכתב, מדלגים.
# - המקור לא נמחק ולא זז - זה כונן ה-USB / כרטיס ה-SD של המשתמש. מעתיקים לשם פנוי (_2, _3...) ב-Import.
# - Steam שומר DASH (session.mpd + קטעי m4s) - remux ל-MP4 ב-ffmpeg, בלי קידוד מחדש.
#
# 17.11.2026 (2.0.1), מהבדיקה המעמיקה:
#   - תיקיית היעד (Import) שנמצאת בתוך מקור לא נסרקת - אחרת כל ייבוא העתיק שוב את מה שכבר יובא (_2, _3...).
#   - הקובץ נרשם גם לפי שם + גודל + זמן, בלי הנתיב: אותו כונן USB באות אחרת לא מיובא שוב.
#   - העתקה לשם זמני ואז שינוי שם: העתקה שנכשלה לא משאירה סרטון חתוך ב-Import. קובץ שנכשל מדולג, והשאר ממשיכים.
#     אין מקום בדיסק - עוצרים עם הודעה, לא ממלאים את הכונן עד הסוף.
#   - הקליפ המיובא מקבל זמן שינוי של עכשיו: עם הזמן המקורי, ניקוי הקליפים הישנים העביר לארכיון קליפ שרק עכשיו יובא.
#   - Steam: רק קליפים שהמשתמש שמר (clips), לא הקלטת הרקע המתמשכת - היא ענקית, גדלה כל הזמן ויובאה שוב ושוב.
import json
import os
import re
import shutil
import subprocess
import time
from typing import Callable, Dict, List, NamedTuple, Optional

from utils.capture.import_presets import Preset
from utils.media.timelapse import VIDEO_EXTENSIONS

IMPORT_EXTENSIONS = tuple(sorted(set(VIDEO_EXTENSIONS) | {".webm"}))
STABLE_SECONDS = 5
MAX_FILES_PER_RUN = 500
FREE_SPACE_MARGIN = 200 * 1024 ** 2     # כמה נשאר פנוי בכונן היעד אחרי כל קובץ


class Item(NamedTuple):
    source: str      # קובץ וידאו, או session.mpd של Steam
    kind: str        # file / steam
    size: int
    mtime: float

    @property
    def key(self) -> str:
        return f"{os.path.normcase(os.path.abspath(self.source))}|{self.size}|{int(self.mtime)}"

    @property
    def name_key(self) -> str:
        """בלי הנתיב: אותו קובץ בכונן שקיבל אות אחרת. ל-Steam (תיקייה, לא קובץ) - רק המפתח המלא."""
        return f"name:{os.path.basename(self.source).lower()}|{self.size}|{int(self.mtime)}" if self.kind == "file" else self.key


def _seen(item: "Item", manifest: Dict[str, str]) -> bool:
    return item.key in manifest or item.name_key in manifest


def _inside(path: str, folder: Optional[str]) -> bool:
    if not folder:
        return False
    root = os.path.normcase(os.path.abspath(folder)).rstrip("\\/") + os.sep
    return (os.path.normcase(os.path.abspath(path)) + os.sep).startswith(root)


def load_manifest(path: str) -> Dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _walk(root: str, recursive: bool):
    if recursive:
        for folder, _dirs, files in os.walk(root):
            for name in files:
                yield os.path.join(folder, name)
    else:
        try:
            for name in os.listdir(root):
                yield os.path.join(root, name)
        except OSError:
            return


def _steam_roots(path: str) -> List[str]:
    """userdata של Steam -> תיקיות gamerecordings של כל החשבונות (בלי לסרוק את שאר userdata); תיקייה אחרת - היא עצמה."""
    try:
        accounts = [os.path.join(path, name, "gamerecordings") for name in sorted(os.listdir(path))]
    except OSError:
        return [path]
    return [folder for folder in accounts if os.path.isdir(folder)] or [path]


def _steam_dir_stats(folder: str):
    size, newest = 0, 0.0
    for sub, _dirs, files in os.walk(folder):
        for name in files:
            try:
                st = os.stat(os.path.join(sub, name))
            except OSError:
                continue
            size += st.st_size
            newest = max(newest, st.st_mtime)
    return size, newest


def find_new(preset: Preset, manifest: Dict[str, str], now: Optional[float] = None, exclude: Optional[str] = None) -> List[Item]:
    """exclude - תיקיית היעד של הייבוא: מה שבתוכה כבר יובא, גם כשהיא יושבת בתוך המקור."""
    now = time.time() if now is None else now
    pattern = re.compile(preset.pattern, re.IGNORECASE) if preset.pattern else None
    items: List[Item] = []
    if preset.kind == "steam":
        for path in (p for root in _steam_roots(preset.path) for p in _walk(root, True)):
            if os.path.basename(path).lower() != "session.mpd" or not _steam_is_saved_clip(path):
                continue
            size, newest = _steam_dir_stats(os.path.dirname(path))
            item = Item(path, "steam", size, newest)
            if not _seen(item, manifest) and now - newest >= STABLE_SECONDS:
                items.append(item)
    else:
        for path in _walk(preset.path, preset.recursive):
            name = os.path.basename(path)
            if not name.lower().endswith(IMPORT_EXTENSIONS) or (pattern and not pattern.search(name)) or _inside(path, exclude):
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            item = Item(path, "file", st.st_size, st.st_mtime)
            if st.st_size > 0 and not _seen(item, manifest) and now - st.st_mtime >= STABLE_SECONDS:
                items.append(item)
    return sorted(items, key=lambda i: i.mtime)[:MAX_FILES_PER_RUN]


def free_name(folder: str, name: str) -> str:
    stem, ext = os.path.splitext(name)
    candidate, number = os.path.join(folder, name), 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem}_{number}{ext}")
        number += 1
    return candidate


def _steam_is_saved_clip(mpd: str) -> bool:
    """gamerecordings\\clips\\clip_...\\ - קליפ שהמשתמש שמר. gamerecordings\\video\\bg_... - הקלטת הרקע, לא מייבאים."""
    parts = [p.lower() for p in os.path.normpath(mpd).split(os.sep)]
    return "clips" in parts and any(p.startswith("clip_") for p in parts)


def _steam_name(mpd: str) -> str:
    """gamerecordings\\clips\\clip_<appid>_<date>\\video\\bg_...\\session.mpd -> clip_<appid>_<date>.mp4"""
    parts = os.path.normpath(mpd).split(os.sep)
    clip = next((p for p in reversed(parts) if p.startswith("clip_")), None) \
        or next((p for p in reversed(parts) if p.startswith("bg_")), "steam_clip")   # הקלטת רקע בלי קליפ
    return clip + ".mp4"


def import_items(items: List[Item], dest: str, manifest_path: str, ffmpeg_exe: str, creationflags: int = 0,
                 on_progress: Optional[Callable[[int, int, str], None]] = None, failures: Optional[List[str]] = None) -> List[str]:
    """מחזיר את הקבצים שיובאו. מה שנכשל נאסף ב-failures (שם הקובץ והסיבה) והייבוא ממשיך לבא; כשאין מקום בדיסק - עוצרים."""
    os.makedirs(dest, exist_ok=True)
    manifest = load_manifest(manifest_path)
    failures = failures if failures is not None else []
    done: List[str] = []
    for index, item in enumerate(items, start=1):
        name = os.path.basename(item.source)
        target = free_name(dest, _steam_name(item.source) if item.kind == "steam" else name)
        partial = target + ".part"
        try:
            if shutil.disk_usage(dest).free < item.size + FREE_SPACE_MARGIN:
                failures.append(f"{name}: אין מספיק מקום פנוי בכונן של תיקיית ה-Import")
                break
            if item.kind == "steam":
                # מתוך התיקייה של ה-mpd: עם נתיב מוחלט בלוכסנים הפוכים ה-DASH demuxer לא פותח את הקטעים ("Failed to open an
                # initialization section"); בשם יחסי הוא פותר אותם נכון
                result = subprocess.run([ffmpeg_exe, "-hide_banner", "-y", "-i", name, "-map", "0", "-c", "copy",
                                         "-movflags", "+faststart", "-f", "mp4", os.path.abspath(partial)], capture_output=True,
                                        timeout=900, creationflags=creationflags, cwd=os.path.dirname(item.source))
                if result.returncode != 0:
                    raise OSError("ffmpeg לא הצליח לחבר את הקליפ")
            else:
                shutil.copy2(item.source, partial)
            os.replace(partial, target)
            os.utime(target, None)       # זמן שינוי = עכשיו: קליפ שיובא היום לא נחשב "ישן" בניקוי של Import
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(f"{name}: {error}")
            try:
                os.remove(partial)
            except OSError:
                pass
            continue
        manifest[item.key] = target
        manifest[item.name_key] = target
        done.append(target)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
        os.replace(tmp, manifest_path)
        if on_progress:
            on_progress(index, len(items), target)
    return done
