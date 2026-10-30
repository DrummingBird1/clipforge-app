# tests/dataviz/test_web_app_dataviz_batch_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "🖼 דוח תמונות" - דוח לכל הפרקים באפליקציה, קישור לדף הדוח, ו"🎬 רינדור מלא" רק
# אחרי אישור (חלון האישור מעל ה-dialog), דרך התור (כאן הריצה עצמה מוחלפת - בלי רינדור אמיתי).
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "דוח", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    calls = []
    monkeypatch.setattr(web_app, "_start_script_run", lambda script, folder, payload, host: calls.append(payload) or {"ok": True})
    return calls


def test_report_for_all_episodes_and_full_render_needs_a_confirmation(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolBatch")
    page.wait_for_selector("#dvzBatchSource option[value='app:']", state="attached")
    page.select_option("#dvzBatchSource", "app:")
    page.click("#dvzBatchStartBtn")
    page.wait_for_selector("#dvzBatchReportLink", timeout=90000)
    assert page.get_attribute("#dvzBatchReportLink", "href").endswith("/index.html")
    assert "1 תקינים" in page.inner_text("#dvzBatchResult")
    page.click("#dvzBatchFullBtn")
    page.wait_for_selector("#veConfirmModalBg.show")
    page.click("#veConfirmCancelBtn")
    assert screen == []                                                                  # בוטל - כלום
    page.click("#dvzBatchFullBtn")
    page.click("#veConfirmOkBtn")
    page.wait_for_function("() => document.getElementById('dvzBatchMsg').textContent.length > 0")
    assert screen[0]["dv_episodes"] == ["alarms"] and screen[0]["dv_mode"] == "full"
