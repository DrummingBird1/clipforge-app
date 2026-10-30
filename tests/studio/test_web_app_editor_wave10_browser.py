# tests/studio/test_web_app_editor_wave10_browser.py
#
# גל 10 בדפדפן אמיתי (Edge דרך Playwright): המבנה החדש של עורך-העל - בוררים
# מאוחדים במקום שדות כפולים, פשוט/מתקדם, "רק מה ששונה", כרטיסי שכבות, המרת
# טקסט קבוע לשכבה, דיאלוג פרופילים, מצבי הרצה - והתצוגה המקדימה: מחיצה נגררת,
# אזורי בטיחות, ידיות גרירה ללוגו/PiP/שכבות, ציר-זמן אינטראקטיבי וקטע וידאו.
import os
import shutil
import subprocess


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(page):
    """גל 23: מחכים שכל רענון ה-UI הנגזר (debounced) הסתיים - לא לזמן קבוע."""
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


def _set(page, element_id, value):
    page.evaluate(
        """([id, value]) => { const el = document.getElementById(id);
            if (el.type === 'checkbox') el.checked = value; else el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }""",
        [element_id, value],
    )
    _settle(page)  # רענון ה-UI הנגזר הוא debounced


def _opts(page):
    return page.evaluate("() => _collectRunOptions()")


def _show_fake_frame(page, width=90, height=160):
    """במה עם פריים מזויף (data-URL) בגודל נתון - בלי שרת/ffmpeg."""
    page.evaluate("""([w, h]) => new Promise(resolve => {
        const c = document.createElement('canvas'); c.width = w; c.height = h;
        const ctx = c.getContext('2d'); ctx.fillStyle = '#345'; ctx.fillRect(0, 0, w, h);
        const url = c.toDataURL('image/png');
        const after = document.getElementById('vePreviewAfter');
        after.onload = () => resolve();
        document.getElementById('vePreviewBefore').src = url;
        after.src = url;
        document.getElementById('vePreviewStageWrap').hidden = false;
        document.getElementById('vePreviewStage').dataset.outputWidth = w;
        document.getElementById('vePreviewStage').dataset.outputHeight = h;
    })""", [width, height])
    page.evaluate("() => document.getElementById('vePreviewStage').scrollIntoView({block: 'center'})")


# --- בוררים מאוחדים (במקום שדות כפולים) ---

def test_format_chips_write_the_hidden_legacy_fields(editor_page):
    page = editor_page
    page.click("#veFormatChips button[data-format='9:16']")
    opts = _opts(page)
    assert opts["vertical"] is True and not opts["dual_output"]
    assert page.evaluate("() => document.querySelector('#veFormatChips button[data-format=\"9:16\"]').getAttribute('aria-checked')") == "true"
    page.click("#veFormatChips button[data-format='16:9']")
    opts = _opts(page)
    assert opts["vertical"] is False and not opts["dual_output"]


def test_an_old_dual_output_profile_converts_to_targets(editor_page):
    # גל 28: אין יותר צ'יפ "שניהם" (כפילות של היעדים) - פרופיל ישן עם פלט כפול מקבל הסבר והמרה
    page = editor_page
    assert page.locator("#veFormatChips button[data-format='dual']").count() == 0
    page.evaluate("() => _applyVideoEditorFields({dual_output: true, vertical: false, aspect: ''})")
    page.wait_for_selector("#veDualLegacyRow:not([hidden])")
    assert _opts(page)["dual_output"] is True
    page.click("#veDualLegacyRow button:has-text('המר ליעדים')")
    opts = _opts(page)
    assert not opts["dual_output"] and set(opts["targets"]) == {"youtube", "shorts"}
    assert page.is_hidden("#veDualLegacyRow")
    # יעדים פעילים - בורר הפורמט נעול (היעד קובע)
    page.wait_for_function("() => [...document.querySelectorAll('#veFormatChips button')].every(b => b.disabled)")


def test_fill_mode_select_maps_to_crop_and_blur_flags(editor_page):
    page = editor_page
    page.click("#veFormatChips button[data-format='9:16']")
    page.select_option("#veFillMode", "face")
    opts = _opts(page)
    assert opts["smart_crop"] is True and opts["smart_crop_face"] is True and not opts["blur_background"]
    page.select_option("#veFillMode", "blur")
    opts = _opts(page)
    assert opts["blur_background"] is True and not opts["smart_crop"]


def test_denoise_select_follows_profile_load_and_writes_level(editor_page):
    page = editor_page
    page.evaluate("() => _applyVideoEditorFields({denoise: true, denoise_level: 'strong'})")
    assert page.evaluate("() => document.getElementById('veDenoiseMode').value") == "strong"
    page.select_option("#veDenoiseMode", "off")
    assert _opts(page)["denoise"] is False


# --- פשוט / מתקדם, "רק מה ששונה" ---

def test_simple_mode_hides_advanced_areas_and_is_remembered(editor_page):
    page = editor_page
    page.evaluate("() => setVeMode('simple')")
    assert page.evaluate("() => getComputedStyle(document.querySelector('[data-cat=perf]')).display") == "none"
    assert page.evaluate("() => document.getElementById('veModeSimpleBtn').getAttribute('aria-pressed')") == "true"
    assert page.evaluate("() => _veLoadPref('veMode', '')") == "simple"
    page.click("#veModeAdvancedBtn")
    assert page.evaluate("() => getComputedStyle(document.querySelector('[data-cat=perf]')).display") != "none"


def test_only_changed_filter_shows_just_modified_rows(editor_page):
    page = editor_page
    page.evaluate("() => setVeOnlyChanged(true)")
    _settle(page)
    codec_row_visible = "() => getComputedStyle(document.getElementById('veCodec').closest('.ve-row')).display !== 'none'"
    assert page.evaluate(codec_row_visible) is False
    _set(page, "veCodec", "av1")
    page.wait_for_function(codec_row_visible)
    page.evaluate("() => setVeOnlyChanged(false)")


# --- כרטיסי שכבות + המרת טקסט קבוע לשכבה ---

def test_layer_cards_appear_on_add_and_clear_on_remove(editor_page):
    page = editor_page
    assert page.evaluate("() => document.querySelector('[data-card=logo]').hidden") is True
    page.evaluate("() => addVeLayerCard('logo')")
    assert page.evaluate("() => document.querySelector('[data-card=logo]').hidden") is False
    _set(page, "veWatermarkPath", r"C:\logo.png")
    page.evaluate("() => removeVeLayerCard('logo')")
    _settle(page)
    assert _opts(page)["watermark_path"] == ""
    assert page.evaluate("() => document.querySelector('[data-card=logo]').hidden") is True


def test_old_profile_static_text_becomes_a_text_layer(editor_page):
    page = editor_page
    page.evaluate("() => _applyVideoEditorFields({text: 'Hello old', text_position: 'top'})")
    opts = _opts(page)
    assert not opts["text"]
    layers = page.evaluate("() => JSON.parse(document.getElementById('veLayers').value)")
    assert layers[0]["type"] == "text" and layers[0]["text"] == "Hello old" and layers[0]["position"].startswith("top")


# --- דיאלוג פרופילים + מצבי הרצה ---

def test_profile_dialog_opens_from_top_bar_and_escape_closes(editor_page):
    page = editor_page
    page.click("button[aria-label='אפשרויות שמירה']")  # גל 27: בתפריט של 💾 שמור ▾
    page.click("#veProfileManagerBtn")
    page.wait_for_selector("#veProfileModalBg.show")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('veProfileModalBg').classList.contains('show')")


def test_run_mode_menu_switches_the_run_button(editor_page):
    page = editor_page
    page.click("#veRunModeBtn")
    page.check("input[name=veRunMode][value=validate]")
    assert _opts(page)["validate_only"] is True
    assert "בדוק" in page.inner_text("#veStickyRunBtn")
    page.evaluate("() => { const r = document.querySelector('input[name=veRunMode][value=normal]'); r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }")
    assert _opts(page)["validate_only"] is False
    assert "הרץ" in page.inner_text("#veStickyRunBtn")


# --- תצוגה מקדימה: מחיצה, אזורי בטיחות, ידיות גרירה ---

def test_before_after_divider_drags_with_mouse_and_keyboard(editor_page):
    page = editor_page
    _show_fake_frame(page, 320, 180)
    stage = page.locator("#vePreviewStage").bounding_box()
    divider = page.locator("#vePreviewDivider").bounding_box()
    page.mouse.move(divider["x"] + divider["width"] / 2, divider["y"] + divider["height"] / 2)
    page.mouse.down()
    page.mouse.move(stage["x"] + stage["width"] * 0.3, stage["y"] + stage["height"] / 2, steps=5)
    page.mouse.up()
    value = int(page.evaluate("() => document.getElementById('vePreviewSplit').value"))
    assert 27 <= value <= 33
    assert page.evaluate("() => document.getElementById('vePreviewStage').style.getPropertyValue('--ve-split')") == f"{value}%"
    page.focus("#vePreviewDivider")
    page.keyboard.press("ArrowRight")
    assert int(page.evaluate("() => document.getElementById('vePreviewSplit').value")) == value + 2


def test_safe_zones_overlay_and_warning_for_logo_under_buttons(editor_page):
    page = editor_page
    _show_fake_frame(page, 90, 160)
    page.select_option("#veSafeZones", "shorts")
    assert page.evaluate("() => document.querySelectorAll('#veSafeZonesOverlay > div').length") == 3
    assert page.evaluate("() => _veLoadPref('veSafeZones', '')") == "shorts"
    _set(page, "veWatermarkPath", r"C:\logo.png")
    page.evaluate("() => { document.getElementById('veWatermarkX').value = '0.93'; document.getElementById('veWatermarkY').value = '0.6'; _veRenderDragHandles(); }")
    assert page.evaluate("() => document.querySelector('#veDragHandles [data-kind=logo]').classList.contains('ve-in-zone')")
    warn = page.inner_text("#veSafeZonesWarn")
    assert "לוגו" in warn and "לייק" in warn
    page.select_option("#veSafeZones", "")
    assert page.evaluate("() => document.getElementById('veSafeZonesWarn').hidden")


def test_dragging_pip_and_layer_handles_sets_exact_positions(editor_page):
    page = editor_page
    _show_fake_frame(page, 320, 180)
    _set(page, "vePipPath", r"C:\cam.mp4")
    page.evaluate("() => { addVeLayer('text'); const layers = _veLayersValue(); layers[0].text = 'Drag me'; _veWriteLayers(layers); _veRenderLayersEditor(true); }")
    _settle(page)  # רענון ה-UI הנגזר (debounced) מצייר את הידיות מחדש - מחכים שיסתיים לפני גרירה
    page.evaluate("() => _veRenderDragHandles()")

    def drag(selector, fx, fy):
        # הוספת השכבה ממקדת את שדה הטקסט שלה (גלילה) - מחזירים את הבמה לתצוגה
        page.evaluate("() => document.getElementById('vePreviewStage').scrollIntoView({block: 'center'})")
        stage = page.locator("#vePreviewStage").bounding_box()
        box = page.locator(selector).bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(stage["x"] + stage["width"] * fx, stage["y"] + stage["height"] * fy, steps=6)
        page.mouse.up()
        _settle(page)

    drag("#veDragHandles [data-kind=pip]", 0.25, 0.3)
    opts = _opts(page)
    assert opts["pip_x"] == pytest.approx(0.25, abs=0.03) and opts["pip_y"] == pytest.approx(0.3, abs=0.03)
    page.evaluate("() => _veRenderDragHandles()")
    drag("#veDragHandles [data-kind=layer]", 0.7, 0.2)
    [layer] = page.evaluate("() => JSON.parse(document.getElementById('veLayers').value)")
    assert layer["position"] == "custom"
    assert layer["x"] == pytest.approx(0.7, abs=0.03) and layer["y"] == pytest.approx(0.2, abs=0.03)
    # בחירת מיקום מהרשימה מבטלת את הגרירה של ה-PiP
    page.select_option("#vePipPosition", "top-left")
    assert _opts(page)["pip_x"] is None


def test_drag_handles_toggle_hides_them(editor_page):
    page = editor_page
    _show_fake_frame(page, 320, 180)
    _set(page, "veWatermarkPath", r"C:\logo.png")
    page.evaluate("() => _veRenderDragHandles()")
    assert page.evaluate("() => document.querySelectorAll('#veDragHandles .ve-drag-handle').length") == 1
    page.uncheck("#vePreviewHandles")
    assert page.evaluate("() => document.querySelectorAll('#veDragHandles .ve-drag-handle').length") == 0


# --- ציר-זמן אינטראקטיבי ---

def _fake_timeline(page, duration=100):
    page.evaluate("""(d) => { _veTimeline = {path: 'x.mp4', duration: d};
        document.querySelector('[data-cat=time]').open = true;
        document.getElementById('veTimelineBox').hidden = false;
        document.getElementById('veTimeline').scrollIntoView({block: 'center'});
        _veRenderTimelineOverlays(); }""", duration)


def test_timeline_trim_handles_drag_and_shift_drag_adds_range(editor_page):
    page = editor_page
    _fake_timeline(page)
    timeline = page.locator("#veTimeline").bounding_box()
    y = timeline["y"] + timeline["height"] / 2

    def drag_handle(which, fraction):
        box = page.locator(f"#veTlHandle-{which}").bounding_box()
        # הידיות בקצוות חתוכות בחצי (overflow של הפס) - תופסים את החלק הגלוי
        page.mouse.move(box["x"] + box["width"] * (0.75 if which == "start" else 0.25), y)
        page.mouse.down()
        page.mouse.move(timeline["x"] + timeline["width"] * fraction, y, steps=6)
        page.mouse.up()
        _settle(page)

    drag_handle("start", 0.2)
    assert _opts(page)["trim_start"] == pytest.approx(20, abs=1.5)
    drag_handle("end", 0.8)
    opts = _opts(page)
    assert opts["trim_start"] + opts["trim_duration"] == pytest.approx(80, abs=1.5)
    # Shift+גרירה על הפס = טווח להסרה
    page.keyboard.down("Shift")
    page.mouse.move(timeline["x"] + timeline["width"] * 0.4, y)
    page.mouse.down()
    page.mouse.move(timeline["x"] + timeline["width"] * 0.5, y, steps=6)
    page.mouse.up()
    page.keyboard.up("Shift")
    _settle(page)
    [[start, end]] = page.evaluate("() => JSON.parse(document.getElementById('veRemoveRanges').value)")
    assert start == pytest.approx(40, abs=1.5) and end == pytest.approx(50, abs=1.5)
    # מקלדת על ידית: חץ ימינה מזיז את ההתחלה בחצי שנייה
    before = _opts(page)["trim_start"]
    page.focus("#veTlHandle-start")
    page.keyboard.press("ArrowRight")
    _settle(page)
    assert _opts(page)["trim_start"] == pytest.approx(before + 0.5, abs=0.11)


def test_highlight_markers_show_and_pick_the_peak(editor_page):
    page = editor_page
    _fake_timeline(page)
    page.evaluate("() => { _veHighlightMarkers = {file: document.getElementById('vePreviewFile').value, peaks: [30.04, 72.5]}; _veRenderTimelineOverlays(); }")
    assert page.evaluate("() => document.querySelectorAll('#veTimelineOverlays .ve-tl-peak').length") == 2
    page.click("#veTimelineOverlays .ve-tl-peak >> nth=1")
    assert page.evaluate("() => _veTimelineCursor") == 72.5
    assert "🔥" in page.inner_text("#veTimelineCursorText")


# --- קטע וידאו אמיתי (ffmpeg) ---

@needs_ffmpeg
def test_preview_clip_plays_in_stage_and_returns_to_frame(editor_page, tmp_path, editor_server, monkeypatch):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    monkeypatch.setattr(editor_server["web_app"], "PREVIEWS_DIR", str(tmp_path / "previews"))
    clips = tmp_path / "in"
    clips.mkdir()
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=5:size=320x180:rate=10", "-f", "lavfi", "-i", "sine=duration=5",
                    "-c:a", "aac", "-pix_fmt", "yuv420p", "-shortest", str(clips / "clip.mp4")],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)
    page = editor_page
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(clips))
    page.wait_for_function("() => document.getElementById('vePreviewFile').options.length === 1", timeout=15000)
    page.select_option("#vePreviewClipSeconds", "3")
    page.click("#vePreviewClipBtn")
    page.wait_for_function("() => document.getElementById('vePreviewStage').classList.contains('ve-stage-video')", timeout=90000)
    page.wait_for_function("() => document.getElementById('vePreviewClip').readyState >= 1 && document.getElementById('vePreviewClipBefore').readyState >= 1", timeout=20000)
    assert page.evaluate("() => document.getElementById('vePreviewClip').videoWidth") == 1920
    assert not page.evaluate("() => document.getElementById('vePreviewClipWrap').hidden")
    assert "🎬" in page.inner_text("#vePreviewStatus")
    page.click("#vePreviewClipWrap button:has-text('פריים')")
    assert page.evaluate("() => document.getElementById('vePreviewStage').classList.contains('ve-stage-video')") is False
    assert page.evaluate("() => document.getElementById('vePreviewClipWrap').hidden") is True
