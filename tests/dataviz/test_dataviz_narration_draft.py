# tests/dataviz/test_dataviz_narration_draft.py
#
# 20.10.2026: טיוטת תסריט קריינות מהנתונים - הרגעים החזקים עם הזמן שלהם, משפט מ-Gemini (מזויף בלבד), טיוטה מקומית
# כשאין Gemini / במכסה / כשהמפסק פתוח; story.script מגיע לכתוביות ולקריינות ברגע שלו.
import json

import pytest
from fastapi.testclient import TestClient

from dataviz import captions, narration
from dataviz.episode import load_episode
from dataviz.plan import build_plan
from dataviz.web import episodes as de
from dataviz.web import narration_draft
from entrypoints import web_app
from entrypoints.web_app import app
from tests.dataviz_helpers import write_episode
from tests.fake_gemini import FakeGemini
from utils.media.gemini_quota import QuotaWatch

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "dataviz_episodes").mkdir(parents=True)
    monkeypatch.setattr(web_app, "DATA_DIR", str(data))
    monkeypatch.setattr(narration_draft, "_QUOTA", QuotaWatch())
    return {"data": data, "folder": write_episode(data / "dataviz_episodes", name="tiny")}


def _reply(prompt):
    dates = [line[2:12] for line in prompt.splitlines() if line.startswith("- ")]
    return "```json\n" + json.dumps([{"date": d, "text": f"משפט על {d}"} for d in dates], ensure_ascii=False) + "\n```"


def test_moments_are_the_strong_ones_in_video_order(env):
    result = narration_draft.draft(env["folder"], {}, ask=_reply)
    lines = result["lines"]
    assert result["source"] == "gemini" and lines
    assert [line["seconds"] for line in lines] == sorted(line["seconds"] for line in lines)
    kinds = {line["kind"] for line in lines}
    assert "jump" in kinds and "end" in kinds
    jumps = {line["date"]: line["fact"] for line in lines if line["kind"] == "jump"}
    assert "800" in jumps["2023-10-07"]                                          # היום עם ה-800
    assert all(line["text"] == f"משפט על {line['date']}" for line in lines)


def test_without_gemini_the_draft_is_local_from_the_same_moments(env):
    def broken(prompt):
        raise RuntimeError("no network")
    result = narration_draft.draft(env["folder"], {}, ask=broken)
    assert result["source"] == "local" and "Gemini לא זמין" in result["warning"]
    assert all(line["text"] == line["fact"] for line in result["lines"])


def test_quota_errors_open_the_breaker_and_skip_gemini(env):
    calls = []

    def quota(prompt):
        calls.append(prompt)
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
    for _ in range(3):
        assert narration_draft.draft(env["folder"], {}, ask=quota)["source"] == "local"
    result = narration_draft.draft(env["folder"], {}, ask=quota)
    assert len(calls) == 3 and result["source"] == "local" and "בהפסקה" in result["warning"]


def test_real_sdk_against_the_fake_server(env, monkeypatch):
    with FakeGemini([("ok", json.dumps([{"date": "2023-10-07", "text": "היום שהכל השתנה"}], ensure_ascii=False))]) as fake:
        for key, value in fake.env().items():
            monkeypatch.setenv(key, value)
        result = narration_draft.draft(env["folder"], {})
    assert fake.requests and result["source"] == "gemini"
    assert next(line for line in result["lines"] if line["date"] == "2023-10-07")["text"] == "היום שהכל השתנה"
    others = [line for line in result["lines"] if line["date"] != "2023-10-07"]
    assert all(line["text"] == line["fact"] for line in others)                  # מה ש-Gemini לא החזיר - העובדה


def test_script_lines_reach_captions_and_narration_at_their_moment(env):
    overrides = {"story": {"script": [{"date": "2023-10-07", "text": "וכאן הכל משתנה"}]}}
    episode = load_episode(env["folder"], overrides)
    plan = build_plan(episode, "full")
    fps = float(episode.config["video"]["fps"])
    spans = [s for s in captions.caption_spans(plan, fps) if s["kind"] == "script"]
    assert [s["text"] for s in spans] == ["וכאן הכל משתנה"]
    frame = plan[int(round(spans[0]["start"] * fps))]
    assert episode.dates[int(frame["x"])].strftime("%Y-%m-%d") >= "2023-10-07"
    lines = narration.narration_lines(spans + [{"kind": "event", "start": 1.0, "text": "x", "label": "x"}], events=False)
    assert [text for _t, text in lines] == ["וכאן הכל משתנה"]                    # תסריט מוקרא גם בלי אירועים
    plain = build_plan(load_episode(env["folder"], {}), "full")
    assert not any("say" in f for f in plain)                                    # בלי תסריט - הפריימים כמו קודם


def test_route_returns_a_draft_and_the_list_is_saved_like_other_story_lists(env, monkeypatch):
    monkeypatch.setattr(narration_draft, "_gemini", _reply)
    resp = client.post("/api/dataviz/narration_draft", json={"episode": "tiny"})
    assert resp.status_code == 200 and resp.json()["source"] == "gemini"
    assert de.load_overrides_for_path(env["folder"]) == {}                      # רק טיוטה - לא נכתב כלום
    assert client.post("/api/dataviz/narration_draft", json={"episode": "nope"}).status_code == 404
    with pytest.raises(de.EpisodeError):
        de.update_override_fields(str(env["data"]), "tiny", {"story.script": [{"date": "2023-10-08"}]}, [])   # בלי משפט
    de.update_override_fields(str(env["data"]), "tiny", {"story.script": [{"date": "2023-10-07", "text": " שלום ", "extra": 1}]}, [])
    assert de.load_overrides_for_path(env["folder"])["story"]["script"] == [{"date": "2023-10-07", "text": "שלום"}]
