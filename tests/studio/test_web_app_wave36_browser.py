# tests/studio/test_web_app_wave36_browser.py
#
# גל 36 בדפדפן: קבוצות שכבות (הסתרה ונעילה לקבוצה), המיתוג כשורה נעולה, יישור ופיזור, קווי עזר,
# שכבות מוכנות מובנות בספרייה, מרכז הריצות, שם ותגיות + השוואה בין ריצות, תזמון מהגיליון,
# "פתח את הפרויקט" מהתוצאות, תבניות יצוא, ויחידות שאפשר לגרור.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

IDLE = "() => typeof uiPendingWork === 'function' && uiPendingWork() === 0"


def _set_layers(page, layers):
    page.evaluate("(l) => { _veWriteLayers(l); _veRenderLayersEditor(true); _veRenderLayersList(); }", layers)
    page.wait_for_function(IDLE)


def test_layer_groups_hide_and_lock_together(editor_page):
    page = editor_page
    _set_layers(page, [{"type": "text", "text": "A", "start": 0, "end": 3, "group": "פתיח"},
                       {"type": "text", "text": "B", "start": 0, "end": 3, "group": "פתיח"},
                       {"type": "text", "text": "C", "start": 0, "end": 3}])
    headers = page.eval_on_selector_all("#veLayersList .ve-ll-group", "els => els.map(e => e.dataset.group)")
    assert headers == ["פתיח"]
    assert page.evaluate("() => document.querySelectorAll('#veLayersList .ve-ll-in-group').length") == 2
    page.click("#veLayersList .ve-ll-group button[aria-label='הסתר את כל הקבוצה']")
    assert page.evaluate("() => _veLayersValue().map(l => !!l.hidden)") == [True, True, False]
    page.click("#veLayersList .ve-ll-group button[aria-label='נעל את כל הקבוצה']")
    assert page.evaluate("() => _veLayersValue().map(l => !!l.locked)") == [True, True, False]
    page.evaluate("() => ungroupVe('פתיח')")
    assert page.evaluate("() => _veLayersValue().every(l => !l.group)")
    assert page.evaluate("() => document.querySelectorAll('#veLayersList .ve-ll-group').length") == 0


def test_align_and_distribute_layers(editor_page):
    page = editor_page
    _set_layers(page, [{"type": "text", "text": "A", "start": 0, "end": 30, "position": "top-left"},
                       {"type": "text", "text": "B", "start": 0, "end": 30, "position": "bottom-center"},
                       {"type": "text", "text": "C", "start": 0, "end": 30, "position": "center"}])
    page.evaluate("() => _veSelectObject('layer', 0, {quiet: true})")
    page.evaluate("() => alignVeLayer('hcenter')")
    first = page.evaluate("() => _veLayersValue()[0]")
    assert first["position"] == "custom" and first["x"] == 0.5 and first["y"] == 0.1
    page.evaluate("() => alignVeLayer('bottom')")
    assert page.evaluate("() => _veLayersValue()[0].y") == 0.9
    page.evaluate("() => _veSetFieldValue(document.getElementById('veLayers'), JSON.stringify(_veLayersValue().map((l, i) => ({...l, position: 'custom', x: [0.2, 0.3, 0.8][i], y: 0.5}))))")
    page.evaluate("() => distributeVeLayers()")
    xs = page.evaluate("() => _veLayersValue().map(l => l.x)")
    assert xs == [0.2, 0.5, 0.8]
    # קווי עזר בנגן (הכפתור בשורת הכלים של הנגן, שמוצגת רק כשיש קובץ - כאן קוראים לפעולה עצמה)
    page.evaluate("() => toggleVeGuides()")
    assert page.evaluate("() => document.getElementById('vePreviewStage').classList.contains('ve-guides-on')")
    assert page.get_attribute("#veGuidesBtn", "aria-pressed") == "true"


def test_branding_shows_as_a_locked_row_and_builtin_ready_layers(editor_page):
    page = editor_page
    page.evaluate("""() => { const s = document.getElementById('veBrandKit'); s.add(new Option('הערוץ שלי', 'הערוץ שלי')); s.value = 'הערוץ שלי';
        _veRenderLayersList(); }""")
    assert "הערוץ שלי" in page.inner_text("#veLayersList .ve-ll-brand")
    page.evaluate("() => openVeLibrary('ready')")
    page.wait_for_function("() => document.querySelectorAll('#veLibraryList .ve-ready-preview').length >= 4")
    page.click("#veLibraryList .ve-library-item:first-child button")
    assert page.evaluate("() => _veLayersValue().some(l => l.type === 'text' && l.position === 'bottom-left')")


def test_runs_center_labels_and_compare(editor_page):
    page = editor_page
    runs = [
        {"id": "r1", "folder": "C:/a", "started_at": "2026-10-15T10:00:00", "status": "success", "settings": {"codec": "h264", "fps": 30}, "files_created": 2},
        {"id": "r2", "folder": "C:/a", "started_at": "2026-10-15T11:00:00", "status": "success", "settings": {"codec": "hevc", "fps": 30}, "files_created": 2},
    ]
    # פתיחת המגירה טוענת את ההיסטוריה מהשרת (ריקה בטסט) - ההיסטוריה המזויפת נכנסת דרך loadVeRuns עצמה
    page.evaluate("""(r) => { loadVeRuns = async () => { _veRunsCache = r; _renderVeRuns(); };
        document.getElementById('veRunsDrawer').open = true; loadVeRuns(); }""", runs)
    page.wait_for_function("() => document.querySelectorAll('#veRunsList .ve-run-row').length === 2")
    assert page.is_disabled("#veHubCompareBtn")
    # כל סימון בונה את הרשימה מחדש - בוחרים מחדש כל פעם; לחיצה בקוד (המגירה בתחתית, מתחת לשורת הסטטוס)
    for run_id in ("r1", "r2"):
        page.evaluate("(id) => document.querySelector(`#veRunsList .ve-run-row[data-run-id='${id}'] .ve-run-compare-pick input`).click()", run_id)
    assert not page.is_disabled("#veHubCompareBtn")
    page.evaluate("() => document.getElementById('veHubCompareBtn').click()")
    assert page.is_visible("#veRunCompareModalBg")
    diff = page.eval_on_selector_all("#veRunCompareBody tr.ve-compare-diff", "rows => rows.map(r => r.cells[0].textContent)")
    assert len(diff) == 1   # רק הקודק שונה
    page.evaluate("() => closeVeRunCompare()")
    page.evaluate("() => refreshVeRunsHub()")
    page.wait_for_function("() => document.getElementById('veHubHistory').textContent.startsWith('2')")


def test_schedule_from_the_run_sheet_and_project_from_results(editor_page, tmp_path):
    page = editor_page
    page.evaluate("() => { window.__scheduled = 0; openVeScheduleDialog = () => { window.__scheduled++; }; }")
    page.evaluate("() => scheduleFromVeRunSheet()")
    assert page.evaluate("() => window.__scheduled") == 1
    page.evaluate("(f) => { _veSyncResultsProject({input_dir: f}); }", str(tmp_path))
    assert page.is_visible("#veResultsProjectBtn") or not page.evaluate("() => document.getElementById('veResultsProjectBtn').hidden")
    page.evaluate("() => openVeResultsProject()")
    assert page.evaluate("() => state.folder") == str(tmp_path)


def test_export_templates_and_dragging_units(editor_page):
    page = editor_page
    page.evaluate("() => { vePrompt = async () => 'YouTube 4K'; }")
    page.evaluate("() => _veSetFieldValue(document.getElementById('veCodec'), 'av1')")
    page.evaluate("() => saveVeExportTemplate()")
    page.wait_for_function("() => [...document.getElementById('veExportTemplate').options].some(o => o.value === 'YouTube 4K')")
    page.evaluate("() => _veSetFieldValue(document.getElementById('veCodec'), 'h264')")
    page.select_option("#veExportTemplate", "YouTube 4K")
    assert page.input_value("#veCodec") == "av1"
    assert page.evaluate("() => document.getElementById('veGifFps').nextElementSibling.classList.contains('ve-scrub')")
