# tests/web/test_web_phone_lazy.py
#
# 23.10.2026: מסך "📱 בטלפון" נטען רק כשפותחים אותו - JS, CSS ו-HTML. בדף הראשי רק כפתור הניווט, שורת switchTab והקישור
# הישיר למסך (?screen=).
from entrypoints.web import frontend_assembly as fa


def test_the_phone_screen_is_not_in_the_main_page():
    main_js, lazy = fa.bundle("js"), fa.lazy_bundle("phone")
    for name in ("loadPhoneScreen", "refreshPhoneScreen", "phoneStopRun", "phoneDecide", "phoneRerun", "phoneToggleQueue"):
        assert f"function {name}(" in lazy and f"function {name}(" not in main_js, name
    assert 'uiLoadLazy("phone")' in main_js and 'get("screen")' in main_js
    assert ".phone-btn" in lazy and ".phone-btn" not in fa.bundle("css")


def test_its_html_arrives_with_the_screen():
    page = fa.assemble_page()
    html = "".join(fa.lazy_html_fragments("phone"))
    for element in ('id="phoneNow"', 'id="phoneQueue"', 'id="phoneApprovals"', 'id="phoneRuns"', 'id="phoneStopBtn"'):
        assert element in html and element not in page, element
    assert 'data-tab="phone"' in page and 'data-lazy-html="phone"' in page
