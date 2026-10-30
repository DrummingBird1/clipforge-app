# tests/studio/test_web_app_studio_project_templates_browser.py
#
# 24.10.2026, מנה 8 - החלטת המשתמש מסיור השימושיות בסטודיו: תיקייה חדשה בלי פרויקט שמור שואלת "להתחיל מ: הפרויקט הקודם /
# סגנון או תבנית / ברירת מחדל" (ברירת המחדל - מה שבטופס, כמו קודם). "📑 שמור את הפרויקט כתבנית" בתפריט ⋯, והתבניות בבורר
# הסגנונות וב"📋 כל הפרויקטים". ובהערת המפנה ל-#72: גובה שגררו לציר הזמן גובר על 22vh, עד גבול שמשאיר לנגן מקום (89-studio-more.js).
# xdist-group: workspace
import pytest

from tests.web.test_web_app_wave27_browser import _make_clip, _set_folder, _studio, needs_ffmpeg

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
BAR = "#veStartFromBar:not([hidden])"
SAVE = """async ([name, settings, kind]) => { await fetch('/api/video_editor_profiles', {method: 'POST', headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({name, settings, kind})}); await loadVideoEditorProfiles(); }"""
DELETE = "async (names) => { for (const n of names) await fetch('/api/video_editor_profiles/' + encodeURIComponent(n), {method: 'DELETE'}); }"
PRESET = "() => document.getElementById('vePreset').value"


def _open(page):
    _studio(page)
    page.wait_for_function(LOADED)


def test_a_new_folder_asks_where_to_start_from(editor_page, tmp_path):
    page = editor_page
    for name in ("a", "b", "c", "d", "saved"):
        (tmp_path / name).mkdir()
    _open(page)
    try:
        page.evaluate(SAVE, ["T8 style", {"codec": "h264"}, None])
        page.evaluate(SAVE, ["T8 template", {"codec": "hevc"}, "template"])
        _set_folder(page, tmp_path / "a")
        page.wait_for_selector(BAR)                                                     # קודם: אין שאלה
        labels = page.evaluate("() => [...document.getElementById('veStartFromStyle').options].map(o => o.textContent)")
        assert labels.index("📑 T8 template") < labels.index("T8 style")               # התבניות קודם
        page.select_option("#veStartFromStyle", "T8 template")
        page.wait_for_selector("#veStartFromBar", state="hidden")
        assert page.evaluate(PRESET) == "profile:T8 template" and page.input_value("#veCodec") == "hevc"

        _set_folder(page, tmp_path / "b")
        page.wait_for_selector(BAR)
        page.click("#veStartFromBar button:has-text('ברירת מחדל')")
        page.wait_for_selector("#veStartFromBar", state="hidden")
        assert page.evaluate(PRESET) == "" and page.input_value("#veCodec") != "hevc"   # בלי אישור נוסף - זו הבחירה עצמה

        page.select_option("#veCodec", "hevc")
        _set_folder(page, tmp_path / "c")
        page.wait_for_selector(BAR)
        page.click("#veStartFromBar button:has-text('הפרויקט הקודם')")
        page.wait_for_selector("#veStartFromBar", state="hidden")
        assert page.input_value("#veCodec") == "hevc"                                     # מה שבטופס - כמו קודם

        saved = str(tmp_path / "saved")
        page.evaluate("async (f) => fetch('/api/editor_projects', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({folder: f, recipe: {codec: 'hevc'}})})", saved)
        _set_folder(page, tmp_path / "d")
        page.wait_for_selector(BAR)
        _set_folder(page, saved)
        page.wait_for_function("(f) => _veProjectLoadedFor === f && _veProjectSaveInfo.state === 'saved'", arg=saved)
        page.wait_for_selector("#veStartFromBar", state="hidden")                         # לתיקייה עם פרויקט שמור - אין שאלה
    finally:
        page.evaluate(DELETE, ["T8 style", "T8 template"])


def test_save_the_project_as_a_template_from_the_menu(editor_page):
    page = editor_page
    _open(page)
    try:
        page.evaluate("() => { vePrompt = async () => 'T8 menu'; }")
        page.click("#veViewMenuBtn")
        page.click("#veViewMenu button:has-text('שמור את הפרויקט כתבנית')")              # קודם: אין כזה
        page.wait_for_function("() => (state.videoEditorProfileMeta['T8 menu'] || {}).kind === 'template'")
        assert page.evaluate("() => document.querySelector('#vePreset option[value=\"profile:T8 menu\"]').textContent").startswith("📑 ")
        settings = page.evaluate("async () => (await (await fetch('/api/video_editor_profiles')).json())['T8 menu']")
        assert {"layers", "targets", "brand_kit"} <= set(settings) and settings["queue_files"] is None

        page.evaluate("() => openVeJobs()")
        page.wait_for_selector("#veJobsTemplates:not([hidden]) :text('T8 menu')")          # ב"📋 כל הפרויקטים"
        page.click("#veJobsTemplates button:has-text('החל על הפרויקט')")
        page.wait_for_selector("#veJobsView", state="hidden")
        assert page.evaluate(PRESET) == "profile:T8 menu"
    finally:
        page.evaluate(DELETE, ["T8 menu"])


@needs_ffmpeg
def test_a_dragged_timeline_height_wins_over_22vh_and_leaves_the_player_room(editor_page, tmp_path):
    page = editor_page
    page.set_viewport_size({"width": 1440, "height": 1200})
    _make_clip(tmp_path / "clip.mp4")
    _open(page)
    page.evaluate("() => { setVeMode('advanced'); setVeLayout('tabs'); _veActivateTab('time'); }")
    _set_folder(page, tmp_path)
    page.wait_for_function("() => _veInLiveMode() && document.getElementById('veLiveVideo').readyState >= 2", timeout=20000)
    assert page.evaluate("() => document.getElementById('veTimelineDock').style.maxHeight") == ""   # בלי גרירה - 22vh, כמו קודם
    page.evaluate("() => { document.getElementById('veViewer').scrollTop = 0; document.getElementById('veTimelineDock').style.setProperty('--ve-tl-h', '220px'); }")
    page.wait_for_function("() => document.getElementById('veTimelineDock').offsetHeight > innerHeight * 0.22 + 8", timeout=10000)   # קודם: עד 22vh
    page.wait_for_function("""() => { const viewer = document.getElementById('veViewer').getBoundingClientRect();
      const dock = document.getElementById('veTimelineDock').getBoundingClientRect();
      return document.getElementById('veLive').offsetHeight >= 150 && dock.bottom <= viewer.bottom + 1; }""", timeout=10000)
