# tests/web/test_web_app_wave27_browser.py
#
# גל 27 בדפדפן אמיתי - "לנקות את המסך": הפס העליון בשורה אחת (כל השאר בתפריטים),
# שבב תיקייה עם תיקיות אחרונות, פס סטטוס אחד בתחתית, איפוס רק בשדה ששונה (ריחוף /
# קליק ימני), הנגן מציג פריים ברגע שנטענת תיקייה, בורר אחד לסוג התצוגה, וחיפוש
# ופעולות קבוצתיות בתור.
import os
import shutil
import subprocess


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _ffmpeg_available():
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    exe = get_ffmpeg_exe()
    return (os.path.isabs(exe) and os.path.exists(exe)) or bool(shutil.which(exe))


needs_ffmpeg = pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg לא זמין")


def _make_clip(path, seconds=4):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=640x360:rate=10", "-f", "lavfi", "-i", f"sine=duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


def _settle(page):
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def _set_folder(page, folder):
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))


def _set_value(page, element_id, value):
    page.evaluate(
        """([id, value]) => { const el = document.getElementById(id);
            if (el.type === 'checkbox') el.checked = value; else el.value = value;
            el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }""",
        [element_id, value],
    )
    _settle(page)


def _studio(page):
    page.evaluate("() => setVeFocus(true)")
    page.wait_for_function("() => document.body.classList.contains('ve-focus')")


# --- הפס העליון ---

def test_the_top_bar_is_one_row_and_the_rest_lives_in_menus(editor_page):
    page = editor_page
    _studio(page)
    tops = page.evaluate("""() => [...document.querySelectorAll('#veStickyBar .ve-topbar-row > *')]
        .filter(e => e.offsetParent).map(e => Math.round(e.getBoundingClientRect().top + e.getBoundingClientRect().height / 2))""")
    assert max(tops) - min(tops) <= 4, tops  # שורה אחת
    visible_buttons = page.evaluate("() => [...document.querySelectorAll('#veStickyBar button')].filter(b => b.offsetParent).length")
    assert visible_buttons <= 14, visible_buttons   # גל 58-60: 🛟 עזרה, 🔍 חיפוש כללי ו-✕ סגור - כל השאר עדיין בתפריטים
    # מה שיצא מהשורה - בתפריטים
    for menu, item in (("veFolderMenu", "veJobsBtn"), ("veSaveMenu", "veProfileManagerBtn"), ("veRunMenu", "veScheduleBtn"),
                       ("veStickyBar", "veFocusBtn"), ("veViewMenu", "veCompactToggle")):   # גל 60: "סגור" גלוי בסרגל; 24.10.2026: "רק מה ששיניתי" - ליד החיפוש
        assert page.evaluate(f"() => !!document.querySelector('#{menu} #{item}')"), item
    page.click("#veRunModeBtn")
    assert page.is_visible("#veRunMenu button:has-text('בדוק הגדרות עכשיו')") and page.is_visible("#veRunMenu button:has-text('הערך גודל ומשך')")
    # שורת הנתיב של האפליקציה מוסתרת בסטודיו - השבב מחליף אותה
    assert not page.is_visible("#folderInput")


def test_the_folder_chip_shows_the_short_name_and_recent_folders(editor_page, tmp_path):
    page = editor_page
    _studio(page)
    assert "בחר תיקייה" in page.inner_text("#veFolderChip")
    first, second = tmp_path / "first_job", tmp_path / "second_job"
    for folder in (first, second):
        folder.mkdir()
        (folder / "a.mp4").write_bytes(b"x")
        page.evaluate("""async (folder) => { await fetch('/api/editor_projects', {method: 'PUT', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({folder})}); }""", str(folder))
    _set_folder(page, first)
    page.wait_for_function("() => document.getElementById('veFolderChipName').textContent === 'first_job'")
    page.click("#veFolderChip")
    assert page.inner_text("#veFolderMenuPath") == str(first)
    recent = f"#veRecentFolders button[data-folder='{second.as_posix()}'], #veRecentFolders button[data-folder='{second}']"
    page.wait_for_selector(recent.replace("\\", "\\\\"))
    assert not page.evaluate(f"() => [...document.querySelectorAll('#veRecentFolders button')].some(b => b.dataset.folder === {str(first)!r})")
    page.evaluate(f"() => [...document.querySelectorAll('#veRecentFolders button')].find(b => b.dataset.folder === {str(second)!r}).click()")
    page.wait_for_function(f"() => state.folder === {str(second)!r}")
    assert page.inner_text("#veFolderChipName") == "second_job"
    assert page.evaluate("() => document.getElementById('veFolderMenu').hidden")


# --- פס הסטטוס ---

def test_one_status_bar_at_the_bottom_without_a_duplicate_file_count(editor_page, tmp_path):
    page = editor_page
    _studio(page)
    for name in ("a.mp4", "b.mp4", "c.mp4"):
        (tmp_path / name).write_bytes(b"x")
    _set_folder(page, tmp_path)
    page.wait_for_function("() => document.getElementById('veFileCount').textContent.includes('3')")
    _settle(page)
    bar = page.evaluate("""() => { const b = document.getElementById('veStatusBar').getBoundingClientRect();
        const s = document.getElementById('veStickyBar').getBoundingClientRect(); return {bar: b.top, top: s.top, height: b.height}; }""")
    assert bar["bar"] > bar["top"] + 200 and bar["height"] < 60, bar
    for element_id in ("veSummaryText", "veFileCount", "veEtaDisplay"):  # גל 30: אינדיקטור השמירה עבר לפס העליון
        assert page.evaluate(f"() => !!document.querySelector('#veStatusBar #{element_id}')"), element_id
    # מספר הקבצים מופיע פעם אחת
    assert "קבצים" not in page.inner_text("#veSummaryText")


def test_warnings_collapse_into_a_status_bar_button(editor_page):
    page = editor_page
    assert page.evaluate("() => document.getElementById('veWarningsToggle').hidden")
    page.select_option("#veSilenceMode", "edges")
    _set_value(page, "veTrimStart", "2")
    page.wait_for_function("() => !document.getElementById('veWarningsToggle').hidden")
    assert " ".join(page.inner_text("#veWarningsToggle").split()) == "⚠️ 1"  # האייקון הוא פריט flex - innerText מפריד בשורה
    assert page.evaluate("() => document.getElementById('veWarningsBox').hidden")
    page.click("#veWarningsToggle")
    assert page.is_visible("#veWarningsBox") and "חיתוך שקט" in page.inner_text("#veWarningsBox")
    page.click("#veWarningsToggle")
    assert not page.is_visible("#veWarningsBox")


# --- איפוס רק בשדה ששונה ---

def test_reset_appears_only_on_changed_fields_and_on_right_click(editor_page):
    page = editor_page
    visible_resets = "() => [...document.querySelectorAll('#veCategories .ve-field-reset')].filter(b => getComputedStyle(b).display !== 'none' && b.offsetParent).length"
    assert page.evaluate(visible_resets) == 0
    assert page.inner_text("#veCatSummary-look").strip() == ""
    _set_value(page, "veEqSaturation", "1.5")
    assert page.evaluate(visible_resets) == 1
    assert page.evaluate("() => document.querySelector('details[data-cat=look]').classList.contains('ve-cat-changed')")
    row = page.locator("#veEqSaturation").locator("xpath=ancestor::div[contains(@class,'ve-row')][1]")
    row.locator("label").first.click(button="right")
    page.wait_for_selector("#veRowMenu:not([hidden])")
    page.click("#veRowMenu button:has-text('אפס לברירת המחדל')")
    _settle(page)
    assert page.evaluate("() => document.getElementById('veEqSaturation').value") == "1"
    assert page.evaluate(visible_resets) == 0
    assert page.evaluate("() => document.getElementById('veRowMenu').hidden")
    # קליק ימני על שדה שלא שונה - תפריט הדפדפן הרגיל (שלנו לא נפתח)
    page.locator("#veEqContrast").locator("xpath=ancestor::div[contains(@class,'ve-row')][1]").locator("label").first.click(button="right")
    assert page.evaluate("() => document.getElementById('veRowMenu').hidden")


# --- הנגן ---

@needs_ffmpeg
def test_loading_a_folder_shows_a_frame_right_away(editor_page, tmp_path):
    page = editor_page
    _make_clip(tmp_path / "clip.mp4")
    _set_folder(page, tmp_path)
    page.wait_for_function("() => !document.getElementById('vePreviewStageWrap').hidden && _veInLiveMode()", timeout=15000)
    page.wait_for_function("() => document.getElementById('veLiveVideo').readyState >= 2", timeout=20000)
    assert page.evaluate("() => document.getElementById('veLiveVideo').paused")  # מציג פריים, לא מנגן לבד
    assert page.get_attribute("#veLiveBtn", "aria-pressed") == "true"
    assert page.get_attribute("#veFrameBtn", "aria-pressed") == "false"


def test_the_preview_toolbar_is_one_mode_switch_with_player_tools_in_the_corner(editor_page):
    page = editor_page
    group = page.evaluate("() => [...document.querySelectorAll('.ve-preview-modes .ve-mode-toggle button')].map(b => b.id)")
    assert group == ["veLiveBtn", "veFrameBtn", "vePreviewClipBtn"]
    for element_id in ("vePreviewHandles", "veSafeZones", "veScopesBtn", "vePreviewAuto"):
        assert page.evaluate(f"() => !!document.querySelector('#vePreviewStageWrap .ve-stage-tools #{element_id}')"), element_id
    # בדיקה והערכה כבר לא בנגן
    assert page.evaluate("() => !document.querySelector('#veViewer [onclick^=runVeValidation], #veViewer [onclick^=runVeEstimate]')")


# --- התור ---

def test_queue_search_and_the_floating_bulk_bar(editor_page, tmp_path):
    page = editor_page
    for name in ("intro_a.mp4", "match_1.mp4", "match_2.mp4", "outro.mp4"):
        (tmp_path / name).write_bytes(b"x")
    _set_folder(page, tmp_path)
    page.evaluate("() => refreshVeQueue()")
    page.wait_for_function("() => document.querySelectorAll('#veQueueList .ve-queue-row').length === 4")
    assert not page.is_visible("#veQueueBulkBar")
    assert not page.is_visible("#veQueueFilters")
    page.fill("#veQueueSearch", "match")
    visible = "() => [...document.querySelectorAll('#veQueueList .ve-queue-row')].filter(r => !r.hidden).map(r => r.dataset.name)"
    assert page.evaluate(visible) == ["match_1.mp4", "match_2.mp4"]
    # "בחר הכל" בוחר רק את מה שהחיפוש מראה
    page.click("#veQueueToolbar button[aria-label='בחר הכל']")
    assert page.evaluate("() => _veQueueState.filter(f => f._picked).map(f => f.name)") == ["match_1.mp4", "match_2.mp4"]
    assert page.is_visible("#veQueueBulkBar") and "2" in page.inner_text("#veQueuePickedCount")
    page.click("#veQueueBulkBar button:has-text('הוצא')")
    assert page.evaluate("() => _veQueueState.filter(f => f.selected).map(f => f.name)") == ["intro_a.mp4", "outro.mp4"]
    page.click("#veQueueBulkBar button[aria-label='נקה בחירה']")
    assert not page.is_visible("#veQueueBulkBar")
    page.fill("#veQueueSearch", "")
    assert len(page.evaluate(visible)) == 4
    page.click("#veQueueFilterBtn")
    assert page.is_visible("#veQueueFilters") and page.get_attribute("#veQueueFilterBtn", "aria-expanded") == "true"
