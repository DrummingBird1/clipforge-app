# tests/dataviz/test_dataviz_smart_story.py
#
# 20.10.2026: עורך הגרפים החכם, פריטים 8-9 - "מוצא הסיפור" (החלפת מקום ראשון שנשארת, שיא, שבר במגמה, מספר עגול ->
# סוג סיפור, עצירות, הדגשות וקטעי מהירות) והצעות לאירועים בתאריכים החזקים (כל אחת צריכה אישור ועם מקור; Gemini רק
# דרך כללי המכסה ורק מזויף כאן; הניתוח עצמו לא קורא ל-Gemini).
import pandas as pd
import pytest

from dataviz.smart import draft, events
from dataviz.smart.story import find_moments, speed_sections, story_type
from utils.media.gemini_quota import QuotaWatch


def _m(rows, columns, start=2000):
    return pd.DataFrame(rows, columns=columns, index=pd.to_datetime([f"{start + i}-01-01" for i in range(len(rows))]))


def test_a_lead_change_counts_only_when_it_stays():
    m = _m([[10, 5, 1], [20, 15, 2], [30, 31, 3], [40, 39, 4], [50, 60, 5], [60, 70, 6], [70, 80, 7], [80, 90, 8]], ["א", "ב", "ג"])
    leads = [mo for mo in find_moments(m, "amount", {"label": "עולים"}) if mo["kind"] == "lead"]
    assert [(mo["date"], mo["entity"]) for mo in leads] == [("2004-01-01", "ב")]   # 2002 - רק תקופה אחת, לא נחשב
    assert "ב עוקף את א" in leads[0]["text"] and "60 עולים" in leads[0]["text"]


def test_records_trend_breaks_and_round_numbers():
    level = _m([[10], [12], [15], [19], [24], [22], [18], [15], [13], [12], [11], [10]], ["מפלס"])
    moments = find_moments(level, "level", {"label": "מטר", "suffix": " מ'"}, leads=False)
    kinds = {mo["kind"]: mo for mo in moments}
    assert kinds["record"]["date"] == "2004-01-01" and "24 מ'" in kinds["record"]["text"]
    assert kinds["trend"]["text"].endswith("ירידה") and "מפלס" in kinds["trend"]["text"]
    total = _m([[300_000 * (i + 1)] for i in range(6)], ["סך"])
    round_moment = next(mo for mo in find_moments(total, "level", {"label": "$", "prefix": "$"}) if mo["kind"] == "round")
    assert round_moment["text"] == "סך חוצה את $1 מיליון" and round_moment["date"] == "2003-01-01"


def test_story_type_and_speed_sections():
    assert story_type([{"kind": "lead", "strength": 3}] * 3, "bar_race", 10)["value"] == "race"
    assert story_type([], "line_race", 2)["value"] == "compare"
    split = story_type([{"kind": "trend", "strength": 2.2, "date": "2010-01-01"}], "line_race", 5)
    assert split["value"] == "before_after" and split["split"] == "2010-01-01"
    sections = speed_sections([{"date": "2001-01-01", "strength": 3}, {"date": "2001-03-01", "strength": 3}],
                              pd.Timestamp("2000-01-01"), pd.Timestamp("2020-01-01"))
    slow = [s for s in sections if s["speed"] == 0.5]
    assert len(slow) == 1                                                     # שני רגעים קרובים - קטע איטי אחד
    assert any(s["speed"] == 2.0 and s["start"] >= slow[0]["end"] for s in sections)   # הקטע השקט - מהר


def _race_folder(tmp_path):
    lines = ["year,entity,immigrants"]
    for i, year in enumerate(range(1985, 1996)):
        lines += [f"{year},אירופה,{100 + i}", f"{year},אסיה,{50 + (300 if year >= 1990 else 0)}", f"{year},אפריקה,{20}", f"{year},אמריקה,{10}"]
    (tmp_path / "immigrants_by_continent.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (tmp_path / "SOURCES.md").write_text("עלייה לישראל, הלמ\"ס\n", encoding="utf-8")
    return tmp_path


def test_the_story_of_a_folder(tmp_path):
    story = draft.analyze(str(_race_folder(tmp_path)))["story"]
    lead = next(mo for mo in story["moments"] if mo["kind"] == "lead")
    assert lead["entity"] == "אסיה" and lead["date"].startswith("199")
    assert story["pauses"] and all(p["text"] and p["date"] for p in story["pauses"])
    assert any(c["entity"] == "אסיה" for c in story["callouts"])
    assert story["start"] == "1985-01-01" and story["end"] == "1995-01-01"


def test_event_suggestions_need_approval_and_match_the_topic(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "_gemini", lambda prompt: pytest.fail("הניתוח לא קורא ל-Gemini"))
    result = draft.analyze(str(_race_folder(tmp_path)))["events"]
    labels = [s["label"] for s in result["suggestions"]]
    assert "העלייה הגדולה מברית המועצות" in labels                         # נושא העלייה, ליד הקפיצה ב-1990
    assert "מחאת האוהלים" not in labels and "התפוצצות בועת הדוט-קום" not in labels
    assert all(s["needs_approval"] and s["source"] and s["moment"] for s in result["suggestions"])
    world = tmp_path / "world"
    world.mkdir()
    (world / "medals_per_games.csv").write_text("year,entity,total_medals\n1988,a,5\n1988,b,1\n1992,a,5\n1992,b,9\n1996,a,6\n1996,b,12\n", encoding="utf-8")
    moments = [{"date": "1992-01-01", "kind": "lead", "strength": 3, "text": "b עוקף את a"}]
    picked = events.suggest(str(world), moments, "1988-01-01", "1996-01-01", use_gemini=False)["suggestions"]
    assert [s["label"] for s in picked] == ["פירוק ברית המועצות"]               # עולמי וספורט - לא העלייה (ישראלי)


def test_gemini_suggestions_are_checked_and_follow_the_quota_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(events, "_QUOTA", QuotaWatch())
    (tmp_path / "events.csv").write_text("date,label\n1990-02-01,כבר בתיקייה\n", encoding="utf-8")
    moments = [{"date": "1990-01-01", "kind": "lead", "strength": 3, "text": "אסיה עוקף את אירופה"},
               {"date": "2005-01-01", "kind": "record", "strength": 2.5, "text": "השיא"}]
    reply = ('[{"date": "2005-06-01", "label": "אירוע אמיתי", "source": "ויקיפדיה", "moment": "2005-01-01"},'
             ' {"date": "2005-07-01", "label": "בלי מקור", "source": ""},'
             ' {"date": "1990-02-15", "label": "אותו חודש כמו מה שבתיקייה", "source": "x"},'
             ' {"date": "1970-01-01", "label": "רחוק מכל רגע", "source": "x"}]')
    result = events.suggest(str(tmp_path), moments, "1985-01-01", "2010-01-01", ask=lambda prompt: reply)
    assert result["existing"][0]["label"] == "כבר בתיקייה" and result["source"] == "gemini"
    assert [(s["label"], s["origin"]) for s in result["suggestions"] if s["origin"] == "gemini"] == [("אירוע אמיתי", "gemini")]

    def quota(prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota")
    calls = []
    for _ in range(4):
        result = events.suggest(str(tmp_path), moments, "1985-01-01", "2010-01-01", ask=lambda p: calls.append(p) or quota(p))
    assert len(calls) == 3 and "בהפסקה" in result["warning"]                  # המפסק נפתח אחרי 3 כשלי מכסה


def test_matrix_of_two_sources_is_sorted_without_a_pandas4_warning(monkeypatch):
    """25.10.2026: pd.concat של שני מקורות עם תאריכים שונים - Pandas4Warning (ב-pandas 4 ברירת המחדל לא ממיינת)."""
    import warnings

    import dataviz.sources
    from dataviz.smart import story
    tables = {
        "a.csv": pd.DataFrame({"time": pd.to_datetime(["2001-01-01", "2003-01-01"]), "entity": ["א", "א"], "value": [1.0, 2.0]}),
        "b.csv": pd.DataFrame({"time": pd.to_datetime(["2000-01-01", "2002-01-01"]), "entity": ["ב", "ב"], "value": [5.0, 1.0]}),
    }
    monkeypatch.setattr(dataviz.sources, "read_table", lambda spec, folder: tables[spec["path"]].copy())
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = story.matrix("x", {"sources": [{"path": "a.csv"}, {"path": "b.csv"}]})
    assert list(result.index.year) == [2000, 2001, 2002, 2003]
    assert list(result["ב"]) == [5.0, 5.0, 6.0, 6.0]
