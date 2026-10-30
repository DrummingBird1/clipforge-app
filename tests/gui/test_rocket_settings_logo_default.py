# tests/gui/test_rocket_settings_logo_default.py
#
# שדה הלוגו בטאב Rocket Settings (GUI שולחני): ברירת המחדל הייתה assets/overlay.png, שכבר לא בריפו
# (16.10.2026) - עכשיו ריקה, כמו ב-rocket_shorts_publisher.py וב-/api/rocket_settings.
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
    return RocketSettingsTabComponent(shared_tk_root, MagicMock())


def test_logo_field_is_empty_when_no_logo_was_chosen(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"input_dir": "D:/Clips"})
    try:
        assert comp.overlay_path_var.get() == ""
    finally:
        comp.destroy()


def test_logo_field_shows_the_saved_logo(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"watermark_image_path": "D:/logo.png"})
    try:
        assert comp.overlay_path_var.get() == "D:/logo.png"
    finally:
        comp.destroy()
