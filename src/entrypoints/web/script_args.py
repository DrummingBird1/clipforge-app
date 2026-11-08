# entrypoints/web/script_args.py
#
# Pure payload -> CLI-args builders for the web app (moved out of web_app.py, no behavior change;
# web_app re-exports every name so `web_app._build_extra_args` etc. keep working).

from utils.shared import data_paths
from utils.video.video_editor import EFFORT_LEVELS, SUPPORTED_CONTAINERS, WATERMARK_POSITIONS, parse_fps_value, parse_region_fractions, parse_time_seconds, sanitize_batch_overrides, validate_output_template
import json
import os
import re


def _web_app():
    # lazy: tests monkeypatch web_app.CAPTIONS_EDITS_DIR, and web_app imports this module
    from entrypoints import web_app
    return web_app


NVENC_PRESETS = ("p1", "p2", "p3", "p4", "p5", "p6", "p7")


def _clamped_float(raw, low, high):
    """float מהודק לטווח, או None על ריק/לא-מספר - לשדות אופציונליים שלא
    נשלחים בכלל כשלא מולאו (בניגוד ל-float(... or default) שמחליף ריק בברירת מחדל)."""
    if raw in (None, ""):
        return None
    try:
        return max(low, min(high, float(raw)))
    except (TypeError, ValueError):
        return None


def _fmt_num(value):
    """מספר לשורת-פקודה בלי אפסים מיותרים (25.0 -> "25", 0.350 -> "0.35")."""
    return ("%f" % float(value)).rstrip("0").rstrip(".")


_ASPECTS = ("16:9", "9:16", "1:1", "4:5", "4:3", "custom")


_CHOICES = {
    "fit": ("auto", "crop", "pad"), "resolution": ("auto", "720p", "1080p", "1440p", "2160p"),
    "scale_algo": ("bicubic", "lanczos", "bilinear", "spline", "neighbor", "area"),
    "denoise_level": ("light", "medium", "strong"), "sharpen_level": ("light", "medium", "strong"),
    "tonemap": ("hable", "mobius", "reinhard"), "flip": ("none", "h", "v", "both"),
    "caption_style": ("classic", "bold", "outline", "box", "karaoke"),
    "captions_model": ("tiny", "base", "small", "medium", "large-v3"), "captions_export": ("srt", "vtt", "both"),
    # גל 25
    "curves_preset": ("none", "lighter", "darker", "increase_contrast", "linear_contrast", "medium_contrast",
                      "strong_contrast", "vintage", "cross_process", "color_negative"),
    "audio_compressor": ("off", "gentle", "voice", "strong"), "audio_denoise": ("off", "light", "medium", "strong"),
}


_CHOICE_DEFAULTS = {"fit": "auto", "resolution": "auto", "scale_algo": "bicubic", "denoise_level": "medium", "sharpen_level": "medium",
                    "tonemap": "hable", "flip": "none", "caption_style": "classic", "captions_model": "small"}


_COLOR_TEXT_RE = re.compile(r"^(#|0x)?[0-9a-fA-F]{6}$|^[a-zA-Z]{3,20}$")


def _build_wave7_args(payload):
    args = []
    aspect = str(payload.get("aspect") or "")
    if aspect == "custom":
        # מותאם בלי רוחב+גובה תקינים לא נשלח בכלל (הסקריפט היה עוצר עם שגיאה) -
        # הפלט נשאר 16:9/9:16 לפי "פורמט אנכי", וה-UI מזהיר על כך.
        width = _clamped_float(payload.get("custom_width"), 16, 8192)
        height = _clamped_float(payload.get("custom_height"), 16, 8192)
        if width and height:
            args += ["--aspect", "custom", "--custom-width", str(int(width)), "--custom-height", str(int(height))]
    elif aspect in _ASPECTS:
        args += ["--aspect", aspect]
    for key, flag in (("fit", "--fit"), ("resolution", "--resolution"), ("scale_algo", "--scale-algo"), ("tonemap", "--tonemap"), ("flip", "--flip")):
        value = str(payload.get(key) or "")
        if value in _CHOICES[key] and value != _CHOICE_DEFAULTS[key]:
            args += [flag, value]
    if payload.get("dual_output"):
        args += ["--dual-output"]
    wm_vertical = str(payload.get("watermark_position_vertical") or "")
    if wm_vertical in WATERMARK_POSITIONS and str(payload.get("watermark_path", "")).strip():
        args += ["--watermark-position-vertical", wm_vertical]
    speed = _clamped_float(payload.get("speed"), 0.25, 4.0)
    if speed is not None and abs(speed - 1.0) >= 0.001:
        args += ["--speed", _fmt_num(speed)]
    if payload.get("codec", "h264") == "h264":
        crf_raw = payload.get("crf")
        if crf_raw not in (None, ""):
            try:
                args += ["--crf", str(max(0, min(51, int(crf_raw))))]
            except (TypeError, ValueError):
                pass
    if str(payload.get("lut_path", "")).strip():
        intensity = _clamped_float(payload.get("lut_intensity"), 0.0, 1.0)
        if intensity is not None and intensity < 0.999:
            args += ["--lut-intensity", _fmt_num(round(intensity, 3))]
    for key, flag, default, low, high in (
        ("eq_brightness", "--eq-brightness", 0.0, -1.0, 1.0), ("eq_contrast", "--eq-contrast", 1.0, 0.0, 3.0),
        ("eq_saturation", "--eq-saturation", 1.0, 0.0, 3.0), ("eq_gamma", "--eq-gamma", 1.0, 0.1, 10.0),
    ):
        value = _clamped_float(payload.get(key), low, high)
        if value is not None and abs(value - default) >= 0.001:
            args += [flag, _fmt_num(round(value, 3))]
    if payload.get("denoise"):
        level = str(payload.get("denoise_level") or "medium")
        if level in _CHOICES["denoise_level"] and level != "medium":
            args += ["--denoise-level", level]
    if payload.get("sharpen"):
        level = str(payload.get("sharpen_level") or "medium")
        if level in _CHOICES["sharpen_level"] and level != "medium":
            args += ["--sharpen-level", level]
    try:
        rotate = int(payload.get("rotate") or 0)
    except (TypeError, ValueError):
        rotate = 0
    if rotate in (90, 180, 270):
        args += ["--rotate", str(rotate)]
    if payload.get("deinterlace"):
        args += ["--deinterlace"]
    pad_color = str(payload.get("pad_color") or "").strip()
    if pad_color and pad_color.lower() not in ("black", "#000000", "0x000000") and _COLOR_TEXT_RE.match(pad_color):
        args += ["--pad-color", pad_color]
    track_raw = payload.get("audio_track")
    if track_raw not in (None, ""):
        try:
            track = int(track_raw)
            if 0 <= track <= 32:
                args += ["--audio-track", str(track)]
        except (TypeError, ValueError):
            pass
    if payload.get("keep_audio") and payload.get("captions"):
        style = str(payload.get("caption_style") or "classic")
        if style in _CHOICES["caption_style"] and style != "classic":
            args += ["--caption-style", style]
        language = str(payload.get("captions_language") or "").strip()
        if language and re.fullmatch(r"[a-z]{2,3}", language):
            args += ["--captions-language", language]
        model = str(payload.get("captions_model") or "small")
        if model in _CHOICES["captions_model"] and model != "small":
            args += ["--captions-model", model]
        export = str(payload.get("captions_export") or "")
        if export in _CHOICES["captions_export"]:
            args += ["--captions-export", export]
            if payload.get("captions_no_burn"):
                args += ["--captions-no-burn"]
        # item 70: עורך תמלול - הסקריפט מחפש שם תמלול ערוך לכל קובץ (לפי sha1 של הנתיב)
        args += ["--captions-srt-dir", _web_app().CAPTIONS_EDITS_DIR]
    return args


# גל 25: תיקון צבע (גלגלים ועקומות) ושמע (EQ, קומפרסור, הפחתת רעש). טקסט של גלגל/עקומה
# נשלח רק אם הוא בפורמט הנכון - שגיאה בודדת לא מפילה את כל הריצה (validate_fields מסמן
# את השדה בממשק), ושדות השמע רק עם שמע.
_GRADE_TRIPLET_RE = re.compile(r"^\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*$")


_CURVE_POINTS_RE = re.compile(r"^\s*\d+(\.\d+)?/\d+(\.\d+)?(\s+\d+(\.\d+)?/\d+(\.\d+)?)+\s*$")


def _build_wave25_args(payload):
    args = []
    for key, flag in (("grade_shadows", "--grade-shadows"), ("grade_midtones", "--grade-midtones"), ("grade_highlights", "--grade-highlights")):
        value = str(payload.get(key) or "").strip()
        if value and _GRADE_TRIPLET_RE.match(value) and any(abs(float(v)) >= 0.001 for v in value.split(",")):
            args += [flag, value.replace(" ", "")]
    preset = str(payload.get("curves_preset") or "none")
    if preset in _CHOICES["curves_preset"] and preset != "none":
        args += ["--curves-preset", preset]
    for key, flag in (("curves_master", "--curves-master"), ("curves_red", "--curves-red"), ("curves_green", "--curves-green"), ("curves_blue", "--curves-blue")):
        value = " ".join(str(payload.get(key) or "").split())
        if value and _CURVE_POINTS_RE.match(value):
            args += [flag, value]
    if not payload.get("keep_audio"):
        return args
    highpass = _clamped_float(payload.get("audio_highpass"), 0.0, 400.0)
    if highpass:
        args += ["--audio-highpass", str(int(highpass))]
    for key, flag in (("audio_eq_low", "--audio-eq-low"), ("audio_eq_mid", "--audio-eq-mid"), ("audio_eq_high", "--audio-eq-high")):
        value = _clamped_float(payload.get(key), -20.0, 20.0)
        if value is not None and abs(value) >= 0.05:
            args += [flag, _fmt_num(round(value, 2))]
    if "--audio-eq-mid" in args:
        freq = _clamped_float(payload.get("audio_eq_mid_freq"), 200.0, 5000.0)
        if freq and int(freq) != 1000:
            args += ["--audio-eq-mid-freq", str(int(freq))]
    for key, flag in (("audio_compressor", "--audio-compressor"), ("audio_denoise", "--audio-denoise")):
        value = str(payload.get(key) or "off")
        if value in _CHOICES[key] and value != "off":
            args += [flag, value]
    model = str(payload.get("audio_denoise_model") or "").strip().strip('"')
    if model and "--audio-denoise" in args:
        args += ["--audio-denoise-model", model]
    return args


_HEX6_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _hex_or_none(value, default):
    text = str(value or "").strip()
    if not _HEX6_RE.match(text):
        return None
    text = "#" + text.lstrip("#").upper()
    return None if text == default else text


def _int_in(value, low, high):
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError):
        return None


def _build_wave7b_args(payload, layers_path=None):
    from utils.video.video_editor_layers import LAYER_POSITIONS, sanitize_layers
    args = []
    # require_existing_images=False: גם בתצוגת-הפקודה (בלי לבדוק קבצים) השכבות נחשבות
    if sanitize_layers(payload.get("layers"), require_existing_images=False):
        args += ["--layers-json", layers_path or "<layers.json>"]
    timestamp = str(payload.get("timestamp_overlay") or "")
    if timestamp in LAYER_POSITIONS:
        args += ["--timestamp-overlay", timestamp]
    if payload.get("progress_bar"):
        args += ["--progress-bar"]
        color = _hex_or_none(payload.get("progress_bar_color"), "#FF0000")
        if color:
            args += ["--progress-bar-color", color]
        if payload.get("progress_bar_position") == "top":
            args += ["--progress-bar-position", "top"]
        height = _int_in(payload.get("progress_bar_height"), 2, 80)
        if height and height != 8:
            args += ["--progress-bar-height", str(height)]
    thickness = _int_in(payload.get("frame_thickness"), 0, 200)
    if thickness:
        args += ["--frame-thickness", str(thickness)]
        color = _hex_or_none(payload.get("frame_color"), "#FFFFFF")
        if color:
            args += ["--frame-color", color]
    if payload.get("vignette") in ("light", "medium", "strong"):
        args += ["--vignette", payload["vignette"]]
    ken_burns = _clamped_float(payload.get("ken_burns"), 0.0, 0.5)
    if ken_burns:
        args += ["--ken-burns", _fmt_num(round(ken_burns, 3))]
    move = _clamped_float(payload.get("watermark_move_seconds"), 0.0, 3600.0)
    if move and str(payload.get("watermark_path", "")).strip():
        args += ["--watermark-move-seconds", _fmt_num(move)]
    if payload.get("pip_audio") and str(payload.get("pip_path", "")).strip() and payload.get("keep_audio"):
        args += ["--pip-audio"]
        if payload.get("pip_duck"):
            args += ["--pip-duck"]
    for key, flag in (("intro_path", "--intro-path"), ("outro_path", "--outro-path")):
        value = str(payload.get(key) or "").strip()
        if value:
            args += [flag, value]
    if payload.get("boomerang"):
        args += ["--boomerang"]
    loops = _int_in(payload.get("loop_count"), 1, 10)
    if loops and loops > 1:
        args += ["--loop-count", str(loops)]
    for key, flag in (("meta_title", "--meta-title"), ("meta_comment", "--meta-comment")):
        value = str(payload.get(key) or "").strip()[:500]
        if value:
            args += [flag, value]
    chapters = "|".join(line.strip() for line in str(payload.get("chapters") or "").splitlines() if line.strip())[:4000]
    if chapters:
        args += ["--chapters", chapters]
    export_gif = str(payload.get("export_gif") or "")
    if export_gif in ("gif", "webp", "both"):
        args += ["--export-gif", export_gif]
        width = _int_in(payload.get("gif_width"), 64, 1920)
        if width and width != 480:
            args += ["--gif-width", str(width)]
        fps = _int_in(payload.get("gif_fps"), 1, 30)
        if fps and fps != 12:
            args += ["--gif-fps", str(fps)]
    if payload.get("export_audio") in ("mp3", "m4a", "wav"):
        args += ["--export-audio", payload["export_audio"]]
    return args


# extra_args מותנה בסקריפט הנבחר בכוונה - זהה לעיקרון ב-ui/dashboard.py
# (ראו ההסבר המלא ב-utils/worker.add_script_task): רק story_cutter.py מכיר
# --ai-provider, ורק video_editor.py מכיר את שאר הדגלים - סקריפט אחר שמקבל
# דגל לא מוכר קורס עם "unrecognized arguments".
DATAVIZ_MODES = ("stills", "preview", "test", "full", "share", "shorts")   # shorts: גל 55


# טבלת בניית הארגומנטים לפי סקריפט (במקום שרשרת if ענקית): כל סקריפט = פונקציה שמחזירה את רשימת הארגומנטים שלו.
# הפלט זהה בדיוק לגרסה הקודמת - tests/studio/test_build_extra_args_golden.py בודק 1420 מטענים מוקלטים.

def _args_dataviz(payload, batch_overrides_path=None, layers_path=None):
    # רק ערכים מרשימות סגורות - לעולם לא טקסט חופשי לשורת הפקודה
    from dataviz.charts import CHART_MODULES
    args = []
    if payload.get("dv_mode") in DATAVIZ_MODES:
        args += ["--mode", payload["dv_mode"]]
    if payload.get("dv_chart") in CHART_MODULES:
        args += ["--chart", payload["dv_chart"]]
    if payload.get("dv_publish") == "on":
        args.append("--publish")
    elif payload.get("dv_publish") == "off":
        args.append("--no-publish")
    # גל 41: יעד (מרשימה סגורה) ותור של כמה פרקים (שמות שעוברים את NAME_RE בלבד)
    if payload.get("dv_target") in ("youtube", "shorts", "tiktok"):
        args += ["--target", payload["dv_target"]]
    if payload.get("dv_lang") in ("en", "both"):   # גל 55: גרסה באנגלית / שתי השפות
        args += ["--lang", payload["dv_lang"]]
    # 27.10.2026: רינדור טווח - שני תאריכים ISO בלבד (בדיקה מדויקת, לא טקסט חופשי בשורת הפקודה)
    span = payload.get("dv_range")
    if isinstance(span, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2},\d{4}-\d{2}-\d{2}", span):
        args += ["--range", span]
    episodes = payload.get("dv_episodes")
    if isinstance(episodes, list) and episodes:
        from utils.dataviz_episodes import NAME_RE
        names = [str(n) for n in episodes if isinstance(n, str) and NAME_RE.match(n)]
        if names:
            args += ["--episodes", ",".join(names[:30])]
    queue_file = payload.get("dv_queue_file")
    if isinstance(queue_file, str) and os.path.basename(queue_file) == data_paths.DATAVIZ_QUEUE and os.path.isabs(queue_file):
        args += ["--queue-file", queue_file]   # גל 44: מצב התור וביטול לכל פרק
    return args


def _args_story_cutter(payload, batch_overrides_path=None, layers_path=None):
    ai_provider = payload.get("ai_provider", "gemini")
    if ai_provider not in ("gemini", "local"):
        ai_provider = "gemini"
    return ["--ai-provider", ai_provider]


def _ve_args_watermark(payload, args, batch_overrides_path=None, layers_path=None):
    watermark_path = str(payload.get("watermark_path", "")).strip()
    if watermark_path:
        args += ["--watermark_path", watermark_path, "--watermark_position", payload.get("watermark_position", "bottom-right")]
        try:
            opacity = max(0.0, min(1.0, float(payload.get("watermark_opacity", 1.0) or 1.0)))
        except (TypeError, ValueError):
            opacity = 1.0
        if opacity < 1.0:
            args += ["--watermark_opacity", str(opacity)]
        try:
            scale = float(payload.get("watermark_scale", 0.15) or 0.15)
            if scale > 0 and abs(scale - 0.15) >= 0.0001:
                args += ["--watermark_scale", str(scale)]
        except (TypeError, ValueError):
            pass
        # item: גרירת watermark חופשית - שני השדות ביחד, אחרת מתעלם משניהם
        # (video_editor.py עצמו כבר נופל בחזרה ל---watermark_position במקרה
        # הזה, ראו שם - אין צורך לכפול את הבדיקה כאן).
        try:
            wm_x = float(payload.get("watermark_x"))
            wm_y = float(payload.get("watermark_y"))
            args += ["--watermark_x", str(wm_x), "--watermark_y", str(wm_y)]
        except (TypeError, ValueError):
            pass


def _ve_args_remove_watermark_and_pip(payload, args, batch_overrides_path=None, layers_path=None):
    remove_watermark_position = str(payload.get("remove_watermark_position", "")).strip()
    if remove_watermark_position in WATERMARK_POSITIONS:
        args += ["--remove_watermark_position", remove_watermark_position]
        # item: פער CLI→Web - גודל אזור המחיקה (ברירות המחדל של הסקריפט 0.2/0.12
        # לא נשלחות, כדי שהפקודה תישאר נקייה בדיוק כמו קודם כשלא נגעו בהן).
        for key, flag, default in (
            ("remove_watermark_width_fraction", "--remove_watermark_width_fraction", 0.2),
            ("remove_watermark_height_fraction", "--remove_watermark_height_fraction", 0.12),
        ):
            fraction = _clamped_float(payload.get(key), 0.01, 1.0)
            if fraction is not None and abs(fraction - default) >= 0.0001:
                args += [flag, _fmt_num(fraction)]
    pip_path = str(payload.get("pip_path", "")).strip()
    if pip_path:
        args += ["--pip", pip_path, "--pip-position", payload.get("pip_position", "bottom-right")]
        try:
            pip_scale = float(payload.get("pip_scale", 0.3) or 0.3)
            if pip_scale > 0 and abs(pip_scale - 0.3) >= 0.0001:
                args += ["--pip-scale", str(pip_scale)]
        except (TypeError, ValueError):
            pass
        # גל 10: גרירת PiP על התצוגה המקדימה - שני השדות ביחד, אחרת מתעלם משניהם
        pip_x = _clamped_float(payload.get("pip_x"), 0.0, 1.0)
        pip_y = _clamped_float(payload.get("pip_y"), 0.0, 1.0)
        if pip_x is not None and pip_y is not None:
            args += ["--pip-x", _fmt_num(pip_x), "--pip-y", _fmt_num(pip_y)]
        try:
            pip_opacity = max(0.0, min(1.0, float(payload.get("pip_opacity", 1.0) or 1.0)))
        except (TypeError, ValueError):
            pip_opacity = 1.0
        if pip_opacity < 1.0:
            args += ["--pip-opacity", str(pip_opacity)]


def _ve_args_trim(payload, args, batch_overrides_path=None, layers_path=None):
    if payload.get("vertical"):
        args += ["--vertical"]
        if payload.get("smart_crop"):
            args += ["--smart-crop"]
            if payload.get("smart_crop_face"):
                args += ["--smart-crop-face"]
    if payload.get("blur_background"):
        args += ["--blur-background"]
    only_files = payload.get("only_files")
    if isinstance(only_files, list) and only_files:
        args += ["--only-files", json.dumps([str(name) for name in only_files], ensure_ascii=False)]
    # item 56: מתג תתי-תיקיות - רק False מפורש מכבה (None/חסר = פרופיל ישן =
    # ההתנהגות הקודמת, תתי-תיקיות מעובדות תמיד).
    if payload.get("include_subfolders") is False:
        args += ["--no-subfolders"]
    # item: קלט mm:ss לשדות שניות - parse_time_seconds מקבל גם "1:30" (לא רק 90),
    # כך שגם פרופיל מיובא/ישן עם זמן-כטקסט עובר נכון, לא רק מה שהדפדפן כבר המיר.
    trim_start = parse_time_seconds(payload.get("trim_start")) or 0.0
    if trim_start > 0:
        args += ["--trim-start", str(float(trim_start))]
    trim_duration = parse_time_seconds(payload.get("trim_duration"))
    if trim_duration is not None:
        args += ["--trim-duration", str(float(trim_duration))]
    if payload.get("trim_silence"):
        args += ["--trim-silence"]
    target_seconds = int(round(parse_time_seconds(payload.get("target_seconds")) or 0))
    if target_seconds > 0:
        args += ["--target-seconds", str(target_seconds)]


def _ve_args_captions(payload, args, batch_overrides_path=None, layers_path=None):
    if payload.get("keep_audio"):
        args += ["--keep-audio"]
        if payload.get("captions"):
            args += ["--captions"]
            if payload.get("captions_translate"):
                args += ["--captions-translate"]
            args += [
                "--caption-font", str(payload.get("caption_font") or "Arial"),
                "--caption-color", str(payload.get("caption_color") or "#FFFFFF"),
                "--caption-position", str(payload.get("caption_position") or "bottom"),
            ]
            try:
                caption_font_size = max(1, int(payload.get("caption_font_size", 16) or 16))
            except (TypeError, ValueError):
                caption_font_size = 16
            args += ["--caption-font-size", str(caption_font_size)]
            max_chars = _int_in(payload.get("caption_max_chars"), 0, 80)
            if max_chars:
                args += ["--caption-max-chars", str(max_chars)]


def _ve_args_fps_loudnorm_lut(payload, args, batch_overrides_path=None, layers_path=None):
    if payload.get("loudnorm"):
        args += ["--loudnorm"]
        loudnorm_target_raw = payload.get("loudnorm_target")
        if loudnorm_target_raw not in (None, ""):
            try:
                args += ["--loudnorm-target", str(float(loudnorm_target_raw))]
            except (TypeError, ValueError):
                pass
    if payload.get("denoise"):
        args += ["--denoise"]
    if payload.get("sharpen"):
        args += ["--sharpen"]
    if payload.get("thumbnail"):
        args += ["--thumbnail"]
    fps = str(payload.get("fps", "")).strip()
    if fps:
        try:
            parse_fps_value(fps)
            args += ["--fps", fps]
        except ValueError:
            pass  # קלט לא תקין - מתעלם בשקט, video_editor.py נופל ל"שמירת קצב מקורי" בלעדיו
    lut_path = str(payload.get("lut_path", "")).strip()
    if lut_path:
        args += ["--lut", lut_path]
    if payload.get("auto_levels"):
        args += ["--auto-levels"]
    if payload.get("noise_gate"):
        args += ["--noise-gate"]
    if payload.get("remove_mid_silence"):
        args += ["--remove-mid-silence"]
    if payload.get("stabilize"):
        args += ["--stabilize"]


def _ve_args_fades_text_audio_parallel(payload, args, batch_overrides_path=None, layers_path=None):
    if payload.get("chromakey"):
        args += [
            "--chromakey",
            "--chromakey-color", str(payload.get("chromakey_color") or "0x00FF00"),
            "--chromakey-bg-color", str(payload.get("chromakey_bg_color") or "0x000000"),
        ]
        for key, flag, default in (
            ("chromakey_similarity", "--chromakey-similarity", 0.2),
            ("chromakey_blend", "--chromakey-blend", 0.05),
        ):
            value = _clamped_float(payload.get(key), 0.0, 1.0)
            if value is not None and abs(value - default) >= 0.0001:
                args += [flag, _fmt_num(value)]
    fade_in_seconds = parse_time_seconds(payload.get("fade_in_seconds"))
    if fade_in_seconds:
        args += ["--fade-in-seconds", str(float(fade_in_seconds))]
    fade_out_seconds = parse_time_seconds(payload.get("fade_out_seconds"))
    if fade_out_seconds:
        args += ["--fade-out-seconds", str(float(fade_out_seconds))]
    text = str(payload.get("text", "")).strip()
    if text:
        args += ["--text", text]
        text_position = str(payload.get("text_position") or "bottom")
        if text_position in ("bottom", "top", "center"):
            args += ["--text-position", text_position]
        text_font = str(payload.get("text_font", "")).strip()
        if text_font:
            args += ["--text-font", text_font]
        text_font_size_raw = payload.get("text_font_size")
        if text_font_size_raw not in (None, ""):
            try:
                args += ["--text-font-size", str(max(1, int(text_font_size_raw)))]
            except (TypeError, ValueError):
                pass
        text_color = str(payload.get("text_color", "")).strip()
        if text_color:
            args += ["--text-color", text_color]
    replace_audio_path = str(payload.get("replace_audio_path", "")).strip()
    if replace_audio_path:
        args += ["--replace-audio", replace_audio_path]
    remove_ranges_raw = payload.get("remove_ranges")
    if remove_ranges_raw:
        args += ["--remove-ranges", json.dumps(remove_ranges_raw) if not isinstance(remove_ranges_raw, str) else remove_ranges_raw]
    if payload.get("preserve_resolution"):
        args += ["--preserve-resolution"]
    if payload.get("no_suffix"):
        args += ["--no-suffix"]
    if payload.get("number_videos"):
        args += ["--number-videos"]
        number_prefix = str(payload.get("number_prefix", "")).strip()
        if number_prefix:
            args += ["--number-prefix", number_prefix]
        number_start_raw = payload.get("number_start")
        if number_start_raw not in (None, ""):
            try:
                number_start = max(1, int(number_start_raw))
                args += ["--number-start", str(number_start)]
            except (TypeError, ValueError):
                pass
    try:
        parallel = max(1, int(payload.get("parallel", 1) or 1))
    except (TypeError, ValueError):
        parallel = 1
    if parallel > 1:
        args += ["--parallel", str(parallel)]
    max_concurrent_nvenc_raw = payload.get("max_concurrent_nvenc")
    if parallel > 1 and max_concurrent_nvenc_raw not in (None, ""):
        try:
            max_concurrent_nvenc = max(1, int(max_concurrent_nvenc_raw))
            args += ["--max-concurrent-nvenc", str(max_concurrent_nvenc)]
        except (TypeError, ValueError):
            pass
    effort = str(payload.get("effort") or "high")
    if effort in EFFORT_LEVELS and effort != "high":
        args += ["--effort", effort]
    container = str(payload.get("container") or "mp4")
    if container in SUPPORTED_CONTAINERS and container != "mp4":
        args += ["--container", container]
    output_template = str(payload.get("output_template", "")).strip()
    if output_template:
        try:
            validate_output_template(output_template)
            args += ["--output-template", output_template]
        except ValueError:
            pass  # placeholder לא מוכר - מתעלם בשקט, video_editor.py נופל לשם-הפלט הרגיל בלעדיו


def _ve_args_output(payload, args, batch_overrides_path=None, layers_path=None):
    # גל 12: לכל יעד (Shorts/TikTok/...) תת-תיקיית פלט משלו - שני יעדים באותו כיוון לא דורסים זה את זה
    output_subdir = str(payload.get("output_subdir") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", output_subdir):
        args += ["--output-subdir", output_subdir]
    if payload.get("validate_only"):
        args += ["--validate-only"]
    if payload.get("notify_per_file"):
        args += ["--notify-per-file"]
    export_report = str(payload.get("export_report") or "")
    if export_report in ("csv", "xlsx", "both"):
        args += ["--export-report", export_report]

    # item: פער CLI→Web - 15 דגלים שהיו קיימים בסקריפט בלי שום שדה בווב.
    if payload.get("hwaccel"):
        args += ["--hwaccel"]
    if payload.get("hwaccel_decode"):
        args += ["--hwaccel-decode"]
    if payload.get("smooth_fps"):
        args += ["--smooth-fps"]
    target_size_mb = _clamped_float(payload.get("target_size_mb"), 0.0, 100000.0)
    if target_size_mb:
        args += ["--target-size-mb", _fmt_num(target_size_mb)]


def _ve_args_detect_and_nvenc(payload, args, batch_overrides_path=None, layers_path=None):
    if payload.get("force"):
        args += ["--force"]
    if payload.get("preview_only"):
        args += ["--preview-only"]
    args += _build_wave7_args(payload)
    args += _build_wave7b_args(payload, layers_path)
    args += _build_wave25_args(payload)
    # item 43: סף שקט מותאם (נשלח רק כשיש בכלל זיהוי-שקט פעיל ורק אם שונה מברירת המחדל)
    if payload.get("trim_silence") or payload.get("remove_mid_silence"):
        threshold = _clamped_float(payload.get("silence_threshold_db"), -90.0, 0.0)
        if threshold is not None and abs(threshold + 30.0) >= 0.01:
            args += ["--silence-threshold-db", _fmt_num(threshold)]
        min_duration = _clamped_float(payload.get("silence_min_duration"), 0.05, 30.0)
        if min_duration is not None and abs(min_duration - 0.3) >= 0.001:
            args += ["--silence-min-duration", _fmt_num(min_duration)]
    # item 50: אזור מחיקת-watermark שסומן בגרירת מלבן (שברי פריים המקור)
    region = parse_region_fractions(payload.get("remove_watermark_region"))
    if region is not None:
        args += ["--remove-watermark-region", ",".join(_fmt_num(round(v, 4)) for v in region)]
    nvenc_preset = str(payload.get("nvenc_preset") or "")
    if nvenc_preset in NVENC_PRESETS:
        args += ["--nvenc-preset", nvenc_preset]


def _ve_args_concat_and_transition(payload, args, batch_overrides_path=None, layers_path=None):
    nvenc_cq_raw = payload.get("nvenc_cq")
    if nvenc_cq_raw not in (None, ""):
        try:
            args += ["--nvenc-cq", str(max(0, min(51, int(nvenc_cq_raw))))]
        except (TypeError, ValueError):
            pass

    # item: מצב "🔗 איחוד קטעים" - סדר התור (הקבצים המסומנים, לפי הסדר שלהם)
    # הוא סדר האיחוד. פחות משני קבצים לא נשלח בכלל (api_run כבר חוסם את זה
    # בהודעה ברורה לפני שמגיעים לכאן - זו רק רשת ביטחון ל-preview_command).
    if payload.get("concat_mode"):
        concat_files = payload.get("concat_files")
        if isinstance(concat_files, list) and len(concat_files) >= 2:
            args += ["--concat-files", json.dumps([str(f) for f in concat_files], ensure_ascii=False)]
            transition = str(payload.get("concat_transition") or "fade")
            args += ["--concat-transition", transition if transition in ("fade", "none") else "fade"]
            duration = _clamped_float(payload.get("concat_transition_duration"), 0.0, 30.0)
            if duration is not None and abs(duration - 1.0) >= 0.0001:
                args += ["--concat-transition-duration", _fmt_num(duration)]
            output_name = str(payload.get("concat_output_name") or "").strip()
            if output_name and output_name != "concat_result":
                args += ["--concat-output-name", output_name]


def _args_video_editor(payload, batch_overrides_path=None, layers_path=None):
    args = ["--codec", payload.get("codec", "h264")]
    _ve_args_watermark(payload, args, batch_overrides_path, layers_path)
    _ve_args_remove_watermark_and_pip(payload, args, batch_overrides_path, layers_path)
    _ve_args_trim(payload, args, batch_overrides_path, layers_path)
    _ve_args_captions(payload, args, batch_overrides_path, layers_path)
    _ve_args_fps_loudnorm_lut(payload, args, batch_overrides_path, layers_path)
    _ve_args_fades_text_audio_parallel(payload, args, batch_overrides_path, layers_path)
    _ve_args_output(payload, args, batch_overrides_path, layers_path)
    _ve_args_detect_and_nvenc(payload, args, batch_overrides_path, layers_path)
    _ve_args_concat_and_transition(payload, args, batch_overrides_path, layers_path)

    # item: דריסות פר-קובץ - --batch-overrides מקבל נתיב לקובץ JSON, לא JSON
    # גולמי; _build_extra_args נשאר טהור (בלי כתיבה לדיסק, גם preview_command
    # קורא לו) - api_run כותב את הקובץ ומעביר את הנתיב, ובלעדיו (תצוגת פקודה)
    # מוצג placeholder קריא במקומו.
    if sanitize_batch_overrides(payload.get("batch_overrides")):
        args += ["--batch-overrides", batch_overrides_path or "<batch_overrides.json>"]
    return args


def _args_rocket_shorts(payload, batch_overrides_path=None, layers_path=None):
    args = []
    if payload.get("dry_run"):
        args.append("--dry-run")
    if payload.get("no_square"):
        args.append("--no-square")
    if payload.get("no_loudnorm"):
        args.append("--no-loudnorm")
    return args


def _args_super_manager(payload, batch_overrides_path=None, layers_path=None):
    mode = str(payload.get("sm_mode") or "scan")
    args = ["--mode", mode if mode in ("scan", "report", "clean") else "scan"]
    if args[1] == "scan":
        target_dir = str(payload.get("sm_target_dir", "")).strip()
        if target_dir:
            args += ["--target_dir", target_dir]
        if not payload.get("sm_export_excel", True):
            args += ["--no-excel"]
        if not payload.get("sm_export_html", True):
            args += ["--no-html"]
    elif args[1] == "clean":
        keep_policy = str(payload.get("sm_keep_policy") or "oldest")
        if keep_policy in ("oldest", "newest") and keep_policy != "oldest":
            args += ["--keep", keep_policy]
        if payload.get("sm_execute"):
            args += ["--execute"]
    return args


def _args_super_streamer(payload, batch_overrides_path=None, layers_path=None):
    mode = str(payload.get("ss_mode") or "folder")
    args = ["--mode", mode if mode in ("twitch", "obs", "folder") else "folder"]
    if args[1] == "twitch":
        try:
            limit = max(1, int(payload.get("ss_twitch_limit", 10) or 10))
            if limit != 10:
                args += ["--limit", str(limit)]
        except (TypeError, ValueError):
            pass
    return args


_SCRIPT_ARG_BUILDERS = {
    "dataviz_maker.py": _args_dataviz,
    "story_cutter.py": _args_story_cutter,
    "video_editor.py": _args_video_editor,
    "rocket_shorts_publisher.py": _args_rocket_shorts,
    "super_manager.py": _args_super_manager,
    "super_streamer.py": _args_super_streamer,
}


def _build_extra_args(script_basename, payload, batch_overrides_path=None, layers_path=None):
    builder = _SCRIPT_ARG_BUILDERS.get(script_basename)
    if builder is None:
        return []
    return builder(payload, batch_overrides_path=batch_overrides_path, layers_path=layers_path)
