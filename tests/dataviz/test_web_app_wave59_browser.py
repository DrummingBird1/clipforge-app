# tests/dataviz/test_web_app_wave59_browser.py
#
# גל 59 בדפדפן - סידור עורך הגרפים: "⭐ בסיסי" ראשון בעורך המלא (במקום הטופס הנפרד) עם "↩️ אפס הכל", פעולות הפרק בתפריט ⋯,
# "שינויים להרצה הזו" מקופל עם תקציר, כפתורי הכרטיס בריחוף, "➕ פרק חדש" שפותח חלון, ההסבר רק כשאין פרקים, ותאריך וזמן
# בסרטון מתחת לתצוגה החיה. config.yaml של הפרקים לא משתנה.
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


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_the_settings_column_starts_with_what_to_run(editor_page, screen):
    page = editor_page
    _open(page)
    assert page.is_hidden("#dvzIntroHint")                                    # יש פרקים - ההסבר בריחוף על הכותרת
    assert not page.evaluate("() => !!document.getElementById('dvzSettings')")  # הטופס הנפרד יצא
    # פעולות הפרק בתפריט ⋯
    assert page.is_hidden("#dvzEpisodeMenu")
    page.click("#dvzEpisodeMenuBtn")
    assert page.is_visible("#dvzEpisodeMenu button:has-text('שכפל פרק')") and page.is_visible("#dvzEpisodeMenu button:has-text('ערכת ערוץ')")
    page.keyboard.press("Escape")
    # שינויים להרצה הזו - מקופל, עם תקציר
    assert not page.evaluate("() => document.getElementById('dvzRunOverrides').open")
    assert "לפי הגדרות הפרק" in page.inner_text("#dvzRunOverridesSummary")
    page.click("#dvzRunOverrides > summary")
    page.select_option("#dvzChart", "pie_race")
    page.select_option("#dvzPublish", "off")
    summary = page.inner_text("#dvzRunOverridesSummary")
    assert "תרשים:" in summary and "עוגה" in summary and "בלי חבילת פרסום" in summary
    # תאריך וזמן בסרטון
    page.wait_for_function("() => document.getElementById('dvzPreviewInfo').textContent.includes('⏱')", timeout=30000)
    assert page.evaluate("() => document.getElementById('dvzPreviewInfo').title").startswith("פריים")


def test_card_tools_show_on_hover_and_new_episode_opens_a_dialog(editor_page, screen):
    page = editor_page
    _open(page)
    tools = '.dvz-card-wrap:has(.dvz-card[data-episode="alarms"]) .dvz-card-tools'
    page.mouse.move(5, 5)
    assert page.evaluate(f"() => getComputedStyle(document.querySelector('{tools}')).opacity") == "0"
    page.hover('.dvz-card[data-episode="alarms"]')
    page.wait_for_function(f"() => getComputedStyle(document.querySelector('{tools}')).opacity === '1'")
    assert page.is_visible(f"{tools} [data-hide-for=alarms]") and page.is_visible(f"{tools} .dvz-queue-pick")
    page.click("#dvzNewBtn")
    assert page.evaluate("() => document.getElementById('dvzNewDialog').open") and page.is_visible("#dvzSmartPath")   # 21.10.2026: מתיקייה קודם
    page.click("#dvzNewDialog [data-new-way=files]")   # 21.10.2026: "➕ פרק חדש" -> "📄 מקבצים"
    assert page.is_visible("#dvzNewCsv")
    page.click("#dvzNewDialog >> text=✕ סגור")
    assert not page.evaluate("() => document.getElementById('dvzNewDialog').open")


def test_basics_come_first_in_the_full_editor_and_reset_all(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzEditorBody .dvz-group")
    first = page.evaluate("() => [...document.querySelectorAll('#dvzEditorBody .dvz-group')].slice(0, 2).map(g => [g.open, g.querySelector('summary').textContent])")
    assert first[0][0] and "בסיסי" in first[0][1] and first[1][0]           # "בסיסי" ו"טקסטים" פתוחות
    assert page.input_value("#dvzF-title") == "אזעקות לדוגמה"
    original = page.input_value("#dvzF-subtitle")
    page.fill("#dvzF-subtitle", "תת-כותרת חדשה")
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('נשמר')")
    page.evaluate("() => { window.veConfirm = async () => true; }")
    page.click("#dvzResetAllBtn")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('אופסו')")
    assert page.input_value("#dvzF-subtitle") == original                  # חזרה לערך מהקובץ של הפרק
    assert hashlib.md5(screen["config"].read_bytes()).hexdigest() == screen["md5"]
