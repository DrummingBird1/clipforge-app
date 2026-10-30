# tests/studio/test_web_app_studio_timeline_dock_browser.py
#
# 24.10.2026, מנה 6 - החלטת המשתמש מסיור השימושיות בסטודיו (ממצא 9): ב-1440x900 ציר הזמן היה מתחת לקצה המסך (y=862) בתוך העמודה
# האמצעית שנגללת, וכשגוללים אליו הנגן יוצא מהמסך. עכשיו בלשונית "✂️ זמן" ציר הזמן צמוד לתחתית העמודה, עם גלילה משלו כשהוא
# גבוה, והנגן מצטמצם לגובה שנשאר - הנגן, פס הנגן וציר הזמן נראים יחד בלי לגלול (89-studio-more.js / .css).
# xdist-group: workspace
import pytest

from tests.web.test_web_app_wave27_browser import _make_clip, _set_folder, _studio, needs_ffmpeg

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
TOGETHER = """() => { const viewer = document.getElementById('veViewer').getBoundingClientRect();
  const bar = document.getElementById('veLiveBar').getBoundingClientRect(), dock = document.getElementById('veTimelineDock').getBoundingClientRect();
  return document.getElementById('veViewer').scrollTop === 0 && bar.bottom <= dock.top + 1 && dock.top < viewer.bottom
         && dock.bottom <= viewer.bottom + 1 && dock.height >= 60 && document.getElementById('veLive').offsetHeight >= 150; }"""


@needs_ffmpeg
def test_in_the_time_tab_the_player_and_the_timeline_fit_together(editor_page, tmp_path):
    page = editor_page
    page.set_viewport_size({"width": 1440, "height": 900})
    _make_clip(tmp_path / "clip.mp4")
    _studio(page)
    page.wait_for_function(LOADED)
    page.evaluate("() => { setVeMode('advanced'); setVeLayout('tabs'); _veActivateTab('time'); }")   # התוכן של ציר הזמן - במומחה
    _set_folder(page, tmp_path)
    page.wait_for_function("() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", timeout=20000)
    page.evaluate("() => { document.getElementById('veViewer').scrollTop = 0; _veScheduleLiveRebuild(); }")
    page.wait_for_function(TOGETHER, timeout=10000)                                   # קודם: ציר הזמן מתחת לקצה העמודה

    page.evaluate("() => _veActivateTab('look')")                                       # בשאר הלשוניות - כמו קודם
    assert not page.evaluate("() => document.getElementById('videoEditorOptions').classList.contains('ve-tl-docked')")
    page.evaluate("() => { _veActivateTab('time'); setVeLayout('accordion'); }")          # וב"הכל ברשימה"
    assert not page.evaluate("() => document.getElementById('videoEditorOptions').classList.contains('ve-tl-docked')")
