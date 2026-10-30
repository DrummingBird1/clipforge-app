# tests/gui/test_settings_tab_favorites.py
#
# item: תיבת העדפות לכל פרופיל - קטגוריית "⭐ מועדפים" (settings_tab.py)
# מציגה 'מראה' (mirror widget) חדש לכל שדה שב-state.video_editor_favorite_fields
# (CSV), משותף על אותו Var/handler של השדה המקורי כדי ששני הצדדים יתעדכנו
# בו-זמנית. בודק גם את דיאלוג הבחירה (_open_favorites_dialog) ואת שני מסלולי
# ה-widget (Var-bound: entry/switch, ו-option-menu: codec/watermark_position וכו').


import customtkinter as ctk
import pytest

import ui.settings_tab as settings_tab_module
from ui.settings_tab import SettingsTabComponent
from utils.shared.state import state


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    monkeypatch.setattr(settings_tab_module, "_DND_AVAILABLE", False)


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_favorite_fields", "")


def _make_comp(shared_tk_root):
    return SettingsTabComponent(shared_tk_root)


def _find_checkboxes_by_text(widget):
    """אוסף רקורסיבית את כל ה-CTkCheckBox מתחת ל-widget, keyed לפי הטקסט שלהם -
    אין דרך אחרת "רשמית" לאתר checkbox ספציפי מתוך דיאלוג שנבנה דינמית."""
    found = {}
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkCheckBox):
            found[child.cget("text")] = child
        found.update(_find_checkboxes_by_text(child))
    return found


def test_empty_favorites_shows_placeholder_message(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        children = comp.cat_favorites.winfo_children()
        assert len(children) == 1
        assert "מועדפים" in children[0].cget("text") or "לחץ" in children[0].cget("text")
    finally:
        comp.destroy()


def test_starring_a_switch_field_creates_a_synced_mirror(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "vertical")
    comp = _make_comp(shared_tk_root)
    try:
        comp._rebuild_favorites_box()
        checkboxless_switches = [
            w for w in _collect_all(comp.cat_favorites) if isinstance(w, ctk.CTkSwitch)
        ]
        assert len(checkboxless_switches) == 1
        mirror_switch = checkboxless_switches[0]

        # ה-Switch המקורי (בקטגוריית "פורמט וקרופ") וה-mirror חולקים את אותו
        # Var - שינוי אחד מהם דרך ה-Var עצמו אמור להשתקף מיידית בשני המקומות,
        # בלי שום קוד סנכרון נוסף (זה כל הרעיון בשימוש ב-Var משותף).
        comp.vertical_var.set(True)
        assert mirror_switch.get() == 1
    finally:
        comp.destroy()


def test_starring_an_entry_field_creates_a_synced_mirror(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "trim_start")
    comp = _make_comp(shared_tk_root)
    try:
        comp._rebuild_favorites_box()
        entries = [w for w in _collect_all(comp.cat_favorites) if isinstance(w, ctk.CTkEntry)]
        assert len(entries) == 1
        mirror_entry = entries[0]

        comp.trim_start_var.set("12.5")
        assert mirror_entry.get() == "12.5"
    finally:
        comp.destroy()


def test_starring_an_option_menu_field_creates_a_mirror_and_stays_in_sync(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_codec", "h264")
    monkeypatch.setattr(state, "video_editor_favorite_fields", "codec")
    comp = _make_comp(shared_tk_root)
    try:
        comp._rebuild_favorites_box()
        assert "codec" in comp._favorite_mirrors
        mirror = comp._favorite_mirrors["codec"]
        hevc_display = comp._codec_value_to_display["hevc"]
        assert mirror.get() == comp._codec_value_to_display["h264"]

        # שינוי מהמקור (codec_menu, כאילו המשתמש בחר בקטגוריה המקורית) -
        # אמור לעדכן גם את ה-mirror.
        comp._on_codec_selected(hevc_display)
        assert state.video_editor_codec == "hevc"
        assert mirror.get() == hevc_display

        # שינוי מה-mirror עצמו (כאילו המשתמש בחר מתוך תיבת המועדפים) - אמור
        # לעדכן גם את ה-menu המקורי.
        h264_display = comp._codec_value_to_display["h264"]
        mirror.set(h264_display)
        comp._on_codec_selected(h264_display)  # command= של ה-mirror קורא לאותו handler
        assert state.video_editor_codec == "h264"
        assert comp.codec_menu.get() == h264_display
    finally:
        comp.destroy()


def test_unknown_favorite_field_is_skipped_silently(shared_tk_root, monkeypatch):
    # שדה ששמו שונה/הוסר מאז שנשמר כמועדף - לא אמור לזרוק, רק להתעלם ממנו.
    monkeypatch.setattr(state, "video_editor_favorite_fields", "not_a_real_field,vertical")
    comp = _make_comp(shared_tk_root)
    try:
        comp._rebuild_favorites_box()
        switches = [w for w in _collect_all(comp.cat_favorites) if isinstance(w, ctk.CTkSwitch)]
        assert len(switches) == 1
    finally:
        comp.destroy()


def test_favorites_dialog_lists_every_registered_field_and_precheck_current_ones(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "vertical")
    comp = _make_comp(shared_tk_root)
    try:
        registry = comp._favorite_field_registry()
        comp._open_favorites_dialog()
        toplevels = [w for w in comp.winfo_children() if isinstance(w, ctk.CTkToplevel)]
        assert len(toplevels) == 1
        checkboxes = _find_checkboxes_by_text(toplevels[0])
        assert len(checkboxes) == len(registry)

        vertical_label = registry["vertical"][0]
        assert checkboxes[vertical_label].get() == 1
        codec_label = registry["codec"][0]
        assert checkboxes[codec_label].get() == 0
        toplevels[0].destroy()
    finally:
        comp.destroy()


def test_favorites_dialog_apply_and_close_saves_selection_and_rebuilds(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "")
    comp = _make_comp(shared_tk_root)
    try:
        registry = comp._favorite_field_registry()
        comp._open_favorites_dialog()
        toplevels = [w for w in comp.winfo_children() if isinstance(w, ctk.CTkToplevel)]
        dialog = toplevels[0]
        checkboxes = _find_checkboxes_by_text(dialog)
        checkboxes[registry["codec"][0]].select()

        apply_btn = next(w for w in dialog.winfo_children() if isinstance(w, ctk.CTkButton))
        apply_btn.invoke()

        assert "codec" in state.video_editor_favorite_fields.split(",")
        assert "codec" in comp._favorite_mirrors
    finally:
        comp.destroy()


def test_apply_video_editor_profile_fields_restores_favorites_and_rebuilds(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "")
    comp = _make_comp(shared_tk_root)
    try:
        comp._apply_video_editor_profile_fields({"favorite_fields": "vertical,codec"})
        assert state.video_editor_favorite_fields == "vertical,codec"
        switches = [w for w in _collect_all(comp.cat_favorites) if isinstance(w, ctk.CTkSwitch)]
        assert len(switches) == 1
        assert "codec" in comp._favorite_mirrors
    finally:
        comp.destroy()


def test_apply_video_editor_profile_fields_defaults_to_no_favorites_for_old_profiles(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_favorite_fields", "vertical")
    comp = _make_comp(shared_tk_root)
    try:
        comp._apply_video_editor_profile_fields({})  # פרופיל ישן - אין key בכלל
        assert state.video_editor_favorite_fields == ""
    finally:
        comp.destroy()


def _collect_all(widget):
    result = [widget]
    for child in widget.winfo_children():
        result.extend(_collect_all(child))
    return result
