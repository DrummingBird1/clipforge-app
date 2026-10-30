# tests/web/test_web_app_wave28_browser.py
#
# גל 28 בדפדפן אמיתי - "פאנל הגדרות שאפשר להתמצא בו": בסטודיו ההגדרות בלשוניות לפי
# הסכמה, "מראה" התפצל לצבע ולאפקטים, "ייצוא" לתתי-אזורים, תתי-אזורים מתקפלים עם
# תקציר, שדות תלויים מהסכמה, עמודת תוויות אחידה, שדות זמן (חיצים/גרירה/⌖ מהנגן),
# ⓘ עם ההסבר מהמקראה, ופלט כפול ישן שמומר ליעדים.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(page):
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _set_value(page, element_id, value):
    page.evaluate(
        """([id, value]) => { const el = document.getElementById(id);
            if (el.type === 'checkbox') el.checked = value; else el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }""",
        [element_id, value],
    )
    _settle(page)


def _visible_areas(page):
    return page.evaluate("() => _veCategoryEls().filter(d => getComputedStyle(d).display !== 'none').map(d => d.dataset.cat)")


def _row_of(page, element_id):
    return page.locator(f"#{element_id}").locator("xpath=ancestor::div[contains(@class,'ve-row')][1]")


# --- לשוניות ---

def test_the_studio_inspector_is_tabbed_by_the_schema_areas(editor_page):
    page = editor_page
    page.evaluate("() => { setVeFocus(true); setVeLayout('tabs'); }")  # גל 31: הטסטים רצים ב"הכל ברשימה"
    assert page.evaluate("() => _veCurrentLayout()") == "tabs"
    tabs = page.evaluate("() => [...document.querySelectorAll('#veCatTabs button')].map(b => b.dataset.cat)")
    schema = page.evaluate("async () => (await (await fetch('/api/video_editor/schema')).json()).areas.map(a => a.id)")
    assert tabs == [a for a in schema if a != "queue"]
    assert tabs[:6] == ["time", "look", "effects", "layers", "sound", "output"]  # גל 34: סדר זרימת העבודה
    page.click("#veCatTabs button[data-cat=effects]")
    assert _visible_areas(page) == ["effects"]
    # מספר השינויים על הלשונית
    _set_value(page, "veEqSaturation", "1.4")
    page.wait_for_function("() => (document.querySelector('#veCatTabs button[data-cat=look] .ve-tab-changed') || {}).textContent === '1'")
    # סביבות העבודה הישנות = לשוניות
    page.evaluate("() => setVeWorkspace('audio')")
    assert _visible_areas(page) == ["sound"]
    # במצב פשוט אין לשונית "ביצועים"
    page.evaluate("() => setVeMode('simple')")
    _settle(page)
    assert "perf" not in page.evaluate("() => [...document.querySelectorAll('#veCatTabs button')].map(b => b.dataset.cat)")
    # גל 31: "הכל ברשימה" - כל האזורים, בלי לשוניות
    page.evaluate("() => setVeLayout('accordion')")
    assert page.evaluate("() => _veCurrentLayout()") == "accordion"
    assert page.is_hidden("#veCatTabs")


def test_look_and_export_are_split_and_bookends_moved_to_time(editor_page):
    page = editor_page
    area_of = "(id) => document.getElementById(id).closest('details.ve-category').dataset.cat"
    section_of = "(id) => document.getElementById(id).closest('.ve-subcat').dataset.subcat"
    for element_id, area in (("veEqSaturation", "look"), ("veGradeShadows", "look"), ("veDenoiseMode", "effects"), ("veVignette", "effects"),
                             ("veChromakey", "effects"), ("veIntroPath", "time"), ("veBoomerang", "time"), ("veLoopCount", "time"),
                             ("veCodec", "export"), ("veOutputTemplate", "export"), ("veChapters", "export")):
        assert page.evaluate(area_of, element_id) == area, element_id
    for element_id, section in (("veCodec", "file"), ("veNumberVideos", "naming"), ("veThumbnail", "extra-outputs"),
                                ("veMetaTitle", "metadata"), ("veIntroPath", "bookends"), ("veFadeInSeconds", "bookends")):
        assert page.evaluate(section_of, element_id) == section, element_id
    assert "צבע" in page.inner_text("details[data-cat=look] .ve-cat-title")


# --- תתי-אזורים מתקפלים ---

def test_sections_collapse_to_a_one_line_summary(editor_page):
    page = editor_page
    page.evaluate("() => setVeCollapseSubcats(true)")
    grade = "[data-subcat=grade]"
    assert page.evaluate(f"() => document.querySelector('{grade}').classList.contains('ve-subcat-collapsed')")
    assert not page.evaluate("() => document.querySelector('[data-subcat=color]').classList.contains('ve-subcat-collapsed')")  # ראשי
    assert not page.is_visible("#veCurvesPreset")
    assert page.inner_text(f"{grade} .ve-subcat-summary") == "ברירת מחדל"
    # שינוי בתוך תת-אזור מקופל מופיע בתקציר
    _set_value(page, "veCurvesPreset", "vintage")
    page.wait_for_function(f"() => document.querySelector('{grade} .ve-subcat-summary').textContent.includes('וינטג')")
    page.click(f"{grade} > .ve-subcat-title")
    assert page.is_visible("#veCurvesPreset")
    assert page.evaluate("() => _veLoadPref('veSubcatOpen', {})['look/grade']") is True
    page.focus(f"{grade} > .ve-subcat-title")
    page.keyboard.press("Enter")
    assert not page.is_visible("#veCurvesPreset")
    # קפיצה לשדה (אזהרה / חיפוש / מועדף) פותחת את תת-האזור
    page.evaluate("() => veScrollToField('chromakey_color') || veScrollToField('curves_preset')")
    assert page.is_visible("#veCurvesPreset")
    # בזמן חיפוש תוכן מקופל שעונה לחיפוש גלוי
    page.evaluate("() => _veSetSubcatOpen(document.querySelector('[data-subcat=chromakey]'), false)")
    page.fill("#veSearchInput", "כרומה")
    assert page.is_visible("#veChromakey")


# --- שדות תלויים ---

def test_dependent_fields_from_the_schema_wait_for_their_parent(editor_page):
    page = editor_page
    page.wait_for_function("() => VE_DEPENDENT_PARENTS.veChromakeyBgColor === 'veChromakey'")
    assert _row_of(page, "veChromakeyColor").is_hidden()
    assert _row_of(page, "veLutIntensity").is_hidden()
    _set_value(page, "veChromakey", True)
    assert _row_of(page, "veChromakeyColor").is_visible()
    _set_value(page, "veLutPath", "C:\\\\looks\\\\film.cube")
    assert _row_of(page, "veLutIntensity").is_visible()
    # שדה שחולק שורה עם האב: רק השדה מוסתר, האב נשאר
    assert page.is_visible("#veNumberVideos") and page.is_hidden("#veNumberPrefix")
    _set_value(page, "veNumberVideos", True)
    assert page.is_visible("#veNumberPrefix") and page.is_visible("#veNumberStart")


# --- פקדים אחידים, ⓘ, שדות זמן ---

def test_labels_share_one_column_and_help_comes_from_the_glossary(editor_page):
    page = editor_page
    starts = page.evaluate("""() => ['veEqBrightness', 'veEqContrast', 'veEqSaturation', 'veEqGamma'].map(id =>
        Math.round(document.getElementById(id).getBoundingClientRect().right))""")
    assert max(starts) - min(starts) <= 2, starts  # כל הסליידרים מתחילים באותו קו (RTL: הצד הימני)
    button = _row_of(page, "veLutPath").locator(".ve-info-btn")
    assert button.inner_text() == "ⓘ"
    page.wait_for_function("() => _fieldHelpCache && _fieldHelpCache.lut_path")
    button.click()
    help_text = page.evaluate("() => _fieldHelpCache.lut_path.tooltip")
    assert page.inner_text("#veCategories .ve-info-box") == help_text


def test_time_fields_step_with_arrows_scrub_and_take_the_player_time(editor_page):
    page = editor_page
    page.click("#veTrimStart")
    page.fill("#veTrimStart", "2")
    page.keyboard.press("ArrowUp")
    assert page.input_value("#veTrimStart") == "2.1"
    page.keyboard.press("Shift+ArrowUp")
    assert page.input_value("#veTrimStart") == "3.1"
    page.fill("#veTrimStart", "75")
    page.keyboard.press("Tab")
    assert page.input_value("#veTrimStart") == "1:15"
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("ArrowDown")
    assert page.input_value("#veTrimStart") == "1:14.9"
    # ⌖ לוקח את הזמן מהנגן (במצב פריים - שדה הזמן של התצוגה המקדימה)
    page.fill("#vePreviewTime", "12.5")
    _row_of(page, "veTrimStart").locator(".ve-time-now").first.click()
    assert page.input_value("#veTrimStart") == "12.5"
    # גרירה על התווית משנה זמן בעשיריות
    label = _row_of(page, "veTrimStart").locator("label").first
    box = label.bounding_box()
    page.mouse.move(box["x"] + 5, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + 45, box["y"] + box["height"] / 2, steps=5)
    page.mouse.up()
    value = page.evaluate("() => _veParseTime(document.getElementById('veTrimStart').value)")
    assert value != 12.5 and abs(value - 12.5) <= 1.5
