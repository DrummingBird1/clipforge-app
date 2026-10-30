# dataviz/smart/draft.py
#
# 20.10.2026: מתיקיית נתונים לבחירות של טיוטת פרק. כל שלב מוסיף בחירות עם סיבה וביטחון; choices() מחזיר את התמונה
# השטוחה (לציון מול הקורפוס ולמסך "ההגדרות הסופיות"). קריאה בלבד מהתיקייה.
import os
import re
from typing import Any, Dict, List

from dataviz.smart.scan import scan_folder

AGGREGATE_WORDS = r"national|total|overall|all_|_all|ארצי|כלל|סך"


def _time_range(folder: str, f: Dict[str, Any]) -> Any:
    """(ראשון, אחרון) של עמודת הזמן בקובץ, או None."""
    from dataviz.smart.columns import parse_times
    from dataviz.smart.scan import load_table
    df = load_table(folder, f["name"]) if folder else None
    if df is None or f["roles"]["time"]["column"] not in df.columns:
        return None
    times = parse_times(df[f["roles"]["time"]["column"]].astype(str)).dropna()
    return (times.min(), times.max()) if len(times) else None


def _split_by_time(folder: str, a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """ג14: שני קבצים של אותה סדרה לתקופות שונות (exports_2000_2009, exports_2010_2019) - לא "אותם נתונים פעמיים"."""
    first, second = _time_range(folder, a), _time_range(folder, b)
    return first is not None and second is not None and (first[1] < second[0] or second[1] < first[0])


def pick_series(files: List[Dict[str, Any]], folder: str = "") -> List[Dict[str, Any]]:
    """הסדרות שהפרק משתמש בהן: מה ש-SOURCES.md קורא לו 'engine data' קודם; סדרה מצרפית בלי ישות ('national', 'total')
    לצד סדרות לפי ישות - בחוץ (סכום של האחרות); שני קבצים עם אותה עמודת ערך ואותן ישויות - אחד מהם (engine / 'levels'),
    אלא אם הם לתקופות שונות (ג14) - אז שניהם, והמנוע מחבר אותם לסדרה אחת לפי הזמן."""
    series = [f for f in files if f["kind"] == "series"]
    engine = [f for f in series if f.get("engine")]
    if engine:
        return engine
    with_entity = [f for f in series if f["roles"]["entity"] and f["roles"]["entity"].get("unique", 1) > 1]
    if with_entity:
        series = [f for f in series if f in with_entity or not re.search(AGGREGATE_WORDS, f["name"].lower())]
    chosen: List[Dict[str, Any]] = []
    for f in sorted(series, key=lambda f: (0 if "level" in f["name"].lower() else 1, f["name"])):
        names = set((f["roles"]["entity"] or {}).get("names") or [])
        if any(c["roles"]["value"]["column"] == f["roles"]["value"]["column"] and names == set((c["roles"]["entity"] or {}).get("names") or [])
               and not _split_by_time(folder, c, f) for c in chosen):
            continue   # אותה עמודת ערך ואותן ישויות באותן תקופות - אותם נתונים פעמיים
        chosen.append(f)
    return chosen


def analyze(folder: str) -> Dict[str, Any]:
    """הניתוח המלא: סריקה, בחירת הסדרות, איך הן משתלבות (מקורות, צירים, השלמה), ניקוי, תרשים, סיפור והצעות לאירועים
    (בלי Gemini - הוא רק בבקשה מפורשת מהמסך)."""
    from dataviz.smart.chart import choose
    from dataviz.smart.clean import clean
    from dataviz.smart.events import suggest
    from dataviz.smart.relations import plan
    from dataviz.smart.story import find_story
    scan = scan_folder(folder)
    series = pick_series(scan["files"], folder)
    result: Dict[str, Any] = {"scan": scan, "series": series, "plan": plan(folder, series) if series else None,
                              "cleaning": clean(folder, series) if series else None}
    result["chart"] = choose(folder, result)
    story = find_story(folder, result)
    result["story"] = story
    result["events"] = suggest(folder, story["moments"], story["start"], story["end"], use_gemini=False) if story.get("start") else None
    return result


def guess_files(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """23.10.2026 (המלצה 5 מסיור השימושיות): הניחוש של העורך החכם לטופס "מקבצים" - לכל קובץ כמות / רמה, ציר והשלמה,
    ולפרק תרשים, כותרת ותת-כותרת. files = [{filename, csv_text}] לפי הסדר בטופס (הראשון - הקובץ הראשי). הקבצים נכתבים
    לתיקייה זמנית ונמחקים; קובץ שהניתוח לא בחר כסדרה - None. בשני צירים הציר הימני תמיד על קובץ נוסף (בטופס אין ציר
    לקובץ הראשי)."""
    import shutil
    import tempfile

    from dataviz.smart.texts import facts, rule_texts
    from dataviz.web.episodes import csv_file_names
    names = csv_file_names({"filename": files[0].get("filename"), "extra_sources": [{"filename": f.get("filename")} for f in files[1:]]})
    folder = tempfile.mkdtemp(prefix="dataviz_guess_")
    try:
        for name, f in zip(names, files):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
                fh.write(str(f.get("csv_text") or ""))
        analysis = analyze(folder)
        if not analysis["series"]:
            return {"files": [None] * len(names), "chart": None, "title": "", "subtitle": ""}
        specs = {s["path"]: s for s in analysis["plan"]["sources"]}
        guessed: List[Any] = [{"kind": specs[n].get("kind", "amount"), "axis": specs[n].get("axis", "left"), "fill": specs[n].get("fill", "none")}
                              if n in specs else None for n in names]
        if guessed[0] and guessed[0]["axis"] == "right":
            for g in guessed:
                if g:
                    g["axis"] = "left" if g["axis"] == "right" else "right"
        texts = rule_texts(facts(analysis, os.path.splitext(names[0])[0], folder))
        return {"files": guessed, "chart": analysis["chart"]["value"], "title": texts["titles"][0]["he"], "subtitle": texts["subtitles"][0]["he"]}
    finally:
        shutil.rmtree(folder, ignore_errors=True)   # safe: התיקייה הזמנית שיצרנו כאן


def choices(folder: str) -> Dict[str, Any]:
    result = analyze(folder)
    series = result["series"]
    if not series:
        return {"file": None, "columns": []}
    main = series[0]["roles"]
    return {"file": sorted(f["name"] for f in series), "columns": series[0]["columns"],
            "time": main["time"]["column"], "period": main["time"]["period"],
            "entity": (main["entity"] or {}).get("column"), "value": main["value"]["column"],
            "unit": (main["unit"] or {}).get("label") or None, "kind": (main.get("kind") or {}).get("value"), "chart": result["chart"]["value"], "top_n": result["chart"]["top_n"],
            "unit_by_file": {f["name"]: (f["roles"]["unit"] or {}).get("label") or None for f in series},
            "layout": result["plan"]["layout"], "fill": {s["path"]: s.get("fill") for s in result["plan"]["sources"] if s.get("fill")},
            "cleaning": result["cleaning"], "folder": os.path.abspath(folder)}
