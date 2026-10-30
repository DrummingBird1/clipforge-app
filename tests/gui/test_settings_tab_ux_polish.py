# tests/gui/test_settings_tab_ux_polish.py
#
# עשרת פריטי העיצוב/UX לעורך-העל (item: שינויים לא-שמורים, אישור-מעבר, תקציר-
# קטגוריה, קידוד-צבע, פס פעולות צף, סידור מועדפים, איפוס-קטגוריה, מספרים
# חיים לגרירת watermark, מקראה, טור הכרות) + המונחים הקצרים/טולטיפים
# (FIELD_HELP) שמחליפים את תוויות-המשפט הישנות.
#
# הערה על _on_video_editor_preset_selected: קריאה ישירה אליו (כמו בכל שאר
# הטסטים של הקובץ, ראו test_settings_tab_video_editor_profiles.py) לא מעדכנת
# את preset_menu.get() בעצמה - ב-GUI אמיתי CTkOptionMenu קובע את הטקסט
# המוצג שלו *לפני* שהוא קורא ל-command, אבל קריאה ישירה מדלגת על זה. לכן
# preset_menu.set(...) נקרא כאן במפורש לפני כל קריאה כזו, בדיוק כמו ש-CTk
# עצמו היה עושה בלחיצה אמיתית.


import customtkinter as ctk
import pytest

import ui.settings_tab as settings_tab_module
from ui.settings_tab import SettingsTabComponent
from utils.video import video_editor_profiles as vep
from utils.shared.state import state
from utils.video.video_editor_field_help import FIELD_HELP


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    monkeypatch.setattr(settings_tab_module, "_DND_AVAILABLE", False)


@pytest.fixture(autouse=True)
def _suppress_dialogs(monkeypatch):
    monkeypatch.setattr(settings_tab_module.messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(settings_tab_module.messagebox, "askyesno", lambda *a, **k: True)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_favorite_fields", "")
    monkeypatch.setattr(state, "video_editor_onboarding_seen", False)
    monkeypatch.setattr(state, "video_editor_trim_start", "0")
    monkeypatch.setattr(state, "video_editor_codec", "h264")
    # קטגוריית "format" נבדקת בכמה טסטים לפי ספירת switch-ים פעילים - צריך
    # שכל אחד מהם יתחיל False במפורש, אחרת state (singleton גלובלי, לא
    # מאותחל-מחדש בין טסטים) עלול לדלוף ערך משאר. runsuite.
    monkeypatch.setattr(state, "video_editor_vertical", False)
    monkeypatch.setattr(state, "video_editor_smart_crop", False)
    monkeypatch.setattr(state, "video_editor_blur_background", False)
    monkeypatch.setattr(state, "video_editor_preserve_resolution", False)


def _make_comp(shared_tk_root):
    return SettingsTabComponent(shared_tk_root)


def _collect(widget):
    result = [widget]
    for child in widget.winfo_children():
        result.extend(_collect(child))
    return result


def _select_profile(comp, display_name):
    """מדמה בחירת פרופיל אמיתית מהתפריט - קובע את התצוגה לפני קריאת ה-handler,
    בדיוק כמו ש-CTkOptionMenu עצמו עושה בלחיצת משתמש אמיתית (ראו הערה למעלה)."""
    comp.preset_menu.set(display_name)
    comp._on_video_editor_preset_selected(display_name)


# --- מונחים קצרים במקום רצף-מילים ---

def test_trim_start_label_shows_short_term_not_old_sentence(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        cat_trim = comp._category_content_by_key["trim"]
        labels = [w.cget("text") for w in _collect(cat_trim) if isinstance(w, ctk.CTkLabel)]
        # t() הופך סדר-מילים בעברית טהורה (fix_hebrew_word_order, item ותיק) -
        # התווית בפועל עוברת דרך t(), אז ההשוואה חייבת גם היא.
        assert settings_tab_module.t(FIELD_HELP["trim_start"].term) in labels
        assert not any("ריק=עד הסוף" in text for text in labels)  # ההסבר המלא עבר לטולטיפ, לא בתווית
    finally:
        comp.destroy()


def test_switch_field_shows_short_term(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        cat_format = comp._category_content_by_key["format"]
        switches = {w.cget("text"): w for w in _collect(cat_format) if isinstance(w, ctk.CTkSwitch)}
        assert settings_tab_module.t(FIELD_HELP["blur_background"].term) in switches
        assert not any("פסים שחורים" in text for text in switches)
    finally:
        comp.destroy()


# --- מקראה ---

def test_glossary_dialog_lists_every_field_and_filters_by_search(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        dialog = comp._open_glossary_dialog()
        toplevels = [w for w in comp.winfo_children() if isinstance(w, ctk.CTkToplevel)]
        assert len(toplevels) == 1
        term_labels = {w.cget("text") for w in _collect(dialog) if isinstance(w, ctk.CTkLabel)}
        assert FIELD_HELP["watermark_scale"].term in term_labels

        dialog.search_var.set("watermark")
        dialog.rebuild()
        term_labels_filtered = {w.cget("text") for w in _collect(dialog) if isinstance(w, ctk.CTkLabel)}
        assert FIELD_HELP["watermark_scale"].term in term_labels_filtered
        assert FIELD_HELP["trim_start"].term not in term_labels_filtered
        dialog.destroy()
    finally:
        comp.destroy()


# --- קידוד-צבע לקטגוריה ---

def test_category_sections_get_a_distinct_border_color(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        watermark_section = comp._category_content_by_key["watermark"].master
        trim_section = comp._category_content_by_key["trim"].master
        assert watermark_section.cget("border_color") != trim_section.cget("border_color")
        assert int(watermark_section.cget("border_width")) > 0
    finally:
        comp.destroy()


# --- תקציר-מצב לקטגוריה ---

def test_category_summary_reflects_active_switches(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.vertical_var.set(True)
        comp._update_category_summaries()
        summary = comp._category_summary_vars["format"].get()
        assert "1" in summary and "מתגים" in summary
    finally:
        comp.destroy()


def test_category_summary_reports_no_special_settings_when_empty(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp._update_category_summaries()
        # t() הופך סדר-מילים בעברית (fix_hebrew_word_order, item ותיק - טקסט
        # מוצג נכון ב-Tkinter הרגיל שלא עושה bidi-shaping אמיתי) - ההשוואה
        # חייבת לעבור דרך אותו t() כמו הקוד עצמו, לא מול המחרוזת המקורית.
        assert comp._category_summary_vars["format"].get() == settings_tab_module.t("ללא הגדרות מיוחדות")
    finally:
        comp.destroy()


# --- שינויים לא-שמורים + אישור-מעבר ---

def test_unsaved_indicator_appears_after_editing_loaded_profile_and_clears_on_save(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        vep.save_profile("Test", comp._collect_video_editor_profile_settings())
        comp._refresh_video_editor_profile_menu()
        _select_profile(comp, f"{comp._custom_profile_display_prefix}Test")
        assert comp.unsaved_indicator_var.get() == ""

        comp.trim_start_var.set("5")
        comp._on_trim_start_changed()
        comp._update_unsaved_indicator()
        assert comp.unsaved_indicator_var.get() != ""

        comp._update_video_editor_profile()
        assert comp.unsaved_indicator_var.get() == ""
    finally:
        comp.destroy()


def test_switching_profile_with_unsaved_changes_prompts_and_reverts_on_cancel(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        vep.save_profile("A", {**comp._collect_video_editor_profile_settings(), "trim_start": "0"})
        vep.save_profile("B", {**comp._collect_video_editor_profile_settings(), "trim_start": "77"})
        comp._refresh_video_editor_profile_menu()
        _select_profile(comp, f"{comp._custom_profile_display_prefix}A")
        assert state.video_editor_trim_start == "0"
        comp.trim_start_var.set("9")
        comp._on_trim_start_changed()

        monkeypatch.setattr(settings_tab_module.messagebox, "askyesno", lambda *a, **k: False)
        _select_profile(comp, f"{comp._custom_profile_display_prefix}B")
        # בוטל - B לא הוחל בפועל, ההגדרה הלא-שמורה מ-A נשארת כמות שהייתה
        # ("9.0" - _on_trim_start_changed עצמו מנרמל קלט דרך float(), לא קשור לשינוי הזה).
        assert state.video_editor_trim_start == "9.0"
    finally:
        comp.destroy()


def test_switching_profile_with_unsaved_changes_proceeds_on_confirm(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        vep.save_profile("A", {**comp._collect_video_editor_profile_settings(), "trim_start": "0"})
        vep.save_profile("B", {**comp._collect_video_editor_profile_settings(), "trim_start": "77"})
        comp._refresh_video_editor_profile_menu()
        _select_profile(comp, f"{comp._custom_profile_display_prefix}A")
        comp.trim_start_var.set("9")
        comp._on_trim_start_changed()

        monkeypatch.setattr(settings_tab_module.messagebox, "askyesno", lambda *a, **k: True)
        _select_profile(comp, f"{comp._custom_profile_display_prefix}B")
        assert state.video_editor_trim_start == "77"
    finally:
        comp.destroy()


# --- איפוס לברירת מחדל ---

def test_reset_to_defaults_restores_default_values(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.vertical_var.set(True)
        comp._on_vertical_toggled()
        assert state.video_editor_vertical is True

        comp._reset_video_editor_to_defaults()
        assert state.video_editor_vertical is False
        assert comp.preset_menu.get() == comp._preset_placeholder
    finally:
        comp.destroy()


def test_reset_to_defaults_declines_without_confirmation(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        comp.vertical_var.set(True)
        comp._on_vertical_toggled()
        monkeypatch.setattr(settings_tab_module.messagebox, "askyesno", lambda *a, **k: False)
        comp._reset_video_editor_to_defaults()
        assert state.video_editor_vertical is True  # לא אופס - המשתמש ביטל
    finally:
        comp.destroy()


# --- סידור-ידני של המועדפים ---

def test_reorder_favorites_moves_field_up_and_down(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "vertical,codec,trim_start")
    comp = _make_comp(shared_tk_root)
    try:
        comp._move_favorite("trim_start", -1)
        assert state.video_editor_favorite_fields == "vertical,trim_start,codec"
        comp._move_favorite("vertical", -1)  # כבר ראשון - לא זז
        assert state.video_editor_favorite_fields == "vertical,trim_start,codec"
    finally:
        comp.destroy()


# --- מספרים חיים לגרירת watermark ---

def test_watermark_drag_coords_label_updates_during_motion(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp._wm_preview_ctk_image = object()  # מדמה שתמונה כבר נטענה - אחרת הגרירה מתעלמת מהאירוע
        comp.wm_preview_label.place(x=0, y=0)
        comp._wm_drag_start = (0, 0)

        class _FakeEvent:
            x, y = 20, 10

        comp._on_watermark_drag_motion(_FakeEvent())
        assert "%" in comp.wm_drag_coords_var.get()
    finally:
        comp.destroy()


def test_clear_custom_position_clears_coords_label(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_watermark_x", "0.5")
    monkeypatch.setattr(state, "video_editor_watermark_y", "0.5")
    comp = _make_comp(shared_tk_root)
    try:
        comp.wm_drag_coords_var.set("x=50%  y=50%")
        comp._clear_watermark_custom_position()
        assert comp.wm_drag_coords_var.get() == ""
    finally:
        comp.destroy()


# --- טור הכרות ראשוני ---

def test_onboarding_banner_shown_when_not_seen_and_dismiss_persists(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "selected_script", "my_scripts/video/video_editor.py")
    comp = _make_comp(shared_tk_root)
    try:
        comp.update_script_context("video_editor.py", "", "video_editor.py")
        assert comp.video_editor_onboarding_banner.winfo_manager() == "pack"

        comp._dismiss_video_editor_onboarding()
        assert state.video_editor_onboarding_seen is True
        assert comp.video_editor_onboarding_banner.winfo_manager() == ""
    finally:
        comp.destroy()


def test_onboarding_banner_hidden_when_already_seen(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "selected_script", "my_scripts/video/video_editor.py")
    monkeypatch.setattr(state, "video_editor_onboarding_seen", True)
    comp = _make_comp(shared_tk_root)
    try:
        comp.update_script_context("video_editor.py", "", "video_editor.py")
        assert comp.video_editor_onboarding_banner.winfo_manager() == ""
    finally:
        comp.destroy()


# --- פס פעולות צף ---

def test_sticky_bar_save_button_saves_profile(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("FromStickyBar")
        buttons = [w for w in comp.video_editor_sticky_bar.winfo_children() if isinstance(w, ctk.CTkButton)]
        save_btn = next(b for b in buttons if b.cget("command") == comp._save_video_editor_profile)
        save_btn.invoke()
        assert "FromStickyBar" in vep.load_profiles()
    finally:
        comp.destroy()
