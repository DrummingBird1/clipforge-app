# tests/dataviz/test_web_app_dataviz_export_folder_browser.py
#
# 23.10.2026, תיקיית הייצוא בעורך הגרפים: מעל התוצרים שורה "💾 נשמר ב-..." (לאן נכתבים תוצרים חדשים עכשיו), ואזהרה כשתיקיית
# הייצוא לא זמינה. "📂 פתח תיקייה" פותח את התיקייה שבה התוצר נמצא בפועל (תיקיית הייצוא או workspace), לא תמיד את הראשונה.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

# "פתח תיקייה" פותח את סייר הקבצים - בטסט רק רושמים לאן (עטיפה של window.fetch: ה-service worker עוקף את page.route)
_STUB_OPEN_FOLDER = """() => { window._opened = []; const real = window.fetch;
  window.fetch = (url, opts) => String(url).includes('/api/open_folder')
    ? (window._opened.push(JSON.parse(opts.body).path), Promise.resolve(new Response('{"ok": true}', {status: 200})))
    : real(url, opts); }"""


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace, exports = tmp_path / "data", tmp_path / "workspace", tmp_path / "exports"
    (data / "dataviz_episodes").mkdir(parents=True)
    write_episode(data / "dataviz_episodes", name="alpha")
    new = exports / "dataviz" / "outputs" / "horizontal"
    old = workspace / "dataviz" / "outputs" / "horizontal"
    new.mkdir(parents=True)
    old.mkdir(parents=True)
    (new / "alpha.mp4").write_bytes(b"new")
    (old / "alpha_test.mp4").write_bytes(b"old")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_EXPORT_DIR", str(exports))
    return {"exports": exports, "new": new, "old": old, "tmp": tmp_path}


def _open_screen(page):
    page.evaluate(_STUB_OPEN_FOLDER)
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzOutputs .dvz-output[data-name='alpha_test.mp4']")


def test_the_outputs_say_where_they_are_saved_and_open_their_own_folder(editor_page, screen):
    page = editor_page
    _open_screen(page)
    line = page.locator("#dvzSavedTo")
    assert line.is_visible()                                                    # קודם: לא היה
    assert line.inner_text() == f"💾 נשמר ב-{screen['exports'] / 'dataviz' / 'outputs'}"
    page.click("#dvzOutputs .dvz-output[data-name='alpha_test.mp4'] button:has-text('📂 פתח תיקייה')")
    page.click("#dvzOutputs .dvz-output[data-name='alpha.mp4'] button:has-text('📂 פתח תיקייה')")
    page.wait_for_function("() => window._opened.length === 2")
    assert page.evaluate("() => window._opened") == [str(screen["old"]), str(screen["new"])]   # קודם: פעמיים הראשונה


def test_an_unavailable_export_folder_shows_a_warning(editor_page, screen, monkeypatch):
    monkeypatch.setenv("CLIPFORGE_EXPORT_DIR", str(screen["tmp"] / "unplugged"))
    page = editor_page
    _open_screen(page)
    page.wait_for_selector("#dvzSavedTo .dvz-saved-problem")
    assert "תיקיית הייצוא לא זמינה עכשיו" in page.inner_text("#dvzSavedTo")
    assert "workspace" in page.inner_text("#dvzSavedTo span:first-child")
