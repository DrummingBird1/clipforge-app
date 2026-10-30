# dataviz/smart/columns.py
#
# 20.10.2026: מה כל עמודה בטבלה - זמן (ובאיזו רזולוציה), ישות, או ערך - ובאילו יחידות. כל בחירה עם ביטחון (0-1) וסיבה
# בעברית, כדי שהטיוטה תסביר את עצמה ("🤖 בחרתי 'year' כי..."). רק קריאה של הטבלה; כלום לא נכתב.
import re
import warnings
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

Choice = Dict[str, Any]

TIME_WORDS = {"date": 3, "תאריך": 3, "year": 3, "שנה": 3, "month": 3, "חודש": 3, "time": 2, "period": 2, "quarter": 2,
              "day": 2, "יום": 2, "week": 2, "when": 1}
ENTITY_WORDS = {"entity": 4, "name": 2, "שם": 2, "country": 2, "מדינה": 2, "party": 2, "מפלגה": 2, "city": 2, "עיר": 2,
                "product": 2, "מוצר": 2, "region": 2, "district": 2, "מחוז": 2, "type": 1, "category": 1, "item": 1,
                "branch": 1, "origin": 1, "continent": 1, "יבשת": 1, "group": 1}
# עמודות שהן מזהה / קוד / תוספת - לא ערך ולא ישות לתצוגה
ID_WORDS = ("_id", "id", "iso", "iso3", "noc", "code", "series_id", "edition_id", "knesset")
META_WORDS = ("points", "valid_days", "days", "note", "notes", "base", "station", "source", "article", "url", "first_point",
              "last_point", "ref_date", "since", "diff", "pct_change", "monthly_pct", "check")
VALUE_WORDS = ("value", "total", "count", "price", "population", "seats", "immigrants", "exports", "medals", "vehicles",
               "index", "level", "gdp", "expectancy", "temperature", "amount", "sum", "spend", "per_capita", "cost",
               "שווי", "ערך", "מחיר", "כמות", "סך", "הוצאה")

# יחידה לפי מילים בשם העמודה / בשם הישות / ב-SOURCES.md. (תבנית, תווית, תחילית, סיומת, קנה מידה)
UNIT_RULES = [
    (r"usd|us\$|dollar|\$", "$", "$", "", ""),
    (r"\bnis\b|_nis|shekel|ש\"?ח|₪|ils", "₪", "₪", "", ""),
    (r"(^|[^a-z])eur(o|os)?([^a-z]|$)|€|אירו", "€", "€", "", ""),
    (r"°c|celsius|מעלות|temperature|טמפרטורה", "°C", "", "°C", ""),
    (r"pct|percent|%|אחוז", "%", "", "%", ""),
    (r"per_?100_?k|per_?100,?000|ל-?100 אלף|ל-?100,000", "ל-100 אלף", "", " ל-100 אלף", ""),
    (r"per_?1_?k\b|per_?1,?000\b|ל-?1,?000", "ל-1,000", "", " ל-1,000", ""),
    (r"(^|[^a-z])twh([^a-z]|$)", "TWh", "", " TWh", ""),
    (r"(^|[^a-z])gwh([^a-z]|$)", "GWh", "", " GWh", ""),
    (r"(^|[^a-z])mwh([^a-z]|$)", "MWh", "", " MWh", ""),
    (r"(^|[^a-z])kwh([^a-z]|$)", "kWh", "", " kWh", ""),
    (r"(^|[^a-z])(gw|gigawatt)([^a-z]|$)|גיגה.?וו?אט", "GW", "", " GW", ""),
    (r"(^|[^a-z])(mw|megawatt)([^a-z]|$)|מגה.?וו?אט", "MW", "", " MW", ""),
    (r"(^|[^a-z])(kw|kilowatt)([^a-z]|$)|קילו.?וו?אט", "kW", "", " kW", ""),
    (r"מ\"מ|(^|[^a-z])mm([^a-z]|$)|millimet|מילימטר", "מ\"מ", "", " מ\"מ", ""),
    (r"life_expectancy|expectancy|תוחלת", "שנים", "", " שנים", ""),
    (r"meter|מטר|מפלס|(level|height|depth)_m\b", "מטר", "", " מ'", ""),
    (r"index|מדד", "נקודות מדד", "", "", ""),
    (r"population|אוכלוסי|תושבים", "תושבים", "", "", ""),
    (r"immigrants|עולים", "עולים", "", "", ""),
    (r"seats|מושבים", "מושבים", "", "", ""),
    (r"medal|מדלי", "מדליות", "", "", ""),
    (r"vehicles|(^|[^a-z])cars?([^a-z]|$)|כלי רכב|מכוניות", "כלי רכב", "", "", ""),
    (r"downloads?|installs?|הורדות", "הורדות", "", "", ""),
    (r"employ|workers|staff|מועסקים|עובדים", "מועסקים", "", "", ""),
    (r"visitors|tourists|תיירים|מבקרים", "מבקרים", "", "", ""),
    (r"tonnes?|(^|[^a-z])tons?([^a-z]|$)|טון", "טון", "", " טון", ""),
    (r"vaccinat|מחוסנים|חיסונים", "מחוסנים", "", "", ""),
]
SCALE_RULES = [(r"million|מיליון", "מיליון"), (r"thousand|אלפים|אלפי", "אלפים"), (r"billion|מיליארד", "מיליארד")]


def _words(name: str) -> List[str]:
    return [w for w in re.split(r"[^\w֐-׿]+", str(name).lower().replace("-", "_")) for w in w.split("_") if w]


def _score(name: str, table: Mapping[str, int]) -> int:
    words = _words(name)
    return max((points for word, points in table.items() if word in words), default=0)


def _is_meta(name: str) -> bool:
    low = str(name).lower()
    return any(m == low or low.endswith("_" + m) or low.startswith(m + "_") or m in _words(name) for m in META_WORDS)


def _is_id(name: str, series: pd.Series) -> bool:
    low = str(name).lower()
    if any(low == w or low.endswith("_" + w) or low.startswith(w + "_") for w in ID_WORDS):
        return True
    text = series.dropna().astype(str)
    return bool(len(text)) and text.str.fullmatch(r"[A-Z]{2,4}").mean() > 0.9   # קודי מדינה (ISR, USA)


def _hebrew_share(series: pd.Series) -> float:
    text = series.dropna().astype(str).head(400)
    return float(text.str.contains(r"[֐-׿]").mean()) if len(text) else 0.0


def parse_times(series: pd.Series) -> pd.Series:
    """תאריכים מעמודה: שנה (1948), YYYY-MM, YYYY-MM-DD, DD/MM/YYYY, MM/YYYY, רבעון (2020-Q3), חודש בעברית ("ינואר 2022").
    NaT כשלא מצליח."""
    from dataviz.sources import fiscal_start_year, is_fiscal_text, normalize_time_text
    text = series.astype(str).str.strip()
    if len(text) and text.map(is_fiscal_text).mean() > 0.9:   # שנות כספים "2014/15" - השנה שבה מתחילות
        text = text.map(lambda v: str(fiscal_start_year(v)))
    text = text.map(normalize_time_text)
    years = pd.to_numeric(text, errors="coerce")
    if years.notna().mean() > 0.9 and years.dropna().between(1000, 2200).all() and (years.dropna() % 1 == 0).all():
        return pd.to_datetime(years.astype("Int64").astype(str), format="%Y", errors="coerce")
    for fmt in ("%Y-%m-%d", "%Y-%m", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%m/%Y"):
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        if parsed.notna().mean() > 0.9:
            return parsed
    if text.astype("string").str.contains(r"\d", na=False).mean() <= 0.9:   # עמודה ריקה נשארת float (pandas 3)
        return pd.Series(pd.NaT, index=series.index)
    with warnings.catch_warnings():   # בלי פורמט אחיד pandas מזהיר על כל עמודה - כאן זה הניסיון האחרון
        warnings.simplefilter("ignore")
        return pd.to_datetime(text, errors="coerce", dayfirst=True)


def _period(name: str, parsed: pd.Series, raw: Optional[pd.Series] = None) -> Dict[str, Any]:
    from dataviz.sources import is_fiscal_text, is_quarter_text
    if raw is not None and len(raw) and raw.astype(str).str.strip().map(is_quarter_text).mean() > 0.9:
        return {"value": "quarter", "reason": "רבעונים (2020-Q3)"}
    if raw is not None and len(raw) and raw.astype(str).str.strip().map(is_fiscal_text).mean() > 0.9:
        return {"value": "year", "reason": "שנות כספים (2014/15) - לפי השנה שבה מתחילות"}
    days = parsed.dropna().drop_duplicates().sort_values()
    gaps = days.diff().dt.days.dropna()
    gap = float(gaps.median()) if len(gaps) else 0.0
    by_name = "year" if "year" in _words(name) or "שנה" in _words(name) else "month" if "month" in _words(name) or "חודש" in _words(name) else ""
    if by_name == "year" or (not by_name and gap >= 300 and (days.dt.month == days.dt.month.iloc[0]).all() and (days.dt.day == 1).all()):
        return {"value": "year", "reason": "ערכים שנתיים" + (" (שם העמודה)" if by_name else f" (פער טיפוסי {gap:.0f} ימים)")}
    if not by_name and 85 <= gap <= 95 and (days.dt.day == 1).all() and days.dt.month.isin([1, 4, 7, 10]).all():
        return {"value": "quarter", "reason": f"ערכים רבעוניים (פער טיפוסי {gap:.0f} ימים)"}
    if by_name == "month" or (25 <= gap <= 35 and days.dt.day.nunique() == 1):   # גם תאריך קבוע באמצע החודש (15)
        return {"value": "month", "reason": "ערכים חודשיים" + (" (שם העמודה)" if by_name else f" (פער טיפוסי {gap:.0f} ימים, תמיד ב-{days.dt.day.iloc[0]} בחודש)")}
    if 6 <= gap <= 8:
        return {"value": "day", "reason": "נתונים שבועיים - כל ערך ביום שלו (ברזולוציה יומית)"}
    return {"value": "day", "reason": f"תאריכים מלאים (פער טיפוסי {gap:.0f} ימים)"}


def time_column(df: pd.DataFrame) -> Optional[Choice]:
    """עמודת הזמן: שם שמרמז על זמן + כמה מהערכים הם תאריכים. שנה מלאה עדיפה על תאריך משני (ref_date)."""
    best: Optional[Choice] = None
    for column in df.columns:
        if _is_meta(column) and _score(column, TIME_WORDS) < 3:
            continue
        parsed = parse_times(df[column])
        ok = float(parsed.notna().mean()) if len(df) else 0.0
        if ok < 0.9:
            continue
        name_points = _score(column, TIME_WORDS)
        score = ok * 2 + name_points
        if best is None or score > best["score"]:
            period = _period(str(column), parsed, df[column])
            confidence = min(0.98, 0.5 + 0.12 * name_points + 0.1 * ok)
            best = {"column": str(column), "period": period["value"], "score": score, "confidence": round(confidence, 2),
                    "reason": f"'{column}': {ok:.0%} מהערכים תאריכים; {period['reason']}"}
    return best


TOTAL_RE = re.compile(r"^\s*(total|grand total|all|overall|sum|סה\"?כ|סך הכל|סך הכול|הכל|כולל|סך)\s*$", re.I)


def is_total_name(name: Any) -> bool:
    return bool(TOTAL_RE.match(str(name)))


def entity_column(df: pd.DataFrame, time: Optional[str]) -> Optional[Choice]:
    """עמודת הישות: טקסט שחוזר על עצמו לאורך הזמן (2 עד 300 ערכים), עדיפות לשם 'entity'/'country'... ולטקסט בעברית.
    שורות בלי זמן תקין ושורת סך ("Total", "סה"כ") - לא ישויות (totals = השמות שהוצאו)."""
    best: Optional[Choice] = None
    if time is not None:
        df = df[parse_times(df[time]).notna()]
    for column in df.columns:
        melted = str(column) == "<columns>"   # ישויות שהיו כותרות עמודות (USD, EUR) - לא קוד מזהה
        if column == time or pd.api.types.is_numeric_dtype(df[column]) or (not melted and (_is_meta(column) or _is_id(column, df[column]))):
            continue
        unique = df[column].nunique(dropna=True)
        name_points = _score(column, ENTITY_WORDS)
        if not (2 <= unique <= 300 or (unique == 1 and name_points >= 2)) or (unique > 1 and unique >= len(df) * 0.95):
            continue   # ערך אחד - רק בעמודה שנקראת entity/name (קובץ של סדרה אחת, עם השם שלה)
        hebrew = _hebrew_share(df[column])
        names = sorted(n for n in df[column].dropna().astype(str).unique())
        totals = [n for n in names if is_total_name(n)]
        names = [n for n in names if n not in totals]
        unique = len(names)
        score = name_points + hebrew * 2 + (1 if unique < 60 else 0)
        if best is None or score > best["score"]:
            confidence = min(0.97, 0.45 + 0.1 * name_points + 0.2 * hebrew)
            best = {"column": str(column), "score": score, "confidence": round(confidence, 2), "unique": int(unique),
                    "names": names[:300], "totals": totals,
                    "reason": f"'{column}': {unique} ערכים שחוזרים לאורך הזמן" + (", בעברית" if hebrew > 0.5 else "")}
    return best


def value_columns(df: pd.DataFrame, time: Optional[str], entity: Optional[str]) -> List[Choice]:
    """עמודות מספריות שהן ערך (לא מזהה, לא תוספת כמו מספר נקודות מדידה), מהמתאימה ביותר. delta_X היא נגזרת של X -
    עדיפה X (עם kind: level), ו-delta_X נשארת כחלופה."""
    rows: List[Choice] = []
    columns = [str(c) for c in df.columns]
    for column in df.columns:
        if column in (time, entity) or _is_id(column, df[column]):
            continue
        from dataviz.sources import to_numbers
        numbers = to_numbers(df[column])
        ok = float(numbers.notna().mean()) if len(df) else 0.0
        if ok < 0.3:   # מדד שקיים רק בחלק מהשנים (הוצאה לבריאות מ-2000) עדיין עמודת ערך - בציון נמוך יותר
            continue
        name = str(column)
        derived = name.lower().startswith("delta_")
        meta = _is_meta(name)
        named = any(w in name.lower() for w in VALUE_WORDS)
        has_delta = any(c.lower().startswith("delta_") and name.lower().endswith(c.lower()[6:]) for c in columns if c != name)
        score = ok + (2 if named else 0) - (3 if meta else 0) - (2 if derived else 0) + (1 if has_delta else 0)
        base = next((c for c in columns if derived and c != name and c.lower().endswith(name[6:].lower())), None)
        rows.append({"column": name, "score": round(score, 2), "derived_from": base if derived else None,
                     "confidence": round(max(0.2, min(0.95, 0.4 + 0.2 * score)), 2),
                     "reason": f"'{name}': {ok:.0%} מספרים" + ("; שם של ערך" if named else "") + ("; נראה כתוספת/בדיקה" if meta else "")
                     + (f"; הפרש של '{base}'" if derived and base else "")})
    return sorted(rows, key=lambda r: -r["score"])


def unit_of(column: str, entity_names: Sequence[str] = (), sources_text: str = "", file_name: str = "",
            cells: Sequence[Any] = (), units_row: str = "") -> Choice:
    """יחידות הערך: משורת היחידות מתחת לכותרת, מהסימן בתאים (₪4,688,143), משם העמודה, משם הקובץ, מהסוגריים בשמות
    הישויות ("(°C, בית דגן)") ומשורת Units ב-SOURCES.md."""
    if units_row:
        known = unit_of(units_row)
        label = known["label"] or units_row
        return {**known, "label": label, "suffix": known["suffix"] or f" {units_row}", "confidence": 0.9,
                "reason": f"{label} לפי שורת היחידות מתחת לכותרת"}
    symbols = [s for s in ("₪", "$", "€", "£", "%") if sum(1 for c in list(cells)[:200] if s in str(c)) > len(list(cells)[:200]) / 2]
    if symbols:
        sym = symbols[0]
        return {"label": sym, "prefix": sym if sym != "%" else "", "suffix": "%" if sym == "%" else "", "scale": "", "confidence": 0.9,
                "reason": f"{sym} - הסימן בתאים עצמם"}
    entity_text = " ".join(str(e) for e in list(entity_names)[:20])
    units_line = next((line for line in sources_text.splitlines() if re.search(r"\bunits?\b|יחידות", line, re.I)), "")
    stem = re.sub(r"\.\w+$", "", file_name)
    for where, text, confidence in (("שם העמודה", column, 0.85), ("שם הקובץ", stem, 0.75), ("שמות הישויות", entity_text, 0.75),
                                    ("SOURCES.md", units_line, 0.7)):
        low = text.lower()
        for pattern, label, prefix, suffix, _scale in UNIT_RULES:
            if re.search(pattern, low):
                scale = next((s for p, s in SCALE_RULES if re.search(p, low)), "")
                return {"label": label + (f" ({scale})" if scale else ""), "prefix": prefix, "suffix": suffix, "scale": scale,
                        "confidence": confidence, "reason": f"{label} לפי {where}" + (f" ('{text[:60]}')" if where != "שם העמודה" else f" ('{column}')")}
    return {"label": "", "prefix": "", "suffix": "", "scale": "", "confidence": 0.3, "reason": "לא נמצאה יחידה - מספר בלבד"}


def _mentioned_value(values: List[Choice], docs: str) -> Optional[Choice]:
    """README / SOURCES.md שאומר באיזו עמודת ערך הפרק משתמש ("The episode shows IMPORTS (imports_tonnes_million)")."""
    sentences = [s for s in re.split(r"(?<=[.;!?])\s+|\n", docs) if re.search(r"episode|shows?|uses?|chart|video|מציג|הפרק|בסרטון|בגרף", s, re.I)]
    hits = [v for v in values if not v.get("derived_from") and any(re.search(rf"(?<![\w]){re.escape(v['column'])}(?![\w])", s) for s in sentences)]
    return hits[0] if len(hits) == 1 else None


def _entity_columns(df: pd.DataFrame, time: Optional[str]) -> bool:
    """ישויות כעמודות: לפחות 3 עמודות מספריות (חוץ מהזמן) ששמותיהן קצרים / קודים ולא שמות של מדד (USD, EUR, GBP...)."""
    from dataviz.sources import to_numbers
    others = [c for c in df.columns if c != time]
    numeric = [c for c in others if to_numbers(df[c]).notna().mean() > 0.8]
    if len(numeric) < 3 or len(numeric) != len(others):
        return False
    return not any(any(w in str(c).lower() for w in VALUE_WORDS) or "_" in str(c) for c in numeric)


def analyze(df: pd.DataFrame, sources_text: str = "", file_name: str = "") -> Dict[str, Any]:
    """תפקידי העמודות בטבלה: {time, entity, values, value, unit}. value = הבחירה הראשונה (או None)."""
    time = time_column(df)
    entity = entity_column(df, time["column"] if time else None)
    values = value_columns(df, time["column"] if time else None, entity["column"] if entity else None)
    mentioned = _mentioned_value(values, sources_text) if values else None
    if mentioned and mentioned is not values[0]:
        values.remove(mentioned)
        values.insert(0, {**mentioned, "confidence": 0.9, "reason": mentioned["reason"] + "; README / SOURCES.md אומר שזו עמודת הפרק"})
    value = values[0] if values else None
    names = list(entity.get("names") or [])[:30] if entity else []
    units_row = str((df.attrs.get("read") or {}).get("units", {}).get(value["column"], "")) if value else ""
    unit = unit_of(value["column"], names, sources_text, file_name, df[value["column"]].dropna().astype(str).tolist() if value else [],
                   units_row) if value else None
    return {"time": time, "entity": entity, "values": values, "value": value, "unit": unit}
