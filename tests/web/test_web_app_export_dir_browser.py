# tests/web/test_web_app_export_dir_browser.py
#
# 23.10.2026: "📂 תיקיית ייצוא" בהגדרות הכלליות - שמירה של תיקייה, הצעה ליצור תיקייה שלא קיימת, וחזרה לברירת המחדל.
# ההגדרה בקובץ זמני של הטסט (השרת של הטסטים רץ באותו תהליך).
import os

import pytest

from utils.shared import export_dir

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)


def _save(page, value):
    page.fill("#gsExportDir", value)
    page.click("#gsExportSave")


def test_choose_create_and_reset_the_export_folder(editor_page, settings, tmp_path):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('globalsettings'); }")
    page.wait_for_function("() => document.getElementById('gsExportInfo').innerText.includes('workspace')")

    target = tmp_path / "new" / "exports"
    _save(page, str(target))
    page.wait_for_selector("#veConfirmModalBg.show")      # "התיקייה לא קיימת. ליצור אותה?"
    page.click("#veConfirmOkBtn")
    page.wait_for_function("(p) => document.getElementById('gsExportInfo').innerText.includes(p)", arg=str(target))
    assert target.is_dir() and export_dir.load_root() == str(target)

    page.click("#gsExportReset")
    page.wait_for_function("() => document.getElementById('gsExportDir').value === ''")
    page.wait_for_function("() => !document.getElementById('gsExportInfo').innerText.includes('new')")
    assert export_dir.load_root() == "" and os.path.isdir(target)   # חזרה לברירת המחדל לא מוחקת כלום


def test_a_folder_for_one_tool(editor_page, settings, tmp_path):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('globalsettings'); }")
    page.wait_for_function("() => document.getElementById('gsExportInfo').innerText.includes('workspace')")
    page.click("text=תיקייה לכלי מסוים")
    studio = tmp_path / "studio_out"
    studio.mkdir()
    page.fill("[data-export-tool=studio] input", str(studio))
    page.click("[data-export-tool=studio] >> text=שמור")
    page.wait_for_function("() => (document.getElementById('toastHost') || {innerText: ''}).innerText.includes('נשמרה')")
    assert export_dir.load_tool_root("studio") == str(studio) and export_dir.load_root() == ""
