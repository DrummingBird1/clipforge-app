# tests/gui/test_settings_tab.py
#
# בודק את התוספת של גרירה-ושחרור (Drag&Drop) ועריכה ישירה לשדה התיקייה ב-
# SettingsTabComponent (היה קודם תווית קריאה-בלבד + כפתור "בחר תיקייה" בלבד).
import os


import pytest

from utils.shared.state import state
from ui.settings_tab import SettingsTabComponent
import ui.settings_tab as settings_tab_module


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    # drop_target_register() דורש TkinterDnD._require() על ה-root הספציפי
    # (LauncherApp.__init__ עושה את זה בפועל) - shared_tk_root של הטסטים הוא
    # ctk.CTk() רגיל בלי זה. אותו מסלול-קוד נתמך שכבר קיים כש-tkinterdnd2 לא
    # מותקן בכלל - ראו except ImportError ב-ui/settings_tab.py.
    monkeypatch.setattr(settings_tab_module, "_DND_AVAILABLE", False)


class _FakeDropEvent:
    def __init__(self, data):
        self.data = data


def test_typing_a_valid_folder_path_saves_it(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.folder_path_var.set(str(tmp_path))
        comp._on_folder_entry_changed()
        assert state.selected_gameplay_folder == os.path.normpath(str(tmp_path))
    finally:
        comp.destroy()


def test_typing_an_invalid_path_does_not_overwrite_saved_folder(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "selected_gameplay_folder", str(tmp_path))
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.folder_path_var.set(str(tmp_path / "still_typing"))
        comp._on_folder_entry_changed()
        assert state.selected_gameplay_folder == str(tmp_path)  # לא נדרס
    finally:
        comp.destroy()


def test_dropping_a_folder_sets_it_directly(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.on_folder_dropped(_FakeDropEvent(str(tmp_path)))
        assert state.selected_gameplay_folder == os.path.normpath(str(tmp_path))
        assert comp.folder_path_var.get() == os.path.normpath(str(tmp_path))
    finally:
        comp.destroy()


def test_dropping_a_video_file_uses_its_parent_folder(tmp_path, monkeypatch, shared_tk_root):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"x")
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.on_folder_dropped(_FakeDropEvent(str(video_file)))
        assert state.selected_gameplay_folder == os.path.normpath(str(tmp_path))
    finally:
        comp.destroy()


def test_dropped_path_with_tkinterdnd2_braces_is_parsed(tmp_path, monkeypatch, shared_tk_root):
    # tkinterdnd2 עוטף נתיבים עם רווחים ב-{ } - למשל "{C:/My Folder}"
    monkeypatch.setattr(state, "selected_gameplay_folder", "")
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.on_folder_dropped(_FakeDropEvent("{" + str(tmp_path) + "}"))
        assert state.selected_gameplay_folder == os.path.normpath(str(tmp_path))
    finally:
        comp.destroy()


def test_dropping_something_nonexistent_is_ignored(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "selected_gameplay_folder", "/original")
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.on_folder_dropped(_FakeDropEvent("C:/does/not/exist/at/all"))
        assert state.selected_gameplay_folder == "/original"
    finally:
        comp.destroy()


# --- watermark preview (item: watermark preview) ---

def _make_watermark_image(path, size=(64, 64), color=(255, 0, 0, 255)):
    from PIL import Image
    Image.new("RGBA", size, color).save(path)


def test_watermark_preview_empty_path_shows_no_image(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_path_var.set("")
        comp._update_watermark_preview()
        assert comp._wm_preview_ctk_image is None
    finally:
        comp.destroy()


def test_watermark_preview_valid_image_sets_ctk_image(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_watermark_position", "bottom-right")
    monkeypatch.setattr(state, "video_editor_vertical", False)
    wm_path = tmp_path / "logo.png"
    _make_watermark_image(wm_path)

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.vertical_var.set(False)
        comp._set_watermark_path(str(wm_path))
        assert comp._wm_preview_ctk_image is not None
    finally:
        comp.destroy()


def test_watermark_preview_invalid_image_file_shows_no_image(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    not_an_image = tmp_path / "not_an_image.png"
    not_an_image.write_bytes(b"this is not a real image file")

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp._set_watermark_path(str(not_an_image))
        assert comp._wm_preview_ctk_image is None
    finally:
        comp.destroy()


def test_watermark_preview_missing_file_shows_no_image(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp._set_watermark_path(str(tmp_path / "does_not_exist.png"))
        assert comp._wm_preview_ctk_image is None
    finally:
        comp.destroy()


def test_watermark_preview_box_resizes_for_vertical(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_watermark_position", "bottom-right")
    wm_path = tmp_path / "logo.png"
    _make_watermark_image(wm_path)

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.vertical_var.set(True)
        comp._set_watermark_path(str(wm_path))
        assert int(comp.wm_preview_box.cget("width")) == 120
        assert int(comp.wm_preview_box.cget("height")) == 213

        comp.vertical_var.set(False)
        comp._update_watermark_preview()
        assert int(comp.wm_preview_box.cget("width")) == 213
        assert int(comp.wm_preview_box.cget("height")) == 120
    finally:
        comp.destroy()


def test_watermark_preview_updates_on_position_change(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_watermark_position", "bottom-right")
    wm_path = tmp_path / "logo.png"
    _make_watermark_image(wm_path)

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.vertical_var.set(False)
        comp._set_watermark_path(str(wm_path))
        assert comp._wm_preview_ctk_image is not None

        # שינוי מיקום לא אמור לזרוק חריגה, ואמור להשאיר תצוגה תקינה
        comp._on_watermark_position_selected(comp._wm_position_value_to_display["top-left"])
        assert comp._wm_preview_ctk_image is not None
    finally:
        comp.destroy()


# --- 10 new video_editor.py options (item: video editor upgrades UI wiring) ---

def test_watermark_opacity_changed_clamps_to_0_1_range(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_opacity_var.set("1.5")
        comp._on_watermark_opacity_changed()
        assert state.video_editor_watermark_opacity == "1.0"

        comp.watermark_opacity_var.set("-0.5")
        comp._on_watermark_opacity_changed()
        assert state.video_editor_watermark_opacity == "0.0"
    finally:
        comp.destroy()


def test_watermark_opacity_changed_invalid_input_falls_back_to_opaque(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_opacity_var.set("not-a-number")
        comp._on_watermark_opacity_changed()
        assert state.video_editor_watermark_opacity == "1.0"
    finally:
        comp.destroy()


def test_watermark_opacity_valid_value_persisted(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_opacity_var.set("0.35")
        comp._on_watermark_opacity_changed()
        assert state.video_editor_watermark_opacity == "0.35"
    finally:
        comp.destroy()


def test_watermark_opacity_slider_clamps_and_persists(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp._on_watermark_opacity_slider_changed(0.35)
        assert state.video_editor_watermark_opacity == "0.35"

        comp._on_watermark_opacity_slider_changed(1.5)
        assert state.video_editor_watermark_opacity == "1.0"

        comp._on_watermark_opacity_slider_changed(-0.5)
        assert state.video_editor_watermark_opacity == "0.0"
    finally:
        comp.destroy()


def test_watermark_opacity_entry_and_slider_stay_in_sync(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_opacity_var.set("0.2")
        comp._on_watermark_opacity_changed()
        assert comp.watermark_opacity_slider_var.get() == 0.2

        comp._on_watermark_opacity_slider_changed(0.8)
        assert comp.watermark_opacity_var.get() == "0.8"
    finally:
        comp.destroy()


def test_watermark_preview_reflects_opacity_in_alpha_channel(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_watermark_position", "bottom-right")
    monkeypatch.setattr(state, "video_editor_vertical", False)
    monkeypatch.setattr(state, "video_editor_watermark_opacity", "0.5")
    wm_path = tmp_path / "logo.png"
    _make_watermark_image(wm_path)

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.vertical_var.set(False)
        comp.watermark_opacity_var.set("0.5")
        comp._set_watermark_path(str(wm_path))
        assert comp._wm_preview_ctk_image is not None
        # CTkImage שומר את התמונות המקוריות (לפני resize/CTk-internal scaling)
        # תחת ._light_image - בודקים שהאלפא הופחת בפועל, לא רק ש"לא קרס".
        pil_image = comp._wm_preview_ctk_image._light_image
        alpha_values = list(pil_image.split()[3].getdata())
        assert max(alpha_values) < 255, "האלפא אמור להיות מופחת עם opacity=0.5"
        assert max(alpha_values) > 0, "לא אמור להיות שקוף לגמרי"
    finally:
        comp.destroy()


def test_watermark_scale_entry_updates_state_and_slider(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_scale_var.set("30")
        comp._on_watermark_scale_changed()
        assert state.video_editor_watermark_scale == "0.3"
        assert comp.watermark_scale_slider_var.get() == 30
    finally:
        comp.destroy()


def test_watermark_scale_slider_updates_state_and_entry(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp._on_watermark_scale_slider_changed(40)
        assert state.video_editor_watermark_scale == "0.4"
        assert comp.watermark_scale_var.get() == "40"
    finally:
        comp.destroy()


def test_watermark_scale_clamped_to_valid_range(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.watermark_scale_var.set("999")
        comp._on_watermark_scale_changed()
        assert state.video_editor_watermark_scale == "0.5"

        comp.watermark_scale_var.set("-5")
        comp._on_watermark_scale_changed()
        assert state.video_editor_watermark_scale == "0.05"
    finally:
        comp.destroy()


def test_watermark_drag_updates_custom_center_fraction(tmp_path, monkeypatch, shared_tk_root):
    # item: גרירת watermark חופשית - מדמה ButtonPress+B1-Motion (בלי אירועי
    # Tk אמיתיים - בונים אובייקט event מינימלי עם x/y, אותו עיקרון שהודגם
    # ב-tests/gui/test_settings_tab.py's טסטים אחרים לאירועי Tk).
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_vertical", False)
    wm_path = tmp_path / "logo.png"
    _make_watermark_image(wm_path)

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.vertical_var.set(False)
        comp._set_watermark_path(str(wm_path))
        assert comp._wm_preview_ctk_image is not None
        comp.update_idletasks()

        class _FakeEvent:
            pass

        start_event = _FakeEvent()
        start_event.x, start_event.y = 5, 5
        comp._on_watermark_drag_start(start_event)

        motion_event = _FakeEvent()
        motion_event.x, motion_event.y = 5 + 50, 5 + 20
        comp._on_watermark_drag_motion(motion_event)

        assert state.video_editor_watermark_x != ""
        assert state.video_editor_watermark_y != ""
        assert 0.0 <= float(state.video_editor_watermark_x) <= 1.0
        assert 0.0 <= float(state.video_editor_watermark_y) <= 1.0

        comp._on_watermark_drag_end(motion_event)
        assert comp._wm_drag_start is None
    finally:
        comp.destroy()


def test_selecting_a_preset_position_clears_custom_drag_position(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        state.video_editor_watermark_x = "0.3"
        state.video_editor_watermark_y = "0.7"
        comp._on_watermark_position_selected(comp._wm_position_value_to_display["top-left"])
        assert state.video_editor_watermark_x == ""
        assert state.video_editor_watermark_y == ""
        assert state.video_editor_watermark_position == "top-left"
    finally:
        comp.destroy()


def test_clear_watermark_custom_position_resets_both_fields(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        state.video_editor_watermark_x = "0.3"
        state.video_editor_watermark_y = "0.7"
        comp._clear_watermark_custom_position()
        assert state.video_editor_watermark_x == ""
        assert state.video_editor_watermark_y == ""
    finally:
        comp.destroy()


def test_smart_crop_and_blur_background_toggles_persist(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.smart_crop_var.set(True)
        comp._on_smart_crop_toggled()
        assert state.video_editor_smart_crop is True

        comp.blur_background_var.set(True)
        comp._on_blur_background_toggled()
        assert state.video_editor_blur_background is True
    finally:
        comp.destroy()


def test_trim_start_changed_clamps_to_non_negative(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.trim_start_var.set("-3")
        comp._on_trim_start_changed()
        assert state.video_editor_trim_start == "0.0"

        comp.trim_start_var.set("5.5")
        comp._on_trim_start_changed()
        assert state.video_editor_trim_start == "5.5"
    finally:
        comp.destroy()


def test_trim_duration_changed_empty_clears_value(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.trim_duration_var.set("10")
        comp._on_trim_duration_changed()
        assert state.video_editor_trim_duration == "10.0"

        comp.trim_duration_var.set("")
        comp._on_trim_duration_changed()
        assert state.video_editor_trim_duration == ""
    finally:
        comp.destroy()


def test_trim_duration_changed_invalid_input_clears_value(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.trim_duration_var.set("garbage")
        comp._on_trim_duration_changed()
        assert state.video_editor_trim_duration == ""
    finally:
        comp.destroy()


def test_trim_silence_toggle_persists(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.trim_silence_var.set(True)
        comp._on_trim_silence_toggled()
        assert state.video_editor_trim_silence is True
    finally:
        comp.destroy()


def test_captions_toggle_persists(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.captions_var.set(True)
        comp._on_captions_toggled()
        assert state.video_editor_captions is True
    finally:
        comp.destroy()


def test_loudnorm_target_changed_valid_and_blank(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.loudnorm_target_var.set("-20")
        comp._on_loudnorm_target_changed()
        assert state.video_editor_loudnorm_target == "-20.0"

        comp.loudnorm_target_var.set("")
        comp._on_loudnorm_target_changed()
        assert state.video_editor_loudnorm_target == ""
    finally:
        comp.destroy()


def test_denoise_and_sharpen_toggles_persist_independently(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.denoise_var.set(True)
        comp._on_denoise_toggled()
        assert state.video_editor_denoise is True
        assert state.video_editor_sharpen is False

        comp.sharpen_var.set(True)
        comp._on_sharpen_toggled()
        assert state.video_editor_sharpen is True
    finally:
        comp.destroy()


def test_update_script_context_restores_all_new_fields_for_video_editor(monkeypatch, shared_tk_root):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "selected_script", "my_scripts/video/video_editor.py")
    monkeypatch.setattr(state, "video_editor_watermark_opacity", "0.42")
    monkeypatch.setattr(state, "video_editor_smart_crop", True)
    monkeypatch.setattr(state, "video_editor_blur_background", True)
    monkeypatch.setattr(state, "video_editor_trim_start", "3")
    monkeypatch.setattr(state, "video_editor_trim_duration", "7")
    monkeypatch.setattr(state, "video_editor_trim_silence", True)
    monkeypatch.setattr(state, "video_editor_captions", True)
    monkeypatch.setattr(state, "video_editor_loudnorm_target", "-16")
    monkeypatch.setattr(state, "video_editor_denoise", True)
    monkeypatch.setattr(state, "video_editor_sharpen", True)

    comp = SettingsTabComponent(shared_tk_root)
    try:
        comp.update_script_context("video_editor.py", "desc", "video_editor.py")
        assert comp.watermark_opacity_var.get() == "0.42"
        assert comp.watermark_opacity_slider_var.get() == 0.42
        assert comp.smart_crop_var.get() is True
        assert comp.blur_background_var.get() is True
        assert comp.trim_start_var.get() == "3"
        assert comp.trim_duration_var.get() == "7"
        assert comp.trim_silence_var.get() is True
        assert comp.captions_var.get() is True
        assert comp.loudnorm_target_var.get() == "-16"
        assert comp.denoise_var.get() is True
        assert comp.sharpen_var.get() is True
    finally:
        comp.destroy()
