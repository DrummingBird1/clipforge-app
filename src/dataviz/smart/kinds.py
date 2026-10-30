# dataviz/smart/kinds.py
#
# 20.10.2026: כמות או רמה. כמות (amount) - כל שורה מוסיפה, והסרטון מצטבר (עולים, מדליות, יצוא בשנה); רמה (level) - כל
# ערך הוא המצב באותו זמן ולא מחברים (טמפרטורה, מחיר, מדד, אוכלוסייה, מושבים, צי רכב). לפי היחידות, המילים בשם העמודה
# והקובץ, ואיך הערכים מתנהגים (רמה משתנה מעט ביחס לגודלה; סדרה שרק עולה - כבר מצטברת). ביטחון וסיבה.
import re
from typing import Any, Dict, Mapping, Optional

import pandas as pd

# מטבע לבד לא אומר רמה (מכירות, יצוא - כמויות); מחיר / לנפש כן - לפי המילים
LEVEL_UNITS = ("°C", "%", "נקודות מדד", "שנים", "מטר", "MW", "GW", "kW")
LEVEL_WORDS = r"level|index|price|rate|temperature|expectancy|population|seats|fleet|stock|balance|per_capita|average|avg|mean|ratio|share|מדד|מחיר|מפלס|אוכלוסי|ממוצע|שיעור"
AMOUNT_WORDS = (r"immigrants|arrivals|deaths|births|medals|exports|imports|sales|revenue|rain|alarms|events|cases|count|new_|_new|"
                r"per_games|added|consumption|production|generation|עולים|מדליות|יצוא|התרעות|מקרים|מכירות|הכנסות|משקעים|גשם|צריכה|ייצור|הפקה")
# אנרגיה (GWh...) - כמות שנצרכה / הופקה בתקופה; הספק (MW) - רמה
ENERGY_UNITS = ("TWh", "GWh", "MWh", "kWh")


def guess_kind(column: str, file_name: str = "", unit: Optional[Mapping[str, Any]] = None, df: Optional[pd.DataFrame] = None,
               time: Optional[str] = None, entity: Optional[str] = None) -> Dict[str, Any]:
    """{value: amount/level, confidence, reason}."""
    text = f"{column} {file_name}".lower()
    level = amount = 0.0
    reasons = []
    unit_label = str((unit or {}).get("label") or "")
    if unit_label.startswith(ENERGY_UNITS):
        amount += 1.5
        reasons.append(f"{unit_label} - אנרגיה שנצרכה / הופקה בתקופה")
    elif any(unit_label.startswith(u) for u in LEVEL_UNITS) and "מיליון" not in unit_label:
        level += 1.5
        reasons.append(f"היחידה {unit_label} היא מצב ולא תוספת")
    level_word, amount_word = re.search(LEVEL_WORDS, text), re.search(AMOUNT_WORDS, text)
    if level_word:
        level += 2
        reasons.append(f"'{level_word.group(0)}' בשם")
    if amount_word:
        amount += 2.5
        reasons.append(f"'{amount_word.group(0)}' בשם - דברים שקורים ונספרים")
    if "levels" in file_name.lower() or "_level" in file_name.lower():
        level += 1
    behavior = _behavior(df, time, entity, column) if df is not None and time else None
    if behavior:
        if behavior["monotonic"] > 0.95 and behavior["entities"] > 1:
            level += 1.5
            reasons.append("כל הסדרות רק עולות - כבר מצטבר")
        elif behavior["change"] < 0.12:
            level += 1
            reasons.append(f"הערך משתנה בממוצע {behavior['change']:.0%} בין תקופות - מצב יציב")
        elif behavior["change"] > 0.5:
            amount += 1
            reasons.append(f"הערך קופץ בממוצע {behavior['change']:.0%} בין תקופות - כמויות")
    kind = "level" if level > amount else "amount"
    margin = abs(level - amount)
    confidence = round(min(0.95, 0.5 + 0.1 * margin), 2) if (level or amount) else 0.4
    return {"value": kind, "confidence": confidence,
            "reason": ("; ".join(reasons) if reasons else "בלי סימן ברור - ברירת המחדל כמות") + (" - רמה" if kind == "level" else " - כמות")}


def _behavior(df: pd.DataFrame, time: str, entity: Optional[str], column: str) -> Optional[Dict[str, float]]:
    from dataviz.smart.columns import parse_times
    values = pd.to_numeric(df[column], errors="coerce")
    # ב20: לפי הזמן עצמו - מיון כטקסט שם 02/01/2020 אחרי 01/12/2020, וסדרה שכבר מצטברת נראתה כמו כמויות (ונצברה פעמיים)
    frame = pd.DataFrame({"t": parse_times(df[time].astype(str)), "e": df[entity].astype(str) if entity else "all", "v": values}).dropna()
    if frame.empty:
        return None
    changes, monotonic = [], []
    for _name, group in frame.sort_values("t").groupby("e"):
        v = group["v"].to_numpy()
        if len(v) < 3:
            continue
        scale = max(float(abs(v).mean()), 1e-9)
        changes.append(float(abs(pd.Series(v).diff().dropna()).mean()) / scale)
        monotonic.append(float((pd.Series(v).diff().dropna() >= 0).mean()))
    if not changes:
        return None
    return {"change": float(pd.Series(changes).median()), "monotonic": float(pd.Series(monotonic).mean()), "entities": float(len(changes))}
