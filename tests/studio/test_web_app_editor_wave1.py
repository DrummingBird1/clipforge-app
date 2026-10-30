# tests/studio/test_web_app_editor_wave1.py
#
# סבב 102-ההצעות לעורך-העל, גל 1 - בטיחות-מידע ופער CLI→Web:
#   58 - גיבוי אוטומטי מסתובב לקובצי הפרופילים + שחזור מגיבוי
#   59 - מחיקה רכה (סל מחזור) לפרופילים
#   29-37 - דגלי CLI שלא היה להם שום שדה בווב (hwaccel/hwaccel-decode/smooth-fps/
#           target-size-mb/force/preview-only/nvenc-cq/nvenc-preset/chromakey
#           similarity+blend/remove-watermark width+height)
#   38 - מצב "🔗 איחוד קטעים" בווב (--concat-files לפי סדר התור)
#   39 - דריסות פר-קובץ (--batch-overrides) inline בשורות התור
#
# כל נתיב-נתונים מופנה ל-tmp_path (autouse fixture למטה) - אף טסט כאן לא נוגע
# בתיקיית data/ האמיתית (שם יושבים פרופילים אמיתיים ובלתי-ניתנים-לשחזור).
import json
from tests import PROJECT_ROOT
import os
import subprocess
import sys


import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import video_editor_profiles as vep
from utils.video.video_editor import BATCH_OVERRIDE_ALLOWED_FIELDS, sanitize_batch_overrides
from tests.page_source import served_page_text

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

REAL_DATA_DIR = os.path.realpath(web_app.DATA_DIR)


@pytest.fixture(autouse=True)
def _isolate_data(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app, "BATCH_OVERRIDES_DIR", str(tmp_path / "batch_overrides"))
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


def _args(payload, **kwargs):
    return web_app._build_extra_args("video_editor.py", payload, **kwargs)


# --- 58: גיבוי אוטומטי מסתובב ---

def test_backup_and_trash_paths_follow_patched_profiles_path(tmp_path):
    # הבטחת-בטיחות: טסטים שמפנים את PROFILES_PATH ל-tmp_path חייבים לקבל גם
    # את תיקיית הגיבויים וסל-המחזור שם - לא בתוך data/ האמיתית.
    assert os.path.realpath(vep._backup_dir_for(vep.PROFILES_PATH)).startswith(os.path.realpath(str(tmp_path)))
    assert os.path.realpath(vep._trash_path()).startswith(os.path.realpath(str(tmp_path)))
    assert not os.path.realpath(vep._trash_path()).startswith(REAL_DATA_DIR)


def test_first_save_creates_no_backup_second_save_backs_up_previous_state():
    vep.save_profile("A", {"codec": "h264"})
    assert vep.list_profile_backups() == []  # לא היה קובץ קודם לגבות
    vep.save_profile("B", {"codec": "hevc"})
    backups = vep.list_profile_backups()
    assert len(backups) == 1
    assert backups[0]["profile_names"] == ["A"]
    assert backups[0]["profile_count"] == 1


def test_backups_rotate_keeping_recent_limit(monkeypatch):
    monkeypatch.setattr(vep, "MAX_RECENT_BACKUPS_PER_FILE", 3)
    for i in range(8):
        vep.save_profile(f"P{i}", {"codec": "h264"})
    backups = vep.list_profile_backups()
    # 3 אחרונים + (אותו יום - כבר כלול) = 3 בדיוק
    assert len(backups) == 3
    assert backups[0]["profile_count"] == 7  # הגיבוי האחרון = המצב לפני השמירה האחרונה


def test_meta_and_history_writes_are_backed_up_too(tmp_path):
    vep.save_profile("A", {"codec": "h264"})
    vep.save_profile("A", {"codec": "hevc"})  # דוחף היסטוריה + כותב מטא שוב
    backup_dir = vep._backup_dir_for(vep.META_PATH)
    names = os.listdir(backup_dir)
    assert any(n.startswith("video_editor_profile_meta__") for n in names)


def test_restore_backup_merge_missing_does_not_touch_existing_profiles():
    vep.save_profile("Keep", {"codec": "h264"})
    vep.save_profile("Lost", {"codec": "av1"})
    vep.save_profile("X", {"codec": "h264"})  # הגיבוי שנוצר כאן מכיל Keep(h264)+Lost
    backup_id = next(b["id"] for b in vep.list_profile_backups() if b["profile_names"] == ["Keep", "Lost"])
    vep.delete_profile("Lost")
    vep.save_profile("Keep", {"codec": "hevc"})
    result = vep.restore_profile_backup(backup_id, mode="merge_missing")
    profiles = vep.load_profiles()
    assert result["restored"] == ["Lost"]
    assert profiles["Lost"]["codec"] == "av1"
    assert profiles["Keep"]["codec"] == "hevc"  # קיים - לא נדרס בגרסה הישנה מהגיבוי
    assert "X" in profiles


def test_restore_backup_replace_restores_deleted_profile_and_is_itself_reversible():
    vep.save_profile("Gold", {"codec": "av1", "vertical": True})
    vep.save_profile("Other", {"codec": "h264"})
    backup_with_gold = next(b for b in vep.list_profile_backups() if b["profile_names"] == ["Gold"])
    vep.delete_profile("Gold")
    assert "Gold" not in vep.load_profiles()
    result = vep.restore_profile_backup(backup_with_gold["id"], mode="replace")
    assert result["restored"] == ["Gold"]
    assert vep.load_profiles()["Gold"]["codec"] == "av1"
    # המצב שלפני ההחלפה (Other בלבד) גובה בעצמו - אפשר לחזור אליו.
    assert any(b["profile_names"] == ["Other"] for b in vep.list_profile_backups())


def test_restore_backup_rejects_unknown_or_traversal_ids_and_modes():
    vep.save_profile("A", {"codec": "h264"})
    vep.save_profile("B", {"codec": "h264"})
    with pytest.raises(ValueError):
        vep.restore_profile_backup("..\\..\\config.json")
    with pytest.raises(ValueError):
        vep.restore_profile_backup("nope.json")
    with pytest.raises(ValueError):
        vep.restore_profile_backup(vep.list_profile_backups()[0]["id"], mode="bogus")


def test_backup_endpoints_list_and_restore():
    vep.save_profile("Gold", {"codec": "av1"})
    vep.save_profile("Tmp", {"codec": "h264"})
    vep.delete_profile("Gold")
    resp = client.get("/api/video_editor_profile_backups")
    assert resp.status_code == 200
    backups = resp.json()["backups"]
    gold_backup = next(b for b in backups if "Gold" in b["profile_names"])
    resp = client.post("/api/video_editor_profile_backups/restore", json={"id": gold_backup["id"], "mode": "merge_missing"})
    assert resp.status_code == 200
    assert "Gold" in resp.json()["restored"]
    assert "Gold" in vep.load_profiles()


def test_backup_restore_endpoint_rejects_bad_id():
    resp = client.post("/api/video_editor_profile_backups/restore", json={"id": "../x.json"})
    assert resp.status_code == 400


# --- 59: מחיקה רכה ---

def test_delete_moves_profile_with_history_and_meta_to_trash():
    vep.save_profile("R", {"codec": "h264"})
    vep.save_profile("R", {"codec": "hevc"})  # היסטוריה אחת
    vep.record_profile_used("R")
    assert vep.delete_profile("R") is True
    assert "R" not in vep.load_profiles()
    trash = vep.list_trash()
    assert len(trash) == 1
    assert trash[0]["name"] == "R"
    assert trash[0]["history_count"] == 1
    assert trash[0]["codec"] == "hevc"


def test_restore_from_trash_brings_back_history_and_meta():
    vep.save_profile("R", {"codec": "h264"})
    vep.save_profile("R", {"codec": "hevc"})
    vep.record_profile_used("R")
    vep.delete_profile("R")
    entry_id = vep.list_trash()[0]["id"]
    restored = vep.restore_from_trash(entry_id)
    assert restored["name"] == "R"
    assert vep.load_profiles()["R"]["codec"] == "hevc"
    assert len(vep.get_profile_history("R")) == 1
    assert vep.load_profile_meta("R")["run_count"] == 1
    assert vep.list_trash() == []


def test_restore_from_trash_refuses_to_overwrite_live_profile_but_accepts_new_name():
    vep.save_profile("R", {"codec": "h264"})
    vep.delete_profile("R")
    vep.save_profile("R", {"codec": "av1"})  # פרופיל חדש באותו שם נוצר בינתיים
    entry_id = vep.list_trash()[0]["id"]
    with pytest.raises(ValueError):
        vep.restore_from_trash(entry_id)
    vep.restore_from_trash(entry_id, new_name="R (old)")
    profiles = vep.load_profiles()
    assert profiles["R"]["codec"] == "av1"
    assert profiles["R (old)"]["codec"] == "h264"


def test_purge_trash_entry():
    vep.save_profile("R", {"codec": "h264"})
    vep.delete_profile("R")
    entry_id = vep.list_trash()[0]["id"]
    assert vep.purge_trash_entry(entry_id) is True
    assert vep.list_trash() == []
    assert vep.purge_trash_entry(entry_id) is False


def test_trash_endpoints_roundtrip():
    vep.save_profile("R", {"codec": "h264"})
    client.delete("/api/video_editor_profiles/R")
    entries = client.get("/api/video_editor_profile_trash").json()["entries"]
    assert [e["name"] for e in entries] == ["R"]
    resp = client.post(f"/api/video_editor_profile_trash/{entries[0]['id']}/restore", json={})
    assert resp.status_code == 200
    assert "R" in vep.load_profiles()
    client.delete("/api/video_editor_profiles/R")
    entry_id = client.get("/api/video_editor_profile_trash").json()["entries"][0]["id"]
    assert client.delete(f"/api/video_editor_profile_trash/{entry_id}").status_code == 200
    assert client.delete(f"/api/video_editor_profile_trash/{entry_id}").status_code == 404


# --- 29-37: פער CLI→Web ---

def test_new_gap_flags_each_emitted():
    args = _args({
        "codec": "hevc", "hwaccel": True, "hwaccel_decode": True, "smooth_fps": True,
        "target_size_mb": 25, "force": True, "preview_only": True, "nvenc_preset": "p7", "nvenc_cq": 21,
    })
    for flag in ("--hwaccel", "--hwaccel-decode", "--smooth-fps", "--force", "--preview-only"):
        assert flag in args
    assert args[args.index("--target-size-mb") + 1] == "25"
    assert args[args.index("--nvenc-preset") + 1] == "p7"
    assert args[args.index("--nvenc-cq") + 1] == "21"


def test_gap_flags_absent_by_default():
    args = _args({})
    for flag in ("--hwaccel", "--hwaccel-decode", "--smooth-fps", "--force", "--preview-only",
                 "--target-size-mb", "--nvenc-preset", "--nvenc-cq", "--chromakey-similarity",
                 "--remove_watermark_width_fraction", "--concat-files", "--batch-overrides"):
        assert flag not in args
    assert args == ["--codec", "h264"]


def test_invalid_nvenc_values_are_dropped_or_clamped():
    assert "--nvenc-preset" not in _args({"nvenc_preset": "p9"})
    assert "--nvenc-cq" not in _args({"nvenc_cq": "abc"})
    args = _args({"nvenc_cq": 99})
    assert args[args.index("--nvenc-cq") + 1] == "51"


def test_target_size_zero_or_blank_is_off():
    assert "--target-size-mb" not in _args({"target_size_mb": 0})
    assert "--target-size-mb" not in _args({"target_size_mb": ""})
    assert "--target-size-mb" not in _args({"target_size_mb": None})


def test_chromakey_similarity_and_blend_only_with_chromakey_and_non_default():
    assert "--chromakey-similarity" not in _args({"chromakey_similarity": 0.4})
    args = _args({"chromakey": True, "chromakey_similarity": 0.2, "chromakey_blend": 0.05})
    assert "--chromakey-similarity" not in args and "--chromakey-blend" not in args
    args = _args({"chromakey": True, "chromakey_similarity": 0.35, "chromakey_blend": 0.1})
    assert args[args.index("--chromakey-similarity") + 1] == "0.35"
    assert args[args.index("--chromakey-blend") + 1] == "0.1"


def test_remove_watermark_fractions_only_with_position_and_non_default():
    assert "--remove_watermark_width_fraction" not in _args({"remove_watermark_width_fraction": 0.3})
    args = _args({"remove_watermark_position": "top-left", "remove_watermark_width_fraction": 0.3, "remove_watermark_height_fraction": 0.12})
    assert args[args.index("--remove_watermark_width_fraction") + 1] == "0.3"
    assert "--remove_watermark_height_fraction" not in args


def test_gap_fields_are_profile_fields_and_have_help():
    from utils.video.video_editor_field_help import FIELD_HELP
    for key in ("hwaccel", "hwaccel_decode", "smooth_fps", "target_size_mb", "force", "preview_only",
                "nvenc_cq", "nvenc_preset", "chromakey_similarity", "chromakey_blend",
                "remove_watermark_width_fraction", "remove_watermark_height_fraction",
                "concat_mode", "concat_transition", "concat_transition_duration", "concat_output_name"):
        assert key in vep.PROFILE_FIELDS
        assert key in FIELD_HELP


def test_gap_fields_present_in_html_and_generic_registry():
    html = served_page_text(client)
    for element_id in ("veHwaccel", "veHwaccelDecode", "veSmoothFps", "veTargetSizeMb", "veForce", "vePreviewOnly",
                       "veNvencCq", "veNvencPreset", "veChromakeySimilarity", "veChromakeyBlend",
                       "veRemoveWatermarkWidthFraction", "veRemoveWatermarkHeightFraction",
                       "veConcatMode", "veConcatTransition", "veConcatTransitionDuration", "veConcatOutputName"):
        assert f'id="{element_id}"' in html, element_id
        assert f'id: "{element_id}"' in html, element_id  # רשום ב-VE_GENERIC_FIELDS
    assert "function _applyGenericVeFields" in html
    assert "function _collectGenericVeFields" in html
    assert "..._collectGenericVeFields()" in html
    assert "_applyGenericVeFields(fields);" in html


def test_preview_command_endpoint_shows_gap_flags():
    resp = client.post("/api/video_editor/preview_command", json={"codec": "av1", "hwaccel": True, "target_size_mb": 8})
    assert "--hwaccel" in resp.json()["command"]
    assert "--target-size-mb 8" in resp.json()["command"]


# --- 38: מצב איחוד קטעים ---

def test_concat_mode_args_follow_queue_order():
    args = _args({"concat_mode": True, "concat_files": ["b.mp4", "a.mp4", "c.mp4"], "concat_transition": "none",
                  "concat_transition_duration": 0.5, "concat_output_name": "my_reel"})
    assert json.loads(args[args.index("--concat-files") + 1]) == ["b.mp4", "a.mp4", "c.mp4"]
    assert args[args.index("--concat-transition") + 1] == "none"
    assert args[args.index("--concat-transition-duration") + 1] == "0.5"
    assert args[args.index("--concat-output-name") + 1] == "my_reel"


def test_concat_mode_defaults_are_not_repeated_on_command_line():
    args = _args({"concat_mode": True, "concat_files": ["a.mp4", "b.mp4"], "concat_transition_duration": 1.0, "concat_output_name": "concat_result"})
    assert "--concat-transition-duration" not in args
    assert "--concat-output-name" not in args
    assert args[args.index("--concat-transition") + 1] == "fade"


def test_concat_mode_with_single_file_emits_nothing_and_run_is_rejected(tmp_path, monkeypatch):
    assert "--concat-files" not in _args({"concat_mode": True, "concat_files": ["a.mp4"]})
    calls = []
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: calls.append(1))
    resp = client.post("/api/run", json={"script": "video/video_editor.py", "folder": str(tmp_path), "concat_mode": True, "concat_files": ["a.mp4"]})
    assert resp.status_code == 400
    assert "איחוד" in resp.json()["error"]
    assert calls == []


def test_concat_files_ignored_when_mode_off():
    assert "--concat-files" not in _args({"concat_mode": False, "concat_files": ["a.mp4", "b.mp4"]})


# --- 39: דריסות פר-קובץ ---

def test_sanitize_batch_overrides_filters_fields_types_and_paths():
    raw = {
        "C:\\clips\\a.mp4": {"watermark_path": " C:\\logo.png ", "watermark_opacity": "0.5", "evil": "rm -rf", "trim_start": -3},
        "b.mp4": {"watermark_position": "nowhere", "watermark_scale": "abc"},
        "c.mp4": {"trim_duration": "4.5", "watermark_scale": 5},
        "d.mp4": "not a dict",
    }
    clean = sanitize_batch_overrides(raw)
    assert clean == {
        "a.mp4": {"watermark_path": "C:\\logo.png", "watermark_opacity": 0.5},  # trim_start שלילי מושמט (גל 3: parse_time_seconds)
        "c.mp4": {"trim_duration": 4.5, "watermark_scale": 1.0},
    }
    assert sanitize_batch_overrides(None) == {}
    assert sanitize_batch_overrides([1, 2]) == {}


def test_batch_override_fields_shared_between_web_and_script():
    import re
    script_src = open(os.path.join(PROJECT_ROOT, "my_scripts", "video", "video_editor.py"), encoding="utf-8").read()
    assert "SHARED_BATCH_OVERRIDE_ALLOWED_FIELDS" in script_src
    assert re.search(r"BATCH_OVERRIDE_ALLOWED_FIELDS = set\(SHARED_BATCH_OVERRIDE_ALLOWED_FIELDS\)", script_src)
    # גל 12 (עריכת קליפ): גם טווחים להסרה ושכבות לקובץ אחד; גל 30: לוגו שנגרר לקליפ אחד
    assert set(BATCH_OVERRIDE_ALLOWED_FIELDS) == {"watermark_path", "watermark_position", "watermark_opacity", "watermark_scale", "trim_start", "trim_duration",
                                                  "remove_ranges", "layers", "watermark_x", "watermark_y"}


def test_sanitize_batch_overrides_keeps_a_whole_logo_center_only():
    assert sanitize_batch_overrides({"a.mp4": {"watermark_x": "0.25", "watermark_y": 1.7}}) == {"a.mp4": {"watermark_x": 0.25, "watermark_y": 1.0}}
    assert sanitize_batch_overrides({"a.mp4": {"watermark_x": 0.5}}) == {}  # בלי y - בלי מרכז
    assert sanitize_batch_overrides({"a.mp4": {"watermark_x": "nan", "watermark_y": 0.5}}) == {}


def test_build_extra_args_batch_overrides_placeholder_without_path_and_real_path_with():
    payload = {"batch_overrides": {"a.mp4": {"trim_start": 2}}}
    args = _args(payload)
    assert args[args.index("--batch-overrides") + 1] == "<batch_overrides.json>"
    args = _args(payload, batch_overrides_path="C:\\tmp\\o.json")
    assert args[args.index("--batch-overrides") + 1] == "C:\\tmp\\o.json"
    assert "--batch-overrides" not in _args({"batch_overrides": {"a.mp4": {"bogus": 1}}})


def test_api_run_writes_sanitized_overrides_file_and_passes_its_path(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: calls.append((a, k)))
    resp = client.post("/api/run", json={
        "script": "video/video_editor.py", "folder": str(tmp_path),
        "batch_overrides": {"a.mp4": {"watermark_scale": 0.3, "junk": 1}},
    })
    assert resp.status_code == 200, resp.text
    extra_args = calls[0][1]["extra_args"]
    path = extra_args[extra_args.index("--batch-overrides") + 1]
    assert os.path.realpath(path).startswith(os.path.realpath(str(tmp_path / "batch_overrides")))
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a.mp4": {"watermark_scale": 0.3}}


def test_queue_overrides_editor_and_concat_ui_present_in_html():
    html = served_page_text(client)
    assert "function enterVeClipMode" in html  # גל 30: ✏️ בשורת התור = מצב עריכת קליפ (במקום עורך הדריסות)
    assert "function _veBatchOverrides" in html
    assert "function onVeConcatModeToggled" in html
    assert "batch_overrides: _veBatchOverrides()" in html
    assert "concat_files:" in html


def test_profile_backup_trash_and_confirm_dialogs_present_in_html():
    html = served_page_text(client)
    for marker in ('id="profileBackupsModalBg"', 'id="profileTrashModalBg"', 'id="veConfirmModalBg"',
                   "function openProfileBackupsDialog", "function openProfileTrashDialog", "function veConfirm",
                   'id="veImageResultModalBg"', "msg.result.preview_path"):
        assert marker in html, marker


# --- e2e: הארגומנטים שהווב בונה למצב איחוד מתקבלים ע"י הסקריפט האמיתי ---

def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    import shutil
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")
def test_web_built_concat_args_run_end_to_end(tmp_path):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    base_dir = PROJECT_ROOT
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    for name, color in (("one.mp4", "red"), ("two.mp4", "blue")):
        subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"color=c={color}:s=160x120:d=2:r=10", "-pix_fmt", "yuv420p", str(input_dir / name)],
                       capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    output_name = f"wave1_concat_{os.getpid()}"
    args = _args({"concat_mode": True, "concat_files": ["one.mp4", "two.mp4"], "concat_transition_duration": 0.5, "concat_output_name": output_name})
    output_path = None
    try:
        result = subprocess.run([sys.executable, os.path.join(base_dir, "my_scripts", "video", "video_editor.py"), "--input_dir", str(input_dir), *args],
                                cwd=base_dir, capture_output=True, text=True, encoding="utf-8", timeout=180, creationflags=NO_WINDOW_FLAGS)
        assert result.returncode == 0, result.stdout + result.stderr
        result_line = next(line for line in result.stdout.splitlines() if line.startswith("RESULT: "))
        parsed = json.loads(result_line[len("RESULT: "):])
        assert parsed["clips_merged"] == 2
        output_path = parsed["output_path"]
        assert os.path.basename(output_path).startswith(output_name)
        assert os.path.exists(output_path)
    finally:
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
