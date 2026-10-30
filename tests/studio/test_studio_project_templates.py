# tests/studio/test_studio_project_templates.py
#
# 24.10.2026, מנה 8 - החלטת המשתמש מסיור השימושיות בסטודיו: "שמור את הפרויקט כתבנית" הוא סגנון מורחב - ההגדרות, השכבות,
# המיתוג והיעדים, בלי הקבצים של התיקייה. נשמר כסגנון רגיל ב-video_editor_profiles.json ומסומן kind=template בקובץ המטא; הסכימה
# רק נוספת, וסגנונות בפורמט הישן נטענים בדיוק כמו קודם. הקבצים מופנים ל-tmp_path - לא data/ האמיתית.
import json

import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video import video_editor_profiles as vep

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)

LAYER = {"type": "text", "text": "GG", "x": 0.5, "y": 0.2}
# סגנון כמו שהיה שמור לפני המנה: שם -> הגדרות, חלק מהשדות חסרים, ובמטא אין kind
OLD_PROFILES = {"Rocket League": {"codec": "hevc", "vertical": True, "watermark_path": "C:\\logo.png", "queue_files": ["a.mp4"]},
                "Minecraft": {"codec": "h264", "target_seconds": 45}}
OLD_META = {"Rocket League": {"schema_version": 2, "run_count": 7, "tags": ["rl"], "color": "blue"}}


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "video_editor_profiles.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "video_editor_profile_meta.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "video_editor_profile_history.json"))
    monkeypatch.setattr(web_app.limiter, "enabled", False)
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **k: None)


def _write_old_format(tmp_path):
    (tmp_path / "video_editor_profiles.json").write_text(json.dumps(OLD_PROFILES, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp_path / "video_editor_profile_meta.json").write_text(json.dumps(OLD_META, ensure_ascii=False, indent=2), encoding="utf-8")


def test_a_template_keeps_the_settings_layers_brand_and_targets_without_the_files():
    vep.save_template("Gameplay", {"codec": "hevc", "layers": [LAYER], "targets": ["shorts", "tiktok"], "brand_kit": "RL",
                                   "queue_files": ["clip_1.mp4", "clip_2.mp4"]})
    saved = vep.load_profiles()["Gameplay"]
    assert saved["codec"] == "hevc" and saved["layers"] == [LAYER] and saved["targets"] == ["shorts", "tiktok"]
    assert saved["brand_kit"] == "RL" and saved["queue_files"] is None
    assert set(saved) == set(vep.PROFILE_FIELDS)                          # אותו פורמט כמו כל סגנון
    assert vep.load_profile_meta("Gameplay")["kind"] == "template"
    vep.save_profile("Plain", {"codec": "h264", "queue_files": ["clip_1.mp4"]})
    assert vep.load_profile_meta("Plain")["kind"] == "style"              # סגנון רגיל - כמו קודם, עם התור
    assert vep.load_profiles()["Plain"]["queue_files"] == ["clip_1.mp4"]


def test_old_format_styles_load_exactly_as_before(tmp_path):
    _write_old_format(tmp_path)
    assert vep.load_profiles() == OLD_PROFILES
    meta = vep.load_all_profile_meta()
    assert meta["Rocket League"]["kind"] == "style" and meta["Minecraft"]["kind"] == "style"
    assert meta["Rocket League"]["run_count"] == 7 and meta["Rocket League"]["tags"] == ["rl"]
    vep.save_template("Gameplay", {"codec": "hevc", "layers": [LAYER]})
    on_disk = json.loads((tmp_path / "video_editor_profiles.json").read_text(encoding="utf-8"))
    assert {name: on_disk[name] for name in OLD_PROFILES} == OLD_PROFILES   # הסגנונות הישנים לא נכתבו מחדש בפורמט אחר
    meta_on_disk = json.loads((tmp_path / "video_editor_profile_meta.json").read_text(encoding="utf-8"))
    assert meta_on_disk["Rocket League"] == OLD_META["Rocket League"]
    assert vep.load_all_profile_meta()["Rocket League"]["kind"] == "style"


def test_the_api_saves_a_template_and_the_meta_says_so(tmp_path):
    _write_old_format(tmp_path)
    resp = client.post("/api/video_editor_profiles", json={"name": "Gameplay", "kind": "template",
                                                           "settings": {"codec": "hevc", "targets": ["shorts"], "queue_files": ["x.mp4"]}})
    assert resp.status_code == 200 and resp.json()["settings"]["queue_files"] is None
    meta = client.get("/api/video_editor_profiles_meta_all").json()["meta"]
    assert meta["Gameplay"]["kind"] == "template" and meta["Rocket League"]["kind"] == "style"
    profiles = client.get("/api/video_editor_profiles").json()
    assert profiles["Gameplay"]["targets"] == ["shorts"] and profiles["Rocket League"]["codec"] == "hevc"
    resp = client.post("/api/video_editor_profiles", json={"name": "Style", "settings": {"codec": "h264", "queue_files": ["x.mp4"]}})
    assert resp.json()["settings"]["queue_files"] == ["x.mp4"] and vep.load_profile_meta("Style")["kind"] == "style"
