# tests/gui/test_dashboard_backup_mirror.py
#
# בודק את _run_backup_mirror אחרי הרחבתו משורש "exports" יחיד לשלוש תיקיות-
# אוריינטציה נפרדות (vertical/horizontal/square - item: reorganize workspace
# by orientation) - בעיקר את הדילוג השקט על תיקייה שעדיין לא נוצרה אצל
# המשתמש הזה (square/ במיוחד, כי enable_square_export כבוי כברירת מחדל),
# כדי שזה לא ייספר בטעות כ"גיבוי נכשל".
import os


import ui.dashboard as dashboard_module
import utils.shared.backup_sync as backup_sync_module
from ui.dashboard import DashboardTabComponent
from utils.shared.state import state


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def _make_comp(shared_tk_root):
    return DashboardTabComponent(shared_tk_root, lambda color, text: None)


def test_backup_mirror_skips_orientation_dirs_that_do_not_exist_yet(shared_tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_module, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    (tmp_path / "workspace" / "vertical").mkdir(parents=True)
    (tmp_path / "workspace" / "horizontal").mkdir(parents=True)
    # workspace/square/ בכוונה לא נוצרת - מדמה משתמש עם enable_square_export כבוי.
    monkeypatch.setattr(dashboard_module.threading, "Thread", _ImmediateThread)
    backup_dest = tmp_path / "backup_dest"
    monkeypatch.setattr(state, "backup_folder_path", str(backup_dest))

    calls = []

    def _fake_mirror(src, dst):
        calls.append(src)
        return (2, None)

    # _run_backup_mirror עושה "from utils.shared.backup_sync import mirror_folder"
    # מקומי בתוך הפונקציה עצמה - מונקיפאץ' על dashboard_module לא היה משפיע
    # (הפונקציה מייבאת מחדש בכל קריאה), צריך לתקוף את utils.shared.backup_sync עצמו.
    monkeypatch.setattr(backup_sync_module, "mirror_folder", _fake_mirror)

    comp = _make_comp(shared_tk_root)
    try:
        comp._run_backup_mirror()
        assert sorted(os.path.basename(c) for c in calls) == ["horizontal", "vertical"]
    finally:
        comp.destroy()


def test_backup_mirror_shows_combined_copied_count_across_orientation_dirs(shared_tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_module, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    (tmp_path / "workspace" / "vertical").mkdir(parents=True)
    (tmp_path / "workspace" / "horizontal").mkdir(parents=True)
    monkeypatch.setattr(dashboard_module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(state, "backup_folder_path", str(tmp_path / "backup_dest"))
    monkeypatch.setattr(backup_sync_module, "mirror_folder", lambda src, dst: (3, None))

    comp = _make_comp(shared_tk_root)
    try:
        comp._run_backup_mirror()
        comp._dispatcher.drain()
        assert "6" in comp.info_label.cget("text")  # 3 + 3 מהשתי התיקיות הקיימות
    finally:
        comp.destroy()


def test_backup_mirror_reports_combined_errors(shared_tk_root, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_module, "WORKSPACE_DIR", str(tmp_path / "workspace"))
    (tmp_path / "workspace" / "vertical").mkdir(parents=True)
    (tmp_path / "workspace" / "horizontal").mkdir(parents=True)
    monkeypatch.setattr(dashboard_module.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(state, "backup_folder_path", str(tmp_path / "backup_dest"))
    monkeypatch.setattr(backup_sync_module, "mirror_folder", lambda src, dst: (0, "דיסק מלא"))

    comp = _make_comp(shared_tk_root)
    try:
        comp._run_backup_mirror()
        comp._dispatcher.drain()
        assert "דיסק מלא" in comp.info_label.cget("text")
    finally:
        comp.destroy()
