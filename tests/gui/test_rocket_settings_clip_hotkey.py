# tests/gui/test_rocket_settings_clip_hotkey.py
#
# בודק את שדה קיצור המקלדת "Clip That!" (item) שנוסף לטאב Rocket Settings -
# שדה יחיד חדש, אותו דפוס מצומצם כמו test_rocket_settings_recap_period.py.
import json
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


def test_defaults_to_empty_when_no_hotkey_saved(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json")
    try:
        assert comp.clip_hotkey_var.get() == ""
    finally:
        comp.destroy()


def test_restores_a_previously_saved_hotkey(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"clip_hotkey": "ctrl+alt+c"})
    try:
        assert comp.clip_hotkey_var.get() == "ctrl+alt+c"
    finally:
        comp.destroy()


def test_save_persists_the_hotkey_stripped_of_whitespace(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path)
    try:
        comp.clip_hotkey_var.set("  ctrl+alt+z  ")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["clip_hotkey"] == "ctrl+alt+z"
    finally:
        comp.destroy()


def test_save_persists_an_empty_hotkey_when_cleared(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path, saved_settings={"clip_hotkey": "ctrl+alt+c"})
    try:
        comp.clip_hotkey_var.set("")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["clip_hotkey"] == ""
    finally:
        comp.destroy()
