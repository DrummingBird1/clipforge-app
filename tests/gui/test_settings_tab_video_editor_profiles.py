# tests/gui/test_settings_tab_video_editor_profiles.py
#
# פרופיל אישי (item) ב-SettingsTabComponent - snapshot מלא של טופס video_editor.py
# (כולל watermark_path/opacity, לא רק "סוג עריכה" כללי כמו VIDEO_EDITOR_PRESETS
# הקבועים) שהמשתמש שומר/טוען/מוחק בעצמו. אותה utils/video/video_editor_profiles.py
# בדיוק כמו web_app.py's /api/video_editor_profiles - מקור אמת יחיד.


import pytest

import ui.settings_tab as settings_tab_module
from ui.settings_tab import SettingsTabComponent
from utils.video import video_editor_profiles as vep
from utils.shared.state import state

_STATE_DEFAULTS = [
    ("video_editor_watermark_path", ""),
    ("video_editor_watermark_position", "bottom-right"),
    ("video_editor_watermark_opacity", "1.0"),
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
]


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    # ראו tests/gui/test_settings_tab.py - drop_target_register() דורש TkinterDnD
    # מאותחל על ה-root הספציפי, לא זמין על shared_tk_root של הטסטים.
    monkeypatch.setattr(settings_tab_module, "_DND_AVAILABLE", False)


@pytest.fixture(autouse=True)
def _suppress_confirmation_dialogs(monkeypatch):
    # item: הודעת אישור שמירת/עדכון פרופיל - messagebox.showinfo האמיתי פותח
    # דיאלוג מודאלי שחוסם וממתין ללחיצת משתמש; בלי המוק הזה, כל טסט שקורא
    # ל-_save_video_editor_profile()/_update_video_editor_profile() היה נתקע
    # (timeout) בסביבת טסטים אוטומטית בלי משתמש שילחץ OK.
    monkeypatch.setattr(settings_tab_module.messagebox, "showinfo", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _isolate_profiles_path(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    monkeypatch.setattr(state, "save_config", lambda: None)
    for attr, value in _STATE_DEFAULTS:
        monkeypatch.setattr(state, attr, value)


def _make_comp(shared_tk_root):
    return SettingsTabComponent(shared_tk_root)


class _FakeInputDialog:
    """מדמה ctk.CTkInputDialog (item: שינוי שם לפרופיל) - הדיאלוג האמיתי חוסם
    בלולאת אירועים משלו וממתין לקלט אנושי, לא מתאים לטסט אוטומטי. next_value
    (class attribute, לא instance) נקבע ע"י כל טסט בנפרד לפני הקריאה
    ל-_rename_video_editor_profile - None מדמה ביטול הדיאלוג (X/Cancel)."""
    next_value = None

    def __init__(self, text=None, title=None):
        pass

    def get_input(self):
        return _FakeInputDialog.next_value


def test_saving_profile_persists_full_settings_snapshot(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "video_editor_watermark_path", "C:\\logo.png")
    monkeypatch.setattr(state, "video_editor_vertical", True)
    monkeypatch.setattr(state, "video_editor_codec", "hevc")
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("Rocket League")
        comp._save_video_editor_profile()

        saved = vep.load_profiles()["Rocket League"]
        assert saved["watermark_path"] == "C:\\logo.png"
        assert saved["vertical"] is True
        assert saved["codec"] == "hevc"
    finally:
        comp.destroy()


def test_saving_profile_selects_it_and_shows_delete_button(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("MyProfile")
        comp._save_video_editor_profile()

        assert comp.preset_menu.get() == "👤 MyProfile"
        assert comp.delete_profile_btn.winfo_manager() == "pack"
        assert comp.update_profile_btn.winfo_manager() == "pack"
        assert comp.profile_name_var.get() == ""  # השדה מתאפס אחרי שמירה מוצלחת
    finally:
        comp.destroy()


# --- item: אפשרות לעדכן פרופיל קיים ---

def test_updating_selected_profile_overwrites_it_with_current_settings(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("ToUpdate")
        comp._save_video_editor_profile()
        assert vep.load_profiles()["ToUpdate"]["codec"] == "h264"

        monkeypatch.setattr(state, "video_editor_codec", "av1")
        monkeypatch.setattr(state, "video_editor_vertical", True)
        comp._update_video_editor_profile()

        updated = vep.load_profiles()["ToUpdate"]
        assert updated["codec"] == "av1"
        assert updated["vertical"] is True
        # לא נוצר פרופיל חדש - אותו שם בדיוק נדרס.
        assert list(vep.load_profiles().keys()) == ["ToUpdate"]
        # הבחירה בתפריט נשארת על אותו פרופיל.
        assert comp.preset_menu.get() == "👤 ToUpdate"
    finally:
        comp.destroy()


def test_update_button_does_nothing_when_no_profile_selected(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.preset_menu.set(comp._preset_placeholder)
        comp._update_video_editor_profile()  # לא אמור לזרוק/ליצור פרופיל - שום פרופיל לא נבחר
        assert vep.load_profiles() == {}
    finally:
        comp.destroy()


def test_update_button_does_nothing_when_builtin_preset_selected(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("Existing")
        comp._save_video_editor_profile()
        # מדמה בחירה אמיתית של preset קבוע מהתפריט - CTkOptionMenu האמיתי
        # מעדכן את הערך הנבחר-בעצמו לפני/יחד עם קריאת ה-command, בניגוד לקריאה
        # ישירה ל-_on_video_editor_preset_selected בלבד (שלא נוגעת ב-preset_menu עצמו).
        comp.preset_menu.set("📱 טיקטוק/שורטס מהיר")
        comp._on_video_editor_preset_selected("📱 טיקטוק/שורטס מהיר")

        comp._update_video_editor_profile()  # preset קבוע נבחר כרגע, לא פרופיל אישי - no-op

        assert vep.load_profiles()["Existing"]["vertical"] is False  # לא נדרס בטעות
    finally:
        comp.destroy()


def test_saving_profile_with_blank_name_does_nothing(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("   ")
        comp._save_video_editor_profile()
        assert vep.load_profiles() == {}
    finally:
        comp.destroy()


def test_selecting_saved_profile_applies_all_fields(shared_tk_root):
    vep.save_profile("Full Profile", {
        "watermark_path": "C:\\wm.png", "watermark_position": "top-left", "watermark_opacity": 0.5,
        "vertical": True, "smart_crop": False, "blur_background": True,
        "trim_start": 2.5, "trim_duration": 8, "trim_silence": True,
        "target_seconds": 45, "keep_audio": True, "loudnorm": True, "loudnorm_target": -18,
        "denoise": True, "sharpen": True, "thumbnail": True, "codec": "av1",
    })
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp._on_video_editor_preset_selected("👤 Full Profile")

        assert state.video_editor_watermark_path == "C:\\wm.png"
        assert state.video_editor_vertical is True
        assert state.video_editor_blur_background is True
        assert state.video_editor_trim_start == "2.5"
        assert state.video_editor_target_seconds == "45"
        assert state.video_editor_codec == "av1"
        assert comp.watermark_path_var.get() == "C:\\wm.png"
        assert comp.vertical_var.get() is True
        assert comp.codec_menu.get() == comp._codec_value_to_display["av1"]
        assert comp.delete_profile_btn.winfo_manager() == "pack"
        assert comp.update_profile_btn.winfo_manager() == "pack"
    finally:
        comp.destroy()


def test_selecting_profile_with_missing_fields_falls_back_to_defaults(shared_tk_root):
    vep.save_profile("Sparse", {"vertical": True})
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp._on_video_editor_preset_selected("👤 Sparse")

        assert state.video_editor_watermark_path == ""
        assert state.video_editor_codec == "h264"
        assert state.video_editor_trim_start == "0"
    finally:
        comp.destroy()


def test_selecting_builtin_preset_still_works_alongside_profiles(shared_tk_root):
    vep.save_profile("SomeProfile", {"vertical": True})
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp._on_video_editor_preset_selected("📱 טיקטוק/שורטס מהיר")

        assert state.video_editor_vertical is True
        assert state.video_editor_codec == "hevc"
        assert comp.delete_profile_btn.winfo_manager() == ""
        assert comp.update_profile_btn.winfo_manager() == ""
    finally:
        comp.destroy()


def test_deleting_selected_profile_removes_it_and_resets_menu(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("ToDelete")
        comp._save_video_editor_profile()
        assert "ToDelete" in vep.load_profiles()

        comp._delete_video_editor_profile()

        assert "ToDelete" not in vep.load_profiles()
        assert comp.preset_menu.get() == comp._preset_placeholder
        assert comp.delete_profile_btn.winfo_manager() == ""
        assert comp.update_profile_btn.winfo_manager() == ""
    finally:
        comp.destroy()


def test_delete_button_does_nothing_when_no_profile_selected(shared_tk_root):
    comp = _make_comp(shared_tk_root)
    try:
        comp.preset_menu.set(comp._preset_placeholder)
        comp._delete_video_editor_profile()  # לא אמור לזרוק - שום פרופיל לא נבחר
    finally:
        comp.destroy()


def test_refresh_picks_up_profile_saved_externally(shared_tk_root):
    # מדמה פרופיל שנשמר מתהליך אחר (למשל הווב) - אותו קובץ data/video_editor_profiles.json
    # בדיוק, נקרא מחדש בכל כניסה לפאנל (update_script_context), לא רק באתחול.
    comp = _make_comp(shared_tk_root)
    try:
        assert "👤 FromWeb" not in comp.preset_menu.cget("values")
        vep.save_profile("FromWeb", {"codec": "h264"})
        comp._refresh_video_editor_profile_menu()
        assert "👤 FromWeb" in comp.preset_menu.cget("values")
    finally:
        comp.destroy()


# --- תיקיית קלט בפרופיל (item) ---

def test_saving_profile_persists_current_folder(shared_tk_root, monkeypatch):
    monkeypatch.setattr(state, "selected_gameplay_folder", "D:\\Gameplay\\RocketLeague")
    comp = _make_comp(shared_tk_root)
    try:
        comp.profile_name_var.set("WithFolder")
        comp._save_video_editor_profile()
        assert vep.load_profiles()["WithFolder"]["folder"] == "D:\\Gameplay\\RocketLeague"
    finally:
        comp.destroy()


def test_selecting_profile_restores_its_folder(shared_tk_root, monkeypatch):
    vep.save_profile("HasFolder", {"codec": "h264", "folder": "D:\\Clips\\Minecraft"})
    monkeypatch.setattr(state, "selected_gameplay_folder", "C:\\SomethingElse")
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp._on_video_editor_preset_selected("👤 HasFolder")
        assert state.selected_gameplay_folder == "D:\\Clips\\Minecraft"
        assert comp.folder_path_var.get() == "D:\\Clips\\Minecraft"
    finally:
        comp.destroy()


def test_selecting_profile_without_folder_field_does_not_clobber_current_folder(shared_tk_root, monkeypatch):
    # פרופיל "ישן" שנשמר לפני התכונה הזו - אין לו מפתח "folder" בכלל (None).
    vep.save_profile("NoFolderKey", {"codec": "h264"})
    monkeypatch.setattr(state, "selected_gameplay_folder", "C:\\KeepMe")
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp._on_video_editor_preset_selected("👤 NoFolderKey")
        assert state.selected_gameplay_folder == "C:\\KeepMe"
    finally:
        comp.destroy()


# --- שינוי שם לפרופיל (item) ---

def test_renaming_selected_profile_updates_menu_and_keeps_settings(shared_tk_root, monkeypatch):
    monkeypatch.setattr(settings_tab_module.ctk, "CTkInputDialog", _FakeInputDialog)
    _FakeInputDialog.next_value = "RenamedProfile"
    vep.save_profile("OriginalProfile", {"codec": "hevc", "vertical": True})
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        # comp.preset_menu.set(...) בנוסף לקריאת ה-callback הישירה - CTkOptionMenu
        # אמיתי מעדכן את הערך הנבחר-בעצמו לפני שקורא ל-command, בניגוד לקריאה
        # ישירה ל-_on_video_editor_preset_selected בלבד (ראו test_settings_tab_video_editor_profiles.py's
        # test_update_button_does_nothing_when_builtin_preset_selected).
        comp.preset_menu.set("👤 OriginalProfile")
        comp._on_video_editor_preset_selected("👤 OriginalProfile")
        comp._rename_video_editor_profile()

        profiles = vep.load_profiles()
        assert "OriginalProfile" not in profiles
        assert profiles["RenamedProfile"]["codec"] == "hevc"
        assert comp.preset_menu.get() == "👤 RenamedProfile"
    finally:
        comp.destroy()


def test_rename_does_nothing_when_dialog_cancelled(shared_tk_root, monkeypatch):
    monkeypatch.setattr(settings_tab_module.ctk, "CTkInputDialog", _FakeInputDialog)
    _FakeInputDialog.next_value = None  # ביטול הדיאלוג
    vep.save_profile("StaysTheSame", {"codec": "h264"})
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp.preset_menu.set("👤 StaysTheSame")
        comp._on_video_editor_preset_selected("👤 StaysTheSame")
        comp._rename_video_editor_profile()
        assert "StaysTheSame" in vep.load_profiles()
    finally:
        comp.destroy()


def test_rename_does_nothing_when_no_profile_selected(shared_tk_root, monkeypatch):
    monkeypatch.setattr(settings_tab_module.ctk, "CTkInputDialog", _FakeInputDialog)
    _FakeInputDialog.next_value = "ShouldNotBeUsed"
    comp = _make_comp(shared_tk_root)
    try:
        comp.preset_menu.set(comp._preset_placeholder)
        comp._rename_video_editor_profile()  # לא אמור לזרוק - שום פרופיל לא נבחר
    finally:
        comp.destroy()


def test_rename_to_existing_other_profile_name_is_rejected(shared_tk_root, monkeypatch):
    monkeypatch.setattr(settings_tab_module.ctk, "CTkInputDialog", _FakeInputDialog)
    _FakeInputDialog.next_value = "AlreadyTaken"
    shown_errors = []
    monkeypatch.setattr(settings_tab_module.messagebox, "showerror", lambda title, msg: shown_errors.append(msg))
    vep.save_profile("ToRename", {"codec": "h264"})
    vep.save_profile("AlreadyTaken", {"codec": "av1"})
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp.preset_menu.set("👤 ToRename")
        comp._on_video_editor_preset_selected("👤 ToRename")
        comp._rename_video_editor_profile()  # לא זורק - נדחה עם דיאלוג שגיאה גלוי (item: בדיקת באגים מקיפה)

        profiles = vep.load_profiles()
        assert profiles["ToRename"]["codec"] == "h264"
        assert profiles["AlreadyTaken"]["codec"] == "av1"
        assert len(shown_errors) == 1
        assert "AlreadyTaken" in shown_errors[0]
    finally:
        comp.destroy()


def test_rename_button_shows_and_hides_alongside_update_and_delete(shared_tk_root):
    vep.save_profile("Toggle", {"codec": "h264"})
    comp = _make_comp(shared_tk_root)
    try:
        comp._refresh_video_editor_profile_menu()
        comp._on_video_editor_preset_selected("👤 Toggle")
        assert comp.rename_profile_btn.winfo_manager() == "pack"

        comp._on_video_editor_preset_selected("📱 טיקטוק/שורטס מהיר")
        assert comp.rename_profile_btn.winfo_manager() == ""
    finally:
        comp.destroy()
