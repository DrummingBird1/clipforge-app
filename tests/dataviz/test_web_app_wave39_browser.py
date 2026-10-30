# tests/dataviz/test_web_app_wave39_browser.py
#
# גל 39 בדפדפן: העורך המלא של עורך הגרפים - שדות בקבוצות עם ברירת מחדל / קובץ / שונה כאן, טיוטה
# שמוצגת בתצוגה החיה ונשמרת רק ב"שמור", אירועים בטבלה, צבע קבוע לישות, החרגת ישות, ו"מה שונה".
# config.yaml של הפרק לא משתנה אף פעם. פריימים בודדים בלבד (matplotlib), בלי ffmpeg.
# xdist-group: workspace
import hashlib
import json


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
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"data": data, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest(),
            "overrides": data / "dataviz_overrides" / "alarms.json"}


def _open_editor(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")


def _saved(screen):
    return json.loads(screen["overrides"].read_text(encoding="utf-8")) if screen["overrides"].exists() else {}


def test_fields_show_default_and_save_only_on_save(editor_page, screen):
    page = editor_page
    _open_editor(page)
    tabs = page.evaluate("() => [...document.querySelectorAll('#dvzEditorTabs button')].map(b => b.dataset.tab)")
    assert tabs == ["fields", "events", "story", "colors", "entities", "map", "voice", "music", "langs", "changes"]   # גל 50: סיפור; גל 55: שפות
    row = "#dvzEditorBody .dvz-field[data-path='intro.title']"
    assert "ברירת מחדל" in page.inner_text(f"{row} .dvz-field-meta")
    posts = []   # אבחון: אם הטיוטה נשמרת לפני "שמור" - מי שלח את הבקשה
    page.on("request", lambda r: posts.append(f"{r.method} {r.url.split('?')[0]} {(r.post_data or '')[:200]}") if r.method == "POST" else None)
    page.fill("#dvzF-intro-title", "פתיח חדש")
    page.wait_for_function("() => document.getElementById('dvzDraftCount').textContent.startsWith('1')")
    assert _saved(screen) == {}, posts   # טיוטה - עוד לא נשמר
    assert page.evaluate("() => document.getElementById('dvzPreviewPos').value") == "10"   # הפתיח - התצוגה קפצה אליו
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('נשמר')")
    assert _saved(screen) == {"intro": {"title": "פתיח חדש"}}
    page.wait_for_selector(f"{row}.is-changed")
    page.click(f"{row} button[aria-label^='חזרה']")
    page.click("#dvzDraftSave")
    page.wait_for_function("() => !document.querySelector(\"#dvzEditorBody .dvz-field[data-path='intro.title']\")?.classList.contains('is-changed')")
    assert _saved(screen) == {}
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_events_colors_entities_and_changes(editor_page, screen):
    page = editor_page
    _open_editor(page)
    page.click("#dvzEditorTabs button[data-tab=events]")
    page.wait_for_selector("#dvzEditorBody .dvz-ev-table")
    rows_before = page.evaluate("() => document.querySelectorAll('#dvzEditorBody .dvz-ev-table tr').length")
    page.click("#dvzEditorBody button:has-text('אירוע')")
    assert page.evaluate("() => document.querySelectorAll('#dvzEditorBody .dvz-ev-table tr').length") == rows_before + 1
    page.click("#dvzEditorTabs button[data-tab=entities]")
    first = page.evaluate("() => document.querySelector('#dvzEditorBody .dvz-entity-table tbody tr td').textContent")
    page.evaluate("() => document.querySelector('#dvzEditorBody .dvz-entity-table tbody input[type=checkbox]').click()")
    page.click("#dvzEditorTabs button[data-tab=colors]")
    page.evaluate("() => document.querySelector('#dvzEditorBody .dvz-entity-table button').click()")   # צבע קבוע לישות הראשונה
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('נשמר')", timeout=20000)
    saved = _saved(screen)
    assert len(saved["events"]) == rows_before + 1
    assert saved["entities"]["exclude"] == [first]
    assert len(saved["colors"]) == 1
    page.click("#dvzEditorTabs button[data-tab=changes]")
    paths = page.eval_on_selector_all("#dvzEditorBody .dvz-changes-table tbody tr td:first-child", "els => els.map(e => e.textContent)")
    assert {"events", "colors", "entities.exclude"} <= set(paths)
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
