# tests/dataviz/test_web_app_wave47_browser.py
#
# גל 47 בדפדפן: קיבוץ התור לפי תיקייה - קובצי התיקייה הראשית בקבוצה אחת, ותתי-התיקיות (שהסקריפט מעבד במלואן)
# כקבוצות מתחת לתור עם הסרטונים שבהן; כש"כולל תתי-תיקיות" כבוי - הודעה במקומן. בלי ffmpeg.


import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

IDLE = "() => typeof uiPendingWork === 'function' && uiPendingWork() === 0"


def test_the_queue_groups_by_folder_and_lists_subfolders(editor_page, tmp_path):
    page = editor_page
    for name in ("a.mp4", "b.mp4"):
        (tmp_path / name).write_bytes(b"x")
    sub = tmp_path / "יום 2"
    sub.mkdir()
    for name in ("c.mp4", "d.mkv", "notes.txt"):
        (sub / name).write_bytes(b"x")
    (tmp_path / "ריקה").mkdir()
    page.evaluate("() => _veSavePref('veAutoFrame', false)")
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    page.wait_for_function("() => (_veQueueState || []).length === 2", timeout=15000)
    page.wait_for_function(IDLE)
    page.select_option("#veQueueGroup", "folder")
    labels = page.evaluate("() => [...document.querySelectorAll('#veQueueList .ve-queue-row')].map(r => r.dataset.groupLabel || '')")
    assert labels[0].endswith("התיקייה הראשית") and labels[1] == ""
    page.wait_for_selector("#veQueueSubfolders .ve-queue-subfolder summary")
    groups = page.eval_on_selector_all("#veQueueSubfolders .ve-queue-subfolder summary", "els => els.map(e => e.textContent)")
    assert len(groups) == 1 and "יום 2" in groups[0] and "2" in groups[0]       # רק סרטונים, תיקייה ריקה לא מוצגת
    page.evaluate("() => { const box = document.getElementById('veIncludeSubfolders'); box.checked = false; _veRenderSubfolderGroups(); }")
    page.wait_for_selector("#veQueueSubfolders >> text=לא ירונדרו")
    page.select_option("#veQueueGroup", "")
    page.wait_for_function("() => !document.getElementById('veQueueSubfolders')")
