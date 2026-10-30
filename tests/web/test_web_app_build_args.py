# tests/web/test_web_app_build_args.py - REST endpoint tests for web_app.py, topic: build_args (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
import json
from tests.web_app_support import (  # noqa: F401
    web_app,
)


def test_build_extra_args_story_cutter_default_gemini():
    assert web_app._build_extra_args("story_cutter.py", {}) == ["--ai-provider", "gemini"]


def test_build_extra_args_story_cutter_local():
    assert web_app._build_extra_args("story_cutter.py", {"ai_provider": "local"}) == ["--ai-provider", "local"]


def test_build_extra_args_story_cutter_rejects_unknown_provider():
    # קלט לא צפוי מהדפדפן (בעריכה ידנית של הבקשה וכו') - נופל חזרה ל-gemini
    # בלי לזרוק, בדיוק כמו state.story_cutter_ai_provider בגרסה השולחנית.
    assert web_app._build_extra_args("story_cutter.py", {"ai_provider": "not-a-real-provider"}) == ["--ai-provider", "gemini"]


def test_build_extra_args_video_editor_defaults_to_codec_only():
    assert web_app._build_extra_args("video_editor.py", {}) == ["--codec", "h264"]


def test_build_extra_args_video_editor_full_options():
    payload = {
        "codec": "hevc", "watermark_path": "C:\\logo.png", "watermark_position": "top-left",
        "watermark_opacity": 0.5,
        "remove_watermark_position": "bottom-right",
        "vertical": True, "smart_crop": True, "blur_background": True,
        "trim_start": 5, "trim_duration": 10, "trim_silence": True,
        "target_seconds": 60, "keep_audio": True, "captions": True,
        "caption_font": "Rubik", "caption_font_size": 22, "caption_color": "#00FFAA", "caption_position": "top",
        "loudnorm": True, "loudnorm_target": -20, "denoise": True, "sharpen": True, "thumbnail": True,
        "fps": "30000/1001",
        "lut_path": "C:\\looks\\my.cube", "auto_levels": True, "noise_gate": True, "remove_mid_silence": True,
        "stabilize": True, "chromakey": True, "chromakey_color": "0xFF0000", "chromakey_bg_color": "0x0000FF",
        "preserve_resolution": True, "no_suffix": True,
        "number_videos": True, "number_prefix": "Clip", "number_start": 42,
        "parallel": 3, "max_concurrent_nvenc": 2, "effort": "low",
        "container": "mkv", "output_template": "{date}_{name}_{codec}", "validate_only": True, "notify_per_file": True,
        "export_report": "both",
    }
    args = web_app._build_extra_args("video_editor.py", payload)
    assert args == [
        "--codec", "hevc", "--watermark_path", "C:\\logo.png", "--watermark_position", "top-left",
        "--watermark_opacity", "0.5",
        "--remove_watermark_position", "bottom-right",
        "--vertical", "--smart-crop", "--blur-background",
        "--trim-start", "5.0", "--trim-duration", "10.0", "--trim-silence",
        "--target-seconds", "60", "--keep-audio", "--captions",
        "--caption-font", "Rubik", "--caption-color", "#00FFAA", "--caption-position", "top", "--caption-font-size", "22",
        "--loudnorm", "--loudnorm-target", "-20.0",
        "--denoise", "--sharpen", "--thumbnail",
        "--fps", "30000/1001",
        "--lut", "C:\\looks\\my.cube", "--auto-levels", "--noise-gate", "--remove-mid-silence", "--stabilize",
        "--chromakey", "--chromakey-color", "0xFF0000", "--chromakey-bg-color", "0x0000FF",
        "--preserve-resolution", "--no-suffix",
        "--number-videos", "--number-prefix", "Clip", "--number-start", "42",
        "--parallel", "3", "--max-concurrent-nvenc", "2", "--effort", "low",
        "--container", "mkv", "--output-template", "{date}_{name}_{codec}", "--validate-only", "--notify-per-file",
        "--export-report", "both",
        "--captions-srt-dir", web_app.CAPTIONS_EDITS_DIR,  # גל 7 (item 70): תמלולים ערוכים גוברים על תמלול אוטומטי
    ]


def test_build_extra_args_video_editor_blank_watermark_path_omitted():
    args = web_app._build_extra_args("video_editor.py", {"watermark_path": "   "})
    assert "--watermark_path" not in args


def test_build_extra_args_video_editor_remove_watermark_position_included_when_valid():
    args = web_app._build_extra_args("video_editor.py", {"remove_watermark_position": "top-left"})
    assert "--remove_watermark_position" in args
    assert args[args.index("--remove_watermark_position") + 1] == "top-left"


# --- 10 new video_editor.py options (item: video editor upgrades UI wiring) ---

def test_build_extra_args_video_editor_watermark_opacity_omitted_when_full_opacity():
    args = web_app._build_extra_args("video_editor.py", {"watermark_path": "C:\\logo.png", "watermark_opacity": 1.0})
    assert "--watermark_opacity" not in args


def test_build_extra_args_video_editor_watermark_opacity_omitted_without_watermark_path():
    args = web_app._build_extra_args("video_editor.py", {"watermark_opacity": 0.3})
    assert "--watermark_opacity" not in args


# --- item: watermark - גודל + גרירה חופשית ---

def test_build_extra_args_video_editor_watermark_scale_included_when_non_default():
    args = web_app._build_extra_args("video_editor.py", {"watermark_path": "C:\\logo.png", "watermark_scale": 0.3})
    assert args[args.index("--watermark_scale") + 1] == "0.3"


def test_build_extra_args_video_editor_watermark_scale_omitted_when_default():
    args = web_app._build_extra_args("video_editor.py", {"watermark_path": "C:\\logo.png", "watermark_scale": 0.15})
    assert "--watermark_scale" not in args


def test_build_extra_args_video_editor_watermark_scale_omitted_without_watermark_path():
    args = web_app._build_extra_args("video_editor.py", {"watermark_scale": 0.3})
    assert "--watermark_scale" not in args


def test_build_extra_args_video_editor_watermark_custom_xy_included_when_both_set():
    args = web_app._build_extra_args("video_editor.py", {
        "watermark_path": "C:\\logo.png", "watermark_x": 0.3, "watermark_y": 0.7,
    })
    assert args[args.index("--watermark_x") + 1] == "0.3"
    assert args[args.index("--watermark_y") + 1] == "0.7"


def test_build_extra_args_video_editor_watermark_custom_xy_omitted_when_only_one_set():
    args = web_app._build_extra_args("video_editor.py", {"watermark_path": "C:\\logo.png", "watermark_x": 0.3})
    assert "--watermark_x" not in args
    assert "--watermark_y" not in args


def test_build_extra_args_video_editor_smart_crop_omitted_without_vertical():
    args = web_app._build_extra_args("video_editor.py", {"smart_crop": True})
    assert "--smart-crop" not in args
    assert "--vertical" not in args


def test_build_extra_args_video_editor_blur_background_included_without_vertical():
    args = web_app._build_extra_args("video_editor.py", {"blur_background": True})
    assert "--blur-background" in args


def test_build_extra_args_video_editor_blur_background_included_together_with_vertical():
    # item: הכנסת סרטון אופקי לתוך מסגרת אנכית בלי לחתוך ממנו - שני הדגלים
    # ביחד (לא if/elif) הם בדיוק איך זה נשלח ל-CLI script עכשיו.
    args = web_app._build_extra_args("video_editor.py", {"vertical": True, "blur_background": True})
    assert "--vertical" in args
    assert "--blur-background" in args


def test_build_extra_args_video_editor_trim_start_omitted_when_zero():
    args = web_app._build_extra_args("video_editor.py", {"trim_start": 0})
    assert "--trim-start" not in args


def test_build_extra_args_video_editor_trim_duration_omitted_when_none():
    args = web_app._build_extra_args("video_editor.py", {"trim_duration": None})
    assert "--trim-duration" not in args


def test_build_extra_args_video_editor_captions_omitted_without_keep_audio():
    args = web_app._build_extra_args("video_editor.py", {"captions": True})
    assert "--captions" not in args
    assert "--keep-audio" not in args


def test_build_extra_args_video_editor_captions_translate_included_with_captions():
    args = web_app._build_extra_args("video_editor.py", {"keep_audio": True, "captions": True, "captions_translate": True})
    assert "--captions" in args
    assert "--captions-translate" in args


def test_build_extra_args_video_editor_captions_translate_omitted_without_captions():
    args = web_app._build_extra_args("video_editor.py", {"keep_audio": True, "captions_translate": True})
    assert "--captions-translate" not in args


def test_build_extra_args_video_editor_loudnorm_target_omitted_without_loudnorm():
    args = web_app._build_extra_args("video_editor.py", {"loudnorm_target": -18})
    assert "--loudnorm-target" not in args
    assert "--loudnorm" not in args


def test_build_extra_args_video_editor_loudnorm_target_omitted_when_blank():
    args = web_app._build_extra_args("video_editor.py", {"loudnorm": True, "loudnorm_target": None})
    assert "--loudnorm" in args
    assert "--loudnorm-target" not in args


def test_build_extra_args_video_editor_denoise_sharpen_independent_of_each_other():
    args = web_app._build_extra_args("video_editor.py", {"denoise": True})
    assert "--denoise" in args
    assert "--sharpen" not in args


def test_build_extra_args_video_editor_remove_watermark_position_omitted_when_blank():
    args = web_app._build_extra_args("video_editor.py", {"remove_watermark_position": ""})
    assert "--remove_watermark_position" not in args


def test_build_extra_args_video_editor_remove_watermark_position_omitted_when_absent():
    args = web_app._build_extra_args("video_editor.py", {})
    assert "--remove_watermark_position" not in args


def test_build_extra_args_video_editor_rejects_invalid_remove_watermark_position():
    # מיקום לא-תקין (למשל טעות הקלדה/מניפולציה ידנית של הבקשה) לא אמור לעבור
    # ל-CLI בכלל - video_editor.py עצמו כן היה דוחה אותו, אבל עדיף לא לסמוך
    # רק על השכבה הבאה כשקל לבדוק את זה כאן.
    args = web_app._build_extra_args("video_editor.py", {"remove_watermark_position": "middle-ish"})
    assert "--remove_watermark_position" not in args


def test_build_extra_args_video_editor_remove_and_add_watermark_together():
    # "מחיקת watermark ישן והחלפתו באחר" - שני הדגלים באותה ריצה בדיוק כמו
    # שה-GUI השולחני כבר תומך בו (video_editor.py עצמו מפעיל delogo ואז
    # overlay באותו מעבר ffmpeg יחיד).
    payload = {"watermark_path": "C:\\new_logo.png", "watermark_position": "bottom-left", "remove_watermark_position": "top-right"}
    args = web_app._build_extra_args("video_editor.py", payload)
    assert "--watermark_path" in args
    assert "--remove_watermark_position" in args
    assert args[args.index("--remove_watermark_position") + 1] == "top-right"


# --- שימור FPS מקורי (item: UI wiring) ---

def test_build_extra_args_video_editor_fps_included_when_valid():
    args = web_app._build_extra_args("video_editor.py", {"fps": "30000/1001"})
    assert "--fps" in args
    assert args[args.index("--fps") + 1] == "30000/1001"


def test_build_extra_args_video_editor_fps_omitted_when_blank():
    args = web_app._build_extra_args("video_editor.py", {"fps": "  "})
    assert "--fps" not in args


def test_build_extra_args_video_editor_fps_omitted_when_invalid():
    # קלט לא תקין (למשל טעות הקלדה) - מתעלם בשקט במקום לשלוח ל-CLI ולגרום
    # ל-video_editor.py להיכשל עם --fps לא תקין; נופל ל"שמירת קצב מקורי".
    args = web_app._build_extra_args("video_editor.py", {"fps": "not-a-number"})
    assert "--fps" not in args


# --- "שדרוג ענקי" (item: UI wiring) ---

def test_build_extra_args_video_editor_lut_path_included_when_set():
    args = web_app._build_extra_args("video_editor.py", {"lut_path": "C:\\looks\\my.cube"})
    assert "--lut" in args
    assert args[args.index("--lut") + 1] == "C:\\looks\\my.cube"


def test_build_extra_args_video_editor_lut_path_omitted_when_blank():
    args = web_app._build_extra_args("video_editor.py", {"lut_path": "   "})
    assert "--lut" not in args


def test_build_extra_args_video_editor_auto_levels_noise_gate_stabilize_independent():
    args = web_app._build_extra_args("video_editor.py", {"auto_levels": True, "stabilize": True})
    assert "--auto-levels" in args
    assert "--stabilize" in args
    assert "--noise-gate" not in args
    assert "--remove-mid-silence" not in args


def test_build_extra_args_video_editor_chromakey_includes_colors_when_enabled():
    payload = {"chromakey": True, "chromakey_color": "0xABCDEF", "chromakey_bg_color": "0x123456"}
    args = web_app._build_extra_args("video_editor.py", payload)
    assert "--chromakey" in args
    assert args[args.index("--chromakey-color") + 1] == "0xABCDEF"
    assert args[args.index("--chromakey-bg-color") + 1] == "0x123456"


def test_build_extra_args_video_editor_chromakey_omitted_when_disabled():
    args = web_app._build_extra_args("video_editor.py", {"chromakey_color": "0xABCDEF"})
    assert "--chromakey" not in args
    assert "--chromakey-color" not in args


def test_build_extra_args_video_editor_caption_style_included_only_with_captions():
    payload = {"keep_audio": True, "captions": True, "caption_font": "Rubik", "caption_position": "center"}
    args = web_app._build_extra_args("video_editor.py", payload)
    assert args[args.index("--caption-font") + 1] == "Rubik"
    assert args[args.index("--caption-position") + 1] == "center"


def test_build_extra_args_video_editor_caption_style_omitted_without_captions():
    args = web_app._build_extra_args("video_editor.py", {"keep_audio": True, "caption_font": "Rubik"})
    assert "--caption-font" not in args


def test_build_extra_args_video_editor_caption_style_defaults_applied():
    # captions=True בלי לספק caption_font/color/position/size בכלל - נופל
    # לברירות המחדל של video_editor.py עצמו, לא משמיט את הדגלים או קורס.
    args = web_app._build_extra_args("video_editor.py", {"keep_audio": True, "captions": True})
    assert args[args.index("--caption-font") + 1] == "Arial"
    assert args[args.index("--caption-color") + 1] == "#FFFFFF"
    assert args[args.index("--caption-position") + 1] == "bottom"
    assert args[args.index("--caption-font-size") + 1] == "16"


def test_build_extra_args_video_editor_preserve_resolution_and_no_suffix_omitted_by_default():
    args = web_app._build_extra_args("video_editor.py", {})
    assert "--preserve-resolution" not in args
    assert "--no-suffix" not in args


def test_build_extra_args_video_editor_preserve_resolution_and_no_suffix_included_when_set():
    args = web_app._build_extra_args("video_editor.py", {"preserve_resolution": True, "no_suffix": True})
    assert "--preserve-resolution" in args
    assert "--no-suffix" in args


def test_build_extra_args_video_editor_number_videos_omitted_by_default():
    args = web_app._build_extra_args("video_editor.py", {"number_prefix": "Clip", "number_start": 5})
    assert "--number-videos" not in args
    assert "--number-prefix" not in args
    assert "--number-start" not in args


def test_build_extra_args_video_editor_number_videos_included_with_prefix_and_start():
    args = web_app._build_extra_args(
        "video_editor.py", {"number_videos": True, "number_prefix": "Clip", "number_start": 42}
    )
    assert "--number-videos" in args
    assert args[args.index("--number-prefix") + 1] == "Clip"
    assert args[args.index("--number-start") + 1] == "42"


def test_build_extra_args_video_editor_number_start_blank_is_omitted():
    args = web_app._build_extra_args("video_editor.py", {"number_videos": True, "number_start": None})
    assert "--number-videos" in args
    assert "--number-start" not in args


def test_build_extra_args_video_editor_number_start_invalid_is_omitted():
    args = web_app._build_extra_args("video_editor.py", {"number_videos": True, "number_start": "not-a-number"})
    assert "--number-videos" in args
    assert "--number-start" not in args


def test_build_extra_args_video_editor_number_prefix_blank_is_omitted():
    args = web_app._build_extra_args("video_editor.py", {"number_videos": True, "number_prefix": "   "})
    assert "--number-videos" in args
    assert "--number-prefix" not in args


def test_build_extra_args_video_editor_parallel_omitted_when_one_or_absent():
    assert "--parallel" not in web_app._build_extra_args("video_editor.py", {})
    assert "--parallel" not in web_app._build_extra_args("video_editor.py", {"parallel": 1})


def test_build_extra_args_video_editor_parallel_included_when_above_one():
    args = web_app._build_extra_args("video_editor.py", {"parallel": 4})
    assert args[args.index("--parallel") + 1] == "4"


def test_build_extra_args_video_editor_parallel_invalid_falls_back_to_omitted():
    assert "--parallel" not in web_app._build_extra_args("video_editor.py", {"parallel": "not-a-number"})


def test_build_extra_args_video_editor_max_concurrent_nvenc_omitted_when_parallel_is_one():
    args = web_app._build_extra_args("video_editor.py", {"max_concurrent_nvenc": 2})
    assert "--max-concurrent-nvenc" not in args


def test_build_extra_args_video_editor_max_concurrent_nvenc_included_with_parallel():
    args = web_app._build_extra_args("video_editor.py", {"parallel": 4, "max_concurrent_nvenc": 2})
    assert args[args.index("--max-concurrent-nvenc") + 1] == "2"


def test_build_extra_args_video_editor_max_concurrent_nvenc_blank_is_omitted():
    args = web_app._build_extra_args("video_editor.py", {"parallel": 4, "max_concurrent_nvenc": None})
    assert "--max-concurrent-nvenc" not in args


def test_build_extra_args_video_editor_effort_omitted_when_high_or_absent():
    assert "--effort" not in web_app._build_extra_args("video_editor.py", {})
    assert "--effort" not in web_app._build_extra_args("video_editor.py", {"effort": "high"})


def test_build_extra_args_video_editor_effort_included_when_not_high():
    args = web_app._build_extra_args("video_editor.py", {"effort": "medium"})
    assert args[args.index("--effort") + 1] == "medium"


def test_build_extra_args_video_editor_effort_invalid_omitted():
    assert "--effort" not in web_app._build_extra_args("video_editor.py", {"effort": "extreme"})


def test_build_extra_args_video_editor_effort_auto_included():
    args = web_app._build_extra_args("video_editor.py", {"effort": "auto"})
    assert args[args.index("--effort") + 1] == "auto"


def test_build_extra_args_video_editor_container_omitted_when_mp4_or_absent():
    assert "--container" not in web_app._build_extra_args("video_editor.py", {})
    assert "--container" not in web_app._build_extra_args("video_editor.py", {"container": "mp4"})


def test_build_extra_args_video_editor_container_included_when_mkv():
    args = web_app._build_extra_args("video_editor.py", {"container": "mkv"})
    assert args[args.index("--container") + 1] == "mkv"


def test_build_extra_args_video_editor_container_invalid_omitted():
    assert "--container" not in web_app._build_extra_args("video_editor.py", {"container": "webm"})


def test_build_extra_args_video_editor_output_template_included_when_valid():
    args = web_app._build_extra_args("video_editor.py", {"output_template": "{date}_{name}_{codec}"})
    assert args[args.index("--output-template") + 1] == "{date}_{name}_{codec}"


def test_build_extra_args_video_editor_output_template_omitted_when_blank():
    assert "--output-template" not in web_app._build_extra_args("video_editor.py", {"output_template": "   "})


def test_build_extra_args_video_editor_output_template_invalid_placeholder_omitted():
    assert "--output-template" not in web_app._build_extra_args("video_editor.py", {"output_template": "{unknown_field}"})


def test_build_extra_args_video_editor_validate_only_and_notify_per_file_omitted_by_default():
    args = web_app._build_extra_args("video_editor.py", {})
    assert "--validate-only" not in args
    assert "--notify-per-file" not in args


def test_build_extra_args_video_editor_validate_only_and_notify_per_file_included_when_set():
    args = web_app._build_extra_args("video_editor.py", {"validate_only": True, "notify_per_file": True})
    assert "--validate-only" in args
    assert "--notify-per-file" in args


def test_build_extra_args_video_editor_export_report_omitted_by_default():
    assert "--export-report" not in web_app._build_extra_args("video_editor.py", {})
    assert "--export-report" not in web_app._build_extra_args("video_editor.py", {"export_report": ""})


def test_build_extra_args_video_editor_export_report_included_when_valid():
    for value in ("csv", "xlsx", "both"):
        args = web_app._build_extra_args("video_editor.py", {"export_report": value})
        assert args[args.index("--export-report") + 1] == value


def test_build_extra_args_video_editor_export_report_invalid_value_omitted():
    assert "--export-report" not in web_app._build_extra_args("video_editor.py", {"export_report": "pdf"})


def test_build_extra_args_unknown_script_returns_empty():
    assert web_app._build_extra_args("disk_scanner.py", {"ai_provider": "local"}) == []


def test_build_extra_args_rocket_shorts_defaults_to_no_flags():
    assert web_app._build_extra_args("rocket_shorts_publisher.py", {}) == []


def test_build_extra_args_rocket_shorts_all_flags():
    payload = {"dry_run": True, "no_square": True, "no_loudnorm": True}
    assert web_app._build_extra_args("rocket_shorts_publisher.py", payload) == ["--dry-run", "--no-square", "--no-loudnorm"]


def test_build_extra_args_fade_in_out(monkeypatch):
    monkeypatch.setattr(web_app, "parse_fps_value", lambda v: None)
    args = web_app._build_extra_args("video_editor.py", {"fade_in_seconds": 1.5, "fade_out_seconds": 2})
    assert "--fade-in-seconds" in args and "1.5" in args
    assert "--fade-out-seconds" in args and "2.0" in args


def test_build_extra_args_text_overlay(monkeypatch):
    monkeypatch.setattr(web_app, "parse_fps_value", lambda v: None)
    args = web_app._build_extra_args("video_editor.py", {
        "text": "Hello", "text_position": "top", "text_font": "Roboto", "text_font_size": 30, "text_color": "#000000",
    })
    assert args[args.index("--text") + 1] == "Hello"
    assert "--text-position" in args and "top" in args
    assert "--text-font" in args and "Roboto" in args
    assert "--text-font-size" in args and "30" in args
    assert "--text-color" in args and "#000000" in args


def test_build_extra_args_text_overlay_omitted_when_blank():
    args = web_app._build_extra_args("video_editor.py", {"text": "   "})
    assert "--text" not in args


def test_build_extra_args_replace_audio_path():
    args = web_app._build_extra_args("video_editor.py", {"replace_audio_path": "C:\\music.mp3"})
    assert "--replace-audio" in args and "C:\\music.mp3" in args


def test_build_extra_args_remove_ranges_passthrough_string():
    args = web_app._build_extra_args("video_editor.py", {"remove_ranges": "[[1,2]]"})
    assert "--remove-ranges" in args and "[[1,2]]" in args


def test_build_extra_args_remove_ranges_list_serialized_to_json():
    args = web_app._build_extra_args("video_editor.py", {"remove_ranges": [[1, 2], [3, 4]]})
    idx = args.index("--remove-ranges")
    assert json.loads(args[idx + 1]) == [[1, 2], [3, 4]]
