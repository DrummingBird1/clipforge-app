# tests/studio/test_web_app_wave37_browser.py
#
# גל 37 בדפדפן: תקציב "עומס מסך" - כמה פקדים גלויים בכל רמה (פשוט < רגיל < מומחה, ו"רגיל" באמת
# מסתיר את ההגדרות הנדירות), הקישור לתיעוד לפי הדגל מסכימת השדות, וה-API הפנימי של האזורים.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

IDLE = "() => typeof uiPendingWork === 'function' && uiPendingWork() === 0"

# פקד גלוי = כפתור / שדה / בורר שמוצג (לא בתוך אזור מוסתר או details סגור)
COUNT_VISIBLE = """() => [...document.querySelectorAll('#videoEditorOptions :is(button, input:not([type=hidden]), select, textarea)')]
    .filter(el => el.offsetParent !== null && !el.closest('[hidden], .modal-bg:not(.show)')).length"""

# תקרה נדיבה למצב הפשוט - עוצרת התנפחות; המספרים בפועל מודפסים בכל ריצה
SIMPLE_CAP = 150


def _count(page, mode):
    page.evaluate("(m) => setVeMode(m)", mode)
    page.wait_for_function(IDLE)
    return page.evaluate(COUNT_VISIBLE)


def test_visible_controls_budget_per_level(editor_page):
    page = editor_page
    page.evaluate("() => setVeLayout('accordion')")
    counts = {mode: _count(page, mode) for mode in ("simple", "regular", "advanced")}
    print("visible controls per level:", counts)
    assert counts["simple"] < counts["regular"] < counts["advanced"], counts
    assert counts["advanced"] - counts["regular"] >= 15, counts   # "רגיל" באמת מסתיר את הנדירות
    assert counts["simple"] <= SIMPLE_CAP, counts


def test_docs_link_uses_the_flag_from_the_field_schema(editor_page):
    page = editor_page
    page.wait_for_function("() => !!_veFieldSchema && !!_veFieldSchema.lut_path")
    assert page.evaluate("() => _veFieldSchema.lut_path.flag") == "--lut"
    page.evaluate("() => openVeFieldDocs('nvenc_cq', 'NVENC')")
    page.wait_for_function("() => document.getElementById('veDocsBody').textContent.includes('--nvenc-cq')", timeout=10000)
    page.evaluate("() => closeVeDocs()")


def test_internal_api_reaches_each_area(editor_page):
    page = editor_page
    areas = page.evaluate("() => Object.keys(veApi)")
    assert areas == ["queue", "timeline", "inspector", "layers", "library", "player", "runs"]
    assert page.evaluate("() => Object.isFrozen(veApi) && Object.isFrozen(veApi.layers)")
    page.evaluate("() => veApi.library.open('target')")
    page.wait_for_function("() => document.getElementById('veLibraryModalBg').classList.contains('show')")
    page.evaluate("() => veApi.library.close()")
    page.evaluate("() => veApi.layers.write([{type: 'text', text: 'API', start: 0, end: 2}])")
    assert page.evaluate("() => veApi.layers.list().map(l => l.text)") == ["API"]
