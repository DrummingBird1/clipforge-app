# utils.video.video_editor_geometry - split out of the original module (no behavior change); the original module re-exports every name.

from typing import Any, List, Optional, Tuple
import re

from utils.video.video_editor_naming import WATERMARK_POSITIONS


def resolve_trim_bounds(duration: float, trim_start: float, trim_duration: Optional[float]) -> Tuple[float, float]:
    """מחזיר (effective_start, effective_duration) אחרי הצמדה (clamp) לגבולות
    האמיתיים של הקובץ (item: trim range) - trim_start/trim_duration שחורגים
    מהאורך בפועל נחתכים בעדינות במקום לגרום ל--ss/-t לא הגיוניים (שליליים/
    שעוברים את סוף הקובץ) ב-ffmpeg. (0.0, duration) אם אין חיתוך בפועל."""
    start = max(0.0, min(trim_start, duration))
    remaining = duration - start
    if trim_duration is None:
        effective_duration = remaining
    else:
        effective_duration = max(0.0, min(trim_duration, remaining))
    return start, effective_duration


_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")


_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def parse_silence_intervals(ffmpeg_stderr: str, duration: Optional[float] = None) -> List[Tuple[float, float]]:
    """מפרש פלט stderr של ffmpeg's silencedetect filter לרשימת (start, end)
    שניות (item: auto-trim silence). silence_start תמיד כתוב לפני ה-silence_end
    התואם לו (ffmpeg כותב כרונולוגית), אז זיווג לפי סדר-הופעה בטקסט נכון.
    שקט אחרון שנמשך עד סוף הקובץ לא מקבל שורת silence_end בכלל (ה-EOF קוטע
    אותו) - אם duration ניתן, "סוגרים" אותו ידנית שם במקום להשמיט אותו בשקט."""
    starts = [float(m.group(1)) for m in _SILENCE_START_RE.finditer(ffmpeg_stderr)]
    ends = [float(m.group(1)) for m in _SILENCE_END_RE.finditer(ffmpeg_stderr)]
    intervals = list(zip(starts, ends))
    if len(starts) > len(ends) and duration is not None:
        intervals.append((starts[-1], duration))
    return intervals


def compute_silence_trim_bounds(
    duration: float, silence_intervals: List[Tuple[float, float]], min_silence_seconds: float = 0.3
) -> Tuple[float, Optional[float]]:
    """מחזיר (trim_start, trim_duration) לפי שקט *בקצוות* הקובץ בלבד (item:
    auto-trim silence) - שקט באמצע הקובץ לא נחתך, זה trim, לא ניקוי-שקטים
    כללי. מתעלם משקט קצר מ-min_silence_seconds בקצה (רעש רקע/מיקרו-פאוזה לא
    נחשב "פתיח/סיום שקט" אמיתי). (0.0, None) - כלומר "בלי שינוי" - אם אין
    שקט משמעותי בקצה כלשהו."""
    if not silence_intervals:
        return 0.0, None

    trim_start = 0.0
    first_start, first_end = silence_intervals[0]
    if first_start <= 0.05 and (first_end - first_start) >= min_silence_seconds:
        trim_start = first_end

    trim_end = duration
    last_start, last_end = silence_intervals[-1]
    if last_end >= duration - 0.05 and (last_end - last_start) >= min_silence_seconds:
        trim_end = last_start

    trim_end = max(trim_end, trim_start)
    trim_duration = trim_end - trim_start
    if trim_start <= 0.0 and trim_duration >= duration - 0.01:
        return 0.0, None
    return trim_start, trim_duration


def _resolve_position_xy(frame_width: int, frame_height: int, target_w: int, target_h: int, position: str, margin: int) -> Tuple[int, int]:
    """חלק המיקום/הידוק (clamp) המשותף ל-compute_watermark_geometry ול-
    compute_removal_region - שתיהן צריכות בדיוק את אותה לוגיקת פינה/מרכז+margin,
    ההבדל היחיד ביניהן הוא איך target_w/target_h עצמם מחושבים."""
    if position not in WATERMARK_POSITIONS:
        raise ValueError(f"מיקום לא מוכר: {position!r} (אפשרויות: {', '.join(WATERMARK_POSITIONS)})")

    x_by_position = {
        "top-left": margin,
        "bottom-left": margin,
        "top-right": frame_width - target_w - margin,
        "bottom-right": frame_width - target_w - margin,
        "top-center": (frame_width - target_w) // 2,
        "bottom-center": (frame_width - target_w) // 2,
        "center": (frame_width - target_w) // 2,
    }
    y_by_position = {
        "top-left": margin,
        "top-right": margin,
        "top-center": margin,
        "bottom-left": frame_height - target_h - margin,
        "bottom-right": frame_height - target_h - margin,
        "bottom-center": frame_height - target_h - margin,
        "center": (frame_height - target_h) // 2,
    }

    x = max(0, min(x_by_position[position], max(0, frame_width - target_w)))
    y = max(0, min(y_by_position[position], max(0, frame_height - target_h)))
    return x, y


def compute_watermark_geometry(
    output_width: int,
    output_height: int,
    watermark_width: int,
    watermark_height: int,
    position: str,
    scale_fraction: float = 0.15,
    margin: int = 20,
    custom_center_fraction: Optional[Tuple[float, float]] = None,
) -> Tuple[int, int, int, int]:
    """מחשב את גודל ה-watermark המוקטן (שומר יחס גובה-רוחב מקורי לפי scale_fraction
    מרוחב הפלט) ואת מיקומו (x,y) בפיקסלים, לפי פינה/מרכז נבחר. מחזיר
    (target_w, target_h, x, y). התוצאה תמיד מהודקת (clamp) בתוך גבולות הפריים
    כדי שwatermark גדול/margin גדול מדי לא "יברח" מחוץ למסך.

    custom_center_fraction (item: גרירת watermark חופשית) - (x_fraction, y_fraction)
    של *מרכז* ה-watermark כאחוז מרוחב/גובה הפלט (0.0-1.0), גובר על position
    כליל כשניתן - כך שגרירה על תצוגה מקדימה לא תלויה בפינה/מרכז קבועים.
    מרכז (לא פינה עליונה-שמאלית) כדי שגודל ה-watermark יוכל להשתנות
    (scale_fraction) בלי שהנקודה שהמשתמש בפועל גרר-אליה "תזוז" בעקבות זה -
    היא נשארת מרכז ה-watermark בכל גודל. position עדיין נדרש ותקין (לא
    None) גם במצב הזה, רק לא בשימוש בפועל - נשאר ה-preset האחרון שנבחר,
    כדי שחזרה למצב "preset" (בלי custom_center_fraction) תמשיך משם."""
    if watermark_width <= 0 or watermark_height <= 0:
        raise ValueError("מידות ה-watermark חייבות להיות חיוביות")
    if scale_fraction <= 0:
        raise ValueError("scale_fraction חייב להיות חיובי")

    target_w = max(1, int(output_width * scale_fraction))
    target_h = max(1, round(target_w * watermark_height / watermark_width))
    # scale_fraction בלבד מגביל רק את הרוחב - watermark עם יחס-גובה-רוחב קיצוני
    # (צר וגבוה מאוד) יכול עדיין לצאת עם target_h שגדול מ-output_height עצמו
    # (נמצא ע"י בדיקת property-based, לא שימוש רגיל - לוגו רגיל לא מגיע לזה).
    # אם זה קורה, עוברים לגזירה לפי גובה במקום רוחב, ושומרים על יחס-גובה-רוחב.
    if target_h > output_height:
        target_h = max(1, output_height)
        target_w = max(1, round(target_h * watermark_width / watermark_height))
    if custom_center_fraction is not None:
        cx_fraction, cy_fraction = custom_center_fraction
        cx_fraction = max(0.0, min(1.0, cx_fraction))
        cy_fraction = max(0.0, min(1.0, cy_fraction))
        x = round(cx_fraction * output_width - target_w / 2)
        y = round(cy_fraction * output_height - target_h / 2)
        x = max(0, min(x, max(0, output_width - target_w)))
        y = max(0, min(y, max(0, output_height - target_h)))
    else:
        x, y = _resolve_position_xy(output_width, output_height, target_w, target_h, position, margin)
    return target_w, target_h, x, y


def compute_removal_region(
    frame_width: int,
    frame_height: int,
    position: str,
    width_fraction: float = 0.2,
    height_fraction: float = 0.12,
    margin: int = 20,
) -> Tuple[int, int, int, int]:
    """מחשב אזור מלבני (x, y, w, h) למחיקת watermark ישן (ffmpeg delogo) - אותה
    מערכת מיקום/margin בדיוק כמו compute_watermark_geometry, אבל בלי תמונת
    מקור שממנה אפשר לגזור יחס-גובה-רוחב: אין "watermark חדש" למחוק, רק אזור
    ישן שגודלו נגזר ישירות משברי רוחב/גובה הפריים (ברירת המחדל - 20%/12% -
    נדיבה במכוון, עדיף למחוק קצת יותר משטח נקי סביב הלוגו מאשר להשאיר שארית
    שלו גלויה). מחזיר (x, y, w, h) - סדר שונה מ-compute_watermark_geometry
    בכוונה, כדי להתאים ישירות לארגומנטים של פילטר ffmpeg delogo=x:y:w:h."""
    if width_fraction <= 0 or height_fraction <= 0:
        raise ValueError("width_fraction/height_fraction חייבים להיות חיוביים")

    target_w = max(2, int(frame_width * width_fraction))
    target_h = max(2, int(frame_height * height_fraction))
    x, y = _resolve_position_xy(frame_width, frame_height, target_w, target_h, position, margin)
    return x, y, target_w, target_h


def parse_region_fractions(text: Any) -> Optional[Tuple[float, float, float, float]]:
    """item 50 (בחירת אזור מחיקת-watermark בגרירת מלבן): "x,y,w,h" כשברים
    (0-1) של פריים המקור -> tuple, או None על ריק/לא-תקין/אזור ריק."""
    if text is None:
        return None
    parts = str(text).replace(" ", "").split(",")
    if len(parts) != 4:
        return None
    try:
        x, y, w, h = (float(p) for p in parts)
    except ValueError:
        return None
    if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0):
        return None
    return x, y, min(w, 1 - x), min(h, 1 - y)


def compute_custom_removal_region(frame_width: int, frame_height: int, fractions: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    """(x, y, w, h) בפיקסלים לפילטר delogo מאזור שסומן ידנית. delogo דורש שהאזור
    יהיה כולו בתוך הפריים ולא יגע בקצה (הוא מטשטש לפי הפיקסלים *סביב* האזור) -
    לכן מהודק למרווח של פיקסל אחד לפחות מכל קצה, ולגודל מינימלי של 2x2."""
    fx, fy, fw, fh = fractions
    x = max(1, min(int(round(fx * frame_width)), frame_width - 3))
    y = max(1, min(int(round(fy * frame_height)), frame_height - 3))
    w = max(2, min(int(round(fw * frame_width)), frame_width - 1 - x))
    h = max(2, min(int(round(fh * frame_height)), frame_height - 1 - y))
    return x, y, w, h
