# tests/dataviz/test_web_app_dataviz_files_smart_guess_browser.py
#
# 23.10.2026, המלצה 5: בטופס "מקבצים" הניחוש של העורך החכם ממלא את סוג הערכים (גם בקובץ הנוסף), הציר של הקובץ הנוסף, סוג
# התרשים והכותרת - רק בשדות שהמשתמש לא נגע בהם. קודם: "כמות", "מרוץ עמודות", ציר שמאל ושם הקובץ - 6 תיקונים ביד.
# xdist-group: workspace
import pytest

from tests.dataviz_helpers import write_episode

pytestmark = [pytest.mark.filterwarnings("ignore::DeprecationWarning"), pytest.mark.xdist_group("workspace")]

TEMP = "year,entity,level_value\\n2000,טמפרטורה (°C),18\\n2001,טמפרטורה (°C),19\\n2002,טמפרטורה (°C),18.5\\n2003,טמפרטורה (°C),19.2\\n"
LAKE = "year,entity,level_value\\n2000,מפלס (מטר),210\\n2001,מפלס (מטר),211\\n2002,מפלס (מטר),209\\n2003,מפלס (מטר),208.5\\n"


@pytest.fixture
def screen(editor_server, tmp_path, monkeypatch):
    web_app = editor_server["web_app"]
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    workspace.mkdir()
    write_episode(data / "dataviz_episodes", name="alpha")
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    return data


def _choose(page):
    page.evaluate(f"""() => dvzCsvChosen({{files: [new File(["{TEMP}"], "temperature.csv", {{type: "text/csv"}}),
                                                  new File(["{LAKE}"], "lake.csv", {{type: "text/csv"}})]}})""")


def _open_form(page):
    page.evaluate("() => { localStorage.setItem('dvzMode', 'regular'); closeVeEditor(); switchTab('dataviz'); }")
    page.wait_for_selector("#dvzEpisodes .dvz-card")
    page.evaluate("() => dvzOpenNew('files')")
    page.wait_for_selector("#dvzNewDialog[open]")


def test_the_from_files_form_takes_the_smart_editors_guess(editor_page, screen):
    page = editor_page
    _open_form(page)
    _choose(page)
    page.wait_for_function("() => document.getElementById('dvzNewChart').value === 'line_race'", timeout=15000)   # קודם: מרוץ עמודות
    form = page.evaluate("""() => {
        const extra = _dvzExtraFiles[0].mapping;
        return {kind: dvzNewKind.value, title: dvzNewTitle.value, extraKind: extra.querySelector('[data-field="kind"]').value,
                extraAxis: extra.querySelector('[data-field="axis"]').value};
    }""")
    assert form["kind"] == "level" and form["extraKind"] == "level" and form["extraAxis"] == "right"   # קודם: כמות, כמות, שמאל
    assert form["title"] and form["title"] != "temperature"                    # קודם: שם הקובץ


def test_a_field_the_user_changed_keeps_its_value(editor_page, screen):
    page = editor_page
    _open_form(page)
    page.select_option("#dvzNewChart", "pie_race")                              # שינוי של המשתמש לפני הקבצים
    _choose(page)
    page.wait_for_function("() => document.getElementById('dvzNewKind').value === 'level'", timeout=15000)
    assert page.evaluate("() => document.getElementById('dvzNewChart').value") == "pie_race"
