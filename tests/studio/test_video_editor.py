# tests/studio/test_video_editor.py
import os


import pytest

from utils.video.video_editor import (
    CODEC_ARGS,
    DEFAULT_CONTAINER,
    EFFORT_LEVELS,
    EFFORT_NVENC_PRESET,
    HDR_TONEMAP_FILTER,
    LOUDNORM_FILTER,
    LOUDNORM_STATS,
    NOISE_GATE_FILTER,
    SUPPORTED_CONTAINERS,
    VIDEO_EDITOR_PRESETS,
    build_chromakey_filters,
    build_concat_transitions_filter_complex,
    build_edit_filter_complex,
    build_fps_filter,
    build_silence_removal_filters,
    compute_removal_region,
    compute_xfade_offsets,
    compute_render_signature,
    compute_silence_trim_bounds,
    compute_target_bitrate_kbps,
    compute_watermark_geometry,
    get_codec_args,
    get_hdr_output_args,
    get_lut_filter,
    get_two_pass_codec_args,
    get_vidstabdetect_filter,
    get_vidstabtransform_filter,
    is_hdr_source,
    parse_fps_value,
    parse_silence_intervals,
    resolve_auto_effort,
    resolve_effective_output_dimensions,
    resolve_effort_thread_count,
    resolve_output_dimensions,
    resolve_output_filename,
    resolve_output_fps,
    resolve_scale_chain,
    resolve_sig_path,
    resolve_trim_bounds,
    should_skip_scale,
    validate_output_template,
)
from utils.media.timelapse import (
    HORIZONTAL_SCALE_CHAIN,
    HORIZONTAL_SCALE_CHAIN_CUDA,
    VERTICAL_SCALE_CHAIN,
    VERTICAL_SCALE_CHAIN_CUDA,
)


def test_get_codec_args_known_codecs():
    for codec in ("h264", "hevc", "av1"):
        args = get_codec_args(codec)
        assert args == CODEC_ARGS[codec]
        assert "-c:v" in args


def test_get_codec_args_unknown_raises():
    with pytest.raises(ValueError):
        get_codec_args("mpeg2")


def test_get_codec_args_preset_override():
    args = get_codec_args("hevc", preset="p1")
    assert args[args.index("-preset") + 1] == "p1"
    assert args[args.index("-cq") + 1] == "19"  # cq לא נדרס - נשאר ברירת המחדל


def test_get_codec_args_cq_override():
    args = get_codec_args("av1", cq=30)
    assert args[args.index("-cq") + 1] == "30"
    assert args[args.index("-preset") + 1] == "p5"  # preset לא נדרס


def test_get_codec_args_cq_override_uses_crf_for_h264():
    args = get_codec_args("h264", cq=15)
    assert args[args.index("-crf") + 1] == "15"


def test_get_codec_args_no_overrides_matches_defaults():
    assert get_codec_args("hevc", preset=None, cq=None) == CODEC_ARGS["hevc"]


def test_resolve_scale_chain_and_dimensions():
    assert resolve_scale_chain(False) == HORIZONTAL_SCALE_CHAIN
    assert resolve_scale_chain(True) == VERTICAL_SCALE_CHAIN
    assert resolve_output_dimensions(False) == (1920, 1080)
    assert resolve_output_dimensions(True) == (1080, 1920)


def test_resolve_scale_chain_use_hwaccel_returns_cuda_chains():
    assert resolve_scale_chain(False, use_hwaccel=True) == HORIZONTAL_SCALE_CHAIN_CUDA
    assert resolve_scale_chain(True, use_hwaccel=True) == VERTICAL_SCALE_CHAIN_CUDA


# --- smart crop (item: smart crop for vertical conversion) ---

def test_resolve_scale_chain_crop_offset_zero_or_none_unchanged():
    assert resolve_scale_chain(True, crop_x_offset=None) == VERTICAL_SCALE_CHAIN
    assert resolve_scale_chain(True, crop_x_offset=0.0) == VERTICAL_SCALE_CHAIN


def test_resolve_scale_chain_crop_offset_injects_x_expression():
    chain = resolve_scale_chain(True, crop_x_offset=0.5)
    assert "crop=1080:1920:x=(in_w-1080)/2*(1+0.5000):y=(in_h-1920)/2" in chain
    assert chain.startswith("scale=1080:1920:force_original_aspect_ratio=increase,")


def test_resolve_scale_chain_crop_offset_negative():
    chain = resolve_scale_chain(True, crop_x_offset=-1.0)
    assert "x=(in_w-1080)/2*(1+-1.0000)" in chain


def test_resolve_scale_chain_crop_offset_ignored_for_horizontal():
    # אין crop בכלל בשרשרת האופקית (pad, לא crop) - אין מה להזיז.
    assert resolve_scale_chain(False, crop_x_offset=0.7) == HORIZONTAL_SCALE_CHAIN


def test_resolve_scale_chain_crop_offset_with_hwaccel():
    chain = resolve_scale_chain(True, use_hwaccel=True, crop_x_offset=0.3)
    assert "crop=1080:1920:x=(in_w-1080)/2*(1+0.3000):y=(in_h-1920)/2" in chain
    assert "scale_cuda=w=1080:h=1920" in chain  # שאר השרשרת (CUDA) לא נפגעה


# --- skip redundant scale (item: skip-if-already-correct-orientation) ---

def test_should_skip_scale_exact_match():
    assert should_skip_scale(1920, 1080, vertical=False) is True
    assert should_skip_scale(1080, 1920, vertical=True) is True


def test_should_skip_scale_mismatch():
    assert should_skip_scale(1280, 720, vertical=False) is False
    assert should_skip_scale(1920, 1080, vertical=True) is False


def test_should_skip_scale_unknown_dimensions_never_skips():
    assert should_skip_scale(None, 1080, vertical=False) is False
    assert should_skip_scale(1920, None, vertical=False) is False


def test_should_skip_scale_with_target_dimensions_override():
    # target_dimensions (item: --preserve-resolution) - בודק מול יעד מפורש
    # במקום מידות הפלט הקבועות.
    assert should_skip_scale(640, 360, vertical=False, target_dimensions=(640, 360)) is True
    assert should_skip_scale(640, 360, vertical=False, target_dimensions=(1920, 1080)) is False
    assert should_skip_scale(640, 360, vertical=False) is False  # ברירת מחדל (None) - לא נגררת


# --- שימור רזולוציית מקור (item: --preserve-resolution) ---

def test_resolve_effective_output_dimensions_disabled_matches_fixed_output():
    assert resolve_effective_output_dimensions(False, False, 3840, 2160) == (1920, 1080)
    assert resolve_effective_output_dimensions(True, False, 3840, 2160) == (1080, 1920)


def test_resolve_effective_output_dimensions_unknown_input_falls_back_to_fixed():
    assert resolve_effective_output_dimensions(False, True, None, None) == (1920, 1080)
    assert resolve_effective_output_dimensions(False, True, 1920, None) == (1920, 1080)


def test_resolve_effective_output_dimensions_horizontal_preserves_exact_source_size():
    assert resolve_effective_output_dimensions(False, True, 640, 360) == (640, 360)
    assert resolve_effective_output_dimensions(False, True, 3840, 2160) == (3840, 2160)


def test_resolve_effective_output_dimensions_horizontal_rounds_odd_dimensions_up():
    assert resolve_effective_output_dimensions(False, True, 641, 361) == (642, 362)


def test_resolve_effective_output_dimensions_vertical_below_default_keeps_default():
    # מקור קטן מהפלט הקבוע (1080x1920) - "שימור" לא צריך להקטין, נשאר קבוע.
    assert resolve_effective_output_dimensions(True, True, 640, 480) == (1080, 1920)


def test_resolve_effective_output_dimensions_vertical_above_default_scales_up():
    # מקור 2560x1440 (גדול מ-1080p) - קופסת 9:16 בגודל תואם-מקור, לא מוקטן ל-1080x1920.
    assert resolve_effective_output_dimensions(True, True, 2560, 1440) == (1440, 2560)


def test_resolve_scale_chain_target_dimensions_override_horizontal():
    chain = resolve_scale_chain(False, target_width=640, target_height=360)
    assert chain == "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2"


def test_resolve_scale_chain_target_dimensions_override_vertical():
    chain = resolve_scale_chain(True, target_width=1440, target_height=2560)
    assert chain == "scale=1440:2560:force_original_aspect_ratio=increase,crop=1440:2560"


def test_resolve_scale_chain_target_dimensions_matching_default_unchanged():
    assert resolve_scale_chain(False, target_width=1920, target_height=1080) == HORIZONTAL_SCALE_CHAIN


def test_resolve_scale_chain_target_dimensions_with_crop_offset():
    chain = resolve_scale_chain(True, crop_x_offset=0.5, target_width=1440, target_height=2560)
    assert "crop=1440:2560:x=(in_w-1440)/2*(1+0.5000):y=(in_h-2560)/2" in chain


# --- דרגות מאמץ קידוד (item: --effort) ---

def test_resolve_effort_thread_count_high_means_unlimited():
    assert resolve_effort_thread_count("high", cpu_count=16) == 0


def test_resolve_effort_thread_count_low_is_fixed_small_value():
    assert resolve_effort_thread_count("low", cpu_count=16) == 2
    assert resolve_effort_thread_count("low", cpu_count=2) == 2


def test_resolve_effort_thread_count_medium_is_half_cpu_count():
    assert resolve_effort_thread_count("medium", cpu_count=16) == 8
    assert resolve_effort_thread_count("medium", cpu_count=3) == 2  # קלאמפ ל-2 לפחות


def test_resolve_effort_thread_count_unknown_cpu_count_falls_back():
    assert resolve_effort_thread_count("medium", cpu_count=None) == 2


def test_effort_levels_and_nvenc_preset_mapping():
    assert EFFORT_LEVELS == ("low", "medium", "high", "auto")
    assert EFFORT_NVENC_PRESET["high"] is None
    assert EFFORT_NVENC_PRESET["low"] != EFFORT_NVENC_PRESET["medium"]


# --- זיהוי עומס-מחשב אוטומטי ל---effort (item: --effort auto) ---

def test_resolve_auto_effort_high_load_returns_low():
    assert resolve_auto_effort(80, 10) == "low"
    assert resolve_auto_effort(10, 90) == "low"


def test_resolve_auto_effort_medium_load_returns_medium():
    assert resolve_auto_effort(50, 10) == "medium"


def test_resolve_auto_effort_low_load_returns_high():
    assert resolve_auto_effort(10, 5) == "high"


def test_resolve_auto_effort_unknown_load_returns_high():
    assert resolve_auto_effort(None, None) == "high"


def test_resolve_auto_effort_partial_unknown_uses_known_axis():
    assert resolve_auto_effort(None, 90) == "low"
    assert resolve_auto_effort(75, None) == "low"


def test_resolve_auto_effort_boundaries():
    assert resolve_auto_effort(70, 0) == "low"
    assert resolve_auto_effort(69.9, 0) == "medium"
    assert resolve_auto_effort(40, 0) == "medium"
    assert resolve_auto_effort(39.9, 0) == "high"


# --- מיכל יצוא + תבנית שם-קובץ מותאמת אישית (items: --container, --output-template) ---

def test_supported_containers_excludes_webm():
    assert SUPPORTED_CONTAINERS == ("mp4", "mkv")
    assert DEFAULT_CONTAINER == "mp4"


def test_resolve_output_filename_default_behavior_matches_old_suffix_scheme():
    assert resolve_output_filename("clip", vertical=False) == "clip_edited_horizontal.mp4"
    assert resolve_output_filename("clip", vertical=True) == "clip_edited_vertical.mp4"


def test_resolve_output_filename_no_suffix():
    assert resolve_output_filename("clip", vertical=False, no_suffix=True) == "clip.mp4"


def test_resolve_output_filename_custom_container():
    assert resolve_output_filename("clip", vertical=False, container="mkv") == "clip_edited_horizontal.mkv"


def test_resolve_output_filename_template_overrides_no_suffix():
    name = resolve_output_filename("clip", vertical=True, no_suffix=True, template="{name}_{codec}_{orientation}", codec="hevc")
    assert name == "clip_hevc_vertical.mp4"


def test_resolve_output_filename_template_date_placeholder_is_yyyymmdd():
    name = resolve_output_filename("clip", vertical=False, template="{date}_{name}")
    date_part = name.split("_")[0]
    assert len(date_part) == 8 and date_part.isdigit()


def test_resolve_output_filename_number_placeholder():
    assert resolve_output_filename("clip", vertical=False, template="Clip #{number}", number=7) == "Clip #7.mp4"


def test_resolve_output_filename_number_placeholder_missing_number_is_blank():
    # number לא הועבר בכלל (None) - לא זורק, פשוט מרנדר ריק (item: מספור
    # סרטונים לא רלוונטי לריצה הזו כלל, ה-template בכל זאת מזכיר {number}).
    assert resolve_output_filename("clip", vertical=False, template="Clip #{number}") == "Clip #.mp4"


def test_validate_output_template_accepts_number_placeholder():
    validate_output_template("Clip #{number}")  # לא זורק


def test_validate_output_template_accepts_known_placeholders():
    validate_output_template("{date}_{name}_{codec}_{orientation}")  # לא זורק


def test_validate_output_template_rejects_unknown_placeholder():
    with pytest.raises(ValueError):
        validate_output_template("{name}_{resolution}")


# --- תיקיית SIG נפרדת (item: --sig בתת-תיקייה) ---

def test_resolve_sig_path_uses_sig_subdir_next_to_output():
    output_path = os.path.join("workspace", "studio", "horizontal", "clip_edited_horizontal.mp4")
    expected = os.path.join("workspace", "studio", "horizontal", "_sig", "clip_edited_horizontal.mp4.sig.json")
    assert resolve_sig_path(output_path) == expected


def test_resolve_sig_path_distinguishes_same_basename_in_different_dirs():
    sig_a = resolve_sig_path(os.path.join("workspace", "studio", "horizontal", "clip.mp4"))
    sig_b = resolve_sig_path(os.path.join("workspace", "studio", "vertical", "clip.mp4"))
    assert sig_a != sig_b


# --- trim range (item: trim range) ---

def test_resolve_trim_bounds_no_trim_requested():
    assert resolve_trim_bounds(120.0, 0.0, None) == (0.0, 120.0)


def test_resolve_trim_bounds_start_only():
    assert resolve_trim_bounds(120.0, 30.0, None) == (30.0, 90.0)


def test_resolve_trim_bounds_start_and_duration():
    assert resolve_trim_bounds(120.0, 10.0, 20.0) == (10.0, 20.0)


def test_resolve_trim_bounds_duration_clamped_to_remaining():
    # ביקשו 50 שניות אחרי חיתוך-התחלה של 100 מתוך 120 - נשארו רק 20.
    assert resolve_trim_bounds(120.0, 100.0, 50.0) == (100.0, 20.0)


def test_resolve_trim_bounds_start_beyond_duration_clamped():
    start, duration = resolve_trim_bounds(60.0, 999.0, None)
    assert start == 60.0
    assert duration == 0.0


def test_resolve_trim_bounds_negative_start_clamped_to_zero():
    assert resolve_trim_bounds(60.0, -5.0, None) == (0.0, 60.0)


# --- auto-trim silence (item: auto-trim silence) ---

def test_parse_silence_intervals_basic():
    stderr = (
        "[silencedetect @ 0x1] silence_start: 0\n"
        "[silencedetect @ 0x1] silence_end: 1.5 | silence_duration: 1.5\n"
        "[silencedetect @ 0x1] silence_start: 58.2\n"
        "[silencedetect @ 0x1] silence_end: 60.0 | silence_duration: 1.8\n"
    )
    assert parse_silence_intervals(stderr) == [(0.0, 1.5), (58.2, 60.0)]


def test_parse_silence_intervals_no_silence():
    assert parse_silence_intervals("no silencedetect lines here") == []


def test_parse_silence_intervals_trailing_silence_to_eof_without_duration():
    stderr = "[silencedetect @ 0x1] silence_start: 55.0\n"
    assert parse_silence_intervals(stderr) == []  # אין duration - לא ניתן "לסגור" את המרווח
    assert parse_silence_intervals(stderr, duration=60.0) == [(55.0, 60.0)]


def test_compute_silence_trim_bounds_no_intervals():
    assert compute_silence_trim_bounds(60.0, []) == (0.0, None)


def test_compute_silence_trim_bounds_leading_silence_only():
    intervals = [(0.0, 3.0)]
    assert compute_silence_trim_bounds(60.0, intervals) == (3.0, 57.0)


def test_compute_silence_trim_bounds_trailing_silence_only():
    intervals = [(57.0, 60.0)]
    assert compute_silence_trim_bounds(60.0, intervals) == (0.0, 57.0)


def test_compute_silence_trim_bounds_both_ends():
    intervals = [(0.0, 2.0), (58.0, 60.0)]
    assert compute_silence_trim_bounds(60.0, intervals) == (2.0, 56.0)


def test_compute_silence_trim_bounds_middle_silence_ignored():
    # שקט באמצע הקובץ (לא נוגע לאף קצה) - זה trim, לא ניקוי-שקטים כללי.
    intervals = [(25.0, 27.0)]
    assert compute_silence_trim_bounds(60.0, intervals) == (0.0, None)


def test_compute_silence_trim_bounds_short_edge_silence_ignored():
    # פחות מ-min_silence_seconds (ברירת מחדל 0.3) - מיקרו-פאוזה, לא "פתיח שקט".
    intervals = [(0.0, 0.1)]
    assert compute_silence_trim_bounds(60.0, intervals) == (0.0, None)


def test_compute_silence_trim_bounds_entirely_silent_clip():
    intervals = [(0.0, 60.0)]
    trim_start, trim_duration = compute_silence_trim_bounds(60.0, intervals)
    assert trim_duration <= 0.0


def test_compute_watermark_geometry_bottom_right():
    # וואטרמארק ריבועי (200x200), 15% מרוחב פלט 1920 = 288px, מרג'ין 20
    target_w, target_h, x, y = compute_watermark_geometry(1920, 1080, 200, 200, "bottom-right", scale_fraction=0.15, margin=20)
    assert target_w == 288
    assert target_h == 288
    assert x == 1920 - 288 - 20
    assert y == 1080 - 288 - 20


def test_compute_watermark_geometry_top_left():
    target_w, target_h, x, y = compute_watermark_geometry(1920, 1080, 200, 200, "top-left", scale_fraction=0.15, margin=20)
    assert (x, y) == (20, 20)


def test_compute_watermark_geometry_center():
    target_w, target_h, x, y = compute_watermark_geometry(1920, 1080, 200, 200, "center", scale_fraction=0.15, margin=20)
    assert x == (1920 - target_w) // 2
    assert y == (1080 - target_h) // 2


def test_compute_watermark_geometry_preserves_aspect_ratio():
    # וואטרמארק רחב (400x100, יחס 4:1) - הגובה המוקטן צריך לשמור על אותו יחס
    target_w, target_h, _x, _y = compute_watermark_geometry(1920, 1080, 400, 100, "center")
    assert target_h == round(target_w / 4)


def test_compute_watermark_geometry_clamped_when_oversized():
    # scale_fraction ענק שגורם ל-watermark גדול מהפריים - x/y לא אמורים לצאת שליליים
    target_w, target_h, x, y = compute_watermark_geometry(200, 200, 100, 100, "bottom-right", scale_fraction=2.0, margin=20)
    assert x >= 0
    assert y >= 0


def test_compute_watermark_geometry_tall_watermark_does_not_overflow_height():
    # רגרסיה שנמצאה ע"י tests/studio/test_property_based_video_math.py (hypothesis):
    # scale_fraction מגביל רק את הרוחב - watermark צר וגבוה מאוד (יחס 1:3) על
    # פריים ריבועי היה מפיק target_h=150 על output_height=100 (חורג מהפריים).
    target_w, target_h, x, y = compute_watermark_geometry(100, 100, 1, 3, "top-left", scale_fraction=0.5)
    assert target_h <= 100
    assert y + target_h <= 100


def test_compute_watermark_geometry_invalid_position_raises():
    with pytest.raises(ValueError):
        compute_watermark_geometry(1920, 1080, 200, 200, "top-middle")


def test_compute_watermark_geometry_invalid_dims_raise():
    with pytest.raises(ValueError):
        compute_watermark_geometry(1920, 1080, 0, 200, "center")


def test_compute_watermark_geometry_top_center():
    target_w, target_h, x, y = compute_watermark_geometry(1920, 1080, 200, 200, "top-center", scale_fraction=0.15, margin=20)
    assert x == (1920 - target_w) // 2
    assert y == 20


def test_compute_watermark_geometry_bottom_center():
    target_w, target_h, x, y = compute_watermark_geometry(1920, 1080, 200, 200, "bottom-center", scale_fraction=0.15, margin=20)
    assert x == (1920 - target_w) // 2
    assert y == 1080 - target_h - 20


def test_compute_watermark_geometry_custom_center_fraction_overrides_position():
    # item: גרירת watermark חופשית - custom_center_fraction גובר על position
    # כליל (כאן "bottom-right", שהיה נותן x/y אחרים לגמרי בלי custom).
    target_w, target_h, x, y = compute_watermark_geometry(
        1000, 1000, 200, 200, "bottom-right", scale_fraction=0.1, custom_center_fraction=(0.5, 0.5),
    )
    assert (x + target_w / 2, y + target_h / 2) == (500, 500)


def test_compute_watermark_geometry_custom_center_fraction_at_edge_is_clamped_not_offscreen():
    # מרכז ב-(0,0) (פינה שמאלית-עליונה) - חצי מה-watermark "רוצה" לצאת שלילי,
    # אבל x/y עצמם (הפינה השמאלית-עליונה שלו) חייבים להישאר >= 0 בפועל.
    target_w, target_h, x, y = compute_watermark_geometry(
        1000, 1000, 200, 200, "center", scale_fraction=0.1, custom_center_fraction=(0.0, 0.0),
    )
    assert x == 0
    assert y == 0


def test_compute_watermark_geometry_custom_center_fraction_out_of_range_is_clamped():
    # 1.5/-0.5 (קלט לא תקין, למשל גרירה שנתקעה מעבר לגבולות התצוגה המקדימה) -
    # לא זורק, מהודק בשקט ל-0.0/1.0 כמו כל שאר ה-clamp-ים בפונקציה הזו.
    target_w, target_h, x, y = compute_watermark_geometry(
        1000, 1000, 200, 200, "center", scale_fraction=0.1, custom_center_fraction=(1.5, -0.5),
    )
    assert x == 1000 - target_w
    assert y == 0


def test_compute_removal_region_bottom_right():
    # 20%/12% מרוחב/גובה פריים 1920x1080, מרג'ין 20 - בדיוק אותה לוגיקת
    # מיקום/הידוק כמו compute_watermark_geometry, בלי תמונת מקור.
    x, y, w, h = compute_removal_region(1920, 1080, "bottom-right", width_fraction=0.2, height_fraction=0.12, margin=20)
    assert w == int(1920 * 0.2)
    assert h == int(1080 * 0.12)
    assert x == 1920 - w - 20
    assert y == 1080 - h - 20


def test_compute_removal_region_top_left():
    x, y, _w, _h = compute_removal_region(1920, 1080, "top-left", margin=20)
    assert (x, y) == (20, 20)


def test_compute_removal_region_clamped_when_oversized():
    x, y, _w, _h = compute_removal_region(200, 200, "bottom-right", width_fraction=2.0, height_fraction=2.0, margin=20)
    assert x >= 0
    assert y >= 0


def test_compute_removal_region_invalid_position_raises():
    with pytest.raises(ValueError):
        compute_removal_region(1920, 1080, "top-middle")


def test_compute_removal_region_invalid_fractions_raise():
    with pytest.raises(ValueError):
        compute_removal_region(1920, 1080, "center", width_fraction=0)


def test_build_edit_filter_complex_no_watermark_no_speed_no_audio():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30)
    assert filter_complex == f"[0:v]{HORIZONTAL_SCALE_CHAIN},fps=30[outv]"
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_with_watermark():
    geometry = (288, 288, 1612, 772)
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=geometry)
    assert "[1:v]scale=288:288[wm]" in filter_complex
    assert "[base][wm]overlay=1612:772[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_with_pip_alone():
    geometry = (300, 200, 50, 50)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, pip_geometry=geometry, pip_input_index=1
    )
    assert "[1:v]scale=300:200[pip]" in filter_complex
    assert filter_complex.endswith("overlay=50:50[outv]")
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_with_pip_and_watermark_together():
    # item: PiP - watermark (מיתוג) נשאר תמיד עליון/אחרון בשרשרת, ו-PiP תופס
    # אינדקס-קלט 1 (לפני watermark, שעובר לאינדקס 2) - בודק גם את סדר
    # ה-overlay-ים וגם את הזזת אינדקס ה-watermark יחד, לא רק אחד מהם.
    pip_geometry = (300, 200, 50, 50)
    watermark_geometry = (288, 288, 1612, 772)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=watermark_geometry,
        pip_geometry=pip_geometry, pip_input_index=1,
    )
    assert "[1:v]scale=300:200[pip]" in filter_complex
    assert "[base][pip]overlay=50:50[after_pip]" in filter_complex
    assert "[2:v]scale=288:288[wm]" in filter_complex
    assert "[after_pip][wm]overlay=1612:772[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_pip_opacity_below_one_adds_alpha_channel():
    geometry = (300, 200, 50, 50)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, pip_geometry=geometry, pip_input_index=1, pip_opacity=0.5,
    )
    assert "[1:v]format=rgba,colorchannelmixer=aa=0.50,scale=300:200[pip]" in filter_complex


def test_build_edit_filter_complex_pip_ignored_without_use_hwaccel_flag_combo():
    # pip_geometry ניתן אבל use_hwaccel=True - מתעלם בשקט (אין מקבילת CUDA),
    # התנהגות זהה בדיוק ל-watermark-בלבד (בלי PiP בכלל).
    watermark_geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, watermark_geometry=watermark_geometry,
        pip_geometry=(300, 200, 50, 50), pip_input_index=1,
        use_hwaccel=True, output_width=1920, output_height=1080,
    )
    assert "[pip]" not in filter_complex
    assert "[1:v]format=nv12,hwupload_cuda,scale_cuda=w=288:h=288[wm]" in filter_complex
    assert "[base][wm]overlay_cuda=1612:772" in filter_complex


def test_build_edit_filter_complex_with_removal_region():
    region = (10, 20, 300, 100)
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, removal_region=region)
    assert filter_complex.startswith(f"[0:v]delogo=x=10:y=20:w=300:h=100,{HORIZONTAL_SCALE_CHAIN},fps=30[outv]")
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_removal_region_runs_before_scale():
    # delogo חייב לרוץ על רזולוציית הקלט המקורית (לפני שינוי גודל לפלט) - ראו
    # התיעוד ב-build_edit_filter_complex. בודק סדר מפורש, לא רק "מכיל".
    region = (0, 0, 50, 50)
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, removal_region=region)
    delogo_pos = filter_complex.index("delogo=")
    scale_pos = filter_complex.index(HORIZONTAL_SCALE_CHAIN)
    assert delogo_pos < scale_pos


def test_build_edit_filter_complex_removal_region_combined_with_new_watermark():
    # מוחקים watermark ישן ומוסיפים אחד חדש (אולי במיקום אחר) באותה ריצה
    removal = (0, 0, 100, 50)
    watermark = (288, 288, 1612, 772)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=watermark, removal_region=removal
    )
    assert "delogo=x=0:y=0:w=100:h=50" in filter_complex
    assert "[base][wm]overlay=1612:772[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_hwaccel_with_watermark_uses_cuda_filters_and_fixes_alignment():
    # overlay_cuda בבנייה שנבדקה ידנית מדליף גובה מיושר-16 בפועל (1920x1088
    # במקום 1920x1080) - scale_cuda נוסף עם passthrough=0 אחריו מתקן את זה.
    # ראו build_edit_filter_complex's docstring למה passthrough=0 (לא ברירת
    # המחדל) הכרחי כאן.
    geometry = (288, 288, 1612, 772)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, watermark_geometry=geometry,
        use_hwaccel=True, output_width=1920, output_height=1080,
    )
    assert "[1:v]format=nv12,hwupload_cuda,scale_cuda=w=288:h=288[wm]" in filter_complex
    assert "[base][wm]overlay_cuda=1612:772,scale_cuda=w=1920:h=1080:passthrough=0[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_hwaccel_with_watermark_requires_output_dimensions():
    geometry = (288, 288, 1612, 772)
    with pytest.raises(ValueError):
        build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN_CUDA, 30, watermark_geometry=geometry, use_hwaccel=True)


def test_build_edit_filter_complex_hwaccel_with_removal_region_bridges_cpu_delogo():
    # delogo אין לו מקבילת CUDA - hwdownload/format=nv12 לפניו,
    # format=nv12/hwupload_cuda אחריו, כדי שהשרשרת תחזור ל-GPU מיד.
    region = (10, 20, 300, 100)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, removal_region=region, use_hwaccel=True,
    )
    assert filter_complex.startswith(
        f"[0:v]hwdownload,format=nv12,delogo=x=10:y=20:w=300:h=100,format=nv12,hwupload_cuda,{HORIZONTAL_SCALE_CHAIN_CUDA},fps=30[outv]"
    )
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_hwaccel_without_removal_region_has_no_cpu_bridge():
    # בלי delogo בכלל, אין שום סיבה לרדת ל-CPU - השרשרת כולה נשארת CUDA.
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN_CUDA, 30, use_hwaccel=True)
    assert "hwdownload" not in filter_complex
    assert filter_complex == f"[0:v]{HORIZONTAL_SCALE_CHAIN_CUDA},fps=30[outv]"


def test_build_edit_filter_complex_hwaccel_combined_removal_region_and_watermark():
    removal = (0, 0, 100, 50)
    watermark = (288, 288, 1612, 772)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, watermark_geometry=watermark, removal_region=removal,
        use_hwaccel=True, output_width=1920, output_height=1080,
    )
    assert "hwdownload,format=nv12,delogo=x=0:y=0:w=100:h=50,format=nv12,hwupload_cuda" in filter_complex
    assert "overlay_cuda=1612:772,scale_cuda=w=1920:h=1080:passthrough=0[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_with_speed_and_audio():
    # מקדם 1.5 נשאר בטווח atempo יחיד (0.5-2.0) - לא מצריך שרשור, בניגוד ל-4.0
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, setpts_expr="setpts=PTS/1.500000", speed_factor=1.5, keep_audio=True
    )
    assert "setpts=PTS/1.500000" in filter_complex
    assert "[0:a]atempo=1.500000[outa]" in filter_complex
    assert maps == ["-map", "[outv]", "-map", "[outa]"]


def test_build_edit_filter_complex_keep_audio_without_speed_maps_original():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True)
    assert maps == ["-map", "[outv]", "-map", "0:a?"]
    assert "0:a" not in filter_complex.split(";")[0]


def test_build_edit_filter_complex_loudnorm_without_speed_routes_through_filter_complex():
    # בלי loudnorm/atempo, אודיו ממופה ישירות (0:a?) - ברגע שיש loudnorm, ffmpeg
    # לא מרשה יותר מיפוי ישיר על stream, חייב לעבור filter_complex גם הוא.
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, loudnorm=True)
    assert "[0:a]loudnorm=I=-14:LRA=11:TP=-1.5:print_format=json,aresample=48000[outa]" in filter_complex
    assert maps == ["-map", "[outv]", "-map", "[outa]"]


def test_build_edit_filter_complex_loudnorm_with_speed_chains_after_atempo():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, setpts_expr="setpts=PTS/1.500000", speed_factor=1.5, keep_audio=True, loudnorm=True
    )
    assert "[0:a]atempo=1.500000,loudnorm=I=-14:LRA=11:TP=-1.5:print_format=json,aresample=48000[outa]" in filter_complex


def test_build_edit_filter_complex_loudnorm_without_keep_audio_has_no_effect():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, loudnorm=True)
    assert "loudnorm" not in filter_complex
    assert maps == ["-map", "[outv]"]


# --- watermark opacity (item) ---

def test_build_edit_filter_complex_watermark_opacity_applies_colorchannelmixer():
    geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=geometry, watermark_opacity=0.5,
    )
    assert "[1:v]format=rgba,colorchannelmixer=aa=0.50,scale=288:288[wm]" in filter_complex


def test_build_edit_filter_complex_watermark_opacity_full_opaque_has_no_effect():
    geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=geometry, watermark_opacity=1.0,
    )
    assert "colorchannelmixer" not in filter_complex
    assert "[1:v]scale=288:288[wm]" in filter_complex


def test_build_edit_filter_complex_watermark_opacity_none_has_no_effect():
    geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=geometry)
    assert "colorchannelmixer" not in filter_complex


def test_build_edit_filter_complex_watermark_opacity_ignored_with_hwaccel():
    # nv12 (מה שה-watermark מומר אליו לפני overlay_cuda) אין לו ערוץ אלפא -
    # אין דרך לבטא שקיפות שם, אז opacity מתעלם בשקט בנתיב ה-hwaccel.
    geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, watermark_geometry=geometry, watermark_opacity=0.3,
        use_hwaccel=True, output_width=1920, output_height=1080,
    )
    assert "colorchannelmixer" not in filter_complex


# --- denoise / sharpen (item) ---

def test_build_edit_filter_complex_denoise_adds_hqdn3d_before_scale():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, denoise=True)
    assert filter_complex == f"[0:v]hqdn3d,{HORIZONTAL_SCALE_CHAIN},fps=30[outv]"


def test_build_edit_filter_complex_denoise_ignored_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN_CUDA, 30, denoise=True, use_hwaccel=True)
    assert "hqdn3d" not in filter_complex


def test_build_edit_filter_complex_sharpen_adds_unsharp_after_fps():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, sharpen=True)
    assert filter_complex == f"[0:v]{HORIZONTAL_SCALE_CHAIN},fps=30,unsharp[outv]"


def test_build_edit_filter_complex_denoise_and_sharpen_combined_with_watermark():
    geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=geometry, denoise=True, sharpen=True,
    )
    assert filter_complex.startswith(f"[0:v]hqdn3d,{HORIZONTAL_SCALE_CHAIN},fps=30,unsharp[base]")


# --- configurable loudnorm target (item) ---

def test_build_edit_filter_complex_custom_loudnorm_filter_overrides_default():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, loudnorm=True, loudnorm_filter="loudnorm=I=-20:LRA=11:TP=-1.5",
    )
    assert "[0:a]loudnorm=I=-20:LRA=11:TP=-1.5:print_format=json,aresample=48000[outa]" in filter_complex
    assert LOUDNORM_FILTER not in filter_complex


# --- שימור FPS מקורי (item) ---

def test_parse_fps_value_plain_integer():
    assert parse_fps_value("30") == 30.0


def test_parse_fps_value_decimal():
    assert parse_fps_value("29.97") == 29.97


def test_parse_fps_value_fraction():
    assert parse_fps_value("30000/1001") == pytest.approx(29.9700299700)


def test_parse_fps_value_rejects_zero_or_negative():
    with pytest.raises(ValueError):
        parse_fps_value("0")
    with pytest.raises(ValueError):
        parse_fps_value("-30")


def test_parse_fps_value_rejects_zero_denominator():
    with pytest.raises(ValueError):
        parse_fps_value("30/0")


def test_parse_fps_value_rejects_garbage():
    with pytest.raises(ValueError):
        parse_fps_value("not-a-number")


def test_resolve_output_fps_explicit_override_wins():
    fps_str, fps_value = resolve_output_fps("60", "30000/1001")
    assert fps_str == "60"
    assert fps_value == 60.0


def test_resolve_output_fps_preserves_source_when_no_override():
    fps_str, fps_value = resolve_output_fps(None, "30000/1001")
    assert fps_str == "30000/1001"
    assert fps_value == pytest.approx(29.9700299700)


def test_resolve_output_fps_falls_back_to_default_when_source_unknown():
    fps_str, fps_value = resolve_output_fps(None, None)
    assert fps_str == "30"
    assert fps_value == 30.0


def test_resolve_output_fps_falls_back_to_default_when_source_unparsable():
    fps_str, fps_value = resolve_output_fps(None, "0/0")
    assert fps_str == "30"
    assert fps_value == 30.0


def test_build_edit_filter_complex_accepts_fractional_fps_string():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, "30000/1001")
    assert "fps=30000/1001" in filter_complex


# --- שימור הגדרות HDR (item) ---

def test_is_hdr_source_detects_pq():
    assert is_hdr_source("smpte2084") is True


def test_is_hdr_source_detects_hlg():
    assert is_hdr_source("arib-std-b67") is True


def test_is_hdr_source_sdr_is_false():
    assert is_hdr_source("bt709") is False


def test_is_hdr_source_none_is_false():
    assert is_hdr_source(None) is False


def test_get_hdr_output_args_includes_pix_fmt_and_color_tags():
    args = get_hdr_output_args("bt2020", "smpte2084", "bt2020nc")
    assert args == [
        "-pix_fmt", "p010le",
        "-color_primaries", "bt2020",
        "-color_trc", "smpte2084",
        "-colorspace", "bt2020nc",
    ]


def test_get_hdr_output_args_omits_missing_fields():
    args = get_hdr_output_args(None, "smpte2084", None)
    assert args == ["-pix_fmt", "p010le", "-color_trc", "smpte2084"]


def test_build_edit_filter_complex_tonemap_to_sdr_prepends_filter():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, tonemap_to_sdr=True)
    assert filter_complex == f"[0:v]{HDR_TONEMAP_FILTER},{HORIZONTAL_SCALE_CHAIN},fps=30[outv]"


def test_build_edit_filter_complex_tonemap_to_sdr_ignored_with_hwaccel():
    # אין מקבילת CUDA ל-zscale/tonemap מוכחת בפרויקט הזה - אותו דפוס כמו denoise/sharpen.
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN_CUDA, 30, tonemap_to_sdr=True, use_hwaccel=True)
    assert "tonemap" not in filter_complex


def test_build_edit_filter_complex_tonemap_to_sdr_runs_before_removal_region():
    region = (10, 20, 300, 100)
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, tonemap_to_sdr=True, removal_region=region)
    tonemap_pos = filter_complex.index("tonemap")
    delogo_pos = filter_complex.index("delogo=")
    assert tonemap_pos < delogo_pos


# --- LUT (item) ---

def test_get_lut_filter_basic_path():
    assert get_lut_filter("/tmp/looks/my_lut.cube") == "lut3d=file='/tmp/looks/my_lut.cube'"


def test_get_lut_filter_escapes_windows_path():
    assert get_lut_filter("C:\\Looks\\my_lut.cube") == "lut3d=file='C\\:/Looks/my_lut.cube'"


def test_build_edit_filter_complex_lut_applied_after_sharpen():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, sharpen=True, lut_path="/tmp/my_lut.cube")
    assert filter_complex == f"[0:v]{HORIZONTAL_SCALE_CHAIN},fps=30,unsharp,lut3d=file='/tmp/my_lut.cube'[outv]"


def test_build_edit_filter_complex_no_lut_has_no_lut3d():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30)
    assert "lut3d" not in filter_complex


# --- auto-levels (item) ---

def test_build_edit_filter_complex_auto_levels_adds_normalize_before_scale():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, auto_levels=True)
    assert filter_complex == f"[0:v]normalize,{HORIZONTAL_SCALE_CHAIN},fps=30[outv]"


def test_build_edit_filter_complex_auto_levels_ignored_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN_CUDA, 30, auto_levels=True, use_hwaccel=True)
    assert "normalize" not in filter_complex


def test_build_edit_filter_complex_auto_levels_runs_before_denoise_position_combined():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, denoise=True, auto_levels=True)
    assert filter_complex == f"[0:v]hqdn3d,normalize,{HORIZONTAL_SCALE_CHAIN},fps=30[outv]"


# --- אינטרפולציית פריימים חלקה (item) ---

def test_build_fps_filter_plain():
    assert build_fps_filter(30) == "fps=30"


def test_build_fps_filter_smooth_uses_minterpolate():
    assert build_fps_filter(60, smooth=True) == "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:vsbmc=1"


def test_build_edit_filter_complex_smooth_fps_uses_minterpolate():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 60, smooth_fps=True)
    assert "minterpolate=fps=60" in filter_complex
    assert "fps=60" not in filter_complex.replace("minterpolate=fps=60", "")


def test_build_edit_filter_complex_smooth_fps_ignored_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN_CUDA, 60, smooth_fps=True, use_hwaccel=True)
    assert "minterpolate" not in filter_complex
    assert "fps=60" in filter_complex


# --- הסרת שקט באמצע הקובץ, מסונכרן (item) ---

def test_build_silence_removal_filters_empty_intervals():
    assert build_silence_removal_filters([]) == ("", "")


def test_build_silence_removal_filters_builds_matching_select_aselect():
    video_filter, audio_filter = build_silence_removal_filters([(1.0, 2.5), (10.0, 11.25)])
    assert video_filter == "select='not(between(t,1.000,2.500)+between(t,10.000,11.250))',setpts=N/FRAME_RATE/TB"
    assert audio_filter == "aselect='not(between(t,1.000,2.500)+between(t,10.000,11.250))',asetpts=N/SR/TB"


def test_build_edit_filter_complex_silence_removal_applies_to_both_streams():
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, silence_removal_intervals=[(1.0, 2.0)],
    )
    assert "select='not(between(t,1.000,2.000))',setpts=N/FRAME_RATE/TB" in filter_complex
    assert "[0:a]aselect='not(between(t,1.000,2.000))',asetpts=N/SR/TB[outa]" in filter_complex
    assert maps == ["-map", "[outv]", "-map", "[outa]"]


def test_build_edit_filter_complex_silence_removal_runs_before_timelapse_setpts():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, setpts_expr="setpts=PTS/2.000000", silence_removal_intervals=[(1.0, 2.0)],
    )
    select_pos = filter_complex.index("select=")
    timelapse_pos = filter_complex.index("setpts=PTS/2.000000")
    assert select_pos < timelapse_pos


def test_build_edit_filter_complex_no_silence_intervals_is_a_no_op():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, silence_removal_intervals=[])
    assert "select=" not in filter_complex


# --- early_fps_drop (item: טיימלאפס מהיר יותר - fps= לפני scale/watermark/
# sharpen/lut במקום אחריהם, כש-setpts_expr קיים בלי פילטר תלוי-שכנים) ---

def test_build_edit_filter_complex_high_speed_timelapse_moves_fps_before_scale():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, setpts_expr="setpts=PTS/200.000000",
    )
    fps_pos = filter_complex.index("fps=30")
    scale_pos = filter_complex.index(HORIZONTAL_SCALE_CHAIN)
    assert fps_pos < scale_pos
    assert filter_complex.count("fps=30") == 1


def test_build_edit_filter_complex_no_setpts_keeps_fps_after_scale():
    # בלי טיימלאפס (setpts_expr=None) אין מה "לחסוך" - הסדר הרגיל (scale ואז fps) נשאר.
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30)
    fps_pos = filter_complex.index("fps=30")
    scale_pos = filter_complex.index(HORIZONTAL_SCALE_CHAIN)
    assert scale_pos < fps_pos


@pytest.mark.parametrize("blocking_kwargs", [
    {"denoise": True},
    {"auto_levels": True},
    {"stabilize_transform_path": "transforms.trf"},
    {"silence_removal_intervals": [(1.0, 2.0)]},
    {"smooth_fps": True},
])
def test_build_edit_filter_complex_early_fps_drop_disabled_with_temporal_filters(blocking_kwargs):
    # denoise/auto_levels/stabilize/silence-removal/smooth_fps תלויים בשכנים-בזמן
    # אמיתיים (או, ל-smooth_fps, ביוצרים פריימים חדשים) - ההיגיון של "fps= לא
    # תלוי בתוכן אז אפשר להזיז אותו" לא תקף להם, נשארים בסדר הרגיל (scale לפני fps).
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, setpts_expr="setpts=PTS/200.000000", **blocking_kwargs,
    )
    fps_pos = filter_complex.index("fps=30")
    scale_pos = filter_complex.index(HORIZONTAL_SCALE_CHAIN)
    assert scale_pos < fps_pos


def test_build_edit_filter_complex_early_fps_drop_disabled_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, setpts_expr="setpts=PTS/200.000000", use_hwaccel=True,
    )
    fps_pos = filter_complex.index("fps=30")
    scale_pos = filter_complex.index(HORIZONTAL_SCALE_CHAIN_CUDA)
    assert scale_pos < fps_pos


def test_build_edit_filter_complex_early_fps_drop_still_composites_watermark_correctly():
    watermark = compute_watermark_geometry(1920, 1080, 300, 150, "bottom-right", scale_fraction=0.15, margin=20)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, setpts_expr="setpts=PTS/200.000000", watermark_geometry=watermark,
    )
    fps_pos = filter_complex.index("fps=30")
    scale_pos = filter_complex.index(HORIZONTAL_SCALE_CHAIN)
    assert fps_pos < scale_pos
    assert filter_complex.count("fps=30") == 1
    assert "[base][wm]overlay=" in filter_complex
    assert filter_complex.rstrip().endswith("[outv]")
    assert maps == ["-map", "[outv]"]
    assert "aselect=" not in filter_complex


# --- Fade-in/fade-out (item) ---

def test_build_edit_filter_complex_fade_in_applied_to_video():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, fade_in_seconds=2.0)
    assert "[outv]fade=t=in:st=0:d=2.000[outv2]" in filter_complex
    assert maps == ["-map", "[outv2]"]


def test_build_edit_filter_complex_fade_out_requires_output_duration():
    # בלי output_duration_seconds אין דרך לחשב מתי ה-fade-out *מתחיל* - מתעלם בשקט.
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, fade_out_seconds=2.0)
    assert "fade=t=out" not in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_fade_out_start_time_computed_from_duration():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, fade_out_seconds=3.0, output_duration_seconds=60.0,
    )
    assert "fade=t=out:st=57.000:d=3.000" in filter_complex


def test_build_edit_filter_complex_fade_in_and_out_together_with_audio():
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, fade_in_seconds=1.0, fade_out_seconds=1.0,
        output_duration_seconds=10.0, keep_audio=True,
    )
    assert "[outv]fade=t=in:st=0:d=1.000,fade=t=out:st=9.000:d=1.000[outv2]" in filter_complex
    assert "afade=t=in:st=0:d=1.000" in filter_complex
    assert "afade=t=out:st=9.000:d=1.000" in filter_complex
    assert maps == ["-map", "[outv2]", "-map", "[outa]"]


def test_build_edit_filter_complex_no_fade_keeps_plain_outv_label():
    _filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30)
    assert maps == ["-map", "[outv]"]


# --- כיתוב טקסט קבוע (item) ---
#
# text_file_path (לא טקסט מוטמע ישירות בתוך מחרוזת ה-filter_complex) בכוונה -
# נבדק בפועל מול ffmpeg אמיתי: text= דרש שילוב לא-טריוויאלי של גם escaping
# וגם quoting יחד כדי ש-':' יעבוד, ואז ה-quote-breakout (ל-"'") והה-escape
# (ל-':') השחיתו בשקט תו ' באמצע טקסט עם שניהם יחד. textfile= עוקף את זה
# לגמרי - ראו utils/video/video_editor.py's build_drawtext_filter לפירוט המלא.

def test_build_edit_filter_complex_text_overlay_uses_drawtext():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, text_file_path="C:\\tmp\\text.txt")
    assert "drawtext=textfile='C\\:/tmp/text.txt':font=Arial:fontsize=24:fontcolor=#FFFFFF:expansion=none:x=(w-text_w)/2:y=h-text_h-20[outv2]" in filter_complex
    assert maps == ["-map", "[outv2]"]


def test_build_edit_filter_complex_text_position_top():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, text_file_path="text.txt", text_position="top")
    assert "y=20" in filter_complex


def test_build_edit_filter_complex_text_position_center():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, text_file_path="text.txt", text_position="center")
    assert "y=(h-text_h)/2" in filter_complex


def test_build_edit_filter_complex_text_disables_expansion():
    # item: drawtext מפרש %{...} כברירת מחדל - לא רלוונטי לטקסט סטטי, וגם
    # שובר '%' גולמי בטקסט המשתמש בלי הסיבה הזו - expansion=none מנוטרל תמיד.
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, text_file_path="text.txt")
    assert "expansion=none" in filter_complex


def test_build_edit_filter_complex_text_and_fade_together_text_applies_first():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, text_file_path="text.txt", fade_in_seconds=1.0,
    )
    drawtext_pos = filter_complex.index("drawtext=")
    fade_pos = filter_complex.index("fade=t=in")
    assert drawtext_pos < fade_pos


def test_build_edit_filter_complex_no_text_file_path_skips_drawtext():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30)
    assert "drawtext=" not in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_drawtext_filter_escapes_windows_path_colon():
    from utils.video.video_editor import build_drawtext_filter
    result = build_drawtext_filter("C:\\Users\\me\\text.txt", "bottom", "Arial", 24, "#FFFFFF")
    assert "textfile='C\\:/Users/me/text.txt'" in result
    assert "expansion=none" in result


# --- החלפת פס קול חלופי (item) ---

def test_build_edit_filter_complex_replace_audio_uses_given_input_index():
    _filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, replace_audio_input_index=2,
    )
    assert maps == ["-map", "[outv]", "-map", "2:a?"]


def test_build_edit_filter_complex_replace_audio_with_loudnorm_routes_through_filter_complex():
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, loudnorm=True, replace_audio_input_index=2,
    )
    assert "[2:a]loudnorm=I=-14:LRA=11:TP=-1.5:print_format=json,aresample=48000[outa]" in filter_complex
    assert maps == ["-map", "[outv]", "-map", "[outa]"]


def test_build_edit_filter_complex_no_replace_audio_defaults_to_input_zero():
    _filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True)
    assert maps == ["-map", "[outv]", "-map", "0:a?"]


# --- פענוח מואץ-GPU בלי NVENC (item: --hwaccel-decode) ---

def test_build_edit_filter_complex_hwaccel_decode_only_prepends_hwdownload():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, hwaccel_decode_only=True)
    assert filter_complex.startswith("[0:v]hwdownload,format=nv12,")


def test_build_edit_filter_complex_hwaccel_decode_only_uses_normal_cpu_scale_chain():
    # לא scale_cuda - הפריימים כבר ירדו ל-CPU לפני ה-scale, אז זהה לגמרי
    # לשרשרת ה-CPU הרגילה (use_hwaccel=False) מעבר ל-hwdownload הנוסף בהתחלה.
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, hwaccel_decode_only=True)
    assert HORIZONTAL_SCALE_CHAIN in filter_complex
    assert "scale_cuda" not in filter_complex


def test_build_edit_filter_complex_hwaccel_decode_only_before_stabilize_and_tonemap():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, hwaccel_decode_only=True,
        stabilize_transform_path="transforms.trf", tonemap_to_sdr=True,
    )
    hwdownload_pos = filter_complex.index("hwdownload")
    stabilize_pos = filter_complex.index("vidstabtransform")
    tonemap_pos = filter_complex.index(HDR_TONEMAP_FILTER)
    assert hwdownload_pos < stabilize_pos < tonemap_pos


def test_build_edit_filter_complex_no_hwaccel_decode_only_is_a_no_op():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30)
    assert "hwdownload" not in filter_complex


def test_build_edit_filter_complex_hwaccel_decode_only_still_allows_watermark():
    watermark = compute_watermark_geometry(1920, 1080, 300, 150, "bottom-right", scale_fraction=0.15, margin=20)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, hwaccel_decode_only=True, watermark_geometry=watermark,
    )
    assert "[base][wm]overlay=" in filter_complex
    assert "overlay_cuda" not in filter_complex
    assert maps == ["-map", "[outv]"]


# --- שער רעש (item) ---

def test_build_edit_filter_complex_noise_gate_adds_agate_before_loudnorm():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, noise_gate=True, loudnorm=True)
    assert f"[0:a]{NOISE_GATE_FILTER},{LOUDNORM_FILTER}{LOUDNORM_STATS},aresample=48000[outa]" in filter_complex


def test_build_edit_filter_complex_noise_gate_without_keep_audio_has_no_effect():
    filter_complex, maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, noise_gate=True)
    assert "agate" not in filter_complex
    assert maps == ["-map", "[outv]"]


# --- כרומה קי (item) ---

def test_build_chromakey_filters_returns_key_and_bg_filters():
    key_filter, bg_filter = build_chromakey_filters("0x00FF00", 0.2, 0.05, "0x000000", 1920, 1080)
    assert key_filter == "chromakey=color=0x00FF00:similarity=0.2:blend=0.05"
    assert bg_filter == "color=c=0x000000:s=1920x1080"


def test_build_edit_filter_complex_chromakey_builds_composite_graph():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, chromakey_color="0x00FF00", input_width=1920, input_height=1080,
    )
    assert "chromakey=color=0x00FF00:similarity=0.2:blend=0.05[__ck_fg]" in filter_complex
    assert "color=c=0x000000:s=1920x1080[__ck_bg]" in filter_complex
    assert f"[__ck_bg][__ck_fg]overlay=shortest=1,{HORIZONTAL_SCALE_CHAIN},fps=30[outv]" in filter_complex


def test_build_edit_filter_complex_chromakey_without_dimensions_falls_back_to_normal_path():
    # chromakey_color בלי input_width/input_height - אי אפשר לבנות רקע color=
    # בגודל נכון, אז נופל לנתיב הרגיל בלי chromakey בכלל (לא קורס).
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, chromakey_color="0x00FF00")
    assert "chromakey" not in filter_complex


def test_build_edit_filter_complex_chromakey_ignored_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, chromakey_color="0x00FF00", input_width=1920, input_height=1080, use_hwaccel=True,
    )
    assert "chromakey" not in filter_complex


def test_build_edit_filter_complex_chromakey_takes_priority_over_blur_background():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, chromakey_color="0x00FF00", input_width=1920, input_height=1080,
        blur_background=True, output_width=1920, output_height=1080,
    )
    assert "chromakey" in filter_complex
    assert "gblur" not in filter_complex


# --- ייצוב וידאו, two-pass (item) ---

def test_get_vidstabdetect_filter_basic():
    assert get_vidstabdetect_filter("/tmp/transforms.trf") == "vidstabdetect=shakiness=5:accuracy=15:result='/tmp/transforms.trf'"


def test_get_vidstabdetect_filter_escapes_windows_path():
    assert get_vidstabdetect_filter("C:\\tmp\\transforms.trf") == "vidstabdetect=shakiness=5:accuracy=15:result='C\\:/tmp/transforms.trf'"


def test_get_vidstabtransform_filter_basic():
    assert get_vidstabtransform_filter("/tmp/transforms.trf") == "vidstabtransform=input='/tmp/transforms.trf':zoom=0:smoothing=15"


def test_build_edit_filter_complex_stabilize_runs_first_before_tonemap():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, stabilize_transform_path="/tmp/transforms.trf", tonemap_to_sdr=True,
    )
    assert filter_complex.startswith("[0:v]vidstabtransform=input='/tmp/transforms.trf':zoom=0:smoothing=15,zscale=")


def test_build_edit_filter_complex_stabilize_ignored_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, stabilize_transform_path="/tmp/transforms.trf", use_hwaccel=True,
    )
    assert "vidstabtransform" not in filter_complex


def test_build_edit_filter_complex_no_custom_loudnorm_filter_uses_default():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, keep_audio=True, loudnorm=True)
    assert f"[0:a]{LOUDNORM_FILTER}{LOUDNORM_STATS},aresample=48000[outa]" in filter_complex


# --- skip redundant scale (item) ---

def test_build_edit_filter_complex_empty_scale_chain_skips_scale_step():
    filter_complex, _maps = build_edit_filter_complex("", 30)
    assert filter_complex == "[0:v]fps=30[outv]"


def test_build_edit_filter_complex_empty_scale_chain_with_denoise_and_watermark():
    geometry = (288, 288, 1612, 772)
    filter_complex, _maps = build_edit_filter_complex("", 30, watermark_geometry=geometry, denoise=True)
    assert filter_complex.startswith("[0:v]hqdn3d,fps=30[base]")


# --- blurred background instead of black bars (item) ---

def test_build_edit_filter_complex_blur_background_builds_split_overlay_subgraph():
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, blur_background=True, output_width=1920, output_height=1080,
    )
    assert "split=2[__bg_src][__fg_src]" in filter_complex
    assert "gblur=sigma=20" in filter_complex
    assert "[__bg][__fg]overlay=(W-w)/2:(H-h)/2,fps=30[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_blur_background_ignored_with_hwaccel():
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN_CUDA, 30, blur_background=True, use_hwaccel=True, output_width=1920, output_height=1080,
    )
    assert "split" not in filter_complex
    assert "gblur" not in filter_complex


def test_build_edit_filter_complex_blur_background_without_output_dimensions_falls_back():
    filter_complex, _maps = build_edit_filter_complex(HORIZONTAL_SCALE_CHAIN, 30, blur_background=True)
    assert "split" not in filter_complex
    assert filter_complex == f"[0:v]{HORIZONTAL_SCALE_CHAIN},fps=30[outv]"


def test_build_edit_filter_complex_blur_background_combined_with_watermark():
    geometry = (288, 288, 1612, 772)
    filter_complex, maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, watermark_geometry=geometry, blur_background=True,
        output_width=1920, output_height=1080,
    )
    assert "[__bg][__fg]overlay=(W-w)/2:(H-h)/2,fps=30[base]" in filter_complex
    assert "[base][wm]overlay=1612:772[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_blur_background_fits_vertical_output_without_cropping():
    # item: הכנסת סרטון אופקי לתוך מסגרת אנכית (טיקטוק) בלי לחתוך ממנו - הפונקציה
    # לא תלויה כלל בכיוון (רק ב-output_width/output_height), אז אותה תת-גרף
    # split+overlay עובד גם ליעד אנכי (1080x1920): הרקע ("increase"+crop) ממלא
    # את כל הפריים, החזית ("decrease", שומרת יחס, לא נחתכת) מוצגת עליו במרכז.
    filter_complex, maps = build_edit_filter_complex(
        VERTICAL_SCALE_CHAIN, 30, blur_background=True, output_width=1080, output_height=1920,
    )
    assert "[__bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=20[__bg]" in filter_complex
    assert "[__fg_src]scale=1080:1920:force_original_aspect_ratio=decrease[__fg]" in filter_complex
    assert "[__bg][__fg]overlay=(W-w)/2:(H-h)/2,fps=30[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_edit_filter_complex_blur_background_preserves_removal_region_before_split():
    region = (10, 20, 300, 100)
    filter_complex, _maps = build_edit_filter_complex(
        HORIZONTAL_SCALE_CHAIN, 30, removal_region=region, blur_background=True,
        output_width=1920, output_height=1080,
    )
    assert filter_complex.startswith("[0:v]delogo=x=10:y=20:w=300:h=100,split=2[__bg_src][__fg_src]")


def test_video_editor_presets_have_valid_values():
    # מקור אמת יחיד ל-GUI השולחני ולוובאפ - וידוא שכל preset מכיל בדיוק את
    # השדות הצפויים עם ערכים שבאמת קיימים (codec תקין, לא typo וכו').
    required_keys = {"vertical", "target_seconds", "keep_audio", "loudnorm", "codec"}
    assert len(VIDEO_EDITOR_PRESETS) >= 1
    for name, preset in VIDEO_EDITOR_PRESETS.items():
        assert set(preset.keys()) == required_keys, name
        assert isinstance(preset["vertical"], bool), name
        assert isinstance(preset["target_seconds"], int) and preset["target_seconds"] >= 0, name
        assert isinstance(preset["keep_audio"], bool), name
        assert isinstance(preset["loudnorm"], bool), name
        assert preset["codec"] in CODEC_ARGS, name


# --- compute_render_signature (item: smart re-encode skip) ---

def test_compute_render_signature_is_deterministic():
    sig1 = compute_render_signature("src1", {"codec": "h264", "vertical": True})
    sig2 = compute_render_signature("src1", {"codec": "h264", "vertical": True})
    assert sig1 == sig2


def test_compute_render_signature_ignores_params_key_order():
    sig1 = compute_render_signature("src1", {"a": 1, "b": 2})
    sig2 = compute_render_signature("src1", {"b": 2, "a": 1})
    assert sig1 == sig2


def test_compute_render_signature_changes_with_different_source():
    sig1 = compute_render_signature("src1", {"codec": "h264"})
    sig2 = compute_render_signature("src2", {"codec": "h264"})
    assert sig1 != sig2


def test_compute_render_signature_changes_with_different_params():
    sig1 = compute_render_signature("src1", {"codec": "h264"})
    sig2 = compute_render_signature("src1", {"codec": "hevc"})
    assert sig1 != sig2


def test_compute_render_signature_is_a_hex_string():
    sig = compute_render_signature("src1", {"codec": "h264"})
    assert isinstance(sig, str)
    assert len(sig) == 64  # sha256 hex digest
    int(sig, 16)  # לא אמור לזרוק - זה hex תקין


# --- compute_target_bitrate_kbps / get_two_pass_codec_args (item: two-pass VBR quality mode) ---

def test_compute_target_bitrate_kbps_basic():
    # 1MB ל-8 שניות בלי אודיו: 1*8192/8 = 1024 kbps
    assert compute_target_bitrate_kbps(1.0, 8.0, audio_kbps=0) == 1024


def test_compute_target_bitrate_kbps_subtracts_audio():
    without_audio = compute_target_bitrate_kbps(1.0, 8.0, audio_kbps=0)
    with_audio = compute_target_bitrate_kbps(1.0, 8.0, audio_kbps=128)
    assert with_audio == without_audio - 128


def test_compute_target_bitrate_kbps_has_a_safety_floor():
    # יעד קטן מדי לאורך ארוך מאוד - לא אמור לרדת ל-0/שלילי
    assert compute_target_bitrate_kbps(0.01, 3600.0) == 100


def test_compute_target_bitrate_kbps_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        compute_target_bitrate_kbps(0, 10.0)
    with pytest.raises(ValueError):
        compute_target_bitrate_kbps(1.0, 0)


def test_get_two_pass_codec_args_h264_uses_classic_two_pass():
    args = get_two_pass_codec_args("h264", 1000, 1, "/tmp/passlog")
    assert args == ["-c:v", "libx264", "-preset", "medium", "-b:v", "1000k", "-pass", "1", "-passlogfile", "/tmp/passlog"]


def test_get_two_pass_codec_args_h264_pass_two():
    args = get_two_pass_codec_args("h264", 1000, 2, "/tmp/passlog")
    assert "-pass" in args
    assert args[args.index("-pass") + 1] == "2"


def test_get_two_pass_codec_args_hevc_uses_nvenc_multipass():
    args = get_two_pass_codec_args("hevc", 2000, 2, "")
    assert args[:2] == ["-c:v", "hevc_nvenc"]
    assert "-rc" in args and args[args.index("-rc") + 1] == "vbr"
    assert "-b:v" in args and args[args.index("-b:v") + 1] == "2000k"
    assert "-multipass" in args and args[args.index("-multipass") + 1] == "fullres"
    assert "-pass" not in args  # NVENC לא תומך בקבצי pass-log כמו libx264


def test_get_two_pass_codec_args_av1_uses_nvenc_multipass():
    args = get_two_pass_codec_args("av1", 2000, 2, "")
    assert args[:2] == ["-c:v", "av1_nvenc"]
    assert "-multipass" in args


def test_get_two_pass_codec_args_maxrate_is_1_5x_bitrate():
    args = get_two_pass_codec_args("hevc", 2000, 2, "")
    assert args[args.index("-maxrate") + 1] == "3000k"


def test_get_two_pass_codec_args_preset_override():
    args = get_two_pass_codec_args("hevc", 2000, 2, "", preset="p1")
    assert args[args.index("-preset") + 1] == "p1"


def test_get_two_pass_codec_args_unknown_codec_raises():
    with pytest.raises(ValueError):
        get_two_pass_codec_args("mpeg2", 1000, 1, "")


def test_get_two_pass_codec_args_invalid_pass_num_raises():
    with pytest.raises(ValueError):
        get_two_pass_codec_args("h264", 1000, 3, "/tmp/passlog")


# --- מעברים בין כמה קטעים (item: concat עם קרוספייד/דיסולב) ---

def test_compute_xfade_offsets_two_clips():
    # מקור: [10s][8s], T=2s - merged=10; offset_1=10-2=8; merged=10+8-2=16.
    assert compute_xfade_offsets([10.0, 8.0], 2.0) == [8.0]


def test_compute_xfade_offsets_three_clips():
    # [10s][8s][6s], T=2s - offset_1=8 (כמו למעלה), merged=16;
    # offset_2=16-2=14, merged=16+6-2=20 (=24 שניות מקור - 2*2s חפיפה).
    assert compute_xfade_offsets([10.0, 8.0, 6.0], 2.0) == [8.0, 14.0]


def test_compute_xfade_offsets_four_equal_clips():
    # ארבעה קטעים של 5s, T=1s - כל merged גדל ב-4s (5-1) בכל שלב.
    offsets = compute_xfade_offsets([5.0, 5.0, 5.0, 5.0], 1.0)
    assert offsets == [4.0, 8.0, 12.0]


def test_compute_xfade_offsets_single_clip_returns_empty():
    assert compute_xfade_offsets([10.0], 1.0) == []


def test_compute_xfade_offsets_empty_list_returns_empty():
    assert compute_xfade_offsets([], 1.0) == []


def test_build_concat_transitions_filter_complex_requires_at_least_two_clips():
    with pytest.raises(ValueError):
        build_concat_transitions_filter_complex([10.0], HORIZONTAL_SCALE_CHAIN)


def test_build_concat_transitions_filter_complex_fade_two_clips_video_only():
    filter_complex, maps = build_concat_transitions_filter_complex(
        [10.0, 8.0], HORIZONTAL_SCALE_CHAIN, transition="fade", transition_duration=2.0,
    )
    assert f"[0:v]{HORIZONTAL_SCALE_CHAIN},setsar=1[s0]" in filter_complex
    assert f"[1:v]{HORIZONTAL_SCALE_CHAIN},setsar=1[s1]" in filter_complex
    assert "[s0][s1]xfade=transition=fade:duration=2.000:offset=8.000[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]
    assert "acrossfade" not in filter_complex


def test_build_concat_transitions_filter_complex_fade_three_clips_chains_correctly():
    filter_complex, maps = build_concat_transitions_filter_complex(
        [10.0, 8.0, 6.0], HORIZONTAL_SCALE_CHAIN, transition="fade", transition_duration=2.0,
    )
    assert "[s0][s1]xfade=transition=fade:duration=2.000:offset=8.000[vx1]" in filter_complex
    assert "[vx1][s2]xfade=transition=fade:duration=2.000:offset=14.000[outv]" in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_concat_transitions_filter_complex_fade_with_audio():
    filter_complex, maps = build_concat_transitions_filter_complex(
        [10.0, 8.0, 6.0], HORIZONTAL_SCALE_CHAIN, transition="fade", transition_duration=2.0, include_audio=True,
    )
    assert "[0:a][1:a]acrossfade=d=2.000[ax1]" in filter_complex
    assert "[ax1][2:a]acrossfade=d=2.000[outa]" in filter_complex
    assert maps == ["-map", "[outv]", "-map", "[outa]"]


def test_build_concat_transitions_filter_complex_fade_without_audio_has_no_amap():
    _filter_complex, maps = build_concat_transitions_filter_complex(
        [10.0, 8.0], HORIZONTAL_SCALE_CHAIN, transition="fade", transition_duration=2.0, include_audio=False,
    )
    assert maps == ["-map", "[outv]"]


def test_build_concat_transitions_filter_complex_none_uses_plain_concat():
    filter_complex, maps = build_concat_transitions_filter_complex(
        [10.0, 8.0, 6.0], HORIZONTAL_SCALE_CHAIN, transition="none",
    )
    assert "concat=n=3:v=1:a=0[outv]" in filter_complex
    assert "xfade" not in filter_complex
    assert maps == ["-map", "[outv]"]


def test_build_concat_transitions_filter_complex_none_with_audio_interleaves_streams():
    filter_complex, maps = build_concat_transitions_filter_complex(
        [10.0, 8.0], HORIZONTAL_SCALE_CHAIN, transition="none", include_audio=True,
    )
    assert "[s0][0:a][s1][1:a]concat=n=2:v=1:a=1[outv][outa]" in filter_complex
    assert "acrossfade" not in filter_complex
    assert maps == ["-map", "[outv]", "-map", "[outa]"]
