# tests/web/test_web_app_tray_language.py
#
# 30.10.2026: תפריט אייקון המגש (web/server_startup._run_tray_icon) בשפת ההתקנה - בהתקנה באנגלית הוא היה בעברית. pystray
# מוחלף במודול מזויף שרק אוסף את התוויות, כך שאין אייקון אמיתי.
import json
import sys
import types

from tests.web_app_support import web_app
from entrypoints.web import server_startup


def _labels_for(language, tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"language": language}), encoding="utf-8")
    monkeypatch.setattr(web_app, "CONFIG_FILE", str(config))
    seen = []
    fake = types.SimpleNamespace(
        MenuItem=lambda text, action, default=False: seen.append(text) or text,
        Menu=lambda *items: items,
        Icon=lambda *_a, **_k: types.SimpleNamespace(run=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "pystray", fake)
    server_startup._run_tray_icon(types.SimpleNamespace(should_exit=False), "http://127.0.0.1:8878/")
    return seen


def test_the_tray_menu_is_english_on_an_english_install(tmp_path, monkeypatch):
    assert _labels_for("en", tmp_path, monkeypatch) == ["Open ClipForge", "Stop server"]


def test_the_tray_menu_stays_hebrew_on_a_hebrew_install(tmp_path, monkeypatch):
    assert _labels_for("he", tmp_path, monkeypatch) == ["פתח בדפדפן", "כבה שרת"]
