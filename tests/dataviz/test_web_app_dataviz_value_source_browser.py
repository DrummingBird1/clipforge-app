# tests/test_web_app_dataviz_value_source_browser.py
#
# עורך הגרפים בדפדפן (19.10.2026): "מאיפה הערך" - שבב אחד בראש כל שדה שאומר מי קובע (config.yaml / שונה בדפדפן /
# ברירת מחדל / טיוטה), ו"📜 ההגדרות הסופיות" - מה שהרינדור יקבל בפועל, לכל הגדרה המקור שלה. config.yaml לא משתנה.
# xdist-group: workspace
import hashlib


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
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _source(page, path):
    return page.inner_text(f"#dvzEditorBody .dvz-field[data-path='{path}'] .dvz-src")


def test_each_field_says_where_its_value_comes_from_and_the_final_view_matches(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    assert _source(page, "title") == "📄 config.yaml"
    assert _source(page, "publish.title") == "⚙️ ברירת מחדל"
    page.fill("#dvzF-intro-title", "פתיח מהדפדפן")
    assert _source(page, "intro.title") == "📝 טיוטה - עוד לא נשמרה"
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('נשמר')")
    assert _source(page, "intro.title") == "✏️ שונה בדפדפן"
    assert page.evaluate("() => document.querySelectorAll('#dvzEditorBody .dvz-field .dvz-src').length") == \
        page.evaluate("() => document.querySelectorAll('#dvzEditorBody .dvz-field').length")
    # ההגדרות הסופיות
    page.click("#dvzFinalBtn")
    page.wait_for_selector("#dvzFinalBody tbody tr")
    rows = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#dvzFinalBody tbody tr')]"
                         ".map(tr => [tr.cells[0].textContent, [tr.cells[1].textContent, tr.cells[2].textContent]]))")
    assert rows["intro.title"] == ["פתיח מהדפדפן", "✏️ שונה בדפדפן"]
    assert rows["title"] == ["אזעקות לדוגמה", "📄 config.yaml"]
    assert "publish.title" not in rows                                      # רק מה שלא ברירת מחדל
    page.uncheck("#dvzFinalChanged")
    assert page.evaluate("() => [...document.querySelectorAll('#dvzFinalBody tbody tr')].some(tr => tr.cells[0].textContent === 'publish.title' && tr.cells[2].textContent === '⚙️ ברירת מחדל')")
    page.click("#dvzFinalDialog >> text=✕ סגור")
    assert not page.evaluate("() => document.getElementById('dvzFinalDialog').open")
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
