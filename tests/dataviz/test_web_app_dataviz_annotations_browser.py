# tests/dataviz/test_web_app_dataviz_annotations_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "📌 הערה" ליד התצוגה - לחיצה על הגרף פותחת שורה עם התאריך והערך של הנקודה, "➕ הוסף"
# שם הערה בטיוטה (story.annotations), וגרירה של הערה קיימת מזיזה אותה. הצירים מגיעים מהשרת (X-Frame-Axes).
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
    write_episode(data / "dataviz_episodes", overrides={"title": "קווים", "chart": "line_race", **VIDEO}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))


def _pixel(page, fx, fy):
    """נקודה בתמונה לפי חלקים (0-1) מתוך אזור הנתונים שהשרת דיווח."""
    return page.evaluate("""([fx, fy]) => { const a = dvzState.previewAxes, r = document.getElementById('dvzPreviewImg').getBoundingClientRect();
        const x = a.box[0] + fx * (a.box[2] - a.box[0]), y = a.box[1] + fy * (a.box[3] - a.box[1]);
        return [r.left + x * r.width, r.top + (1 - y) * r.height]; }""", [fx, fy])


def test_click_adds_a_note_and_drag_moves_it(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.wait_for_function("() => dvzState.previewAxes && dvzState.previewAxes.box", timeout=30000)
    page.click("#dvzAnnotateBtn")
    assert page.get_attribute("#dvzAnnotateBtn", "aria-pressed") == "true"
    x, y = _pixel(page, 0.5, 0.5)
    page.mouse.click(x, y)
    page.wait_for_selector("#dvzAnnotateForm:not([hidden])")
    page.fill("#dvzAnnotateText", "כאן קרה משהו")
    page.click("#dvzAnnotateForm >> text=➕ הוסף הערה")
    page.wait_for_function("() => (dvzEd.draft['story.annotations'] || []).length === 1")
    note = page.evaluate("() => dvzEd.draft['story.annotations'][0]")
    assert note["text"] == "כאן קרה משהו" and note["date"] and isinstance(note["value"], (int, float))
    page.wait_for_function("() => dvzState.previewAxes", timeout=30000)
    # גרירה: מהנקודה של ההערה ימינה
    start = page.evaluate("() => { const p = _dvzAnnotationPixel(dvzEd.draft['story.annotations'][0]); return [p.x, p.y]; }")
    page.mouse.move(*start)
    page.mouse.down()
    x2, _y2 = _pixel(page, 0.8, 0.5)
    page.mouse.move(x2, start[1], steps=5)
    page.mouse.up()
    moved = page.evaluate("() => dvzEd.draft['story.annotations'][0]")
    assert moved["date"] > note["date"] and len(page.evaluate("() => dvzEd.draft['story.annotations']")) == 1
