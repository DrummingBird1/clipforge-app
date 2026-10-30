# tests/dataviz/test_web_app_dataviz_smart_browser.py
#
# עורך הגרפים בדפדפן (20.10.2026): "📂→🎬 מתיקייה" - תיקיית נתונים -> פרק עם טיוטה; פאנל "🤖 הבחירות האוטומטיות" עם
# סיבה וביטחון, ביטול של בחירה אחת, והסימון 🤖 ב"ההגדרות הסופיות".
# xdist-group: workspace
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
    write_episode(data / "dataviz_episodes", overrides={"title": "קיים"}, name="alarms")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    source = tmp_path / "medals"
    source.mkdir()
    lines = ["year,country,total_medals"]
    for year in range(1980, 1996):
        lines += [f"{year},צרפת,20", f"{year},יפן,{5 + (60 if year >= 1988 else 0)}", f"{year},איטליה,8", f"{year},קנדה,3"]
    (source / "medals_per_games.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"data": data, "source": source}


def test_folder_to_draft_and_the_robot_marks(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzNewBtn")   # 21.10.2026: "➕ פרק חדש" -> "📂 מתיקייה" (ברירת המחדל)
    page.fill("#dvzSmartPath", str(screen["source"]))
    page.click("#dvzNewDialog .dvz-new-more summary")   # השם וערכת הערוץ - מקופלים
    page.fill("#dvzSmartName", "medals_auto")
    page.click("#dvzSmartGoBtn")
    page.wait_for_selector("#dvzSmartPanel[open] #dvzSmartChoices .dvz-review-card[data-path='title']", timeout=60000)
    assert page.is_visible("#dvzSmartChoices .dvz-review-card[data-path='chart'] >> text=✓ מאשר")   # 21.10.2026: מסך הסקירה
    assert page.evaluate("() => dvzState.selected") == "medals_auto"
    page.click("#dvzSmartChoices .dvz-review-card[data-path='title'] >> text=בטל")
    page.wait_for_function("() => document.querySelector(\"#dvzSmartChoices .dvz-review-card[data-path='title']\").textContent.includes('בוטל')")
    saved = json.loads((screen["data"] / "dataviz_overrides" / "medals_auto.json").read_text(encoding="utf-8"))
    assert "title" not in saved and saved["chart"] == "bar_race"
    # 21.10.2026: "✓ מאשר" רק מסמן; "✏️ שנה" סוגר את הסקירה ופותח את העורך על השדה
    page.click("#dvzSmartChoices .dvz-review-card[data-path='chart'] >> text=✓ מאשר")
    page.wait_for_selector("#dvzSmartChoices .dvz-review-card.is-ok[data-path='chart']")
    record = json.loads((screen["data"] / "dataviz_smart" / "medals_auto.json").read_text(encoding="utf-8"))
    assert next(c for c in record["choices"] if c["path"] == "chart")["accepted"]
    page.click("#dvzSmartChoices .dvz-review-card[data-path='chart'] >> text=שנה")
    page.wait_for_selector("#dvzEditorBody .dvz-field-focus[data-path='chart']")
    assert not page.evaluate("() => document.getElementById('dvzSmartPanel').open")
    page.evaluate("() => dvzShowFinalConfig()")
    page.wait_for_selector("#dvzFinalBody tr[data-auto='1']")
    assert page.locator("#dvzFinalBody tr[data-auto='1']").count() >= 3
    # 21.10.2026: תיקייה -> סקירה -> רינדור: "▶ לרינדור" פותח את "✅ לפני רינדור" (הנתונים, העובדות והקריאות ברשימה אחת)
    page.click("#dvzFinalDialog >> text=✕ סגור")
    page.evaluate("() => dvzOpenSmartPanel()")
    page.click("#dvzSmartToRun")
    page.wait_for_selector("#dvzPrerender[open] #dvzPreRunBtn")
    page.wait_for_function("() => /^[✓⚠]/.test(document.getElementById('dvzPreSummary').textContent)", timeout=60000)
    assert page.locator("#dvzPreData .dvz-finding").count() >= 1 and page.locator("#dvzPreFacts > .dvz-finding").count() == 1


def test_watch_settings_and_preferences(editor_page, screen, tmp_path):
    root = tmp_path / "graphs"
    (root / "existing").mkdir(parents=True)
    (root / "existing" / "a.csv").write_text("year,v\n2000,1\n", encoding="utf-8")
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzToolsBtn")   # 21.10.2026: ב"🧰 כלים" - "⚙️ הגדרות עורך הגרפים"
    page.click("#dvzToolSettings")
    page.wait_for_function("() => document.getElementById('dvzPrefs').textContent.length > 0")
    page.check("#dvzWatchOn")
    page.fill("#dvzWatchRoot", str(root))
    page.click("#dvzWatchSaveBtn")
    page.wait_for_function("() => document.getElementById('dvzSmartSettingsMsg').textContent.includes('1')")
    saved = json.loads((screen["data"] / "dataviz_smart" / "watch.json").read_text(encoding="utf-8"))
    assert saved["enabled"] and saved["seen"] == ["existing"]
