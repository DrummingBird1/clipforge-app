# tests/dataviz/test_dataviz_wave59.py - גל 59: סידור עורך הגרפים. הטופס "הגדרות הפרק (עריכה)" יצא - אותם 8 שדות בקבוצה "⭐ בסיסי"
# בראש העורך המלא (dataviz/schema.py), והתצוגה החיה מקבלת את התאריך וקצב הפריימים של הפריים (לזמן בסרטון במקום מספר פריים).
from urllib.parse import unquote


from fastapi.testclient import TestClient

from dataviz import schema
from dataviz.charts import CHART_MODULES
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from dataviz.web import episodes as de

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

SMALL = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 40}}
BASIC = ["title", "subtitle", "chart", "theme", "ranking.top_n", "publish.title", "publish.description", "publish.hashtags"]


def test_the_basic_group_holds_what_the_old_form_edited():
    assert schema.GROUPS[0][0] == "basic"
    assert [f["path"] for f in schema.FIELDS if f["group"] == "basic"] == BASIC
    assert sorted(schema.CHART_CHOICES) == sorted(CHART_MODULES)          # סוג תרשים חדש לא יישכח בבחירה
    assert set(de.BASIC_FORM_PATHS) - {"publish.enabled"} == set(BASIC)


def test_basic_fields_save_through_the_full_editor(tmp_path):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    write_episode(data / "dataviz_episodes", name="ep", overrides=SMALL)
    saved = de.update_override_fields(str(data), "ep", {"title": "חדש", "chart": "pie_race", "theme": "dark", "ranking.top_n": 5,
                                                         "publish.hashtags": "#א\n#ב"}, [])
    assert saved["title"] == "חדש" and saved["chart"] == "pie_race" and saved["theme"] == "dark"
    assert saved["ranking"]["top_n"] == 5 and saved["publish"]["hashtags"] == ["#א", "#ב"]


def test_the_preview_frame_carries_its_date_and_fps(tmp_path, monkeypatch):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    (data / "dataviz_episodes").mkdir(parents=True)
    write_episode(data / "dataviz_episodes", name="ep", overrides=SMALL)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(web_app, "WORKSPACE_DIR", str(workspace))
    resp = client.get("/api/dataviz/preview_frame", params={"episode": "ep", "pos": 0.5, "scale": 0.35})
    assert resp.status_code == 200
    assert float(resp.headers["X-Frame-Fps"]) > 0
    assert unquote(resp.headers["X-Frame-Date"])                          # פריים באמצע הסרטון - יש לו תאריך
    assert int(resp.headers["X-Frame-Index"]) < int(resp.headers["X-Frame-Count"])
