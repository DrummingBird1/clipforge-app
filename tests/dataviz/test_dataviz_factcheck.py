# tests/dataviz/test_dataviz_factcheck.py
#
# 20.10.2026: בדיקת עובדות לפני רינדור - המספרים שיופיעו על המסך (סוף כל שנה, תיבת הסיום, התראות שיא) מול הקבצים, עם
# שורות המקור. פרק נקי - הכל מתאים; ציר זמן שחותך חלק מתקופה - מסומן "לא מתאים"; שם חלופי - שינוי מכוון, לא נבדק.
# לקריאה בלבד.
import hashlib
import os

import pytest
from fastapi.testclient import TestClient

from dataviz.web import factcheck
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


def _tree(root):
    return sorted((os.path.relpath(os.path.join(d, f), root), hashlib.md5(open(os.path.join(d, f), "rb").read()).hexdigest())
                  for d, _dirs, files in os.walk(root) for f in files)


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    return data


def test_a_clean_episode_matches_its_files_and_shows_the_source_rows(env):
    folder = write_episode(env / "dataviz_episodes", name="tiny")
    before = _tree(env)
    body = client.get("/api/dataviz/episodes/data", params={"episode": "tiny", "part": "facts"}).json()["data"]
    assert body["checked"] > 5 and body["mismatches"] == 0 and body["transforms"] == []
    end = {r["entity"]: r for r in body["end_box"]}
    assert end["2023"]["shown"] == end["2023"]["expected"] == "820" and end["2023"]["ok"] is True    # 800 + 20 מ-South
    assert end["2020"]["source_rows"][-1]["source"] == "annual.csv" and end["2020"]["source_rows"][-1]["value"] == 732
    assert {r["date"][-5:] for r in body["key_frames"]} == {"12-31", "11-01"}                       # סוף כל שנה, והיום האחרון
    assert _tree(env) == before and os.path.isdir(folder)                                          # לקריאה בלבד


def test_a_number_that_differs_from_the_files_is_flagged(env):
    folder = write_episode(env / "dataviz_episodes", overrides={"timeline": {"start": "2020-06-01"}}, name="cropped")
    result = factcheck.fact_check(folder, {})
    wrong = [r for r in result["key_frames"] if r["ok"] is False]
    by_entity = {r["entity"]: r for r in wrong}
    assert by_entity["2020"]["expected"] == "732" and by_entity["2020"]["shown"] != "732"            # חודשי 2020 שנחתכו
    assert by_entity["2019"]["expected"] == "365" and by_entity["2019"]["shown"] == "0"
    assert result["mismatches"] >= len(wrong)


def test_deliberate_changes_are_listed_and_not_checked(env):
    folder = write_episode(env / "dataviz_episodes", overrides={"entities": {"aliases": {"2023": "השנה האחרונה"}}}, name="aliased")
    result = factcheck.fact_check(folder, {})
    assert {"entity": "השנה האחרונה", "reason": "שם חלופי: 2023 -> השנה האחרונה"} in result["transforms"]
    row = next(r for r in result["end_box"] if r["entity"] == "השנה האחרונה")
    assert row["ok"] is None and result["mismatches"] == 0
