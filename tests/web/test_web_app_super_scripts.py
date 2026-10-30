# tests/web/test_web_app_super_scripts.py
#
# אינטגרציית web_app.py לשני "סקריפטי-העל" החדשים (item: הצעה לאיחוד סקריפטים
# ל"סקריפט-על", כמו עורך-העל): "מנהל-העל" (my_scripts/tools/super_manager.py,
# --mode scan|report|clean) ו-"משדר-העל" (my_scripts/stream/super_streamer.py,
# --mode twitch|obs|folder) - מרקאפ/_build_extra_args/ARCHIVED_SCRIPTS. TestClient
# בלבד; בדיקת ההרצה האמיתית של הסקריפטים עצמם ב-tests/bot/test_super_manager.py/
# test_super_streamer.py, ובדיקת ההתנהגות החיה בדפדפן בוצעה ידנית (ראו סיכום השיחה).


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from tests.page_source import served_page_text

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _index_html():
    return served_page_text(client)  # גל 24: ה-HTML + ה-bundles של CSS/JS


# --- ARCHIVED_SCRIPTS - הסקריפטים המקוריים שהתאחדו ---

def test_all_six_merged_originals_plus_migrate_secrets_and_timelapse_are_archived():
    resp = client.get("/api/scripts")
    archived_ids = {s["id"] for s in resp.json() if s["archived"]}
    expected_basenames = {
        "timelapse_maker.py", "disk_scanner.py", "report_to_excel.py", "duplicate_cleaner.py",
        "twitch_clip_import.py", "obs_replay_watcher.py", "capture_folder_watcher.py", "migrate_secrets_to_vault.py",
    }
    archived_basenames = {sid.split("/")[-1] for sid in archived_ids}
    assert archived_basenames == expected_basenames


def test_super_manager_and_super_streamer_themselves_are_not_archived():
    resp = client.get("/api/scripts")
    scripts = {s["id"].split("/")[-1]: s for s in resp.json()}
    assert scripts["super_manager.py"]["archived"] is False
    assert scripts["super_streamer.py"]["archived"] is False


def test_scripts_that_only_partially_overlap_remain_unarchived():
    # item: nuance מפורש מהשיחה - rocket_shorts_publisher/story_cutter/
    # duplicate_scene_detector/file_renamer חופפים חלקית בלבד לעורך-העל,
    # ו-audio_converter לא קשור לשרשרת שהתאחדה ב"מנהל-העל" -
    # אף אחד מאלה לא אמור להיות בארכיון.
    resp = client.get("/api/scripts")
    scripts = {s["id"].split("/")[-1]: s for s in resp.json()}
    for name in ("rocket_shorts_publisher.py", "story_cutter.py", "duplicate_scene_detector.py",
                 "file_renamer.py", "audio_converter.py"):
        assert scripts[name]["archived"] is False, f"{name} should not be archived"


# --- מנהל-העל UI ---

def test_super_manager_category_and_mode_fields_present_in_html():
    html = _index_html()
    assert 'id="superManagerOptions"' in html
    assert 'id="smMode"' in html
    assert 'id="smTargetDir"' in html
    assert 'id="smKeepPolicy"' in html
    assert 'id="smExecute"' in html


def test_super_manager_mode_visibility_function_present():
    html = _index_html()
    assert "function updateSuperManagerModeVisibility()" in html


def test_build_extra_args_super_manager_scan_mode_default():
    args = web_app._build_extra_args("super_manager.py", {})
    assert args == ["--mode", "scan"]


def test_build_extra_args_super_manager_scan_mode_full_options():
    args = web_app._build_extra_args("super_manager.py", {
        "sm_mode": "scan", "sm_target_dir": "D:\\Clips", "sm_export_excel": False, "sm_export_html": False,
    })
    assert args == ["--mode", "scan", "--target_dir", "D:\\Clips", "--no-excel", "--no-html"]


def test_build_extra_args_super_manager_report_mode_has_no_extra_flags():
    args = web_app._build_extra_args("super_manager.py", {"sm_mode": "report"})
    assert args == ["--mode", "report"]


def test_build_extra_args_super_manager_clean_mode_dry_run_by_default():
    args = web_app._build_extra_args("super_manager.py", {"sm_mode": "clean"})
    assert args == ["--mode", "clean"]


def test_build_extra_args_super_manager_clean_mode_execute_and_keep_newest():
    args = web_app._build_extra_args("super_manager.py", {"sm_mode": "clean", "sm_keep_policy": "newest", "sm_execute": True})
    assert args == ["--mode", "clean", "--keep", "newest", "--execute"]


def test_build_extra_args_super_manager_invalid_mode_falls_back_to_scan():
    args = web_app._build_extra_args("super_manager.py", {"sm_mode": "not-a-real-mode"})
    assert args == ["--mode", "scan"]


# --- משדר-העל UI ---

def test_super_streamer_category_and_mode_fields_present_in_html():
    html = _index_html()
    assert 'id="superStreamerOptions"' in html
    assert 'id="ssMode"' in html
    assert 'id="ssTwitchLimit"' in html


def test_super_streamer_mode_visibility_function_present():
    html = _index_html()
    assert "function updateSuperStreamerModeVisibility()" in html


def test_build_extra_args_super_streamer_folder_mode_default():
    args = web_app._build_extra_args("super_streamer.py", {})
    assert args == ["--mode", "folder"]


def test_build_extra_args_super_streamer_twitch_mode_default_limit_omitted():
    args = web_app._build_extra_args("super_streamer.py", {"ss_mode": "twitch"})
    assert args == ["--mode", "twitch"]


def test_build_extra_args_super_streamer_twitch_mode_custom_limit_included():
    args = web_app._build_extra_args("super_streamer.py", {"ss_mode": "twitch", "ss_twitch_limit": 25})
    assert args == ["--mode", "twitch", "--limit", "25"]


def test_build_extra_args_super_streamer_obs_mode_has_no_extra_flags():
    args = web_app._build_extra_args("super_streamer.py", {"ss_mode": "obs"})
    assert args == ["--mode", "obs"]


def test_build_extra_args_super_streamer_invalid_mode_falls_back_to_folder():
    args = web_app._build_extra_args("super_streamer.py", {"ss_mode": "not-a-real-mode"})
    assert args == ["--mode", "folder"]


# --- selectScript wiring (JS) ---

def test_select_script_shows_super_manager_panel_only_for_its_own_script():
    html = _index_html()
    assert 'document.getElementById("superManagerOptions").hidden = basename !== "super_manager.py";' in html


def test_select_script_shows_super_streamer_panel_only_for_its_own_script():
    html = _index_html()
    assert 'document.getElementById("superStreamerOptions").hidden = basename !== "super_streamer.py";' in html
