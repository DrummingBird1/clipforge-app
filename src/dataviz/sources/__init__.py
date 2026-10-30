# dataviz/sources/__init__.py
#
# קריאת מקורות נתונים (CSV / Excel / JSON) לטבלה אחידה: עמודות time, entity, value,
# period ("day"/"month"/"year") - ואז daily_matrix() הופכת את כל המקורות למטריצה יומית
# אחת (תאריך x ישות), כשסכום של חודש/שנה מתפזר על הימים שלו (spread.py).
#
# הגדרת מקור (מתוך config.yaml) - הסוג (csv / excel / json) לפי סיומת הקובץ, או במפתח type:
#   - path: alarms.csv
#     filter: {origin: North}        (שורות שבהן העמודה שווה לערך, או לאחד מרשימה)
#     time: {column: time}          (period: day כברירת מחדל / month / year)
#     value: count                  (כל שורה היא מופע אחד, או {column: total})
#     entity: {from_time: year}     (הישות = השנה של התאריך, או {column: country})
#     kind: level                   (18.10.2026: כל ערך הוא רמה - טמפרטורה, מפלס - ולא תוספת; בלי kind = תוספת, כמו תמיד)

import hashlib
import json
import os
import re
import warnings
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import pandas as pd

from dataviz.sources.spread import period_days, spread_to_days

READERS = ("csv", "excel", "json")
PERIODS = ("day", "month", "year", "quarter")   # 20.10.2026: quarter - "2020-Q3", "Q3 2020", "רבעון 3 2020"
MISSING_MODES = ("zero", "previous", "interpolate")   # גל 52: ימים חסרים במקור יומי
FILL_MODES = ("none", "step", "linear")   # 20.10.2026: נתונים דלילים (מפקד כל ~10 שנים) - none = כמו תמיד
KINDS = ("amount", "level")   # 18.10.2026: amount = כל שורה מוסיפה (ברירת המחדל); level = הערך עצמו, לא מצטבר
_EXT_TO_TYPE = {".csv": "csv", ".tsv": "csv", ".txt": "csv", ".xlsx": "excel", ".xls": "excel", ".xlsm": "excel", ".json": "json"}


def source_type(spec: Mapping[str, Any]) -> str:
    kind = spec.get("type")
    if kind:
        return str(kind)
    name = str(spec.get("path") or str(spec.get("url") or "").split("?")[0])
    return _EXT_TO_TYPE.get(os.path.splitext(name)[1].lower(), "csv")


# גל 52: מקור מכתובת (URL / Google Sheets) - המנוע רק קורא את העותק שהורד; ההורדה עצמה (בלחיצה או בתזמון) היא
# של מי שמפעיל את המנוע (ב-ClipForge: utils/dataviz_remote.py), לתיקייה data.cache_dir.
_CACHE_EXT = {"csv": ".csv", "excel": ".xlsx", "json": ".json"}


def url_cache_path(spec: Mapping[str, Any], config: Mapping[str, Any]) -> str:
    """איפה העותק המקומי של מקור מכתובת: data.cache_dir (או .url_cache בתיקיית הפרק) / <טביעה של הכתובת>.<סיומת>."""
    folder = str((config.get("data") or {}).get("cache_dir") or os.path.join(str(config.get("base_dir", "")), ".url_cache"))
    digest = hashlib.sha1(str(spec["url"]).encode("utf-8")).hexdigest()[:16]
    return os.path.join(folder, digest + _CACHE_EXT.get(source_type(spec), ".csv"))


def resolved_sources(config: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """המקורות לקריאה: למקור מכתובת בלי path נכנס הנתיב המלא של העותק שהורד."""
    return [_url_spec(spec, config) if spec.get("url") and not spec.get("path") else dict(spec) for spec in config.get("sources") or []]


def _url_spec(spec: Mapping[str, Any], config: Mapping[str, Any]) -> Dict[str, Any]:
    """23.10.2026: עותק של כתובת ‎.tsv נשמר כ-‎.csv - ונקרא עם פסיק (KeyError על עמודת הזמן). המפריד לפי הכתובת."""
    resolved = dict(spec, path=url_cache_path(spec, config))
    if not spec.get("sep") and str(spec["url"]).split("?")[0].lower().endswith(".tsv"):
        resolved["sep"] = "\t"
    return resolved


def read_raw(spec: Mapping[str, Any], base_dir: str) -> pd.DataFrame:
    """הקובץ כמו שהוא, כטבלת pandas - לפי הסוג."""
    path = os.path.join(base_dir, str(spec["path"]))
    kind = source_type(spec)
    if kind == "csv":
        sep = spec.get("sep") or ("\t" if path.lower().endswith(".tsv") else ",")
        # 20.10.2026: decimal (",": 1,722), thousands ("," / "." / " "), header_row (שורת הכותרת האמיתית, אחרי שורת
        # כותרת-על) - רק כשהמקור מבקש; בלי - בדיוק כמו קודם
        options: Dict[str, Any] = {}
        if spec.get("decimal"):
            options["decimal"] = str(spec["decimal"])
        if spec.get("thousands"):
            options["thousands"] = str(spec["thousands"])
        if spec.get("header_row"):
            options["header"] = int(spec["header_row"])
        if spec.get("skip_rows"):   # 20.10.2026: שורת יחידות מתחת לכותרת ("", "", "GWh") ושורות כותרת-על
            options["skiprows"] = [int(r) for r in spec["skip_rows"]]
        return pd.read_csv(path, sep=sep, encoding=spec.get("encoding", "utf-8"), **options)
    if kind == "excel":
        return pd.read_excel(path, sheet_name=spec.get("sheet", 0), header=int(spec.get("header_row") or 0))
    if kind == "json":
        with open(path, "r", encoding=spec.get("encoding", "utf-8-sig")) as f:   # 23.10.2026: JSON עם BOM (גם בלי - כמו utf-8)
            data = json.load(f)
        for key in str(spec.get("records") or "").split(".") if spec.get("records") else []:
            data = data[key]
        return pd.json_normalize(data)
    raise ValueError(f"סוג מקור לא מוכר: {kind!r} (קיימים: {', '.join(READERS)})")


def _apply_filter(df: pd.DataFrame, flt: Mapping[str, Any] | None) -> pd.DataFrame:
    if not flt:
        return df
    mask = pd.Series(True, index=df.index)
    for column, wanted in flt.items():
        values = wanted if isinstance(wanted, (list, tuple)) else [wanted]
        mask &= df[column].isin(values)
    return df[mask]


# 20.10.2026: חודשים בעברית ("ינואר 2022") ורבעונים ("2020-Q3") - הופכים לתאריך שקורא כל pandas. ערכים אחרים לא משתנים
HEBREW_MONTHS = {"ינואר": 1, "פברואר": 2, "מרץ": 3, "מרס": 3, "אפריל": 4, "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
                 "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
                 # 23.10.2026: עוד כתיב ("מארס") וקיצורים ("פבר׳ 2022") - קודם נזרקו כתאריך לא תקין
                 "מארס": 3, "ינו": 1, "פבר": 2, "אפר": 4, "יונ": 6, "יול": 7, "אוג": 8, "ספט": 9, "אוק": 10, "נוב": 11, "דצמ": 12}
_HEBREW_MONTH_RE = re.compile(r"^\s*(" + "|".join(sorted(HEBREW_MONTHS, key=len, reverse=True)) + r")[׳'\.]?\s*[-/ ,]?\s*(\d{4})\s*$")
_QUARTER_RES = (re.compile(r"^\s*(\d{4})\s*[-/ ]?\s*[Qq]([1-4])\s*$"), re.compile(r"^\s*[Qq]([1-4])\s*[-/ ]?\s*(\d{4})\s*$"),
                re.compile(r"^\s*רבעון\s*([1-4])\s*[-/ ,]?\s*(\d{4})\s*$"))


_DOTTED_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})\s*$")


def normalize_time_text(value: Any) -> Any:
    """'ינואר 2022' -> '2022-01-01', '2020-Q3' / 'Q3 2020' / 'רבעון 3 2020' -> '2020-07-01', '14.04.23' -> '2023-04-14'
    (תאריך עם נקודות - יום.חודש.שנה). אחרת - כמו שהוא."""
    if not isinstance(value, str):
        return value
    dotted = _DOTTED_RE.match(value)
    if dotted and 1 <= int(dotted.group(2)) <= 12 and 1 <= int(dotted.group(1)) <= 31:
        year = int(dotted.group(3))
        year = year + (2000 if year < 70 else 1900) if year < 100 else year
        return f"{year}-{int(dotted.group(2)):02d}-{int(dotted.group(1)):02d}"
    match = _HEBREW_MONTH_RE.match(value)
    if match:
        return f"{match.group(2)}-{HEBREW_MONTHS[match.group(1)]:02d}-01"
    for i, pattern in enumerate(_QUARTER_RES):
        match = pattern.match(value)
        if match:
            q_year, quarter = (match.group(1), match.group(2)) if i == 0 else (match.group(2), match.group(1))
            return f"{q_year}-{3 * int(quarter) - 2:02d}-01"
    return value


_FISCAL_RE = re.compile(r"^\s*(1[89]\d\d|20\d\d)\s*[/\-–]\s*(\d{2}|\d{4})\s*$")


def fiscal_start_year(value: Any) -> Any:
    """שנת כספים "2014/15" / "2014-2015" -> 2014 (השנה שבה היא מתחילה). אחרת - כמו שהוא."""
    match = _FISCAL_RE.match(str(value)) if isinstance(value, str) else None
    if not match:
        return value
    start, end = int(match.group(1)), match.group(2)
    following = (start + 1) % 100 if len(end) == 2 else start + 1
    return start if int(end) == following else value


def is_fiscal_text(value: Any) -> bool:
    return isinstance(value, str) and fiscal_start_year(value) != value


def is_quarter_text(value: Any) -> bool:
    return isinstance(value, str) and any(p.match(value) for p in _QUARTER_RES)


# 23.10.2026: פורמטים לעמודת זמן של טקסט, לפי הסדר של האשף החכם (smart/columns.parse_times). בלי פורמט pandas ניחש לפי
# השורה הראשונה: "01/02/2021" נקרא חודש-ראשון (כל חודשי השנה התקפלו לינואר) ושורות עם יום מעל 12 נזרקו בשקט, ועמודה
# שמערבבת תאריך ותאריך-שעה איבדה שורות. ISO8601 קורא את שניהם; DD/MM/YYYY - כמו באשף (ובנתונים ישראליים)
_TEXT_TIME_FORMATS = ("ISO8601", "%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%m/%Y", "%m.%Y")


def _text_times(text: pd.Series) -> pd.Series:
    """הפורמט שקורא הכי הרבה ערכים; בתיקו - הקודם ברשימה. הניחוש הישן של pandas (בלי פורמט) אחרון."""
    text = text.map(normalize_time_text)
    best: pd.Series | None = None
    for fmt in (*_TEXT_TIME_FORMATS, None):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")   # בלי פורמט pandas מזהיר על כל עמודה
                parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        except (ValueError, TypeError):   # למשל אזורי זמן מעורבים
            continue
        if best is None or parsed.notna().sum() > best.notna().sum():
            best = parsed
    return best if best is not None else pd.Series(pd.NaT, index=text.index, dtype="datetime64[ns]")


def _numeric_times(raw: pd.Series) -> pd.Series:
    """23.10.2026: זמן מספרי בתקופה יומית / חודשית - קודם נקרא כננו-שניות מ-1970. שנה (2019), YYYYMM (202001) ו-YYYYMMDD
    (20200115) הופכים לתאריך; מספר אחר - לא תאריך."""
    numbers = pd.to_numeric(raw, errors="coerce")
    whole = numbers.where(numbers.notna() & (numbers % 1 == 0))
    text = whole.dropna().astype("int64").astype(str)
    result = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    for digits, fmt, low, high in ((4, "%Y", 1000, 2200), (6, "%Y%m", 100001, 220012), (8, "%Y%m%d", 10000101, 22001231)):
        mask = (text.str.len() == digits) & whole.loc[text.index].between(low, high)
        result.loc[mask[mask].index] = pd.to_datetime(text[mask], format=fmt, errors="coerce")
    return result


def _period_bounds(raw: pd.Series, period: str) -> pd.Series:
    """תחילת התקופה של כל שורה (יום/חודש/רבעון/שנה) כ-Timestamp מנורמל. ערך שאינו זמן - NaT (השורה נזרקת)."""
    text = pd.api.types.is_object_dtype(raw) or pd.api.types.is_string_dtype(raw)
    if period == "year":
        # 23.10.2026: תא ריק, שורת הערה ("Source: ...") או תאריך מלא כבר לא מפילים את הפרק (astype(int)) - שנה מתאריך מלא,
        # ושאר הערכים NaT כמו בשאר התקופות
        values = raw.map(fiscal_start_year) if text else raw   # 20.10.2026: שנת כספים "2014/15" -> 2014
        years = pd.to_numeric(values, errors="coerce")
        if text and years.isna().any():
            years = years.fillna(_text_times(raw.astype("string").str.strip()).dt.year)
        years = years.where(years.between(1000, 2200))
        times = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
        valid = years.dropna()
        times.loc[valid.index] = pd.to_datetime(valid.astype(int).astype(str) + "-01-01")
        return times
    if text:
        times = _text_times(raw)
    elif pd.api.types.is_numeric_dtype(raw) and not pd.api.types.is_bool_dtype(raw):
        times = _numeric_times(raw)
    else:
        times = pd.to_datetime(raw, errors="coerce")
    if period == "month":
        return times.dt.to_period("M").dt.to_timestamp()
    if period == "quarter":
        return times.dt.to_period("Q").dt.to_timestamp()
    return times.dt.normalize()


_NUMBER_RE = re.compile(r"^\s*(?P<sign>[-−])?\s*[₪$€£]?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?P<mult>[KkMmBb])?\s*[₪$€£%]?\s*$")
_MULTIPLIERS = {"k": 1e3, "m": 1e6, "b": 1e9}


def to_numbers(series: pd.Series, decimal: Any = None, thousands: Any = None) -> pd.Series:
    """עמודת ערכים למספרים. 20.10.2026: גם '₪4,688,143', '$1.2M', '12%', '1,234' - ערכים שקודם לא נקראו (הפכו ל-0). מספרים
    רגילים - בדיוק כמו קודם. 23.10.2026: decimal / thousands של המקור - read_csv מחיל אותם רק כשכל העמודה מספרים, ותא
    אחד של "-" או ".." השאיר אותה טקסט: "1,5" נקרא 0 ו-"1.234" (אלפים) נקרא 1.234."""
    text = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
    if text and (thousands or (decimal and str(decimal) != ".")):
        strings = series.map(lambda v: isinstance(v, str))   # רק טקסט - מספר שכבר נקרא לא עובר את ההחלפה
        local = series[strings].astype(str)
        if thousands:
            local = local.str.replace(str(thousands), "", regex=False)
        if decimal and str(decimal) != ".":
            local = local.str.replace(str(decimal), ".", regex=False)
        series = series.astype(object).copy()
        series[strings] = local
    numbers = pd.to_numeric(series, errors="coerce")
    if not text:
        return numbers
    missing = numbers.isna() & series.notna()
    if not missing.any():
        return numbers

    def parse(value: Any) -> Any:
        match = _NUMBER_RE.match(str(value))
        if not match:
            return float("nan")
        number = float(match.group("num").replace(",", "")) * _MULTIPLIERS.get((match.group("mult") or "").lower(), 1.0)
        return -number if match.group("sign") else number
    return numbers.where(~missing, series[missing].map(parse))


# 20.10.2026: טבלה רחבה (השנים הן כותרות העמודות) - wide: true הופך אותה לשורות; עמודת הזמן והערך מקבלות את השמות האלה
WIDE_TIME, WIDE_VALUE = "<years-as-columns>", "<cells>"


def year_columns(columns: Sequence[Any]) -> List[str]:
    return [str(c) for c in columns if re.fullmatch(r"\s*(1[89]\d\d|20\d\d)\s*", str(c))]


ENTITY_COLUMNS = "<columns>"   # שם העמודה של הישויות אחרי ההמרה (כותרות העמודות הן הישויות)


def melt_entity_columns(df: pd.DataFrame, time_column: str) -> pd.DataFrame:
    """20.10.2026: ישויות כעמודות (month, USD, EUR, GBP...) - כל עמודה מלבד הזמן היא ישות; הופך לשורות."""
    values = [c for c in df.columns if str(c) != str(time_column)]
    return df.melt(id_vars=[time_column], value_vars=values, var_name=ENTITY_COLUMNS, value_name=WIDE_VALUE)


def melt_wide(df: pd.DataFrame) -> pd.DataFrame:
    years = year_columns(df.columns)
    ids = [c for c in df.columns if str(c) not in years]
    return df.melt(id_vars=ids, value_vars=[c for c in df.columns if str(c) in years], var_name=WIDE_TIME, value_name=WIDE_VALUE)


def read_table(spec: Mapping[str, Any], base_dir: str, missing: str = "zero") -> pd.DataFrame:
    """מקור אחד -> טבלה אחידה [time, entity, value, period] (שורות בלי זמן תקין נזרקות). missing = של הפרק (data.missing)."""
    df = _apply_filter(read_raw(spec, base_dir), spec.get("filter"))
    if spec.get("wide"):   # 20.10.2026
        df = melt_wide(df)
    if spec.get("entity_columns"):   # 20.10.2026: ישויות כעמודות
        df = melt_entity_columns(df, str((spec.get("time") or {}).get("column") if isinstance(spec.get("time"), Mapping) else spec.get("time")))
    time_spec = spec.get("time") or {}
    if isinstance(time_spec, str):
        time_spec = {"column": time_spec}
    period = str(time_spec.get("period", "day"))
    times = _period_bounds(df[time_spec["column"]], period)
    # שורות בלי זמן תקין נזרקות לפני חישוב הישות - אחרת NaN הופך את עמודת השנים ל-float (2021.0)
    valid = times.notna()
    if len(df) and not valid.any():   # 23.10.2026: שורות שמהן אף אחת לא תאריך = קובץ שלא נטען (קודם: קריסה בשנה, שקט בשאר)
        raise ValueError(f"אין אף שורת נתונים תקינה: אף ערך בעמודה '{time_spec['column']}' הוא לא זמן ({spec.get('path') or spec.get('url')}).")
    df, times = df[valid], times[valid]

    value_spec = spec.get("value", "count")
    if value_spec == "count":
        values = pd.Series(1.0, index=df.index)
    else:
        column = value_spec["column"] if isinstance(value_spec, Mapping) else str(value_spec)
        values = to_numbers(df[column], spec.get("decimal"), spec.get("thousands"))
        # 23.10.2026: תא ריק (או שלא נקרא) הוא "לא ידוע", לא 0 - ברמה הקו צנח ל-0 באותו יום, ו-fill / missing לא השלימו
        # תקופה שכבר "קיימת" עם 0. במקורות כאלה השורה נזרקת; בכמות רגילה (סכום) 0 ושורה חסרה הם אותו דבר
        if spec.get("kind") == "level" or str(spec.get("fill") or "none") != "none" or str(spec.get("missing") or missing) != "zero":
            df, times, values = df[values.notna()], times[values.notna()], values[values.notna()]
        values = values.fillna(0.0)

    entity_spec = spec.get("entity") or {"from_time": "year"}
    if isinstance(entity_spec, str):
        entities = pd.Series(entity_spec, index=df.index)
    elif entity_spec.get("from_time") == "year":
        entities = times.dt.year.astype(int)
    elif entity_spec.get("from_time") == "month":
        entities = times.dt.strftime("%Y-%m")
    else:
        # 25.10.2026: "  ישראל " מקובץ אחד ו-"ישראל" מקובץ אחר היו שתי ישויות, והרווחים הזיזו את השם בתווית
        entities = df[entity_spec["column"]].map(lambda name: name.strip() if isinstance(name, str) else name)

    table = pd.DataFrame({"time": times, "entity": entities, "value": values})
    if spec.get("exclude_entities"):   # 20.10.2026: שורת סך ("Total", "סה\"כ") - לא ישות
        table = table[~table["entity"].astype(str).isin([str(e) for e in spec["exclude_entities"]])]
    table["period"] = period
    return table.reset_index(drop=True)


def source_name(spec: Mapping[str, Any]) -> str:
    """ק4: השם של מקור כמו שהמשתמש מכיר אותו - המקרא שלו, ואם אין - שם הקובץ בלי הסיומת (מקור מכתובת - סוף הכתובת)."""
    if spec.get("legend"):
        return str(spec["legend"])
    where = str(spec.get("path") or spec.get("url") or "")
    name = os.path.basename(where.split("?")[0].rstrip("/")) or where
    return os.path.splitext(name)[0] or name


def share_entities(tables: List[pd.DataFrame], specs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """23.10.2026 (ק4, החלטת המשתמש): ישות שמופיעה בכמה מקורות. עד היום העמודות שלה פשוט חוברו - שתי רמות נתנו סכום
    (20 + 22 = 44 במקום 22), ואוכלוסייה ותמ"ג של אותה מדינה (ציר ימני) - קו אחד.
    - בלי חפיפה בזמן: סדרה אחת לפי הזמן. בכמויות התוספות ממילא לא נפגשות; ברמות השורות של המקורות המאוחרים עוברות
      לטבלה של המקור הראשון בזמן, כך שהקו ממשיך מהערך האחרון כמו במקור אחד.
    - עם חפיפה (גם בתקופה אחת), או במקורות מסוג אחר (רמה מול כמות) או בציר אחר: ישות לכל מקור, "שם (מקור)",
      ורשומה לאזהרה ב"לפני רינדור".
    תקופה משותפת אחת עם אותו ערך בדיוק - הסוף של קובץ אחד וההתחלה של הבא - היא תפר ולא חפיפה: נספרת פעם אחת.
    הטבלאות מתעדכנות במקום (מי שקרא ל-daily_matrix רואה את השמות החדשים). מחזיר את הרשומות לאזהרה."""
    groups: List[Dict[Any, pd.DataFrame]] = [{_plain(e): rows for e, rows in table.groupby("entity", sort=False)} for table in tables]
    shared: Dict[Any, List[int]] = {}
    for index, group in enumerate(groups):
        for entity in group:
            shared.setdefault(entity, []).append(index)
    notes: List[Dict[str, Any]] = []
    for entity, indexes in shared.items():
        if len(indexes) < 2:
            continue
        spans = []
        for index in indexes:
            rows = groups[index][entity]
            level = specs[index].get("kind") == "level"
            values = rows.groupby("time")["value"].agg("mean" if level else "sum")
            period = str(rows["period"].iloc[0])
            spans.append({"index": index, "level": level, "axis": specs[index].get("axis") == "right", "period": period,
                          "values": values, "first": values.index.min(), "end": period_days(values.index.max(), period)[-1]})
        spans.sort(key=lambda s: s["first"])
        reason = "kind" if len({s["level"] for s in spans}) > 1 else "axis" if len({s["axis"] for s in spans}) > 1 else ""
        seams = []
        for k, a in enumerate(spans):
            for b in spans[k + 1:]:
                if reason or b["first"] > a["end"]:
                    continue
                common = a["values"].index.intersection(b["values"].index)
                if (len(common) == 1 and common[0] == a["values"].index.max() == b["values"].index.min() and a["period"] == b["period"]
                        and a["values"][common[0]] == b["values"][common[0]]):
                    seams.append((b["index"], common[0]))
                else:
                    reason = "overlap"
        if reason:
            names = [source_name(specs[s["index"]]) for s in spans]
            if len(set(names)) < len(names):   # שני מקורות עם אותו שם (שני גיליונות של אותו קובץ) - גם המספר שלהם
                names = [f"{name} {s['index'] + 1}" for name, s in zip(names, spans)]
            renamed = [f"{entity} ({name})" for name in names]
            for s, new in zip(spans, renamed):
                table = tables[s["index"]]
                tables[s["index"]] = table.assign(entity=table["entity"].where(table["entity"].map(_plain) != entity, new))
            notes.append({"entity": str(entity), "sources": names, "names": renamed, "reason": reason})
            continue
        for index, when in seams:
            table = tables[index]
            tables[index] = table[~((table["entity"].map(_plain) == entity) & (table["time"] == when))].reset_index(drop=True)
        if spans[0]["level"]:
            first = spans[0]["index"]
            moved = []
            for s in spans[1:]:
                table = tables[s["index"]]
                mine = table["entity"].map(_plain) == entity
                moved.append(table[mine])
                tables[s["index"]] = table[~mine].reset_index(drop=True)
            tables[first] = pd.concat([tables[first], *moved], ignore_index=True)
    return notes


def daily_matrix(tables: List[pd.DataFrame], specs: Sequence[Mapping[str, Any]], base_dir: str,
                 start: Any = None, end: Any = None, missing: str = "zero") -> Tuple[pd.DataFrame, Dict[Any, int]]:
    """ק4: קודם ישויות שמופיעות בכמה מקורות (share_entities - סדרה אחת לפי הזמן, או ישות לכל מקור), ואז המטריצה.
    הרשומות לאזהרה ב-matrix.attrs["shared"]."""
    shared = share_entities(tables, specs)
    matrix, origins = _daily_matrix(tables, specs, base_dir, start, end, missing)
    matrix.attrs["shared"] = shared
    return matrix, origins


def _daily_matrix(tables: List[pd.DataFrame], specs: Sequence[Mapping[str, Any]], base_dir: str,
                  start: Any = None, end: Any = None, missing: str = "zero") -> Tuple[pd.DataFrame, Dict[Any, int]]:
    """כל המקורות -> מטריצה יומית אחת: אינדקס = כל הימים בטווח, עמודה לכל ישות (ממוינות),
    ערך = כמה נוסף באותו יום. סכומים של חודש/שנה מתפזרים על הימים לפי spread בהגדרות.
    מחזיר גם origins: ישות -> אינדקס המקור הראשון שסיפק אותה (בשביל מרקם ומקרא)."""
    per_source: List[pd.DataFrame] = []
    for table, spec in zip(tables, specs):
        per_source.append(_source_daily(table, spec, base_dir, str(spec.get("missing") or missing)))
    starts = [d.index.min() for d in per_source if len(d)]
    ends = [d.index.max() for d in per_source if len(d)]
    if not starts:
        raise ValueError("אין אף שורת נתונים תקינה במקורות.")
    all_dates = pd.date_range(start=pd.Timestamp(start) if start else min(starts),
                              end=pd.Timestamp(end) if end else max(ends), freq="D")
    if not len(all_dates):   # 23.10.2026: קודם - argmax של רשימה ריקה, בלי הסבר
        raise ValueError("timeline.start אחרי סוף הנתונים (או אחרי timeline.end) - אין ימים להציג.")
    # מספרים (שנים) קודם ואז שמות - מקורות עם סוגי ישויות שונים (גל 52: שנה ממקור אחד, עיר ממקור מכתובת) לא נכשלים במיון
    entities = sorted({_plain(e) for d in per_source for e in d.columns}, key=lambda e: (isinstance(e, str), e if not isinstance(e, str) else 0, str(e)))
    matrix = pd.DataFrame(0.0, index=all_dates, columns=entities)
    origins: Dict[Any, int] = {}
    for index, (daily, spec) in enumerate(zip(per_source, specs)):
        for entity in daily.columns:
            origins.setdefault(_plain(entity), index)
            column = daily[entity].reindex(all_dates).fillna(0.0)
            if spec.get("kind") == "level":
                # 23.10.2026: רמה עם timeline.start אחרי תחילת הנתונים - התוספות שלפני ההתחלה (וביום הראשון שלהן - כל
                # הרמה) נחתכו, והקו התחיל מ-0. הן נכנסות ליום הראשון שמוצג, כך שהמצטבר נשאר הרמה
                column.iloc[0] += float(daily[entity][daily.index < all_dates[0]].sum())
            matrix[_plain(entity)] = matrix[_plain(entity)] + column
    return matrix, origins


def _level_daily(table: pd.DataFrame, period: str, missing: str) -> pd.DataFrame:
    """18.10.2026: מקור של רמות (kind: level). כל ישות מתחילה בערך הראשון שלה מהיום הראשון של התקופה הראשונה,
    בלי לצבור ובלי לפזר. בשנה/חודש - הערך של כל תקופה מתקבל ביום האחרון שלה וביניהן קו ישר (כמו פיזור שווה של
    השינוי על ימי התקופה, כך שאחרי התקופה הראשונה הקו זהה למה שתוספות היו נותנות); התקופה הראשונה מחזיקה את הערך
    הראשון. במקור יומי - ימים חסרים בקו ישר בין הימים הידועים (missing: previous - הערך הקודם). אחרי הערך האחרון
    הקו נשאר. כמה שורות לאותה תקופה וישות - הממוצע שלהן. המטריצה היומית שומרת תוספות: ביום הראשון הרמה כולה,
    ואחר כך השינוי מיום ליום - כך שהמצטבר הוא בדיוק הרמה."""
    columns: Dict[Any, pd.Series] = {}
    for entity, rows in table.groupby("entity", sort=False):
        means = rows.groupby("time")["value"].mean().sort_index()
        starts = pd.DatetimeIndex(means.index)
        periods = rows.groupby("time")["period"].first().reindex(means.index)
        if periods.nunique() > 1:   # ק4: שורות ממקור עם תקופה אחרת (שנתי ואחריו חודשי) - כל אחת בסוף התקופה שלה
            ends = pd.DatetimeIndex([period_days(t, p)[-1] for t, p in periods.items()])
            anchors = pd.concat([pd.Series([means.iloc[0]], index=starts[:1]), pd.Series(means.to_numpy(), index=ends)])
            anchors = anchors[~anchors.index.duplicated(keep="last")].sort_index()
            days = pd.date_range(starts[0], ends.max(), freq="D")
        elif period == "day":
            anchors = pd.Series(means.to_numpy(), index=starts)
            days = pd.date_range(starts[0], starts[-1], freq="D")
        else:
            ends = pd.DatetimeIndex([period_days(t, period)[-1] for t in starts])
            anchors = pd.concat([pd.Series([means.iloc[0]], index=starts[:1]), pd.Series(means.to_numpy(), index=ends)])
            days = pd.date_range(starts[0], ends[-1], freq="D")
        level = anchors.reindex(days)
        level = level.ffill() if missing == "previous" else level.interpolate(method="linear")
        increments = level.diff()
        increments.iloc[0] = level.iloc[0]
        columns[_plain(entity)] = increments
    return pd.DataFrame(columns).fillna(0.0).astype(float)


def _plain(value: Any) -> Any:
    """np.int32(2014) -> 2014 - שמות ישויות כטיפוסי פייתון רגילים (צבעים, תוויות, pickle)."""
    return value.item() if hasattr(value, "item") else value


def _fill_periods(table: pd.DataFrame, period: str, fill: str) -> pd.DataFrame:
    """20.10.2026: תקופות חסרות בין תקופות ידועות (שנה / חודש) מקבלות ערך: step - הערך של התקופה הקודמת, linear - קו
    ישר בין השכנות. לפני הישות הראשונה ואחרי האחרונה - כלום. אחר כך הפיזור הרגיל לימים."""
    rows = []
    for entity, group in table.groupby("entity", sort=False):
        series = group.set_index("time")["value"].sort_index()
        full = pd.date_range(series.index.min(), series.index.max(), freq={"year": "YS", "quarter": "QS"}.get(period, "MS"))
        filled = series.reindex(full)
        filled = filled.ffill() if fill == "step" else filled.interpolate(method="linear")
        rows.append(pd.DataFrame({"time": full, "entity": entity, "value": filled.to_numpy()}))
    return pd.concat(rows, ignore_index=True) if rows else table


def _source_daily(table: pd.DataFrame, spec: Mapping[str, Any], base_dir: str, missing: str = "zero") -> pd.DataFrame:
    period = table["period"].iloc[0] if len(table) else "day"
    fill = str(spec.get("fill") or "none")
    if fill != "none":   # 20.10.2026: יומי ורמות - דרך missing הקיים (previous / interpolate)
        missing = "previous" if fill == "step" else "interpolate"
    if spec.get("kind") == "level":
        return _level_daily(table, period, missing)
    if period == "day":
        grouped = table.groupby(["time", "entity"])["value"].sum().unstack("entity")
        grouped.index = pd.DatetimeIndex(grouped.index)
        if missing != "zero" and len(grouped):
            # גל 52: מקור שמדווח ערך לכל יום (ולא מופעים) - יום שחסר מקבל את הערך הקודם, או קו ישר בין הימים שסביבו
            grouped = grouped.reindex(pd.date_range(grouped.index.min(), grouped.index.max(), freq="D"))
            # 23.10.2026: previous רק בתוך הטווח של כל ישות (limit_area) - קודם הערך האחרון של ישות חזר כל יום עד סוף המקור
            grouped = grouped.ffill(limit_area="inside") if missing == "previous" else grouped.interpolate(method="linear", limit_area="inside")
        return grouped.fillna(0.0).astype(float)
    weights = None
    weight_spec = (spec.get("spread") or {}).get("weights")
    if weight_spec:
        weights = read_raw(weight_spec, base_dir)
    columns: Dict[Any, pd.Series] = {}
    # 18.10.2026: שורות של אותה תקופה ואותה ישות מתחברות לפני הפיזור (הפיזור לינארי בסכום) - קובץ גדול לא מפזר שורה-שורה
    table = table.groupby(["time", "entity"], sort=False)["value"].sum().reset_index()
    if fill != "none":
        table = _fill_periods(table, period, fill)
    for start, entity, total in zip(table["time"], table["entity"], table["value"]):
        series = spread_to_days(start, period, total, spec.get("spread") or {}, weights)
        entity = _plain(entity)
        columns[entity] = series if entity not in columns else columns[entity].add(series, fill_value=0.0)
    return pd.DataFrame(columns)
