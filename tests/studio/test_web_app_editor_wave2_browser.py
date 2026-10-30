# tests/studio/test_web_app_editor_wave2_browser.py
#
# גל 2 של 102-ההצעות - ארגון וסידור עורך-העל (items 1-18), נבדק בדפדפן אמיתי
# (Microsoft Edge דרך Playwright, ראו editor_page ב-conftest.py) ולא רק ברמת
# מרקאפ: סדר קטגוריות לפי זרימת-עבודה, שכבות מאוחדות, מעברים/אפקטים, חשיפה
# מדורגת, טאבים/שתי עמודות, מצב צפוף, זכירת פתוח/סגור, גרירת סדר, איפוס
# קטגוריה, אזהרות ⚠️, קיבוץ כפתורי פרופיל, כפתור הרץ + ספירת קבצים בפס הצף,
# כרטיס-תקציר, empty-state, חיפוש גלובלי, Ctrl+K וקיצורי מקלדת.


import pytest


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(page):
    """גל 23: מחכים שכל רענון ה-UI הנגזר (debounced) הסתיים - לא לזמן קבוע."""
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _set_value(page, element_id, value):
    page.evaluate(
        """([id, value]) => { const el = document.getElementById(id);
            if (el.type === 'checkbox') el.checked = value; else el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }""",
        [element_id, value],
    )
    _settle(page)  # _veRefreshAllDerivedUi הוא debounced (150ms)


def _row_hidden(page, element_id):
    return page.evaluate("id => getComputedStyle(document.getElementById(id).closest('.ve-row')).display === 'none'", element_id)


def test_categories_follow_workflow_order_with_layers_and_effects(editor_page):
    # גל 10 (סידור מחדש): 7 אזורים לפי זרימת-העבודה; קבצים+תצוגה מקדימה בחלונית
    # הצד וריצות במגירה למטה - לא חלק מהסדר הניתן-לגרירה.
    order = editor_page.evaluate("() => _veCategoryOrder()")
    # גל 28: "מראה" התפצל ל"צבע" (look) ול"אפקטים וניקוי" (effects)
    # גל 34: הפלט והצורה עברו אחרי השמע - קודם עורכים, אחר כך מחליטים על הפלט
    assert order == ["time", "look", "effects", "layers", "sound", "output", "export", "perf"]
    subcats = editor_page.evaluate("() => Array.from(document.querySelectorAll('[data-cat=layers] .ve-subcat')).map(s => s.dataset.subcat)")
    assert subcats == ["watermark", "pip", "timed-layers", "decor", "frame", "removal"]
    # טקסט קבוע הפך לשכבת טקסט (השדה הישן מוסתר), ו-fade הוא חלק מ"זמן"
    assert editor_page.evaluate("() => document.getElementById('veText').closest('#veLegacyFields') !== null")
    assert editor_page.evaluate("() => document.getElementById('veFadeInSeconds').closest('[data-cat]').dataset.cat") == "time"


def test_old_deep_links_to_watermark_and_pip_still_land_in_layers(editor_page):
    editor_page.evaluate("() => { document.querySelector('[data-cat=layers]').open = false; veScrollToCategory('pip'); }")
    assert editor_page.evaluate("() => document.querySelector('[data-cat=layers]').open") is True


def test_progressive_disclosure_hides_dependent_rows_until_parent_is_set(editor_page):
    assert _row_hidden(editor_page, "veWatermarkOpacity")
    assert _row_hidden(editor_page, "veChromakeySimilarity")
    _set_value(editor_page, "veWatermarkPath", "C:\\logo.png")
    _set_value(editor_page, "veChromakey", True)
    assert not _row_hidden(editor_page, "veWatermarkOpacity")
    assert not _row_hidden(editor_page, "veChromakeySimilarity")
    # "הצג תמיד שדות תלויים" - מעומעם במקום מוסתר
    _set_value(editor_page, "veChromakey", False)
    editor_page.evaluate("() => setVeShowDependent(true)")
    assert not _row_hidden(editor_page, "veChromakeySimilarity")
    assert editor_page.evaluate("() => document.getElementById('veChromakeySimilarity').closest('.ve-row').classList.contains('ve-dep-dim')")


def test_rules_show_warnings_and_category_markers(editor_page):
    _set_value(editor_page, "veCaptions", True)
    warnings = editor_page.evaluate("() => Array.from(document.querySelectorAll('#veWarningsBox .ve-warning')).map(e => e.textContent)")
    assert any("שמירת אודיו" in w for w in warnings)
    assert editor_page.evaluate("() => !document.getElementById('veCatWarn-sound').hidden")
    _set_value(editor_page, "veKeepAudio", True)
    assert editor_page.evaluate("() => document.getElementById('veCatWarn-sound').hidden")
    assert editor_page.evaluate("() => document.getElementById('veWarningsBox').hidden")


def test_hwaccel_with_h264_warns_in_export_and_resources(editor_page):
    _set_value(editor_page, "veHwaccel", True)
    for cat in ("export", "perf"):
        assert editor_page.evaluate(f"() => !document.getElementById('veCatWarn-{cat}').hidden")
    _set_value(editor_page, "veCodec", "hevc")
    assert editor_page.evaluate("() => document.getElementById('veCatWarn-export').hidden")


def test_tabs_layout_shows_one_category_and_switches(editor_page):
    editor_page.evaluate("() => setVeLayout('tabs')")
    visible = editor_page.evaluate("() => _veCategoryEls().filter(d => getComputedStyle(d).display !== 'none').map(d => d.dataset.cat)")
    assert visible == ["time"]  # גל 34: הלשוניות בסדר זרימת העבודה
    editor_page.click("#veCatTabs button:has-text('שמע')")
    visible = editor_page.evaluate("() => _veCategoryEls().filter(d => getComputedStyle(d).display !== 'none').map(d => d.dataset.cat)")
    assert visible == ["sound"]


def test_list_layout_shows_every_area(editor_page):
    # גל 31: "שתי עמודות" ירדה (היא הייתה רק מחוץ לסטודיו) - בסטודיו לשוניות או הכל ברשימה
    editor_page.evaluate("() => setVeLayout('accordion')")
    shown = editor_page.evaluate("() => _veCategoryEls().filter(d => getComputedStyle(d).display !== 'none').length")
    assert shown == editor_page.evaluate("() => _veCategoryEls().length") and editor_page.is_hidden("#veCatTabs")
    editor_page.evaluate("() => setVeLayout('columns')")  # ערך ישן מהעדפות - לשוניות
    assert editor_page.evaluate("() => _veCurrentLayout()") == "tabs"


def test_view_preferences_survive_reload(editor_page, editor_server):
    editor_page.evaluate("() => { setVeCompact(true); _veMoveCategory('perf', 'output'); }")
    editor_page.evaluate("() => { document.querySelector('details[data-cat=output]').open = false; }")  # ברשימה
    _settle(editor_page)
    editor_page.evaluate("() => setVeLayout('tabs')")
    editor_page.reload()
    editor_page.wait_for_function("() => typeof state !== 'undefined' && state.scripts.length > 0")
    editor_page.evaluate("() => selectScript(state.scripts.find(s => s.id.endsWith('video_editor.py')).id)")
    assert editor_page.evaluate("() => document.getElementById('videoEditorOptions').classList.contains('ve-compact')")
    assert editor_page.evaluate("() => _veCurrentLayout()") == "tabs"
    order = editor_page.evaluate("() => _veCategoryOrder()")
    assert order.index("perf") == order.index("output") - 1
    editor_page.evaluate("() => setVeLayout('accordion')")  # מצב פתוח/סגור נשמר לרשימה
    assert editor_page.evaluate("() => document.querySelector('details[data-cat=output]').open") is False


def test_alt_arrow_moves_focused_category(editor_page):
    editor_page.focus("[data-cat=look] > summary")
    editor_page.keyboard.press("Alt+ArrowUp")
    order = editor_page.evaluate("() => _veCategoryOrder()")
    assert order.index("look") < order.index("time")


def test_reset_category_resets_only_that_category_after_confirm(editor_page):
    _set_value(editor_page, "veDenoise", True)
    _set_value(editor_page, "veSharpen", True)
    _set_value(editor_page, "veKeepAudio", True)
    editor_page.click("[data-cat-reset=effects]")  # גל 28: רעש/חידוד באזור "אפקטים וניקוי"
    editor_page.wait_for_selector("#veConfirmModalBg.show")
    assert "2" in editor_page.inner_text("#veConfirmMessage")
    editor_page.click("#veConfirmOkBtn")
    editor_page.wait_for_function("() => !document.getElementById('veDenoise').checked && !document.getElementById('veSharpen').checked")
    assert editor_page.evaluate("() => document.getElementById('veDenoise').checked") is False
    assert editor_page.evaluate("() => document.getElementById('veSharpen').checked") is False
    assert editor_page.evaluate("() => document.getElementById('veKeepAudio').checked") is True
    # הכותרת לא התקפלה/נפתחה בגלל הלחיצה על ↺
    assert editor_page.evaluate("() => document.querySelector('[data-cat=effects]').open") is True
    assert editor_page.evaluate("() => document.getElementById('veDenoiseMode').value") == "off"


def test_reset_category_cancel_keeps_values(editor_page):
    _set_value(editor_page, "veDenoise", True)
    editor_page.click("[data-cat-reset=effects]")
    editor_page.wait_for_selector("#veConfirmModalBg.show")
    editor_page.click("#veConfirmCancelBtn")
    assert editor_page.evaluate("() => document.getElementById('veDenoise').checked") is True


def test_empty_state_and_changed_count_in_category_summaries(editor_page):
    # גל 27: אזור בלי שינויים - כותרת בלי טקסט (לא "שום דבר לא מופעל כאן" בכל אזור)
    assert editor_page.inner_text("#veCatSummary-effects").strip() == ""
    # הסיכום מתעדכן ב-debounce - מחכים לטקסט עצמו ולא לזמן קבוע (runner איטי ב-CI)
    summary_has = "(text) => document.getElementById('veCatSummary-effects').innerText.includes(text)"
    _set_value(editor_page, "veDenoise", True)
    editor_page.wait_for_function(summary_has, arg="הגדרה אחת שונתה")
    _set_value(editor_page, "veSharpen", True)
    editor_page.wait_for_function(summary_has, arg="2 הגדרות שונו")


def test_profile_actions_grouped_in_profile_manager_dialog(editor_page):
    # גל 10: כל פעולות הפרופיל עברו לדיאלוג "👤 פרופילים" - בפס העליון נשארו
    # רק בורר הפרופיל, 💾 שמור (עם ▾ לשמירה בשם) והכפתור שפותח את הדיאלוג.
    assert editor_page.evaluate("() => document.getElementById('veProfileModalBg').classList.contains('show')") is False
    editor_page.click("button[aria-label='אפשרויות שמירה']")  # גל 27: בתפריט של 💾 שמור ▾
    editor_page.click("#veProfileManagerBtn")
    editor_page.wait_for_selector("#veProfileModalBg.show")
    editor_page.fill("#veProfileName", "Browser Test")
    editor_page.evaluate("() => saveVideoEditorProfile()")
    editor_page.wait_for_function("() => !document.getElementById('veRenameProfileBtn').hidden")
    buttons = editor_page.evaluate("() => Array.from(document.querySelectorAll('#veProfileModalBg button')).filter(b => !b.hidden && b.offsetParent).map(b => b.id).filter(Boolean)")
    assert {"veUpdateProfileBtn", "veRenameProfileBtn", "veDuplicateProfileBtn", "veHistoryProfileBtn", "veExportProfileBtn", "veDeleteProfileBtn", "veDefaultProfileBtn"} <= set(buttons)
    editor_page.evaluate("() => closeVeProfileManager()")
    assert editor_page.evaluate("() => document.getElementById('veProfileModalBg').classList.contains('show')") is False


def test_sticky_run_button_mirrors_main_run_button_and_file_count(editor_page, tmp_path):
    for name in ("a.mp4", "b.mkv", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub").mkdir()
    assert editor_page.evaluate("() => document.getElementById('veStickyRunBtn').disabled") is True
    editor_page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    editor_page.wait_for_function("() => !document.getElementById('veFileCount').hidden")
    assert editor_page.evaluate("() => document.getElementById('veStickyRunBtn').disabled") is False
    count_text = editor_page.inner_text("#veFileCount")
    assert "2 קבצים" in count_text and "1 תתי-תיקיות" in count_text


def test_summary_card_reflects_settings(editor_page):
    assert "אופקי 16:9" in editor_page.inner_text("#veSummaryText")
    _set_value(editor_page, "veVertical", True)
    _set_value(editor_page, "veCodec", "av1")
    text = editor_page.inner_text("#veSummaryText")
    assert "אנכי 9:16" in text and "AV1" in text


def test_global_search_filters_rows_and_restores(editor_page):
    editor_page.fill("#veSearchInput", "LUFS")  # החיפוש רץ סינכרונית על input
    visible_cats = editor_page.evaluate("() => _veCategoryEls().filter(d => getComputedStyle(d).display !== 'none').map(d => d.dataset.cat)")
    assert visible_cats == ["sound"]
    assert not _row_hidden(editor_page, "veLoudnormTarget")  # תלוי ב-loudnorm, אבל בחיפוש רק מעומעם
    editor_page.fill("#veSearchInput", "")
    editor_page.dispatch_event("#veSearchInput", "input")
    visible_cats = editor_page.evaluate("() => _veCategoryEls().filter(d => getComputedStyle(d).display !== 'none').length")
    assert visible_cats == 8  # גל 28: 8 אזורי-הגדרות (קבצים/תצוגה/ריצות מחוץ לרשימה)


def test_slash_focuses_search_and_question_mark_opens_shortcuts(editor_page):
    editor_page.click("#veSummaryCard")
    editor_page.keyboard.press("/")
    assert editor_page.evaluate("() => document.activeElement.id") == "veSearchInput"
    editor_page.evaluate("() => document.activeElement.blur()")
    editor_page.keyboard.press("?")
    assert editor_page.evaluate("() => document.getElementById('veShortcutsModalBg').classList.contains('show')")


def test_ctrl_k_palette_lists_editor_fields_and_jumps(editor_page):
    editor_page.keyboard.press("Control+k")
    editor_page.fill("#paletteInput", "LUT")
    sections = editor_page.evaluate("() => Array.from(document.querySelectorAll('#paletteList .ve-palette-section')).map(e => e.textContent)")
    assert "⚙️ הגדרות" in sections
    editor_page.evaluate("() => document.querySelector('[data-cat=look]').open = false")
    editor_page.keyboard.press("Enter")
    assert editor_page.evaluate("() => document.querySelector('[data-cat=look]').open") is True


def test_ctrl_s_without_profile_prompts_for_name_and_saves(editor_page, ve_prompt):
    editor_page.click("#veSummaryCard")
    editor_page.keyboard.press("Control+s")
    ve_prompt(editor_page, "Shortcut Saved")
    editor_page.wait_for_function("() => document.getElementById('vePreset').value === 'profile:Shortcut Saved'", timeout=5000)
