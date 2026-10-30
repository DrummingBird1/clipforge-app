# tests/web/test_web_app_wave30_browser.py
#
# גל 30 בדפדפן אמיתי - מודל עבודה פשוט ומילים ברורות: מצב אחד לעריכת קליפ (באנר, סימון ליד
# שדה שנדרס, נעילה של מה שחל על כל הקבצים, "כמו כל הקבצים" ו"החל על כל הקבצים"), אינדיקטור
# שמירה אחד, מראות מוכנים עם תצוגה, ומצב "פשוט" של ארבעה צעדים.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _settle(page):
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _opts(page):
    return page.evaluate("() => _collectRunOptions()")


def _open_folder(page, folder, names=("a.mp4", "b.mp4")):
    for name in names:
        (folder / name).write_bytes(b"x")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function(f"() => (_veQueueState || []).length === {len(names)} && document.querySelector('#veQueueList .ve-queue-clip-btn')", timeout=15000)


def _set(page, element_id, value):
    page.evaluate("([id, v]) => _veSetFieldValue(document.getElementById(id), v)", [element_id, value])


def _confirm(page):
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmOkBtn")


# --- מצב אחד לעריכת קליפ ---

def test_clip_mode_keeps_logo_and_time_changes_for_one_clip(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    _set(page, "veWatermarkPath", "C:\\logo.png")
    page.click("#veQueueList .ve-queue-row[data-name='b.mp4'] .ve-queue-clip-btn")
    assert page.is_visible("#veClipBanner") and page.inner_text("#veClipBannerName") == "b.mp4"
    assert "עוד בלי שינויים" in page.inner_text("#veClipBannerCount")
    _set(page, "veWatermarkScale", "30")
    _set(page, "veTrimStart", "3")
    opts = _opts(page)
    # כל הקבצים לא השתנו; הקליפ קיבל רק את מה ששונה בו
    assert opts["watermark_scale"] == 0.15 and opts["trim_start"] == 0
    assert opts["clip_edits"] == {"b.mp4": {"trim_start": 3, "trim_duration": None, "remove_ranges": [], "watermark_scale": 0.3}}
    assert "2 שינויים" in page.inner_text("#veClipBannerCount")
    # ✏️ ליד השדה שנדרס - לחיצה מחזירה אותו לערך של כל הקבצים
    scale_row = "document.getElementById('veWatermarkScale').closest('.ve-row')"
    assert page.evaluate(f"() => {scale_row}.classList.contains('ve-row-clip-override')")
    page.evaluate(f"() => {scale_row}.querySelector('.ve-clip-mark').click()")
    assert page.input_value("#veWatermarkScale") == "15"
    assert _opts(page)["clip_edits"] == {"b.mp4": {"trim_start": 3, "trim_duration": None, "remove_ranges": []}}
    # הערך שווה שוב לכל הקבצים = אין דריסה
    _set(page, "veTrimStart", "0")
    assert "clip_edits" not in _opts(page)
    page.click("#veClipBanner button:has-text('סיום')")
    assert page.is_hidden("#veClipBanner") and page.evaluate("() => _veTimeScope") == "recipe"


def test_clip_mode_locks_what_applies_to_all_files(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    page.evaluate("() => _veWriteLayers([{type: 'text', text: 'ALL', start: 0, end: null, position: 'top-center'}])")
    page.evaluate("() => _veRenderLayersEditor(true)")
    page.evaluate("() => enterVeClipMode('a.mp4')")
    inert = "(id) => !!document.getElementById(id).closest('[inert]')"
    assert page.evaluate(inert, "veCodec") and page.evaluate(inert, "veEqSaturation")
    assert not page.evaluate(inert, "veTrimStart") and not page.evaluate(inert, "veWatermarkScale")
    # שכבה של כל הקבצים נעולה; שכבה חדשה במצב קליפ שייכת לקליפ
    assert page.evaluate("() => document.querySelector('#veLayersRows .ve-layer-row[data-index=\"0\"]').inert")
    page.evaluate("() => addVeLayer('text')")
    assert page.evaluate("() => _veLayersValue()[1].clip") == "a.mp4"
    assert not page.evaluate("() => document.querySelector('#veLayersRows .ve-layer-row[data-index=\"1\"]').inert")
    assert "1 שינויים" in page.inner_text("#veClipBannerCount")
    # החלת הגדרות (סגנון/ביטול) היא לכל הקבצים - יוצאת קודם ממצב הקליפ
    page.evaluate("() => _applyVideoEditorFields({codec: 'av1'})")
    assert page.evaluate("() => [_veTimeScope, document.querySelectorAll('[inert].ve-clip-locked').length]") == ["recipe", 0]


def test_promote_and_revert_a_clip(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    page.evaluate("() => enterVeClipMode('a.mp4')")
    _set(page, "veTrimStart", "4")
    page.evaluate("() => addVeLayer('text')")
    page.click("#veClipPromoteBtn")
    _confirm(page)
    page.wait_for_function("() => !_veClipEdits['a.mp4']")
    opts = _opts(page)
    assert opts["trim_start"] == 4 and "clip_edits" not in opts and "clip" not in opts["layers"][0]
    # שינוי חדש ו"כמו כל הקבצים" - הקליפ חוזר לערכים של כולם (עם אישור כשיש לו שכבות)
    _set(page, "veTrimStart", "7")
    page.evaluate("() => addVeLayer('text')")
    page.click("#veClipRevertBtn")
    _confirm(page)
    page.wait_for_function("() => !_veClipEdits['a.mp4'] && _veLayersValue().length === 1")
    assert page.input_value("#veTrimStart") == "4"


def test_project_clip_edits_from_before_wave30_are_normalized(editor_page):
    out = editor_page.evaluate("""() => _veNormalizeClipEdits({
        'a.mp4': {trim_start: '0', trim_duration: '', remove_ranges: ''},
        'b.mp4': {trim_start: '0', trim_duration: '', remove_ranges: '', reset_time: true},
        'c.mp4': {trim_start: '5', trim_duration: '', remove_ranges: ''},
        'd.mp4': {trim_start: '0', trim_duration: '', remove_ranges: '', watermark_scale: '20'}})""")
    # קודם: שלושה שדות ריקים = "בלי עריכה"; עכשיו נשמרת רק דריסה אמיתית
    assert sorted(out) == ["b.mp4", "c.mp4", "d.mp4"] and out["d.mp4"] == {"watermark_scale": "20"}


# --- אינדיקטור שמירה אחד ---

def test_one_save_indicator_for_project_and_style(editor_page, tmp_path, monkeypatch):
    from utils.video import video_editor_profiles as vep
    monkeypatch.setattr(vep, "PROFILES_PATH", str(tmp_path / "p.json"))
    monkeypatch.setattr(vep, "META_PATH", str(tmp_path / "m.json"))
    monkeypatch.setattr(vep, "HISTORY_PATH", str(tmp_path / "h.json"))
    vep.save_profile("Base", {"codec": "h264"})
    page = editor_page
    folder = tmp_path / "clips"
    folder.mkdir()
    _open_folder(page, folder)
    page.wait_for_function("() => document.getElementById('veSaveStateText').textContent.includes('נשמר')", timeout=10000)
    assert page.is_hidden("#veSaveStateUpdate") and page.is_hidden("#veSaveStateNew")
    page.evaluate("() => loadVideoEditorProfiles()")
    page.evaluate("() => { document.getElementById('vePreset').value = 'profile:Base'; applyVideoEditorPreset(); }")
    page.wait_for_function("() => document.getElementById('veCodec').value === 'h264' && !!state.veBaseline")
    _set(page, "veCodec", "av1")
    page.wait_for_function("() => document.getElementById('veSaveState').dataset.state === 'dirty'")
    assert 'הסגנון "Base" שונה' in page.inner_text("#veSaveStateText")
    assert page.is_visible("#veSaveStateUpdate") and page.is_visible("#veSaveStateNew")
    # הסטטוס הישן בפס התחתון לא קיים יותר - אינדיקטור אחד
    assert page.evaluate("() => !document.getElementById('veUnsavedIndicator') && !document.getElementById('veProjectStatus')")
    page.click("#veSaveStateUpdate")
    page.wait_for_function("() => document.getElementById('veSaveState').dataset.state !== 'dirty'", timeout=10000)
    assert page.is_hidden("#veSaveStateUpdate")


# --- מראות מוכנים ---

def test_look_cards_apply_and_follow_the_sliders(editor_page):
    page = editor_page
    page.wait_for_function("() => document.querySelectorAll('#veLookCards .ve-look-card').length === 6")
    assert page.get_attribute("#veLookCards [data-look=natural]", "aria-pressed") == "true"
    page.click("#veLookCards [data-look=bw]")
    assert page.evaluate("() => [veEqSaturation.value, veEqContrast.value]") == ["0", "1.2"]
    assert page.get_attribute("#veLookCards [data-look=bw]", "aria-pressed") == "true"
    assert page.get_attribute("#veStepLookCards [data-look=bw]", "aria-pressed") == "true"
    page.click("#veLookCards [data-look=cinematic]")
    opts = _opts(page)
    assert opts["vignette"] == "light" and opts["grade_shadows"] == "-0.04,0,0.05"
    # כל כרטיס מציג את המראה שלו (פילטר צבע, ולמראות עם גלגלים/עקומות - פילטר SVG משלהם)
    filters = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#veLookCards .ve-look-card')].map(c => [c.dataset.look, c.querySelector('.ve-look-thumb').style.filter]))")
    assert "saturate(0)" in filters["bw"] and "veLookGrade-cinematic" in filters["cinematic"] and "url(" not in filters["vivid"]
    # כוונון בסליידר אחרי בחירה = "מותאם אישית"
    _set(page, "veEqSaturation", "0.7")
    page.wait_for_function("() => !document.querySelector('#veLookCards .ve-look-card[aria-pressed=true]')")
    assert page.is_visible(".ve-look-block .ve-look-custom")
    page.click("#veLookCards [data-look=natural]")
    opts = _opts(page)
    assert (opts["eq_saturation"], opts["eq_contrast"], opts["vignette"], opts["grade_shadows"]) == (1, 1, "none", "")


# --- "פשוט" = ארבעה צעדים ---

def test_simple_mode_is_four_steps(editor_page, tmp_path):
    page = editor_page
    _open_folder(page, tmp_path)
    page.evaluate("() => setVeMode('simple')")
    _settle(page)
    assert page.is_visible("#veSteps")
    for selector in ("#veCategories", "#veSide", "#veTimelineDock"):
        assert page.is_hidden(selector), selector
    assert [s for s in page.evaluate("() => [...document.querySelectorAll('#veSteps .ve-step')].map(s => s.dataset.step)")] == ["folder", "targets", "look", "run"]
    page.wait_for_function("() => document.getElementById('veStepFolderText').textContent.includes('2')")
    assert tmp_path.name in page.inner_text("#veStepFolderText")
    # צעד 2 - אותם יעדים כמו באזור "פלט"
    page.click("#veStepTargets button[data-target=shorts]")
    assert _opts(page)["targets"] == ["shorts"]
    assert page.get_attribute("#veTargetChips button[data-target=shorts]", "aria-pressed") == "true"
    page.wait_for_function("() => document.querySelector('#veSteps [data-step=targets]').classList.contains('ve-step-done')")
    page.click("#veStepTargets button[data-target=tiktok]")
    page.wait_for_function("() => document.getElementById('veStepRunText').textContent === '2 קבצים × 2 יעדים = 4 סרטונים'")
    # צעד 3 - כרטיסי מראה
    page.click("#veStepLookCards [data-look=vivid]")
    assert page.evaluate("() => veEqSaturation.value") == "1.45"
    # חיפוש הגדרה מציג את האזורים גם במצב פשוט
    page.fill("#veSearchInput", "קודק")
    page.dispatch_event("#veSearchInput", "input")
    page.wait_for_function("() => getComputedStyle(document.getElementById('veCategories')).display !== 'none'")
    assert page.is_hidden("#veSteps")
    page.fill("#veSearchInput", "")
    page.dispatch_event("#veSearchInput", "input")
    # קפיצה לשדה (אזהרה/Ctrl+K) עוברת למתקדם
    page.evaluate("() => _veRevealElement(document.getElementById('veCodec'))")
    assert page.evaluate("() => _veCurrentMode()") == "advanced"
    assert page.is_hidden("#veSteps") and page.is_visible("#veCategories")
    page.evaluate("() => setVeMode('simple')")
    page.click("#veSteps .ve-steps-more")
    assert page.evaluate("() => _veCurrentMode()") == "regular"   # 24.10.2026, החלטת המשתמש: "רגיל", לא "מומחה"


# --- מילים אחידות ---

def test_the_editor_speaks_of_styles_projects_and_branding(editor_page):
    page = editor_page
    assert page.inner_text("#vePreset option[value='']") == "בחר סגנון..."
    menu = page.evaluate("() => document.getElementById('veSaveMenu').textContent + document.getElementById('veFolderMenu').textContent")
    assert "שמור כסגנון חדש" in menu and "כל הפרויקטים" in menu
    assert page.get_attribute("#veBrandKit", "aria-label") == "מיתוג"
    text = page.evaluate("() => document.getElementById('videoEditorOptions').textContent")
    for old in ("פרופיל", "עבודות", "ערכת מותג", "מתכון"):
        assert old not in text, old
