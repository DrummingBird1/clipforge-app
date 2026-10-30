# tests/dataviz/test_dataviz_files_smart_guess.py
#
# 23.10.2026, המלצה 5 מסיור השימושיות של 21.10.2026: הטופס "מקבצים" דרש 6 תיקונים ביד - כמות /
# רמה בשני הקבצים, ציר ימני לשני, מרוץ קווים, וכותרת במקום שם הקובץ - כשהעורך החכם כבר ידע. /api/dataviz/episodes/smart_guess
# מחזיר את הניחוש שלו לקבצים שנבחרו (לא נכתב דבר).
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

TEMP = "year,entity,level_value\n2000,טמפרטורה (°C),18\n2001,טמפרטורה (°C),19\n2002,טמפרטורה (°C),18.5\n2003,טמפרטורה (°C),19.2\n"
LAKE = "year,entity,level_value\n2000,מפלס (מטר),210\n2001,מפלס (מטר),211\n2002,מפלס (מטר),209\n2003,מפלס (מטר),208.5\n"


def _guess(files):
    return client.post("/api/dataviz/episodes/smart_guess", json={"files": files})


def test_two_level_files_in_different_units_get_levels_two_axes_lines_and_a_title():
    for first, second in (("temperature.csv", "lake.csv"), ("lake.csv", "temperature.csv")):
        texts = {"temperature.csv": TEMP, "lake.csv": LAKE}
        resp = _guess([{"filename": first, "csv_text": texts[first]}, {"filename": second, "csv_text": texts[second]}])
        assert resp.status_code == 200, resp.text                              # קודם: 404 (אין ניחוש לטופס)
        guess = resp.json()
        assert [f["kind"] for f in guess["files"]] == ["level", "level"]
        assert [f["axis"] for f in guess["files"]] == ["left", "right"]          # הציר הימני תמיד על הקובץ הנוסף
        assert guess["chart"] == "line_race"
        assert guess["title"] and "csv" not in guess["title"] and guess["title"] != first


def test_a_bad_request_is_refused_and_nothing_is_guessed_without_a_series():
    assert _guess([]).status_code == 400
    assert _guess([{"filename": "x.csv", "csv_text": "  "}]).status_code == 400
    assert _guess("nope").status_code == 400
    resp = _guess([{"filename": "notes.csv", "csv_text": "a,b\nx,y\n"}])
    assert resp.status_code == 200 and resp.json()["files"] == [None] and resp.json()["chart"] is None
