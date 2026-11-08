# utils/video/editor_model.py
#
# גל 12 - מודל הנתונים v2 של עורך-העל, מקור-אמת אחד לשלוש שאלות שעד עכשיו
# היו מפוזרות (או בכלל לא קיימות) בין ה-HTML, ה-JS וה-Python:
#
#   1. "לאן שייך כל שדה" - רמה (מתכון / יעד / מותג / פרויקט / ריצה / ממשק) ואזור
#      במסך (פלט / זמן / מראה / שכבות / שמע / יצוא / ביצועים / קבצים).
#   2. "יעדים" - Shorts / TikTok / Reels / YouTube / דיסקורד... - כל יעד = הגדרות
#      פלט (פורמט/איכות/גודל) + אזור-בטיחות + תת-תיקיית פלט. ריצה = מתכון × יעדים.
#   3. "עריכת קליפ" - חיתוך/טווחים/שכבות לקובץ אחד בתיקייה, שמתורגמים לדריסות
#      פר-קובץ (--batch-overrides) של הרנדרר.
#
# האחסון של פרופיל נשאר שטוח (שדה לכל הגדרה) בכוונה: הדסקטופ הקפוא, ה-CLI
# ומשימות מתוזמנות קוראים אותו כך. v2 הוא שכבת המודל מעל האחסון: הקיבוץ, היעדים,
# עריכות-הקליפ, המיגרציה (צד-שרת, אחת לכולם) וייצוא מובנה.

import copy
import math
from typing import Any, Dict, List, Optional, Tuple

from utils.video.video_editor import parse_time_seconds
from utils.video.video_editor_profiles import PROFILE_FIELDS

SCHEMA_VERSION = 2

# גל 28: האזורים הם גם הלשוניות של המפקח בסטודיו, בסדר הזה. "מראה" התפצל ל"צבע" (המפתח
# "look" נשאר - העדפות, חוקים וקישורים ישנים) ול"אפקטים וניקוי".
# גל 34: בסדר של זרימת העבודה - זמן, צבע, אפקטים, שכבות, שמע, ורק אז הפלט והייצוא.
AREAS: Tuple[str, ...] = ("time", "look", "effects", "layers", "sound", "output", "export", "perf", "queue")
AREA_TITLES: Dict[str, str] = {
    "output": "📐 פלט וצורה", "time": "✂️ זמן", "look": "🎨 צבע", "effects": "✨ אפקטים וניקוי", "layers": "🧩 שכבות",
    "sound": "🔊 שמע וכתוביות", "export": "📦 ייצוא", "perf": "⚙️ ביצועים", "queue": "📁 קבצים",
}

# אזור לכל שדה. נבדק מול ה-HTML בפועל (tests/studio/test_editor_model.py): שדה שמוצג
# בממשק יושב באזור הזה, ושדה "legacy" מוסתר שייך לאזור של הבורר המאוחד שכותב אותו.
FIELD_AREAS: Dict[str, str] = {}
for _area, _fields in {
    "output": ("targets", "vertical", "aspect", "custom_width", "custom_height", "dual_output", "fit", "smart_crop", "smart_crop_face",
               "blur_background", "pad_color", "preserve_resolution", "resolution", "scale_algo", "rotate", "flip"),
    "time": ("trim_start", "trim_duration", "trim_silence", "remove_mid_silence", "silence_threshold_db", "silence_min_duration",
             "remove_ranges", "speed", "target_seconds", "fade_in_seconds", "fade_out_seconds",
             "intro_path", "outro_path", "boomerang", "loop_count"),
    "look": ("lut_path", "lut_intensity", "eq_brightness", "eq_contrast", "eq_saturation", "eq_gamma", "auto_levels", "tonemap",
             "grade_shadows", "grade_midtones", "grade_highlights", "curves_preset", "curves_master", "curves_red", "curves_green", "curves_blue"),
    "effects": ("denoise", "denoise_level", "sharpen", "sharpen_level", "stabilize", "deinterlace", "vignette", "ken_burns",
                "chromakey", "chromakey_color", "chromakey_bg_color", "chromakey_similarity", "chromakey_blend"),
    "layers": ("brand_kit", "watermark_path", "watermark_position", "watermark_opacity", "watermark_scale", "watermark_x", "watermark_y",
               "watermark_position_vertical", "watermark_move_seconds", "pip_path", "pip_position", "pip_scale", "pip_opacity",
               "pip_x", "pip_y", "layers", "text", "text_position", "text_font", "text_font_size", "text_color", "timestamp_overlay",
               "progress_bar", "progress_bar_color", "progress_bar_position", "progress_bar_height", "frame_thickness", "frame_color",
               "frame_radius", "remove_watermark_position", "remove_watermark_width_fraction", "remove_watermark_height_fraction", "remove_watermark_region"),
    "sound": ("keep_audio", "replace_audio_path", "audio_track", "loudnorm", "loudnorm_target", "noise_gate", "pip_audio", "pip_duck",
              "captions", "captions_translate", "captions_language", "captions_model", "caption_style", "caption_font", "caption_font_size",
              "caption_color", "caption_position", "caption_max_chars", "captions_export", "captions_no_burn",
              "audio_highpass", "audio_eq_low", "audio_eq_mid", "audio_eq_mid_freq", "audio_eq_high", "audio_compressor", "audio_denoise",
              "audio_denoise_model"),
    "export": ("codec", "crf", "nvenc_cq", "target_size_mb", "container", "fps", "smooth_fps", "thumbnail", "no_suffix", "output_template",
               "number_videos", "number_prefix", "number_start", "meta_title", "meta_comment", "chapters", "export_gif", "gif_width",
               "gif_fps", "export_audio"),
    "perf": ("hwaccel", "hwaccel_decode", "parallel", "effort", "nvenc_preset", "max_concurrent_nvenc", "notify_per_file", "export_report"),
    "queue": ("folder", "queue_files", "include_subfolders", "concat_mode", "concat_transition", "concat_transition_duration",
              "concat_output_name"),
}.items():
    for _field in _fields:
        FIELD_AREAS[_field] = _area

# גל 28: תתי-אזורים בכל אזור (בסדר המסך) - כל אחד מתקפל לשורת תקציר במפקח. שדה שלא
# מופיע כאן יושב בגוף האזור עצמו (תמיד גלוי). "primary" = פתוח כברירת מחדל. נבדק מול
# ה-HTML בפועל (tests/studio/test_editor_model.py) - כל שדה גלוי יושב בתת-האזור שלו.
SECTIONS: Dict[str, Tuple[Tuple[str, str, bool, Tuple[str, ...]], ...]] = {
    "time": (
        ("cuts", "✂️ טווחים להסרה", True, ("remove_ranges",)),
        ("bookends", "🎬 מעברים, פתיח, סיום וחזרות", False,
         ("fade_in_seconds", "fade_out_seconds", "intro_path", "outro_path", "boomerang", "loop_count")),
    ),
    "look": (
        ("color", "🎨 בהירות, ניגודיות ו-LUT", True,
         ("lut_path", "lut_intensity", "eq_brightness", "eq_contrast", "eq_saturation", "eq_gamma", "auto_levels", "tonemap")),
        ("grade", "🎨 גלגלי צבע ועקומות", False,
         ("grade_shadows", "grade_midtones", "grade_highlights", "curves_preset", "curves_master", "curves_red", "curves_green", "curves_blue")),
    ),
    "effects": (
        ("cleanup", "🧹 ניקוי תמונה", True, ("denoise", "denoise_level", "sharpen", "sharpen_level", "stabilize", "deinterlace")),
        ("effects", "✨ אפקטים", False, ("vignette", "ken_burns")),
        ("chromakey", "🟩 כרומה קי", False, ("chromakey", "chromakey_color", "chromakey_bg_color", "chromakey_similarity", "chromakey_blend")),
    ),
    "layers": (
        ("watermark", "🏷️ לוגו (סימן מים)", True,
         ("watermark_path", "watermark_position", "watermark_scale", "watermark_opacity", "watermark_position_vertical",
          "watermark_move_seconds", "watermark_x", "watermark_y")),
        ("pip", "📺 PiP (תמונה-בתוך-תמונה)", True, ("pip_path", "pip_position", "pip_x", "pip_y", "pip_scale", "pip_opacity")),
        ("timed-layers", "📚 טקסט, תמונות וטיימרים", True, ("layers",)),
        ("decor", "▬ סרגל התקדמות", True, ("progress_bar", "progress_bar_color", "progress_bar_position", "progress_bar_height")),
        ("frame", "🖼️ מסגרת", True, ("frame_thickness", "frame_color", "frame_radius")),
        ("removal", "🧽 מחיקת לוגו ישן", True, ("remove_watermark_region", "remove_watermark_position",
                                                  "remove_watermark_width_fraction", "remove_watermark_height_fraction")),
    ),
    "sound": (
        ("audio-fx", "🎚️ עיבוד שמע", False,
         ("audio_highpass", "audio_eq_low", "audio_eq_mid", "audio_eq_mid_freq", "audio_eq_high", "audio_compressor", "audio_denoise",
          "audio_denoise_model")),
        ("captions", "💬 כתוביות", False,
         ("captions", "caption_style", "captions_language", "captions_model", "captions_translate", "caption_font", "caption_font_size",
          "caption_color", "caption_position", "caption_max_chars", "captions_export", "captions_no_burn")),
    ),
    "export": (
        ("file", "📄 קובץ", True, ("codec", "target_size_mb", "crf", "nvenc_cq", "container", "fps", "smooth_fps")),
        ("naming", "🏷️ שם ומספור", False, ("output_template", "no_suffix", "number_videos", "number_prefix", "number_start")),
        ("extra-outputs", "➕ קבצים נוספים", False, ("thumbnail", "export_gif", "gif_width", "gif_fps", "export_audio")),
        ("metadata", "📝 תגיות ופרקים", False, ("meta_title", "meta_comment", "chapters")),
    ),
}
FIELD_SECTIONS: Dict[str, str] = {field: section for sections in SECTIONS.values() for section, _t, _p, fields in sections for field in fields}

# גל 28: שדה שאין לו שום השפעה בלי שדה-אב - מוסתר במפקח עד שהאב פעיל. "set" = לאב יש ערך,
# "true" = האב מסומן, ">1" = מספר גדול מ-1, ו-"!X" = האב שונה מ-X. ה-JS קורא את הטבלה מהסכמה.
DEPENDS_ON: Dict[str, Tuple[str, str]] = {
    "lut_intensity": ("lut_path", "set"),
    "chromakey_color": ("chromakey", "true"), "chromakey_bg_color": ("chromakey", "true"),
    "chromakey_similarity": ("chromakey", "true"), "chromakey_blend": ("chromakey", "true"),
    "number_prefix": ("number_videos", "true"), "number_start": ("number_videos", "true"),
    "gif_fps": ("export_gif", "set"),
    "audio_denoise_model": ("audio_denoise", "!off"),
    "captions_language": ("captions", "true"), "captions_model": ("captions", "true"), "caption_style": ("captions", "true"),
    "caption_font_size": ("captions", "true"), "caption_position": ("captions", "true"), "captions_export": ("captions", "true"),
    "captions_no_burn": ("captions", "true"), "caption_max_chars": ("captions", "true"),
    "watermark_position_vertical": ("watermark_path", "set"), "watermark_move_seconds": ("watermark_path", "set"),
    "progress_bar_color": ("progress_bar", "true"), "progress_bar_position": ("progress_bar", "true"),
    "progress_bar_height": ("progress_bar", "true"),
}

# רמות: "target" = מה שיעד קובע (פורמט/איכות/גודל), "brand" = מה שערכת-מותג
# מחזיקה, "project" = שייך לתיקייה ולא למתכון, "run" = מצב-ריצה חד-פעמי,
# "ui" = העדפת תצוגה. כל השאר = "recipe" (חל על כל הקבצים).
TARGET_FIELDS: Tuple[str, ...] = ("vertical", "aspect", "custom_width", "custom_height", "dual_output", "fit", "resolution",
                                  "codec", "crf", "nvenc_cq", "target_size_mb", "container", "fps")
BRAND_FIELDS: Tuple[str, ...] = ("watermark_path", "watermark_position", "watermark_opacity", "watermark_scale", "watermark_x",
                                 "watermark_y", "watermark_position_vertical", "watermark_move_seconds", "caption_style", "caption_font",
                                 "caption_font_size", "caption_color", "caption_position", "caption_max_chars", "intro_path", "outro_path", "frame_color",
                                 "frame_thickness", "frame_radius", "progress_bar_color")
PROJECT_FIELDS: Tuple[str, ...] = ("folder", "queue_files", "include_subfolders")
RUN_FIELDS: Tuple[str, ...] = ("force", "preview_only", "validate_only")
UI_FIELDS: Tuple[str, ...] = ("favorite_fields",)
CLIP_EDIT_FIELDS: Tuple[str, ...] = ("trim_start", "trim_duration", "remove_ranges", "layers")


def field_level(field: str) -> str:
    for level, fields in (("target", TARGET_FIELDS), ("brand", BRAND_FIELDS), ("project", PROJECT_FIELDS), ("run", RUN_FIELDS), ("ui", UI_FIELDS)):
        if field in fields:
            return level
    return "recipe"


def field_area(field: str) -> Optional[str]:
    return FIELD_AREAS.get(field)


def field_section(field: str) -> Optional[str]:
    return FIELD_SECTIONS.get(field)


# --- יעדים ---
# כל יעד = שדות שהוא דורס (מעל המתכון) + אזור-בטיחות לתצוגה המקדימה + תת-תיקיית
# פלט (כדי ששני יעדים באותו כיוון - Shorts ו-TikTok - לא ידרסו זה את זה).
TARGET_PRESETS: Dict[str, Dict[str, Any]] = {
    "shorts": {"label": "YouTube Shorts", "icon": "▶️", "safe_zone": "shorts", "subdir": "shorts",
               "fields": {"vertical": True, "aspect": "", "dual_output": False, "fit": "auto"}},
    "tiktok": {"label": "TikTok", "icon": "🎵", "safe_zone": "tiktok", "subdir": "tiktok",
               "fields": {"vertical": True, "aspect": "", "dual_output": False, "fit": "auto"}},
    "reels": {"label": "Instagram Reels", "icon": "📸", "safe_zone": "reels", "subdir": "reels",
              "fields": {"vertical": True, "aspect": "", "dual_output": False, "fit": "auto"}},
    "youtube": {"label": "YouTube", "icon": "📺", "safe_zone": "youtube", "subdir": "youtube",
                "fields": {"vertical": False, "aspect": "", "dual_output": False}},
    "youtube_4k": {"label": "YouTube 4K", "icon": "🖥️", "safe_zone": "youtube", "subdir": "youtube_4k",
                   "fields": {"vertical": False, "aspect": "", "dual_output": False, "resolution": "2160p"}},
    "square": {"label": "פיד מרובע 1:1", "icon": "⬛", "safe_zone": "", "subdir": "square",
               "fields": {"vertical": False, "aspect": "1:1", "dual_output": False}},
    "discord": {"label": "דיסקורד (עד 10MB)", "icon": "💬", "safe_zone": "", "subdir": "discord",
                "fields": {"vertical": False, "aspect": "", "dual_output": False, "codec": "h264", "container": "mp4", "target_size_mb": 9.5}},
    "archive": {"label": "ארכיון (איכות מלאה)", "icon": "🗄️", "safe_zone": "", "subdir": "archive",
                "fields": {"vertical": False, "aspect": "", "dual_output": False, "codec": "hevc", "nvenc_cq": 18, "target_size_mb": None}},
}


def sanitize_targets(raw: Any) -> List[str]:
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",")]
    if not isinstance(raw, (list, tuple)):
        return []
    seen: List[str] = []
    for item in raw:
        if isinstance(item, str) and item in TARGET_PRESETS and item not in seen:
            seen.append(item)
    return seen


def expand_targets(payload: Dict[str, Any]) -> List[Tuple[Optional[str], Dict[str, Any]]]:
    """ריצה = מתכון × יעדים: [(מזהה-יעד, payload לריצה)]. בלי יעדים - ריצה אחת
    כמו תמיד (מזהה None). כל יעד מקבל תת-תיקיית פלט משלו."""
    targets = sanitize_targets(payload.get("targets"))
    if not targets:
        return [(None, payload)]
    runs = []
    for target_id in targets:
        preset = TARGET_PRESETS[target_id]
        run = copy.deepcopy(payload)
        for key, value in preset["fields"].items():
            if value is None:
                run.pop(key, None)
            else:
                run[key] = value
        run["output_subdir"] = preset["subdir"]
        run["target_id"] = target_id
        runs.append((target_id, run))
    return runs


# --- עריכת קליפ ---
FAR_END_SECONDS = 10_000_000.0  # "עד סוף הקובץ" - הרנדרר מהדק לאורך האמיתי


def _clean_ranges(raw: Any) -> List[List[float]]:
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    ranges = []
    for item in raw:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        start, end = parse_time_seconds(item[0]), parse_time_seconds(item[1])
        if start is None or end is None or not (end > start >= 0) or math.isinf(end):
            continue
        ranges.append([round(start, 3), round(end, 3)])
    return _merge_ranges(ranges)


def _merge_ranges(ranges: List[List[float]]) -> List[List[float]]:
    merged: List[List[float]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


# גל 30: הלוגו לקליפ אחד (קובץ, מיקום/גרירה, גודל, שקיפות) - עובר כמו שהוא; הטיפוסים
# נבדקים ב-sanitize_batch_overrides
CLIP_LOGO_FIELDS = ("watermark_path", "watermark_position", "watermark_x", "watermark_y", "watermark_scale", "watermark_opacity")
CLIP_TIME_FIELDS = ("trim_start", "trim_duration", "remove_ranges")


def compile_clip_edit(edit: Any) -> Dict[str, Any]:
    """עריכת-קליפ ({trim_start, trim_duration, remove_ranges, layers, watermark_*}) -> דריסות
    פר-קובץ לרנדרר. חיתוך בלבד נשאר חיתוך (-ss מהיר); חיתוך + טווחים מתורגם
    לטווחים בלבד ([0,התחלה] + הטווחים + [סוף,∞]) - הרנדרר לא משלב חיתוך מפורש
    עם הסרת-טווחים, ובטווחים כולם באותם זמני-מקור. עריכה בלי שדות זמן בכלל (למשל
    רק לוגו) לא נוגעת בזמן - הקובץ נשאר עם החיתוך של כל הקבצים."""
    if not isinstance(edit, dict):
        return {}
    out: Dict[str, Any] = {}
    for key in CLIP_LOGO_FIELDS:
        if edit.get(key) not in (None, ""):
            out[key] = edit[key]
    layers = edit.get("layers")
    if isinstance(layers, list) and layers:
        out["layers"] = layers[:20]
    if not any(key in edit for key in CLIP_TIME_FIELDS) and not edit.get("reset_time"):
        return out
    start = parse_time_seconds(edit.get("trim_start")) or 0.0
    duration = parse_time_seconds(edit.get("trim_duration")) if edit.get("trim_duration") not in (None, "") else None
    if duration is not None and duration <= 0:
        duration = None
    ranges = _clean_ranges(edit.get("remove_ranges"))
    if ranges:
        full = list(ranges)
        if start > 0:
            full.append([0.0, round(start, 3)])
        if duration is not None:
            full.append([round(start + duration, 3), FAR_END_SECONDS])
        out["remove_ranges"] = _merge_ranges(full)
    else:
        if start > 0:
            out["trim_start"] = round(start, 3)
        if duration is not None:
            out["trim_duration"] = round(duration, 3)
        if edit.get("reset_time"):
            out["trim_start"] = out.get("trim_start", 0.0)
    return out


def merge_clip_edits_into_overrides(overrides: Dict[str, Dict[str, Any]], clip_edits: Any) -> Dict[str, Dict[str, Any]]:
    """עריכות-קליפ גוברות על דריסות-התור (שהן ברמת "watermark/חיתוך לקובץ")."""
    merged = {name: dict(values) for name, values in (overrides or {}).items()}
    if not isinstance(clip_edits, dict):
        return merged
    import os
    for filename, edit in clip_edits.items():
        compiled = compile_clip_edit(edit)
        if not compiled or not isinstance(filename, str):
            continue
        name = os.path.basename(filename.strip())
        target = merged.setdefault(name, {})
        if "remove_ranges" in compiled:
            target.pop("trim_start", None)
            target.pop("trim_duration", None)
        target.update(compiled)
    return {name: values for name, values in merged.items() if values}


def split_clip_layers(layers: Any) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """שכבות המתכון -> (שכבות לכל הקבצים, {קובץ: שכבות רק לו}). שכבה עם "clip"
    (שם קובץ) היא שכבת-קליפ - למשל "GOAL!" ב-0:12 של קליפ אחד."""
    import json
    import os
    if isinstance(layers, str):
        try:
            layers = json.loads(layers) if layers.strip() else []
        except ValueError:
            layers = []
    if not isinstance(layers, list):
        return [], {}
    shared: List[Dict[str, Any]] = []
    per_file: Dict[str, List[Dict[str, Any]]] = {}
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        clip = str(layer.get("clip") or "").strip()
        clean = {k: v for k, v in layer.items() if k != "clip"}
        if clip:
            per_file.setdefault(os.path.basename(clip), []).append(clean)
        else:
            shared.append(clean)
    return shared, per_file


def with_clip_layers(payload: Dict[str, Any]) -> Dict[str, Any]:
    """payload -> שכבות-הקליפ עוברות משדה layers אל clip_edits[קובץ].layers."""
    shared, per_file = split_clip_layers(payload.get("layers"))
    if not per_file:
        return payload
    out = dict(payload)
    out["layers"] = shared
    edits = {name: dict(edit) for name, edit in (payload.get("clip_edits") or {}).items() if isinstance(edit, dict)}
    for name, layers in per_file.items():
        edits.setdefault(name, {})["layers"] = [*edits.get(name, {}).get("layers", []), *layers]
    out["clip_edits"] = edits
    return out


def pick_target(payload: Dict[str, Any], target_id: Optional[str] = None) -> Dict[str, Any]:
    """לתצוגה-מקדימה/בדיקה/הערכה: ה-payload של יעד אחד (המבוקש, או הראשון)."""
    runs = expand_targets(payload)
    for run_target, run in runs:
        if run_target == target_id:
            return run
    return runs[0][1]


# --- מיגרציה (צד-שרת, אחת לכולם) ---
TEXT_POSITION_TO_LAYER = {"top": "top-center", "center": "center", "bottom": "bottom-center"}


def corner_region(corner: str, width: float, height: float) -> str:
    x = 0.0 if corner.endswith("left") else (1 - width if corner.endswith("right") else (1 - width) / 2)
    y = 0.0 if corner.startswith("top") else (1 - height if corner.startswith("bottom") else (1 - height) / 2)
    return ",".join(f"{round(v, 3):g}" for v in (x, y, width, height))


def migrate_profile(fields: Dict[str, Any]) -> Dict[str, Any]:
    """פרופיל ישן -> v2: טקסט קבוע וחותמת-זמן הופכים לשכבות (הממשק כבר לא מציג
    אותם כשדות), ופינת-מחיקה + אחוזים הופכת לאזור x,y,w,h. אידמפוטנטי."""
    out = dict(fields or {})
    import json
    layers_raw = out.get("layers")
    try:
        layers = json.loads(layers_raw) if isinstance(layers_raw, str) and layers_raw.strip() else (list(layers_raw) if isinstance(layers_raw, list) else [])
    except ValueError:
        layers = []
    changed = False
    text = out.get("text")
    if isinstance(text, str) and text.strip():
        layers.insert(0, {"type": "text", "text": text, "start": 0, "end": None,
                          "position": TEXT_POSITION_TO_LAYER.get(str(out.get("text_position") or "bottom"), "bottom-center"),
                          "opacity": 1, "font": out.get("text_font") or "Arial", "font_size": int(out.get("text_font_size") or 24),
                          "color": out.get("text_color") or "#FFFFFF", "box": False, "animation": "none"})
        out["text"] = ""
        changed = True
    if out.get("timestamp_overlay"):
        layers.append({"type": "timestamp", "start": 0, "end": None, "position": out["timestamp_overlay"], "opacity": 1,
                       "font": "Arial", "font_size": 36, "color": "#FFFFFF", "box": True, "animation": "none"})
        out["timestamp_overlay"] = ""
        changed = True
    if changed:
        out["layers"] = json.dumps(layers, ensure_ascii=False) if isinstance(layers_raw, str) else layers
    corner = out.get("remove_watermark_position")
    if corner and not out.get("remove_watermark_region"):
        width = float(out.get("remove_watermark_width_fraction") or 0.2)
        height = float(out.get("remove_watermark_height_fraction") or 0.12)
        out["remove_watermark_region"] = corner_region(str(corner), width, height)
        out["remove_watermark_position"] = ""
        changed = True
    out["schema_version"] = SCHEMA_VERSION
    return out


def structured_view(fields: Dict[str, Any]) -> Dict[str, Any]:
    """ייצוא v2 מובנה: {schema, recipe: {אזור: {שדה: ערך}}, targets, brand_kit}."""
    recipe: Dict[str, Dict[str, Any]] = {area: {} for area in AREAS}
    other: Dict[str, Any] = {}
    for key, value in (fields or {}).items():
        if key in ("targets", "brand_kit", "schema_version"):
            continue
        area = FIELD_AREAS.get(key)
        if area:
            recipe[area][key] = value
        else:
            other[key] = value
    return {"schema": SCHEMA_VERSION, "recipe": {area: values for area, values in recipe.items() if values},
            "targets": sanitize_targets(fields.get("targets")), "brand_kit": fields.get("brand_kit") or "", "other": other}


def flatten_structured(data: Dict[str, Any]) -> Dict[str, Any]:
    """הפך של structured_view (ייבוא) - מקבל גם פרופיל שטוח ישן כמו שהוא."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_VERSION or "recipe" not in data:
        return dict(data or {})
    flat: Dict[str, Any] = dict(data.get("other") or {})
    for values in (data.get("recipe") or {}).values():
        if isinstance(values, dict):
            flat.update(values)
    flat["targets"] = sanitize_targets(data.get("targets"))
    flat["brand_kit"] = data.get("brand_kit") or ""
    return flat


def schema_description() -> Dict[str, Any]:
    """מה שהממשק צריך לדעת על המודל (GET /api/video_editor/schema)."""
    fields = list(PROFILE_FIELDS)
    return {
        "schema_version": SCHEMA_VERSION,
        "areas": [{"id": area, "title": AREA_TITLES[area],
                   "sections": [{"id": sid, "title": title, "primary": primary, "fields": list(sfields)}
                                for sid, title, primary, sfields in SECTIONS.get(area, ())]} for area in AREAS],
        "fields": {field: {"area": field_area(field), "level": field_level(field), "section": field_section(field)} for field in fields},
        "depends_on": {field: {"on": parent, "when": when} for field, (parent, when) in DEPENDS_ON.items()},
        "targets": {key: {k: v for k, v in preset.items()} for key, preset in TARGET_PRESETS.items()},
        "brand_fields": list(BRAND_FIELDS),
        "clip_edit_fields": list(CLIP_EDIT_FIELDS),
    }
