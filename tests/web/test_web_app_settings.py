# tests/web/test_web_app_settings.py - REST endpoint tests for web_app.py, topic: settings (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
import json
from tests.web_app_support import (  # noqa: F401
    _setup_fake_data_dir,
    client,
    web_app,
)


def test_api_settings_export_returns_404_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "does_not_exist.json"))

    resp = client.get("/api/settings/export")

    assert resp.status_code == 404


def test_api_settings_export_returns_existing_config_contents(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"theme": "Pink", "language": "he"}', encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    resp = client.get("/api/settings/export")

    assert resp.status_code == 200
    assert resp.json() == {"theme": "Pink", "language": "he"}


def test_api_settings_import_writes_config_and_backs_up_existing(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"theme": "Green"}', encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    resp = client.post("/api/settings/import", json={"theme": "Pink", "language": "en"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"theme": "Pink", "language": "en"}
    backup_path = tmp_path / "config.json.bak"
    assert json.loads(backup_path.read_text(encoding="utf-8")) == {"theme": "Green"}


def test_api_settings_import_creates_file_when_none_existed(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    resp = client.post("/api/settings/import", json={"theme": "Blue"})

    assert resp.status_code == 200
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"theme": "Blue"}
    assert not (tmp_path / "config.json.bak").exists()


def test_api_settings_import_rejects_non_dict_json(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "config.json"))

    resp = client.post("/api/settings/import", json=["not", "a", "dict"])

    assert resp.status_code == 400


def test_api_settings_import_rejects_malformed_json(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "config.json"))

    resp = client.post("/api/settings/import", content=b"{not valid json", headers={"Content-Type": "application/json"})

    assert resp.status_code == 400


def test_api_settings_import_records_audit_log_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "config.json"))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/settings/import", json={"theme": "Blue"})

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "settings_import")


def test_api_backup_create_encrypted_creates_file_and_records_audit_log(tmp_path, monkeypatch):
    data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/backup/create_encrypted", json={"passphrase": "hunter2"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"].endswith(".ibkp")
    assert "config.json" in data["included_files"]
    assert (backups_dir / data["filename"]).exists()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "backup_create")
    assert kwargs["details"] == data["filename"]


def test_api_backup_create_encrypted_requires_passphrase(tmp_path, monkeypatch):
    _setup_fake_data_dir(tmp_path, monkeypatch)
    resp = client.post("/api/backup/create_encrypted", json={"passphrase": ""})
    assert resp.status_code == 400


def test_api_backup_create_encrypted_rejects_mismatched_origin(tmp_path, monkeypatch):
    _setup_fake_data_dir(tmp_path, monkeypatch)
    resp = client.post(
        "/api/backup/create_encrypted", json={"passphrase": "hunter2"},
        headers={"origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_api_backup_list_returns_known_backups(tmp_path, monkeypatch):
    _data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)
    (backups_dir / "encrypted_backup_20260101_000000.ibkp").write_bytes(b"fake bytes")
    (backups_dir / "not_a_backup.txt").write_text("ignore me", encoding="utf-8")

    resp = client.get("/api/backup/list")

    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["filename"] == "encrypted_backup_20260101_000000.ibkp"
    assert entries[0]["size_bytes"] == len(b"fake bytes")


def test_api_backup_list_returns_empty_when_no_backups_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BACKUPS_DIR", str(tmp_path / "does_not_exist"))
    resp = client.get("/api/backup/list")
    assert resp.status_code == 200
    assert resp.json() == []


def test_api_backup_download_serves_existing_file(tmp_path, monkeypatch):
    _data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)
    (backups_dir / "encrypted_backup_20260101_000000.ibkp").write_bytes(b"fake encrypted content")

    resp = client.get("/api/backup/download/encrypted_backup_20260101_000000.ibkp")

    assert resp.status_code == 200
    assert resp.content == b"fake encrypted content"


def test_api_backup_download_rejects_path_traversal(tmp_path, monkeypatch):
    _setup_fake_data_dir(tmp_path, monkeypatch)
    resp = client.get("/api/backup/download/..%2f..%2fsecrets_vault.py")
    assert resp.status_code == 404


def test_api_backup_download_returns_404_for_missing_file(tmp_path, monkeypatch):
    _setup_fake_data_dir(tmp_path, monkeypatch)
    resp = client.get("/api/backup/download/does_not_exist.ibkp")
    assert resp.status_code == 404


def test_api_backup_restore_round_trip_restores_files_and_records_audit_log(tmp_path, monkeypatch):
    data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)
    create_resp = client.post("/api/backup/create_encrypted", json={"passphrase": "hunter2"})
    filename = create_resp.json()["filename"]

    (data_dir / "config.json").write_text(json.dumps({"theme": "Pink"}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/backup/restore", json={"passphrase": "hunter2", "filename": filename})

    assert resp.status_code == 200
    assert "config.json" in resp.json()["restored_files"]
    restored_config = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
    assert restored_config == {"theme": "Green"}
    backed_up = json.loads((data_dir / "config.json.bak").read_text(encoding="utf-8"))
    assert backed_up == {"theme": "Pink"}
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ("web", "backup_restore")
    assert kwargs["details"] == filename


def test_api_backup_restore_rejects_wrong_passphrase(tmp_path, monkeypatch):
    _data_dir, backups_dir = _setup_fake_data_dir(tmp_path, monkeypatch)
    create_resp = client.post("/api/backup/create_encrypted", json={"passphrase": "right-password"})
    filename = create_resp.json()["filename"]

    resp = client.post("/api/backup/restore", json={"passphrase": "wrong-password", "filename": filename})

    assert resp.status_code == 400


def test_api_backup_restore_rejects_unknown_filename(tmp_path, monkeypatch):
    _setup_fake_data_dir(tmp_path, monkeypatch)
    resp = client.post("/api/backup/restore", json={"passphrase": "x", "filename": "does_not_exist.ibkp"})
    assert resp.status_code == 404


def test_api_backup_restore_rejects_mismatched_origin(tmp_path, monkeypatch):
    _setup_fake_data_dir(tmp_path, monkeypatch)
    resp = client.post(
        "/api/backup/restore", json={"passphrase": "x", "filename": "whatever.ibkp"},
        headers={"origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_api_settings_global_get_returns_defaults_when_no_config(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "does_not_exist.json"))
    resp = client.get("/api/settings/global")
    assert resp.status_code == 200
    assert resp.json() == {"webhook": "", "turbo_active": False, "nas_folder": "", "auto_backup_active": False, "night_active": False}


def test_api_settings_global_save_and_reload_roundtrip(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    payload = {"webhook": "https://discord.com/hook", "turbo_active": True, "nas_folder": "D:/Backups", "auto_backup_active": True, "night_active": True}

    save_resp = client.post("/api/settings/global", json=payload)
    assert save_resp.status_code == 200

    get_resp = client.get("/api/settings/global")
    assert get_resp.json() == payload


def test_api_settings_global_save_preserves_other_config_keys(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"theme": "Pink", "video_editor_codec": "hevc"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    client.post("/api/settings/global", json={"webhook": "x", "turbo_active": False, "nas_folder": "", "auto_backup_active": False, "night_active": False})

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["theme"] == "Pink"
    assert saved["video_editor_codec"] == "hevc"
    assert saved["webhook"] == "x"


def test_api_settings_reset_backs_up_existing_and_resets_to_defaults(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"theme": "Pink", "webhook": "old-hook"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    resp = client.post("/api/settings/reset")

    assert resp.status_code == 200
    backup = json.loads((tmp_path / "config.json.bak").read_text(encoding="utf-8"))
    assert backup == {"theme": "Pink", "webhook": "old-hook"}
    reset_config = json.loads(config_path.read_text(encoding="utf-8"))
    assert reset_config["theme"] == "Green"
    assert reset_config["webhook"] == ""


def test_api_settings_reset_records_audit_log_entry(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"theme": "Pink"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/settings/reset")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "settings_reset")


def test_api_settings_themes_returns_known_presets():
    resp = client.get("/api/settings/themes")
    assert resp.status_code == 200
    themes = resp.json()
    assert "Green" in themes
    assert "accent" in themes["Green"]


def test_api_settings_style_get_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(tmp_path / "does_not_exist.json"))
    resp = client.get("/api/settings/style")
    assert resp.status_code == 200
    data = resp.json()
    assert data["theme"] == "Green"
    assert data["language"] == "en"   # 30.10.2026: התקנה חדשה באנגלית (utils/shared/ui_language.py)


def test_api_settings_style_save_rejects_unknown_theme(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    client.post("/api/settings/style", json={"theme": "NotARealTheme", "custom_accent_hex": "", "language": "he"})

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["theme"] == "Green"


def test_api_settings_style_save_rejects_unknown_language(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    client.post("/api/settings/style", json={"theme": "Green", "custom_accent_hex": "", "language": "fr"})

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["language"] == "he"


def test_api_settings_style_save_updates_custom_theme_swatch(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config_path))

    resp = client.post("/api/settings/style", json={"theme": "Custom", "custom_accent_hex": "#123456", "language": "he"})
    assert resp.status_code == 200

    themes_resp = client.get("/api/settings/themes")
    assert themes_resp.json()["Custom"]["accent"] == "#123456"


# --- Rocket Shorts (item 4/N desktop-parity gaps): /api/rocket_settings ---

def test_api_rocket_settings_get_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(tmp_path / "does_not_exist.json"))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "does_not_exist_counter.txt"))

    resp = client.get("/api/rocket_settings")

    assert resp.status_code == 200
    data = resp.json()
    assert data["input_dir"] == web_app.BASE_DIR
    assert data["watermark_image_path"] == ""
    assert data["preset"] is None
    assert data["enable_weekly_recap"] is False
    assert data["weekly_recap_period"] == "week"
    assert data["weekly_recap_day"] == 6
    assert data["enable_captions"] is False
    assert data["enable_captions_translate"] is False
    assert data["clip_hotkey"] == ""
    assert data["capture_voice_channel_id"] == ""
    assert data["capture_watch_dir"] == ""
    assert data["max_concurrent_renders"] == 1
    assert data["counter"] == 1


def test_api_rocket_settings_get_reflects_saved_file(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    settings_path.write_text(json.dumps({
        "input_dir": "D:/Clips", "output_dir": "D:/Exports", "watermark_image_path": "D:/logo.png",
        "encoder": "hevc_nvenc", "ffmpeg_preset": "p5", "quality_cq": 19,
        "enable_weekly_recap": True, "weekly_recap_period": "month", "weekly_recap_day": 2,
        "enable_captions": True, "enable_captions_translate": True, "clip_hotkey": "ctrl+alt+c",
        "capture_voice_channel_id": "111222333", "capture_watch_dir": "D:\\Streamlabs Output", "max_concurrent_renders": 3,
    }), encoding="utf-8")
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))

    resp = client.get("/api/rocket_settings")

    assert resp.status_code == 200
    data = resp.json()
    assert data["input_dir"] == "D:/Clips"
    assert data["output_dir"] == "D:/Exports"
    assert data["preset"] == "📱 Balanced (HEVC NVENC, P5)"
    assert data["enable_weekly_recap"] is True
    assert data["weekly_recap_period"] == "month"
    assert data["weekly_recap_day"] == 2
    assert data["enable_captions"] is True
    assert data["enable_captions_translate"] is True
    assert data["clip_hotkey"] == "ctrl+alt+c"
    assert data["capture_voice_channel_id"] == "111222333"
    assert data["capture_watch_dir"] == "D:\\Streamlabs Output"
    assert data["max_concurrent_renders"] == 3


def test_api_rocket_settings_get_falls_back_to_week_for_an_invalid_saved_period(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    settings_path.write_text(json.dumps({"weekly_recap_period": "fortnight"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))

    resp = client.get("/api/rocket_settings")

    assert resp.json()["weekly_recap_period"] == "week"


def test_api_rocket_settings_presets_lists_all_five(tmp_path, monkeypatch):
    resp = client.get("/api/rocket_settings/presets")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["presets"]) == 5
    assert len(data["recap_days"]) == 7


def test_api_rocket_settings_save_writes_file_and_counter(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    counter_path = tmp_path / "counter.txt"
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(counter_path))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={
        "input_dir": "D:/Clips", "output_dir": "D:/Exports", "watermark_image_path": "D:/logo.png",
        "preset": "🚀 Max Quality (HEVC NVENC, P7)",
        "enable_weekly_recap": True, "weekly_recap_period": "year", "weekly_recap_day": 5,
        "enable_captions": True, "enable_captions_translate": True, "clip_hotkey": " ctrl+alt+z ",
        "capture_voice_channel_id": " 444555666 ",
        "capture_watch_dir": " D:\\ShadowPlay ",
        "max_concurrent_renders": 4,
        "counter": 42,
    })

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["input_dir"] == "D:/Clips"
    assert saved["rocket_videos_directory"] == "D:/Clips"
    assert saved["output_dir"] == "D:/Exports"
    assert saved["watermark_image_path"] == "D:/logo.png"
    assert saved["encoder"] == "hevc_nvenc"
    assert saved["ffmpeg_preset"] == "p7"
    assert saved["quality_cq"] == 17
    assert saved["enable_weekly_recap"] is True
    assert saved["weekly_recap_period"] == "year"
    assert saved["weekly_recap_day"] == 5
    assert saved["enable_captions"] is True
    assert saved["enable_captions_translate"] is True
    assert saved["clip_hotkey"] == "ctrl+alt+z"
    assert saved["capture_voice_channel_id"] == "444555666"
    assert saved["capture_watch_dir"] == "D:\\ShadowPlay"
    assert saved["max_concurrent_renders"] == 4
    assert counter_path.read_text(encoding="utf-8") == "42"


def test_api_rocket_settings_naming_defaults_are_the_same_with_or_without_a_counter(tmp_path, monkeypatch):
    """30.10.2026: מה שחסר בקובץ מוצג עם ברירת המחדל - "Shorts", בלי משחק, רזולוציית המקור - כמו שה-publisher ירנדר."""
    settings_path, counter_path = tmp_path / "rocket_settings.json", tmp_path / "counter.txt"
    settings_path.write_text(json.dumps({"input_dir": "D:/Clips"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(counter_path))
    assert {k: client.get("/api/rocket_settings").json()[k] for k in ("title_prefix", "game_name")} == {"title_prefix": "Shorts",
                                                                                                         "game_name": ""}
    counter_path.write_text("42", encoding="utf-8")
    assert {k: client.get("/api/rocket_settings").json()[k] for k in ("title_prefix", "game_name", "output_resolution")} == {
        "title_prefix": "Shorts", "game_name": "", "output_resolution": "source"}


def test_api_rocket_settings_save_keeps_the_prefix_when_an_old_page_does_not_send_it(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    settings_path.write_text(json.dumps({"title_prefix": "MyShorts", "game_name": "Minecraft"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    assert client.post("/api/rocket_settings", json={"input_dir": "D:/Clips"}).status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert (saved["title_prefix"], saved["game_name"]) == ("MyShorts", "Minecraft")

    client.post("/api/rocket_settings", json={"input_dir": "D:/Clips", "title_prefix": ' My:Clips? ', "game_name": " "})
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert (saved["title_prefix"], saved["game_name"]) == ("MyClips", "")
    assert "output_resolution" not in saved   # הדף לא שלח - לא נכתב

    client.post("/api/rocket_settings", json={"input_dir": "D:/Clips", "output_resolution": "1080"})
    assert json.loads(settings_path.read_text(encoding="utf-8"))["output_resolution"] == "1080"
    client.post("/api/rocket_settings", json={"input_dir": "D:/Clips", "output_resolution": "8K"})
    assert json.loads(settings_path.read_text(encoding="utf-8"))["output_resolution"] == "source"


def test_api_rocket_settings_save_defaults_max_concurrent_renders_to_1_when_invalid(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={"input_dir": "D:/Clips", "max_concurrent_renders": "not-a-number"})

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["max_concurrent_renders"] == 1


def test_api_rocket_settings_save_defaults_weekly_recap_day_to_6_when_invalid(tmp_path, monkeypatch):
    # item: בדיקת באגים מקיפה - weekly_recap_day היה קורא int() בלי try/except,
    # בניגוד לשני השדות המספריים האחרים באותה פונקציה - ערך לא-מספרי היה
    # מפיל את כל השמירה (500) ומאבד גם שדות אחרים שלא קשורים באותה בקשה.
    settings_path = tmp_path / "rocket_settings.json"
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={"input_dir": "D:/Clips", "weekly_recap_day": "not-a-number"})

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["weekly_recap_day"] == 6


# --- /api/rocket_settings/probe_nvenc (item: מודעות למגבלת סשנים אמיתית של NVENC) ---

def test_api_rocket_settings_probe_nvenc_returns_detected_count(monkeypatch):
    monkeypatch.setattr(web_app, "probe_max_concurrent_nvenc_sessions", lambda ffmpeg_exe: 3)

    resp = client.post("/api/rocket_settings/probe_nvenc")

    assert resp.status_code == 200
    assert resp.json() == {"detected": 3}


def test_api_rocket_settings_probe_nvenc_rejects_mismatched_origin(monkeypatch):
    monkeypatch.setattr(web_app, "probe_max_concurrent_nvenc_sessions", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))

    resp = client.post("/api/rocket_settings/probe_nvenc", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403


def test_api_rocket_settings_save_ignores_an_invalid_period_and_falls_back_to_week(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={"input_dir": "D:/Clips", "weekly_recap_period": "fortnight"})

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["weekly_recap_period"] == "week"


def test_api_rocket_settings_save_defaults_output_dir_to_input_dir(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={
        "input_dir": "D:/Clips", "output_dir": "", "watermark_image_path": "",
        "enable_weekly_recap": False, "weekly_recap_day": 0, "enable_captions": False, "counter": 1,
    })

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["output_dir"] == "D:/Clips"


def test_api_rocket_settings_save_preserves_unmanaged_keys(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    settings_path.write_text(json.dumps({"input_dir": "old", "some_other_key": "keep-me"}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={
        "input_dir": "new", "output_dir": "new", "watermark_image_path": "",
        "enable_weekly_recap": False, "weekly_recap_day": 0, "enable_captions": False, "counter": 1,
    })

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["some_other_key"] == "keep-me"
    assert saved["input_dir"] == "new"


def test_api_rocket_settings_save_ignores_invalid_preset(tmp_path, monkeypatch):
    settings_path = tmp_path / "rocket_settings.json"
    settings_path.write_text(json.dumps({"encoder": "libx264", "ffmpeg_preset": "medium", "quality_cq": 22}), encoding="utf-8")
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))
    monkeypatch.setattr(web_app, "DATA_DIR", str(tmp_path))

    resp = client.post("/api/rocket_settings", json={
        "input_dir": "D:/Clips", "output_dir": "D:/Clips", "watermark_image_path": "",
        "preset": "does-not-exist", "enable_weekly_recap": False, "weekly_recap_day": 0,
        "enable_captions": False, "counter": 1,
    })

    assert resp.status_code == 200
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["encoder"] == "libx264"


def test_api_rocket_settings_save_requires_same_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "ROCKET_SETTINGS_PATH", str(tmp_path / "rocket_settings.json"))
    monkeypatch.setattr(web_app, "ROCKET_COUNTER_PATH", str(tmp_path / "counter.txt"))

    resp = client.post(
        "/api/rocket_settings",
        json={"input_dir": "x", "output_dir": "x", "watermark_image_path": "", "enable_weekly_recap": False,
              "weekly_recap_day": 0, "enable_captions": False, "counter": 1},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403


# --- GitHub Releases update check (8/N desktop-parity gaps) ---

def test_api_update_check_reports_new_version(monkeypatch):
    monkeypatch.setattr(web_app, "check_for_update", lambda current: "v9.9.9")

    resp = client.get("/api/update_check")

    assert resp.status_code == 200
    data = resp.json()
    assert data["latest_version"] == "v9.9.9"
    assert data["current_version"] == web_app.APP_VERSION
    assert data["releases_url"] == web_app.RELEASES_PAGE_URL


def test_api_update_check_reports_none_when_up_to_date(monkeypatch):
    monkeypatch.setattr(web_app, "check_for_update", lambda current: None)

    resp = client.get("/api/update_check")

    assert resp.status_code == 200
    assert resp.json()["latest_version"] is None


# --- /api/update_check/apply (item: true auto-update) ---

def test_api_update_apply_returns_success_result(monkeypatch):
    monkeypatch.setattr(web_app, "apply_update", lambda repo_dir: (True, "העדכון הותקן בהצלחה."))

    resp = client.post("/api/update_check/apply")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "העדכון הותקן בהצלחה."}


def test_api_update_apply_returns_failure_result(monkeypatch):
    monkeypatch.setattr(web_app, "apply_update", lambda repo_dir: (False, "יש שינויים מקומיים לא-שמורים."))

    resp = client.post("/api/update_check/apply")

    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "message": "יש שינויים מקומיים לא-שמורים."}


def test_api_update_apply_passes_base_dir(monkeypatch):
    calls = []
    monkeypatch.setattr(web_app, "apply_update", lambda repo_dir: calls.append(repo_dir) or (True, "ok"))

    client.post("/api/update_check/apply")

    assert calls == [web_app.BASE_DIR]


def test_api_update_apply_rejects_mismatched_origin(monkeypatch):
    monkeypatch.setattr(web_app, "apply_update", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))

    resp = client.post("/api/update_check/apply", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403


def test_api_update_apply_records_audit_log(monkeypatch):
    monkeypatch.setattr(web_app, "apply_update", lambda repo_dir: (True, "ok"))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    client.post("/api/update_check/apply")

    assert calls[0][0] == ("web", "update_apply")


# --- System diagnostics (9/N desktop-parity gaps): /api/diagnostics ---

def test_api_diagnostics_reports_all_checks(monkeypatch):
    monkeypatch.setattr(
        web_app, "run_diagnostics",
        lambda: [("FFmpeg", True, "C:/ffmpeg.exe"), ("מסד נתונים", False, "boom")],
    )

    resp = client.get("/api/diagnostics")

    assert resp.status_code == 200
    assert resp.json() == [
        {"name": "FFmpeg", "ok": True, "detail": "C:/ffmpeg.exe"},
        {"name": "מסד נתונים", "ok": False, "detail": "boom"},
    ]


def test_api_diagnostics_uses_real_checks_end_to_end():
    # בלי monkeypatch - קורא ל-utils/shared/diagnostics.py האמיתי, כדי לוודא שהאינטגרציה
    # (לא רק ה-mock) עובדת: על סביבת הפיתוח האמיתית לפחות FFmpeg/Python/DB תקינים.
    resp = client.get("/api/diagnostics")

    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 5
    assert all(set(["name", "ok", "detail"]).issubset(r.keys()) for r in results)


# --- /api/credentials/check_validity (item: credential vault health-check) ---

def test_api_credentials_check_validity_returns_results(monkeypatch):
    monkeypatch.setattr(
        web_app, "check_credential_validity",
        lambda: [("GEMINI_API_KEY", True, True, "תקין"), ("TWITCH_CLIENT_ID/SECRET", False, None, "לא מוגדר")],
    )

    resp = client.post("/api/credentials/check_validity")

    assert resp.status_code == 200
    assert resp.json() == [
        {"name": "GEMINI_API_KEY", "configured": True, "valid": True, "detail": "תקין"},
        {"name": "TWITCH_CLIENT_ID/SECRET", "configured": False, "valid": None, "detail": "לא מוגדר"},
    ]


def test_api_credentials_check_validity_rejects_mismatched_origin(monkeypatch):
    monkeypatch.setattr(web_app, "check_credential_validity", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))

    resp = client.post("/api/credentials/check_validity", headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403


def test_api_credentials_check_validity_records_audit_log_entry(monkeypatch):
    monkeypatch.setattr(web_app, "check_credential_validity", lambda: [])
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    resp = client.post("/api/credentials/check_validity")

    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "credentials_check_validity")


# --- /api/credentials/rotation_status, /api/credentials/rotate (item: key-age tracking) ---

def test_api_credentials_rotation_status_returns_results(monkeypatch):
    monkeypatch.setattr(
        web_app, "get_rotation_status",
        lambda: [("GEMINI_API_KEY", True, 12, False), ("DISCORD_TOKEN", True, 200, True)],
    )

    resp = client.get("/api/credentials/rotation_status")

    assert resp.status_code == 200
    assert resp.json() == [
        {"name": "GEMINI_API_KEY", "configured": True, "age_days": 12, "stale": False},
        {"name": "DISCORD_TOKEN", "configured": True, "age_days": 200, "stale": True},
    ]


def test_api_credentials_rotate_rejects_unknown_name(monkeypatch):
    monkeypatch.setattr(web_app, "is_vault_available", lambda: True)

    resp = client.post("/api/credentials/rotate", json={"name": "NOT_A_REAL_KEY", "value": "x"})

    assert resp.status_code == 400


def test_api_credentials_rotate_rejects_empty_value(monkeypatch):
    monkeypatch.setattr(web_app, "is_vault_available", lambda: True)

    resp = client.post("/api/credentials/rotate", json={"name": "GEMINI_API_KEY", "value": ""})

    assert resp.status_code == 400


def test_api_credentials_rotate_rejects_when_vault_unavailable(monkeypatch):
    monkeypatch.setattr(web_app, "is_vault_available", lambda: False)

    resp = client.post("/api/credentials/rotate", json={"name": "GEMINI_API_KEY", "value": "new-value"})

    assert resp.status_code == 400


def test_api_credentials_rotate_calls_set_secret_and_logs_name_only(monkeypatch):
    monkeypatch.setattr(web_app, "is_vault_available", lambda: True)
    calls = []
    monkeypatch.setattr(web_app, "set_vault_secret", lambda name, value: calls.append((name, value)))
    audit_calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: audit_calls.append((a, kw)))

    resp = client.post("/api/credentials/rotate", json={"name": "GEMINI_API_KEY", "value": "new-secret-value"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert calls == [("GEMINI_API_KEY", "new-secret-value")]
    # הערך עצמו אף פעם לא נכתב ל-audit log - רק שם ה-credential.
    assert audit_calls[0] == (("web", "credential_rotate"), {"details": "GEMINI_API_KEY", "username": audit_calls[0][1]["username"]})
    assert "new-secret-value" not in str(audit_calls)


def test_api_credentials_rotate_rejects_mismatched_origin(monkeypatch):
    monkeypatch.setattr(web_app, "is_vault_available", lambda: True)
    monkeypatch.setattr(web_app, "set_vault_secret", lambda *a: (_ for _ in ()).throw(AssertionError("should not be called")))

    resp = client.post(
        "/api/credentials/rotate", json={"name": "GEMINI_API_KEY", "value": "x"},
        headers={"origin": "https://evil.example.com"},
    )

    assert resp.status_code == 403
