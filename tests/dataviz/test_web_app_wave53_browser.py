# tests/dataviz/test_web_app_wave53_browser.py
#
# גל 53 בדפדפן: ביטול וחזרה בטיוטה של העורך המלא (כפתורים ו-Ctrl+Z / Ctrl+Y), חיפוש הגדרה, סימנים על הסליידר,
# הנפשה (GIF במקום פריים) ברווח, ותגיות ותיקיות לפרקים ברשימה. config.yaml של הפרקים לא משתנה.
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
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO,
                                                         "story": {"chapters": [{"date": "2022-01-01", "title": "פרק שני"}]}}, name="alarms")
    write_episode(data / "dataviz_episodes", overrides={"title": "מכוניות", **VIDEO}, name="cars")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    config = data / "dataviz_episodes" / "alarms" / "config.yaml"
    return {"data": data, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click(".dvz-card[data-episode=alarms]")


def test_undo_redo_and_settings_search(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    assert page.is_disabled("#dvzUndoBtn") and page.is_disabled("#dvzRedoBtn")
    page.fill("#dvzF-intro-title", "כותרת ראשונה")
    page.evaluate("() => { dvzUndo.lastAt = 0; setDvzMode('advanced'); document.querySelector('[data-path=\"ranking.log_scale\"]').closest('details').open = true; }")
    page.check("#dvzF-ranking-log_scale")                    # (השינוי הבא נחשב צעד נפרד; קבוצת הדירוג סגורה כברירת מחדל)
    assert page.evaluate("() => dvzEd.draft['ranking.log_scale']") is True
    page.click("#dvzUndoBtn")
    assert page.evaluate("() => 'ranking.log_scale' in dvzEd.draft") is False
    assert page.evaluate("() => dvzEd.draft['intro.title']") == "כותרת ראשונה"
    page.click("#dvzRedoBtn")
    assert page.evaluate("() => dvzEd.draft['ranking.log_scale']") is True
    page.click("#dvzPreviewPane h3")                          # פוקוס מחוץ לשדות - Ctrl+Z של העורך
    page.keyboard.press("Control+z")
    page.keyboard.press("Control+z")
    assert page.evaluate("() => Object.keys(dvzEd.draft).length") == 0
    page.keyboard.press("Control+y")
    assert page.evaluate("() => dvzEd.draft['intro.title']") == "כותרת ראשונה"
    # חיפוש הגדרה
    page.fill("#dvzFieldSearch", "לוגריתמי")
    visible = page.eval_on_selector_all("#dvzEditorBody .dvz-field:not([hidden])", "els => els.map(e => e.dataset.path)")
    assert visible == ["ranking.log_scale"]
    page.fill("#dvzFieldSearch", "")
    assert page.evaluate("() => document.querySelectorAll('#dvzEditorBody .dvz-field[hidden]').length") == 0
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_markers_animation_and_keyboard_on_the_preview(editor_page, screen):
    page = editor_page
    _open(page)
    page.wait_for_selector("#dvzMarkers .dvz-marker.is-chapter")
    assert page.evaluate("() => document.querySelectorAll('#dvzMarkers .dvz-marker.is-event').length") == 2
    page.click("#dvzMarkers .dvz-marker.is-chapter")
    pos = float(page.get_attribute("#dvzMarkers .dvz-marker.is-chapter", "data-pos"))
    assert abs(int(page.input_value("#dvzPreviewPos")) - pos * 1000) <= 1
    page.click("#dvzPreviewPane h3")
    before = int(page.input_value("#dvzPreviewPos"))
    page.keyboard.press("ArrowLeft")                          # בעברית שמאלה = קדימה
    assert int(page.input_value("#dvzPreviewPos")) == min(1000, before + 10)
    with page.expect_response(lambda r: "/api/dataviz/preview_clip" in r.url) as info:
        page.keyboard.press(" ")
    # 27.10.2026: ההנפשה מבקשת וידאו (format=mp4); בלי ffmpeg שעובד השרת חוזר ל-GIF
    assert info.value.status == 200 and info.value.headers["content-type"] in ("video/mp4", "image/gif")
    assert page.get_attribute("#dvzAnimateBtn", "aria-pressed") == "true"
    page.click("#dvzAnimateBtn")
    assert page.get_attribute("#dvzAnimateBtn", "aria-pressed") == "false"


def test_tags_and_folders_in_the_episode_list(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click(".dvz-card-wrap:has(.dvz-card[data-episode=cars]) .dvz-tag-edit")
    page.fill(".dvz-tag-form input[aria-label='תגיות']", "רכב, #ישראל")
    page.fill(".dvz-tag-form input[aria-label='תיקייה']", "עונה 1")
    page.click(".dvz-tag-form button")
    page.wait_for_selector(".dvz-folder-head")
    heads = page.eval_on_selector_all(".dvz-folder-head", "els => els.map(e => e.textContent)")
    assert heads == ["📁 עונה 1", "📄 בלי תיקייה"]
    assert page.inner_text(".dvz-card[data-episode=cars] .dvz-card-badges").count("#") == 2
    saved = json.loads((screen["data"] / "dataviz_tags.json").read_text(encoding="utf-8"))
    assert saved["episodes"]["cars"] == {"tags": ["ישראל", "רכב"], "folder": "עונה 1"}
    page.fill("#dvzSearch", "#רכב")
    assert page.eval_on_selector_all(".dvz-card", "els => els.map(e => e.dataset.episode)") == ["cars"]
