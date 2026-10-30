# tests/gui/test_rocket_settings_capture_watch_dir.py
#
# בודק את שדה "תיקיית מעקב" (item: אינטגרציה עם תוכנת לכידה נוספת -
# Streamlabs/ShadowPlay) שנוסף לטאב Rocket Settings - אותו דפוס מצומצם כמו
# test_rocket_settings_voice_channel.py.
import json
import os
from unittest.mock import MagicMock


import pytest

import ui.rocket_settings_tab as rocket_settings_tab_module
from ui.rocket_settings_tab import RocketSettingsTabComponent


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    monkeypatch.setattr(rocket_settings_tab_module, "_DND_AVAILABLE", False)


def _make_component(shared_tk_root, monkeypatch, settings_path, saved_settings=None):
    monkeypatch.setattr(rocket_settings_tab_module, "SETTINGS_FILE_PATH", str(settings_path))
    if saved_settings is not None:
        settings_path.write_text(json.dumps(saved_settings), encoding="utf-8")
    app = MagicMock()
    return RocketSettingsTabComponent(shared_tk_root, app)


def test_defaults_to_empty_when_no_watch_dir_saved(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json")
    try:
        assert comp.capture_watch_dir_var.get() == ""
    finally:
        comp.destroy()


def test_restores_a_previously_saved_watch_dir(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"capture_watch_dir": "D:\\Streamlabs Output"})
    try:
        assert comp.capture_watch_dir_var.get() == "D:\\Streamlabs Output"
    finally:
        comp.destroy()


def test_save_persists_the_watch_dir_stripped_of_whitespace(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path)
    try:
        comp.capture_watch_dir_var.set("  D:\\ShadowPlay  ")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["capture_watch_dir"] == "D:\\ShadowPlay"
    finally:
        comp.destroy()


def test_save_persists_an_empty_watch_dir_when_cleared(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path, saved_settings={"capture_watch_dir": "D:\\Old"})
    try:
        comp.capture_watch_dir_var.set("")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["capture_watch_dir"] == ""
    finally:
        comp.destroy()


def test_browse_capture_watch_dir_sets_selected_folder(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json")
    try:
        monkeypatch.setattr(rocket_settings_tab_module.filedialog, "askdirectory", lambda **kw: str(tmp_path))
        comp.browse_capture_watch_dir()
        assert comp.capture_watch_dir_var.get() == os.path.normpath(str(tmp_path))
    finally:
        comp.destroy()
