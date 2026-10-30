# utils/video/color_audio.py
#
# גל 25: כלי צבע ושמע מקצועיים לעורך-העל - בונים מחרוזות פילטר ל-ffmpeg:
#   צבע: שלושה גלגלי lift/gamma/gain (colorbalance - היסט R,G,B לצללים/אמצעיים/
#        הדגשות) ועקומות (curves - preset + נקודות לערוץ הראשי ול-R/G/B).
#   שמע: חיתוך נמוכים (highpass), EQ של שלושה פסים (bass/equalizer/treble),
#        קומפרסור (acompressor, שלוש הגדרות מוכנות) והפחתת רעש - afftdn מובנה,
#        או arnndn (רשת נוירונים לדיבור) כשנבחר קובץ מודל .rnnn.
# הכל טהור (בלי ffmpeg) - הקורא (my_scripts/video/video_editor.py) משלב את
# התוצאה בשרשרת. ערך ריק/ברירת מחדל = "" / [] (בלי פילטר בכלל).

import re
from typing import List, Optional, Sequence, Tuple

from utils.video.video_editor import _escape_ffmpeg_filter_path

# --- צבע ---

GRADE_RANGES = ("shadows", "midtones", "highlights")
CURVES_PRESETS: Tuple[str, ...] = (
    "none", "lighter", "darker", "increase_contrast", "linear_contrast", "medium_contrast",
    "strong_contrast", "vintage", "cross_process", "color_negative",
)
CURVE_CHANNELS = ("master", "red", "green", "blue")
MAX_CURVE_POINTS = 16
_NUM = r"-?\d+(?:\.\d+)?"
_TRIPLET_RE = re.compile(rf"^\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*$")


def parse_rgb_offsets(text: Optional[str]) -> Tuple[float, float, float]:
    """"r,g,b" (כל אחד -1..1) -> טאפל. ריק = (0,0,0). ValueError על פורמט לא תקין."""
    if text is None or not str(text).strip():
        return (0.0, 0.0, 0.0)
    match = _TRIPLET_RE.match(str(text))
    if not match:
        raise ValueError(f"צריך שלושה מספרים R,G,B (למשל 0.1,0,-0.05), התקבל: {text!r}")
    r, g, b = (max(-1.0, min(1.0, float(v))) for v in match.groups())
    return (r, g, b)


def build_colorbalance_filter(shadows: Optional[str] = None, midtones: Optional[str] = None, highlights: Optional[str] = None) -> str:
    """גלגלי lift/gamma/gain: היסט R,G,B לכל טווח בהירות. "" כשכולם אפס."""
    parts = []
    for prefix, text in (("s", shadows), ("m", midtones), ("h", highlights)):
        for channel, value in zip("rgb", parse_rgb_offsets(text)):
            if abs(value) >= 0.001:
                parts.append(f"{channel}{prefix}={value:.3f}")
    return "colorbalance=" + ":".join(parts) if parts else ""


def parse_curve_points(text: Optional[str]) -> List[Tuple[float, float]]:
    """"x/y x/y ..." (0..1, x עולה ממש, 2-16 נקודות) -> רשימה. ריק = [] (בלי עקומה)."""
    if text is None or not str(text).strip():
        return []
    points: List[Tuple[float, float]] = []
    for token in str(text).split():
        match = re.fullmatch(rf"({_NUM})/({_NUM})", token)
        if not match:
            raise ValueError(f"נקודה לא תקינה {token!r} - הפורמט הוא x/y (למשל 0.5/0.6)")
        x, y = float(match.group(1)), float(match.group(2))
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValueError(f"נקודה {token!r} מחוץ לטווח 0-1")
        if points and x <= points[-1][0]:
            raise ValueError("ערכי x חייבים לעלות משמאל לימין")
        points.append((x, y))
    if len(points) < 2:
        raise ValueError("עקומה צריכה לפחות שתי נקודות")
    if len(points) > MAX_CURVE_POINTS:
        raise ValueError(f"עד {MAX_CURVE_POINTS} נקודות לעקומה")
    return points


def _is_identity(points: Sequence[Tuple[float, float]]) -> bool:
    return all(abs(x - y) < 0.0005 for x, y in points) and points[0][0] == 0.0 and points[-1][0] == 1.0


def build_curves_filter(preset: Optional[str] = None, master: Optional[str] = None, red: Optional[str] = None,
                        green: Optional[str] = None, blue: Optional[str] = None) -> str:
    """curves עם preset ו/או נקודות. נקודות של ערוץ גוברות על ה-preset באותו ערוץ
    (התנהגות ffmpeg). עקומה זהותית (y=x) לא נשלחת. "" כשאין כלום."""
    preset = (preset or "none").strip()
    if preset not in CURVES_PRESETS:
        raise ValueError(f"preset עקומות לא מוכר: {preset!r}")
    parts = [f"preset={preset}"] if preset != "none" else []
    for channel, text in zip(CURVE_CHANNELS, (master, red, green, blue)):
        points = parse_curve_points(text)
        if points and not _is_identity(points):
            formatted = " ".join(f"{_fmt(x)}/{_fmt(y)}" for x, y in points)
            parts.append(f"{channel}='{formatted}'")
    return "curves=" + ":".join(parts) if parts else ""


def build_color_grade_filter(shadows: Optional[str] = None, midtones: Optional[str] = None, highlights: Optional[str] = None,
                             curves_preset: Optional[str] = None, curves_master: Optional[str] = None, curves_red: Optional[str] = None,
                             curves_green: Optional[str] = None, curves_blue: Optional[str] = None) -> str:
    """גלגלים ואז עקומות (כמו בתוכנות עריכה: איזון צבע ואחריו הטון הסופי)."""
    return ",".join(f for f in (
        build_colorbalance_filter(shadows, midtones, highlights),
        build_curves_filter(curves_preset, curves_master, curves_red, curves_green, curves_blue),
    ) if f)


# --- שמע ---

COMPRESSOR_PRESETS = {
    "gentle": "acompressor=threshold=-18dB:ratio=2:attack=20:release=250:makeup=2dB",
    "voice": "acompressor=threshold=-24dB:ratio=4:attack=5:release=150:makeup=5dB",
    "strong": "acompressor=threshold=-30dB:ratio=8:attack=3:release=100:makeup=8dB",
}
AUDIO_DENOISE_LEVELS = {
    "light": "afftdn=nr=6:nf=-50",
    "medium": "afftdn=nr=12:nf=-45",
    "strong": "afftdn=nr=20:nf=-40",
}
# arnndn: mix = כמה מהאות הנקי (1 = הכל) - אותן שלוש עוצמות
_RNN_MIX = {"light": 0.5, "medium": 0.8, "strong": 1.0}
EQ_LOW_HZ, EQ_HIGH_HZ = 120, 8000


def build_audio_denoise_filter(level: Optional[str], model_path: Optional[str] = None) -> str:
    level = (level or "off").strip()
    if level == "off":
        return ""
    if level not in AUDIO_DENOISE_LEVELS:
        raise ValueError(f"עוצמת הפחתת רעש לא מוכרת: {level!r}")
    model = (model_path or "").strip().strip('"')
    if model:
        return f"arnndn=m='{_escape_ffmpeg_filter_path(model)}':mix={_RNN_MIX[level]}"
    return AUDIO_DENOISE_LEVELS[level]


def build_audio_eq_filters(highpass_hz: float = 0, low_db: float = 0.0, mid_db: float = 0.0, mid_hz: float = 1000,
                           high_db: float = 0.0) -> List[str]:
    filters: List[str] = []
    if highpass_hz and highpass_hz > 0:
        filters.append(f"highpass=f={int(max(20, min(400, highpass_hz)))}")
    if abs(low_db) >= 0.05:
        filters.append(f"bass=g={_fmt(max(-20.0, min(20.0, low_db)))}:f={EQ_LOW_HZ}")
    if abs(mid_db) >= 0.05:
        freq = int(max(200, min(5000, mid_hz or 1000)))
        filters.append(f"equalizer=f={freq}:t=q:w=1:g={_fmt(max(-20.0, min(20.0, mid_db)))}")
    if abs(high_db) >= 0.05:
        filters.append(f"treble=g={_fmt(max(-20.0, min(20.0, high_db)))}:f={EQ_HIGH_HZ}")
    return filters


def build_audio_fx_chain(highpass_hz: float = 0, low_db: float = 0.0, mid_db: float = 0.0, mid_hz: float = 1000, high_db: float = 0.0,
                         compressor: Optional[str] = None, denoise: Optional[str] = None, denoise_model: Optional[str] = None) -> List[str]:
    """הסדר: חיתוך נמוכים -> הפחתת רעש -> EQ -> קומפרסור (לפני loudnorm, שבא אחריהם)."""
    chain: List[str] = []
    eq = build_audio_eq_filters(highpass_hz, low_db, mid_db, mid_hz, high_db)
    if eq and eq[0].startswith("highpass"):
        chain.append(eq.pop(0))
    noise = build_audio_denoise_filter(denoise, denoise_model)
    if noise:
        chain.append(noise)
    chain += eq
    compressor = (compressor or "off").strip()
    if compressor != "off":
        if compressor not in COMPRESSOR_PRESETS:
            raise ValueError(f"הגדרת קומפרסור לא מוכרת: {compressor!r}")
        chain.append(COMPRESSOR_PRESETS[compressor])
    return chain


def _fmt(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text
