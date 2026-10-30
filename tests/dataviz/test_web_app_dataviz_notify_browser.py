# tests/dataviz/test_web_app_dataviz_notify_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "🔔 התראות" - שמירת webhook (למאגר סודות מזויף), הדיאלוג מראה רק "מוגדר" וסוף הכתובת,
# ו"בטל התראות" מוחק. בלי Discord אמיתי ובלי Credential Manager אמיתי.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode
from utils.shared import secrets_vault

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

URL = "https://discord.com/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyzABCDEF"


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "התראות"}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    store = {}
    monkeypatch.setattr(secrets_vault, "get_secret", lambda key, default="": store.get(key, default))
    monkeypatch.setattr(secrets_vault, "set_secret", lambda key, value: store.__setitem__(key, value))
    monkeypatch.setattr(secrets_vault, "delete_secret", lambda key: store.pop(key, None))
    return store


def test_save_and_clear_the_webhook(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolSettings")
    page.wait_for_function("() => document.getElementById('dvzNotifyState').textContent.length > 0")
    assert page.is_disabled("#dvzNotifyTestBtn")
    page.fill("#dvzNotifyUrl", URL)
    page.click("#dvzNotifySaveBtn")
    page.wait_for_function("() => document.getElementById('dvzNotifyState').textContent.includes('ABCDEF')")
    assert screen["DATAVIZ_DISCORD_WEBHOOK"] == URL and page.input_value("#dvzNotifyUrl") == ""
    assert "abcdefghijklmnop" not in page.inner_text("#dvzSettings")
    page.click("#dvzNotifyClearBtn")
    page.wait_for_function("() => document.getElementById('dvzNotifyTestBtn').disabled")
    assert screen == {}
