# tests/infra/test_state_config.py
#
# load_config() היה עושה d.get(key, default) בלי לבדוק טיפוס בכלל - config.json
# פגום (למשל ערך מספרי במקום bool) היה זולג בשקט לתוך state ורק מתגלה (או לא)
# עמוק בתוך קוד ה-GUI. עכשיו כל שדה עובר דרך CONFIG_SCHEMA (utils/shared/state.py)
# עם בדיקת טיפוס מפורשת וחזרה לברירת מחדל + הודעה ברורה כשהוא לא תקין.
import json


import pytest

from utils.shared.state import (
    DARK_PALETTE,
    DEFAULT_UI_SETTINGS,
    HIGH_CONTRAST_PALETTE,
    LIGHT_PALETTE,
    THEME_MODES,
    THEMES,
    _load_saved_theme_mode,
    state,
)


@pytest.fixture(autouse=True)
def _restore_state():
    # state הוא singleton משותף לכל קובצי הטסטים - load_config()/reset_to_defaults()
    # (בניגוד ל-monkeypatch.setattr) משנים אותו לצמיתות, אז כל טסט כאן משחזר את
    # המצב המקורי אחריו כדי לא לדלוף לטסטים אחרים בתהליך. THEMES["Custom"] הוא
    # dict גלובלי (לא ב-state.__dict__) שגם מוחלף על ידי set_custom_accent()/
    # load_config() - צריך לשחזר גם אותו בנפרד.
    snapshot = dict(state.__dict__)
    custom_theme_snapshot = dict(THEMES["Custom"])
    yield
    state.__dict__.clear()
    state.__dict__.update(snapshot)
    THEMES["Custom"] = custom_theme_snapshot


def _write_config(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_wrong_type_field_falls_back_to_default(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"turbo_active": "yes"})  # str, not bool
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.turbo_mode_active is False  # default, not the malformed "yes"
    assert "turbo_active" in capsys.readouterr().out


def test_valid_config_loads_normally(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"turbo_active": True, "language": "en", "theme": "Pink"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.turbo_mode_active is True
    assert state.language == "en"
    assert state.current_theme_name == "Pink"


def test_unknown_theme_mode_falls_back_to_dark(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"theme_mode": "purple"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.theme_mode == "dark"
    assert "theme_mode" in capsys.readouterr().out


def test_high_contrast_theme_mode_loads_via_load_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"theme_mode": "high_contrast"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.theme_mode == "high_contrast"


def test_load_saved_theme_mode_accepts_high_contrast(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"theme_mode": "high_contrast"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    assert _load_saved_theme_mode() == "high_contrast"


def test_load_saved_theme_mode_rejects_unknown_value(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"theme_mode": "purple"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    assert _load_saved_theme_mode() == "dark"


def test_theme_modes_matches_palette_dicts():
    assert set(THEME_MODES) == {"dark", "light", "high_contrast"}


def test_high_contrast_palette_has_same_keys_as_dark_and_light():
    assert set(HIGH_CONTRAST_PALETTE.keys()) == set(DARK_PALETTE.keys())
    assert set(HIGH_CONTRAST_PALETTE.keys()) == set(LIGHT_PALETTE.keys())


def test_malformed_ui_settings_falls_back_to_defaults(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"ui_settings": "not a dict"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.ui_settings == DEFAULT_UI_SETTINGS


def test_reset_to_defaults_restores_every_schema_field(monkeypatch):
    monkeypatch.setattr(state, "turbo_mode_active", True)
    monkeypatch.setattr(state, "language", "en")
    monkeypatch.setattr(state, "ui_settings", {"rings": False})

    state.reset_to_defaults()

    assert state.turbo_mode_active is False
    assert state.language == "he"
    assert state.ui_settings == DEFAULT_UI_SETTINGS


def test_set_custom_accent_updates_theme_and_selects_it():
    state.set_custom_accent("#123456")

    assert state.custom_accent_hex == "#123456"
    assert state.current_theme_name == "Custom"
    assert THEMES["Custom"]["accent"] == "#123456"
    # hover/led_dim צריכים להיות גרסאות מוכהות, לא זהות ל-accent עצמו
    assert THEMES["Custom"]["accent_hover"] != THEMES["Custom"]["accent"]
    assert THEMES["Custom"]["led_dim"] != THEMES["Custom"]["accent"]


def test_derive_theme_from_accent_falls_back_on_invalid_hex():
    from utils.shared.state import derive_theme_from_accent
    theme = derive_theme_from_accent("not-a-color")
    assert theme["accent"].startswith("#")
    assert len(theme["accent"]) == 7


def test_custom_accent_survives_config_reload(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"custom_accent_hex": "#abcdef", "theme": "Custom"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.custom_accent_hex == "#abcdef"
    assert THEMES["Custom"]["accent"] == "#abcdef"
    assert state.current_theme["accent"] == "#abcdef"


def test_story_cutter_ai_provider_loads_valid_value(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"story_cutter_ai_provider": "local"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.story_cutter_ai_provider == "local"


def test_unknown_story_cutter_ai_provider_falls_back_to_gemini(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"story_cutter_ai_provider": "chatgpt"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.story_cutter_ai_provider == "gemini"
    assert "story_cutter_ai_provider" in capsys.readouterr().out


def test_toggle_favorite_script_adds_and_removes(monkeypatch):
    monkeypatch.setattr(state, "favorite_scripts_csv", "")
    monkeypatch.setattr(state, "save_config", lambda: None)

    state.toggle_favorite_script("story_cutter.py")
    assert state.get_favorite_scripts() == {"story_cutter.py"}

    state.toggle_favorite_script("disk_scanner.py")
    assert state.get_favorite_scripts() == {"story_cutter.py", "disk_scanner.py"}

    state.toggle_favorite_script("story_cutter.py")
    assert state.get_favorite_scripts() == {"disk_scanner.py"}


def test_get_favorite_scripts_handles_empty_csv(monkeypatch):
    monkeypatch.setattr(state, "favorite_scripts_csv", "")
    assert state.get_favorite_scripts() == set()


# --- get_dashboard_widget_order (item: reorderable dashboard widgets) ---

def test_get_dashboard_widget_order_default():
    assert state.get_dashboard_widget_order() == ["cpu", "ram", "gpu", "uptime", "docker"]


def test_get_dashboard_widget_order_reflects_saved_custom_order(monkeypatch):
    monkeypatch.setattr(state, "dashboard_widget_order_csv", "gpu,cpu,ram,docker,uptime")
    assert state.get_dashboard_widget_order() == ["gpu", "cpu", "ram", "docker", "uptime"]


def test_get_dashboard_widget_order_falls_back_when_a_widget_is_missing(monkeypatch):
    # CSV חלקי (למשל נערך ידנית, או config.json מגרסה ישנה לפני שהשדה נוסף)
    monkeypatch.setattr(state, "dashboard_widget_order_csv", "cpu,ram")
    assert state.get_dashboard_widget_order() == ["cpu", "ram", "gpu", "uptime", "docker"]


def test_get_dashboard_widget_order_falls_back_when_csv_has_unknown_id(monkeypatch):
    monkeypatch.setattr(state, "dashboard_widget_order_csv", "cpu,ram,gpu,uptime,not_a_real_widget")
    assert state.get_dashboard_widget_order() == ["cpu", "ram", "gpu", "uptime", "docker"]


def test_get_dashboard_widget_order_falls_back_when_csv_is_empty(monkeypatch):
    monkeypatch.setattr(state, "dashboard_widget_order_csv", "")
    assert state.get_dashboard_widget_order() == ["cpu", "ram", "gpu", "uptime", "docker"]


def test_dashboard_widget_order_survives_config_reload(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))
    monkeypatch.setattr(state, "dashboard_widget_order_csv", "docker,uptime,gpu,ram,cpu")

    state.save_config()
    monkeypatch.setattr(state, "dashboard_widget_order_csv", "cpu,ram,gpu,uptime,docker")  # simulate a fresh process
    state.load_config()

    assert state.get_dashboard_widget_order() == ["docker", "uptime", "gpu", "ram", "cpu"]


def test_timelapse_keep_audio_defaults_to_true():
    # רגרסיה: timelapse_maker.py עצמו כבוי כברירת מחדל ב---keep-audio (ה-CLI
    # שלו), אבל בלי שום דרך מה-GUI לשנות את זה, כל טיימלאפס שהופק מהממשק יצא
    # שקט לגמרי בלי אף רמז למה - ברירת המחדל של ה-state (לא של הסקריפט עצמו)
    # חייבת להיות True כדי שמשתמש GUI רגיל יקבל סאונד מהריצה הראשונה שלו.
    state.reset_to_defaults()
    assert state.timelapse_keep_audio is True
    assert state.timelapse_target_seconds == "60"


def test_video_editor_remove_watermark_position_defaults_to_empty():
    state.reset_to_defaults()
    assert state.video_editor_remove_watermark_position == ""


def test_video_editor_remove_watermark_position_loads_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"video_editor_remove_watermark_position": "top-left"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.video_editor_remove_watermark_position == "top-left"


def test_video_editor_watermark_scale_and_custom_xy_default_to_expected_values():
    state.reset_to_defaults()
    assert state.video_editor_watermark_scale == "0.15"
    assert state.video_editor_watermark_x == ""
    assert state.video_editor_watermark_y == ""


def test_video_editor_watermark_scale_and_custom_xy_load_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {
        "video_editor_watermark_scale": "0.25", "video_editor_watermark_x": "0.3", "video_editor_watermark_y": "0.7",
    })
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.video_editor_watermark_scale == "0.25"
    assert state.video_editor_watermark_x == "0.3"
    assert state.video_editor_watermark_y == "0.7"


def test_video_editor_favorite_fields_defaults_to_empty():
    state.reset_to_defaults()
    assert state.video_editor_favorite_fields == ""


def test_video_editor_favorite_fields_loads_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"video_editor_favorite_fields": "vertical,codec"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.video_editor_favorite_fields == "vertical,codec"


def test_video_editor_watermark_position_accepts_new_center_positions(tmp_path, monkeypatch):
    # item: מיקומי watermark חדשים (top-center/bottom-center) - לא אמורים
    # להיחשב "לא מוכר" ולהיאפס בטעות ל-bottom-right בטעינה.
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"video_editor_watermark_position": "top-center"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.video_editor_watermark_position == "top-center"


def test_timelapse_keep_audio_can_be_disabled_via_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    _write_config(config_path, {"timelapse_keep_audio": False, "timelapse_target_seconds": "30"})
    monkeypatch.setattr("utils.shared.state.CONFIG_FILE", str(config_path))

    state.load_config()

    assert state.timelapse_keep_audio is False
    assert state.timelapse_target_seconds == "30"
