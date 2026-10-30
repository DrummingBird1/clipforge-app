# tests/studio/test_web_app_studio_decisions_batch5_browser.py
#
# 24.10.2026, מנה 5 - החלטות המשתמש מסיור השימושיות בסטודיו (ממצאים 3, 2, 6 ו-9 חלקית):
# - באזהרה על השמע כפתור "🔊 הדלק" שמדליק את "שמירת אודיו" (ברירת המחדל לא משתנה), גם בגיליון "לפני הרצה";
# - "💾 שמור" נקרא "⭐ שמור כסגנון" (הוא שומר סגנון; הפרויקט נשמר לבד), ו-Ctrl+S כמו קודם;
# - "כל ההגדרות" במצב פשוט פותח את "רגיל" ולא את "מומחה";
# - הלוג בסטודיו לא נפתח לבד כשריצה מתחילה - לפי ההעדפה של המשתמש (מי שפתח אותו פעם - נשאר פתוח).
import pytest

from tests.web.test_web_app_wave27_browser import _settle, _studio

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

LOADED = "() => !!(window.__uiLazyLoaded && window.__uiLazyLoaded.studio_more)"
AUDIO_ON = "() => !!_collectRunOptions().keep_audio"
QUEUE_WITH_AUDIO = """() => { _veQueueState.push({name: 'a.mp4', selected: true}); _veQueueMeta[state.folder + '|a.mp4'] = {has_audio: true};
  _applyVideoEditorFields({keep_audio: false}); }"""
CLEAR_QUEUE = "() => { _veQueueState.length = 0; delete _veQueueMeta[state.folder + '|a.mp4']; _applyVideoEditorFields({keep_audio: false}); }"


def test_the_audio_warning_turns_audio_on_in_one_click(editor_page):
    page = editor_page
    _studio(page)
    page.wait_for_function(LOADED)
    page.evaluate(QUEUE_WITH_AUDIO)
    page.wait_for_selector("#veWarningsToggle:not([hidden])")
    page.click("#veWarningsToggle")
    page.click("#veWarningsBox button:has-text('הדלק')")                                  # קודם: אין כפתור
    page.wait_for_function(AUDIO_ON)
    page.wait_for_function("() => !document.getElementById('veWarningsBox').textContent.includes('שמירת אודיו')")

    page.evaluate("() => _applyVideoEditorFields({keep_audio: false})")                   # ובגיליון "לפני הרצה"
    page.evaluate("() => openVeRunSheet()")
    page.click("#veRunSheetWarnings button:has-text('הדלק')")
    page.wait_for_function(AUDIO_ON)
    assert "שמירת אודיו" not in page.inner_text("#veRunSheetWarnings")
    page.evaluate("() => closeVeRunSheet()")
    page.evaluate(CLEAR_QUEUE)


def test_save_says_it_saves_a_style_and_ctrl_s_still_works(editor_page):
    page = editor_page
    _studio(page)
    assert "שמור כסגנון" in page.inner_text("#veSaveBtn")                                 # קודם: "💾 שמור"
    assert "כסגנון" in page.get_attribute("#veSaveBtn", "title") and "Ctrl+S" in page.get_attribute("#veSaveBtn", "title")
    page.evaluate("""() => { window.__saved = 0; window.__real = [saveVideoEditorProfile, updateVideoEditorProfile];
      saveVideoEditorProfile = updateVideoEditorProfile = () => { window.__saved++; }; }""")
    page.keyboard.press("Control+s")                                                      # הקיצור לא השתנה
    page.wait_for_function("() => window.__saved === 1")
    page.evaluate("() => { [saveVideoEditorProfile, updateVideoEditorProfile] = window.__real; }")


def test_all_settings_from_simple_opens_regular(editor_page):
    page = editor_page
    _studio(page)
    page.evaluate("() => setVeMode('simple')")
    _settle(page)
    page.click("#veSteps .ve-steps-more")
    assert page.evaluate("() => _veCurrentMode()") == "regular"                           # קודם: "advanced"


def test_the_studio_log_stays_closed_when_a_run_starts(editor_page, editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    monkeypatch.setattr(web_app.worker, "is_running", False)
    monkeypatch.setattr(web_app.worker, "add_script_task", lambda *a, **k: None)
    (tmp_path / "a.mp4").write_bytes(b"x")
    page = editor_page
    page.evaluate("() => localStorage.removeItem('uiStudioConsoleOpen')")
    _studio(page)
    page.evaluate("(f) => { document.getElementById('folderInput').value = f; onFolderTyped(); }", str(tmp_path))
    page.wait_for_function("(f) => state.folder === f", arg=str(tmp_path))
    collapsed = "() => document.getElementById('consoleDrawer').classList.contains('collapsed')"
    assert page.evaluate(collapsed)
    page.evaluate("() => runScript()")
    page.wait_for_function("() => state.running")
    assert page.evaluate(collapsed)                                                       # קודם: נפתח לבד כשהריצה התחילה
    page.evaluate("() => _uiSyncShell()")
    assert page.evaluate(collapsed)                                                       # גם במעבר מסך בזמן ריצה
    page.evaluate("() => { state.running = false; toggleConsoleDrawer(false); state.running = true; _uiSyncShell(); }")
    assert not page.evaluate(collapsed)                                                   # מי שפתח - ההעדפה נשמרת
    page.evaluate("() => { state.running = false; localStorage.removeItem('uiStudioConsoleOpen'); }")
