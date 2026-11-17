# utils/media/moment_finder.py
#
# 16.11.2026 (ClipForge 2.0): "קליפ ארוך לכמה שורטס" - הרגעים הכי חזקים בהקלטה ארוכה או VOD. אותו מדד כמו "זהה הייליטס"
# (utils/video/highlight_detect.py: עוצמת שמע בנתחים של 100ms, סף = ממוצע + offset), אבל במקום טווחים לשמירה - N חלונות
# באורך של Short, שלא חופפים, מהחזק לחלש. השיא יושב ב-70% מהחלון (הבנייה לפניו, התגובה אחריו).
from typing import List, NamedTuple, Sequence

from utils.video.highlight_detect import CHUNK_MS, DEFAULT_THRESHOLD_OFFSET_DB


class Moment(NamedTuple):
    start: float
    end: float
    peak: float      # שניות מתחילת הקובץ
    score: float     # dB מעל הממוצע

    @property
    def peak_in_clip(self) -> float:
        return self.peak - self.start


def find_moments(chunk_dbfs: Sequence[float], average_dbfs: float, duration: float, count: int = 5, length: float = 30.0,
                 threshold_offset_db: float = DEFAULT_THRESHOLD_OFFSET_DB, chunk_ms: int = CHUNK_MS,
                 peak_position: float = 0.7) -> List[Moment]:
    """עד count רגעים באורך length (קצר יותר אם הקובץ קצר), לפי סדר הזמן. נתח מעל הסף = מועמד; בוחרים מהחזק לחלש,
    ומדלגים על מועמד שהחלון שלו חופף לחלון שכבר נבחר."""
    if duration <= 0 or count <= 0:
        return []
    length = min(length, duration)
    threshold = average_dbfs + threshold_offset_db
    candidates = sorted(((value, i * chunk_ms / 1000.0) for i, value in enumerate(chunk_dbfs) if value > threshold), reverse=True)
    chosen: List[Moment] = []
    for value, peak in candidates:
        start = min(max(0.0, peak - length * peak_position), duration - length)
        end = start + length
        if any(start < m.end and m.start < end for m in chosen):
            continue
        chosen.append(Moment(round(start, 2), round(end, 2), round(peak, 2), round(value - average_dbfs, 1)))
        if len(chosen) == count:
            break
    return sorted(chosen, key=lambda m: m.start)
