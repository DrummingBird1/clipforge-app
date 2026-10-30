# tests/studio/test_video_editor_profiles.py


import pytest

from utils.video import video_editor_profiles as vep


@pytest.fixture(autouse=True)
def _isolate_profiles_path(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))


def test_load_profiles_returns_empty_dict_when_file_missing():
    assert vep.load_profiles() == {}


def test_save_profile_then_load_roundtrips():
    settings = {"watermark_path": "C:\\logo.png", "vertical": True, "codec": "hevc"}
    vep.save_profile("Rocket League", settings)
    profiles = vep.load_profiles()
    assert profiles["Rocket League"]["watermark_path"] == "C:\\logo.png"
    assert profiles["Rocket League"]["vertical"] is True
    assert profiles["Rocket League"]["codec"] == "hevc"


def test_save_profile_persists_captions_fields():
    # item: בדיקת באגים מקיפה - captions/captions_translate היו חסרים מ-
    # PROFILE_FIELDS ונדרסו בשקט לכיבוי בכל טעינת פרופיל, למרות שכל שאר שדות
    # הכתוביות (font/size/color/position) נשמרו תקין.
    vep.save_profile("WithCaptions", {"captions": True, "captions_translate": True, "codec": "h264"})
    saved = vep.load_profiles()["WithCaptions"]
    assert saved["captions"] is True
    assert saved["captions_translate"] is True


def test_save_profile_persists_watermark_scale_and_custom_position():
    vep.save_profile("CustomWatermark", {"watermark_scale": 0.25, "watermark_x": 0.3, "watermark_y": 0.7, "codec": "h264"})
    saved = vep.load_profiles()["CustomWatermark"]
    assert saved["watermark_scale"] == 0.25
    assert saved["watermark_x"] == 0.3
    assert saved["watermark_y"] == 0.7


def test_save_profile_persists_favorite_fields():
    vep.save_profile("WithFavorites", {"favorite_fields": "vertical,codec", "codec": "h264"})
    saved = vep.load_profiles()["WithFavorites"]
    assert saved["favorite_fields"] == "vertical,codec"


def test_save_profile_only_keeps_known_fields():
    vep.save_profile("Minecraft", {"vertical": True, "some_unexpected_field": "danger"})
    saved = vep.load_profiles()["Minecraft"]
    assert "some_unexpected_field" not in saved
    assert set(saved.keys()) == set(vep.PROFILE_FIELDS)


def test_save_profile_fills_missing_fields_with_none():
    vep.save_profile("Sparse", {"vertical": True})
    saved = vep.load_profiles()["Sparse"]
    assert saved["watermark_path"] is None
    assert saved["codec"] is None


def test_save_profile_overwrites_existing_name():
    vep.save_profile("Same Name", {"codec": "h264"})
    vep.save_profile("Same Name", {"codec": "av1"})
    profiles = vep.load_profiles()
    assert len(profiles) == 1
    assert profiles["Same Name"]["codec"] == "av1"


def test_save_profile_rejects_empty_name():
    with pytest.raises(ValueError):
        vep.save_profile("   ", {"codec": "h264"})


def test_save_profile_strips_whitespace_from_name():
    vep.save_profile("  Spaced  ", {"codec": "h264"})
    assert "Spaced" in vep.load_profiles()
    assert "  Spaced  " not in vep.load_profiles()


def test_delete_profile_removes_existing_profile():
    vep.save_profile("ToDelete", {"codec": "h264"})
    assert vep.delete_profile("ToDelete") is True
    assert "ToDelete" not in vep.load_profiles()


def test_delete_profile_returns_false_when_not_found():
    assert vep.delete_profile("NeverExisted") is False


def test_load_profiles_returns_empty_dict_on_corrupt_json():
    with open(vep.PROFILES_PATH, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    assert vep.load_profiles() == {}


def test_multiple_profiles_coexist():
    vep.save_profile("A", {"codec": "h264"})
    vep.save_profile("B", {"codec": "hevc"})
    profiles = vep.load_profiles()
    assert set(profiles.keys()) == {"A", "B"}


# --- תיקיית קלט בפרופיל (item) ---

def test_save_profile_persists_folder_field():
    vep.save_profile("WithFolder", {"codec": "h264", "folder": "D:\\Gameplay\\RocketLeague"})
    assert vep.load_profiles()["WithFolder"]["folder"] == "D:\\Gameplay\\RocketLeague"


def test_save_profile_folder_missing_defaults_to_none():
    vep.save_profile("NoFolder", {"codec": "h264"})
    assert vep.load_profiles()["NoFolder"]["folder"] is None


# --- שינוי שם לפרופיל (item: rename_profile) ---

def test_rename_profile_moves_settings_to_new_name():
    vep.save_profile("OldName", {"codec": "hevc", "vertical": True})
    renamed = vep.rename_profile("OldName", "NewName")
    profiles = vep.load_profiles()
    assert "OldName" not in profiles
    assert "NewName" in profiles
    assert profiles["NewName"]["codec"] == "hevc"
    assert profiles["NewName"]["vertical"] is True
    assert renamed == profiles["NewName"]


def test_rename_profile_strips_whitespace_from_new_name():
    vep.save_profile("Original", {"codec": "h264"})
    vep.rename_profile("Original", "  Trimmed  ")
    profiles = vep.load_profiles()
    assert "Trimmed" in profiles
    assert "  Trimmed  " not in profiles


def test_rename_profile_raises_when_old_name_missing():
    with pytest.raises(ValueError):
        vep.rename_profile("NeverExisted", "Whatever")


def test_rename_profile_raises_when_new_name_already_taken_by_another_profile():
    vep.save_profile("First", {"codec": "h264"})
    vep.save_profile("Second", {"codec": "av1"})
    with pytest.raises(ValueError):
        vep.rename_profile("First", "Second")
    # שני הפרופילים המקוריים נשארים בלי שינוי - הרנמ' לא ביצע שום דבר בכשל.
    profiles = vep.load_profiles()
    assert profiles["First"]["codec"] == "h264"
    assert profiles["Second"]["codec"] == "av1"


def test_rename_profile_raises_when_new_name_blank():
    vep.save_profile("Original", {"codec": "h264"})
    with pytest.raises(ValueError):
        vep.rename_profile("Original", "   ")


def test_rename_profile_to_same_name_is_a_no_op_not_an_error():
    vep.save_profile("SameName", {"codec": "h264"})
    result = vep.rename_profile("SameName", "SameName")
    assert result["codec"] == "h264"
    assert list(vep.load_profiles().keys()) == ["SameName"]


# --- גרסת-סכימה + חותמת "בשימוש לאחרונה" (item) ---

def test_save_profile_stamps_schema_version():
    vep.save_profile("Versioned", {"codec": "h264"})
    assert vep.load_profile_meta("Versioned")["schema_version"] == vep.PROFILE_SCHEMA_VERSION


def test_load_profile_meta_defaults_for_never_saved_profile():
    meta = vep.load_profile_meta("NeverSaved")
    # גל 6: המטא-דאטה כוללת גם תגיות/צבע/הערות/ברירת-מחדל/ירושה - כולם בברירות מחדל ריקות
    assert meta == {"schema_version": None, "last_used_at": None, "run_count": 0, "tags": [], "color": "", "notes": "",
                    "is_default": False, "parent": None, "overridden_fields": [], "created_at": None, "kind": "style"}


def test_record_profile_used_increments_run_count_and_sets_timestamp():
    vep.save_profile("Used", {"codec": "h264"})
    assert vep.load_profile_meta("Used")["run_count"] == 0
    vep.record_profile_used("Used")
    vep.record_profile_used("Used")
    meta = vep.load_profile_meta("Used")
    assert meta["run_count"] == 2
    assert meta["last_used_at"] is not None


def test_record_profile_used_is_a_no_op_for_missing_profile():
    vep.record_profile_used("DoesNotExist")  # לא אמור לזרוק
    assert vep.load_profile_meta("DoesNotExist")["run_count"] == 0


# --- שכפול פרופיל / "שמור בשם..." (item) ---

def test_duplicate_profile_copies_settings_under_new_name():
    vep.save_profile("Original", {"codec": "hevc", "vertical": True})
    copied = vep.duplicate_profile("Original", "Copy")
    assert copied["codec"] == "hevc"
    assert copied["vertical"] is True
    profiles = vep.load_profiles()
    assert "Original" in profiles and "Copy" in profiles


def test_duplicate_profile_does_not_touch_source():
    vep.save_profile("Original", {"codec": "hevc"})
    vep.duplicate_profile("Original", "Copy")
    assert vep.load_profiles()["Original"]["codec"] == "hevc"


def test_duplicate_profile_starts_with_fresh_usage_stats():
    vep.save_profile("Original", {"codec": "hevc"})
    vep.record_profile_used("Original")
    vep.duplicate_profile("Original", "Copy")
    assert vep.load_profile_meta("Copy")["run_count"] == 0
    assert vep.load_profile_meta("Copy")["last_used_at"] is None


def test_duplicate_profile_raises_when_source_missing():
    with pytest.raises(ValueError):
        vep.duplicate_profile("NeverExisted", "Copy")


def test_duplicate_profile_raises_when_new_name_taken():
    vep.save_profile("A", {"codec": "h264"})
    vep.save_profile("B", {"codec": "hevc"})
    with pytest.raises(ValueError):
        vep.duplicate_profile("A", "B")


# --- ייצוא/ייבוא פרופיל בודד כ-JSON (item) ---

def test_export_profile_returns_only_profile_fields():
    vep.save_profile("ToExport", {"codec": "hevc", "vertical": True})
    exported = vep.export_profile("ToExport")
    assert set(exported.keys()) == set(vep.PROFILE_FIELDS)
    assert exported["codec"] == "hevc"


def test_export_profile_raises_when_missing():
    with pytest.raises(ValueError):
        vep.export_profile("NeverExisted")


def test_import_profile_creates_new_profile():
    imported = vep.import_profile("Imported", {"codec": "av1", "vertical": True})
    assert imported["codec"] == "av1"
    assert "Imported" in vep.load_profiles()


def test_import_profile_rejects_existing_name_without_overwrite():
    vep.save_profile("Existing", {"codec": "h264"})
    with pytest.raises(ValueError):
        vep.import_profile("Existing", {"codec": "av1"})
    assert vep.load_profiles()["Existing"]["codec"] == "h264"


def test_import_profile_overwrites_when_explicitly_allowed():
    vep.save_profile("Existing", {"codec": "h264"})
    vep.import_profile("Existing", {"codec": "av1"}, overwrite=True)
    assert vep.load_profiles()["Existing"]["codec"] == "av1"


def test_export_then_import_roundtrips():
    vep.save_profile("Source", {"codec": "hevc", "watermark_scale": 0.2})
    exported = vep.export_profile("Source")
    vep.import_profile("Dest", exported)
    assert vep.load_profiles()["Dest"]["codec"] == "hevc"
    assert vep.load_profiles()["Dest"]["watermark_scale"] == 0.2


# --- השוואת שני פרופילים (item: diff) ---

def test_diff_profiles_returns_only_differing_fields():
    vep.save_profile("A", {"codec": "h264", "vertical": True, "denoise": False})
    vep.save_profile("B", {"codec": "hevc", "vertical": True, "denoise": True})
    diff = vep.diff_profiles("A", "B")
    assert diff == {"codec": ["h264", "hevc"], "denoise": [False, True]}


def test_diff_profiles_empty_when_identical():
    vep.save_profile("A", {"codec": "h264"})
    vep.save_profile("B", {"codec": "h264"})
    assert vep.diff_profiles("A", "B") == {}


def test_diff_profiles_raises_when_either_missing():
    vep.save_profile("A", {"codec": "h264"})
    with pytest.raises(ValueError):
        vep.diff_profiles("A", "NeverExisted")
    with pytest.raises(ValueError):
        vep.diff_profiles("NeverExisted", "A")


# --- היסטוריית-שינויים/undo לפרופיל (item) ---

def test_get_profile_history_empty_for_never_overwritten_profile():
    vep.save_profile("Fresh", {"codec": "h264"})
    assert vep.get_profile_history("Fresh") == []


def test_save_profile_overwrite_pushes_previous_state_to_history():
    vep.save_profile("Evolving", {"codec": "h264"})
    vep.save_profile("Evolving", {"codec": "hevc"})
    history = vep.get_profile_history("Evolving")
    assert len(history) == 1
    assert history[0]["codec"] == "h264"
    assert "saved_at" in history[0]


def test_profile_history_caps_at_max_entries():
    vep.save_profile("Busy", {"codec": "h264"})
    for i in range(vep.MAX_HISTORY_PER_PROFILE + 3):
        vep.save_profile("Busy", {"codec": f"codec-{i}"})
    history = vep.get_profile_history("Busy")
    assert len(history) == vep.MAX_HISTORY_PER_PROFILE
    # השמורים הם האחרונים שנדחפו - הישן ביותר בהיסטוריה הוא לא הראשון-אי-פעם.
    assert history[0]["codec"] != "h264"


def test_revert_profile_restores_previous_settings():
    vep.save_profile("Reverting", {"codec": "h264", "vertical": False})
    vep.save_profile("Reverting", {"codec": "hevc", "vertical": True})
    reverted = vep.revert_profile("Reverting", -1)
    assert reverted["codec"] == "h264"
    assert reverted["vertical"] is False
    assert vep.load_profiles()["Reverting"]["codec"] == "h264"


def test_revert_profile_pushes_current_state_to_history_first_so_revert_is_undoable():
    vep.save_profile("Undoable", {"codec": "h264"})
    vep.save_profile("Undoable", {"codec": "hevc"})
    vep.revert_profile("Undoable", -1)
    history = vep.get_profile_history("Undoable")
    # אחרי revert(-1): ההיסטוריה כוללת עכשיו גם את המצב שהיה *לפני* ה-revert (hevc).
    assert any(entry["codec"] == "hevc" for entry in history)
    # revert חוזר (undo ה-undo) אמור להחזיר בחזרה ל-hevc.
    reverted_again = vep.revert_profile("Undoable", -1)
    assert reverted_again["codec"] == "hevc"


def test_revert_profile_raises_for_out_of_range_index():
    vep.save_profile("NoHistory", {"codec": "h264"})
    with pytest.raises(ValueError):
        vep.revert_profile("NoHistory", -1)


def test_revert_profile_raises_when_profile_missing():
    with pytest.raises(ValueError):
        vep.revert_profile("NeverExisted", -1)


# --- ניקוי היסטוריה/מטא-דאטה במחיקה/שינוי-שם (item) ---

def test_delete_profile_cleans_up_history_and_meta():
    vep.save_profile("Doomed", {"codec": "h264"})
    vep.save_profile("Doomed", {"codec": "hevc"})
    vep.record_profile_used("Doomed")
    vep.delete_profile("Doomed")
    assert vep.get_profile_history("Doomed") == []
    assert vep.load_profile_meta("Doomed") == vep.load_profile_meta("NeverSaved")  # מטא-דאטה נוקתה (עברה לסל המחזור)


def test_rename_profile_carries_history_and_meta_to_new_name():
    vep.save_profile("Before", {"codec": "h264"})
    vep.save_profile("Before", {"codec": "hevc"})
    vep.record_profile_used("Before")
    vep.rename_profile("Before", "After")
    assert vep.get_profile_history("Before") == []
    assert vep.get_profile_history("After") != []
    assert vep.load_profile_meta("After")["run_count"] == 1
