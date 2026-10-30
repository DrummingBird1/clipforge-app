# tests/web/test_web_app_design_browser.py
#
# גלים 15-18 (שדרוג העיצוב) בדפדפן אמיתי: מסך הבית, rail ופס עליון, אייקונים
# שמחליפים אימוג'י בלי לשנות את הטקסט, הודעות קופצות במקום alert, ניווט ב-Ctrl+K,
# ובסטודיו - מסך מלא בלי מעטפת, סביבות עבודה, גרירה על תווית, מסלול שכבות,
# מפרידים נגררים וכפתור השהיה אחד.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def home_page(editor_server, edge_browser):
    """דף חדש בלי סקריפט נבחר (מסך הבית)."""
    context = edge_browser.new_context(viewport={"width": 1440, "height": 950}, locale="he-IL")
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


def test_home_screen_shows_actions_projects_and_feed_until_a_script_is_selected(home_page):
    page = home_page
    assert page.is_visible("#homePanel")
    assert not page.is_visible("#folderInput")
    assert page.locator(".home-action").count() >= 6
    page.wait_for_function("() => document.querySelector('#homeProjects').children.length > 0")
    page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
    assert not page.is_visible("#homePanel")
    # גל 31: העורך נפתח תמיד בסטודיו - שבב התיקייה במקום שורת הנתיב
    assert page.evaluate("() => document.body.classList.contains('ve-focus')") and page.is_visible("#veFolderChip")
    assert page.evaluate("() => document.querySelector('.nav-rail .rail-studio').classList.contains('rail-active')")
    page.evaluate("() => goHome()")
    assert page.is_visible("#homePanel")
    assert page.evaluate("() => state.selectedId") is None


def test_rail_switches_screens_and_marks_the_active_one(home_page):
    page = home_page
    page.click(".nav-rail .tab-btn[data-tab=gallery]")
    assert page.is_visible("[data-tab-panel=gallery]")
    assert page.evaluate("() => document.querySelector('.nav-rail .tab-btn[data-tab=gallery]').classList.contains('active')")
    page.click(".brand")
    assert page.is_visible("#homePanel")


def test_emoji_become_icons_but_text_stays_the_same(home_page):
    page = home_page
    info = page.evaluate("""() => {
        const btn = document.getElementById('statsBtn');
        const icon = btn.querySelector('.ei');
        return {text: btn.textContent, icon: icon && icon.dataset.i, hidden: icon && icon.getAttribute('aria-hidden'),
                mask: icon && getComputedStyle(icon).webkitMaskImage.slice(0, 20)};
    }""")
    assert info["text"] == "📊 סטטיסטיקות"
    assert info["icon"] == "chart-column" and info["hidden"] == "true"
    assert info["mask"].startswith("url(")
    # טקסט שנוסף אחר כך ע"י JS מקבל אייקון גם הוא, עם גוון לפי המשמעות
    page.evaluate("() => { const d = document.createElement('div'); d.id = 'zzIcon'; d.textContent = '✅ הושלם'; document.body.appendChild(d); }")
    page.wait_for_function("() => document.querySelector('#zzIcon .ei[data-i=circle-check][data-tone=ok]')")
    assert page.inner_text("#zzIcon").startswith("✅")
    # אפשרויות ב-<select> לא נוגעים בהן (אין HTML בתוך option)
    assert page.evaluate("() => document.querySelector('#aiProviderSelect option').querySelector('.ei')") is None


def test_alert_becomes_a_toast_with_tone(home_page):
    page = home_page
    page.evaluate("() => alert('שגיאה: משהו השתבש')")
    toast = page.locator(".toast").last
    assert toast.get_attribute("data-tone") == "bad"
    assert "משהו השתבש" in toast.inner_text()
    toast.locator(".toast-close").click()
    page.wait_for_function("() => !document.querySelector('.toast:not(.leaving)')", timeout=3000)


def test_ctrl_k_offers_screens_and_system_actions(home_page):
    page = home_page
    page.keyboard.press("Control+k")
    page.fill("#paletteInput", "גלריה")
    sections = page.evaluate("() => Array.from(document.querySelectorAll('#paletteList .ve-palette-section')).map(e => e.textContent)")
    assert "🧭 מסכים" in sections
    page.keyboard.press("Enter")
    assert page.is_visible("[data-tab-panel=gallery]")


def test_activity_feed_shows_a_human_summary(home_page):
    page = home_page
    page.evaluate("""() => _renderHistoryRows([{script: 'video_editor.py', status: 'success', started_at: new Date().toISOString(),
        duration: 245, summary: 'files_created: 24 | errors: 2', result: {files_created: 24, errors: 2}}], '')""")
    item = page.locator("#historyList .feed-item").first
    page.wait_for_function("() => { const e = document.querySelector('#historyList .feed-item'); return !!e && e.innerText.trim().length > 0; }")
    text = item.inner_text()
    assert "24 נוצרו" in text and "2 שגיאות" in text and "4:05" in text and "עכשיו" in text
    item.click()
    assert "files_created: 24" in item.locator(".feed-details").inner_text()


def test_studio_hides_app_chrome_and_has_one_run_control(editor_page):
    page = editor_page
    page.evaluate("() => openStudio()")
    assert page.evaluate("() => document.body.classList.contains('ve-focus')")
    assert not page.is_visible("header.topbar")
    assert not page.is_visible(".nav-rail")
    assert not page.is_visible(".run-row")
    # גל 27: ⏸ מופיע בפס רק כשיש מה להשהות (כפתור מושבת לא תופס מקום)
    assert page.is_visible("#veStickyRunBtn") and not page.is_visible("#veStickyPauseBtn")
    # כפתור ההשהיה בפס העליון משקף את זה של הדף
    # גל 23: המראה קוראת את מצב ההשהיה האמיתי (_paused), לא את טקסט הכפתור שמתורגם באנגלית
    page.evaluate("() => { const b = document.getElementById('pauseBtn'); b.disabled = false; _paused = true; b.textContent = '▶️ המשך'; }")
    page.wait_for_function("() => !document.getElementById('veStickyPauseBtn').disabled && document.getElementById('veStickyPauseBtn').textContent.includes('▶')")
    assert page.is_visible("#veStickyPauseBtn")
    # ערכת Pro Dark: הרקע של הסטודיו שונה מהרקע הרגיל
    assert page.evaluate("() => getComputedStyle(document.body).getPropertyValue('--color-bg').trim()") != page.evaluate(
        "() => getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim()")
    page.evaluate("() => setVeFocus(false)")
    assert page.is_visible("header.topbar")


def test_player_empty_state_follows_the_folder(editor_page, tmp_path):
    page = editor_page
    assert page.is_visible("#veStageEmpty .ve-when-no-folder >> nth=0")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    page.wait_for_function("() => document.getElementById('videoEditorOptions').classList.contains('ve-has-folder')")
    assert page.is_visible("#veStageEmpty .ve-when-folder >> nth=0")


def test_workspaces_open_only_the_relevant_areas_and_restore(editor_page):
    page = editor_page
    before = page.evaluate("() => Object.fromEntries(_veCategoryEls().map(d => [d.dataset.cat, d.open]))")
    page.evaluate("() => setVeWorkspace('audio')")
    opened = page.evaluate("() => _veCategoryEls().filter(d => d.open).map(d => d.dataset.cat)")
    assert opened == ["sound"]
    page.evaluate("() => setVeWorkspace('all')")
    assert page.evaluate("() => Object.fromEntries(_veCategoryEls().map(d => [d.dataset.cat, d.open]))") == before


def test_dragging_a_label_scrubs_the_number(editor_page):
    page = editor_page
    label_id = page.evaluate("""() => {
        const label = Array.from(document.querySelectorAll('#veCategories .ve-row > label.ve-scrub'))
          .find(l => l.offsetParent && _veScrubControlFor(l).type === 'range');
        if (!label) return null;
        label.id = 'zzScrubLabel';
        return label.id;
    }""")
    assert label_id, "אין תווית עם גרירה גלויה"
    start = page.evaluate("() => parseFloat(_veScrubControlFor(document.getElementById('zzScrubLabel')).value)")
    page.locator("#zzScrubLabel").scroll_into_view_if_needed()
    box = page.locator("#zzScrubLabel").bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + 70, box["y"] + box["height"] / 2, steps=6)
    page.mouse.up()
    after = page.evaluate("() => parseFloat(_veScrubControlFor(document.getElementById('zzScrubLabel')).value)")
    assert after != start


def test_layers_track_draws_a_bar_per_layer(editor_page):
    page = editor_page
    count = page.evaluate("""() => {
        _veTimeline = {path: 'x.mp4', duration: 20};
        document.getElementById('veLayers').value = JSON.stringify([
            {type: 'text', text: 'Hi', start: 1, end: 5}, {type: 'timer', start: 3, end: null}, {type: 'text', text: 'late', start: 999}]);
        document.getElementById('veLayers').dispatchEvent(new Event('change'));
        _veRenderLayersTrack();
        return document.querySelectorAll('#veTlLayersTrack .ve-tl-layer').length;
    }""")
    assert count == 2  # שכבה שמתחילה אחרי סוף הפלט לא מצוירת
    lanes = page.evaluate("() => Array.from(document.querySelectorAll('#veTlLayersTrack .ve-tl-layer')).map(b => b.style.getPropertyValue('--lane-top'))")
    assert len(set(lanes)) == 2  # חופפות -> שני נתיבים
    assert page.locator(".ve-track-tag").count() == 4  # גל 29: וידאו, B-roll, שכבות, שמע


def test_studio_panels_resize_by_dragging_and_remember(editor_page):
    page = editor_page
    page.evaluate("() => openStudio()")
    page.wait_for_function("() => getComputedStyle(document.querySelector('.ve-resizer')).display === 'block'")
    resizer = page.locator(".ve-resizer[data-panel=side]")
    resizer.scroll_into_view_if_needed()
    box = resizer.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 40)
    page.mouse.down()
    page.mouse.move(box["x"] - 80, box["y"] + 40, steps=5)
    page.mouse.up()
    width = page.evaluate("() => getComputedStyle(document.getElementById('videoEditorOptions')).getPropertyValue('--ve-side-w').trim()")
    assert width.endswith("px") and int(width[:-2]) >= 200
    assert page.evaluate("() => _veLoadPref('veSideW', 0)") > 0
