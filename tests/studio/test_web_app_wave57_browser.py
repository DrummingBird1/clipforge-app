# tests/studio/test_web_app_wave57_browser.py
#
# גל 57 בדפדפן - תיקוני הפריסה שנמצאו בבדיקת המסכים: בסטודיו הנגן החי ופס הנגן נכנסים בגובה העמודה (בלי גלילה פנימית)
# והלוג מקופל כשאין ריצה (נפתח בכישלון); בעורך הגרפים - בלי תקרת 760 במסך רחב, עריכה בעמודה רחבה עם הלשוניות בשורה
# אחת, ו"הרץ" בסרגל העליון. config.yaml של הפרקים לא משתנה.
# xdist-group: workspace
import hashlib


import pytest

from tests.dataviz_helpers import write_episode
from tests.web.test_web_app_wave27_browser import _make_clip, _set_folder, _studio, needs_ffmpeg

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
FITS = """() => { const viewer = document.getElementById('veViewer'), bar = document.getElementById('veLiveBar');
  return !bar.hidden && bar.getBoundingClientRect().bottom <= viewer.getBoundingClientRect().bottom + 1
         && document.getElementById('veLive').offsetHeight >= 200; }"""
COLLAPSED = "() => document.getElementById('consoleDrawer').classList.contains('collapsed')"


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


# ---------- הסטודיו ----------
@needs_ffmpeg
def test_the_live_player_and_its_bar_fit_the_studio_column(editor_page, tmp_path):
    page = editor_page
    page.set_viewport_size({"width": 1440, "height": 900})
    _make_clip(tmp_path / "clip.mp4")
    _studio(page)
    _set_folder(page, tmp_path)
    page.wait_for_function("() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", timeout=20000)
    page.wait_for_function(FITS, timeout=10000)
    page.evaluate("() => setVeMode('advanced')")                 # במצב מומחה יש עוד דברים בעמודה - הנגן עדיין נכנס
    page.evaluate("() => _veScheduleLiveRebuild()")
    page.wait_for_function(FITS, timeout=10000)


def test_the_studio_log_is_folded_until_something_runs_or_fails(editor_page):
    page = editor_page
    _studio(page)
    page.evaluate("() => { try { localStorage.removeItem('uiStudioConsoleOpen'); } catch (e) {} _uiSyncShell(); }")
    assert page.evaluate(COLLAPSED) and page.is_visible("#consoleToggle")
    page.click("#consoleToggle")
    assert not page.evaluate(COLLAPSED) and page.evaluate("() => localStorage.getItem('uiStudioConsoleOpen')") == "1"
    page.click("#consoleToggle")
    assert page.evaluate(COLLAPSED) and page.evaluate("() => localStorage.getItem('uiStudioConsoleOpen')") == "0"
    page.evaluate("() => appendLogBatch([{line: '❌ הסקריפט נכשל.', tag: 'red'}])")
    assert not page.evaluate(COLLAPSED)                                    # כישלון פותח את הלוג
    assert page.evaluate("() => localStorage.getItem('uiStudioConsoleOpen')") == "0"   # בלי לשנות את ההעדפה


# ---------- עורך הגרפים ----------
def test_wide_screen_editing_layout_and_run_in_the_top_bar(editor_page, screen):
    page = editor_page
    page.set_viewport_size({"width": 1920, "height": 1080})
    # 21.10.2026: עורך הגרפים נפתח ב"פשוט" (רק לשונית ההגדרות) - כאן "רגיל", כדי שכל הלשוניות ייבדקו בשורה אחת
    page.evaluate("() => localStorage.setItem('dvzMode', 'regular')")
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    assert page.evaluate("() => ['dvzMode', 'dvzRunBtn', 'dvzStopBtn', 'dvzStatus', 'dvzProgressBar'].every(id => document.getElementById(id).closest('.dvz-topbar'))")
    assert page.is_visible("#dvzRunBtn") and page.is_visible("#dvzMode")
    sizes = page.evaluate("""() => ({preview: document.getElementById('dvzPreviewPane').getBoundingClientRect().width,
                                     grid: document.querySelector('.dvz-studio').getBoundingClientRect().width,
                                     outputs: document.getElementById('dvzOutputs').closest('.tc-section').getBoundingClientRect().width})""")
    assert sizes["preview"] > 900 and abs(sizes["outputs"] - sizes["grid"]) < 2, sizes   # בלי התקרה של 760
    assert not page.is_visible(".dvz-episodes-toggle")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorTabs button")
    assert not page.is_visible(".dvz-episodes-pane") and page.is_visible(".dvz-episodes-toggle")
    assert page.evaluate("() => document.getElementById('dvzControls').getBoundingClientRect().width") >= 560
    tops = page.evaluate("() => [...document.querySelectorAll('#dvzEditorTabs button')].filter(b => b.offsetParent).map(b => Math.round(b.getBoundingClientRect().top))")
    assert len(tops) == 10 and len(set(tops)) == 1, tops                   # כל הלשוניות, בשורה אחת
    page.click("#dvzModeSimpleBtn")                                        # ב"פשוט" - רק ההגדרות
    assert page.evaluate("() => [...document.querySelectorAll('#dvzEditorTabs button')].filter(b => b.offsetParent).length") == 1
    page.click("#dvzModeRegularBtn")
    assert page.is_visible("#dvzRunBtn")                                   # הרץ לא נדחף למטה
    page.click(".dvz-episodes-toggle")
    assert page.is_visible(".dvz-card[data-episode=alarms]") and page.get_attribute(".dvz-episodes-toggle", "aria-pressed") == "true"
    page.click(".dvz-episodes-toggle")
    assert not page.is_visible(".dvz-episodes-pane")
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
