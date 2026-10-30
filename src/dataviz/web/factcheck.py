# dataviz/web/factcheck.py
#
# 20.10.2026: בדיקת עובדות לפני רינדור - המספרים שיופיעו על המסך (בנקודות מפתח לאורך הזמן, בתיבת הסיום ובהתראות השיא)
# ליד שורות המקור שמהן הם באו, וסימון כשהם לא מתאימים. לקריאה בלבד: שום קובץ לא נכתב.
# "צפוי" = מהקבצים עצמם: בכמות - סכום הערכים של הישות עד סוף התקופה; ברמה - הערך של התקופה האחרונה שהסתיימה.
# "על המסך" = המצטבר של הפרק באותו יום, בפורמט של הסרטון. שינויים מכוונים (שם חלופי, תיקון קפיצה, לנפש, חלון מתגלגל,
# השלמה) משנים מספרים - הם מופיעים ברשימת ההשפעות, וההשוואה של ישות שהם נוגעים בה מסומנת "לא בר-השוואה".
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

MAX_KEY_DATES = 24
MAX_SOURCE_ROWS = 3


def _key_dates(dates: pd.DatetimeIndex) -> List[pd.Timestamp]:
    """סוף כל שנה בטווח, ועוד היום האחרון - עד MAX_KEY_DATES, מפוזרים שווה."""
    ends = [d for d in dates if d.month == 12 and d.day == 31]
    if not ends or ends[-1] != dates[-1]:
        ends.append(dates[-1])
    if len(ends) > MAX_KEY_DATES:
        picks = np.linspace(0, len(ends) - 1, MAX_KEY_DATES).round().astype(int)
        ends = [ends[i] for i in sorted(set(picks))]
    return ends


def _transforms(cfg: Mapping[str, Any], specs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """מה בהגדרות משנה מספרים בכוונה (ישות -> סיבה; '*' = כולן)."""
    items: List[Dict[str, Any]] = []
    entities = cfg.get("entities") or {}
    for raw, alias in (entities.get("aliases") or {}).items():
        items.append({"entity": str(alias), "reason": f"שם חלופי: {raw} -> {alias}"})
    for name in entities.get("exclude") or []:
        items.append({"entity": str(name), "reason": "מוחרגת"})
    for fix in (cfg.get("data") or {}).get("fixes") or []:
        items.append({"entity": str(fix.get("entity")), "reason": f"תיקון ({fix.get('method')}) ב-{fix.get('date')}"})
    values = cfg.get("values") or {}
    if values.get("mode") == "rolling":
        items.append({"entity": "*", "reason": f"חלון מתגלגל ({values.get('window_days')} ימים)"})
    if (values.get("per_capita") or {}).get("enabled"):
        items.append({"entity": "*", "reason": "לנפש"})
    for spec in specs:
        if spec.get("fill") in ("step", "linear"):
            items.append({"entity": "*", "reason": f"השלמה ({spec['fill']}) במקור {os.path.basename(str(spec.get('path') or ''))}"})
    return items


def fact_check(folder: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    from dataviz.web.preview import _lock
    with _lock:   # matplotlib נטען בפעם הראשונה רק בתוך המנעול של התצוגה - שני threads שמייבאים אותו יחד נתקעים (_DeadlockError)
        from dataviz.charts.base import format_number
        from dataviz.render import numbers_context
    from dataviz.episode import load_episode
    from dataviz.plan import build_plan
    from dataviz.sources import read_table, resolved_sources
    episode = load_episode(folder, dict(overrides))
    cfg = episode.config
    specs = resolved_sources(cfg)
    numbers = numbers_context(cfg, episode)
    fmt = lambda v: format_number(float(v), numbers)  # noqa: E731
    tables = []
    for spec in specs:
        table = read_table(spec, cfg["base_dir"])
        from dataviz.sources.spread import period_days
        table["end"] = [period_days(t, p)[-1] for t, p in zip(table["time"], table["period"])]
        table["kind"] = spec.get("kind") or "amount"
        table["source"] = os.path.basename(str(spec.get("path") or spec.get("url") or ""))
        tables.append(table)
    rows_all = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame(columns=["time", "entity", "value", "end", "kind", "source"])
    rows_all["entity"] = [e.item() if hasattr(e, "item") else e for e in rows_all["entity"]]
    transforms = _transforms(cfg, specs)
    touched = {t["entity"] for t in transforms}

    def expected(entity: Any, day: pd.Timestamp) -> Dict[str, Any]:
        rows = rows_all[(rows_all["entity"] == entity) & (rows_all["end"] <= day)].sort_values("end")
        if not len(rows):
            return {"value": None, "rows": []}
        kind = rows["kind"].iloc[-1]
        if kind == "level":
            last = rows[rows["end"] == rows["end"].iloc[-1]]
            value = float(last["value"].mean())
        else:
            value = float(rows["value"].sum())
        sample = [{"time": pd.Timestamp(r.time).strftime("%Y-%m-%d"), "value": float(r.value), "source": r.source}
                  for r in rows.tail(MAX_SOURCE_ROWS).itertuples()]
        return {"value": value, "rows": sample}

    def check(entity: Any, day: pd.Timestamp, shown: float) -> Dict[str, Any]:
        exp = expected(entity, day)
        comparable = "*" not in touched and str(entity) not in touched and exp["value"] is not None
        ok: Optional[bool] = (fmt(shown) == fmt(exp["value"])) if comparable else None
        return {"date": day.strftime("%Y-%m-%d"), "entity": str(entity), "shown": fmt(shown), "expected": fmt(exp["value"]) if exp["value"] is not None else "",
                "ok": ok, "source_rows": exp["rows"]}

    index = {e: i for i, e in enumerate(episode.entities)}
    key_rows = []
    for day in _key_dates(episode.dates):
        di = episode.dates.get_loc(day)
        for entity, col in index.items():
            if episode.start_idx[col] <= di:
                key_rows.append(check(entity, day, float(episode.cum[di, col])))
    plan = build_plan(episode, "full")
    outro = [f for f in plan if f["k"] == "outro"]
    end_box = [check(e, episode.dates[-1], float(v)) for e, v in (outro[-1]["top"] if outro else [])]
    records = []
    previous = None
    for frame in plan:
        toast = frame.get("toast")
        text = toast[0] if toast else None
        if text and text != previous and frame["k"] == "main" and frame["bars"]:
            leader, value, _p = frame["bars"][0]
            day = episode.dates[min(int(frame["x"]), len(episode.dates) - 1)]
            records.append({**check(leader, day, float(value)), "text": text})
        previous = text
    every = key_rows + end_box + records
    return {"key_frames": key_rows, "end_box": end_box, "records": records, "transforms": transforms,
            "checked": sum(1 for r in every if r["ok"] is not None), "mismatches": sum(1 for r in every if r["ok"] is False)}
