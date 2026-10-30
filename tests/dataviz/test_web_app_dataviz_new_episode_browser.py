# tests/test_web_app_dataviz_new_episode_browser.py
#
# עורך הגרפים בדפדפן (19.10.2026, מהסיור): "➕ פרק חדש" מנחש נכון קובץ כמו של הכנרת (שם ישות עם פסיק במרכאות - קודם
# העמודות זזו ועמודת טקסט נבחרה כערך; עמודת שנים = "שנה" ולא "יום"), בחירת כמות / רמה לכל קובץ, שמות הקבצים המקוריים,
# ו"✏️ מיפוי" למקור קיים בחלון הנתונים - נשמר ב-override, config.yaml לא משתנה.
# xdist-group: workspace
import hashlib
import json
import os


import pytest
import yaml

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

VIDEO = {"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}}
TEMP = ("year,entity,level_value,station,valid_days,delta_value\n"
        + "".join(f'{y},"טמפרטורה (°C, בית דגן)",{18 + (y - 2000) * 0.1:.3f},2520 BET DAGAN,365,0.1\n' for y in range(2000, 2010)))
LAKE = ("year,entity,level_value,survey_points,first_point,last_point,delta_value\n"
        + "".join(f'{y},"מפלס הכנרת (מטר, ממוצע)",{210 + (y % 3):.3f},50,{y}-01-02,{y}-12-30,0.5\n' for y in range(2001, 2010)))


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
    return {"data": data}


def _open(page):
    page.evaluate("() => { closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector(".dvz-card")


def test_new_episode_from_lake_like_files_guesses_and_keeps_names(editor_page, screen, tmp_path):
    page = editor_page
    _open(page)
    temp, lake = tmp_path / "temperature betdagan.csv", tmp_path / "lake_level.csv"
    temp.write_text(TEMP, encoding="utf-8")
    lake.write_text(LAKE, encoding="utf-8")
    page.click("#dvzNewBtn")
    page.click("#dvzNewDialog [data-new-way=files]")   # 21.10.2026: "➕ פרק חדש" -> "📄 מקבצים"
    page.set_input_files("#dvzNewCsv", [str(temp), str(lake)])
    page.wait_for_selector("#dvzNewExtra .dvz-source select[data-field='kind']")
    assert page.input_value("#dvzNewValue") == "level_value" and page.input_value("#dvzNewPeriod") == "year"   # לא station, לא יום
    assert page.input_value("#dvzNewGroup") == "entity"
    extra = "#dvzNewExtra .dvz-source select[data-field='%s']"
    assert page.input_value(extra % "value_column") == "level_value" and page.input_value(extra % "period") == "year"
    page.fill("#dvzNewName", "climate")
    page.fill("#dvzNewTitle", "אקלים וכנרת")
    page.select_option("#dvzNewChart", "line_race")
    page.select_option("#dvzNewKind", "level")
    page.select_option(extra % "kind", "level")
    page.click("#dvzCreateBtn")
    page.wait_for_selector('.dvz-card[data-episode="climate"]')
    folder = screen["data"] / "dataviz_episodes" / "climate"
    assert sorted(os.listdir(folder)) == ["config.yaml", "lake_level.csv", "temperature_betdagan.csv"]
    sources = yaml.safe_load((folder / "config.yaml").read_text(encoding="utf-8"))["sources"]
    assert [(s["path"], s.get("kind"), s["value"]) for s in sources] == [
        ("temperature_betdagan.csv", "level", {"column": "level_value"}), ("lake_level.csv", "level", {"column": "level_value"})]


def test_the_mapping_of_a_source_is_edited_from_the_data_window(editor_page, screen):
    page = editor_page
    _open(page)
    config = screen["data"] / "dataviz_episodes" / "alarms" / "config.yaml"
    md5 = hashlib.md5(config.read_bytes()).hexdigest()
    page.evaluate("() => { dvzData.tab = 'sources'; const d = document.getElementById('dvzData'); d.open = true; dvzLoadData(); }")
    page.wait_for_selector(".dvz-source .dvz-edit-mapping")
    page.locator(".dvz-source .dvz-edit-mapping").first.click()
    box = ".dvz-source >> nth=0 >> .dvz-mapping-edit"
    assert page.input_value(f"{box} input[data-field='legend']") == "שנתי"            # מתחיל מהמיפוי הקיים
    page.fill(f"{box} input[data-field='legend']", "סיכום שנתי")
    page.click(f"{box} >> text=💾 שמור מיפוי")
    page.wait_for_function("() => [...document.querySelectorAll('.dvz-source-head')].some(h => h.textContent.includes('מקרא: סיכום שנתי'))")
    overrides = json.loads((screen["data"] / "dataviz_overrides" / "alarms.json").read_text(encoding="utf-8"))
    assert overrides["sources"][0]["legend"] == "סיכום שנתי" and overrides["sources"][0]["texture"] == "stripes"
    assert hashlib.md5(config.read_bytes()).hexdigest() == md5
