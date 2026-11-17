# utils/capture/importer.py
#
# 16.11.2026 (2.0): ייבוא קליפים מתוכנות הקלטה וקונסולות (import_presets.py) לתיקיית ה-Import - בלחיצה.
# - רק קבצים חדשים: manifest (workspace/.cache/import_manifest.json) לפי נתיב + גודל + זמן שינוי, כך שייבוא חוזר מאותו
#   כונן USB לא מעתיק שוב. קובץ ששונה לפני פחות מ-STABLE_SECONDS - עוד נכתב, מדלגים.
# - המקור לא נמחק ולא זז - זה כונן ה-USB / כרטיס ה-SD של המשתמש. מעתיקים לשם פנוי (_2, _3...) ב-Import.
# - Steam שומר DASH (session.mpd + קטעי m4s) - remux ל-MP4 ב-ffmpeg, בלי קידוד מחדש.
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


class Item(NamedTuple):
    source: str      # קובץ וידאו, או session.mpd של Steam
    kind: str        # file / steam
    size: int
    mtime: float

    @property
    def key(self) -> str:
        return f"{os.path.normcase(os.path.abspath(self.source))}|{self.size}|{int(self.mtime)}"


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


def find_new(preset: Preset, manifest: Dict[str, str], now: Optional[float] = None) -> List[Item]:
    now = time.time() if now is None else now
    pattern = re.compile(preset.pattern, re.IGNORECASE) if preset.pattern else None
    items: List[Item] = []
    if preset.kind == "steam":
        for path in (p for root in _steam_roots(preset.path) for p in _walk(root, True)):
            if os.path.basename(path).lower() != "session.mpd":
                continue
            size, newest = _steam_dir_stats(os.path.dirname(path))
            item = Item(path, "steam", size, newest)
            if item.key not in manifest and now - newest >= STABLE_SECONDS:
                items.append(item)
    else:
        for path in _walk(preset.path, preset.recursive):
            name = os.path.basename(path)
            if not name.lower().endswith(IMPORT_EXTENSIONS) or (pattern and not pattern.search(name)):
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            item = Item(path, "file", st.st_size, st.st_mtime)
            if st.st_size > 0 and item.key not in manifest and now - st.st_mtime >= STABLE_SECONDS:
                items.append(item)
    return sorted(items, key=lambda i: i.mtime)[:MAX_FILES_PER_RUN]


def free_name(folder: str, name: str) -> str:
    stem, ext = os.path.splitext(name)
    candidate, number = os.path.join(folder, name), 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{stem}_{number}{ext}")
        number += 1
    return candidate


def _steam_name(mpd: str) -> str:
    """gamerecordings\\clips\\clip_<appid>_<date>\\video\\bg_...\\session.mpd -> clip_<appid>_<date>.mp4"""
    parts = os.path.normpath(mpd).split(os.sep)
    clip = next((p for p in reversed(parts) if p.startswith("clip_")), None) \
        or next((p for p in reversed(parts) if p.startswith("bg_")), "steam_clip")   # הקלטת רקע בלי קליפ
    return clip + ".mp4"


def import_items(items: List[Item], dest: str, manifest_path: str, ffmpeg_exe: str, creationflags: int = 0,
                 on_progress: Optional[Callable[[int, int, str], None]] = None) -> List[str]:
    os.makedirs(dest, exist_ok=True)
    manifest = load_manifest(manifest_path)
    done: List[str] = []
    for index, item in enumerate(items, start=1):
        if item.kind == "steam":
            target = free_name(dest, _steam_name(item.source))
            # מתוך התיקייה של ה-mpd: עם נתיב מוחלט בלוכסנים הפוכים ה-DASH demuxer לא פותח את הקטעים ("Failed to open an
            # initialization section"); בשם יחסי הוא פותר אותם נכון
            result = subprocess.run([ffmpeg_exe, "-hide_banner", "-y", "-i", os.path.basename(item.source), "-map", "0", "-c", "copy",
                                     "-movflags", "+faststart", os.path.abspath(target)], capture_output=True, timeout=900,
                                    creationflags=creationflags, cwd=os.path.dirname(item.source))
            if result.returncode != 0:
                if os.path.exists(target):
                    os.remove(target)
                continue
        else:
            target = free_name(dest, os.path.basename(item.source))
            shutil.copy2(item.source, target)
        manifest[item.key] = target
        done.append(target)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        tmp = manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False)
        os.replace(tmp, manifest_path)
        if on_progress:
            on_progress(index, len(items), target)
    return done
