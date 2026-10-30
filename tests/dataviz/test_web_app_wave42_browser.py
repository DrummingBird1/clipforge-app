# tests/dataviz/test_web_app_wave42_browser.py
#
# גל 42 בדפדפן: מדריך המנוע (כל סוגי התרשים כולל המפה, מצב "שיתוף", ההגדרות החדשות, חיפוש והקולות),
# מצב "תמונה ו-GIF לשיתוף" ברשימת ההרצה עם אומדן, המפה ברשימות סוגי התרשים (ולא בהשוואת התרשימים של
# פרק בלי קובץ מפה), והורדת כתוביות SRT בלי לרנדר. רשימת הקולות מוחלפת (בלי PowerShell בטסט).
# xdist-group: workspace


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
    from dataviz import narration
    from entrypoints.web.routes import dataviz as routes
    routes._voices_cache.clear()
    monkeypatch.setattr(narration, "list_voices", lambda: [{"name": "Microsoft Asaf", "culture": "he-IL", "gender": "Male"}])
    yield {"data": data}
    routes._voices_cache.clear()


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_the_engine_guide_lists_everything_and_searches(editor_page, screen):
    page = editor_page
    _open(page)
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolHelp")
    page.wait_for_selector("#dvzHelp-charts dt")
    codes = page.eval_on_selector_all("#dvzHelp-charts dt code", "els => els.map(e => e.textContent)")
    assert "map_race" in codes and "bar_race" in codes
    assert page.is_visible("#dvzHelp-group-captions") and page.is_visible("#dvzHelp-cli")
    page.wait_for_selector("#dvzHelp-voices >> text=Microsoft Asaf")
    page.fill("#dvzHelpSearch", "geojson")
    page.wait_for_function("() => !document.getElementById('dvzHelp-cli')")
    assert page.is_visible("#dvzHelp-group-map")
    page.fill("#dvzHelpSearch", "zzzz-לא-קיים")
    page.wait_for_selector("#dvzHelpBody .empty-msg")
    page.evaluate("() => dvzCloseHelp()")
    assert page.is_hidden("#dvzHelpBg")


def test_share_mode_map_chart_and_captions_download(editor_page, screen):
    page = editor_page
    _open(page)
    page.click('.dvz-card[data-episode="alarms"]')
    page.select_option("#dvzMode", "share")
    page.wait_for_function("() => document.getElementById('dvzModeHint').textContent.includes('GIF')")
    assert "map_race" in page.eval_on_selector_all("#dvzChartFilter option", "els => els.map(e => e.value)")
    assert "map_race" in page.eval_on_selector_all("#dvzChart option", "els => els.map(e => e.value)")
    assert "map_race" not in page.eval_on_selector_all("#dvzNewChart option", "els => els.map(e => e.value)")
    page.evaluate("() => dvzCompare('charts')")
    page.wait_for_selector("#dvzCompareBox figure")
    labels = page.eval_on_selector_all("#dvzCompareBox figure", "els => els.map(e => e.textContent)")
    assert labels and not any("מפה" in text for text in labels)      # לפרק אין קובץ מפה
    with page.expect_download() as info:
        page.click("#dvzCaptionsBtn")
    download = info.value
    assert download.suggested_filename == "alarms.srt"
    text = open(download.path(), encoding="utf-8").read()
    assert text.startswith("1\n") and "-->" in text
    page.wait_for_selector("#toastHost .toast[data-tone=ok] >> text=כתוביות")
