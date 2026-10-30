# tests/dataviz/test_web_app_dataviz_tool_folder_browser.py
#
# 23.10.2026: בהגדרות הכלליות, תחת "תיקייה לכלי מסוים", שורה "📊 עורך הגרפים" (קודם רק הסטודיו, טיימלאפס והיילייטים).
# ההגדרה בקובץ זמני של הטסט (השרת של הטסטים רץ באותו תהליך).
import pytest

from utils.shared import export_dir

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)


def test_the_graph_editor_gets_a_folder_row_of_its_own(editor_page, settings, tmp_path):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('globalsettings'); }")
    page.wait_for_function("() => document.getElementById('gsExportInfo').innerText.includes('workspace')")
    page.click("text=תיקייה לכלי מסוים")
    own = tmp_path / "dataviz_out"
    own.mkdir()
    page.fill("[data-export-tool=dataviz] input", str(own), timeout=5000)      # קודם: אין שורה
    page.click("[data-export-tool=dataviz] >> text=שמור")
    page.wait_for_function("() => (document.getElementById('toastHost') || {innerText: ''}).innerText.includes('נשמרה')")
    assert export_dir.load_tool_root("dataviz") == str(own) and export_dir.load_root() == ""
