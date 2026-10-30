# dataviz/smart/chart.py
#
# 20.10.2026: איזה תרשים מתאים לצורה של הנתונים, עם סיבה, ביטחון וחלופות:
#   מפה        - יש בתיקייה GeoJSON שהשמות בו מתאימים לישויות
#   שני צירים  - שתי סדרות ביחידות שונות -> קווים (line_race עם ציר ימני); יותר יחידות -> גרפים קטנים
#   פיזור      - לאותן ישויות יש מדד שני ביחידה אחרת (תוחלת חיים מול הוצאה לבריאות) -> scatter_race
#   חלקים משלם - כמות שמתחברת (לא מחיר / מדד / מעלות), עד 12 ישויות, ועדות שהן חלקים של סך אחד: קובץ בדיקת סך,
#                קטגוריית שארית ("אחר", "לא ידוע", "Other") או ערכים שמסתכמים ל-100% בכל תקופה -> שטח מוערם
#   מעט סדרות  - רמה שלא מתחברת (מחיר, מדד, °C, %), עד 25 ישויות -> קווים
#   אחרת       - הרבה ישויות שמתחרות -> מרוץ עמודות
import glob
import json
import os
import re
from typing import Any, Dict, List, Mapping

import pandas as pd

NON_ADDITIVE = ("°C", "%", "נקודות מדד", "שנים", "מטר", "ל-100 אלף", "ל-1,000")
# מטבע: מחיר ליחידה / לנפש / שיעור - לא מתחבר (קווים); סכום כמו תקציב או יצוא - מתחבר
PER_UNIT_RE = r"price|per_|_per|rate|index|avg|average|mean|exchange|מחיר|ממוצע|לנפש|ליטר|שער"
CURRENCIES = ("₪", "$", "€")
RESIDUAL_RE = r"^\s*(other|others|unknown|rest|misc|n/?a|אחר|אחרים|אחרות|לא ידוע|שאר|שונות)\b"


def geojson_match(folder: str, names: List[str]) -> Dict[str, Any]:
    """{share, file, key}: קובץ ה-GeoJSON בתיקייה והמאפיין שהשמות שלו הכי מתאימים לישויות."""
    best: Dict[str, Any] = {"share": 0.0, "file": "", "key": ""}
    for path in glob.glob(os.path.join(folder, "*.geojson")) + glob.glob(os.path.join(folder, "*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        features = data.get("features") if isinstance(data, Mapping) else None
        if not features:
            continue
        keys = {k for feature in features for k in (feature.get("properties") or {})}
        for key in sorted(keys):
            values = {str((feature.get("properties") or {}).get(key)) for feature in features}
            share = sum(1 for n in names if n in values) / len(names) if names else 0.0
            if share > best["share"]:
                best = {"share": share, "file": os.path.basename(path), "key": key}
    return best


def _second_measure(analysis: Mapping[str, Any], main: Mapping[str, Any]) -> str:
    """עמודת ערך שנייה, ביחידה אחרת, לאותן ישויות (באותו קובץ או בקובץ סדרה אחר בתיקייה)."""
    from dataviz.smart.columns import unit_of
    names = set((main["roles"]["entity"] or {}).get("names") or [])
    main_unit = str((main["roles"]["unit"] or {}).get("label") or "").split(" (")[0]   # בלי "(אלפים)" - אותה יחידה
    for f in analysis["scan"]["files"]:
        if f["kind"] != "series" or not f["roles"]["entity"]:
            continue
        other = set(f["roles"]["entity"].get("names") or [])
        if not names or len(names & other) < 0.8 * len(names):
            continue
        for value in f["roles"]["values"]:
            if value["score"] < 0.5 or value.get("derived_from") or value["column"] == main["roles"]["value"]["column"]:
                continue   # 0.5: מדד שני יכול להיות חסר בחלק מהשנים (הוצאה לבריאות רק מ-2000)
            unit = str(unit_of(value["column"])["label"]).split(" (")[0]
            if unit and unit != main_unit:
                return f"{f['name']}: {value['column']}"
    return ""


def _parts_evidence(folder: str, analysis: Mapping[str, Any], main: Mapping[str, Any], names: List[str]) -> str:
    """למה הישויות הן חלקים של סך אחד - או "" כשאין עדות: קובץ בדיקת סך, קטגוריית שארית, או סכום 100% בכל תקופה."""
    if any(f["kind"] == "check" for f in analysis["scan"]["files"]):
        return "יש קובץ בדיקת סך"
    residual = next((n for n in names if re.search(RESIDUAL_RE, str(n).lower())), None)
    if residual:
        return f"יש קטגוריית שארית - '{residual}'"
    if str((main["roles"].get("unit") or {}).get("label") or "").startswith("%") and main["roles"].get("entity"):
        from dataviz.smart.columns import parse_times
        from dataviz.smart.scan import load_table
        df = load_table(folder, main["name"])
        if df is not None:
            roles = main["roles"]
            values = pd.to_numeric(df[roles["value"]["column"]], errors="coerce")
            sums = values.groupby(parse_times(df[roles["time"]["column"]])).sum()
            if len(sums) and ((sums - 100).abs() <= 2).mean() > 0.9:
                return "100%"
    return ""


def choose(folder: str, analysis: Mapping[str, Any]) -> Dict[str, Any]:
    """{value, confidence, reason, alternatives: [{value, reason}], top_n}."""
    series = analysis["series"]
    if not series:
        return {"value": "bar_race", "confidence": 0.2, "reason": "אין סדרה - ברירת מחדל", "alternatives": [], "top_n": 10}
    main = series[0]
    roles = main["roles"]
    names = list((roles["entity"] or {}).get("names") or [])
    entities = sum(max(1, (f["roles"]["entity"] or {}).get("unique", 1)) for f in series)
    kind = (roles.get("kind") or {}).get("value")
    unit = str((roles["unit"] or {}).get("label") or "")
    layout = (analysis.get("plan") or {}).get("layout", "single")
    top_n = max(3, min(entities, 10))   # המנוע: 3 עד 30
    geo = geojson_match(folder, names)
    if geo["share"] >= 0.6:
        return {"value": "map_race", "confidence": round(0.5 + 0.4 * geo["share"], 2), "top_n": top_n, "map": {"geojson": geo["file"], "key": geo["key"]},
                "reason": f"יש מפה ({geo['file']}) בתיקייה, ו-{geo['share']:.0%} מהישויות נמצאות בה (לפי '{geo['key']}')",
                "alternatives": [{"value": "bar_race", "reason": "מרוץ עמודות של אותן ישויות"}]}
    if layout == "dual":
        return {"value": "line_race", "confidence": 0.85, "top_n": top_n, "alternatives": [{"value": "small_multiples", "reason": "גרף נפרד לכל סדרה"}],
                "reason": "שתי סדרות ביחידות שונות - קווים עם ציר לכל אחת"}
    if layout == "small_multiples":
        return {"value": "small_multiples", "confidence": 0.8, "top_n": top_n, "alternatives": [],
                "reason": "כמה סדרות ביחידות שונות - גרף קטן לכל אחת"}
    if entities == 1:   # סדרה אחת לאורך זמן - קו, לא מרוץ של עמודה אחת
        return {"value": "line_race", "confidence": 0.85, "top_n": top_n, "alternatives": [{"value": "bar_race", "reason": "עמודה אחת"}],
                "reason": "סדרה אחת לאורך זמן - קו מראה את המגמה"}
    second = _second_measure(analysis, main)
    if second and entities > 3:
        return {"value": "scatter_race", "confidence": 0.65, "top_n": top_n,
                "reason": f"לאותן ישויות יש מדד שני ביחידה אחרת ({second}) - פיזור, כל ישות נקודה",
                "alternatives": [{"value": "bar_race", "reason": "מרוץ עמודות של המדד הראשון בלבד"}]}
    per_unit = unit.startswith(CURRENCIES) and bool(re.search(PER_UNIT_RE, f"{roles['value']['column']} {main['name']}".lower()))
    additive = not any(unit.startswith(u) for u in NON_ADDITIVE) and not per_unit
    evidence = _parts_evidence(folder, analysis, main, names)
    if (additive or evidence == "100%") and evidence and 2 <= entities <= 12:
        return {"value": "stacked_area_race", "confidence": 0.75, "top_n": top_n,
                "reason": f"{entities} חלקים של סך אחד ({evidence}) - שטח מוערם",
                "alternatives": [{"value": "pie_race", "reason": "עוגה - החלק של כל אחד מהסך"}, {"value": "bar_race", "reason": "מרוץ עמודות"}]}
    if kind == "level" and not additive and entities <= 25:
        return {"value": "line_race", "confidence": 0.75, "top_n": top_n,
                "reason": f"{entities} סדרות של {unit or 'ערך'} לאורך זמן - מצב שלא מתחבר, קווים מראים את המגמה",
                "alternatives": [{"value": "bar_race", "reason": "מרוץ עמודות - מי גבוה יותר בכל רגע"}]}
    return {"value": "bar_race", "confidence": 0.7 if entities > 8 else 0.55, "top_n": top_n,
            "reason": f"{entities} ישויות שמתחרות על המקום הראשון - מרוץ עמודות",
            "alternatives": [{"value": "line_race", "reason": "קווים - המגמה של כל אחת"}] + ([{"value": "bump_race", "reason": "מקומות בדירוג"}] if entities > 5 else [])}
