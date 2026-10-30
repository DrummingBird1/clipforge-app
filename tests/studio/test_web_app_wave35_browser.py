# tests/studio/test_web_app_wave35_browser.py
#
# גל 35 בדפדפן: תור ברשת, מיון וקיבוץ, תגיות צבע כפעולה קבוצתית, ✅ שמוביל לתוצר, הקובץ הקודם/הבא,
# סימנים עם שם, מיני-מפה בזום, זמן שאפשר להקליד, עריכת קליפ על ציר-הזמן ונעילת מסלול שלם.
# ציר-הזמן בלי ffmpeg (ה-CI בלי ffmpeg): משך ידוע ופס תמונות ריק, כמו בטסטי גל 29.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

IDLE = "() => typeof uiPendingWork === 'function' && uiPendingWork() === 0"


def _folder(page, folder, names=("a.mp4", "b.mp4", "c.mp4")):
    for name in names:
        (folder / name).write_bytes(b"x")
    page.evaluate("() => _veSavePref('veAutoFrame', false)")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function("(n) => (_veQueueState || []).length === n && document.getElementById('vePreviewFile').options.length === n",
                           arg=len(names), timeout=15000)
    page.wait_for_function(IDLE)


def _fake_timeline(page, duration=60):
    page.evaluate("""(d) => {
        const c = document.createElement('canvas'); c.width = 800; c.height = 60;
        _veTimeline = {path: 'a.mp4', duration: d};
        document.getElementById('veTimelineImg').src = c.toDataURL('image/png');
        document.getElementById('veTimelineBox').hidden = false;
        _veRenderLayersTrack();
        _veRenderTimelineOverlays();
    }""", duration)
    page.wait_for_function(IDLE)


def test_queue_tags_group_sort_and_grid(editor_page, tmp_path):
    page = editor_page
    _folder(page, tmp_path)
    page.evaluate("() => { _veQueueState.forEach((f, i) => { f._picked = i > 0; }); setVeQueueTag('red'); }")
    tags = page.evaluate("() => [...document.querySelectorAll('#veQueueList .ve-queue-row')].map(r => (r.querySelector('.ve-queue-tag') || {}).dataset?.tag || '')")
    assert tags == ["", "red", "red"]
    page.select_option("#veQueueGroup", "tag")
    names = page.evaluate("() => _veQueueState.map(f => f.name)")
    assert names == ["b.mp4", "c.mp4", "a.mp4"]   # התגית קודם, בלי תגית בסוף
    labels = page.evaluate("() => [...document.querySelectorAll('#veQueueList .ve-queue-row')].map(r => r.dataset.groupLabel || '')")
    assert labels[0].endswith("אדום") and labels[1] == "" and labels[2] == "בלי תגית"
    page.select_option("#veQueueGroup", "")
    page.select_option("#veQueueSort", "name")
    assert page.evaluate("() => _veQueueState.map(f => f.name)") == ["a.mp4", "b.mp4", "c.mp4"]
    assert page.input_value("#veQueueSort") == ""   # מיון הוא פעולה, לא מצב
    page.click("#veQueueGridBtn")
    assert page.evaluate("() => document.getElementById('veQueueList').classList.contains('ve-queue-grid')")
    assert page.get_attribute("#veQueueGridBtn", "aria-pressed") == "true"


def test_rendered_badge_leads_to_the_output(editor_page, tmp_path):
    page = editor_page
    _folder(page, tmp_path)
    page.evaluate("""() => { _veQueueLastRun = {'a.mp4': {source: 'a.mp4', status: 'created', output: 'C:/out/a.mp4'}, __when: Date.now()};
        _renderVeQueue(); }""")
    badge = page.evaluate("() => { const b = document.querySelector('#veQueueList .ve-queue-row[data-name=\"a.mp4\"] .ve-badge-status'); return b && b.getAttribute('role'); }")
    assert badge == "button"


def test_previous_and_next_file_in_the_queue(editor_page, tmp_path):
    page = editor_page
    _folder(page, tmp_path)
    page.evaluate("() => { const s = document.getElementById('vePreviewFile'); s.selectedIndex = 0; s.dispatchEvent(new Event('change')); }")
    assert page.is_disabled("#vePrevFileBtn")
    page.click("#veNextFileBtn")
    assert page.evaluate("() => document.getElementById('vePreviewFile').selectedIndex") == 1
    page.click("#veNextFileBtn")
    assert page.is_disabled("#veNextFileBtn")
    page.click("#vePrevFileBtn")
    assert page.evaluate("() => document.getElementById('vePreviewFile').selectedIndex") == 1


def test_named_markers_minimap_and_typed_time(editor_page, tmp_path):
    page = editor_page
    _folder(page, tmp_path)
    _fake_timeline(page)
    page.fill("#veTimecodeInput", "0:30")
    page.press("#veTimecodeInput", "Enter")
    assert page.evaluate("() => _veTimelineCursor") == 30
    page.evaluate("() => { vePrompt = async () => 'פתיחה'; }")
    page.evaluate("() => addVeMarker()")
    page.wait_for_function("() => !!document.querySelector('#veTimelineOverlays .ve-tl-marker')")
    assert page.evaluate("() => document.querySelector('#veTimelineOverlays .ve-tl-marker').dataset.name") == "פתיחה"
    assert page.evaluate("() => _veMarkers()") == [{"t": 30, "name": "פתיחה"}]
    # הסימן שייך לקובץ - בקובץ אחר אין אותו
    page.evaluate("() => { const s = document.getElementById('vePreviewFile'); s.selectedIndex = 1; }")
    assert page.evaluate("() => _veMarkers()") == []
    page.evaluate("() => { const s = document.getElementById('vePreviewFile'); s.selectedIndex = 0; }")
    # מיני-מפה רק בזום
    page.evaluate("() => setVeTimelineZoom(4)")
    assert page.evaluate("() => !document.getElementById('veTlMinimap').hidden")
    assert page.evaluate("() => document.querySelectorAll('#veTlMinimap .ve-tl-minimap-marker').length") == 1
    page.evaluate("() => setVeTimelineZoom(1)")
    assert page.evaluate("() => document.getElementById('veTlMinimap').hidden")


def test_clip_edit_shows_on_the_timeline_and_whole_track_lock(editor_page, tmp_path):
    page = editor_page
    _folder(page, tmp_path)
    _fake_timeline(page)
    page.evaluate("() => { enterVeClipMode('a.mp4'); _veRenderTimelineOverlays(); }")
    assert page.evaluate("() => document.getElementById('veTimelineDock').classList.contains('ve-timeline-clip')")
    assert "a.mp4" in page.evaluate("() => document.getElementById('veTimelineDock').dataset.clipLabel")
    page.evaluate("() => { exitVeClipMode(); _veRenderTimelineOverlays(); }")
    assert not page.evaluate("() => document.getElementById('veTimelineDock').classList.contains('ve-timeline-clip')")
    page.evaluate("""() => { _veWriteLayers([{type: 'text', text: 'שלום', start: 0, end: 5}, {type: 'text', text: 'עוד', start: 6, end: 9}]);
        _veRenderLayersEditor(true); _veRenderLayersTrack(); _veRenderTimelineOverlays(); }""")
    page.wait_for_function(IDLE)
    page.evaluate("() => toggleVeTrackLock('layers')")
    assert page.evaluate("() => _veLayersValue().every(l => l.locked)")
    page.evaluate("() => _veRenderTimelineOverlays()")
    # הכפתור במסלול מראה שהמסלול נעול (כשתגיות המסלולים קיימות)
    assert page.evaluate("""() => { const b = document.querySelector('.ve-track-tag-row[data-track=layers] .ve-track-lock');
        return !b || b.getAttribute('aria-pressed') === 'true'; }""")
    page.evaluate("() => toggleVeTrackLock('layers')")
    assert page.evaluate("() => _veLayersValue().every(l => !l.locked)")
