# tests/dataviz/test_web_app_wave43_browser.py
#
# גל 43 בדפדפן: בעורך הצבעים - בורר גופן (רשימת הגופנים מוחלפת, בלי סריקה) ובדיקת ניגודיות שמתעדכנת כשמשנים
# צבע, לפני שמירה; ובחלון הנתונים - עדכון נתונים מציע את כל המקורות. config.yaml של הפרק לא משתנה.
# xdist-group: workspace
import hashlib


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", "video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    from entrypoints.web.routes import dataviz as routes
    monkeypatch.setitem(routes._fonts_cache, "fonts", ["Arial", "Rubik"])
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _open_colors(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.click("#dvzEditorTabs button[data-tab=colors]")
    page.wait_for_selector("#dvzEditorBody .dvz-contrast")


def test_contrast_warnings_follow_the_colors_and_a_font_is_picked(editor_page, screen):
    page = editor_page
    _open_colors(page)
    page.wait_for_selector("#dvzEditorBody .dvz-contrast .dvz-check-ok")
    # רקע כמעט בצבע הטקסט - הטקסט והפלטה נעשים חלשים
    page.evaluate("""() => { const input = document.querySelector('#dvzEditorBody .dvz-color-row input[type=color]');
        input.value = '#2a2f36'; input.dispatchEvent(new Event('input', {bubbles: true})); }""")
    page.wait_for_selector("#dvzEditorBody .dvz-contrast .dvz-contrast-list li")
    assert "הטקסט" in page.inner_text("#dvzEditorBody .dvz-contrast")
    assert page.evaluate("() => Math.round(dvzContrast('#000000', '#ffffff'))") == 21
    page.wait_for_selector("#dvzEditorBody .dvz-font-row select option[value=Rubik]", state="attached")
    page.select_option("#dvzEditorBody .dvz-font-row select", "Rubik")
    assert page.evaluate("() => dvzEd.draft['theme_overrides.fonts']")[0] == "Rubik"
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_update_data_offers_every_source(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { dvzData.tab = 'update'; document.getElementById('dvzData').open = true; dvzLoadData(); }")
    page.wait_for_selector("#dvzUpdateSource option", state="attached")
    assert page.eval_on_selector_all("#dvzUpdateSource option", "els => els.map(e => e.value)") == ["0", "1"]
