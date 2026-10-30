# tests/studio/test_web_app_editor_wave13_browser.py
#
# גל 13 בדפדפן אמיתי: מסך מלא ופריסת סטודיו (קבצים | נגן + ציר-זמן | מפקח),
# נגן חי שמצייר את העריכה מעל המקור (ffmpeg אמיתי ליצירת הקליפ), ומסך "עבודות".
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


def _make_clip(path, seconds=6):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    subprocess.run([get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=640x360:rate=10", "-f", "lavfi", "-i", f"sine=duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW_FLAGS, check=True)


def _open_folder(page, folder):
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(folder))
    page.wait_for_function("() => document.getElementById('vePreviewFile').options.length > 0", timeout=15000)


def _settle(page):
    """גל 23: מחכים שכל רענון ה-UI הנגזר (debounced) הסתיים - לא לזמן קבוע."""
    page.wait_for_function("() => typeof uiPendingWork === 'function' && uiPendingWork() === 0")


def test_the_editor_always_opens_in_the_studio_layout(editor_page):
    page = editor_page
    # גל 31: העורך תמיד בסטודיו - אין פריסה שנייה בתוך עמוד הסקריפטים
    assert page.evaluate("() => document.body.classList.contains('ve-focus')")
    assert page.evaluate("() => getComputedStyle(document.querySelector('.sidebar')).display") == "none"
    # שלוש עמודות: קבצים | נגן | מפקח
    boxes = page.evaluate("() => ['veSide', 'veViewer'].map(id => document.getElementById(id).getBoundingClientRect()).concat([document.querySelector('.ve-main').getBoundingClientRect()]).map(r => [Math.round(r.left), Math.round(r.top)])")
    tops = {top for _, top in boxes}
    assert len(tops) == 1, boxes  # באותה שורה
    lefts = [left for left, _ in boxes]
    assert lefts[0] > lefts[1] > lefts[2], boxes  # RTL: קבצים מימין, מפקח משמאל
    assert page.evaluate("() => !!document.querySelector('#veViewer #veTimelineDock')")
    # "✕ סגור" - גל 60: גלוי בסוף הסרגל (כמו בעורך הגרפים), לא בתוך ⋯ - חזרה למסך הבית
    page.click("#veFocusBtn")
    assert page.evaluate("() => [document.body.classList.contains('ve-focus'), state.selectedId]") == [False, None]
    assert page.is_visible("#homePanel")


def test_handle_click_reveals_its_settings_in_the_inspector(editor_page):
    page = editor_page
    page.evaluate("""() => new Promise(resolve => {
        const c = document.createElement('canvas'); c.width = 320; c.height = 180;
        const url = c.toDataURL('image/png'); const after = document.getElementById('vePreviewAfter');
        after.onload = () => resolve(); document.getElementById('vePreviewBefore').src = url; after.src = url;
        document.getElementById('vePreviewStageWrap').hidden = false; })""")
    page.evaluate("() => { const w = document.getElementById('vePipPath'); w.value = 'C:\\\\cam.mp4'; w.dispatchEvent(new Event('change', {bubbles: true})); }")
    _settle(page)
    page.evaluate("() => { _veRenderDragHandles(); document.getElementById('vePreviewStage').scrollIntoView({block: 'center'}); }")
    page.click("#veDragHandles [data-kind=pip]")
    page.wait_for_function("() => document.querySelector('[data-card=pip]').classList.contains('ve-inspect-focus')")


@needs_ffmpeg
def test_live_player_plays_source_with_overlays_and_trim(editor_page, tmp_path):
    page = editor_page
    _make_clip(tmp_path / "clip.mp4", 6)
    _open_folder(page, tmp_path)
    page.evaluate("""() => { addVeLayer('text'); const l = _veLayersValue(); l[0].text = 'LIVE'; l[0].start = 0; l[0].end = null; _veWriteLayers(l); _veRenderLayersEditor(true);
        const t = document.getElementById('veTrimStart'); t.value = '2'; t.dispatchEvent(new Event('input', {bubbles: true})); }""")
    page.click("#veLiveBtn")
    page.wait_for_function("() => document.getElementById('veLiveVideo').readyState >= 1 && _veLive && _veLive.timeline", timeout=20000)
    assert page.evaluate("() => document.getElementById('vePreviewStage').classList.contains('ve-stage-live')")
    timeline = page.evaluate("() => _veLive.timeline")
    assert abs(timeline["start"] - 2) < 0.05 and abs(timeline["outDuration"] - 4) < 0.3
    assert abs(page.evaluate("() => document.getElementById('veLiveVideo').currentTime") - 2) < 0.3
    assert page.evaluate("() => [...document.querySelectorAll('#veLiveOverlays .ve-live-layer')].some(e => e.textContent === 'LIVE')")
    # פורמט אנכי -> הבמה אנכית, בלי ריענון מהשרת
    page.click("#veFormatChips button[data-format='9:16']")
    page.wait_for_function("() => { const r = document.getElementById('veLive').getBoundingClientRect(); return r.height > r.width; }", timeout=5000)
    # רוויה -> פילטר CSS על הווידאו
    page.evaluate("() => { const s = document.getElementById('veEqSaturation'); s.value = '1.5'; s.dispatchEvent(new Event('input', {bubbles: true})); }")
    page.wait_for_function("() => document.getElementById('veLiveVideo').style.filter.includes('saturate(1.5)')", timeout=5000)
    # "בדיקה מדויקת" עוברת לפריים מהשרת
    page.click("button:has-text('בדיקה מדויקת')")
    page.wait_for_function("() => !document.getElementById('vePreviewStage').classList.contains('ve-stage-live')")


def test_live_player_explains_unplayable_file(editor_page, tmp_path):
    page = editor_page
    (tmp_path / "broken.mp4").write_bytes(b"not a video")
    _open_folder(page, tmp_path)
    page.click("#veLiveBtn")
    page.wait_for_function("() => !document.getElementById('veLiveError').hidden", timeout=15000)
    assert "עותק לנגינה" in page.inner_text("#veLiveError")


def test_jobs_screen_lists_projects_and_opens_one(editor_page, tmp_path):
    page = editor_page
    folder = tmp_path / "match_day"
    folder.mkdir()
    (folder / "a.mp4").write_bytes(b"x")
    page.evaluate("""async (folder) => { await fetch('/api/editor_projects', {method: 'PUT', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({folder, targets: ['shorts'], clip_edits: {'a.mp4': {trim_start: '3'}}, profile_name: 'RL'})}); }""", str(folder))
    page.click("#veFolderChip")  # גל 27: "כל העבודות" בתפריט של שבב התיקייה
    page.click("#veJobsBtn")
    page.wait_for_selector("#veJobsList .ve-job-card")
    page.wait_for_function("() => (document.querySelector('#veJobsList .ve-job-card') || {}).innerText && document.querySelector('#veJobsList .ve-job-card').innerText.trim().length > 0")
    card = page.inner_text("#veJobsList .ve-job-card")
    assert "match_day" in card and "Shorts" in card and "1 קליפים" in card and "טרם הורץ" in card
    assert page.evaluate("() => getComputedStyle(document.querySelector('.ve-shell')).display") == "none"
    page.click("#veJobsList .ve-job-card button:has-text('פתח')")
    page.wait_for_function(f"() => state.folder === {str(folder)!r}")
    assert page.evaluate("() => document.getElementById('veJobsView').hidden")
    page.wait_for_function("() => _veClipEdits['a.mp4'] && _veClipEdits['a.mp4'].trim_start === '3'", timeout=10000)
