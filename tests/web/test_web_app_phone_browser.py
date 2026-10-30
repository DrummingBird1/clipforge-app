# tests/web/test_web_app_phone_browser.py
#
# 23.10.2026: מסך "📱 בטלפון" בדפדפן. הנתונים מזויפים בדף (fetch עטוף - page.route לא תופס בקשות שה-service worker
# מטפל בהן), וכל POST נרשם במקום לרוץ: שום ריצה, עצירה או אישור אמיתיים.
import pytest

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]

FAKE = """(running) => {
  window.__posts = [];
  const queue = {paused: false, resume_at: null, pending: [{id: 7, label: 'טיול בצפון', folder: 'D:/Trip'}],
                 running: running ? {script: 'video_editor.py', run_id: 'r9', started_at: Date.now() / 1000 - 90} : null};
  const approvals = [{id: 3, path: 'C:/clips/a.mp4', name: 'a.mp4', game: 'RL', created_at: '2026-10-23'}];
  const runs = {runs: [{id: 'r1', folder: 'D:/Videos/Trip', status: 'success', started_at: '2026-10-23T10:00:00', profile_name: 'Shorts'}]};
  const realFetch = window.fetch;
  const json = (body) => Promise.resolve(new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}}));
  window.fetch = (url, options = {}) => {
    const u = String(url);
    if ((options.method || 'GET') === 'POST' && /^\\/api\\/(stop|pause|resume|render_queue\\/pause|approvals|video_editor\\/runs)/.test(u)) {
      window.__posts.push([u, JSON.parse(options.body || '{}')]);
      return json({ok: true});
    }
    if (u === '/api/render_queue') return json(queue);
    if (u === '/api/approvals') return json(approvals);
    if (u === '/api/video_editor/runs') return json(runs);
    return realFetch(url, options);
  };
}"""


def _open(page, running):
    page.evaluate("() => closeVeEditor()")
    page.evaluate(FAKE, running)
    page.evaluate("() => switchTab('phone')")
    page.wait_for_function("() => document.querySelectorAll('#phoneRuns .phone-run').length === 1")


def _confirm(page):
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => !document.getElementById('veConfirmModalBg').classList.contains('show')")


def test_a_running_render_can_be_followed_and_stopped(editor_page):
    page = editor_page
    _open(page, True)
    assert "video_editor.py" in page.inner_text("#phoneNow")
    assert page.is_enabled("#phoneStopBtn") and page.is_enabled("#phonePauseBtn")
    assert page.is_disabled("#phoneRuns .phone-btn")              # בזמן ריצה אין "הרץ שוב"
    page.evaluate("() => document.dispatchEvent(new CustomEvent('cf-progress', {detail: {pct: 42.4, eta: '3 דק׳'}}))")
    assert page.evaluate("() => document.getElementById('phoneProgress').value") == 42.4
    assert page.inner_text("#phoneProgressText") == "\u206642%\u2069 · 3 דק׳"   # LTR isolate: "42%" ולא "%42"
    page.click("#phonePauseBtn")
    page.wait_for_function("() => window.__posts.length === 1")
    page.click("#phoneStopBtn")
    _confirm(page)
    page.wait_for_function("() => window.__posts.length === 2")
    assert [post[0] for post in page.evaluate("() => window.__posts")] == ["/api/pause", "/api/stop"]


def test_the_queue_approvals_and_running_again(editor_page):
    page = editor_page
    _open(page, False)
    assert "אין ריצה פעילה" in page.inner_text("#phoneNow") and page.is_disabled("#phoneStopBtn")
    assert "1. טיול בצפון" in page.inner_text("#phoneQueue")
    page.click("#phoneQueueBtn")
    page.wait_for_function("() => window.__posts.length === 1")

    page.locator("#phoneApprovals .phone-btn").first.click()          # ✅ אשר
    page.wait_for_function("() => window.__posts.length === 2")
    page.click("#phoneRuns .phone-btn")
    _confirm(page)
    page.wait_for_function("() => window.__posts.length === 3")
    assert page.evaluate("() => window.__posts") == [
        ["/api/render_queue/pause", {"paused": True}], ["/api/approvals/3/decide", {"approved": True}],
        ["/api/video_editor/runs/r1/rerun", {}]]


def test_a_paired_phone_lands_on_the_phone_screen(editor_page, editor_server):
    page = editor_page
    page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}&screen=phone")
    page.wait_for_function("() => !document.querySelector('[data-tab-panel=\"phone\"]').hidden && !!(window.__uiLazyLoaded || {}).phone")
    page.wait_for_function("() => document.getElementById('phoneNow').textContent.length > 0")
    assert page.evaluate("() => document.querySelectorAll('template[data-lazy-html=\"phone\"]').length") == 0
