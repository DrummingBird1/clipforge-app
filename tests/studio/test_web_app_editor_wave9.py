# tests/studio/test_web_app_editor_wave9.py
#
# גל 9 של 102-ההצעות - איכות, נגישות ובדיקות: כיסוי Playwright רחב לפאנל (97),
# aria/סדר-focus (98), bottom-sheet במובייל (99), מתג אנגלית (100), lazy-render +
# debounce למועדפים (101), ואישור עקבי (veConfirm) לכל פעולה הרסנית (102).
import re


from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.video.video_editor_field_help import FIELD_HELP
from utils.video.video_editor_field_help_en import CATEGORY_TITLES_EN, FIELD_HELP_EN
from entrypoints.web import frontend_assembly as fa

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _page_script():
    html = fa.assemble_inline_page()
    return re.findall(r"<script>(.*?)</script>", html, re.S)[-1]


# --- item 100: מונחים באנגלית לכל שדה ---

def test_every_field_has_english_help_and_every_category_a_title():
    assert set(FIELD_HELP_EN) == set(FIELD_HELP)
    for key, (term, tooltip) in FIELD_HELP_EN.items():
        assert term.strip() and tooltip.strip() and len(term) <= 40, key
        assert not re.search(r"[֐-׿]", term + tooltip), f"עברית בתרגום של {key}"
    categories = set(re.findall(r'<details class="ve-category[^"]*"(?: open)? data-cat="([a-z-]+)"', fa.assemble_inline_page()))
    assert categories == set(CATEGORY_TITLES_EN)


def test_field_help_en_endpoint():
    data = client.get("/api/video_editor/field_help_en").json()
    assert data["fields"]["codec"]["term"] == "Codec" and data["categories"]["runs"].endswith("Runs")


# --- item 102: אין יותר confirm() של הדפדפן ---

def test_no_native_confirm_left_in_page_script():
    code = re.sub(r"//[^\n]*", "", _page_script())  # בלי הערות
    assert not re.search(r"(?<![\w.])confirm\(", code)


# --- דפדפן אמיתי ---

def test_browser_every_control_has_an_accessible_name_and_no_positive_tabindex(editor_page):
    page = editor_page
    page.evaluate("() => { for (const d of _veCategoryEls()) d.open = true; addVeLayer('text'); addVeLayer('image'); }")
    missing = page.evaluate("""() => [...document.querySelectorAll('#videoEditorOptions input:not([type=hidden]), #videoEditorOptions select, #videoEditorOptions textarea')]
        .filter(el => !(el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.closest('label') || (el.id && document.querySelector(`label[for="${el.id}"]`))))
        .map(el => el.id || el.outerHTML.slice(0, 80))""")
    # שורות שנוצרות דינמית (שכבות/תור) נושאות aria-label משלהן; כל השאר מקבלים מ-_veApplyAria
    assert missing == [], missing
    assert page.evaluate("() => [...document.querySelectorAll('[tabindex]')].filter(el => parseInt(el.getAttribute('tabindex'), 10) > 0).length") == 0
    assert page.get_attribute("#veEqSaturation", "aria-valuetext") == "1.00"
    page.evaluate("() => { const r = document.getElementById('veEqSaturation'); r.value = '1.4'; r.dispatchEvent(new Event('input', {bubbles: true})); }")
    assert page.get_attribute("#veEqSaturation", "aria-valuetext") == "1.40"
    assert page.get_attribute("#veScheduleModalBg .modal", "role") == "dialog"
    assert page.evaluate("() => document.querySelector('[data-subcat=watermark]').getAttribute('role')") == "group"


def test_browser_english_toggle_swaps_labels_tooltips_and_restores(editor_page):
    page = editor_page
    codec_label = "() => document.getElementById('veCodec').closest('.ve-row').querySelector('label')"
    hebrew = page.evaluate(f"() => ({codec_label})().textContent")
    page.evaluate("() => setVeEnglish(true)")
    page.wait_for_function(f"() => ({codec_label})().textContent.includes('Codec')")
    assert page.evaluate("() => document.querySelector('[data-cat=output] .ve-cat-title').textContent") == "📐 Output & shape"
    assert "NVENC" in page.evaluate(f"() => ({codec_label})().title")
    # checkbox עוטף: הטקסט מתחלף בלי לאבד את ה-input עצמו
    assert page.evaluate("() => document.getElementById('veAutoLevels').closest('label').textContent.includes('Auto levels')")
    assert page.evaluate("() => document.getElementById('veAutoLevels').isConnected")
    # בוררים מאוחדים (composite) מקבלים גם הם מונח באנגלית
    assert page.evaluate("() => document.getElementById('veFormatChips').closest('.ve-row').querySelector('label').textContent") == "Format:"
    assert page.evaluate("() => _veLoadPref('veEnglish', false)") is True
    page.evaluate("() => setVeEnglish(false)")
    assert page.evaluate(f"() => ({codec_label})().textContent") == hebrew
    assert page.evaluate("() => document.querySelector('[data-cat=output] .ve-cat-title').textContent") == "📐 פלט וצורה"


def test_browser_mobile_bottom_sheets_one_at_a_time(editor_page):
    page = editor_page
    page.set_viewport_size({"width": 390, "height": 820})
    page.wait_for_function("() => document.body.classList.contains('ve-sheets')")
    assert page.evaluate("() => _veCategoryEls().every(d => !d.open)")
    page.evaluate("() => { document.querySelector('[data-cat=output]').open = true; }")
    page.wait_for_function("() => document.getElementById('veSheetBackdrop').classList.contains('show')")
    assert page.evaluate("() => getComputedStyle(document.querySelector('[data-cat=output] > .ve-category-body')).position") == "fixed"
    page.evaluate("() => { document.querySelector('[data-cat=time]').open = true; }")
    page.wait_for_function("() => !document.querySelector('[data-cat=output]').open")
    page.click("#veSheetBackdrop", position={"x": 10, "y": 10})
    page.wait_for_function("() => _veCategoryEls().every(d => !d.open)")
    assert page.evaluate("() => JSON.stringify(_veLoadPref('veCatOpen', {}))") == "{}"  # מצב הגיליונות לא נשמר כ"סגור" למחשב
    page.set_viewport_size({"width": 1440, "height": 950})
    page.wait_for_function("() => !document.body.classList.contains('ve-sheets')")
    assert page.evaluate("() => document.querySelector('[data-cat=output]').open") is True  # חזרה לברירת-המחדל במחשב


def test_browser_runs_list_is_lazy_and_favorites_sync_is_debounced(editor_page):
    page = editor_page
    assert page.evaluate("() => _veLazyDone.has('runs')") is False
    page.evaluate("() => { document.querySelector('[data-cat=runs]').open = true; }")
    page.wait_for_function("() => _veLazyDone.has('runs') && document.querySelector('#veRunsList').children.length > 0")
    calls = page.evaluate("""async () => {
        let count = 0; const original = syncAutoFavorites;
        syncAutoFavorites = () => { count++; original(); };
        const range = document.getElementById('veEqContrast');
        for (let i = 0; i < 25; i++) { range.value = String(1 + i / 50); range.dispatchEvent(new Event('input', {bubbles: true})); }
        await new Promise(r => setTimeout(r, 450));
        syncAutoFavorites = original;
        return count;
    }""")
    assert calls == 1


def test_browser_unsaved_changes_switch_uses_ve_confirm(editor_page):
    page = editor_page
    page.evaluate("() => openVeProfileManager()")
    page.fill("#veProfileName", "Base")
    page.once("dialog", lambda dialog: dialog.accept())  # הודעת "נשמר" (alert) - לא אישור
    page.evaluate("() => saveVideoEditorProfile()")
    page.wait_for_function("() => document.getElementById('vePreset').value === 'profile:Base'")
    page.evaluate("() => { const c = document.getElementById('veCodec'); c.value = 'av1'; c.dispatchEvent(new Event('change', {bubbles: true})); }")
    page.evaluate("() => { document.getElementById('vePreset').value = ''; applyVideoEditorPreset(); }")
    page.wait_for_selector("#veConfirmModalBg.show")
    assert page.evaluate("() => document.getElementById('vePreset').value") == "profile:Base"  # חזר עד שמאשרים
    page.click("#veConfirmCancelBtn")
    assert page.evaluate("() => [document.getElementById('vePreset').value, document.getElementById('veCodec').value]") == ["profile:Base", "av1"]
    page.evaluate("() => { document.getElementById('vePreset').value = ''; applyVideoEditorPreset(); }")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.getElementById('vePreset').value === ''")


def test_browser_smoke_every_category_opens_without_console_errors(editor_page):
    errors = []
    editor_page.on("pageerror", lambda exc: errors.append(str(exc)))
    editor_page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" and "Failed to load resource" not in msg.text else None)
    for key in editor_page.evaluate("() => _veCategoryEls().map(d => d.dataset.cat)"):
        editor_page.evaluate("(k) => { const d = document.querySelector(`[data-cat=${k}]`); d.open = true; d.scrollIntoView(); }", key)
        editor_page.wait_for_timeout(60)
    editor_page.evaluate("() => { setVeLayout('tabs'); setVeLayout('columns'); setVeLayout('accordion'); _veRefreshAllDerivedUi(); }")
    editor_page.wait_for_timeout(400)
    assert errors == []


def test_browser_switching_between_unedited_profiles_never_prompts(editor_page, tmp_path, monkeypatch):
    # רגרסיה: ve_profile_name (נקרא מהבורר עצמו) נכנס להשוואת "שינויים לא-שמורים",
    # אז *כל* מעבר מפרופיל אישי הציג אישור מדומה - הוסתר ע"י fixture שאישר confirm() לבד.
    from utils.video import video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "p.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "m.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "h.json"))
    vep.save_profile("One", {"codec": "h264"})
    vep.save_profile("Two", {"codec": "av1"})
    page = editor_page
    page.evaluate("() => loadVideoEditorProfiles()")
    page.evaluate("() => { document.getElementById('vePreset').value = 'profile:One'; applyVideoEditorPreset(); }")
    page.evaluate("() => { document.getElementById('vePreset').value = 'profile:Two'; applyVideoEditorPreset(); }")
    page.wait_for_function("() => document.getElementById('veCodec').value === 'av1'")
    assert page.evaluate("() => document.getElementById('veConfirmModalBg').classList.contains('show')") is False
