# dataviz/smart/story.py
#
# 20.10.2026: "מוצא הסיפור" - הרגעים החזקים בנתונים עצמם: החלפת המקום הראשון, שיאים, עקיפות בין המובילים, שבר במגמה
# ומספרים עגולים. מהם: סוג הסיפור (מהאשף הקיים: race / trend / compare / before_after), עצירות עם הסבר (story.pauses),
# הדגשות (story.callouts), וקטעי מהירות (story.speed - לאט סביב רגע חזק, מהר בקטע שקט). כל רגע עם התאריך, העובדה
# (מספרים מחושבים בלבד) וחוזק; הכל הצעה לטיוטה. קריאה בלבד.
import math
import os
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

MAX_PAUSES = 3
MAX_CALLOUTS = 4
MAX_MOMENTS = 8


def fmt(value: float) -> str:
    """מספר לטקסט: 1,234 / 12.5 / 1.2 מיליון."""
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f} מיליון".replace(".0 ", " ")
    if abs(value) >= 1000 or value == int(value):
        return f"{value:,.0f}"
    return f"{value:.1f}"


def matrix(folder: str, plan: Mapping[str, Any]) -> pd.DataFrame:
    """[תקופה x ישות]: לרמה - הערך האחרון בתקופה (ותקופות חסרות מושלמות קדימה), לכמות - הסכום המצטבר."""
    from dataviz.sources import read_table
    frames = []
    for spec in plan["sources"]:
        table = read_table(spec, folder)
        table["entity"] = table["entity"].astype(str)
        if spec.get("kind") == "level":
            frame = table.pivot_table(index="time", columns="entity", values="value", aggfunc="last").sort_index().ffill()
        else:
            frame = table.pivot_table(index="time", columns="entity", values="value", aggfunc="sum").sort_index().fillna(0.0).cumsum()
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    # sort=True במפורש: ב-pandas 4 ברירת המחדל לאיחוד DatetimeIndex משתנה ל-False (Pandas4Warning) - התקופות נשארות לפי הסדר
    result = pd.concat(frames, axis=1, sort=True).sort_index()
    return result.loc[:, ~result.columns.duplicated()].ffill()


def _day(t: Any) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%d")


def unit_parts(unit: Optional[Mapping[str, Any]]) -> tuple:
    """(תחילית, סיומת) לטקסט: $60,325 מיליון / 22.2°C / 46 מושבים."""
    unit = unit or {}
    label, scale = str(unit.get("label") or ""), str(unit.get("scale") or "")
    prefix, suffix = str(unit.get("prefix") or ""), str(unit.get("suffix") or "")
    if label and not prefix and not suffix:
        suffix = " " + label.split(" (")[0]
    return prefix, suffix + (f" {scale}" if scale else "")


def find_moments(m: pd.DataFrame, kind: str, unit: Optional[Mapping[str, Any]] = None, leads: bool = True) -> List[Dict[str, Any]]:
    """[{date, kind, text, strength, entity?}] - מהחזק לחלש. leads=False - סדרות ביחידות שונות (אין "מי מוביל")."""
    if m.empty or len(m) < 2:
        return []
    moments: List[Dict[str, Any]] = []
    prefix, suffix = unit_parts(unit)
    quiet = max(2, len(m) // 20)          # מוביל חדש נחשב רק אם הוא נשאר כמה תקופות (לא קפיצות הלוך-חזור)
    early = m.index[min(len(m) - 1, len(m) // 10)]
    live = m.loc[m.max(axis=1) > 0] if (m.fillna(0) >= 0).all().all() else m
    if leads and m.shape[1] > 1 and len(live) > 1:
        leaders = live.idxmax(axis=1)
        for i, (t, (prev, cur)) in enumerate(zip(leaders.index[1:], zip(leaders.values[:-1], leaders.values[1:]))):
            if prev != cur and (leaders.values[i + 1:i + 1 + quiet] == cur).all():
                moments.append({"date": _day(t), "kind": "lead", "entity": cur, "previous": prev, "strength": 3.0,
                                "text": f"{cur} עוקף את {prev} ועובר למקום הראשון ({prefix}{fmt(live.loc[t, cur])}{suffix})"})
        top = list(m.iloc[-1].sort_values(ascending=False).index[:5])
        lead_pairs = {(mo["entity"], mo["date"]) for mo in moments}
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                diff = (m[a] - m[b]).dropna()
                signs = diff.apply(lambda v: 1 if v > 0 else (-1 if v < 0 else 0))
                flips = signs[(signs != signs.shift()) & signs.shift().notna() & (signs != 0)]
                for t in flips.index[-1:]:
                    if t <= early:
                        continue   # בהתחלה כולם קרובים לאפס - עקיפה שם היא רעש
                    winner = a if signs[t] > 0 else b
                    loser = b if winner == a else a
                    if (winner, _day(t)) not in lead_pairs:
                        moments.append({"date": _day(t), "kind": "cross", "entity": winner, "strength": 1.5,
                                        "text": f"{winner} עוקף את {loser}"})
    # שיאים: בכמות - התקופה עם התוספת הגדולה ביותר; ברמה - השיא של המובילים (אם לא בסוף)
    if kind == "amount":
        flow = m.diff().fillna(m.iloc[0]).sum(axis=1)
        if len(flow) > 3:
            t = flow.idxmax()
            moments.append({"date": _day(t), "kind": "record", "strength": 2.5,
                            "text": f"השיא: {prefix}{fmt(flow[t])}{suffix} בתקופה אחת"})
    else:
        for entity in list(m.iloc[-1].sort_values(ascending=False).index[:3]):
            series = m[entity].dropna()
            if len(series) > 3 and series.idxmax() != series.index[-1]:
                t = series.idxmax()
                moments.append({"date": _day(t), "kind": "record", "entity": entity, "strength": 2.0,
                                "text": f"השיא של {entity}: {prefix}{fmt(series[t])}{suffix}"})
    if not leads:
        moments = [mo for mo in moments if mo["kind"] != "cross"]
    # שבר במגמה - בסך (כמות) או בממוצע (רמה)
    total = m.sum(axis=1) if kind == "amount" else m.mean(axis=1)
    slope = total.diff()
    window = max(2, len(total) // 6)
    if len(total) >= 3 * window:
        best: Optional[Dict[str, Any]] = None
        for i in range(window, len(total) - window):
            before, after = slope.iloc[i - window + 1:i + 1].mean(), slope.iloc[i + 1:i + 1 + window].mean()
            change = abs(after - before) / (abs(total).mean() / len(total) + 1e-9)
            if (best is None or change > best["change"]) and math.copysign(1, before) != math.copysign(1, after):
                best = {"change": change, "t": total.index[i], "up": after > before}
        if best:
            moments.append({"date": _day(best["t"]), "kind": "trend", "strength": 2.2,
                            "text": (f"המגמה של {m.columns[0]}" if m.shape[1] == 1 else "המגמה") + " מתהפכת - מכאן " + ("עלייה" if best["up"] else "ירידה")})
    # מספר עגול - הסך / המוביל חוצה 1, 2 או 5 כפול חזקה של 10
    watch = total if kind == "amount" else m[m.iloc[-1].idxmax()]
    crossed = None
    for t, (a, b) in zip(watch.index[1:], zip(watch.values[:-1], watch.values[1:])):
        for exp in range(1, 12):
            for base in (1, 2, 5):
                mark = base * 10 ** exp
                if a < mark <= b and mark >= max(abs(watch.iloc[0]) * 2, 10) and (crossed is None or mark >= crossed["mark"]):
                    crossed = {"mark": mark, "t": t}
    if crossed:
        what = "הסך" if kind == "amount" else str(m.iloc[-1].idxmax())
        moments.append({"date": _day(crossed["t"]), "kind": "round", "strength": 1.2 + (0.8 if str(crossed["mark"]).startswith("1") else 0),
                        "text": f"{what} חוצה את {prefix}{fmt(crossed['mark'])}{suffix}"})
    moments.sort(key=lambda mo: (-mo["strength"], mo["date"]))
    seen, unique = set(), []
    for mo in moments:
        if (mo["date"], mo["kind"]) not in seen:
            seen.add((mo["date"], mo["kind"]))
            unique.append(mo)
    return unique[:MAX_MOMENTS]


def story_type(moments: List[Dict[str, Any]], chart: str, entities: int) -> Dict[str, Any]:
    leads = sum(1 for m in moments if m["kind"] == "lead")
    trend = next((m for m in moments if m["kind"] == "trend"), None)
    if entities == 2 or chart == "line_race" and entities <= 2:
        return {"value": "compare", "confidence": 0.7, "reason": "שתי סדרות - זו מול זו"}
    if chart == "bar_race" and leads >= 1 and entities >= 4:
        return {"value": "race", "confidence": min(0.9, 0.6 + 0.1 * leads), "reason": f"{leads} החלפות במקום הראשון - מרוץ"}
    if trend and trend["strength"] >= 2 and leads == 0:
        return {"value": "before_after", "confidence": 0.6, "split": trend["date"], "reason": f"המגמה מתהפכת ב-{trend['date']} - לפני ואחרי"}
    return {"value": "trend", "confidence": 0.6, "reason": "סדרות לאורך זמן בלי מרוץ צמוד - מגמה"}


def speed_sections(moments: List[Dict[str, Any]], start: pd.Timestamp, end: pd.Timestamp) -> List[Dict[str, Any]]:
    """לאט (0.5) חודש-שנה סביב כל רגע חזק, מהר (2) בקטע השקט הארוך ביותר אם הוא יותר מרבע מהזמן."""
    span = max((end - start).days, 1)
    pad = pd.Timedelta(days=max(15, span // 40))
    sections: List[Dict[str, Any]] = []
    strong = sorted(m["date"] for m in moments if m["strength"] >= 2.5)[:3]
    for date in strong:
        t = pd.Timestamp(date)
        a, b = max(start, t - pad), min(end, t + pad)
        if sections and a <= pd.Timestamp(sections[-1]["end"]):
            sections[-1]["end"] = _day(max(b, pd.Timestamp(sections[-1]["end"])))   # רגעים קרובים - קטע איטי אחד
        elif b > a:
            sections.append({"start": _day(a), "end": _day(b), "speed": 0.5})
    marks = [start] + sorted(pd.Timestamp(m["date"]) for m in moments) + [end]
    gaps = [(b - a, a, b) for a, b in zip(marks[:-1], marks[1:])]
    if gaps:
        gap, a, b = max(gaps)
        if gap.days > span / 4:
            a, b = a + pad, b - pad
            if b > a and not any(pd.Timestamp(s["start"]) < b and pd.Timestamp(s["end"]) > a for s in sections):
                sections.append({"start": _day(a), "end": _day(b), "speed": 2.0})
    return sorted(sections, key=lambda s: s["start"])


def find_story(folder: str, analysis: Mapping[str, Any]) -> Dict[str, Any]:
    """{moments, type, pauses, callouts, speed} - הכל הצעה לטיוטה."""
    plan = analysis.get("plan")
    if not plan:
        return {"moments": [], "type": None, "pauses": [], "callouts": [], "speed": []}
    main = analysis["series"][0]["roles"]
    kind = (main.get("kind") or {}).get("value", "amount")
    try:
        m = matrix(os.path.abspath(folder), plan)
        if plan.get("layout") in ("dual", "small_multiples"):   # יחידות שונות - הרגעים של כל סדרה לבד, ביחידות שלה
            moments = []
            for f, spec in zip(analysis["series"], plan["sources"]):
                part = matrix(os.path.abspath(folder), {"sources": [spec]})
                moments += find_moments(part, (f["roles"].get("kind") or {}).get("value", "amount"), f["roles"].get("unit"), leads=False)
            moments.sort(key=lambda mo: (-mo["strength"], mo["date"]))
            moments = moments[:MAX_MOMENTS]
        else:
            moments = find_moments(m, kind, main.get("unit"))
    except (KeyError, ValueError, OSError):
        return {"moments": [], "type": None, "pauses": [], "callouts": [], "speed": []}
    chart = (analysis.get("chart") or {}).get("value", "bar_race")
    kind_of = story_type(moments, chart, m.shape[1])
    by_date = sorted(moments[:MAX_PAUSES], key=lambda mo: mo["date"])
    pauses = [{"date": mo["date"], "text": mo["text"]} for mo in by_date]
    callouts = [{"date": mo["date"], "entity": mo["entity"], "text": mo["text"]}
                for mo in sorted(moments, key=lambda mo: mo["date"]) if mo.get("entity") and mo["kind"] in ("lead", "record")][:MAX_CALLOUTS]
    speed = speed_sections(moments, m.index.min(), m.index.max()) if len(m) else []
    single = plan.get("layout") in ("dual", "small_multiples") or m.shape[1] < 2
    first = m.loc[m.max(axis=1) > 0].iloc[0] if len(m) and (m.max(axis=1) > 0).any() else None
    return {"moments": moments, "type": kind_of, "pauses": pauses, "callouts": callouts, "speed": speed,
            "start": _day(m.index.min()) if len(m) else None, "end": _day(m.index.max()) if len(m) else None,
            "leader_start": None if single or first is None else str(first.idxmax()),
            "leader_end": None if single or not len(m) else str(m.iloc[-1].idxmax())}
