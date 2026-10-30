# tests/studio/test_web_app_studio_overlap_and_next_clip_browser.py
#
# 24.10.2026, מנה 4 מסיור השימושיות בסטודיו (פריטים 11-12 בתוכנית), ב-89-studio-more.js:
# - האזור הבטוח נבדק לפי המלבן המשוער של הפריט, לא לפי מרכז הידית: לוגו שמרכזו מחוץ לאזור הכפתורים של Shorts אבל חלק ממנו
#   מתחתיו - אזהרה (קודם: כלום).
# - אזהרה כשהלוגו מכסה טקסט או שכבה: מתחת לתצוגה, וגם ברשימת האזהרות (פס הסטטוס ו"לפני הרצה").
# - "⏭ עוד N שניות" אחרי קטע: הקטע הבא מתחיל איפה שהקודם נגמר (קודם: להקליד את הזמן ביד).
import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
WARN = "() => document.getElementById('veSafeZonesWarn').hidden ? '' : document.getElementById('veSafeZonesWarn').textContent"
ADD_HANDLE = """([kind, label, x, y, index]) => { const h = document.createElement('div'); h.className = 've-drag-handle';
  Object.assign(h.dataset, {kind, label, x: String(x), y: String(y)}); if (index !== null) h.dataset.index = String(index);
  document.getElementById('veDragHandles').appendChild(h); }"""


@pytest.fixture
def studio(editor_page):
    page = editor_page
    page.evaluate("() => setVeFocus(true)")
    page.wait_for_function(LOADED)
    page.evaluate("() => { document.getElementById('veDragHandles').innerHTML = ''; document.getElementById('veWatermarkScale').value = '15'; }")
    yield page
    page.evaluate("() => { document.getElementById('veDragHandles').innerHTML = ''; document.getElementById('veSafeZones').value = ''; applyVeSafeZones(); }")


def test_a_logo_partly_under_the_side_buttons_is_flagged(studio):
    page = studio
    page.evaluate("() => { document.getElementById('veSafeZones').value = 'shorts'; }")
    page.evaluate(ADD_HANDLE, ["logo", "🖼️ לוגו", 0.80, 0.6, None])   # המרכז ב-0.80, האזור מ-0.86 - הלוגו ברוחב 15% נכנס אליו
    page.evaluate("() => _veCheckHandlesInSafeZones()")
    assert 'לוגו מתחת ל"לייק / תגובה / שיתוף"' in page.evaluate(WARN)                   # קודם: לפי המרכז - בלי אזהרה


def test_a_logo_over_a_text_layer_is_flagged_on_the_preview_and_in_the_warnings(studio):
    page = studio
    page.evaluate("""() => _applyVideoEditorFields({watermark_path: 'C:\\\\logo.png', watermark_position: 'top-right', watermark_x: null, watermark_y: null,
      layers: [{type: 'text', text: 'שלום עולם', position: 'top-right', font_size: 48, start: 0, end: null}]})""")
    page.evaluate(ADD_HANDLE, ["logo", "🖼️ לוגו", 0.915, 0.15, None])
    page.evaluate(ADD_HANDLE, ["layer", "🔤 שלום עולם", 0.86, 0.07, 0])
    page.evaluate("() => _veCheckHandlesInSafeZones()")
    assert "הלוגו מכסה: 🔤 שלום עולם" in page.evaluate(WARN)                                  # קודם: אין אזהרת חפיפה
    assert page.evaluate("() => _veEvaluateRules().some(rule => rule.msg.startsWith('הלוגו מכסה טקסט או שכבה'))")
    page.evaluate("() => _applyVideoEditorFields({layers: [{type: 'text', text: 'שלום עולם', position: 'bottom-left', font_size: 48, start: 0, end: null}]})")
    assert not page.evaluate("() => _veEvaluateRules().some(rule => rule.msg.startsWith('הלוגו מכסה'))")   # בפינה אחרת - בסדר
    page.evaluate("() => _applyVideoEditorFields({watermark_path: '', layers: []})")


def test_the_next_clip_starts_where_the_last_one_ended(studio):
    page = studio
    page.evaluate("""() => { window.__clipAt = null; window.__realClip = refreshVePreviewClip;
      refreshVePreviewClip = () => { window.__clipAt = document.getElementById('vePreviewTime').value; };
      document.getElementById('vePreviewClipSeconds').value = '5';
      _veShowPreviewClip({after_url: '', time: 12, clip_seconds: 5, output_width: 1080, output_height: 1920}); }""")
    assert page.inner_text("#vePreviewNextClip").split()[-3:] == ["עוד", "5", "שניות"]          # קודם: אין
    page.click("#vePreviewNextClip")
    assert page.evaluate("() => window.__clipAt") == "17"
    page.evaluate("() => { refreshVePreviewClip = window.__realClip; closeVePreviewClip(); uiBus.emit('ve:folder-changed', 'C:\\\\other'); }")
    assert page.evaluate("() => document.getElementById('vePreviewNextClip').hidden")         # תיקייה אחרת - כבר לא רלוונטי
