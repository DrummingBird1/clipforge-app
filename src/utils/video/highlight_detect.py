# utils/video/highlight_detect.py
#
# item 85 (102-ההצעות, גל 7): "זהה הייליטס" מתוך עורך-העל - ממלא את "חיתוך כמה
# טווחים" אוטומטית כך שנשארים רק הרגעים הרועשים (שיאי שמע), והשאר מוסר. אותו
# אלגוריתם בדיוק כמו שלב-השמע של my_scripts/video/story_cutter.py (נתחים של 100ms,
# סף דינמי = עוצמה-ממוצעת + offset, מרווח מינימלי בין שיאים, חלון לפני/אחרי כל
# שיא) - בלי שלב ה-AI/Gemini שלו, כדי שזה יהיה מיידי, מקומי וחינמי. לוגיקה טהורה
# (רשימות מספרים פנימה/החוצה) כדי שאפשר לבדוק בלי אודיו אמיתי.

from typing import Any, Dict, List, Sequence, Tuple

CHUNK_MS = 100
DEFAULT_THRESHOLD_OFFSET_DB = 18.0  # זהה ל-story_cutter.py's --threshold
DEFAULT_BEFORE_SECONDS = 20.0       # זהה ל-story_cutter.py's --before
DEFAULT_AFTER_SECONDS = 5.0         # זהה ל-story_cutter.py's --after
DEFAULT_MIN_GAP_SECONDS = 15.0      # story_cutter משתמש ב-60 לקליפים נפרדים; כאן הטווחים מתמזגים, אז צפוף יותר


def find_audio_peaks(chunk_max_dbfs: Sequence[float], average_dbfs: float, threshold_offset_db: float = DEFAULT_THRESHOLD_OFFSET_DB,
                     min_gap_seconds: float = DEFAULT_MIN_GAP_SECONDS, chunk_ms: int = CHUNK_MS) -> List[float]:
    """זמני שיאים (שניות) - נתח שה-max_dBFS שלו מעל average+offset, עם מרווח
    מינימלי בין שיאים (שיא "רועש" אחד לא יוצר עשרות נקודות צמודות)."""
    threshold = average_dbfs + threshold_offset_db
    peaks: List[float] = []
    last = -min_gap_seconds
    for i, value in enumerate(chunk_max_dbfs):
        t = i * chunk_ms / 1000.0
        if value > threshold and t - last >= min_gap_seconds:
            peaks.append(t)
            last = t
    return peaks


def peaks_to_keep_windows(peaks: Sequence[float], duration: float, before: float = DEFAULT_BEFORE_SECONDS,
                          after: float = DEFAULT_AFTER_SECONDS) -> List[Tuple[float, float]]:
    """חלון [שיא-before, שיא+after] לכל שיא, מהודק לאורך הקובץ ומאוחד כשחלונות חופפים."""
    windows = sorted((max(0.0, p - before), min(duration, p + after)) for p in peaks)
    merged: List[Tuple[float, float]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        elif end > start:
            merged.append((start, end))
    return merged


def keep_windows_to_remove_ranges(keep: Sequence[Tuple[float, float]], duration: float, min_range_seconds: float = 0.5) -> List[List[float]]:
    """המשלים של חלונות-השמירה = הטווחים להסרה (בפורמט של --remove-ranges).
    פערים קצרים מ-min_range_seconds לא מוסרים (לא שווה חיתוך של חצי-שנייה)."""
    ranges: List[List[float]] = []
    cursor = 0.0
    for start, end in sorted(keep):
        if start - cursor >= min_range_seconds:
            ranges.append([round(cursor, 2), round(start, 2)])
        cursor = max(cursor, end)
    if duration - cursor >= min_range_seconds:
        ranges.append([round(cursor, 2), round(duration, 2)])
    return ranges


def chunk_levels_dbfs(samples: Sequence[float], sample_rate: int, chunk_ms: int = CHUNK_MS) -> Tuple[List[float], float]:
    """(max_dBFS לכל נתח, ממוצע RMS-dBFS של כל הקובץ) מדגימות מונו מנורמלות
    ל-[-1, 1] - אותן שתי מידות בדיוק ש-story_cutter מקבל מ-pydub (chunk.max_dBFS /
    audio.dBFS), בלי לטעון את כל הקובץ כ-AudioSegment (איטי מאוד על הקלטות ארוכות)."""
    import numpy as np

    data = np.abs(np.asarray(samples, dtype=np.float64))
    if data.size == 0:
        return [], -120.0
    chunk = max(1, int(sample_rate * chunk_ms / 1000))
    count = data.size // chunk
    peaks: List[float] = []
    if count:
        maxima = data[: count * chunk].reshape(count, chunk).max(axis=1)
        peaks = [float(20 * np.log10(v)) if v > 0 else -120.0 for v in maxima]
    rms = float(np.sqrt(np.mean(np.square(data))))
    return peaks, (float(20 * np.log10(rms)) if rms > 0 else -120.0)


def decode_mono_samples(path: str, ffmpeg_exe: str = "ffmpeg", sample_rate: int = 8000):
    """מפענח את פס-הקול לדגימות מונו float ב-[-1, 1] (8kHz מספיק לזיהוי שיאי עוצמה,
    ושעה של הקלטה היא ~58MB בלבד). None אם אין שמע/הפענוח נכשל."""
    import subprocess

    import numpy as np

    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

    result = subprocess.run(
        [ffmpeg_exe, "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"],
        capture_output=True, timeout=900, creationflags=NO_WINDOW_FLAGS,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    return np.frombuffer(result.stdout, dtype="<i2").astype(np.float64) / 32768.0


def detect_highlight_ranges(path: str, ffmpeg_exe: str = "ffmpeg", threshold_offset_db: float = DEFAULT_THRESHOLD_OFFSET_DB,
                            before: float = DEFAULT_BEFORE_SECONDS, after: float = DEFAULT_AFTER_SECONDS,
                            min_gap_seconds: float = DEFAULT_MIN_GAP_SECONDS, sample_rate: int = 8000) -> Dict[str, Any]:
    """הצינור המלא: פענוח -> רמות לכל נתח -> שיאים -> חלונות-שמירה -> טווחים להסרה."""
    samples = decode_mono_samples(path, ffmpeg_exe, sample_rate)
    if samples is None or len(samples) == 0:
        raise ValueError("לא נמצא פס-קול בקובץ - אין ממה לזהות הייליטס.")
    duration = len(samples) / float(sample_rate)
    levels, average = chunk_levels_dbfs(samples, sample_rate)
    peaks = find_audio_peaks(levels, average, threshold_offset_db, min_gap_seconds)
    keep = peaks_to_keep_windows(peaks, duration, before, after)
    return {
        "duration": round(duration, 2), "average_dbfs": round(average, 1), "peaks": [round(p, 2) for p in peaks],
        "keep": [[round(s, 2), round(e, 2)] for s, e in keep],
        "remove_ranges": keep_windows_to_remove_ranges(keep, duration) if keep else [],
        "kept_seconds": round(sum(e - s for s, e in keep), 1),
    }
