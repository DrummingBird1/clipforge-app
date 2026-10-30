# tests/web/test_web_notifications_lazy.py
#
# 23.10.2026: מרכז ההתראות - בדף הראשי רק הכפתור והמונה; הרשימה (JS, CSS ו-HTML) נטענת בלחיצה.
from entrypoints.web import frontend_assembly as fa


def test_only_the_button_and_the_count_are_in_the_main_page():
    main_js, lazy = fa.bundle("js"), fa.lazy_bundle("notifications")
    for name in ("toggleNotificationPanel", "loadNotifications", "openNotificationTarget"):
        assert f"function {name}(" in lazy and f"function {name}(" not in main_js, name
    for name in ("refreshNotificationBadge", "toggleNotificationCenter"):
        assert f"function {name}(" in main_js, name
    assert 'uiLoadLazy("notifications")' in main_js and "pollWhenVisible(refreshNotificationBadge" in main_js
    assert ".notif-item" in lazy and ".notif-item" not in fa.bundle("css") and ".notif-count" in fa.bundle("css")


def test_the_list_html_arrives_with_its_code():
    page = fa.assemble_page()
    html = "".join(fa.lazy_html_fragments("notifications"))
    assert 'id="notifCenter"' in html and 'id="notifList"' in html and 'id="notifList"' not in page
    assert 'id="notifCenterBtn"' in page and 'id="notifBadge"' in page and 'data-lazy-html="notifications"' in page
