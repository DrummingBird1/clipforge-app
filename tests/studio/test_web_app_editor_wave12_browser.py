# tests/studio/test_web_app_editor_wave12_browser.py
#
# גל 12 בדפדפן אמיתי: שבבי יעדים (ומה שהם משנים בממשק), עריכת קליפ (גל 30: מצב אחד -
# "רק הקליפ הזה") עם ✏️ בתור, שכבה לקובץ אחד, מיתוג מקושר, ופרויקט שנשמר אוטומטית
# ומשוחזר כשפותחים שוב את אותה תיקייה.


import pytest


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _opts(page):
    return page.evaluate("() => _collectRunOptions()")


def _open_folder(page, folder):
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function("() => document.getElementById('vePreviewFile').options.length > 0", timeout=15000)


def _fake_clips(folder, names):
    for name in names:
        (folder / name).write_bytes(b"x")


def test_target_chips_drive_options_run_label_and_safe_zone(editor_page):
    page = editor_page
    page.wait_for_selector("#veTargetChips button[data-target=shorts]")
    page.click("#veTargetChips button[data-target=shorts]")
    assert not page.is_visible("#veTargetChips button[data-target=discord]")   # גל 58: מאחורי "עוד יעדים"
    page.click("#veTargetChips .ve-more-targets")
    page.click("#veTargetChips button[data-target=discord]")
    page.click("#veTargetChips .ve-more-targets")                               # מקפלים - יעד שנבחר נשאר גלוי
    assert page.is_visible("#veTargetChips button[data-target=discord]")
    assert _opts(page)["targets"] == ["shorts", "discord"]
    assert page.evaluate("() => document.querySelector('[data-cat=output]').classList.contains('ve-targets-active')")
    assert "2 יעדים" in page.inner_text("#veStickyRunBtn")
    assert page.evaluate("() => document.getElementById('veSafeZones').value") == "shorts"
    assert not page.evaluate("() => document.getElementById('vePreviewTargetWrap').hidden")
    page.click("#veTargetChips button[data-target=shorts]")
    assert _opts(page)["targets"] == ["discord"]
    page.click("#veTargetChips button[data-target=discord]")
    assert _opts(page)["targets"] == [] and "יעדים" not in page.inner_text("#veStickyRunBtn")


def test_targets_restore_from_profile(editor_page):
    page = editor_page
    page.evaluate("() => _applyVideoEditorFields({targets: ['tiktok', 'youtube']})")
    page.wait_for_function("() => document.querySelector('#veTargetChips button[data-target=tiktok]').getAttribute('aria-pressed') === 'true'")
    assert _opts(page)["targets"] == ["tiktok", "youtube"]


def test_clip_mode_keeps_the_project_settings_and_per_clip_trims_separate(editor_page, tmp_path):
    page = editor_page
    _fake_clips(tmp_path, ["a.mp4", "b.mp4"])
    _open_folder(page, tmp_path)
    page.fill("#veTrimStart", "2")
    page.dispatch_event("#veTrimStart", "input")
    page.select_option("#vePreviewFile", "a.mp4")
    page.click("#veClipModeBtn")
    assert page.input_value("#veTrimStart") == "2"  # גל 30: קליפ בלי עריכה מציג את הערך של כל הקבצים
    page.fill("#veTrimStart", "5")
    page.dispatch_event("#veTrimStart", "input")
    opts = _opts(page)
    assert opts["trim_start"] == 2 and opts["clip_edits"] == {"a.mp4": {"trim_start": 5, "trim_duration": None, "remove_ranges": []}}
    # מעבר לקובץ אחר בתצוגה המקדימה = עריכה של הקובץ ההוא
    page.select_option("#vePreviewFile", "b.mp4")
    page.dispatch_event("#vePreviewFile", "change")
    assert page.input_value("#veTrimStart") == "2"
    page.click("#veClipBanner button:has-text('סיום')")
    assert page.input_value("#veTrimStart") == "2"
    page.wait_for_function("() => document.querySelectorAll('#veQueueList .ve-clip-badge').length === 1", timeout=10000)


def test_clip_edits_do_not_mark_the_profile_unsaved(editor_page, tmp_path):
    page = editor_page
    _fake_clips(tmp_path, ["a.mp4"])
    _open_folder(page, tmp_path)
    before = page.evaluate("() => _veComparableOptionsJson()")
    page.click("#veClipModeBtn")
    page.fill("#veTrimStart", "4")
    page.dispatch_event("#veTrimStart", "input")
    # גל 24 (נמצא ב-CI): המועדפים האוטומטיים מחושבים מושהה - כשהחישוב נופל בזמן עריכת
    # הקליפ, trim_start של הקליפ לא נחשב שינוי במתכון. כאן מריצים אותו בכוונה באמצע.
    page.evaluate("() => syncAutoFavorites()")
    assert page.evaluate("() => _veComparableOptionsJson()") == before
    page.evaluate("() => exitVeClipMode()")
    assert page.evaluate("() => _veComparableOptionsJson()") == before


def test_layer_can_belong_to_one_file(editor_page, tmp_path):
    page = editor_page
    _fake_clips(tmp_path, ["a.mp4", "b.mp4"])
    _open_folder(page, tmp_path)
    page.wait_for_function("() => (_veQueueState || []).length === 2", timeout=10000)
    page.evaluate("() => { addVeLayer('text'); const l = _veLayersValue(); l[0].text = 'GOAL'; _veWriteLayers(l); _veRenderLayersEditor(true); }")
    page.select_option("#veLayersRows .ve-layer-clip", "b.mp4")
    assert page.evaluate("() => _veLayersValue()[0].clip") == "b.mp4"
    page.wait_for_function("() => document.querySelectorAll('#veQueueList .ve-clip-badge').length === 1")


def test_brand_kit_save_link_and_diff_indicator(editor_page, ve_prompt):
    page = editor_page
    page.evaluate("() => { const w = document.getElementById('veWatermarkPath'); w.value = 'C:\\\\rl.png'; w.dispatchEvent(new Event('change', {bubbles: true})); }")
    page.click("button:has-text('שמור כמיתוג')")
    ve_prompt(page, "Rocket")
    page.wait_for_function("() => document.getElementById('veBrandKit').value === 'Rocket'")
    assert _opts(page)["brand_kit"] == "Rocket"
    assert "מקושר" in page.inner_text("#veBrandStatus")
    page.evaluate("() => { const w = document.getElementById('veWatermarkPath'); w.value = 'C:\\\\other.png'; w.dispatchEvent(new Event('change', {bubbles: true})); }")
    page.wait_for_function("() => document.getElementById('veBrandStatus').textContent.includes('שונים מהמיתוג')")
    # בחירה מחדש של הערכה מחזירה את ערכיה לשדות
    page.select_option("#veBrandKit", "")
    page.select_option("#veBrandKit", "Rocket")
    page.wait_for_function("() => document.getElementById('veWatermarkPath').value === 'C:\\\\rl.png'")


def test_project_autosaves_and_restores_clip_edits_and_targets(editor_page, tmp_path):
    page = editor_page
    _fake_clips(tmp_path, ["a.mp4"])
    other = tmp_path / "other"
    other.mkdir()
    _fake_clips(other, ["z.mp4"])
    _open_folder(page, tmp_path)
    page.click("#veTargetChips button[data-target=tiktok]")
    page.click("#veClipModeBtn")
    page.fill("#veTrimStart", "6")
    page.dispatch_event("#veTrimStart", "input")
    page.evaluate("() => exitVeClipMode()")
    page.wait_for_function("() => _veProjectSaveInfo.state === 'saved' && document.getElementById('veSaveStateText').textContent.includes('נשמר')", timeout=10000)
    # תיקייה אחרת ואז חזרה - העריכות והיעדים חוזרים
    _open_folder(page, other)
    page.wait_for_function("() => Object.keys(_veClipEdits).length === 0")
    page.click("#veTargetChips button[data-target=tiktok]")  # מבטל
    _open_folder(page, tmp_path)
    page.wait_for_function("() => _veClipEdits['a.mp4'] && _veClipEdits['a.mp4'].trim_start === '6'", timeout=10000)
    assert _opts(page)["targets"] == ["tiktok"]
    # גל 58: אין הבדל בהגדרות - הודעה קופצת שנעלמת, לא שורה ברוחב מלא
    page.wait_for_function("() => (document.getElementById('toastHost') || {}).textContent?.includes('שוחזרו עריכות הקליפים')")
    assert page.evaluate("() => document.getElementById('veProjectBanner').hidden")
