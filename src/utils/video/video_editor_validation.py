# utils/video/video_editor_validation.py
#
# item 44 (102-ההצעות, גל 4): "בדיקת הגדרות עם שגיאה ליד השדה" - שני שלבים:
#   1. validate_fields - בדיקות סטטיות טהורות (קיום קבצים, פורמט צבע/זמן/FPS/
#      תבנית-שם/טווחים) שמחזירות {שדה: הודעה} - מיידיות, בלי להריץ ffmpeg.
#   2. map_ffmpeg_error_to_field - אחרי ריצת --validate-only אמיתית (שרשרת
#      הפילטרים המלאה מול ffmpeg), מתרגמת את ה-stderr של [INVALID] לשדה שכנראה
#      גרם לו, כדי שההודעה תופיע ליד השדה הנכון ולא רק כגוש טקסט בלוג.
# מופרד מ-utils/video/video_editor.py (בניית פילטרים) - זה ממשק-משתמש/אבחון, לא רינדור.

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from utils.video.color_audio import parse_curve_points, parse_rgb_offsets
from utils.video.video_editor import parse_fps_value, parse_time_seconds, validate_output_template

PATH_FIELDS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "watermark_path": ("קובץ ה-watermark", (".png", ".jpg", ".jpeg", ".webp", ".bmp")),
    "pip_path": ("קובץ ה-PiP", (".mp4", ".mkv", ".mov", ".avi", ".webm")),
    "lut_path": ("קובץ ה-LUT", (".cube", ".3dl")),
    "audio_denoise_model": ("קובץ מודל הפחתת הרעש", (".rnnn",)),
    "replace_audio_path": ("קובץ פס-הקול", (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".mp4", ".mkv", ".mov", ".avi", ".webm")),
}
TIME_FIELDS = ("trim_start", "trim_duration", "target_seconds", "fade_in_seconds", "fade_out_seconds")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_HEX0X_RE = re.compile(r"^0x[0-9a-fA-F]{6}$")


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_remove_ranges(raw: Any) -> Optional[str]:
    """None אם תקין (או ריק), אחרת הודעת-שגיאה קריאה."""
    if _blank(raw):
        return None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return "הטווחים אינם JSON תקין"
    if not isinstance(parsed, list):
        return "הטווחים חייבים להיות רשימה של [התחלה, סוף]"
    for index, item in enumerate(parsed, start=1):
        if not (isinstance(item, list) and len(item) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in item)):
            return f"טווח #{index} לא בפורמט [התחלה, סוף]"
        if not item[1] > item[0] >= 0:
            return f"טווח #{index}: הסוף חייב להיות אחרי ההתחלה"
    return None


def validate_fields(payload: Dict[str, Any], known_fonts: Optional[List[str]] = None) -> Dict[str, str]:
    """{שדה: הודעה} לכל שדה עם בעיה ודאית. known_fonts (אופציונלי) - רשימת
    משפחות-הגופן המותקנות; גופן שלא נמצא בה מדווח כאזהרה ('⚠️' בתחילת ההודעה),
    לא כשגיאה - libass/fontconfig נופלים לגופן חלופי ולא נכשלים."""
    errors: Dict[str, str] = {}
    for field, (label, extensions) in PATH_FIELDS.items():
        value = payload.get(field)
        if _blank(value):
            continue
        path = str(value).strip().strip('"')
        if not os.path.exists(path):
            errors[field] = f"{label} לא נמצא: {path}"
        elif os.path.isdir(path):
            errors[field] = f"{label} הוא תיקייה, לא קובץ"
        elif os.path.splitext(path)[1].lower() not in extensions:
            errors[field] = f"⚠️ סוג קובץ לא צפוי ל{label} ({os.path.splitext(path)[1] or 'בלי סיומת'})"

    fps = payload.get("fps")
    if not _blank(fps):
        try:
            parse_fps_value(str(fps))
        except ValueError as e:
            errors["fps"] = str(e)

    template = payload.get("output_template")
    if not _blank(template):
        try:
            validate_output_template(str(template).strip())
        except ValueError as e:
            errors["output_template"] = f"תבנית שם לא תקינה - {e} (זמינים: {{name}} {{codec}} {{orientation}} {{date}} {{number}})"

    ranges_error = validate_remove_ranges(payload.get("remove_ranges"))
    if ranges_error:
        errors["remove_ranges"] = ranges_error

    for field in TIME_FIELDS:
        value = payload.get(field)
        if not _blank(value) and parse_time_seconds(value) is None:
            errors[field] = "זמן לא תקין - השתמש בשניות (90) או mm:ss (1:30)"

    for field in ("caption_color", "text_color"):
        value = payload.get(field)
        if not _blank(value) and not _HEX_RE.match(str(value).strip()):
            errors[field] = "צבע חייב להיות בפורמט #RRGGBB"
    for field in ("chromakey_color", "chromakey_bg_color"):
        value = payload.get(field)
        if payload.get("chromakey") and not _blank(value) and not _HEX0X_RE.match(str(value).strip()):
            errors[field] = "צבע חייב להיות בפורמט 0xRRGGBB"

    # גל 25: גלגלי צבע ועקומות - אותו parser של הרינדור (utils/video/color_audio.py)
    for field in ("grade_shadows", "grade_midtones", "grade_highlights"):
        value = payload.get(field)
        if not _blank(value):
            try:
                parse_rgb_offsets(str(value))
            except ValueError as e:
                errors[field] = str(e)
    for field in ("curves_master", "curves_red", "curves_green", "curves_blue"):
        value = payload.get(field)
        if not _blank(value):
            try:
                parse_curve_points(str(value))
            except ValueError as e:
                errors[field] = str(e)

    # גל 26: קליפ B-roll (שכבת וידאו) שלא קיים - אחרת השכבה פשוט נעלמת בשקט ברינדור
    raw_layers = payload.get("layers")
    if isinstance(raw_layers, str):
        try:
            raw_layers = json.loads(raw_layers) if raw_layers.strip() else []
        except ValueError:
            raw_layers = []
    for layer in raw_layers if isinstance(raw_layers, list) else []:
        if isinstance(layer, dict) and layer.get("type") == "video":
            path = str(layer.get("path") or "").strip().strip('"')
            if not path:
                errors["layers"] = "לשכבת B-roll חסר קליפ"
            elif not os.path.isfile(path):
                errors["layers"] = f"קליפ ה-B-roll לא נמצא: {path}"

    target_size = payload.get("target_size_mb")
    if not _blank(target_size):
        try:
            if float(str(target_size)) <= 0:
                errors["target_size_mb"] = "יעד הגודל חייב להיות חיובי (או ריק לכיבוי)"
        except (TypeError, ValueError):
            errors["target_size_mb"] = "יעד הגודל חייב להיות מספר"

    if known_fonts:
        lowered = {font.lower() for font in known_fonts}
        checks = [("text_font", payload.get("text") and not _blank(payload.get("text"))), ("caption_font", payload.get("captions"))]
        for field, relevant in checks:
            font = payload.get(field)
            if relevant and not _blank(font) and str(font).strip().lower() not in lowered:
                errors[field] = f"⚠️ הגופן '{str(font).strip()}' לא מותקן - ייבחר גופן חלופי"
    return errors


# סדר חשוב: הדפוס הספציפי ביותר קודם (למשל lut3d לפני "No such file" כללי).
_FFMPEG_ERROR_PATTERNS: List[Tuple[str, str]] = [
    (r"lut3d|\.cube", "lut_path"),
    (r"drawtext|fontconfig|Cannot find a valid font|textfile", "text"),
    (r"subtitles|libass|\.srt|\.ass", "captions"),
    (r"chromakey", "chromakey_color"),
    (r"arnndn|\.rnnn", "audio_denoise_model"),
    (r"curves", "curves_master"),
    (r"colorbalance", "grade_midtones"),
    (r"acompressor|afftdn|equalizer|highpass|treble|bass=", "audio_compressor"),
    (r"delogo", "remove_watermark_position"),
    (r"vidstab", "stabilize"),
    (r"minterpolate", "smooth_fps"),
    (r"zscale|tonemap", "codec"),
    (r"hevc_nvenc|av1_nvenc|nvenc|OpenEncodeSessionEx|No capable devices|CUDA|cuda", "codec"),
    (r"Invalid frame rate|fps=", "fps"),
    (r"atempo|loudnorm|agate|afade|aselect", "keep_audio"),
    (r"xfade|acrossfade|concat", "concat_mode"),
]


def map_ffmpeg_error_to_field(stderr_tail: str, payload: Dict[str, Any]) -> Optional[str]:
    """מנחש לאיזה שדה שגיאת ffmpeg שייכת. נתיב-קובץ שמופיע בהודעה ("No such
    file" / "Invalid data found") מתורגם לשדה שמחזיק את אותו נתיב בדיוק - זה
    הניחוש הכי אמין, אז נבדק ראשון. None אם אין שום רמז."""
    text = stderr_tail or ""
    lowered = text.lower()
    for field in PATH_FIELDS:
        value = payload.get(field)
        if not _blank(value):
            path = str(value).strip().strip('"')
            candidates = {path.lower(), path.replace("\\", "/").lower(), os.path.basename(path).lower()}
            if any(candidate and candidate in lowered for candidate in candidates):
                return field
    for pattern, field in _FFMPEG_ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return field
    return None


def parse_validate_output(stdout: str) -> List[Dict[str, str]]:
    """שורות [VALID]/[INVALID] מפלט --validate-only -> [{file, status, detail}].
    ה-detail של [INVALID] הוא זנב ה-stderr של ffmpeg ויכול להתפרס על כמה שורות -
    נאסף עד השורה המובנית הבאה ([...]/RESULT:/PROGRESS:)."""
    results: List[Dict[str, str]] = []
    current: Optional[Dict[str, str]] = None
    for line in (stdout or "").splitlines():
        stripped = line.strip()
        match = re.match(r"^\[(VALID|INVALID)\]\s+(.+?):\s*(.*)$", stripped)
        if match:
            current = {"status": match.group(1).lower(), "file": match.group(2).strip(), "detail": match.group(3).strip()}
            results.append(current)
            continue
        if stripped.startswith(("[", "RESULT:", "PROGRESS:")):
            current = None
            continue
        if current is not None and current["status"] == "invalid" and stripped:
            current["detail"] = (current["detail"] + "\n" + stripped).strip()
    return results
