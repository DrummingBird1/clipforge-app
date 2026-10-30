# dataviz/smart/relations.py
#
# 20.10.2026: איך קבצי הסדרות של פרק משתלבים - מקור (sources) לכל קובץ עם הזמן, הישות, הערך וסוג הערך שזוהו; קבצים עם
# אותן ישויות ואותן יחידות - יחד; יחידות שונות - שני צירים (שתי סדרות) או גרפים קטנים (יותר); רמה עם תקופות חסרות -
# השלמה (מדרגות לבחירות ולמחירים שמתעדכנים מדי פעם, קו ישר לשאר). כל החלטה עם סיבה וביטחון.
from typing import Any, Dict, List

import pandas as pd

from dataviz.smart import columns as cols

STEP_WORDS = ("election", "seats", "knesset", "vote", "price", "בחירות", "מושבים", "מחיר")


def _spec(f: Dict[str, Any]) -> Dict[str, Any]:
    roles = f["roles"]
    spec: Dict[str, Any] = {"path": f["name"], "time": {"column": roles["time"]["column"], "period": roles["time"]["period"]},
                            "value": {"column": roles["value"]["column"]}}
    entity = roles["entity"]
    if entity and entity.get("unique", 0) > 1:
        spec["entity"] = {"column": entity["column"]}
    elif entity and entity.get("names"):
        spec["entity"] = str(entity["names"][0])          # קובץ של סדרה אחת - השם שלה
    else:
        spec["entity"] = f["name"].rsplit(".", 1)[0]
    if (roles.get("kind") or {}).get("value") == "level":
        spec["kind"] = "level"
    if roles.get("wide"):
        spec["wide"] = True
    for key, value in (roles.get("read") or {}).items():   # מפריד / נקודה עשרונית / שורת כותרת / records ב-JSON
        if value not in (None, "", [], {}) and key != "units":
            spec[key] = value
    if roles.get("entity_columns"):
        spec["entity_columns"] = True
    if entity and entity.get("totals"):
        spec["exclude_entities"] = list(entity["totals"])   # שורת סך - לא ישות
    return spec


def _gaps(df: pd.DataFrame, f: Dict[str, Any]) -> float:
    """כמה מהתקופות בין הראשונה לאחרונה חסרות (0-1) - לפי הישות החציונית."""
    roles = f["roles"]
    times = cols.parse_times(df[roles["time"]["column"]])
    period = {"year": "YS", "month": "MS", "quarter": "QS"}.get(roles["time"]["period"])
    if period is None or times.dropna().empty:
        return 0.0
    keys = df[roles["entity"]["column"]].astype(str) if roles["entity"] and roles["entity"].get("unique", 0) > 1 else pd.Series("all", index=df.index)
    shares = []
    for _name, group in pd.DataFrame({"t": times, "e": keys}).dropna().groupby("e"):
        present = group["t"].dt.to_period(period[0]).nunique()
        expected = len(pd.period_range(group["t"].min(), group["t"].max(), freq=period[0]))
        shares.append(1 - present / max(expected, 1))
    return float(pd.Series(shares).median()) if shares else 0.0


def plan(folder: str, series: List[Dict[str, Any]]) -> Dict[str, Any]:
    """{sources, y_axes?, layout: single/merge/dual/small_multiples, decisions: [{what, value, reason, confidence}]}."""
    from dataviz.smart.scan import load_table
    sources = []
    decisions: List[Dict[str, Any]] = []
    for f in series:
        spec = _spec(f)
        df = load_table(folder, f["name"])
        if spec.get("kind") == "level" and df is not None:
            gaps = _gaps(df, f)
            irregular = spec["time"]["period"] == "day" and len(df) > 2
            if gaps > 0.2 or irregular:
                words = f"{f['name']} {spec['value']['column']}".lower()
                spec["fill"] = "step" if any(w in words for w in STEP_WORDS) or irregular else "linear"
                decisions.append({"what": f"fill:{f['name']}", "value": spec["fill"], "confidence": 0.7,
                                  "reason": (f"{gaps:.0%} מהתקופות חסרות" if gaps > 0.2 else "תאריכים לא סדירים (בחירות / עדכונים)")
                                  + (" - הערך נשאר עד העדכון הבא (מדרגות)" if spec["fill"] == "step" else " - קו ישר בין המדידות")})
        sources.append(spec)
    units = [str((f["roles"]["unit"] or {}).get("label") or "") for f in series]
    result: Dict[str, Any] = {"sources": sources, "layout": "single", "decisions": decisions}
    if len(series) > 1:
        distinct = sorted(set(units))
        if len(distinct) == 1:
            result["layout"] = "merge"
            decisions.append({"what": "layout", "value": "merge", "confidence": 0.8,
                              "reason": f"{len(series)} קבצים באותן יחידות ({distinct[0] or 'בלי יחידה'}) - באותו גרף"})
        elif len(series) == 2:
            result["layout"] = "dual"
            sources[1]["axis"] = "right"
            result["y_axes"] = {"left": {"label": units[0]}, "right": {"label": units[1]}}
            decisions.append({"what": "layout", "value": "dual", "confidence": 0.75,
                              "reason": f"שתי סדרות ביחידות שונות ({units[0]} / {units[1]}) - ציר לכל אחת"})
        else:
            result["layout"] = "small_multiples"
            decisions.append({"what": "layout", "value": "small_multiples", "confidence": 0.7,
                              "reason": f"{len(series)} סדרות ב-{len(distinct)} יחידות שונות - גרף קטן לכל אחת"})
    return result
