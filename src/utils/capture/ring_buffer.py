# utils/capture/ring_buffer.py
#
# 16.11.2026 (2.0): replay buffer של מנוע ההקלטה המובנה. ffmpeg כותב קטעים קצרים (segment muxer, seg_000001.ts...) לתיקייה
# זמנית, והקוד כאן: אילו קטעים לשמור כשלוחצים "שמור את X השניות האחרונות", אילו למחוק (חלון + תקרת דיסק), ורשימת ה-concat
# לחיבור בלי קידוד מחדש (-c copy). הכל טהור - רשימות קבצים, בלי ffmpeg - חוץ מ-save_command שרק בונה את הפקודה.
import math
import os
import re
from typing import List, NamedTuple, Optional

SEGMENT_PATTERN = "seg_%06d.ts"
_SEGMENT_NAME = re.compile(r"^seg_(\d{6})\.ts$")
DEFAULT_SEGMENT_SECONDS = 2
DEFAULT_MAX_BYTES = 8 * 1024 ** 3   # 8GB - 4K60 ב-~80Mbps הוא ~10 דקות


class Segment(NamedTuple):
    index: int
    path: str
    size: int


def list_segments(folder: str) -> List[Segment]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    found = []
    for name in names:
        match = _SEGMENT_NAME.match(name)
        if not match:
            continue
        path = os.path.join(folder, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        found.append(Segment(int(match.group(1)), path, size))
    return sorted(found)


def finished(segments: List[Segment]) -> List[Segment]:
    """בלי האחרון - ffmpeg עוד כותב אליו."""
    return segments[:-1]


def select_for_save(segments: List[Segment], seconds: float, segment_seconds: float = DEFAULT_SEGMENT_SECONDS) -> List[Segment]:
    """הקטעים הגמורים שמכסים את X השניות האחרונות (קטע אחד נוסף, כי הקטע הראשון בחלון חלקי)."""
    done = finished(segments)
    if seconds <= 0 or not done:
        return []
    count = math.ceil(seconds / segment_seconds) + 1
    return done[-count:]


def to_delete(segments: List[Segment], keep_seconds: float, segment_seconds: float = DEFAULT_SEGMENT_SECONDS,
              max_bytes: int = DEFAULT_MAX_BYTES) -> List[Segment]:
    """מה למחוק: כל מה שמעבר לחלון (keep_seconds + מרווח של 2 קטעים), ועוד מהישנים כשהסך עובר את max_bytes.
    האחרון (נכתב עכשיו) לעולם לא נמחק."""
    if len(segments) <= 1:
        return []
    keep_count = math.ceil(keep_seconds / segment_seconds) + 2
    old = segments[:-keep_count] if len(segments) > keep_count else []
    kept = segments[len(old):]
    total = sum(s.size for s in kept)
    extra = []
    for segment in kept[:-1]:
        if total <= max_bytes:
            break
        extra.append(segment)
        total -= segment.size
    return old + extra


def concat_list(paths: List[str]) -> str:
    """תוכן קובץ הרשימה של concat demuxer - גרש בנתיב נכתב כ-'\\'' (כמו בתיעוד של ffmpeg)."""
    lines = []
    for path in paths:
        escaped = path.replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def save_command(ffmpeg_exe: str, list_path: str, output_path: str, mp4: Optional[bool] = None) -> List[str]:
    """חיבור הקטעים בלי קידוד מחדש. ל-MP4: faststart (aac_adtstoasc ל-AAC מ-MPEG-TS - ffmpeg מוסיף בעצמו, ודגל מפורש
    נכשל על שמע שאינו AAC)."""
    is_mp4 = output_path.lower().endswith(".mp4") if mp4 is None else mp4
    cmd = [ffmpeg_exe, "-hide_banner", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-map", "0", "-c", "copy"]
    if is_mp4:
        cmd += ["-movflags", "+faststart"]
    return cmd + [output_path]
