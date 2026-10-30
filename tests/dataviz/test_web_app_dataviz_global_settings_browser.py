# tests/dataviz/test_web_app_dataviz_global_settings_browser.py
#
# 21.10.2026 (סבב הפישוט, פריט 7): "📊 הגדרות עורך הגרפים" גם ב"🌐 הגדרות כלליות" - טוען את ה-bundles של עורך הגרפים לפי
# דרישה ופותח את אותו חלון (התראות, תיקייה במעקב, העדפות) גלוי, למרות שמסך עורך הגרפים מוסתר. ההיכרות של עורך הגרפים לא
# מסומנת כנראתה מכאן - היא מחכה למסך עצמו.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות"}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return data


def test_the_settings_open_from_the_global_settings_screen(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('globalsettings'); }")
    page.click("#gsDatavizSettingsBtn")
    page.wait_for_selector("#dvzSettings[open]")
    assert page.is_visible("#dvzNotifyUrl") and page.is_visible("#dvzWatchRoot")
    page.wait_for_function("() => document.getElementById('dvzNotifyState').textContent.length > 0")
    assert "לא מוגדר" in page.inner_text("#dvzNotifyState")
    page.click("#dvzSettings >> text=✕ סגור")
    assert page.evaluate("() => localStorage.getItem('dvzOnboardSeen')") is None and page.locator("#dvzOnboard").count() == 0
