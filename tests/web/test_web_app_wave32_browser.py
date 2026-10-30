# tests/web/test_web_app_wave32_browser.py
#
# גל 32 בדפדפן: אותה תיקייה שנבחרת שוב נטענת (כונן שלא היה מחובר כשהדף נטען), והחלק "🔗 אחרי
# שקליפ נכנס" בהגדרות Rocket - סגנונות, מה מוצג לכל מצב, אזהרה בלי סגנון ושמירה של השדות.
# הגדרות Rocket אמיתיות (data/rocket_settings.json) לא נקראות ולא נכתבות - fetch עטוף (ה-service
# worker מטפל ב-fetch לפני ש-Playwright רואה אותו, אז לא page.route).


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

COUNT_BROWSE = """() => {
  window.__browsePending = 0; window.__browseDone = 0;
  const orig = window.fetch;
  window.fetch = async (...args) => {
    const isBrowse = String(args[0]).startsWith('/api/browse');
    if (isBrowse) window.__browsePending++;
    try { return await orig(...args); }
    finally { if (isBrowse) { window.__browsePending--; window.__browseDone++; } }
  };
}"""

SET_FOLDER = "(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }"


def test_choosing_the_same_folder_again_loads_it_once_it_exists(editor_page, tmp_path):
    page = editor_page
    folder = tmp_path / "external_drive"
    page.evaluate(COUNT_BROWSE)
    page.evaluate(SET_FOLDER, str(folder))
    page.wait_for_function("() => window.__browseDone >= 1 && window.__browsePending === 0")
    assert page.evaluate("() => (_veQueueState || []).length") == 0

    folder.mkdir()
    for name in ("a.mp4", "b.mp4"):
        (folder / name).write_bytes(b"x")
    page.evaluate(SET_FOLDER, str(folder))  # אותו ערך בדיוק - עד גל 32 לא קרה כלום

    page.wait_for_function("() => (_veQueueState || []).length === 2 && _veFolderCounts && _veFolderCounts.files === 2", timeout=15000)


ROCKET_FAKE = """() => {
  window.__saved = null; window.__alert = null;
  window.alert = (m) => { window.__alert = m; };
  const orig = window.fetch;
  const json = (body) => Promise.resolve(new Response(JSON.stringify(body), {headers: {'Content-Type': 'application/json'}}));
  window.fetch = (url, opts = {}) => {
    const u = String(url);
    if (u === '/api/rocket_settings') {
      if ((opts.method || 'GET') === 'POST') { window.__saved = JSON.parse(opts.body); return json({ok: true}); }
      return json({input_dir: 'C:/in', output_dir: 'C:/out', watermark_image_path: '', preset: null, enable_weekly_recap: false,
        weekly_recap_period: 'week', weekly_recap_day: 6, enable_captions: false, enable_captions_translate: false, clip_hotkey: '',
        capture_voice_channel_id: '', capture_watch_dir: '', max_concurrent_renders: 1, counter: 5,
        auto_chain: 'edit_publish', auto_chain_profile: 'Old style', auto_chain_dry_run: true, seo_ai: true});
    }
    if (u === '/api/video_editor_profiles') return json({'Shorts': {}, 'Cinematic': {}});
    if (u === '/api/auto_chain/recent') return json({recent: [{at: 1760000000, file: 'replay.mp4', source: 'obs', action: 'edit',
      text: 'replay.mp4 נכנס לתור - עריכה בסגנון "Shorts" ואז לפרסום'}]});
    return orig(url, opts);
  };
}"""


def _visible(page, selector):
    return page.evaluate("(s) => { const el = document.querySelector(s); return !el.hidden && !el.closest('[hidden]'); }", selector)


def test_rocket_settings_choose_what_happens_after_a_clip_comes_in(editor_page):
    page = editor_page
    page.evaluate(ROCKET_FAKE)
    page.evaluate("() => { closeVeEditor(); switchTab('rocket'); }")
    page.wait_for_function("() => document.getElementById('rsAutoChain').value === 'edit_publish'")

    options = page.eval_on_selector_all("#rsAutoChainProfile option", "els => els.map(o => o.value)")
    assert options == ["", "Cinematic", "Shorts", "Old style"]  # סגנון שנמחק מאז עדיין מוצג (לא נמצא)
    assert page.input_value("#rsAutoChainProfile") == "Old style"
    assert page.is_checked("#rsAutoChainDryRun") and page.is_checked("#rsSeoAi")
    assert "replay.mp4" in page.inner_text("#rsAutoChainRecent")

    expected = {"off": (False, False), "edit": (True, False), "edit_publish": (True, True), "publish": (False, True)}
    for mode, (style_shown, dry_run_shown) in expected.items():
        page.select_option("#rsAutoChain", mode)
        assert (_visible(page, "#rsAutoChainProfile"), _visible(page, "#rsAutoChainDryRun")) == (style_shown, dry_run_shown), mode

    page.select_option("#rsAutoChain", "edit")
    page.select_option("#rsAutoChainProfile", "")
    page.evaluate("() => saveRocketSettings()")
    page.wait_for_function("() => window.__alert !== null")
    assert page.evaluate("() => window.__saved") is None  # עריכה בלי סגנון לא נשמרת

    page.select_option("#rsAutoChain", "edit_publish")
    page.select_option("#rsAutoChainProfile", "Shorts")
    page.uncheck("#rsAutoChainDryRun")
    page.uncheck("#rsSeoAi")
    page.evaluate("() => saveRocketSettings()")
    page.wait_for_function("() => window.__saved !== null")
    saved = page.evaluate("() => window.__saved")
    assert (saved["auto_chain"], saved["auto_chain_profile"], saved["auto_chain_dry_run"], saved["seo_ai"]) == ("edit_publish", "Shorts", False, False)
    assert saved["counter"] == 5  # שאר ההגדרות נשמרות כרגיל
