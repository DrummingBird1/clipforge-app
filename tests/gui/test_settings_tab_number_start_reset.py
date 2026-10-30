# tests/gui/test_settings_tab_number_start_reset.py
#
# item: מספור סרטונים - עריכת שדה "מספר התחלתי" בהגדרות היא "שינוי ידני"
# מפורש שאמור לאפס בפועל את data/video_editor_counter.txt *עכשיו* (לא רק
# לשלוח --number-start לריצה הבאה, שם זה מתעלם כליל אם קובץ המונה כבר קיים -
# ראו utils/video/video_editor_counter.py). בלי זה, שדה שכבר נראה "עודכן" בהגדרות
# היה נשאר חסר-אפקט על המונה האמיתי, בדיוק כמו הבאג שהמשתמש דיווח עליו.


import pytest

import ui.settings_tab as settings_tab_module
from ui.settings_tab import SettingsTabComponent
from utils.shared.state import state


@pytest.fixture(autouse=True)
def _disable_dnd(monkeypatch):
    monkeypatch.setattr(settings_tab_module, "_DND_AVAILABLE", False)


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    monkeypatch.setattr(state, "save_config", lambda: None)
    monkeypatch.setattr(state, "video_editor_number_start", "")


def _make_comp(shared_tk_root):
    return SettingsTabComponent(shared_tk_root)


def test_editing_number_start_to_a_new_value_resets_the_real_counter(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    state.video_editor_number_start = "571"
    comp.number_start_var.set("571")

    reset_calls = []
    monkeypatch.setattr(settings_tab_module, "save_video_editor_counter", lambda value: reset_calls.append(value))

    comp.number_start_var.set("900")
    comp._on_number_start_changed()

    assert reset_calls == [900]
    assert state.video_editor_number_start == "900"


def test_focus_out_without_changing_the_value_does_not_reset_the_counter(shared_tk_root, monkeypatch):
    # פוקוס-יציאה מהשדה קורה גם בלי שהמשתמש הקליד שינוי בפועל - לא אמור לאפס
    # את המונה בכל פעם, אחרת גרירה מקרית לתוך השדה תחזיר אותו אחורה בטעות.
    comp = _make_comp(shared_tk_root)
    state.video_editor_number_start = "571"
    comp.number_start_var.set("571")

    reset_calls = []
    monkeypatch.setattr(settings_tab_module, "save_video_editor_counter", lambda value: reset_calls.append(value))

    comp._on_number_start_changed()  # שום הקלדה לא קרתה - הערך זהה למה שהיה

    assert reset_calls == []


def test_clearing_the_field_does_not_reset_the_counter(shared_tk_root, monkeypatch):
    comp = _make_comp(shared_tk_root)
    state.video_editor_number_start = "571"
    comp.number_start_var.set("571")

    reset_calls = []
    monkeypatch.setattr(settings_tab_module, "save_video_editor_counter", lambda value: reset_calls.append(value))

    comp.number_start_var.set("")
    comp._on_number_start_changed()

    assert reset_calls == []
    assert state.video_editor_number_start == ""
