# dataviz/cleaning.py
#
# גל 52: ניקוי נתונים - שמות דומים של אותה ישות (כתיב שונה: אותיות סופיות, יי/וו, מקפים, גרשיים) כהצעות מיזוג,
# קפיצות חשודות ביום אחד (הרבה מעל הרגיל של אותה ישות - בדרך כלל דיווח מצטבר שנזרק ליום אחד) עם תיקון, ותיקונים
# שנשמרו בהגדרות (data.fixes) שמוחלים על המטריצה היומית לפני הכל. הכל על המטריצה - קבצי הנתונים לא משתנים.

import difflib
import re
from typing import Any, Dict, List, Mapping, Sequence

import numpy as np
import pandas as pd

FIX_ACTIONS = ("spread", "smooth", "set")
OUTLIER_WINDOW = 15            # ימים סביב היום שבודקים מולם ("הרגיל")
OUTLIER_FACTOR = 6.0           # פי כמה מהרגיל זה "חשוד"
OUTLIER_MIN_SHARE = 0.05       # ולפחות 5% מכל הסכום של הישות - קפיצה זניחה לא מעניינת
SIMILAR_RATIO = 0.86
MAX_SIMILAR_ENTITIES = 400     # מעבר לזה רק זהים אחרי ניקוי (השוואת כל הזוגות איטית)
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def name_key(name: Any) -> str:
    """השם בלי ההבדלים שלא משנים את המשמעות: אותיות קטנות, אותיות סופיות, סימנים, אותיות כפולות ורווחים."""
    text = str(name).casefold().translate(_FINALS)
    text = re.sub(r"[\"'׳״`\-_.,()\[\]/\\]", " ", text)
    text = re.sub(r"(.)\1+", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def similar_names(totals: Mapping[str, float], aliases: Mapping[str, str] | None = None) -> List[Dict[str, Any]]:
    """קבוצות של שמות שכנראה אותה ישות: [{names, target, reason}] - target = השם עם הסכום הגדול (הוא נשאר).
    שמות שכבר ממוזגים לאותו שם חלופי לא מוצעים שוב; מספרים (שנים) לא נבדקים."""
    aliases = dict(aliases or {})
    names = [n for n in totals if not str(n).lstrip("-").isdigit()]
    keys = {n: name_key(n) for n in names}
    parent = {n: n for n in names}

    def find(n: str) -> str:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    by_key: Dict[str, List[str]] = {}
    for n in names:
        by_key.setdefault(keys[n], []).append(n)
    for group in by_key.values():
        for other in group[1:]:
            parent[find(other)] = find(group[0])
    if len(names) <= MAX_SIMILAR_ENTITIES:
        unique = sorted(by_key)
        for i, a in enumerate(unique):
            for b in unique[i + 1:]:
                if min(len(a), len(b)) < 4:
                    continue
                matcher = difflib.SequenceMatcher(None, a, b)
                if matcher.real_quick_ratio() >= SIMILAR_RATIO and matcher.ratio() >= SIMILAR_RATIO:
                    ra, rb = find(by_key[a][0]), find(by_key[b][0])
                    if ra != rb:
                        parent[rb] = ra
    groups: Dict[str, List[str]] = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    result: List[Dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        resolved = {aliases.get(m, m) for m in members}
        if len(resolved) < 2:
            continue    # כבר ממוזגים
        members.sort(key=lambda m: -float(totals.get(m, 0)))
        same = len({keys[m] for m in members}) == 1   # זהים אחרי ניקוי, או רק דומים
        result.append({"names": members, "target": members[0], "reason": "same" if same else "similar",
                       "totals": {m: float(totals.get(m, 0)) for m in members}})
    result.sort(key=lambda g: -sum(g["totals"].values()))
    return result


def _typical(series: pd.Series, at: int) -> float:
    """הערך הרגיל של הישות סביב יום at - חציון הימים שסביבו, בלי היום עצמו."""
    lo, hi = max(0, at - OUTLIER_WINDOW), min(len(series), at + OUTLIER_WINDOW + 1)
    around = np.concatenate([series.to_numpy()[lo:at], series.to_numpy()[at + 1:hi]])
    return float(np.median(around)) if len(around) else 0.0


def find_outliers(matrix: pd.DataFrame, limit: int = 30, levels: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    """קפיצות חשודות: יום שבו ישות קיבלה פי OUTLIER_FACTOR מהרגיל שלה ולפחות OUTLIER_MIN_SHARE מכל הסכום שלה.
    23.10.2026: בלי ישויות-רמה (levels) - ביום הראשון שלהן ה"תוספת" היא כל הרמה, וכל רמה סומנה כקפיצה (ו"פיזור" שלה
    המציא עלייה לפני תחילת הנתונים)."""
    found = []
    skip = {str(e) for e in levels}
    for entity in matrix.columns:
        if str(entity) in skip:
            continue
        series = matrix[entity].astype(float)
        total = float(series.sum())
        if total <= 0:
            continue
        candidates = np.flatnonzero((series.to_numpy() >= OUTLIER_MIN_SHARE * total) & (series.to_numpy() > 0))
        for at in candidates:
            value = float(series.iloc[at])
            typical = _typical(series, int(at))
            if value > max(OUTLIER_FACTOR * typical, typical + 1):
                found.append({"entity": str(entity.item() if hasattr(entity, "item") else entity), "date": matrix.index[at].strftime("%Y-%m-%d"),
                              "value": value, "typical": typical, "ratio": value / max(typical, 1.0)})
    found.sort(key=lambda o: -o["ratio"])
    return found[:limit]


def apply_fixes(matrix: pd.DataFrame, fixes: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    """התיקונים שנשמרו: spread - מה שמעל הרגיל מתפזר על days הימים שלפני (הסכום נשמר); smooth - היום מקבל את
    הערך הרגיל (הסכום קטן); set - ערך שנקבע ידנית. ישות לפי השם כטקסט; תאריך מחוץ לטווח - בלי שינוי."""
    if not fixes:
        return matrix
    result = matrix.astype(float).copy()
    columns = {str(c): c for c in result.columns}
    for fix in fixes:
        column = columns.get(str(fix.get("entity")))
        date = pd.Timestamp(str(fix.get("date"))).normalize()
        if column is None or date not in result.index:
            continue
        at = int(result.index.get_loc(date))
        series = result[column]
        value = float(series.iloc[at])
        typical = _typical(series, at)
        action = fix.get("action", "spread")
        if action == "set":
            result.iloc[at, result.columns.get_loc(column)] = float(fix.get("value") or 0.0)
        elif action == "smooth":
            result.iloc[at, result.columns.get_loc(column)] = typical
        else:
            days = max(1, int(fix.get("days") or 30))
            start = max(0, at - days)
            span = at - start
            if span <= 0:
                continue
            excess = max(value - typical, 0.0)
            col = result.columns.get_loc(column)
            result.iloc[at, col] = value - excess
            result.iloc[start:at, col] = result.iloc[start:at, col].to_numpy() + excess / span
    return result
