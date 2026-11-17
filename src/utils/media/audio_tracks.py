# utils/media/audio_tracks.py
#
# 17.11.2026 (ClipForge 2.0.1): ערוצי השמע של קובץ, בשביל ערבוב המיקרופון. ב-2.0.0 ערוץ מיקרופון שלא קיים בקובץ (פרופיל עם
# ערוץ 1 על קליפ עם ערוץ אחד, או הקלטה בלי שמע משחק שבה המיקרופון הוא הערוץ היחיד) הפיל את הרינדור של אותו קובץ.
#   - audio_titles: הכותרת של כל ערוץ שמע לפי הסדר ("" כשאין). מסך ההקלטה של ClipForge כותב "game" ו-"mic".
#   - usable_mic_track: הערוץ המבוקש אם הוא קיים ואינו ערוץ המשחק, אחרת None.
#   - find_mic_track: ערוץ שכותרתו "mic" ואינו הראשון - כך הקלטה של ClipForge מקבלת את הקול בלי לבחור כלום.
import json
import subprocess
from typing import List, Optional

from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

MIC_TITLES = ("mic", "microphone", "מיקרופון")


def audio_titles(path: str, ffprobe_exe: str, timeout: float = 30.0) -> Optional[List[str]]:
    """רשימת הכותרות (באותיות קטנות) של ערוצי השמע, או None כש-ffprobe לא רץ."""
    try:
        out = subprocess.run([ffprobe_exe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index:stream_tags=title",
                              "-of", "json", path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                             creationflags=NO_WINDOW_FLAGS)
        if out.returncode != 0:
            return None
        streams = json.loads(out.stdout or "{}").get("streams") or []
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return [str((stream.get("tags") or {}).get("title") or "").strip().lower() for stream in streams]


def usable_mic_track(titles: Optional[List[str]], requested: Optional[int], game_track: int = 0) -> Optional[int]:
    """requested כשאפשר לערבב אותו, אחרת None. titles=None (לא ידוע) - סומכים על המבקש, כמו קודם."""
    if requested is None or requested < 0:
        return None
    if titles is None:
        return requested
    return requested if requested < len(titles) and requested != game_track else None


def find_mic_track(titles: Optional[List[str]], game_track: int = 0) -> Optional[int]:
    for index, title in enumerate(titles or []):
        if index != game_track and title in MIC_TITLES:
            return index
    return None
