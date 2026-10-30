# tests/gui/test_dashboard_build_extra_args.py
#
# בודק ישירות את DashboardTabComponent._build_extra_args("video_editor.py")
# עבור 10 האפשרויות החדשות (item: video editor upgrades UI wiring) - קריאה
# ישירה למתודה הטהורה (קוראת רק state.video_editor_*, בלי side effects),
# לא דרך run_task()+subprocess+Tk-pump מלא כמו test_dashboard_worker_integration.py's
# test_run_task_passes_remove_watermark_position_only_when_set - אותו מנגנון
# חיווט (extra_args -> worker -> subprocess argv) כבר מוכח שם לכמה דגלים;
# אין צורך להוכיח אותו מחדש בשביל כל אחד מ-10 הדגלים הנוספים.


from ui.dashboard import DashboardTabComponent
from utils.shared.state import state


def _make_comp(shared_tk_root):
    return DashboardTabComponent(shared_tk_root, lambda color, text: None)


def _reset_video_editor_state(monkeypatch):
    for attr, value in [
        ("video_editor_watermark_path", ""),
        ("video_editor_watermark_opacity", "1.0"),
        ("video_editor_watermark_scale", "0.15"),
        ("video_editor_watermark_x", ""),
        ("video_editor_watermark_y", ""),
        ("video_editor_remove_watermark_position", ""),
        ("video_editor_vertical", False),
        ("video_editor_smart_crop", False),
        ("video_editor_blur_background", False),
        ("video_editor_trim_start", "0"),
        ("video_editor_trim_duration", ""),
        ("video_editor_trim_silence", False),
        ("video_editor_target_seconds", "0"),
        ("video_editor_keep_audio", False),
        ("video_editor_captions", False),
        ("video_editor_captions_translate", False),
        ("video_editor_loudnorm", False),
        ("video_editor_loudnorm_target", ""),
        ("video_editor_denoise", False),
        ("video_editor_sharpen", False),
        ("video_editor_thumbnail", False),
        ("video_editor_codec", "h264"),
        ("video_editor_fps", ""),
        ("video_editor_lut_path", ""),
        ("video_editor_auto_levels", False),
        ("video_editor_noise_gate", False),
        ("video_editor_remove_mid_silence", False),
        ("video_editor_stabilize", False),
        ("video_editor_chromakey", False),
        ("video_editor_chromakey_color", "0x00FF00"),
        ("video_editor_chromakey_bg_color", "0x000000"),
        ("video_editor_caption_font", "Arial"),
        ("video_editor_caption_font_size", "16"),
        ("video_editor_caption_color", "#FFFFFF"),
        ("video_editor_caption_position", "bottom"),
        ("video_editor_preserve_resolution", False),
        ("video_editor_no_suffix", False),
        ("video_editor_number_videos", False),
        ("video_editor_number_prefix", "Clip"),
        ("video_editor_number_start", ""),
        ("video_editor_parallel", "1"),
        ("video_editor_max_concurrent_nvenc", ""),
        ("video_editor_effort", "high"),
        ("video_editor_container", "mp4"),
        ("video_editor_output_template", ""),
        ("video_editor_validate_only", False),
        ("video_editor_notify_per_file", False),
        ("video_editor_export_report", ""),
    ]:
        monkeypatch.setattr(state, attr, value)


def test_watermark_opacity_included_only_with_watermark_path_and_non_default(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
        monkeypatch.setattr(state, "video_editor_watermark_opacity", "0.5")
        args = comp._build_extra_args("video_editor.py")
        assert "--watermark_opacity" in args
        assert args[args.index("--watermark_opacity") + 1] == "0.5"
    finally:
        comp.destroy()


def test_watermark_opacity_omitted_when_full_opacity(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
        monkeypatch.setattr(state, "video_editor_watermark_opacity", "1.0")
        args = comp._build_extra_args("video_editor.py")
        assert "--watermark_opacity" not in args
    finally:
        comp.destroy()


def test_watermark_opacity_omitted_without_watermark_path(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_opacity", "0.3")
        args = comp._build_extra_args("video_editor.py")
        assert "--watermark_opacity" not in args
    finally:
        comp.destroy()


def test_watermark_scale_included_when_watermark_path_and_non_default_scale_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
        monkeypatch.setattr(state, "video_editor_watermark_scale", "0.3")
        args = comp._build_extra_args("video_editor.py")
        assert "--watermark_scale" in args
        assert args[args.index("--watermark_scale") + 1] == "0.3"
    finally:
        comp.destroy()


def test_watermark_custom_xy_included_only_when_both_are_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
        monkeypatch.setattr(state, "video_editor_watermark_x", "0.3")
        monkeypatch.setattr(state, "video_editor_watermark_y", "0.7")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--watermark_x") + 1] == "0.3"
        assert args[args.index("--watermark_y") + 1] == "0.7"
    finally:
        comp.destroy()


def test_watermark_custom_xy_omitted_when_only_x_is_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
        monkeypatch.setattr(state, "video_editor_watermark_x", "0.3")
        args = comp._build_extra_args("video_editor.py")
        assert "--watermark_x" not in args
        assert "--watermark_y" not in args
    finally:
        comp.destroy()


def test_smart_crop_included_only_with_vertical(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_vertical", True)
        monkeypatch.setattr(state, "video_editor_smart_crop", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--smart-crop" in args
    finally:
        comp.destroy()


def test_smart_crop_omitted_without_vertical(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_smart_crop", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--smart-crop" not in args
        assert "--vertical" not in args
    finally:
        comp.destroy()


def test_blur_background_included_without_vertical(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_blur_background", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--blur-background" in args
    finally:
        comp.destroy()


def test_blur_background_included_together_with_vertical(shared_tk_root, monkeypatch):
    # item: הכנסת סרטון אופקי לתוך מסגרת אנכית בלי לחתוך ממנו - שני הדגלים
    # ביחד (לא if/elif) הם בדיוק איך זה נשלח ל-CLI script עכשיו.
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_vertical", True)
        monkeypatch.setattr(state, "video_editor_blur_background", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--vertical" in args
        assert "--blur-background" in args
    finally:
        comp.destroy()


def test_trim_start_and_duration_included_when_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_trim_start", "5")
        monkeypatch.setattr(state, "video_editor_trim_duration", "10")
        args = comp._build_extra_args("video_editor.py")
        assert "--trim-start" in args
        assert args[args.index("--trim-start") + 1] == "5.0"
        assert "--trim-duration" in args
        assert args[args.index("--trim-duration") + 1] == "10.0"
    finally:
        comp.destroy()


def test_trim_start_omitted_when_zero(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--trim-start" not in args
        assert "--trim-duration" not in args
    finally:
        comp.destroy()


def test_trim_silence_included_when_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_trim_silence", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--trim-silence" in args
    finally:
        comp.destroy()


def test_captions_included_only_with_keep_audio(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        monkeypatch.setattr(state, "video_editor_captions", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--captions" in args
    finally:
        comp.destroy()


def test_captions_omitted_without_keep_audio(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_captions", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--captions" not in args
        assert "--keep-audio" not in args
    finally:
        comp.destroy()


def test_captions_translate_included_only_with_captions_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        monkeypatch.setattr(state, "video_editor_captions", True)
        monkeypatch.setattr(state, "video_editor_captions_translate", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--captions" in args
        assert "--captions-translate" in args
    finally:
        comp.destroy()


def test_captions_translate_omitted_without_captions_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        monkeypatch.setattr(state, "video_editor_captions_translate", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--captions-translate" not in args
    finally:
        comp.destroy()


def test_loudnorm_target_included_only_with_loudnorm(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_loudnorm", True)
        monkeypatch.setattr(state, "video_editor_loudnorm_target", "-20")
        args = comp._build_extra_args("video_editor.py")
        assert "--loudnorm-target" in args
        assert args[args.index("--loudnorm-target") + 1] == "-20.0"
    finally:
        comp.destroy()


def test_loudnorm_target_omitted_without_loudnorm(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_loudnorm_target", "-20")
        args = comp._build_extra_args("video_editor.py")
        assert "--loudnorm-target" not in args
        assert "--loudnorm" not in args
    finally:
        comp.destroy()


def test_loudnorm_target_omitted_when_blank(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_loudnorm", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--loudnorm" in args
        assert "--loudnorm-target" not in args
    finally:
        comp.destroy()


def test_denoise_and_sharpen_independent(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_denoise", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--denoise" in args
        assert "--sharpen" not in args
    finally:
        comp.destroy()


# --- שימור FPS מקורי (item: UI wiring) ---

def test_fps_included_when_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_fps", "30000/1001")
        args = comp._build_extra_args("video_editor.py")
        assert "--fps" in args
        assert args[args.index("--fps") + 1] == "30000/1001"
    finally:
        comp.destroy()


def test_fps_omitted_when_blank(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--fps" not in args
    finally:
        comp.destroy()


def test_fps_omitted_when_invalid(shared_tk_root, monkeypatch):
    # item: בדיקת באגים מקיפה - dashboard.py לא היה מוודא --fps בכלל (בניגוד
    # ל-web_app.py), אז ערך לא תקין היה מגיע ל-video_editor.py ומפיל את כל
    # הריצה עם exit() בהתחלה, במקום להתעלם בשקט כמו בווב.
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_fps", "not-a-valid-fps")
        args = comp._build_extra_args("video_editor.py")
        assert "--fps" not in args
    finally:
        comp.destroy()


def test_remove_watermark_position_omitted_when_invalid(shared_tk_root, monkeypatch):
    # item: בדיקת באגים מקיפה - אותו חוסר-עקביות מול web_app.py, שדה שונה.
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_remove_watermark_position", "middle-ish")
        args = comp._build_extra_args("video_editor.py")
        assert "--remove_watermark_position" not in args
    finally:
        comp.destroy()


def test_remove_watermark_position_included_when_valid(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_remove_watermark_position", "top-left")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--remove_watermark_position") + 1] == "top-left"
    finally:
        comp.destroy()


def test_caption_font_size_clamped_when_invalid(shared_tk_root, monkeypatch):
    # item: בדיקת באגים מקיפה - caption_font_size היה מועבר גולמי בלי int()/
    # clamp, בניגוד ל-web_app.py שכבר עושה max(1, int(...)) עם נפילה ל-16.
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        monkeypatch.setattr(state, "video_editor_captions", True)
        monkeypatch.setattr(state, "video_editor_caption_font_size", "not-a-number")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--caption-font-size") + 1] == "16"
    finally:
        comp.destroy()


def test_output_template_omitted_when_invalid(shared_tk_root, monkeypatch):
    # item: בדיקת באגים מקיפה - dashboard.py לא היה קורא ל-validate_output_template
    # בכלל, בניגוד ל-web_app.py - placeholder לא מוכר היה מגיע ל-video_editor.py
    # ומפיל את כל הריצה עם exit() בהתחלה, במקום להתעלם בשקט כמו בווב.
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_output_template", "{bogus}_{name}")
        args = comp._build_extra_args("video_editor.py")
        assert "--output-template" not in args
    finally:
        comp.destroy()


# --- "שדרוג ענקי" (item: UI wiring) ---

def test_lut_path_included_when_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_lut_path", "C:\\looks\\my.cube")
        args = comp._build_extra_args("video_editor.py")
        assert "--lut" in args
        assert args[args.index("--lut") + 1] == "C:\\looks\\my.cube"
    finally:
        comp.destroy()


def test_lut_path_omitted_when_blank(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--lut" not in args
    finally:
        comp.destroy()


def test_auto_levels_noise_gate_remove_mid_silence_stabilize_independent(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_auto_levels", True)
        monkeypatch.setattr(state, "video_editor_stabilize", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--auto-levels" in args
        assert "--stabilize" in args
        assert "--noise-gate" not in args
        assert "--remove-mid-silence" not in args
    finally:
        comp.destroy()


def test_chromakey_includes_colors_only_when_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_chromakey", True)
        monkeypatch.setattr(state, "video_editor_chromakey_color", "0xFF0000")
        monkeypatch.setattr(state, "video_editor_chromakey_bg_color", "0x0000FF")
        args = comp._build_extra_args("video_editor.py")
        assert "--chromakey" in args
        assert args[args.index("--chromakey-color") + 1] == "0xFF0000"
        assert args[args.index("--chromakey-bg-color") + 1] == "0x0000FF"
    finally:
        comp.destroy()


def test_chromakey_omitted_when_disabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--chromakey" not in args
        assert "--chromakey-color" not in args
    finally:
        comp.destroy()


def test_caption_style_included_only_with_captions_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        monkeypatch.setattr(state, "video_editor_captions", True)
        monkeypatch.setattr(state, "video_editor_caption_font", "Rubik")
        monkeypatch.setattr(state, "video_editor_caption_position", "top")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--caption-font") + 1] == "Rubik"
        assert args[args.index("--caption-position") + 1] == "top"
    finally:
        comp.destroy()


def test_caption_style_omitted_without_captions_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--caption-font" not in args
        assert "--caption-position" not in args
    finally:
        comp.destroy()


def test_all_ten_new_options_together(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
        monkeypatch.setattr(state, "video_editor_watermark_opacity", "0.5")
        monkeypatch.setattr(state, "video_editor_vertical", True)
        monkeypatch.setattr(state, "video_editor_smart_crop", True)
        monkeypatch.setattr(state, "video_editor_trim_start", "5")
        monkeypatch.setattr(state, "video_editor_trim_duration", "10")
        monkeypatch.setattr(state, "video_editor_trim_silence", True)
        monkeypatch.setattr(state, "video_editor_keep_audio", True)
        monkeypatch.setattr(state, "video_editor_captions", True)
        monkeypatch.setattr(state, "video_editor_loudnorm", True)
        monkeypatch.setattr(state, "video_editor_loudnorm_target", "-20")
        monkeypatch.setattr(state, "video_editor_denoise", True)
        monkeypatch.setattr(state, "video_editor_sharpen", True)

        args = comp._build_extra_args("video_editor.py")

        for flag in (
            "--watermark_opacity", "--vertical", "--smart-crop", "--trim-start", "--trim-duration",
            "--trim-silence", "--keep-audio", "--captions", "--loudnorm", "--loudnorm-target",
            "--denoise", "--sharpen",
        ):
            assert flag in args, f"{flag} חסר מ-{args}"
    finally:
        comp.destroy()


def test_preserve_resolution_and_no_suffix_included_only_when_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--preserve-resolution" not in args
        assert "--no-suffix" not in args

        monkeypatch.setattr(state, "video_editor_preserve_resolution", True)
        monkeypatch.setattr(state, "video_editor_no_suffix", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--preserve-resolution" in args
        assert "--no-suffix" in args
    finally:
        comp.destroy()


def test_number_videos_included_with_prefix_and_start(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--number-videos" not in args

        monkeypatch.setattr(state, "video_editor_number_videos", True)
        monkeypatch.setattr(state, "video_editor_number_prefix", "Clip")
        monkeypatch.setattr(state, "video_editor_number_start", "42")
        args = comp._build_extra_args("video_editor.py")
        assert "--number-videos" in args
        assert args[args.index("--number-prefix") + 1] == "Clip"
        assert args[args.index("--number-start") + 1] == "42"
    finally:
        comp.destroy()


def test_number_prefix_and_start_omitted_when_number_videos_disabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_number_prefix", "Clip")
        monkeypatch.setattr(state, "video_editor_number_start", "42")
        args = comp._build_extra_args("video_editor.py")
        assert "--number-videos" not in args
        assert "--number-prefix" not in args
        assert "--number-start" not in args
    finally:
        comp.destroy()


def test_number_start_blank_is_omitted(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_number_videos", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--number-videos" in args
        assert "--number-prefix" in args  # ברירת מחדל "Clip" - לא ריק, כן מועבר
        assert "--number-start" not in args
    finally:
        comp.destroy()


def test_max_concurrent_nvenc_included_only_with_parallel_above_one(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_max_concurrent_nvenc", "2")
        args = comp._build_extra_args("video_editor.py")
        assert "--max-concurrent-nvenc" not in args  # parallel=1 - לא רלוונטי

        monkeypatch.setattr(state, "video_editor_parallel", "4")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--max-concurrent-nvenc") + 1] == "2"
    finally:
        comp.destroy()


def test_max_concurrent_nvenc_blank_is_omitted(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_parallel", "4")
        args = comp._build_extra_args("video_editor.py")
        assert "--max-concurrent-nvenc" not in args
    finally:
        comp.destroy()


def test_parallel_included_only_when_above_one(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--parallel" not in args

        monkeypatch.setattr(state, "video_editor_parallel", "4")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--parallel") + 1] == "4"
    finally:
        comp.destroy()


def test_effort_included_only_when_not_high(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--effort" not in args

        monkeypatch.setattr(state, "video_editor_effort", "low")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--effort") + 1] == "low"
    finally:
        comp.destroy()


def test_effort_auto_is_included(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        monkeypatch.setattr(state, "video_editor_effort", "auto")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--effort") + 1] == "auto"
    finally:
        comp.destroy()


def test_container_included_only_when_not_mp4(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--container" not in args

        monkeypatch.setattr(state, "video_editor_container", "mkv")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--container") + 1] == "mkv"
    finally:
        comp.destroy()


def test_output_template_included_only_when_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--output-template" not in args

        monkeypatch.setattr(state, "video_editor_output_template", "{date}_{name}")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--output-template") + 1] == "{date}_{name}"
    finally:
        comp.destroy()


def test_validate_only_and_notify_per_file_included_only_when_enabled(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--validate-only" not in args
        assert "--notify-per-file" not in args

        monkeypatch.setattr(state, "video_editor_validate_only", True)
        monkeypatch.setattr(state, "video_editor_notify_per_file", True)
        args = comp._build_extra_args("video_editor.py")
        assert "--validate-only" in args
        assert "--notify-per-file" in args
    finally:
        comp.destroy()


def test_export_report_included_only_when_set(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        _reset_video_editor_state(monkeypatch)
        args = comp._build_extra_args("video_editor.py")
        assert "--export-report" not in args

        monkeypatch.setattr(state, "video_editor_export_report", "xlsx")
        args = comp._build_extra_args("video_editor.py")
        assert args[args.index("--export-report") + 1] == "xlsx"
    finally:
        comp.destroy()
