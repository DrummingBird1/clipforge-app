# tests/dataviz/test_dataviz_smart_texts.py
#
# 20.10.2026: עורך הגרפים החכם, פריטים 10-13 ו-18/20 - כותרות / כותרת משנה / פתיח בעברית ובאנגלית מעובדות מחושבות בלבד
# (בלי Gemini - כללים; עם Gemini - מזויף בלבד, ואפשרות עם מספר שלא חושב נזרקת), חבילת יוטיוב (תיאור, תגיות, פרקים,
# קרדיטים מ-SOURCES.md), תמונה ממוזערת מהרגע החזק וטיוטת קריינות על הרגעים של מוצא הסיפור.
import os

import pytest
from PIL import Image

from dataviz.smart import draft, package, texts, thumb
from dataviz.web import narration_draft
from tests.dataviz_helpers import write_episode
from utils.media.gemini_quota import QuotaWatch


@pytest.fixture
def race(tmp_path):
    lines = ["year,entity,country_en,total_medals"]
    for i, year in enumerate(range(1980, 1996)):
        lines += [f"{year},צרפת,France,{20}", f"{year},יפן,Japan,{5 + (60 if year >= 1988 else 0)}",
                  f"{year},איטליה,Italy,{8}", f"{year},קנדה,Canada,{3}"]
    (tmp_path / "medals_per_games.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "SOURCES.md").write_text("# SOURCES\n- **Source:** Olympedia, medal tables (https://www.olympedia.org).\n- **Units:** medals.\n",
                                         encoding="utf-8")
    return tmp_path


def _facts(folder):
    analysis = draft.analyze(str(folder))
    return analysis, texts.facts(analysis, os.path.basename(str(folder)), str(folder))


def test_titles_and_hooks_come_from_the_facts_in_two_languages(race):
    analysis, f = _facts(race)
    assert (f["start"], f["end"], f["first_leader"], f["last_leader"]) == ("1980", "1995", "צרפת", "יפן")
    result = texts.suggest_texts(f)
    assert result["source"] == "rules"
    assert result["titles"][0] == {"he": "מי מוביל במדליות האולימפיות?", "en": "Who leads in Olympic medals?"}   # ב+ה -> ב
    assert {"he": "ב-1980 במקום הראשון: צרפת. ומה ב-1995?", "en": "In 1980, France was first. And in 1995?"} in result["hooks"]
    for key in ("titles", "subtitles", "hooks"):
        for option in result[key]:
            assert option["he"] and option["en"] and texts.check_numbers(option["he"] + " " + option["en"], f["allowed"]) == []


def test_gemini_options_with_invented_numbers_are_dropped(race, monkeypatch):
    monkeypatch.setattr(texts, "_QUOTA", QuotaWatch())
    _a, f = _facts(race)
    reply = ('{"titles": [{"he": "יפן עוקפת את צרפת ב-1988", "en": "Japan passes France in 1988"},'
             ' {"he": "יפן עם 999 מדליות", "en": "Japan with 999 medals"}], "hooks": []}')
    result = texts.suggest_texts(f, ask=lambda prompt: reply, use_gemini=True)
    assert result["titles"][0] == {"he": "יפן עוקפת את צרפת ב-1988", "en": "Japan passes France in 1988", "ai": "1"}
    assert all("999" not in o["he"] for o in result["titles"]) and "נזרקו" in result["warning"]

    def quota(prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
    for _ in range(4):
        result = texts.suggest_texts(f, ask=quota, use_gemini=True)
    assert result["source"] == "rules" and "בהפסקה" in result["warning"] and result["titles"]   # בלי Gemini - עדיין יש כותרות


def test_the_youtube_package(race):
    analysis, f = _facts(race)
    pack = package.build(f, texts.suggest_texts(f), analysis["story"], analysis["scan"]["docs"], israel=False)
    assert pack["title"] == "מי מוביל במדליות האולימפיות?"
    assert pack["credits"] == ["Olympedia, medal tables"]                    # בלי הכתובת ובלי סוגריים ריקים
    assert "יפן עוקף את צרפת" in pack["description"] and "#נתונים" in pack["hashtags"] and "#ישראל" not in pack["hashtags"]
    assert 1 <= len(pack["chapters"]) <= 5 and all(c["date"] and c["title"] for c in pack["chapters"])
    assert package.credits("- **Source:** CBS, table 2.53\n- **מקור:** הלמ\"ס\n- text about the source of truth\n") == ["CBS, table 2.53", "הלמ\"ס"]


def test_narration_draft_on_the_story_moments(tmp_path, monkeypatch):
    monkeypatch.setattr(narration_draft, "_QUOTA", QuotaWatch())
    folder = write_episode(tmp_path, name="tiny")
    moments = [{"date": "2023-10-07", "kind": "record", "text": "השיא: 800 ביום אחד", "strength": 2.5},
               {"date": "2021-05-10", "kind": "lead", "text": "2021 עוקף", "strength": 3}]
    reply = '[{"date": "2023-10-07", "text": "קפיצה של 900 ביום אחד"}, {"date": "2021-05-10", "text": "המרוץ מתחיל"}]'
    result = narration_draft.draft(folder, {}, ask=lambda prompt: reply, story_moments=moments)
    by_kind = {line["kind"]: line for line in result["lines"]}
    assert set(by_kind) == {"record", "lead"} and by_kind["record"]["seconds"] > by_kind["lead"]["seconds"]
    assert by_kind["record"]["text"] == "השיא: 800 ביום אחד"                 # 900 לא בנתונים - העובדה במקום
    assert by_kind["lead"]["text"] == "המרוץ מתחיל" and "הוחלפו בעובדה" in result["warning"]


def test_thumbnail_from_the_strongest_moment(tmp_path):
    folder = write_episode(tmp_path, name="tiny", overrides={"video": {"width": 640, "height": 360, "fps": 10, "dpi": 40}})
    moments = [{"date": "2021-05-10", "strength": 1.5}, {"date": "2023-10-07", "strength": 3}, {"date": "2022-01-01", "strength": 3}]
    assert thumb.strongest(moments) == "2022-01-01" and thumb.strongest([]) == ""
    out = tmp_path / "out" / "thumb.png"
    result = thumb.make(folder, {}, "2023-10-07", "כותרת לבדיקה", str(out), str(tmp_path / "cache"))
    assert out.is_file() and Image.open(out).size == (320, 180) and result["position"] > 0.5
