# tests/dataviz/test_web_app_wave55_browser.py
#
# גל 55 בדפדפן: לשונית "🌍 שפות" (הגרסה באנגלית נשמרת בקובץ השינויים), בחירת שפה ליד "הרץ" רק לפרק שיש לו תרגום,
# מצב "Shorts אוטומטיים" ברשימת המצבים, ולוח הצפיות (ריק - בלי יוטיוב). config.yaml של הפרקים לא משתנה.
# xdist-group: workspace
import hashlib
import json


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
    write_episode(data / "dataviz_episodes", overrides={"title": "מכוניות", **VIDEO, "translations": {"en": {"title": "Cars"}}}, name="cars")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"data": data, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _open(page, episode):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click(f".dvz-card[data-episode={episode}]")


def test_the_languages_tab_saves_the_english_version(editor_page, screen):
    page = editor_page
    _open(page, "alarms")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.click("#dvzEditorTabs button[data-tab=langs]")
    page.wait_for_selector(".dvz-langs .dvz-lang-grid")
    page.fill(".dvz-lang-row input[data-path='title']", "Alarms example")
    page.fill(".dvz-lang-row input[data-path='intro.question']", "Who wins?")
    page.locator(".dvz-lang-table input").first.fill("The big event")
    draft = page.evaluate("() => dvzEd.draft['translations.en']")
    assert draft["title"] == "Alarms example" and draft["intro"]["question"] == "Who wins?" and list(draft["events"].values()) == ["The big event"]
    page.click("#dvzDraftSave")
    page.wait_for_function("() => !Object.keys(dvzEd.draft).length && dvzEd.data && dvzEd.data.translations.en")
    over = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert over["translations"]["en"]["title"] == "Alarms example"
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_language_choice_shorts_mode_and_the_views_board(editor_page, screen):
    page = editor_page
    _open(page, "alarms")
    assert page.evaluate("() => document.querySelector('.dvz-run-lang').hidden") is True        # בלי תרגום
    assert "shorts" in page.eval_on_selector_all("#dvzMode option", "els => els.map(e => e.value)")
    page.click(".dvz-card[data-episode=cars]")
    page.wait_for_function("() => !document.querySelector('.dvz-run-lang').hidden")
    page.evaluate("() => document.getElementById('dvzRunOverrides').open = true")   # גל 59: מקופל ל"שינויים להרצה הזו"
    page.select_option("#dvzRunLang", "both")
    assert page.evaluate("() => _dvzRunOptions().lang") == "both"
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים"
    page.click("#dvzToolBoard")
    page.wait_for_selector("#dvzBoard[open] .empty-msg")
    page.click("#dvzBoard >> text=סגור")
    assert page.evaluate("() => document.getElementById('dvzBoard').open") is False
