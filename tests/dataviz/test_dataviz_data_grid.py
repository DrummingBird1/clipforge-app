# tests/dataviz/test_dataviz_data_grid.py
#
# 20.10.2026: עריכת נתונים בטבלה - כל השורות של מקור (לא רק 20 התצוגה), עד GRID_MAX_ROWS לעריכה (מעל - לקריאה בלבד).
# השמירה עוברת דרך update_data (השוואה, ואז קובץ חדש) - נבדק בטסט הדפדפן.
import pytest
from fastapi.testclient import TestClient

from dataviz.web import data as dd
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import DAILY_ROWS, write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return write_episode(data / "dataviz_episodes", name="tiny")


def test_the_table_has_every_row_of_the_source_as_text(env):
    annual = dd.source_table(env, {}, 0)
    assert annual["columns"] == ["year", "total"] and annual["rows"] == [["2019", "365"], ["2020", "732"]] and annual["editable"]
    alarms = client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": "table", "source": 1}).json()["data"]
    assert alarms["total"] == len(DAILY_ROWS) == len(alarms["rows"]) > dd.PREVIEW_ROWS          # כל השורות, לא 20
    assert client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": "table", "source": 9}).status_code == 404


def test_a_large_source_is_read_only_in_the_table(env, monkeypatch):
    monkeypatch.setattr(dd, "GRID_MAX_ROWS", 10)
    table = dd.source_table(env, {}, 1)
    assert len(table["rows"]) == 10 and table["total"] == len(DAILY_ROWS) and not table["editable"]
