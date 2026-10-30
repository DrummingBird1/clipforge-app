# tests/web/test_web_app_notifications_browser.py
#
# 23.10.2026: מרכז ההתראות בדפדפן - המונה בדף הראשי, הרשימה נטענת בלחיצה, פתיחה מסמנת "נקרא", לחיצה על התראה עוברת
# למסך שלה, ו-Escape סוגר. ה-DB זמני (אותו תהליך כמו השרת של הטסטים).
import pytest

from utils.shared import notification_log

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]


def test_the_notification_center_counts_lists_and_opens_a_screen(editor_page, tmp_path, monkeypatch):
    monkeypatch.setattr(notification_log, "DB_PATH", str(tmp_path / "notifications.db"))
    notification_log.add("run", "✅ הסתיים: video_editor.py", body="משך: 12 שניות", level="ok", target="scripts")
    notification_log.add("bot", "🤖 הבוט נעצר אחרי קריסות חוזרות", level="bad", target="bot")
    page = editor_page
    page.evaluate("() => { closeVeEditor(); refreshNotificationBadge(); }")   # הסטודיו במסך מלא מכסה את הסרגל העליון
    page.wait_for_function("() => document.getElementById('notifBadge').textContent === '2' && !document.getElementById('notifBadge').hidden")
    assert not page.evaluate("() => !!(window.__uiLazyLoaded || {}).notifications")
    template = "() => document.querySelectorAll('template[data-lazy-html=\"notifications\"]').length"
    assert page.evaluate(template) == 1

    page.click("#notifCenterBtn")
    page.wait_for_function("() => document.querySelectorAll('#notifList .notif-item').length === 2")
    assert page.evaluate(template) == 0
    assert page.get_attribute("#notifCenterBtn", "aria-expanded") == "true"
    rows = page.locator("#notifList .notif-item")
    assert "הבוט נעצר" in rows.nth(0).inner_text() and "משך: 12 שניות" in rows.nth(1).inner_text()
    assert page.evaluate("() => [...document.querySelectorAll('#notifList .notif-item')].every(r => r.classList.contains('unread'))")
    page.wait_for_function("() => document.getElementById('notifBadge').hidden")
    assert notification_log.unread()["unread"] == 0

    rows.nth(0).click()
    page.wait_for_function("() => document.getElementById('notifCenter').hidden")
    page.wait_for_function("() => !document.querySelector('[data-tab-panel=\"bot\"]').hidden")

    notification_log.add("run", "❌ נכשל: a.py", level="bad", target="scripts")
    page.click("#notifCenterBtn")
    page.wait_for_function("() => document.querySelectorAll('#notifList .notif-item').length === 3")
    assert page.evaluate("() => document.querySelectorAll('#notifList .notif-item.unread').length") == 1
    page.keyboard.press("Escape")
    page.wait_for_function("() => document.getElementById('notifCenter').hidden")
    assert page.evaluate("() => document.activeElement.id") == "notifCenterBtn"
