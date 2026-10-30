# tests/dataviz/test_web_app_wave56_browser.py
#
# גל 56 בדפדפן: עורך הגרפים נפתח במסך מלא כמו הסטודיו (בלי הפס העליון וה-rail; ☰ מחזיר את ה-rail; מעבר מסך מבטל),
# הפרק שנבחר בסרגל העליון, "📊 לעורך הגרפים" מתפריט ⋯ של הסטודיו, ו"🎬 פתח בסטודיו" על סרטון מוכן - הסטודיו נפתח
# על תיקייה משלו והתוצר לא זז. config.yaml של הפרקים לא משתנה.
# xdist-group: workspace
import hashlib
import os


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
SHELL = """() => ({focus: document.body.classList.contains('dvz-focus'), studio: document.body.classList.contains('ve-focus'),
                   top: getComputedStyle(document.querySelector('body > header.topbar')).display,
                   rail: getComputedStyle(document.querySelector('body > .nav-rail')).display})"""


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    out = workspace / "dataviz" / "outputs" / "horizontal"
    out.mkdir(parents=True)
    (out / "alarms.mp4").write_bytes(b"not really a video")
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"workspace": workspace, "out": out, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_the_graph_editor_opens_full_screen_like_the_studio(editor_page, screen):
    page = editor_page
    _open(page)
    assert page.evaluate(SHELL) == {"focus": True, "studio": False, "top": "none", "rail": "none"}
    assert page.locator(".dvz-topbar").is_visible() and "אזעקות לדוגמה" in page.inner_text("#dvzTopbarEpisode")
    page.click("#dvzNavBtn")
    assert page.evaluate(SHELL)["rail"] == "flex" and page.get_attribute("#dvzNavBtn", "aria-expanded") == "true"
    page.locator('.nav-rail .tab-btn[data-tab="gallery"]').click()            # מעבר מסך - חזרה למסגרת הרגילה
    assert page.evaluate(SHELL) == {"focus": False, "studio": False, "top": "flex", "rail": "flex"}
    page.locator('.nav-rail .tab-btn[data-tab="dataviz"]').click()
    page.wait_for_function("() => document.body.classList.contains('dvz-focus')")
    assert page.evaluate(SHELL)["rail"] == "none"                             # ה-☰ נסגר במעבר
    page.click(".dvz-topbar >> text=✕ סגור")
    page.wait_for_function("() => !document.body.classList.contains('dvz-focus')")
    assert page.evaluate("() => document.querySelector('[data-tab-panel=\"dataviz\"]').hidden") is True
    # מהסטודיו: ⋯ -> "📊 לעורך הגרפים"
    page.evaluate("() => openStudio()")
    page.wait_for_function("() => document.body.classList.contains('ve-focus')")
    page.click("#veViewMenuBtn")
    page.click("#veViewMenu >> text=לעורך הגרפים")
    page.wait_for_function("() => document.body.classList.contains('dvz-focus') && !document.body.classList.contains('ve-focus')")
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_open_in_studio_gives_the_video_its_own_folder(editor_page, screen):
    page = editor_page
    _open(page)
    card = page.locator('.dvz-output[data-name="alarms.mp4"]')
    card.wait_for()
    card.locator("button.dvz-to-studio").click()
    folder = screen["workspace"] / "dataviz" / "studio_handoff" / "horizontal" / "alarms"
    page.wait_for_function("(f) => state.folder === f", arg=str(folder))
    assert page.evaluate(SHELL)["studio"] is True and page.evaluate(SHELL)["focus"] is False
    assert [f for f in os.listdir(folder) if f.endswith(".mp4")] == ["alarms.mp4"]
    assert (folder / "alarms.mp4").read_bytes() == b"not really a video"
    assert (screen["out"] / "alarms.mp4").read_bytes() == b"not really a video"   # התוצר לא זז
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
