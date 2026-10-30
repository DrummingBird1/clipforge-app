# tests/gui/test_rocket_settings_nvenc_concurrency.py
#
# item: מודעות למגבלת סשנים אמיתית של NVENC - שדה "רינדורים מקבילים" (חדש,
# לא היה חשוף בשום ממשק עד היום, רק נקרא מ-rocket_settings.json ע"י
# rocket_shorts_publisher.py) + כפתור "גלה מגבלה בפועל" בטאב Rocket Settings.
# אותו דפוס מצומצם כמו test_rocket_settings_voice_channel.py.
import json
from unittest.mock import MagicMock


import pytest

import ui.rocket_settings_tab as rocket_settings_tab_module
from ui.rocket_settings_tab import RocketSettingsTabComponent


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    monkeypatch.setattr(rocket_settings_tab_module, "_DND_AVAILABLE", False)


def _make_component(shared_tk_root, monkeypatch, settings_path, saved_settings=None):
    monkeypatch.setattr(rocket_settings_tab_module, "SETTINGS_FILE_PATH", str(settings_path))
    if saved_settings is not None:
        settings_path.write_text(json.dumps(saved_settings), encoding="utf-8")
    app = MagicMock()
    app._main_dispatcher.call_soon = lambda fn: fn()  # מריץ מיידית, בלי event loop אמיתי
    return RocketSettingsTabComponent(shared_tk_root, app)


def test_defaults_to_1_when_no_value_saved(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json")
    try:
        assert comp.max_concurrent_renders_var.get() == "1"
    finally:
        comp.destroy()


def test_restores_a_previously_saved_value(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"max_concurrent_renders": 3})
    try:
        assert comp.max_concurrent_renders_var.get() == "3"
    finally:
        comp.destroy()


def test_save_persists_a_valid_value(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path)
    try:
        comp.max_concurrent_renders_var.set("4")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["max_concurrent_renders"] == 4
    finally:
        comp.destroy()


def test_save_clamps_zero_or_negative_to_1(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path)
    try:
        comp.max_concurrent_renders_var.set("-2")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["max_concurrent_renders"] == 1
        assert comp.max_concurrent_renders_var.get() == "1"
    finally:
        comp.destroy()


def test_save_defaults_non_numeric_value_to_1(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path)
    try:
        comp.max_concurrent_renders_var.set("abc")
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["max_concurrent_renders"] == 1
    finally:
        comp.destroy()


# --- probe_nvenc_limit (item: בדיקה אמיתית, לא ניחוש) ---

def test_probe_applies_detected_value_to_the_field(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(rocket_settings_tab_module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(rocket_settings_tab_module, "probe_max_concurrent_nvenc_sessions", lambda *a, **kw: 3)
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json")
    try:
        comp.probe_nvenc_limit()
        assert comp.max_concurrent_renders_var.get() == "3"
        assert "3" in comp.nvenc_probe_status_label.cget("text")
    finally:
        comp.destroy()


def test_probe_leaves_field_unchanged_when_nvenc_not_detected(tmp_path, monkeypatch, shared_tk_root):
    monkeypatch.setattr(rocket_settings_tab_module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(rocket_settings_tab_module, "probe_max_concurrent_nvenc_sessions", lambda *a, **kw: 0)
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"max_concurrent_renders": 2})
    try:
        comp.probe_nvenc_limit()
        assert comp.max_concurrent_renders_var.get() == "2"  # לא נגעו בו - שום NVENC לא זוהה
        assert "לא זוהה" in comp.nvenc_probe_status_label.cget("text")
    finally:
        comp.destroy()
