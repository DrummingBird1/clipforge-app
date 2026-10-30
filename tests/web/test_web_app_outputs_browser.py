# tests/web/test_web_app_outputs_browser.py
#
# 23.10.2026: מסך "תוצרים" בדפדפן - נטען כשפותחים אותו, מציג תוצרים מ-workspace זמני, מסנן לפי כלי ותאריך, "פתח
# בסטודיו" מכין תיקייה ופותח אותה (openProject), ו"פרסם" שולח את הנתיב ל-route של הפרסום. בלי העלאה אמיתית: fetch של
# /api/clips/* עטוף בדף (page.route לא תופס בקשות שה-service worker מטפל בהן).
import os
import time

import pytest

from utils.shared import export_dir

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning")]

CARDS = "() => document.querySelectorAll('#outputsList .output-card').length"
# textContent ולא inner_text: לכרטיס יש content-visibility:auto (19-access.css), ומיד אחרי הרינדור הדפדפן עוד לא החליט
# שהוא בתצוגה - innerText ריק (נכשל 3 מתוך 4 גם על master)
LIST_TEXT = "() => document.getElementById('outputsList').textContent"


def _video(path, days_old=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    stamp = time.time() - days_old * 86400
    os.utime(path, (stamp, stamp))
    return path


def test_the_outputs_screen_lists_filters_opens_and_publishes(editor_page, editor_server, tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    monkeypatch.setattr(editor_server["web_app"], "WORKSPACE_DIR", str(ws))
    monkeypatch.setattr(export_dir, "SETTINGS_PATH", str(tmp_path / "export_settings.json"))
    monkeypatch.delenv(export_dir.ENV_VAR, raising=False)
    _video(ws / "studio" / "horizontal" / "edited.mp4", days_old=40)
    lapse = _video(ws / "timelapses" / "vertical" / "lapse.mp4")
    page = editor_page
    assert not page.evaluate("() => !!(window.__uiLazyLoaded || {}).outputs")
    assert page.evaluate("() => document.querySelectorAll('template[data-lazy-html=\"outputs\"]').length") == 1
    page.evaluate("() => { closeVeEditor(); switchTab('outputs'); }")
    page.wait_for_function(CARDS + " === 2")
    assert page.evaluate("() => !!window.__uiLazyLoaded.outputs")
    assert page.evaluate("() => document.querySelectorAll('template[data-lazy-html=\"outputs\"]').length") == 0

    page.select_option("#outputsFilterDate", "1")
    page.wait_for_function(CARDS + " === 1")
    assert "lapse.mp4" in page.evaluate(LIST_TEXT)
    page.select_option("#outputsFilterDate", "")
    page.select_option("#outputsFilterTool", "studio")
    page.wait_for_function(CARDS + " === 1")
    assert "edited.mp4" in page.evaluate(LIST_TEXT)
    page.select_option("#outputsFilterTool", "")
    page.fill("#outputsFilterName", "LAPSE")
    page.wait_for_function(CARDS + " === 1")

    page.evaluate("""() => {
      window.__opened = null;
      window.openProject = (folder) => { window.__opened = folder; };
      window.__posts = [];
      const realFetch = window.fetch;
      window.fetch = (url, options) => {
        if (String(url).startsWith('/api/clips/')) {
          window.__posts.push([String(url), JSON.parse(options.body).path]);
          return Promise.resolve(new Response(JSON.stringify({ok: true, tiktok_url: 'about:blank', caption: ''}), {status: 200}));
        }
        return realFetch(url, options);
      };
      window.open = () => null;
    }""")
    assert page.is_disabled("#outputsStudioBtn")
    page.click("#outputsList .output-card")
    page.wait_for_function("() => !document.getElementById('outputsStudioBtn').disabled")
    page.click("#outputsStudioBtn")
    page.wait_for_function("() => !!window.__opened")
    assert page.evaluate("() => window.__opened") == str(ws / "timelapses" / "studio_handoff" / "vertical" / "lapse")
    page.click("#outputsTiktokBtn")
    page.wait_for_function("() => window.__posts.length === 1")
    assert page.evaluate("() => window.__posts[0]") == ["/api/clips/tiktok_export", os.path.normpath(lapse)]
