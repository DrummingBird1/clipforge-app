# tests/studio/test_web_app_wave33_browser.py
#
# גל 33 בדפדפן: המפקח מסודר - מסלול ניווט, חיפוש ו"רק מה ששיניתי" בתוך המפקח, שדות לא רלוונטיים
# מעומעמים עם סיבה (ולא נעולים), אזהרה ליד השדה, כלי קבוצה (איפוס / העתקה / הדבקה), שורת "מה זה
# עושה", "?" שנפתח בתוך הדף וחלון "📖 בתיעוד" מ-/api/docs/section.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

IDLE = "() => typeof uiPendingWork === 'function' && uiPendingWork() === 0"


def _set(page, element_id, value):
    page.evaluate("([id, v]) => { const el = document.getElementById(id); if (el.type === 'checkbox') el.checked = v; else el.value = v;"
                  " el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }",
                  [element_id, value])
    page.wait_for_function(IDLE)


def test_search_and_changed_chip_live_in_the_inspector(editor_page):
    page = editor_page
    assert page.evaluate("() => document.getElementById('veInspectorTools').contains(document.getElementById('veSearchInput'))")
    page.wait_for_function(IDLE)
    before = page.evaluate("() => _veChangedTotal()")
    assert page.evaluate("() => document.getElementById('veChangedChip').textContent").endswith(f"({before})")
    _set(page, "veEqSaturation", "1.5")
    page.wait_for_function("(n) => document.getElementById('veChangedChip').textContent.endsWith(`(${n})`)", arg=before + 1)
    page.click("#veChangedChip")
    assert page.get_attribute("#veChangedChip", "aria-pressed") == "true"
    page.click("#veChangedChip")
    assert page.get_attribute("#veChangedChip", "aria-pressed") == "false"


def test_breadcrumb_shows_folder_and_active_tab(editor_page, tmp_path):
    page = editor_page
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    page.evaluate("() => { setVeLayout('tabs'); _veActivateTab('look'); _veRenderCrumbs(); }")
    crumbs = page.eval_on_selector_all("#veCrumbs .ve-crumb", "els => els.map(e => e.textContent)")
    assert crumbs[0].endswith(tmp_path.name)
    look_title = page.evaluate("() => _veCategoryByKey('look').querySelector('.ve-cat-title').textContent.trim()")
    assert look_title.split(" ", 1)[-1] in crumbs[-1]


def test_irrelevant_fields_are_dimmed_with_a_reason_but_still_editable(editor_page):
    page = editor_page
    page.wait_for_function(IDLE)
    page.evaluate("() => _veRefreshInspectorTools()")
    dimmed = "(id) => _veRelevanceTarget(document.getElementById(id)).classList.contains('ve-ctl-irrelevant')"
    assert page.evaluate(dimmed, "vePipPosition")
    note = page.evaluate("() => (document.getElementById('vePipPosition').closest('.ve-row').querySelector('.ve-rel-note') || {}).textContent")
    assert note and "PiP" in note
    assert not page.evaluate("() => document.getElementById('vePipPosition').inert")   # לא נעול - אפשר למלא מראש
    # המתג ושדה היעד באותה שורה: המתג עצמו לעולם לא מעומעם
    assert page.evaluate(dimmed, "veLoudnormTarget")
    assert not page.evaluate("() => document.getElementById('veLoudnorm').closest('label').classList.contains('ve-ctl-irrelevant')")
    _set(page, "vePipPath", "C:/clips/facecam.mp4")
    page.wait_for_function("() => !_veRelevanceTarget(document.getElementById('vePipPosition')).classList.contains('ve-ctl-irrelevant')")
    assert page.evaluate("() => !document.getElementById('vePipPosition').closest('.ve-row').querySelector('.ve-rel-note')")


def test_rule_warning_appears_next_to_its_field(editor_page):
    page = editor_page
    # הכלל עצמו נבדק בטסטי האזהרות; כאן - שהאזהרה מוצבת בשורה של השדה שלה, ונעלמת כשהכלל כבה
    page.evaluate("() => { window.__rule = VE_RULES.find(x => x.field === 'loudnorm'); window.__rule.when = () => true; _veRenderInlineWarnings(); }")
    row_warn = "() => !!document.getElementById(VE_FAVORITABLE_FIELDS.loudnorm.id).closest('.ve-row').querySelector('.ve-inline-warn')"
    assert page.evaluate(row_warn)
    page.evaluate("() => { window.__rule.when = () => false; _veRenderInlineWarnings(); }")
    assert not page.evaluate(row_warn)


def test_group_tools_copy_reset_and_paste(editor_page):
    page = editor_page
    sub = "#veCategories .ve-subcat[data-subcat=color]"
    assert page.evaluate(f"() => !!document.querySelector('{sub} .ve-subcat-desc')")
    assert page.evaluate(f"() => document.querySelector('{sub} .ve-group-paste').disabled")
    _set(page, "veEqSaturation", "1.5")
    page.evaluate(f"() => copyVeSubcat(document.querySelector('{sub}'))")
    assert not page.evaluate(f"() => document.querySelector('{sub} .ve-group-paste').disabled")
    page.evaluate(f"() => resetVeSubcat(document.querySelector('{sub}'))")
    assert page.input_value("#veEqSaturation") == "1"
    page.evaluate(f"() => pasteVeSubcat(document.querySelector('{sub}'))")
    assert page.input_value("#veEqSaturation") == "1.5"
    # הקיפול של הכותרת לא בולע Enter מהכפתורים
    assert page.evaluate(f"""() => {{
      const btn = document.querySelector('{sub} .ve-group-tool');
      const e = new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true, cancelable: true}});
      btn.dispatchEvent(e);
      return !e.defaultPrevented;
    }}""")


def test_inline_help_and_docs_section(editor_page):
    page = editor_page
    row = page.evaluate_handle("() => document.querySelector('#veCategories .ve-row .ve-help-toggle').closest('.ve-row')")
    page.evaluate("(row) => row.querySelector('.ve-help-toggle').click()", row)
    assert page.evaluate("(row) => !!row.querySelector('.ve-help-inline')", row)
    assert page.evaluate("(row) => row.querySelector('.ve-help-toggle').getAttribute('aria-expanded')", row) == "true"
    page.evaluate("() => openVeFieldDocs('nvenc_preset', 'NVENC preset')")
    page.wait_for_function("() => document.getElementById('veDocsBody').textContent.includes('--nvenc-preset')", timeout=10000)
    assert page.is_visible("#veDocsModalBg")
    page.evaluate("() => closeVeDocs()")
    assert not page.is_visible("#veDocsModalBg")
