# dataviz/smart/scan.py
#
# 20.10.2026: סיווג כל קובץ בתיקיית נתונים - סדרה / אירועים / משקלות / גולמי שלא בשימוש / בדיקה בלבד / מסמכים / הגדרות -
# לפי השם, העמודות, והשורה שמזכירה אותו ב-SOURCES.md / README. לכל קובץ סיבה וביטחון. קריאה בלבד.
import json
import os
import re
import zipfile
from typing import Any, Dict, List, Optional

import pandas as pd

from dataviz.smart import columns as cols

KINDS = ("series", "events", "weights", "raw_unused", "check", "docs", "config", "other")
KIND_LABELS = {"series": "סדרת נתונים", "events": "אירועים", "weights": "משקלות", "raw_unused": "גולמי - לא בשימוש",
               "check": "בדיקה בלבד", "docs": "מסמך", "config": "הגדרות", "other": "אחר"}
MAX_READ_BYTES = 40 * 1024 * 1024
DOC_NAMES = ("sources", "readme", "notes", "license")


def read_docs(folder: str) -> str:
    """הטקסט של SOURCES.md / README (מה שקיים), לסיווג וליחידות."""
    parts = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith((".md", ".txt")) and name.lower().split(".")[0] in DOC_NAMES:
            try:
                with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as f:
                    parts.append(f.read(200_000))
            except OSError:
                continue
    return "\n".join(parts)


def sniff(path: str, encoding: str = "utf-8-sig") -> Dict[str, Any]:
    """איך לקרוא את ה-CSV: מפריד (, ; טאב |), נקודה עשרונית (1,722 כשהמפריד ;), מפריד אלפים ("1,234" במרכאות / 1.234,5),
    ושורת הכותרת האמיתית (אחרי שורת כותרת-על כמו "נתוני תעסוקה לפי מחוז,,"). רק מה שלא ברירת המחדל."""
    import csv
    try:
        with open(path, encoding=encoding, errors="replace") as f:
            sample = f.read(20000)
    except OSError:
        return {}
    lines = [line for line in sample.splitlines() if line.strip()][:30]
    options: Dict[str, Any] = {}
    try:
        sep = csv.Sniffer().sniff("\n".join(lines[:15]), delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    if sep != ",":
        options["sep"] = sep
    body = "\n".join(lines[1:])
    if sep in (";", "\t", "|") and re.search(r"(?:^|[;\t|])-?\d+,\d+(?:[;\t|]|$)", body, re.M):
        options["decimal"] = ","
        if re.search(r"\d\.\d{3},\d", body):
            options["thousands"] = "."
    elif re.search(r'"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?"', body):
        options["thousands"] = ","
    rows = list(csv.reader(lines[:12], delimiter=sep))
    if len(rows) > 2:
        width = max(len(r) for r in rows)
        filled = [sum(1 for c in r if c.strip()) for r in rows]
        for i, row in enumerate(rows[:6]):
            numeric = sum(1 for c in row if re.fullmatch(r"\s*-?[\d.,]+\s*", c or ""))
            if filled[i] >= max(2, width - 1) and numeric < filled[i] / 2:
                if i:
                    options["header_row"] = i   # השורות שלפני - כותרת-על / הערה
                units = _units_row(rows, i)
                if units:   # שורת יחידות ("", "", "GWh") - יחידות, לא נתונים
                    options["units"] = units
                    options["skip_rows"] = list(range(i)) + [i + 1]
                    options.pop("header_row", None)
                break
    return options


def _units_row(rows: List[List[str]], header: int) -> Dict[str, str]:
    """השורה שמתחת לכותרת, אם היא שורת יחידות: רק טקסטים קצרים (GWh, ₪, %), לפחות תא אחד ריק, והשורה שאחריה עם מספרים."""
    if len(rows) < header + 3:
        return {}
    head, below, after = rows[header], rows[header + 1], rows[header + 2]
    cells = [c.strip() for c in below]
    texts = [c for c in cells if c]
    numbers_after = sum(1 for c in after if re.fullmatch(r"\s*-?[\d.,]+\s*", c or ""))
    if not texts or len(texts) == len(cells) or numbers_after == 0:
        return {}
    if any(re.fullmatch(r"-?[\d.,]+", c) or len(c) > 16 for c in texts):
        return {}
    return {head[k].strip(): c for k, c in enumerate(cells) if c and k < len(head)}


def read_csv(path: str, nrows: Optional[int] = None) -> Optional[pd.DataFrame]:
    for encoding in ("utf-8-sig", "cp1255"):
        try:
            options = sniff(path, encoding)
            kwargs = {k: v for k, v in options.items() if k in ("sep", "decimal", "thousands")}
            if options.get("header_row"):
                kwargs["header"] = options["header_row"]
            if options.get("skip_rows"):
                kwargs["skiprows"] = options["skip_rows"]
            df = pd.read_csv(path, nrows=nrows, encoding=encoding, low_memory=False, **kwargs)
            # 23.10.2026: CSV בעברית מ-Excel (cp1255) נקרא כאן, אבל המנוע קרא utf-8 ונפל - הקידוד עובר למקור
            df.attrs["read"] = dict(options, encoding="cp1255") if encoding == "cp1255" else options
            return df
        except UnicodeDecodeError:
            continue
        except (OSError, ValueError, pd.errors.ParserError):
            return None
    return None


def read_json_table(path: str) -> Optional[pd.DataFrame]:
    """JSON שהוא טבלה: רשימה של רשומות, או {"data": [...]} (גם records / items / results / rows / מפתח אחר עם רשימה של
    רשומות). GeoJSON ו-JSON של הגדרות - None."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    records_key = ""
    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            return None
        keys = [k for k in ("data", "records", "items", "results", "rows") if isinstance(data.get(k), list)]
        keys += [k for k, v in data.items() if isinstance(v, list) and k not in keys]
        for key in keys:
            if data[key] and all(isinstance(r, dict) for r in data[key][:20]):
                records_key, data = key, data[key]
                break
    # 23.10.2026: כל הרשומות (לא רק 20 הראשונות) - רשומה שאינה מילון הפילה את כל הסריקה (TypeError)
    if not isinstance(data, list) or len(data) < 2 or not all(isinstance(r, dict) for r in data):
        return None
    try:
        df = pd.json_normalize(data)
    except (TypeError, ValueError):
        return None
    if df.shape[1] < 2:
        return None
    df.attrs["read"] = {"records": records_key} if records_key else {}
    return df


TABLE_EXT = (".csv", ".tsv", ".xlsx", ".xls", ".xlsm", ".json")


def load_table(folder: str, name: str, nrows: Optional[int] = None) -> Optional[pd.DataFrame]:
    """טבלה מהתיקייה כמו שהמנוע יקרא אותה: CSV / TSV / Excel (dataviz.sources.read_raw); טבלה רחבה (שנים ככותרות) -
    מומרת לשורות (melt_wide). None כשלא קריאה."""
    from dataviz.sources import melt_wide, read_raw, year_columns
    path = os.path.join(folder, name)
    if name.lower().endswith((".csv", ".tsv")):
        df = read_csv(path, nrows=nrows)
    elif name.lower().endswith(".json"):
        df = read_json_table(path)
    else:
        try:
            df = read_raw({"path": name}, folder)
        except (OSError, ValueError, ImportError, zipfile.BadZipFile, KeyError):   # 23.10.2026: Excel פגום / חלקי
            return None
    if df is not None and len(year_columns(df.columns)) >= 3:
        read = df.attrs.get("read", {})
        df = melt_wide(df)
        df.attrs["wide"] = True
        df.attrs["read"] = read
    elif df is not None and len(df.columns) >= 4:   # ישויות כעמודות (month, USD, EUR, GBP) - הופך לשורות
        from dataviz.sources import melt_entity_columns
        time = cols.time_column(df)
        if time and cols.entity_column(df, time["column"]) is None and cols._entity_columns(df, time["column"]):
            read = df.attrs.get("read", {})
            df = melt_entity_columns(df, time["column"])
            df.attrs["entity_columns"] = True
            df.attrs["read"] = read
    return df


def _headerless_events(df: pd.DataFrame) -> bool:
    """אירועים בלי שורת כותרת: שתי עמודות, ו"הכותרת" עצמה היא תאריך וטקסט."""
    if df.shape[1] != 2:
        return False
    first, second = str(df.columns[0]), str(df.columns[1])
    return pd.notna(cols.parse_times(pd.Series([first])).iloc[0]) and not second.replace(".", "").isdigit()


def _doc_hint(name: str, docs: str) -> str:
    """מה SOURCES.md אומר על הקובץ, מהמשפטים שמזכירים את שמו: engine (הנתונים של הפרק) / unused / check."""
    stem = os.path.splitext(name)[0].lower()
    # ג13: משפט מזכיר את הקובץ כשיש בו השם המלא, או השם בלי הסיומת כמילה שלמה - רק כשהוא לא מילה רגילה (data.csv -> "data"
    # הופיע ב-"Rows with missing data are not used", וקובץ הנתונים היחיד סומן "לא בשימוש")
    alone = re.compile(rf"(?<![\w.-]){re.escape(stem)}(?![\w-])") if re.search(r"[_\-\d]", stem) else None
    sentences = [s.lower() for s in re.split(r"(?<=[.;!?])\s+|\n", docs)
                 if name.lower() in s.lower() or (alone is not None and alone.search(s.lower()))]
    text = " ".join(sentences)
    if re.search(r"engine data|engine-ready|used by config|the episode uses|הנתונים של הפרק", text):
        return "engine"
    if re.search(r"unused|not used|לא בשימוש|not part of", text):
        return "raw_unused"
    if re.search(r"\bcheck\b|validation|sanity|reconcil|בדיקה", text):
        return "check"
    return ""


def classify(folder: str, name: str, docs: str = "") -> Dict[str, Any]:
    path = os.path.join(folder, name)
    low = name.lower()
    base = {"name": name, "columns": [], "rows": 0}
    if low.endswith((".md", ".txt", ".pdf", ".docx")):
        return {**base, "kind": "docs", "confidence": 0.95, "reason": "מסמך (טקסט / מקורות)"}
    if low.endswith((".yaml", ".yml", ".geojson")) or (low.endswith(".json") and read_json_table(path) is None):
        return {**base, "kind": "config", "confidence": 0.9, "reason": "קובץ הגדרות / מפה"}
    if not low.endswith(TABLE_EXT):
        return {**base, "kind": "other", "confidence": 0.6, "reason": "לא קובץ טבלה"}
    df = load_table(folder, name, nrows=5000 if os.path.getsize(path) > MAX_READ_BYTES else None)
    if df is None:
        return {**base, "kind": "other", "confidence": 0.5, "reason": "טבלה לא קריאה"}
    if df.empty and not ("event" in low or {"date", "label"} <= {str(c).lower() for c in df.columns}):
        return {**base, "kind": "other", "confidence": 0.5, "reason": "טבלה ריקה"}
    columns = [str(c) for c in df.columns]
    base = {"name": name, "columns": columns, "rows": int(len(df))}
    hint = _doc_hint(name, docs)
    words = cols._words(os.path.splitext(name)[0])
    lowered = [c.lower() for c in columns]
    event_headers = {"date", "label", "text", "source", "image", "days", "kind", "תאריך", "אירוע", "תיאור", "כותרת", "הערה", "מקור"}
    if "event" in words or "events" in words or "אירועים" in name or (
            set(lowered) <= event_headers and set(lowered) & {"label", "אירוע", "תיאור", "כותרת"} and len(lowered) >= 2):
        return {**base, "kind": "events", "confidence": 0.95, "reason": "תאריך + תווית - קובץ אירועים"}
    if _headerless_events(df):
        return {**base, "kind": "events", "confidence": 0.75, "headerless": True, "reason": "תאריך וטקסט בכל שורה, בלי שורת כותרת - אירועים"}
    if "unused" in words or hint == "raw_unused":
        return {**base, "kind": "raw_unused", "confidence": 0.95 if "unused" in words else 0.8,
                "reason": "השם מסומן UNUSED" if "unused" in words else "SOURCES.md אומר שהקובץ לא בשימוש"}
    if "check" in words or hint == "check" or ("diff" in lowered and any("sum" in c or "total" in c for c in lowered)):
        return {**base, "kind": "check", "confidence": 0.9 if "check" in words else 0.75,
                "reason": "קובץ בדיקה (סכום מול סך רשמי / diff)" if "check" not in words else "השם מסומן check"}
    if "weight" in words or "weights" in words or any(c.startswith("weight") for c in lowered):
        return {**base, "kind": "weights", "confidence": 0.85, "reason": "משקלות פיזור"}
    if "raw" in words and hint != "engine":
        return {**base, "kind": "raw_unused", "confidence": 0.7, "reason": "השם מסומן raw - כנראה המקור הגולמי של קובץ נקי אחר"}
    roles = cols.analyze(df, docs, name)
    roles["read"] = dict(df.attrs.get("read") or {})
    if df.attrs.get("entity_columns") and roles.get("entity"):
        roles["entity_columns"] = True
        roles["entity"]["reason"] = f"כל עמודה היא ישות ({', '.join(roles['entity'].get('names', [])[:5])}) - הופך לשורות"
    if df.attrs.get("wide") and roles["time"]:
        roles["wide"] = True
        roles["time"]["reason"] = "טבלה רחבה - השנים הן כותרות העמודות (הופכת לשורות)"
    if roles["time"] and roles["value"]:
        from dataviz.smart.kinds import guess_kind
        roles["kind"] = guess_kind(roles["value"]["column"], name, roles["unit"], df, roles["time"]["column"],
                                   roles["entity"]["column"] if roles["entity"] else None)
        return {**base, "kind": "series", "confidence": round(min(roles["time"]["confidence"], roles["value"]["confidence"]), 2),
                "reason": "יש עמודת זמן ועמודת ערך" + ("; SOURCES.md: אלה הנתונים של הפרק" if hint == "engine" else ""),
                "roles": roles, "engine": hint == "engine"}
    return {**base, "kind": "other", "confidence": 0.5, "reason": "אין עמודת זמן או ערך מספרי"}


def scan_folder(folder: str) -> Dict[str, Any]:
    """{folder, docs, files: [{name, kind, label, confidence, reason, columns, rows, roles?}]} - הסדרות קודם."""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise FileNotFoundError(folder)
    docs = read_docs(folder)
    files = []
    for name in sorted(os.listdir(folder)):
        if name.startswith(".") or not os.path.isfile(os.path.join(folder, name)):
            continue
        item = classify(folder, name, docs)
        item["label"] = KIND_LABELS[item["kind"]]
        files.append(item)
    order = {k: i for i, k in enumerate(KINDS)}
    files.sort(key=lambda f: (order[f["kind"]], f["name"]))
    return {"folder": folder, "docs": docs, "files": files}
