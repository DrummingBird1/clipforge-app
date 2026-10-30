# tests/test_web_app_dataviz_import_browser.py
#
# עורך הגרפים בדפדפן (19.10.2026): "📂 ייבא תיקייה" (21.10.2026: "➕ פרק חדש" -> "📂 מתיקייה" עם config.yaml) - בחירת תיקיית פרק מוכנה (גם דרך חלון הדפדוף של האפליקציה), העתקה
# לפרקים של האפליקציה והפרק נבחר מיד. תיקיית המקור לא משתנה.
# xdist-group: workspace
import hashlib
import os
import shutil


import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}


def _tree(root):
    return sorted((os.path.relpath(os.path.join(d, f), root), hashlib.md5(open(os.path.join(d, f), "rb").read()).hexdigest())
                  for d, _dirs, files in os.walk(root) for f in files)


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", overrides={"title": "אזעקות לדוגמה", **VIDEO}, name="alarms")
    source = write_episode(tmp_path / "Graphs", overrides={"title": "פרק מוכן מבחוץ", **VIDEO}, name="ready_one")
    write_episode(workspace / "dataviz" / "staging", overrides={"title": "טיוטה מוכנה", **VIDEO}, name="staged_one")   # 19.10.2026
    with open(os.path.join(source, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("# מקורות\n")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("CLIPFORGE_WORKSPACE_DIR", str(workspace))
    return {"source": source, "episodes": data / "dataviz_episodes"}


def test_import_a_ready_folder_from_the_browser(editor_page, screen):
    page = editor_page
    before = _tree(screen["source"])
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzNewBtn")
    assert page.evaluate("() => document.getElementById('dvzNewDialog').open")
    # בחירה בחלון הדפדוף של האפליקציה: החלון שלנו נסגר, ונפתח שוב עם התיקייה שנבחרה
    page.fill("#dvzSmartPath", os.path.dirname(screen["source"]))
    page.click("#dvzNewDialog >> text=📁 בחר")
    page.wait_for_selector("#modalBg.show")
    assert not page.evaluate("() => document.getElementById('dvzNewDialog').open")
    page.evaluate(f"async () => {{ await browseTo({screen['source']!r}); chooseCurrentFolder(); }}")
    page.wait_for_function("() => document.getElementById('dvzNewDialog').open")
    assert page.input_value("#dvzSmartPath").replace("\\", "/").rstrip("/") == screen["source"].replace("\\", "/")
    assert page.is_hidden("#modalBg") and page.evaluate("() => state.browseTarget") == "folder"
    page.click("#dvzSmartGoBtn")
    page.wait_for_function("() => !document.getElementById('dvzNewDialog').open")
    page.wait_for_selector('.dvz-card[data-episode="ready_one"]')
    assert page.evaluate("() => dvzState.selected") == "ready_one"
    assert _tree(screen["episodes"] / "ready_one") == before and _tree(screen["source"]) == before
    # שוב - אותו שם קיים: הודעה, בלי לדרוס
    page.click("#dvzNewBtn")
    page.fill("#dvzSmartPath", screen["source"])
    page.click("#dvzSmartGoBtn")
    page.wait_for_function("() => document.getElementById('dvzSmartMsg').textContent.includes('כבר קיים')")
    assert page.evaluate("() => [...document.getElementById('dvzImportRecent').options].map(o => o.value)")


def test_an_empty_list_is_one_big_button(editor_page, screen):
    # 21.10.2026 (סבב הפישוט): בלי פרקים - רק "➕ פרק חדש" גדול; הוא פותח את "📂 מתיקייה" עם הפרקים המוכנים
    shutil.rmtree(screen["episodes"] / "alarms")   # תיקייה זמנית של הטסט
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzNewBigBtn")
    assert page.is_hidden("#dvzNewBtn") and page.is_hidden("#dvzSearch")
    page.click("#dvzToolsBtn")   # "🧰 כלים" בסרגל העליון: כלי של פרק מושבת כשאין פרק, השאר פעילים
    assert page.is_disabled("#dvzToolHistory") and page.is_enabled("#dvzToolCatalog") and page.is_enabled("#dvzToolSettings")
    page.keyboard.press("Escape")
    page.click("#dvzNewBigBtn")
    page.wait_for_selector("#dvzImportReady button")
    assert page.is_visible("#dvzSmartPath") and page.is_checked("#dvzUseConfig")
    page.click("#dvzImportReady >> text=טיוטה מוכנה")
    page.click("#dvzSmartGoBtn")
    page.wait_for_selector('.dvz-card[data-episode="staged_one"]')
    assert page.is_visible("#dvzNewBtn") and not page.evaluate("() => document.getElementById('dvzSmartPanel')?.open")


def test_the_dialog_offers_the_ready_staging_folders(editor_page, screen):
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    page.click("#dvzNewBtn")
    page.wait_for_selector("#dvzImportReady button")
    page.click("#dvzImportReady >> text=טיוטה מוכנה")
    assert page.input_value("#dvzSmartPath").replace("\\", "/").endswith("dataviz/staging/staged_one")
    page.click("#dvzSmartGoBtn")
    page.wait_for_selector('.dvz-card[data-episode="staged_one"]')
    assert (screen["episodes"] / "staged_one" / "config.yaml").is_file()


def test_first_run_builds_an_example_step_by_step(editor_page, screen):
    # 21.10.2026 (סבב הפישוט): היכרות - לא ל-Playwright מעצמה (navigator.webdriver), אז כאן בכפייה. פרק לדוגמה מתיקיית
    # הטיוטה: מתיקייה (טיוטה חכמה) -> סקירה -> "✅ לפני רינדור", עם שורת הסבר בכל צעד; מוצגת פעם אחת
    page = editor_page
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")
    assert page.locator("#dvzOnboard").count() == 0 and page.evaluate("() => localStorage.getItem('dvzOnboardSeen')") is None
    page.evaluate("() => dvzMaybeOnboard(true)")
    page.click("#dvzOnboardStart")
    assert page.evaluate("() => localStorage.getItem('dvzOnboardSeen')") == "1"
    assert page.input_value("#dvzSmartPath").replace("\\", "/").endswith("dataviz/staging/staged_one") and not page.is_checked("#dvzUseConfig")
    assert "צעד 1 מתוך 3" in page.inner_text("#dvzNewDialog .dvz-onboard-hint")
    page.click("#dvzSmartGoBtn")
    page.wait_for_selector("#dvzSmartPanel[open] .dvz-onboard-hint", timeout=60000)
    assert "צעד 2 מתוך 3" in page.inner_text("#dvzSmartPanel .dvz-onboard-hint")
    page.click("#dvzSmartToRun")
    page.wait_for_selector("#dvzPrerender[open] .dvz-onboard-hint")
    assert "צעד 3 מתוך 3" in page.inner_text("#dvzPrerender .dvz-onboard-hint") and page.input_value("#dvzMode") == "preview"
    page.click("#dvzPrerender >> text=✕ סגור")
    page.click("#dvzOnboard >> text=דלג")
    assert page.locator("#dvzOnboard, .dvz-onboard-hint").count() == 0
    page.click("#dvzNewBtn")   # הדוגמה כיבתה את "config.yaml כמו שהוא" - בפתיחה הבאה הוא שוב ברירת המחדל
    assert page.is_checked("#dvzUseConfig")
