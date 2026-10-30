# dataviz/smart/clean.py
#
# 20.10.2026: ניקוי אוטומטי לטיוטה - על הטבלה של כל סדרה, עם ההצעות הקיימות של dataviz/cleaning.py. מה שבטוח מוחל
# (שמות שזהים אחרי ניקוי כתיב - "תל-אביב" / "תל אביב" - מתמזגים ב-entities.aliases), ומה שלא בטוח רק מוצע לאישור
# (שמות דומים, קפיצה חשודה, שורות כפולות, ערכים שליליים בכמות, ערכים חסרים). קבצי הנתונים לא משתנים.
from typing import Any, Dict, List

import pandas as pd

from dataviz.cleaning import find_outliers, similar_names
from dataviz.smart import columns as cols
from dataviz.smart.scan import load_table


def clean(folder: str, series: List[Dict[str, Any]]) -> Dict[str, Any]:
    """{aliases: {שם: שם}, fixed: [{what, detail}], suggestions: [{what, detail, needs_approval: True}]}."""
    aliases: Dict[str, str] = {}
    fixed: List[Dict[str, Any]] = []
    suggestions: List[Dict[str, Any]] = []
    for f in series:
        roles = f["roles"]
        df = load_table(folder, f["name"])
        if df is None:
            continue
        df = df[cols.parse_times(df[roles["time"]["column"]]).notna()]   # שורת סך בלי שנה - לא נתון
        value = pd.to_numeric(df[roles["value"]["column"]], errors="coerce")
        missing = int(value.isna().sum())
        if missing:
            suggestions.append({"what": "missing", "file": f["name"], "needs_approval": True,
                                "detail": f"{missing} ערכים חסרים ב-'{roles['value']['column']}' - נספרים כאפס / מושלמים"})
        entity = roles["entity"]["column"] if roles["entity"] and roles["entity"].get("unique", 0) > 1 else None
        keys = [roles["time"]["column"]] + ([entity] if entity else [])
        duplicates = int(df.duplicated(subset=keys).sum())
        if duplicates:
            suggestions.append({"what": "duplicates", "file": f["name"], "needs_approval": True,
                                "detail": f"{duplicates} שורות כפולות (אותו זמן" + (" ואותה ישות" if entity else "") + ") - בכמות הן מתחברות"})
        if (roles.get("kind") or {}).get("value") == "amount" and int((value < 0).sum()):
            suggestions.append({"what": "negative", "file": f["name"], "needs_approval": True,
                                "detail": f"{int((value < 0).sum())} ערכים שליליים בסדרה של כמויות"})
        if not entity:
            continue
        # קפיצה חשודה - בכמויות בלבד (ברמה קפיצה היא שינוי אמיתי), ובנתונים חודשיים / יומיים (בשנתי עם הפסקות - כמו
        # מדליות רק בשנות אולימפיאדה - "הרגיל" הוא אפס וכל ערך נראה קפיצה)
        if (roles.get("kind") or {}).get("value") == "amount" and roles["time"]["period"] in ("day", "month"):
            times = cols.parse_times(df[roles["time"]["column"]])
            matrix = pd.DataFrame({"t": times, "e": df[entity].astype(str), "v": value}).dropna().pivot_table(
                index="t", columns="e", values="v", aggfunc="sum").fillna(0.0)
            for outlier in find_outliers(matrix, limit=5):
                suggestions.append({"what": "outlier", "file": f["name"], "needs_approval": True, "outlier": outlier,
                                    "detail": f"קפיצה חשודה: {outlier['entity']} ב-{outlier['date']} - פי {outlier['ratio']:.0f} מהרגיל"})
        totals = {k: v for k, v in value.abs().groupby(df[entity].astype(str)).sum().to_dict().items() if not cols.is_total_name(k)}
        together = df.groupby(df[roles["time"]["column"]].astype(str))[entity].apply(lambda s: set(s.astype(str)))
        for group in similar_names(totals, aliases):
            if group["reason"] != "same" and any(len(set(group["names"]) & names) > 1 for names in together):
                continue   # מופיעים יחד באותה תקופה - שתי ישויות שונות (אוסטריה / אוסטרליה)
            if group["reason"] == "same":
                for name in group["names"][1:]:
                    aliases[name] = group["target"]
                fixed.append({"what": "merge_names", "file": f["name"],
                              "detail": f"מוזגו שמות זהים בכתיב שונה: {', '.join(group['names'])} -> {group['target']}"})
            else:
                suggestions.append({"what": "similar_names", "file": f["name"], "needs_approval": True, "names": group["names"],
                                    "detail": f"שמות דומים - אולי אותה ישות: {', '.join(group['names'][:4])}"})
    return {"aliases": aliases, "fixed": fixed, "suggestions": suggestions}
