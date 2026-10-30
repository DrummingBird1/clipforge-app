# utils.video.video_editor_batch - split out of the original module (no behavior change); the original module re-exports every name.

from typing import Any, Dict, Optional
import hashlib
import json
import math
import os
import re

from utils.video.video_editor_naming import WATERMARK_POSITIONS


_TIME_TEXT_RE = re.compile(r"^\s*(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)\s*$")


def parse_time_seconds(raw: Any) -> Optional[float]:
    """item: קלט mm:ss לשדות שניות - מקבל מספר רגיל (90, "90", "12.5") או זמן
    בסגנון שעון ("1:30", "01:02:03", "1:30.5") ומחזיר שניות. None על ריק/לא-
    תקין/שלילי - הקורא מחליט מה ברירת המחדל (בדרך כלל "לא נשלח בכלל")."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw >= 0 else None
    text = str(raw).strip()
    if not text:
        return None
    match = _TIME_TEXT_RE.match(text)
    if match:
        hours, minutes, seconds = match.group(1), match.group(2), match.group(3)
        return (int(hours) * 3600 if hours else 0) + int(minutes) * 60 + float(seconds)
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value >= 0 else None


# item: ממשק batch לדריסת דגלים פר-קובץ - מוגבל בכוונה לשדות watermark/trim
# (לא כל ~100 השדות האפשריים), מקור-אמת יחיד לסקריפט (--batch-overrides)
# ולווב (עריכה inline בשורות התור, web_app.py).
BATCH_OVERRIDE_ALLOWED_FIELDS = ("watermark_path", "watermark_position", "watermark_opacity", "watermark_scale", "trim_start", "trim_duration",
                                 # גל 12 (עריכת קליפ): טווחים להסרה ושכבות לקובץ אחד
                                 "remove_ranges", "layers",
                                 # גל 30: מיקום לוגו שנגרר בנגן לקליפ אחד (מרכז, שבר 0-1 מהפלט)
                                 "watermark_x", "watermark_y")


def sanitize_batch_overrides(raw: Any) -> Dict[str, Dict[str, Any]]:
    """מנקה {שם-קובץ: {שדה: ערך}} לפני שנכתב לקובץ --batch-overrides: רק שמות-
    קובץ (basename, לא נתיבים - הסקריפט מתאים לפי os.path.basename), רק שדות
    מ-BATCH_OVERRIDE_ALLOWED_FIELDS, ערכים מומרים לטיפוס הנכון וערכים לא-תקינים
    מושמטים (לא נכשלים). קובץ שנשארו לו אפס דריסות אחרי הניקוי לא נכלל בכלל.
    {} על קלט שאינו dict."""
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for filename, overrides in raw.items():
        if not isinstance(filename, str) or not isinstance(overrides, dict):
            continue
        name = os.path.basename(filename.strip())
        if not name:
            continue
        clean: Dict[str, Any] = {}
        for field in BATCH_OVERRIDE_ALLOWED_FIELDS:
            value = overrides.get(field)
            if value is None or value == "":
                continue
            try:
                if field == "watermark_path":
                    clean[field] = str(value).strip()
                elif field == "watermark_position":
                    if value in WATERMARK_POSITIONS:
                        clean[field] = value
                elif field in ("watermark_opacity", "watermark_x", "watermark_y"):
                    number = float(value)
                    if math.isfinite(number):
                        clean[field] = max(0.0, min(1.0, number))
                elif field == "watermark_scale":
                    scale = float(value)
                    if scale > 0:
                        clean[field] = min(1.0, scale)
                elif field == "remove_ranges":
                    ranges = []
                    for item in value if isinstance(value, list) else []:
                        if isinstance(item, (list, tuple)) and len(item) == 2:
                            start, end = float(item[0]), float(item[1])
                            if end > start >= 0:
                                ranges.append([start, end])
                    if ranges:
                        clean[field] = ranges
                elif field == "layers":
                    layers = [layer for layer in value if isinstance(layer, dict)] if isinstance(value, list) else []
                    if layers:
                        clean[field] = layers[:20]
                else:  # trim_start / trim_duration - גם "1:30" (parse_time_seconds)
                    seconds = parse_time_seconds(value)
                    if seconds is None:
                        continue
                    clean[field] = seconds
            except (TypeError, ValueError):
                continue
        if clean.get("watermark_path") == "":
            del clean["watermark_path"]
        if ("watermark_x" in clean) != ("watermark_y" in clean):  # מרכז חלקי לא קובע מיקום - כמו --watermark_x/y
            clean.pop("watermark_x", None)
            clean.pop("watermark_y", None)
        if clean:
            result[name] = clean
    return result


def compute_render_signature(source_fingerprint: str, params: Dict[str, Any]) -> str:
    """
    חתימה יציבה (sha256 hex) שמייצגת "קובץ מקור + כל הפרמטרים שמשפיעים על
    הפלט" - שני רינדורים עם אותה חתימה בדיוק יפיקו בדיוק אותו קובץ פלט, אז
    רינדור מחדש שלהם הוא בזבוז זמן/GPU בלבד (item: smart re-encode skip).
    source_fingerprint אמור לכלול mtime+size של קובץ המקור (לא רק את הנתיב
    שלו) כדי שקובץ שהוחלף בפועל (אותו שם, תוכן שונה) לא ידלג בטעות על רינדור
    אמיתי. sort_keys=True כדי שסדר המפתחות ב-params לא ישפיע על התוצאה.
    """
    payload = json.dumps({"source": source_fingerprint, "params": params}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
