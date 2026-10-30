# utils/video/video_editor_estimate.py
#
# item 46 (102-ההצעות, גל 4): "הערכת גודל פלט + משך לכל קובץ, לא רק ETA" -
# הערכה מראש (לפני רינדור) של משך הפלט (אחרי חיתוך/טווחים/טיימלאפס/מהירות) ושל
# גודל הקובץ. גודל = יעד-גודל מפורש (--target-size-mb) אם ניתן, אחרת הערכת
# ביטרייט לפי bits-per-pixel אופייני לכל קודק באיכות ברירת-המחדל של הפרויקט
# (CRF 20 / CQ 19 / CQ 24), מותאם ל-CQ/CRF מותאם אישית (כל +6 ≈ חצי ביטרייט).
# זו הערכה בלבד (מסומנת "≈" בממשק) - תוכן בפועל (תנועה/רעש) משנה אותה מאוד.

import json
from typing import Any, Dict, List, Optional, Tuple

from utils.video.video_editor import (
    apply_resolution_preset, parse_fps_value, parse_time_seconds, resolve_aspect_dimensions, resolve_effective_output_dimensions,
)

# bits-per-pixel אופייני לחומר גיימפליי/מצלמה בתנועה, באיכות ברירת המחדל.
CODEC_BITS_PER_PIXEL = {"h264": 0.09, "hevc": 0.06, "av1": 0.045}
CODEC_DEFAULT_QUALITY = {"h264": 20, "hevc": 19, "av1": 24}
AUDIO_KBPS = 128


def estimate_output_seconds(source_seconds: float, opts: Dict[str, Any]) -> Tuple[float, bool]:
    """(משך-פלט-משוער, exact) - exact=False כשחלק מהקיצור תלוי בזיהוי-שקט
    אוטומטי שאי אפשר לדעת מראש (trim_silence/remove_mid_silence)."""
    exact = True
    start = parse_time_seconds(opts.get("trim_start")) or 0.0
    duration = parse_time_seconds(opts.get("trim_duration"))
    has_explicit_trim = start > 0 or duration is not None
    seconds = max(0.0, source_seconds - min(start, source_seconds))
    if duration is not None:
        seconds = min(seconds, duration)
    if not has_explicit_trim:
        if opts.get("trim_silence"):
            exact = False
        ranges_raw = opts.get("remove_ranges")
        if ranges_raw:
            try:
                ranges = json.loads(ranges_raw) if isinstance(ranges_raw, str) else ranges_raw
                removed = sum(max(0.0, min(float(e), source_seconds) - max(float(s), 0.0)) for s, e in ranges)
                seconds = max(0.0, seconds - removed)
            except (ValueError, TypeError):
                pass
        if opts.get("remove_mid_silence") and (opts.get("keep_audio") or opts.get("replace_audio_path")):
            exact = False
    target = parse_time_seconds(opts.get("target_seconds")) or 0.0
    if target > 0 and seconds > target:
        seconds = float(int(target))
    else:
        try:
            speed = float(opts.get("speed") or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        if speed > 0 and abs(speed - 1.0) > 1e-6:
            seconds = seconds / speed
    return apply_post_steps_seconds(seconds, opts), exact


def apply_post_steps_seconds(seconds: float, opts: Dict[str, Any]) -> float:
    """גל 7ב: intro/outro (אורכם מחושב ע"י הקורא ל-_bumper_seconds), בומרנג (x2, רק
    עד 60 שניות - כמו בסקריפט) וחזרות (xN) - לפי אותו סדר כמו maybe_post_process."""
    try:
        seconds += max(0.0, float(opts.get("_bumper_seconds") or 0.0))
    except (TypeError, ValueError):
        pass
    if opts.get("boomerang") and seconds <= 60.0:
        seconds *= 2
    try:
        loops = max(1, min(10, int(opts.get("loop_count") or 1)))
    except (TypeError, ValueError):
        loops = 1
    return seconds * loops


def estimate_output_mb(
    output_seconds: float, source_width: Optional[int], source_height: Optional[int], source_fps: Optional[str], opts: Dict[str, Any],
) -> float:
    target = opts.get("target_size_mb")
    try:
        if target not in (None, "") and float(target) > 0:
            return round(float(target), 1)
    except (TypeError, ValueError):
        pass
    fps_text = str(opts.get("fps") or "").strip() or source_fps or "30"
    try:
        fps = parse_fps_value(fps_text)
    except ValueError:
        fps = 30.0
    requested_codec = str(opts.get("codec") or "")
    codec = requested_codec if requested_codec in CODEC_BITS_PER_PIXEL else "h264"
    quality = opts.get("nvenc_cq") if codec != "h264" else opts.get("crf")
    try:
        quality_delta = (int(quality) - CODEC_DEFAULT_QUALITY[codec]) if quality not in (None, "") else 0
    except (TypeError, ValueError):
        quality_delta = 0
    audio_kbps = AUDIO_KBPS if (opts.get("keep_audio") or opts.get("replace_audio_path")) else 0
    total_kbps = 0.0
    for width, height in estimate_output_dimensions(opts, source_width, source_height):
        video_kbps = width * height * fps * CODEC_BITS_PER_PIXEL[codec] * (2 ** (-quality_delta / 6.0)) / 1000.0
        total_kbps += video_kbps + audio_kbps
    return round(total_kbps * output_seconds / 8 / 1024, 1)


def estimate_output_dimensions(opts: Dict[str, Any], source_width: Optional[int], source_height: Optional[int]) -> List[Tuple[int, int]]:
    """מידות כל פלט שהקובץ יפיק (גל 7): פלט כפול = שני פלטים (16:9 + 9:16),
    יחס-רוחב מותאם/ריבוע/4:5 = מידות היחס, ואחרת 16:9/9:16 הרגילים. סיבוב 90/270
    מחליף את מידות המקור (לשימור רזולוציה), ופריסט רזולוציה חל על כולם."""
    try:
        rotate = int(opts.get("rotate") or 0)
    except (TypeError, ValueError):
        rotate = 0
    if rotate in (90, 270) and source_width and source_height:
        source_width, source_height = source_height, source_width
    preserve = bool(opts.get("preserve_resolution"))
    aspect = str(opts.get("aspect") or "")
    if opts.get("dual_output"):
        dims = [resolve_effective_output_dimensions(vertical, preserve, source_width, source_height) for vertical in (False, True)]
    else:
        custom = None
        if aspect and aspect not in ("16:9", "9:16"):
            try:
                custom = resolve_aspect_dimensions(aspect, _int_or_none(opts.get("custom_width")), _int_or_none(opts.get("custom_height")))
            except ValueError:
                custom = None
        vertical = aspect == "9:16" if aspect in ("16:9", "9:16") else bool(opts.get("vertical"))
        dims = [custom or resolve_effective_output_dimensions(vertical, preserve, source_width, source_height)]
    try:
        return [apply_resolution_preset(d, str(opts.get("resolution") or "auto")) for d in dims]
    except ValueError:
        return dims


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
