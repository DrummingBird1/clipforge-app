# tests/test_dataviz_web_shims.py
#
# 19.10.2026: src/utils/dataviz_*.py עברו ל-src/dataviz/web/. השמות הישנים נשארו (אזורים אחרים מייבאים אותם - למשל
# thumbnail_generator את draw_title, script_args, וטסטים): כל שם ישן הוא אותו מודול בדיוק, כך ש-monkeypatch דרכו
# משנה את מה שהקוד באמת משתמש בו.
import importlib
import inspect


import pytest

MODULES = ["data", "episodes", "handoff", "kits", "library", "preview", "publish", "remote", "thumbnail"]


@pytest.mark.parametrize("name", MODULES)
def test_the_old_name_is_the_same_module(name):
    new = importlib.import_module(f"dataviz.web.{name}")
    assert importlib.import_module(f"utils.dataviz_{name}") is new
    utils = importlib.import_module("utils")
    assert getattr(utils, f"dataviz_{name}") is new          # from utils import dataviz_<name>


def test_old_imports_and_monkeypatch_reach_the_real_code(monkeypatch):
    from utils.dataviz_thumbnail import draw_title             # thumbnail_generator (הבוט) - חתימה לא משתנה
    assert list(inspect.signature(draw_title).parameters)[:3] == ["image_path", "text", "out_path"]
    from dataviz.web import data as new
    from utils import dataviz_data as old
    monkeypatch.setattr(old, "_stamp", lambda: "patched")
    assert new._stamp() == "patched"
