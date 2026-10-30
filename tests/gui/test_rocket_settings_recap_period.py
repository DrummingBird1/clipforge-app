# tests/gui/test_rocket_settings_recap_period.py
#
# בודק את בורר תקופת הריקאפ החדש (week/month/year, item) שנוסף לטאב
# Rocket Settings - שדה יחיד חדש, לא הטאב כולו (אין עדיין test file קיים
# לטאב הזה). MagicMock ל-app - הרכיב רק קורא play_ui_sound()/log_message()
# עליו, אין צורך בחלון LauncherApp אמיתי.
import json
from unittest.mock import MagicMock


import pytest

import ui.rocket_settings_tab as rocket_settings_tab_module
from ui.rocket_settings_tab import RocketSettingsTabComponent


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    # drop_target_register() דורש TkinterDnD._require() על ה-root הספציפי
    # (LauncherApp.__init__ עושה את זה בפועל) - shared_tk_root של הטסטים הוא
    # ctk.CTk() רגיל בלי זה, אותו דפוס בדיוק כמו tests/gui/test_settings_tab.py.
    monkeypatch.setattr(rocket_settings_tab_module, "_DND_AVAILABLE", False)


def _make_component(shared_tk_root, monkeypatch, settings_path, saved_settings=None):
    monkeypatch.setattr(rocket_settings_tab_module, "SETTINGS_FILE_PATH", str(settings_path))
    if saved_settings is not None:
        settings_path.write_text(json.dumps(saved_settings), encoding="utf-8")
    app = MagicMock()
    return RocketSettingsTabComponent(shared_tk_root, app)


def test_defaults_to_weekly_when_no_period_saved(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json")
    try:
        assert comp.recap_period_var.get() == rocket_settings_tab_module.RECAP_PERIOD_VALUE_TO_DISPLAY["week"]
    finally:
        comp.destroy()


def test_restores_a_previously_saved_period(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"weekly_recap_period": "year"})
    try:
        assert comp.recap_period_var.get() == rocket_settings_tab_module.RECAP_PERIOD_VALUE_TO_DISPLAY["year"]
    finally:
        comp.destroy()


def test_unknown_saved_period_falls_back_to_weekly_display(tmp_path, monkeypatch, shared_tk_root):
    comp = _make_component(shared_tk_root, monkeypatch, tmp_path / "rocket_settings.json", saved_settings={"weekly_recap_period": "fortnight"})
    try:
        assert comp.recap_period_var.get() == rocket_settings_tab_module.RECAP_PERIOD_VALUE_TO_DISPLAY["week"]
    finally:
        comp.destroy()


def test_save_persists_the_selected_period(tmp_path, monkeypatch, shared_tk_root):
    settings_path = tmp_path / "rocket_settings.json"
    comp = _make_component(shared_tk_root, monkeypatch, settings_path)
    try:
        comp.recap_period_var.set(rocket_settings_tab_module.RECAP_PERIOD_VALUE_TO_DISPLAY["month"])
        comp.save_rocket_settings()

        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["weekly_recap_period"] == "month"
    finally:
        comp.destroy()
