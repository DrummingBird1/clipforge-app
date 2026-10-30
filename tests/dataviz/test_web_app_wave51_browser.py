# tests/dataviz/test_web_app_wave51_browser.py
#
# גל 51 בדפדפן: מראה מוכן מוחל כטיוטה (ומעבר למראה אחר מנקה את מה שהקודם שינה), הדמיית עיוורון צבעים על התצוגה החיה
# ובדיקת הפלטה, ותמונה לישות מלשונית הישויות (קובץ חדש מחוץ לתיקיית הפרק). config.yaml של הפרק לא משתנה.
# xdist-group: workspace
import hashlib
import io


import pytest
from PIL import Image

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
    return {"data": data, "config": config, "md5": hashlib.md5(config.read_bytes()).hexdigest()}


def _open_tab(page, tab):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    page.click(f"#dvzEditorTabs button[data-tab={tab}]")


def test_looks_and_color_vision_in_the_colors_tab(editor_page, screen):
    page = editor_page
    _open_tab(page, "colors")
    page.wait_for_selector(".dvz-looks button[data-look=minimal]")
    page.click(".dvz-looks button[data-look=minimal]")
    draft = page.evaluate("() => dvzEd.draft")
    assert draft["style.grid"] is False and draft["numbers.style"] == "compact"
    page.click(".dvz-looks button[data-look=bold]")
    draft = page.evaluate("() => dvzEd.draft")
    assert draft["theme"] == "dark" and "numbers.style" not in draft          # מה שהמינימלי שינה - יצא מהטיוטה
    # עיוורון צבעים: אדום וירוק כמעט זהים בדויטרנופיה; הפלטה של "בולט" נבדקת
    issues = page.evaluate("() => dvzVisionIssues(['#ff0000', '#00aa00', '#0000ff']).map(i => i.kind)")
    assert "deutan" in issues
    page.select_option("#dvzVisionSelect", "deutan")
    assert page.evaluate("() => document.getElementById('dvzPreviewImg').style.filter").startswith("url(")
    assert page.evaluate("() => !!document.querySelector('#dvzVisionDefs filter#dvzVision-deutan feColorMatrix')")
    page.select_option("#dvzVisionSelect", "")
    assert page.evaluate("() => document.getElementById('dvzPreviewImg').style.filter") == ""
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]


def test_an_entity_image_is_uploaded_from_the_entities_tab(editor_page, screen):
    page = editor_page
    _open_tab(page, "entities")
    page.wait_for_selector(".dvz-entity-image input[type=file]", state="attached")
    buffer = io.BytesIO()
    Image.new("RGBA", (32, 32), (10, 120, 200, 255)).save(buffer, "PNG")
    first = page.locator(".dvz-entity-table tbody tr").first
    entity = first.locator("td").first.inner_text()
    first.locator(".dvz-entity-image input[type=file]").set_input_files(files=[{"name": "flag.png", "mimeType": "image/png", "buffer": buffer.getvalue()}])
    page.wait_for_selector(".dvz-entity-table tbody tr >> nth=0 >> .dvz-entity-image img")
    folder = screen["data"] / "dataviz_overrides" / "alarms" / "images"
    assert [p.name.split("@")[0] for p in folder.iterdir()] == [entity]
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
