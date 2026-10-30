# tests/dataviz/test_web_app_dataviz_browser_screen.py
#
# מסך "סרטוני נתונים" בדפדפן אמיתי (Edge): כפתור הניווט וקיצור דרך במסך הבית, רשימת פרקים, בקרות,
# הרצה אמיתית של preview דרך ה-worker (ffmpeg אמיתי) עם התקדמות ותוצר שמופיע ונטען, ויצירת פרק מ-CSV.
# data/ ו-workspace זמניים (web_app.DATA_DIR/WORKSPACE_DIR + CLIPFORGE_WORKSPACE_DIR לתהליך הסקריפט).
# xdist-group: workspace
import json
import os


import pytest

from tests.dataviz_helpers import write_episode
from tests.media_support import needs_ffmpeg

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

CSV = "date,city,n\n" + "".join(f"2020-0{m}-{d:02d},{city},{m * d}\n" for m in (1, 2, 3) for d in (1, 15) for city in ("A", "B"))


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
    return {"data": data, "workspace": workspace}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_nav_button_and_home_shortcut_open_the_screen(editor_page, screen):
    page = editor_page
    page.evaluate("() => closeVeEditor()")
    page.locator('.nav-rail .tab-btn[data-tab="dataviz"]').click()
    assert page.locator('[data-tab-panel="dataviz"]').is_visible()
    page.wait_for_selector(".dvz-card")
    page.evaluate("() => switchTab('scripts')")
    shortcut = page.locator(".home-action", has_text="סרטוני נתונים")
    assert shortcut.count() == 1
    shortcut.click()
    assert page.locator('[data-tab-panel="dataviz"]').is_visible()


def test_episode_card_shows_key_config_and_controls_are_complete(editor_page, screen):
    page = editor_page
    _open(page)
    card = page.locator('.dvz-card[data-episode="alarms"]')
    assert "אזעקות לדוגמה" in card.inner_text() and "מרוץ עמודות" in card.inner_text() and "640×360" in card.inner_text()
    assert card.get_attribute("aria-pressed") == "true"
    assert page.locator("#dvzControls").is_visible()
    values = lambda sel: page.eval_on_selector_all(f"{sel} option", "els => els.map(e => e.value)")  # noqa: E731
    assert values("#dvzMode") == ["preview", "stills", "test", "full", "share", "shorts"]   # גל 55: Shorts אוטומטיים
    assert values("#dvzChart") == ["", "bar_race", "line_race", "stacked_area_race", "scatter_race", "bump_race", "heatmap_race", "map_race",
                                   "pie_race", "small_multiples"]   # גל 51: עוגה; 20.10.2026: גרפים קטנים
    assert values("#dvzPublish") == ["default", "on", "off"]
    assert "5 שניות" in page.locator("#dvzModeHint").inner_text()
    page.select_option("#dvzMode", "full")
    assert "הסרטון המלא" in page.locator("#dvzModeHint").inner_text()
    assert page.locator("#dvzStopBtn").is_disabled() and page.locator("#dvzRunBtn").is_enabled()
    assert page.locator("#dvzOutputs").inner_text().startswith("אין עדיין תוצרים")


@needs_ffmpeg
def test_run_preview_renders_for_real_with_progress_and_shows_the_video(editor_page, screen):
    page = editor_page
    _open(page)
    page.select_option("#dvzMode", "preview")
    page.evaluate("() => document.getElementById('dvzRunOverrides').open = true")   # גל 59: מקופל ל"שינויים להרצה הזו"
    page.select_option("#dvzChart", "line_race")
    page.select_option("#dvzPublish", "off")
    page.locator("#dvzRunBtn").click()
    page.wait_for_function("() => document.getElementById('dvzRunBtn').disabled")
    page.wait_for_function("() => document.getElementById('dvzStatus').textContent.includes('הסתיים בהצלחה')", timeout=240000)

    video = screen["workspace"] / "dataviz" / "outputs" / "horizontal" / "alarms_preview.mp4"
    assert video.is_file() and video.stat().st_size > 1000
    assert not (screen["data"] / "dataviz_episodes" / "alarms" / "alarms_preview.mp4").exists()
    page.wait_for_selector('.dvz-output[data-kind="video"]')
    out = page.locator('.dvz-output[data-name="alarms_preview.mp4"]')
    assert "תצוגה מקדימה" in out.inner_text()
    assert page.locator("#dvzRunBtn").is_enabled() and page.locator("#dvzStopBtn").is_disabled()
    assert page.eval_on_selector("#dvzProgressBar", "e => e.style.width") == "100%"
    link = out.locator("a.dvz-link").get_attribute("href")
    assert page.evaluate("async (u) => { const r = await fetch(u); return [r.status, r.headers.get('content-disposition')]; }", link)[0] == 200
    page.wait_for_function("() => document.querySelector('.dvz-video').readyState >= 1", timeout=20000)
    history = page.evaluate("async () => JSON.stringify(await (await fetch('/api/history')).json())")
    assert "dataviz_maker.py" in history          # אותו נתיב ריצה של שאר הסקריפטים - מופיע בהיסטוריית הריצות
    page.screenshot(path=str(screen["workspace"] / "dataviz_screen.png"), full_page=True)


def test_stills_run_shows_thumbnails(editor_page, screen):
    page = editor_page
    _open(page)
    page.select_option("#dvzMode", "stills")
    page.locator("#dvzRunBtn").click()
    page.wait_for_function("() => document.getElementById('dvzStatus').textContent.includes('הסתיים')", timeout=240000)
    assert "בהצלחה" in page.locator("#dvzStatus").inner_text()
    page.wait_for_selector('.dvz-output[data-kind="stills"] img')
    page.wait_for_function("() => [...document.querySelectorAll('.dvz-stills img')].every(i => i.complete && i.naturalWidth > 0)")
    assert page.locator(".dvz-stills img").count() >= 1


def test_run_error_is_shown_and_the_button_recovers(editor_page, screen):
    page = editor_page
    _open(page)
    page.evaluate("() => { dvzState.selected = 'ghost'; }")
    page.locator("#dvzRunBtn").click()
    page.wait_for_function("() => document.getElementById('dvzStatus').textContent.includes('הפרק לא נמצא')")
    assert page.locator("#dvzRunBtn").is_enabled()


def test_publish_link_goes_to_the_approvals_screen(editor_page, screen):
    page = editor_page
    folder = screen["workspace"] / "dataviz" / "outputs" / "horizontal"
    folder.mkdir(parents=True)
    (folder / "alarms.mp4").write_bytes(b"video")
    (folder / "alarms.publish.json").write_text("{}", encoding="utf-8")
    _open(page)
    page.locator(".dvz-output button", has_text="חבילת פרסום ואישור").click()
    assert page.locator('[data-tab-panel="approvals"]').is_visible()


def test_create_episode_from_csv_then_refuses_the_same_name(editor_page, screen, tmp_path):
    page = editor_page
    _open(page)
    csv_path = tmp_path / "my data.csv"
    csv_path.write_text(CSV, encoding="utf-8")
    page.click("#dvzNewBtn")   # גל 59: הטופס בחלון
    page.click("#dvzNewDialog [data-new-way=files]")   # 21.10.2026: "➕ פרק חדש" -> "📄 מקבצים"
    page.set_input_files("#dvzNewCsv", str(csv_path))
    page.wait_for_function("() => document.getElementById('dvzNewTime').options.length === 3")
    assert page.input_value("#dvzNewName") == "my_data"
    page.fill("#dvzNewTitle", "ערים לדוגמה")
    page.select_option("#dvzNewValue", "n")
    page.select_option("#dvzNewGroup", "city")
    page.locator("#dvzCreateBtn").click()
    page.wait_for_selector('.dvz-card[data-episode="my_data"]')
    assert "ערים לדוגמה" in page.locator('.dvz-card[data-episode="my_data"]').inner_text()
    assert sorted(os.listdir(screen["data"] / "dataviz_episodes" / "my_data")) == ["config.yaml", "my_data.csv"]   # 19.10.2026: השם המקורי (נקי)
    before = (screen["data"] / "dataviz_episodes" / "my_data" / "config.yaml").read_bytes()

    page.click("#dvzNewBtn")   # החלון נסגר אחרי היצירה
    page.click("#dvzNewDialog [data-new-way=files]")   # 21.10.2026: "➕ פרק חדש" -> "📄 מקבצים"
    # 23.10.2026: הטופס מתאפס אחרי יצירה (קודם נשארו השם, הכותרת והקובץ) - אותו קובץ שוב, ואותו שם שהוא ממלא
    assert page.input_value("#dvzNewName") == "" and page.input_value("#dvzNewTitle") == ""
    page.set_input_files("#dvzNewCsv", str(csv_path))
    page.wait_for_function("() => document.getElementById('dvzNewName').value === 'my_data'")
    page.fill("#dvzNewTitle", "כותרת אחרת")
    page.select_option("#dvzNewValue", "n")
    page.select_option("#dvzNewGroup", "city")
    page.locator("#dvzCreateBtn").click()
    page.wait_for_function("() => document.getElementById('dvzNewMsg').textContent.includes('כבר קיים')")
    assert (screen["data"] / "dataviz_episodes" / "my_data" / "config.yaml").read_bytes() == before

def test_create_episode_from_several_files_maps_each_extra_file(editor_page, screen, tmp_path):
    # 18.10.2026: כמה קבצים בבחירה אחת - הראשון ממלא את הטופס כמו קודם, וכל קובץ נוסף מקבל מיפוי משלו
    page = editor_page
    _open(page)
    first, second = tmp_path / "cities.csv", tmp_path / "regions.csv"
    first.write_text(CSV, encoding="utf-8")
    second.write_text("year,region,total\n2019,C,365\n2020,C,366\n", encoding="utf-8")
    page.click("#dvzNewBtn")
    page.click("#dvzNewDialog [data-new-way=files]")   # 21.10.2026: "➕ פרק חדש" -> "📄 מקבצים"
    page.set_input_files("#dvzNewCsv", [str(first), str(second)])
    page.wait_for_selector("#dvzNewExtra .dvz-source select[data-field='group_column']")
    assert page.input_value("#dvzNewName") == "cities"
    assert "regions.csv" in page.locator("#dvzNewExtra").inner_text()
    page.fill("#dvzNewTitle", "שני קבצים")
    page.select_option("#dvzNewValue", "n")
    page.select_option("#dvzNewGroup", "city")
    extra = "#dvzNewExtra .dvz-source select[data-field='%s']"
    page.select_option(extra % "period", "year")
    page.select_option(extra % "value_column", "total")
    page.select_option(extra % "group_column", "region")
    page.fill("#dvzNewExtra .dvz-source input[data-field='legend']", "אזורים")
    page.locator("#dvzCreateBtn").click()
    page.wait_for_selector('.dvz-card[data-episode="cities"]')
    folder = screen["data"] / "dataviz_episodes" / "cities"
    assert sorted(os.listdir(folder)) == ["cities.csv", "config.yaml", "regions.csv"]   # 19.10.2026: השמות המקוריים
    import yaml
    sources = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))["sources"]
    assert sources[1] == {"path": "regions.csv", "time": {"column": "year", "period": "year"}, "value": {"column": "total"},
                          "entity": {"column": "region"}, "legend": "אזורים"}


def test_hide_an_episode_from_the_list_and_show_it_again(editor_page, screen):
    page = editor_page
    write_episode(screen["data"] / "dataviz_episodes", overrides={"title": "פרק שהסתיים"}, name="finished")
    _open(page)
    page.wait_for_selector('.dvz-card[data-episode="finished"]')
    before = sorted(str(p.relative_to(screen["data"])) for p in (screen["data"] / "dataviz_episodes").rglob("*"))

    page.locator('[data-hide-for="finished"]').click()
    page.wait_for_function("() => !document.querySelector('.dvz-card[data-episode=\"finished\"]')")
    page.wait_for_selector('.dvz-card[data-episode="alarms"]')       # הרשימה נטענת מחדש - מחכים שתתמלא
    assert page.locator('.dvz-card[data-episode="alarms"]').count() == 1
    assert "(1)" in page.locator("#dvzHiddenCount").inner_text()

    page.locator("#dvzShowHidden").check()
    page.wait_for_selector('.dvz-card-wrap.is-hidden .dvz-card[data-episode="finished"]')
    page.locator('[data-hide-for="finished"]').click()
    page.wait_for_selector('.dvz-card-wrap:not(.is-hidden) .dvz-card[data-episode="finished"]')
    assert page.locator('.dvz-card[data-episode="finished"]').count() == 1
    assert before == sorted(str(p.relative_to(screen["data"])) for p in (screen["data"] / "dataviz_episodes").rglob("*"))


def test_edit_episode_settings_in_the_browser_leaves_config_yaml_untouched_and_resets(editor_page, screen):
    page = editor_page
    config = screen["data"] / "dataviz_episodes" / "alarms" / "config.yaml"
    original = config.read_bytes()
    _open(page)
    page.wait_for_selector('.dvz-card[data-episode="alarms"]')
    page.locator('.dvz-card[data-episode="alarms"]').click()
    # גל 59: הטופס הנפרד יצא - אותם שדות ב"⭐ בסיסי" בראש העורך המלא, ו"↩️ אפס הכל" בסרגל שלו
    page.evaluate("() => { document.getElementById('dvzEditor').open = true; dvzLoadEditor(); }")
    page.wait_for_selector("#dvzF-title")
    page.fill("#dvzF-title", "כותרת ערוכה")
    page.select_option("#dvzF-theme", "dark")
    page.fill("#dvzF-publish-hashtags", "#אחד\n#שניים")
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.querySelector('.dvz-card[data-episode=\"alarms\"] .dvz-card-title')?.textContent === 'כותרת ערוכה'")
    assert config.read_bytes() == original
    over = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert over["title"] == "כותרת ערוכה" and over["theme"] == "dark" and over["publish"]["hashtags"] == ["#אחד", "#שניים"]
    page.evaluate("() => { window.veConfirm = async () => true; }")
    page.click("#dvzResetAllBtn")
    # הכותרת חוזרת - או הודעת שגיאה, שתופיע בכישלון במקום timeout בלי הסבר
    page.wait_for_function("""() => document.querySelector('.dvz-card[data-episode="alarms"] .dvz-card-title')?.textContent !== 'כותרת ערוכה'
        || document.getElementById('dvzEditorStatus').textContent.includes('שגיאה')""")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('אופסו')")
    assert not (screen["data"] / "dataviz_overrides" / "alarms.json").exists()
    assert config.read_bytes() == original
    page.fill("#dvzF-ranking-top_n", "2")
    page.click("#dvzDraftSave")
    page.wait_for_function("() => document.getElementById('dvzEditorStatus').textContent.includes('שגיאה')")