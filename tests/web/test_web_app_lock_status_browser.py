# tests/web/test_web_app_lock_status_browser.py
#
# 30.10.2026: התג בכותרת ("🔒 מקומי · 127.0.0.1") הופך ל"רינדור אחר תפוס כרגע (PID ...)" כשמנעול הרינדור תפוס, וחוזר
# להודעה הכללית כשהוא משתחרר - קודם loadLockStatus יצא בלי לגעת בתג, וההודעה נשארה עד רענון של הדף (נמצא ב-GIF ההדגמה).
# /api/lock_status מזויף בדף (fetch עטוף - page.route לא תופס בקשות של ה-service worker).
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

FAKE = """(locked) => {
  window.__lock = locked;
  if (!window.__realFetch) window.__realFetch = window.fetch;
  window.fetch = (url, options) => String(url) === '/api/lock_status'
    ? Promise.resolve(new Response(JSON.stringify(window.__lock ? {locked: true, pid: 4242, age_seconds: 3, queue_length: 0, is_stale: false}
                                                                 : {locked: false}), {headers: {'Content-Type': 'application/json'}}))
    : window.__realFetch(url, options);
}"""
TEXT = "() => document.getElementById('lockStatus').textContent"


def test_the_lock_badge_goes_back_to_normal_when_the_render_ends(editor_page):
    page = editor_page
    idle = page.evaluate(TEXT)
    assert "127.0.0.1" in idle
    page.evaluate(FAKE, True)
    page.evaluate("() => loadLockStatus()")
    page.wait_for_function("() => document.getElementById('lockStatus').textContent.includes('PID 4242')")
    page.evaluate("() => { window.__lock = false; }")
    page.evaluate("() => loadLockStatus()")
    page.wait_for_function("(idle) => document.getElementById('lockStatus').textContent === idle", arg=idle)   # קודם: נשאר PID
