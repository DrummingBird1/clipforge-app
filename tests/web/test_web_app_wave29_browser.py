# tests/web/test_web_app_wave29_browser.py
#
# גל 29 בדפדפן אמיתי - ציר-הזמן והנגן כמשטח העריכה: פסי שכבות נגררים ומשנים אורך על
# ציר-הזמן (עם הצמדה), מסלול B-roll נפרד וציר-זמן שמשנה גובה, בחירה מסונכרנת בין
# הנגן/ציר-הזמן/הרשימה, סרגל צף וידית שינוי גודל, רשימת שכבות (שם, 👁, 🔒, שכפול,
# סדר), וגרירת קבצים מהמחשב לציר-הזמן ולנגן.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(page):
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _fake_timeline(page, folder, duration=20):
    """ציר-זמן בלי ffmpeg: תיקייה עם קובץ, משך ידוע ופס תמונות ריק - מספיק לגרירות."""
    (folder / "clip.mp4").write_bytes(b"x")
    # בלי פתיחה אוטומטית של הנגן (גל 27): הבמה שמופיעה מעל הציר באיחור מזיזה את הפסים אחרי שנמדדו
    page.evaluate("() => _veSavePref('veAutoFrame', false)")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function("() => document.getElementById('vePreviewFile').options.length > 0", timeout=15000)
    page.evaluate("""(d) => {
        const c = document.createElement('canvas'); c.width = 800; c.height = 60;
        _veTimeline = {path: 'clip.mp4', duration: d};
        document.getElementById('veTimelineImg').src = c.toDataURL('image/png');
        document.getElementById('veTimelineBox').hidden = false;
        document.getElementById('veTimelineSnap').checked = false;
        _veRenderLayersTrack();
        document.getElementById('veTimelineDock').scrollIntoView({block: 'center'});
    }""", duration)
    _settle(page)


def _set_layers(page, layers):
    page.evaluate("(l) => { _veWriteLayers(l); _veRenderLayersEditor(true); _veRenderLayersTrack(); }", layers)
    _settle(page)


def _bar(page, index):
    return page.locator(f".ve-tl-layer[data-index='{index}']")


def _drag(page, selector, dx, edge=None):
    """גרירה עם העכבר. selector הוא CSS (לא locator): הפס/הטווח נבנה מחדש ברענוני רקע, ואלמנט
    שכבר הוחלף נמדד כאפסים - לכן מאתרים מחדש בכל פריים, ולוחצים רק כשהמיקום יציב 3 פריימים
    (בניית עורך השכבות מחדש יכולה להזיז את הגריד, ואיתו את ציר-הזמן, כמה פיקסלים)."""
    css = f"{selector} .ve-tl-edge[data-edge='{edge}']" if edge else selector
    box = page.evaluate("""(css) => new Promise(resolve => {
        let last = null, stable = 0;
        const tick = () => {
            const el = document.querySelector(css);
            const r = el ? el.getBoundingClientRect() : null;
            const key = r && r.width ? [r.left, r.top, r.width].join() : null;
            if (key && key === last && ++stable >= 3) return resolve({x: r.left, y: r.top, width: r.width, height: r.height});
            if (key !== last) { last = key; stable = 0; }
            requestAnimationFrame(tick);
        };
        tick();
    })""", css)
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y, steps=4)
    page.mouse.move(x + dx, y, steps=4)
    page.mouse.up()
    _settle(page)


def _px_per_second(page, duration=20):
    return page.evaluate("() => document.getElementById('veTimeline').getBoundingClientRect().width") / duration


def test_layer_bars_move_and_resize_on_the_timeline(editor_page, tmp_path):
    page = editor_page
    _fake_timeline(page, tmp_path)
    _set_layers(page, [{"type": "text", "text": "Title", "start": 2, "end": 6}, {"type": "video", "path": "C:\\b.mp4", "start": 8, "end": 12}])
    # B-roll במסלול משלו
    assert page.evaluate("() => document.querySelector('#veTlBrollTrack .ve-tl-layer').dataset.index") == "1"
    assert page.evaluate("() => document.querySelector('#veTlLayersTrack .ve-tl-layer').dataset.index") == "0"
    pps = _px_per_second(page)
    _drag(page, ".ve-tl-layer[data-index='0']", 3 * pps)  # הזזה ב-3 שניות
    layer = page.evaluate("() => _veLayersValue()[0]")
    assert abs(layer["start"] - 5) <= 0.3 and abs(layer["end"] - 9) <= 0.3
    _drag(page, ".ve-tl-layer[data-index='0']", 2 * pps, edge="end")  # הארכה
    layer = page.evaluate("() => _veLayersValue()[0]")
    assert abs(layer["start"] - 5) <= 0.3 and abs(layer["end"] - 11) <= 0.3
    _drag(page, ".ve-tl-layer[data-index='0']", -1 * pps, edge="start")
    assert abs(page.evaluate("() => _veLayersValue()[0].start") - 4) <= 0.3
    # הצמדה: פס שנגרר ליד קצה של שכבה אחרת נצמד אליו
    page.evaluate("() => { document.getElementById('veTimelineSnap').checked = true; }")
    title_end = page.evaluate("() => _veLayersValue()[0].end")
    _drag(page, ".ve-tl-layer[data-index='1']", (title_end + 0.12 - 8) * pps)  # B-roll מ-8 עד קצת אחרי סוף הכותרת - נצמד אליו
    assert abs(page.evaluate("() => _veLayersValue()[1].start") - title_end) <= 0.05
    # שכבה נעולה לא זזה
    page.evaluate("() => toggleVeLayerFlag(0, 'locked')")
    before = page.evaluate("() => _veLayersValue()[0].start")
    _drag(page, ".ve-tl-layer[data-index='0']", 3 * pps)
    assert page.evaluate("() => _veLayersValue()[0].start") == before


def test_clicking_an_object_selects_it_everywhere_and_opens_its_settings(editor_page, tmp_path):
    page = editor_page
    _fake_timeline(page, tmp_path)
    _set_layers(page, [{"type": "text", "text": "A", "start": 1, "end": 4}, {"type": "text", "text": "B", "start": 5, "end": 9}])
    _bar(page, 1).click()
    assert page.evaluate("() => _veSelected && _veSelected.kind === 'layer' && _veSelected.index === 1")
    page.wait_for_function("() => document.querySelector('#veLayersList .ve-ll-row[data-index=\"1\"]').classList.contains('ve-selected')")
    assert page.evaluate("() => document.querySelector('.ve-tl-layer[data-index=\"1\"]').classList.contains('ve-selected')")
    # הרשימה: העליונה (האחרונה במערך) למעלה
    order = page.evaluate("() => [...document.querySelectorAll('#veLayersList .ve-ll-row[data-kind=layer]')].map(r => r.dataset.index)")
    assert order == ["1", "0"]
    page.keyboard.press("Escape")
    assert page.evaluate("() => _veSelected") is None


def test_the_layers_list_names_hides_locks_duplicates_and_reorders(editor_page):
    page = editor_page
    _set_layers(page, [{"type": "text", "text": "A", "start": 0, "end": 3}, {"type": "text", "text": "B", "start": 0, "end": 3}])
    row = "#veLayersList .ve-ll-row[data-index='0']"
    page.fill(f"{row} .ve-ll-name", "כותרת פתיחה")
    page.dispatch_event(f"{row} .ve-ll-name", "change")
    assert page.evaluate("() => _veLayersValue()[0].name") == "כותרת פתיחה"
    page.click(f"{row} button[aria-label^='הסתר']")
    assert page.evaluate("() => _veLayersValue()[0].hidden") is True
    # שכבה מוסתרת לא נשלחת לרינדור (השרת מדלג עליה) אבל נשמרת
    assert page.evaluate("() => _collectRunOptions().layers.length") == 2
    page.click("#veLayersList .ve-ll-row[data-index='0'] button[aria-label^='נעל']")
    assert page.evaluate("() => _veLayersValue()[0].locked") is True
    page.click("#veLayersList .ve-ll-row[data-index='1'] button[aria-label='שכפל']")
    assert page.evaluate("() => _veLayersValue().map(l => l.text)") == ["A", "B", "B"]
    page.evaluate("() => moveVeLayer(0, 2)")
    assert page.evaluate("() => _veLayersValue().map(l => l.text)") == ["B", "B", "A"]
    page.click("#veLayersList .ve-ll-row[data-index='2'] button[aria-label='מחק']")
    assert page.evaluate("() => _veLayersValue().map(l => l.text)") == ["B", "B"]


def test_the_timeline_resizes_and_remembers_its_height(editor_page, tmp_path):
    page = editor_page
    _fake_timeline(page, tmp_path)
    grip = page.locator("#veTlResizer").bounding_box()
    before = page.evaluate("() => document.getElementById('veTimelineImg').getBoundingClientRect().height")
    page.mouse.move(grip["x"] + grip["width"] / 2, grip["y"] + 3)
    page.mouse.down()
    page.mouse.move(grip["x"] + grip["width"] / 2, grip["y"] - 57, steps=5)
    page.mouse.up()
    after = page.evaluate("() => document.getElementById('veTimelineImg').getBoundingClientRect().height")
    assert after > before + 40, (before, after)
    assert page.evaluate("() => _veLoadPref('veTimelineHeight', 0)") >= 100


def _drop_file(page, selector, name, data, mime, client_x_fraction=0.5):
    page.evaluate("""([selector, name, data, mime, fx]) => {
        const zone = document.querySelector(selector);
        const rect = zone.getBoundingClientRect();
        const dt = new DataTransfer();
        dt.items.add(new File([new Uint8Array(data)], name, {type: mime}));
        const opts = {bubbles: true, cancelable: true, dataTransfer: dt, clientX: rect.left + rect.width * fx, clientY: rect.top + rect.height / 2};
        zone.dispatchEvent(new DragEvent('dragover', opts));
        zone.dispatchEvent(new DragEvent('drop', opts));
    }""", [selector, name, list(data), mime, client_x_fraction])


def test_dropping_files_on_the_timeline_and_player(editor_page, tmp_path):
    page = editor_page
    _fake_timeline(page, tmp_path)
    # וידאו באמצע ציר-הזמן = B-roll באותו זמן
    _drop_file(page, "#veTimelineScroll", "broll.mp4", b"video", "video/mp4", 0.5)
    page.wait_for_function("() => _veLayersValue().some(l => l.type === 'video')")
    layer = page.evaluate("() => _veLayersValue().find(l => l.type === 'video')")
    assert abs(layer["start"] - 10) <= 0.6 and layer["path"].endswith("broll.mp4")
    assert "editor_assets" in layer["path"] and not (tmp_path / "broll.mp4").exists()  # לא נכנס לתור
    # וידאו בקצה ההתחלה = פתיח; שמע = פס-קול
    _drop_file(page, "#veTimelineScroll", "intro.mp4", b"video", "video/mp4", 0.01)
    page.wait_for_function("() => document.getElementById('veIntroPath').value.endsWith('intro.mp4')")
    _drop_file(page, "#veTimelineScroll", "music.mp3", b"audio", "audio/mpeg", 0.5)
    page.wait_for_function("() => document.getElementById('veReplaceAudioPath').value.endsWith('music.mp3')")
    # תמונה על הנגן = לוגו במקום שבו נזרקה (ואז מדבקה)
    page.evaluate("() => { document.getElementById('vePreviewStageWrap').hidden = false; }")
    _drop_file(page, "#vePreviewStage", "logo.png", b"png", "image/png", 0.8)
    page.wait_for_function("() => document.getElementById('veWatermarkPath').value.endsWith('logo.png')")
    assert abs(page.evaluate("() => parseFloat(document.getElementById('veWatermarkX').value)") - 0.8) <= 0.02
    _drop_file(page, "#vePreviewStage", "sticker.png", b"png", "image/png", 0.3)
    page.wait_for_function("() => _veLayersValue().some(l => l.type === 'image' && l.path.endsWith('sticker.png'))")


def test_removal_ranges_move_resize_and_delete_on_the_timeline(editor_page, tmp_path):
    page = editor_page
    _fake_timeline(page, tmp_path)
    page.evaluate("() => { _veSetFieldValue(document.getElementById('veRemoveRanges'), '[[4,6],[12,14]]'); _veRenderTimelineOverlays(); }")
    pps = _px_per_second(page)
    _drag(page, ".ve-tl-range[data-index='0']", 2 * pps)
    ranges = page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)")
    assert abs(ranges[0][0] - 6) <= 0.3 and abs(ranges[0][1] - 8) <= 0.3 and ranges[1] == [12, 14]
    _drag(page, ".ve-tl-range[data-index='0']", 1 * pps, edge="end")
    ranges = page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)")
    assert abs(ranges[0][1] - 9) <= 0.3
    # הגרירה לא הזיזה את סמן הנגן לנקודת השחרור (הלחיצה שנוצרה ממנה נבלעת)
    cursor = page.evaluate("() => _veTimelineCursor")
    assert cursor is None or abs(cursor - 9) > 0.5, cursor
    page.locator(".ve-tl-range[data-index='1']").dblclick()
    assert len(page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)")) == 1


def test_the_periodic_refresh_keeps_the_timeline_bars_and_ranges(editor_page, tmp_path):
    """25.10.2026: הרענון התקופתי (כל 1.5 שניות) בנה מחדש את פסי השכבות ואת טווחי ההסרה גם בלי שום שינוי - לחיצה
    שהתחילה על פס שהוחלף הלכה לאיבוד (תחת עומס הטסטים של הסטודיו נכשלו על "element was detached from the DOM")."""
    page = editor_page
    _fake_timeline(page, tmp_path)
    _set_layers(page, [{"type": "text", "text": "A", "start": 1, "end": 4}])
    page.evaluate("() => { const i = document.getElementById('veRemoveRanges'); i.value = JSON.stringify([[6, 8]]); _veRefreshAllDerivedUi(); }")
    _settle(page)   # הסבב הזה מצייר (הטווח השתנה); מכאן שום דבר לא משתנה
    page.evaluate("""() => {
        document.querySelector('.ve-tl-layer[data-index="0"]').__kept = true;
        document.querySelector('.ve-tl-range[data-index="0"]').__kept = true;
        _veRefreshAllDerivedUi(); }""")
    _settle(page)
    page.evaluate("() => _veRefreshAllDerivedUi()")   # עוד סבב, כמו הטיימר
    _settle(page)
    assert page.evaluate("() => !!document.querySelector('.ve-tl-layer[data-index=\"0\"]').__kept")
    assert page.evaluate("() => !!document.querySelector('.ve-tl-range[data-index=\"0\"]').__kept")
    # שינוי אמיתי עדיין מצייר מחדש
    page.evaluate("() => { const i = document.getElementById('veRemoveRanges'); i.value = JSON.stringify([[6, 9]]); _veRefreshAllDerivedUi(); }")
    _settle(page)
    assert page.evaluate("() => !document.querySelector('.ve-tl-range[data-index=\"0\"]').__kept")
