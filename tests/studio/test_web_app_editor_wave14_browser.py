# tests/studio/test_web_app_editor_wave14_browser.py
#
# גל 14 בדפדפן אמיתי: ציר-זמן מקצועי (זום, צעד בחיצים, I/O, הצמדה), keyframes
# לשכבות (טבלה + גרירה בזמן מסוים), סקופים, שגיאות עם כפתורי תיקון, ותור הרינדור.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _opts(page):
    return page.evaluate("() => _collectRunOptions()")


def _fake_timeline(page, duration=100):
    page.evaluate("""(d) => { _veTimeline = {path: 'x.mp4', duration: d};
        document.getElementById('veTimelineBox').hidden = false;
        document.getElementById('veTimeline').scrollIntoView({block: 'center'});
        _veRenderTimelineOverlays(); }""", duration)


def _show_fake_frame(page, color="#3366cc", width=320, height=180):
    page.evaluate("""([color, w, h]) => new Promise(resolve => {
        const c = document.createElement('canvas'); c.width = w; c.height = h;
        const ctx = c.getContext('2d'); ctx.fillStyle = color; ctx.fillRect(0, 0, w, h); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w / 4, h);
        const url = c.toDataURL('image/png'); const after = document.getElementById('vePreviewAfter');
        after.onload = () => resolve(); document.getElementById('vePreviewBefore').src = url; after.src = url;
        document.getElementById('vePreviewStageWrap').hidden = false; })""", [color, width, height])


def _settle(page):
    """גל 23: מחכים שכל רענון ה-UI הנגזר (debounced) הסתיים - לא לזמן קבוע."""
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def test_timeline_zoom_widens_the_strip(editor_page):
    page = editor_page
    _fake_timeline(page)
    page.evaluate("() => setVeTimelineZoom(4)")
    ratio = page.evaluate("() => document.getElementById('veTimeline').getBoundingClientRect().width / document.getElementById('veTimelineScroll').clientWidth")
    assert 3.8 < ratio < 4.2
    assert page.inner_text("#veTimelineZoomLabel") == "×4"
    page.evaluate("() => setVeTimelineZoom(1)")
    assert page.inner_text("#veTimelineZoomLabel") == "התאם"


def test_timeline_keyboard_steps_and_in_out_marks(editor_page):
    page = editor_page
    _fake_timeline(page)
    page.evaluate("() => { _veTimelineCursor = 10; }")
    page.focus("#veTimeline")
    page.keyboard.press("Shift+ArrowRight")
    assert page.evaluate("() => _veTimelineCursor") == pytest.approx(11, abs=0.01)
    page.keyboard.press("ArrowRight")
    assert page.evaluate("() => _veTimelineCursor") == pytest.approx(11 + 1 / 30, abs=0.01)
    page.keyboard.press("i")
    _settle(page)
    assert _opts(page)["trim_start"] == pytest.approx(11, abs=0.1)
    page.evaluate("() => { _veTimelineCursor = 40; }")
    page.keyboard.press("o")
    _settle(page)
    opts = _opts(page)
    assert opts["trim_start"] + opts["trim_duration"] == pytest.approx(40, abs=0.1)


def test_dragging_trim_snaps_to_scene_cut(editor_page):
    page = editor_page
    _fake_timeline(page)
    page.evaluate("() => { _veSceneCuts = {file: document.getElementById('vePreviewFile').value, cuts: [30]}; _veRenderTimelineOverlays(); }")
    assert page.evaluate("() => document.querySelectorAll('#veTimelineOverlays .ve-tl-scene').length") == 1
    timeline = page.locator("#veTimeline").bounding_box()
    y = timeline["y"] + timeline["height"] / 2
    handle = page.locator("#veTlHandle-start").bounding_box()
    page.mouse.move(handle["x"] + handle["width"] * 0.75, y)
    page.mouse.down()
    page.mouse.move(timeline["x"] + timeline["width"] * 0.297, y, steps=6)
    page.mouse.up()
    _settle(page)
    assert _opts(page)["trim_start"] == pytest.approx(30, abs=0.01)


def test_keyframes_table_and_drag_create_keyframes(editor_page):
    page = editor_page
    _show_fake_frame(page)
    page.evaluate("() => { addVeLayer('text'); const l = _veLayersValue(); l[0].text = 'KF'; _veWriteLayers(l); _veRenderLayersEditor(true); }")
    page.evaluate("() => { document.getElementById('vePreviewTime').value = '0'; addVeKeyframe(0); document.getElementById('vePreviewTime').value = '2'; addVeKeyframe(0); }")
    layer = page.evaluate("() => _veLayersValue()[0]")
    assert [f["t"] for f in layer["keyframes"]] == [0, 2]
    assert page.inner_text("#veLayersRows .ve-kf-toggle") == "◆ 2"
    assert page.evaluate("() => document.querySelectorAll('.ve-kf-panel .ve-kf-row').length") == 2
    # עריכת x בטבלה
    page.fill(".ve-kf-panel .ve-kf-row >> nth=1 >> input[aria-label='x (%)']", "80")
    page.dispatch_event(".ve-kf-panel .ve-kf-row >> nth=1 >> input[aria-label='x (%)']", "change")
    assert page.evaluate("() => _veLayersValue()[0].keyframes[1].x") == pytest.approx(0.8)
    # גרירה בזמן 1 -> מפתח חדש באמצע
    page.evaluate("() => { document.getElementById('vePreviewTime').value = '1'; _veRenderDragHandles(); document.getElementById('vePreviewStage').scrollIntoView({block: 'center'}); }")
    # הידית מופיעה אחרי שהפריים והפריסה מוכנים - מחכים לה (ב-CI היא עוד לא הייתה גלויה). קודם מחכים שהרענון
    # המושהה (ve:derived-cards, מעריכת ה-x בטבלה) ייגמר: הוא מצייר את הידיות מחדש, וידית שהוחלפה בין ההמתנה
    # למדידה החזירה bounding_box None (1 מתוך 20 תחת עומס)
    _settle(page)
    page.wait_for_selector("#veDragHandles [data-kind=layer]", state="visible")
    stage = page.locator("#vePreviewStage").bounding_box()
    box = page.locator("#veDragHandles [data-kind=layer]").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(stage["x"] + stage["width"] * 0.3, stage["y"] + stage["height"] * 0.6, steps=5)
    page.mouse.up()
    _settle(page)
    frames = page.evaluate("() => _veLayersValue()[0].keyframes")
    assert [f["t"] for f in frames] == [0, 1, 2]
    assert frames[1]["x"] == pytest.approx(0.3, abs=0.03) and frames[1]["y"] == pytest.approx(0.6, abs=0.03)


def test_scopes_draw_from_the_current_frame(editor_page):
    page = editor_page
    _show_fake_frame(page)
    page.click("#veScopesBtn")
    page.wait_for_function("() => !document.getElementById('veScopes').hidden")
    lit = page.evaluate("""() => { const c = document.getElementById('veScopeHist'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 60) n++; return n; }""")
    assert lit > 50
    assert page.inner_text("#veScopesNote")


def test_failed_file_gets_explanation_and_fix_buttons(editor_page):
    page = editor_page
    page.evaluate("""() => _veShowResults({mode: 'render', counts: {errors: 1}, files: [
        {source: 'a.mp4', status: 'error', reason: '[hevc_nvenc] OpenEncodeSessionEx failed: out of memory'}]})""")
    page.wait_for_selector("#veResultsList .ve-fix-box")
    assert "כרטיס המסך" in page.inner_text("#veResultsList .ve-fix-title")
    fixes = page.evaluate("() => [...document.querySelectorAll('#veResultsList .ve-fix-actions button')].map(b => b.dataset.fix)")
    assert fixes == ["retry_serial", "retry_cpu", "retry"]


def test_render_queue_panel_pause_and_busy_settings(editor_page):
    page = editor_page
    page.click("#veFolderChip")  # גל 27: "כל העבודות" בתפריט של שבב התיקייה
    page.click("#veJobsBtn")
    page.wait_for_function("() => document.getElementById('veRenderQueueStatus').textContent.length > 0")
    page.click("#veQueuePauseBtn")
    page.wait_for_function("() => document.getElementById('veRenderQueueStatus').textContent.includes('מושהה')")
    page.click("#veQueuePauseBtn")
    page.wait_for_function("() => !document.getElementById('veRenderQueueStatus').textContent.includes('מושהה')")
    page.fill("#veBusyProcesses", "definitely-not-running.exe")
    page.check("#veWaitWhenBusy")
    page.wait_for_function("() => document.getElementById('veBusyNow').textContent.includes('פנוי')")


def test_run_priority_is_sent_but_not_part_of_the_recipe(editor_page):
    page = editor_page
    before = page.evaluate("() => _veComparableOptionsJson()")
    page.evaluate("() => { document.getElementById('veRunPriority').checked = true; }")
    assert _opts(page)["priority"] == "high"
    assert page.evaluate("() => _veComparableOptionsJson()") == before
