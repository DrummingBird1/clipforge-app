# tests/web/test_web_app_wave19_21_browser.py
#
# גלים 19-21 (שדרוג העיצוב) בדפדפן אמיתי: מסך העבודות (חיפוש/סטטוס/יעד), אריחי
# תוצאות, דיאלוגים (✕/Esc/החזרת פוקוס), טפסים עם אימות, פאנל היסטוריית שינויים,
# צפיפות, skeleton, סיור מודרך, פס התקדמות גלובלי - ובגל 21: תפריט ערכת נושא/
# הדגשה/שפה, ממשק באנגלית שחוזר לעברית בדיוק, טבעת פוקוס ויעדי לחיצה, ובדיקת
# רגרסיה ויזואלית של /styleguide בשלוש הערכות.
import os
from tests import TESTS_DIR


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

BASELINE_DIR = os.path.join(TESTS_DIR, "visual_baselines")
HEBREW_JS = "/[\\u0590-\\u05FF]/"


@pytest.fixture
def home_page(editor_server, edge_browser):
    """דף חדש בלי סקריפט נבחר (מסך הבית), בלי תנועה - כמו משתמש עם prefers-reduced-motion."""
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL", reduced_motion="reduce")
    context.add_init_script("try { if (localStorage.getItem('veFocus') === null) localStorage.setItem('veFocus', 'false'); } catch (e) {}")
    page = context.new_page()
    try:
        page.goto(f"{editor_server['base_url']}/?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    except Exception:
        context.close()
        raise
    yield page
    context.close()


def _visible_hebrew(page, selector):
    return page.evaluate("""([selector, hebrew]) => {
        const re = new RegExp(hebrew.slice(1, -1));
        const out = [];
        for (const root of document.querySelectorAll(selector)) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            for (let n = walker.nextNode(); n; n = walker.nextNode()) {
                const el = n.parentElement;
                if (!re.test(n.nodeValue) || el.closest('[data-no-i18n], .console')) continue;
                const box = el.getBoundingClientRect();
                if (box.width && box.height) out.push(n.nodeValue.trim());
            }
        }
        return out;
    }""", [selector, HEBREW_JS])


# --- גל 19: מסכים ---

def test_jobs_screen_filters_by_search_status_and_target(editor_page, tmp_path):
    page = editor_page
    for name, target in (("w19_alpha", "shorts"), ("w19_beta", "tiktok")):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "a.mp4").write_bytes(b"x")
        page.evaluate("""async ([folder, target]) => { await fetch('/api/editor_projects', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({folder, targets: [target]})}); }""", [str(folder), target])
    page.click("#veFolderChip")  # גל 27: "כל העבודות" בתפריט של שבב התיקייה
    page.click("#veJobsBtn")
    page.wait_for_selector("#veJobsList .ve-job-card")
    visible = "() => [...document.querySelectorAll('#veJobsList .ve-job-card')].filter(c => !c.hidden).map(c => c.querySelector('.ve-job-title').textContent)"
    page.fill("#veJobsSearch", "w19_")
    page.dispatch_event("#veJobsSearch", "input")
    assert sorted(t.split()[-1] for t in page.evaluate(visible)) == ["w19_alpha", "w19_beta"]
    assert page.inner_text("#veJobsCount").startswith("2")
    page.click("#veJobsTargetFilter button[data-target=tiktok]")
    assert [t.split()[-1] for t in page.evaluate(visible)] == ["w19_beta"]
    page.click("#veJobsTargetFilter button[data-target=tiktok]")
    page.evaluate("() => setVeJobsStatusFilter('ok')")
    assert page.evaluate(visible) == []
    page.evaluate("() => setVeJobsStatusFilter('never')")
    assert len(page.evaluate(visible)) == 2
    # כרטיס עבודה: תמונה ממוזערת מהקובץ הראשון וכפתורי פתח/הרץ
    card = page.locator("#veJobsList .ve-job-card:not([hidden])").first
    assert card.locator(".ve-job-thumb").count() == 1
    assert card.locator("button:has-text('פתח')").count() == 1 and card.locator("button:has-text('הרץ')").count() == 1


def test_results_modal_adds_stat_tiles(editor_page):
    page = editor_page
    page.evaluate("""() => _veShowResults({mode: 'render', input_dir: 'C:\\\\x', output_dir: 'C:\\\\out', elapsed_seconds: 75,
        counts: {files_created: 2, skipped: 1, errors: 1},
        files: [{source: 'a.mp4', status: 'created', output: 'C:\\\\out\\\\a.mp4', render_seconds: 10, output_size_mb: 3},
                {source: 'b.mp4', status: 'created', output: 'C:\\\\out\\\\b.mp4', render_seconds: 20, output_size_mb: 5},
                {source: 'c.mp4', status: 'skipped', reason: 'כבר קיים'},
                {source: 'd.mp4', status: 'error', reason: 'שטח דיסק'}]})""")
    tiles = page.inner_text("#veResultsTiles")
    for text in ("נוצרו", "נכשלו", "דולגו", "זמן כולל", "1:15", "ממוצע לקובץ", "0:15", "8.0 MB"):
        assert text in tiles, text
    assert page.locator("#veResultsList .ve-result-card").count() == 4


def test_dialogs_close_with_x_or_esc_and_return_focus(home_page):
    page = home_page
    page.focus("#statsBtn")
    page.keyboard.press("Enter")
    page.wait_for_function("() => document.getElementById('statsModalBg').classList.contains('show')")
    page.wait_for_function("() => document.getElementById('statsModalBg').contains(document.activeElement)")
    assert page.locator("#statsModalBg .modal-close").count() == 1
    page.wait_for_function("() => document.querySelectorAll('#statsTiles .stat-tile').length >= 2")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('statsModalBg').classList.contains('show')")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'statsBtn'")
    page.click("#statsBtn")
    page.wait_for_function("() => document.getElementById('statsModalBg').classList.contains('show')")
    page.click("#statsModalBg .modal-close")
    page.wait_for_function("() => !document.getElementById('statsModalBg').classList.contains('show')")


def test_settings_forms_get_labels_and_inline_validation(home_page):
    page = home_page
    page.click(".nav-rail .tab-btn[data-tab=bot]")
    field = page.locator("#rssUrl").locator("xpath=ancestor::label[contains(@class,'form-field')]")
    assert "כתובת RSS" in field.locator(".form-label").inner_text()
    page.fill("#rssUrl", "nope")
    page.dispatch_event("#rssUrl", "blur")
    assert "is-invalid" in field.get_attribute("class")
    assert "https://example.com/feed" in page.inner_text("#rssUrlError")
    assert page.get_attribute("#rssUrl", "aria-invalid") == "true"
    calls = page.evaluate("() => { let before = document.querySelectorAll('.toast').length; addRssFeed(); return before; }")
    page.wait_for_function(f"() => document.querySelectorAll('.toast').length > {calls}")
    assert page.evaluate("() => document.activeElement.id") in ("rssName", "rssUrl", "rssChannel")
    page.fill("#rssUrl", "https://example.com/feed")
    page.dispatch_event("#rssUrl", "input")
    page.dispatch_event("#rssUrl", "blur")
    assert "is-invalid" not in field.get_attribute("class")


# --- גל 20: ליטוש ---

def test_undo_panel_lists_changes_and_jumps_back(editor_page):
    page = editor_page
    page.evaluate("() => _veResetUndoHistory()")
    for value in ("5", "9"):
        page.evaluate("(v) => { document.getElementById('veTrimStart').value = v; _pushVeUndoSnapshot(); }", value)
    page.evaluate("() => toggleVeUndoPanel(true)")
    assert page.is_visible("#veUndoPanel")
    items = page.locator("#veUndoList .undo-item")
    total = items.count()
    assert total == 3
    assert "current" in items.first.get_attribute("class")
    items.last.click()
    assert page.input_value("#veTrimStart") == "0"
    assert page.locator("#veUndoList .undo-item.future").count() == total - 1
    assert "current" in items.last.get_attribute("class")
    page.evaluate("() => toggleVeUndoPanel(false)")
    assert not page.is_visible("#veUndoPanel")


def test_density_toggle_persists_and_skeleton_replaces_loading_text(home_page):
    page = home_page
    page.click("#densityBtn")
    assert page.evaluate("() => document.documentElement.dataset.density") == "compact"
    assert page.get_attribute("#densityBtn", "aria-pressed") == "true"
    page.reload()
    page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    assert page.evaluate("() => document.documentElement.dataset.density") == "compact"
    count = page.evaluate("() => { const box = document.createElement('div'); document.body.appendChild(box); uiSkeleton(box, 4, 'card'); return box.querySelectorAll('.sk.sk-card').length; }")
    assert count == 4


def test_tour_waits_under_automation_and_runs_on_demand(home_page):
    page = home_page
    page.wait_for_timeout(1300)
    assert page.locator("#tourCard").count() == 0
    page.evaluate("() => startUiTour()")
    page.wait_for_selector("#tourCard")
    assert "1" in page.inner_text("#tourCard .tour-step")
    page.click("#tourCard button:has-text('הבא')")
    assert "2" in page.inner_text("#tourCard .tour-step")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('tourCard') || document.getElementById('tourCard').hidden || !document.getElementById('tourCard').isConnected")
    assert page.evaluate("() => localStorage.getItem('uiTourSeen')") == "1"


def test_global_progress_bar_mirrors_the_run(home_page):
    page = home_page
    page.evaluate("() => { state.running = true; document.getElementById('progressBar').style.width = '40%'; }")
    page.wait_for_function("() => !document.querySelector('.global-progress').hidden")
    assert page.get_attribute(".global-progress", "aria-valuenow") == "40"
    page.evaluate("() => { state.running = false; document.getElementById('progressBar').style.width = '0%'; }")
    page.wait_for_function("() => document.querySelector('.global-progress').hidden")


# --- גל 21: ערכות נושא, שפה ונגישות ---

def test_prefs_menu_sets_theme_accent_and_follows_the_system(home_page):
    page = home_page
    page.click("#themeToggle")
    assert page.is_visible("#uiPrefsMenu") and page.get_attribute("#themeToggle", "aria-expanded") == "true"
    page.click("#uiPrefsMenu [data-theme-opt=contrast]")
    assert page.evaluate("() => document.documentElement.dataset.theme") == "contrast"
    # רקע הגוף עובר transition קצר - מחכים לערך הסופי
    page.wait_for_function("() => getComputedStyle(document.body).backgroundColor === 'rgb(0, 0, 0)'")
    page.click("#uiPrefsMenu [data-theme-opt=dark]")
    page.click("#uiPrefsMenu [data-accent-opt=violet]")
    page.wait_for_function("() => getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() === '#a78bfa'")
    assert page.get_attribute("#uiPrefsMenu [data-accent-opt=violet]", "aria-checked") == "true"
    page.emulate_media(color_scheme="light")
    page.click("#uiPrefsMenu [data-theme-opt=auto]")
    assert page.evaluate("() => document.documentElement.dataset.theme") == "light"
    page.emulate_media(color_scheme="dark")
    page.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
    page.keyboard.press("Escape")
    assert not page.is_visible("#uiPrefsMenu")
    assert page.evaluate("() => document.activeElement.id") == "themeToggle"
    page.reload()
    page.wait_for_function("() => typeof state !== 'undefined' && state.scripts && state.scripts.length > 0", timeout=20000)
    assert page.evaluate("() => [document.documentElement.dataset.themePref, document.documentElement.dataset.accent]") == ["auto", "violet"]


def test_english_ui_translates_everything_visible_and_restores_hebrew(home_page):
    page = home_page
    # textContent ולא innerText: שורות הפיד הן content-visibility:auto - מחוץ למסך ה-innerText שלהן ריק או לא, לפי תזמון הציור.
    # בלי תוכן הפידים עצמם (ריצות/פרויקטים): טסטים אחרים שרצים במקביל מוסיפים להם שורות בין "לפני" ל"אחרי".
    region = """() => ['.topbar', '.nav-rail', '#homePanel'].map(s => {
        const copy = document.querySelector(s).cloneNode(true);
        for (const feed of copy.querySelectorAll('#homeRuns, #homeProjects')) feed.replaceChildren();
        return copy.textContent; }).join('\\n')"""
    # מחכים שפיד הריצות והפרויקטים נטענו - אחרת "לפני" נלכד באמצע הטעינה ונראה שונה מ"אחרי"
    page.wait_for_function("() => document.querySelector('#homeRuns').children.length > 0 && document.querySelector('#homeProjects').children.length > 0")
    before = page.evaluate(region)
    page.evaluate("() => setUiLanguage('en')")
    page.wait_for_function("() => document.documentElement.dir === 'ltr' && document.documentElement.lang === 'en'")
    assert "What are we editing today?" in page.inner_text("#homePanel")
    page.wait_for_function("() => document.querySelectorAll('#homeProjects > *').length > 0")
    assert _visible_hebrew(page, ".topbar, .nav-rail, #homePanel") == []
    # טקסט שנוסף אחרי המעבר מתורגם אוטומטית, כולל תבניות עם מספרים
    page.evaluate("() => uiToast('הקליפ אושר לרינדור', 'ok')")
    page.wait_for_function("() => [...document.querySelectorAll('.toast')].some(t => t.textContent.includes('The clip was approved for rendering'))")
    assert page.evaluate("() => uiTranslate('לפני 5 דק׳')") == "5 min ago"
    assert page.evaluate("() => uiTranslate('✂️ 3 קליפים עם עריכה')") == "✂️ 3 clips with edits"
    page.evaluate("() => setUiLanguage('he')")
    page.wait_for_function("() => document.documentElement.dir === 'rtl'")
    assert page.evaluate(region) == before
    page.evaluate("() => setUiLanguage('en')")
    page.reload()
    page.wait_for_function("() => document.documentElement.lang === 'en'", timeout=20000)
    assert "What are we editing today?" in page.inner_text("#homePanel")


def test_focus_ring_is_visible_and_icon_buttons_are_big_enough(home_page):
    page = home_page
    page.keyboard.press("Tab")
    page.evaluate("() => document.getElementById('statsBtn').focus()")
    ring = page.evaluate("() => { const el = document.getElementById('statsBtn'); return [el.matches(':focus-visible'), getComputedStyle(el).boxShadow]; }")
    assert ring[0] is True and "rgb" in ring[1]
    sizes = page.evaluate("() => [...document.querySelectorAll('.topbar .icon-only')].filter(b => b.offsetParent).map(b => [b.id, b.getBoundingClientRect().width, b.getBoundingClientRect().height])")
    assert sizes and all(w >= 34 and h >= 34 for _id, w, h in sizes), sizes


@pytest.mark.parametrize("theme", ["dark", "light", "contrast"])
def test_styleguide_matches_the_visual_baseline(editor_server, edge_browser, theme):
    """רגרסיה ויזואלית: /styleguide (דטרמיניסטי - רק tokens ורכיבים) מוקטן לאפור ונמדד מול baseline.
    CLIPFORGE_UPDATE_VISUAL_BASELINES=1 כותב baseline חדש (אחרי שינוי עיצוב מכוון)."""
    image_module = pytest.importorskip("PIL.Image")
    from io import BytesIO
    context = edge_browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce", device_scale_factor=1)
    try:
        page = context.new_page()
        page.goto(f"{editor_server['base_url']}/styleguide?token={editor_server['web_app'].ACCESS_TOKEN}")
        page.evaluate(f"() => {{ document.documentElement.dataset.theme = {theme!r}; }}")
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(200)
        shot = page.screenshot()
    finally:
        context.close()
    current = image_module.open(BytesIO(shot)).convert("L").resize((160, 112), image_module.Resampling.BILINEAR)
    baseline_path = os.path.join(BASELINE_DIR, f"styleguide_{theme}.png")
    if os.environ.get("CLIPFORGE_UPDATE_VISUAL_BASELINES") == "1" or not os.path.isfile(baseline_path):
        os.makedirs(BASELINE_DIR, exist_ok=True)
        current.save(baseline_path)
        pytest.skip(f"baseline נכתב: {baseline_path}")
    baseline = image_module.open(baseline_path).convert("L")
    diff = sum(abs(a - b) for a, b in zip(current.getdata(), baseline.getdata())) / (160 * 112)
    assert diff <= 6, f"{theme}: הפרש ממוצע {diff:.2f}/255 מול ה-baseline - שינוי עיצוב לא מכוון? (לעדכון: CLIPFORGE_UPDATE_VISUAL_BASELINES=1)"
