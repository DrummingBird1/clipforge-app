# tests/web/test_web_app_wave31_browser.py
#
# גל 31 בדפדפן אמיתי - ריצה, תוצאות ונוחות: גיליון "לפני הרצה", התוצאות בתוך הסטודיו, לפני/אחרי
# בנגן החי, מפת קיצורים וקיצורי הנגן בכל העורך, Ctrl+K שמבצע, מסך מחשב נייד (פסי אייקונים), מצבים
# ריקים, היררכיה ויזואלית, והעורך תמיד בסטודיו.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(page):
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _opts(page):
    return page.evaluate("() => _collectRunOptions()")


def _open_folder(page, folder, names=("a.mp4", "b.mp4")):
    for name in names:
        (folder / name).write_bytes(b"x")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function(f"() => (_veQueueState || []).length === {len(names)}", timeout=15000)


def _spy_runs(page):
    page.evaluate("() => { window.__runs = 0; runScript = () => { window.__runs++; }; }")


# --- גיליון "לפני הרצה" ---

def test_pre_run_sheet_shows_what_time_size_and_warnings_then_runs(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    _spy_runs(page)
    page.click("#veTargetChips button[data-target=shorts]")
    page.click("#veTargetChips button[data-target=tiktok]")
    page.select_option("#veSilenceMode", "edges")
    page.evaluate("() => _veSetFieldValue(document.getElementById('veTrimStart'), '2')")  # אזהרה: חיתוך + שקט
    page.wait_for_function("() => !document.getElementById('veStickyRunBtn').disabled")
    page.click("#veStickyRunBtn")
    page.wait_for_selector("#veRunSheetBg.show")
    assert page.inner_text("#veRunSheetWhat") == "2 קבצים × 2 יעדים = 4 סרטונים"
    assert "חיתוך שקט" in page.inner_text("#veRunSheetWarnings") and "אזהרות" in page.inner_text("#veRunSheetWarnTitle")
    assert page.locator("#veRunSheetTargets .ve-chip").count() == 2
    page.wait_for_function("() => !document.getElementById('veRunSheetSize').textContent.includes('⏳')", timeout=15000)
    assert page.evaluate("() => window.__runs") == 0  # לא רץ לפני האישור
    # לחיצה על אזהרה סוגרת את הגיליון וקופצת להגדרה
    page.click("#veRunSheetWarnings .ve-warning")
    assert not page.evaluate("() => document.getElementById('veRunSheetBg').classList.contains('show')")
    # Ctrl+Enter פותח, Ctrl+Enter בתוך הגיליון מריץ
    page.locator("body").press("Control+Enter")
    page.wait_for_selector("#veRunSheetBg.show")
    page.keyboard.press("Control+Enter")
    page.wait_for_function("() => window.__runs === 1")
    # "הצג לפני כל הרצה" כבוי - הרצה ישירה
    page.click("#veStickyRunBtn")
    page.wait_for_selector("#veRunSheetBg.show")
    page.uncheck("#veRunSheetAlways")
    page.click("#veRunSheetBg button:has-text('ביטול')")
    page.click("#veStickyRunBtn")
    page.wait_for_function("() => window.__runs === 2")
    assert not page.evaluate("() => document.getElementById('veRunSheetBg').classList.contains('show')")
    assert page.is_checked("#veRunSheetPref") is False or page.evaluate("() => _veLoadPref('veRunSheet', true)") is False


# --- התוצאות בתוך הסטודיו ---

MANIFEST = """(folder) => ({input_dir: folder, output_dir: folder, counts: {files_created: 1, errors: 1}, elapsed_seconds: 12,
    files: [{source: 'a.mp4', status: 'created', output: folder + '\\\\out\\\\a_edited.mp4', output_size_mb: 3.2, render_seconds: 5},
            {source: 'b.mp4', status: 'error', reason: 'ffmpeg failed'}]})"""


def test_results_open_inside_the_studio_as_cards(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    page.evaluate(f"(f) => _veShowResults(({MANIFEST})(f))", str(tmp_path))
    assert page.is_visible("#veResultsPanel")
    assert not page.is_visible("#veViewer details[data-cat=preview]")  # התוצאות במקום הנגן, לא בדיאלוג
    assert page.locator("#veResultsList .ve-result-card").count() == 2
    assert page.get_attribute("#veResultsList .ve-result-card[data-status=error]", "data-status") == "error"
    assert "ve-primary" in page.get_attribute("#veResultsRerunFailedBtn", "class")  # יש נכשלים - זו הפעולה הראשית
    # ⇆ מול המקור: המקור והפלט זה לצד זה
    page.click("#veResultsList .ve-result-card[data-status=created] button:has-text('מול המקור')")
    videos = page.evaluate("() => [...document.querySelectorAll('.ve-result-compare video')].map(v => v.getAttribute('src'))")
    assert len(videos) == 2 and "source_stream" in videos[0] and "file=a.mp4" in videos[0] and "/api/video_editor/stream" in videos[1]
    # לחיצה על התמונה מנגנת במקום
    page.click("#veResultsList .ve-result-card[data-status=created] .ve-result-media")
    assert page.evaluate("() => !!document.querySelector('.ve-result-card[data-status=created] .ve-result-media video')")
    page.click("#veResultsPanel button:has-text('חזרה לעריכה')")
    assert page.is_hidden("#veResultsPanel") and page.is_visible("#veViewer details[data-cat=preview]")


# --- לפני/אחרי בנגן החי ---

def test_live_before_after_split_and_black_and_white(editor_page):
    page = editor_page
    # נמצא בגל 31: רוויה 0 (שחור-לבן) הפכה ל-1 בנגן החי ("|| 1")
    assert "saturate(0)" in page.evaluate("() => _veLiveColorFilter({eq_saturation: 0, eq_contrast: 1.2})")
    assert "saturate(1)" in page.evaluate("() => _veLiveColorFilter({})")
    page.evaluate("() => { _veStage().classList.add('ve-stage-live'); toggleVeLiveCompare(true); _veSetPreviewSplit(30); }")
    assert page.evaluate("() => getComputedStyle(document.getElementById('vePreviewDivider')).display") != "none"
    assert page.evaluate("() => !document.getElementById('veLiveBefore').hidden")
    assert page.evaluate("() => getComputedStyle(document.getElementById('veLiveBefore')).clipPath") == "inset(0px 70% 0px 0px)"
    assert page.get_attribute("#veLiveCompareBtn", "aria-pressed") == "true"
    page.evaluate("() => toggleVeLiveCompare(false)")
    assert page.evaluate("() => getComputedStyle(document.getElementById('vePreviewDivider')).display") == "none"


# --- קיצורים ---

def test_shortcut_map_and_player_keys_work_anywhere_in_the_editor(editor_page):
    page = editor_page
    page.locator("body").press("?")
    page.wait_for_selector("#veShortcutsModalBg.show")
    text = page.inner_text("#veShortcutsList")
    for key in ("J", "K", "L", "I", "O", "Ctrl", "Delete"):
        assert key in text, key
    assert page.locator("#veShortcutsList kbd").count() > 25
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('veShortcutsModalBg').classList.contains('show')")
    # אחרי לחיצה בעקומות (לא ציר-הזמן) - J/K/L ו-I/O עדיין עובדים
    page.evaluate("() => { window.__rates = []; _veLivePlayRate = (d) => window.__rates.push(d); _veTimelineCursor = 3.5; }")
    page.evaluate("() => { setVeLayout('tabs'); _veActivateTab('look'); }")
    page.evaluate("() => _veSetSubcatOpen(document.querySelector('[data-subcat=grade]'), true)")
    page.click("#veCurvesCanvas", position={"x": 110, "y": 60})
    for key in ("l", "j"):
        page.keyboard.press(key)
    assert page.evaluate("() => window.__rates") == [1, -1]
    page.keyboard.press("i")
    assert page.input_value("#veTrimStart") == "3.5"
    # Ctrl+Z בעקומות מבטל את הנקודה (אחרי שהשלב הקודם נרשם - שינויים רצופים מתאחדים לצעד אחד)
    snapshot_taken = "() => _veUndoStack.length && _veUndoStack[_veUndoStack.length - 1] === JSON.stringify(_collectRunOptions())"
    page.wait_for_function(snapshot_taken)
    before = page.evaluate("() => document.getElementById('veCurvesMaster').value")
    page.click("#veCurvesCanvas", position={"x": 60, "y": 150})
    page.wait_for_function("(b) => document.getElementById('veCurvesMaster').value !== b", arg=before)
    page.wait_for_function(snapshot_taken)
    page.keyboard.press("Control+z")
    page.wait_for_function("(b) => document.getElementById('veCurvesMaster').value === b", arg=before)


# --- Ctrl+K שמבצע ---

@pytest.mark.parametrize("query, check", [
    ("קידוד hevc", "() => document.getElementById('veCodec').value === 'hevc'"),
    ("speed 1.5", "() => document.getElementById('veSpeed').value === '1.5'"),
    ("הוסף לוגו", "() => !document.querySelector('.ve-layer-card[data-card=logo]') || !document.querySelector('.ve-layer-card[data-card=logo]').hidden"),
    ("מראה שחור", "() => document.getElementById('veEqSaturation').value === '0'"),
    ("יעד tiktok", "() => _veTargets().includes('tiktok')"),
])
def test_command_palette_does_things(editor_page, query, check):
    page = editor_page
    page.wait_for_function("() => !!_veSchema")
    page.keyboard.press("Control+k")
    page.wait_for_selector("#paletteModalBg.show")
    page.fill("#paletteInput", query)
    page.dispatch_event("#paletteInput", "input")
    page.wait_for_function("() => (document.querySelector('#paletteList .ve-palette-section') || {}).textContent === '⚡ ביצוע'")
    page.keyboard.press("Enter")
    page.wait_for_function(check)


# --- מסך מחשב נייד ---

def test_laptop_screen_folds_side_panels_into_icon_rails(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    page.set_viewport_size({"width": 1366, "height": 768})
    page.evaluate("() => { localStorage.removeItem('veRail_queue'); _veApplyRails(); }")
    assert page.evaluate("() => document.body.classList.contains('ve-laptop')")
    assert page.evaluate("() => document.getElementById('veSide').getBoundingClientRect().width") < 60
    assert page.inner_text("#veRailQueueCount") == "2"
    viewer = "() => document.getElementById('veViewer').getBoundingClientRect().width / document.querySelector('.ve-shell').getBoundingClientRect().width"
    assert page.evaluate(viewer) > 0.55  # הנגן מקבל את רוב הרוחב
    # ההגדרות מתקפלות לפס אייקונים - לחיצה על אייקון פותחת את האזור שלו
    page.click("#veInspectorCollapseBtn")
    assert page.evaluate(viewer) > 0.85
    page.click("#veInspectorRail button[data-cat=sound]")
    assert not page.evaluate("() => document.getElementById('videoEditorOptions').classList.contains('ve-inspector-rail')")
    assert page.is_visible("#veCategories details[data-cat=sound]")
    page.click(".ve-side .ve-rail-btn")
    assert page.evaluate("() => document.getElementById('veSide').getBoundingClientRect().width") > 150
    page.set_viewport_size({"width": 1440, "height": 950})
    page.evaluate("() => _veApplyRails()")
    assert not page.evaluate("() => document.body.classList.contains('ve-laptop')")


# --- מצבים ריקים ---

def test_every_panel_has_a_useful_empty_state(editor_page):
    page = editor_page
    page.evaluate("() => _renderVeQueue()")
    assert "עוד לא נבחרה תיקייה" in page.inner_text("#veQueueList")
    assert page.locator("#veQueueList .ve-empty button:has-text('בחר תיקייה')").count() == 1
    page.evaluate("() => { _veLayersListSignature = null; _veRenderLayersList(); }")
    empty = page.locator("#veLayersList .ve-empty")
    assert "עוד אין שכבות" in empty.inner_text() and "גרור תמונה לכאן" in empty.inner_text()
    page.click("#veLayersList .ve-empty button:has-text('טקסט')")
    assert page.evaluate("() => _veLayersValue().length") == 1 and page.locator("#veLayersList .ve-empty").count() == 0
    page.evaluate("() => { _veRunsCache = []; _renderVeRuns(); }")
    assert "עוד אין ריצות" in page.text_content("#veRunsList")  # מגירת הריצות סגורה
    assert page.evaluate("() => getComputedStyle(document.getElementById('veTimelineEmpty')).display") != "none"


# --- היררכיה ויזואלית ---

HIERARCHY = """() => {
    const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !el.closest('[hidden]'); };
    const transparent = (c) => /rgba\\(0, 0, 0, 0\\)|transparent/.test(c);
    const emphasized = (b) => b.classList.contains('btn-run') || b.classList.contains('ve-primary');
    const areas = [...document.querySelectorAll('#veCategories > details, .ve-side-panel, #veViewer details[data-cat=preview]')];
    const perArea = areas.map(a => [...a.querySelectorAll('button')].filter(b => visible(b) && emphasized(b)).length);
    const plain = [...document.querySelectorAll('#veCategories .ve-category-body button')].filter(b => visible(b)
        && !b.closest('.ve-chips, .ve-mode-toggle, .ve-split, .ve-look-cards') && b.getAttribute('aria-pressed') !== 'true' && !emphasized(b));
    const quiet = plain.filter(b => transparent(getComputedStyle(b).borderTopColor)).length;
    const skip = (el) => /^(BUTTON|INPUT|SELECT|TEXTAREA|IMG|VIDEO|CANVAS|SPAN|LABEL|SUMMARY)$/.test(el.tagName) || el.getBoundingClientRect().width < 140 || el.getBoundingClientRect().height < 30;
    const boxed = (el) => { const s = getComputedStyle(el); return (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none' && !transparent(s.borderTopColor) && parseFloat(s.borderLeftWidth) > 0)
        || (!transparent(s.backgroundColor) && s.backgroundColor !== getComputedStyle(el.parentElement).backgroundColor); };
    let depth = 0;
    for (const root of [document.getElementById('veCategories'), document.getElementById('veSide')]) {
        for (const el of root.querySelectorAll('*')) {
            if (!visible(el) || skip(el) || !boxed(el)) continue;
            let d = 1, p = el.parentElement;
            while (p && p !== root.parentElement) { if (!skip(p) && boxed(p)) d++; p = p.parentElement; }
            depth = Math.max(depth, d);
        }
    }
    return {perArea, quiet, plain: plain.length, depth};
}"""


def test_one_primary_action_per_area_and_no_card_in_card_in_card(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    page.evaluate("() => { addVeLayerCard('logo'); addVeLayer('text'); addVeLayer('image'); }")
    _settle(page)
    result = page.evaluate(HIERARCHY)
    assert max(result["perArea"]) <= 1, result
    assert result["plain"] > 20 and result["quiet"] / result["plain"] >= 0.9, result  # כפתור רגיל שקט, בלי מסגרת
    assert result["depth"] <= 2, result
