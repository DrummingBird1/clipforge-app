# tests/web/test_web_app_wave25_browser.py
#
# גל 25 בדפדפן אמיתי: גלגלי lift/gamma/gain (גרירה, מקלדת, בהירות, איפוס, הקלדה ישירה),
# עורך העקומות (הוספת נקודה, ערוצים, preset), שמירה והחלה מפרופיל, הדמיה בנגן החי,
# אזהרות ליד השדה, וממשק באנגלית בלי עברית.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _open_look(page):
    page.evaluate("() => { const d = document.querySelector('details[data-cat=look]'); d.open = true; d.scrollIntoView({block: 'center'}); }")
    page.wait_for_function("() => document.querySelector('.ve-wheel[data-grade=shadows] .ve-wheel-disc').getBoundingClientRect().width > 40")


def _triplet(page, field_id):
    raw = page.input_value(f"#{field_id}")
    return [float(v) for v in raw.split(",")] if raw else [0.0, 0.0, 0.0]


def _drag_on(page, selector, dx, dy):
    """גרירה מהמרכז של האלמנט אל (dx, dy) יחסית לחצי-הרוחב/גובה שלו (-1..1)."""
    box = page.locator(selector).bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + dx * box["width"] / 2 * 0.5, cy + dy * box["height"] / 2 * 0.5, steps=3)
    page.mouse.move(cx + dx * box["width"] / 2, cy + dy * box["height"] / 2, steps=3)
    page.mouse.up()


def test_dragging_a_wheel_tints_that_range_and_the_controls_stay_in_sync(editor_page):
    page = editor_page
    _open_look(page)
    disc = ".ve-wheel[data-grade=shadows] .ve-wheel-disc"
    _drag_on(page, disc, 0, -0.95)  # למעלה = אדום
    r, g, b = _triplet(page, "veGradeShadows")
    assert r > 0.2 and g < 0 and b < 0 and abs(g - b) < 0.02
    assert page.evaluate("() => document.querySelector('.ve-wheel[data-grade=shadows]').classList.contains('is-set')")
    assert page.evaluate("() => _collectRunOptions().grade_shadows") == page.input_value("#veGradeShadows")

    # בהירות: אותו היסט לכל הערוצים, בלי לשנות את הגוון
    page.fill(".ve-wheel-box:has([data-grade=shadows]) .ve-wheel-luma", "0.1")
    page.dispatch_event(".ve-wheel-box:has([data-grade=shadows]) .ve-wheel-luma", "input")
    r2, g2, b2 = _triplet(page, "veGradeShadows")
    assert abs((r2 + g2 + b2) / 3 - 0.1) < 0.005 and abs((r2 - g2) - (r - g)) < 0.005

    # מקלדת: Delete מאפס את הגוון (הבהירות נשארת), ↺ מאפס הכל
    page.focus(disc)
    page.keyboard.press("Delete")
    assert _triplet(page, "veGradeShadows") == [0.1, 0.1, 0.1]
    page.click(".ve-wheel-box:has([data-grade=shadows]) .ve-wheel-reset")
    assert page.input_value("#veGradeShadows") == ""
    assert not page.evaluate("() => document.querySelector('.ve-wheel[data-grade=shadows]').classList.contains('is-set')")

    # הקלדה ישירה מזיזה את הנקודה (כחול - 240° - שמאלה-למטה)
    page.fill("#veGradeHighlights", "0,0,0.2")
    page.dispatch_event("#veGradeHighlights", "input")
    left, top = page.evaluate("() => { const p = document.querySelector('.ve-wheel[data-grade=highlights] .ve-wheel-puck'); return [parseFloat(p.style.left), parseFloat(p.style.top)]; }")
    assert left < 50 and top > 50


def test_the_curve_editor_adds_points_per_channel_and_respects_presets(editor_page):
    page = editor_page
    _open_look(page)
    page.evaluate("() => document.getElementById('veCurvesCanvas').scrollIntoView({block: 'center'})")
    box = page.locator("#veCurvesCanvas").bounding_box()
    page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.3)  # מעל האלכסון = הבהרה
    points = page.input_value("#veCurvesMaster").split()
    assert len(points) == 3 and points[0] == "0/0" and points[-1] == "1/1"
    x, y = (float(v) for v in points[1].split("/"))
    assert 0.4 < x < 0.6 and y > x
    # ערוץ אחר: השדה שלו מוצג, העקומה הראשית לא נגעה
    page.click("#veCurvesChannels button[data-channel=blue]")
    assert page.is_visible("#veCurvesBlue") and not page.is_visible("#veCurvesMaster")
    page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.7)
    assert len(page.input_value("#veCurvesBlue").split()) == 3
    assert page.input_value("#veCurvesMaster").split() == points
    page.click("#veCurvesChannels button[aria-label]:has-text('↺'), #veCurvesChannels button.btn-ghost")
    assert page.input_value("#veCurvesBlue") == ""
    # preset: מצויר ונשלח, נקודות מותאמות של הערוץ גוברות עליו
    page.select_option("#veCurvesPreset", "vintage")
    opts = page.evaluate("() => _collectRunOptions()")
    assert opts["curves_preset"] == "vintage" and opts["curves_master"] == " ".join(points)
    assert page.evaluate("() => _veCurvePointsFor('red').length") == 3  # מה-preset
    assert page.evaluate("() => _veCurvePointsFor('master').length") == 3  # המותאמת


def test_profile_values_restore_the_widgets_and_the_live_player_previews_the_grade(editor_page):
    page = editor_page
    _open_look(page)
    assert page.evaluate("() => _veLiveGradeFilter(_collectRunOptions())") == ""
    page.evaluate("() => _applyVideoEditorFields({grade_highlights: '0.1,0.05,0', curves_master: '0/0 0.5/0.7 1/1', audio_compressor: 'voice'})")
    assert page.evaluate("() => document.querySelector('.ve-wheel[data-grade=highlights]').classList.contains('is-set')")
    assert page.input_value("#veAudioCompressor") == "voice"
    assert page.evaluate("() => _veLiveGradeFilter(_collectRunOptions())") == " url(#veLiveGrade)"
    tables = page.evaluate("() => ['R', 'G', 'B'].map(c => document.querySelector('#veLiveGradeSvg feFunc' + c).getAttribute('tableValues').split(' ').map(Number))")
    mid = len(tables[0]) // 2
    assert all(len(t) == 33 for t in tables)
    assert tables[0][mid] > 0.6 and tables[0][0] == 0  # העקומה מבהירה את האמצע, השחור נשאר שחור
    assert tables[0][-1] >= tables[2][-1]  # ההדגשות חמות יותר (אדום מעל כחול)
    # בלי תיקון - בלי פילטר (לא מאטים את הנגן סתם)
    page.evaluate("() => _applyVideoEditorFields({})")
    assert page.evaluate("() => _veLiveGradeFilter(_collectRunOptions())") == ""


def test_audio_processing_warns_without_audio_and_shows_db_labels(editor_page):
    page = editor_page
    page.evaluate("() => { const d = document.querySelector('details[data-cat=sound]'); d.open = true; }")
    page.fill("#veAudioEqLow", "3")
    page.dispatch_event("#veAudioEqLow", "input")
    page.evaluate("() => _veRefreshRangeLabels()")
    assert page.inner_text(".ve-range-value[data-for=veAudioEqLow]") == "+3.0 dB"
    warnings = "() => VE_RULES.filter(r => r.field === 'audio_compressor' && r.when(_collectRunOptions())).length"
    page.select_option("#veAudioCompressor", "voice")
    page.evaluate("() => _applyVideoEditorFields({audio_compressor: 'voice', keep_audio: false})")
    assert page.evaluate(warnings) == 1
    page.evaluate("() => _applyVideoEditorFields({audio_compressor: 'voice', keep_audio: true})")
    assert page.evaluate(warnings) == 0
    # תדר ה-EQ האמצעי רלוונטי רק כשיש הגברה/הנמכה באמצע
    assert page.evaluate("() => VE_DEPENDENT_FIELDS.veAudioEqMidFreq()") is False
    page.evaluate("() => { document.getElementById('veAudioEqMid').value = '-2'; }")
    assert page.evaluate("() => VE_DEPENDENT_FIELDS.veAudioEqMidFreq()") is True


def test_the_new_controls_are_fully_translated_in_english(editor_page):
    page = editor_page
    for cat in ("look", "sound"):
        page.evaluate(f"() => {{ document.querySelector('details[data-cat={cat}]').open = true; }}")
    page.evaluate("() => setUiLanguage('en')")
    page.wait_for_function("() => document.documentElement.lang === 'en'")
    leftovers = page.evaluate("""() => {
        const re = /[\\u0590-\\u05FF]/;
        const out = [];
        for (const root of document.querySelectorAll('[data-subcat=grade], [data-subcat=audio-fx]')) {
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            for (let n = walker.nextNode(); n; n = walker.nextNode()) if (re.test(n.nodeValue)) out.push(n.nodeValue.trim());
            for (const el of root.querySelectorAll('[title], [aria-label], [placeholder]'))
                for (const a of ['title', 'aria-label', 'placeholder']) if (re.test(el.getAttribute(a) || '')) out.push(el.getAttribute(a));
        }
        return out;
    }""")
    assert leftovers == []
    assert "Color wheels and curves" in page.inner_text("[data-subcat=grade]")
