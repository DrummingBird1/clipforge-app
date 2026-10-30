# tests/dataviz/test_web_app_dataviz_live_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "▶ הנפשה" היא התצוגה החיה - בקשת live=1 (חדה יותר, 12 פריימים לשנייה), ושינוי בטיוטה
# מבקש GIF חדש של אותו רגע אחרי שמפסיקים להקליד. window.fetch עטוף (service worker - page.route לא רואה את הבקשות).
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
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def test_the_animation_is_the_live_preview_and_follows_the_draft(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { window.__clips = []; const f = window.fetch; window.fetch = (u, o) => { if (String(u).includes('preview_clip')) window.__clips.push(String(u)); return f(u, o); }; }")
    page.click("#dvzAnimateBtn")
    page.wait_for_function("() => window.__clips.length >= 1", timeout=30000)
    assert "live=1" in page.evaluate("() => window.__clips[0]")
    page.wait_for_function("() => document.getElementById('dvzPreviewImg').src.startsWith('blob:')", timeout=30000)
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzF-title")
    page.fill("#dvzF-title", "כותרת חיה")
    page.wait_for_function("() => window.__clips.some(u => u.includes('live=1') && (new URL(u, location.href).searchParams.get('draft') || '').includes('כותרת חיה'))", timeout=30000)
