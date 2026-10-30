# dataviz/web/catalog.py
#
# 20.10.2026: קטלוג מקורות נתונים - רשימה קבועה של סדרות מהלמ"ס (API הסדרות), מהבנק העולמי ומה-OECD. בוחרים סדרה
# ורואים מה היא (מקור, טבלה / מדד, יחידות, תקופה, כתובת); ההורדה רק בלחיצה של המשתמש (שום הורדה שלא ביקש), רק מהכתובת
# הקבועה שבקטלוג (לא מהדפדפן), עם תקרת גודל - ואז הנתונים הופכים לפרק חדש או למקור נוסף בפרק קיים, עם SOURCES.md
# (מקור, כתובת, טבלה, תאריך גישה, יחידות). הטסטים מחליפים את BASES בשרת מזויף - אף טסט לא יוצא לרשת.
# 22.10.2026, אחרי הורדה אמיתית מכל המקורות (באישור המשתמש): OECD מחזיר 403 ל-User-Agent של Python-urllib ובלי
# תוויות מחזיר רק קודי מדינות; ב-API הסדרות של הלמ"ס (apis.cbs.gov.il) אין מדד מחירים בכלל - 120010 שם הוא מדד ייצור
# תעשייתי - אז מדד המחירים מגיע מ-API המדדים (api.cbs.gov.il), שמחזיר 100 קריאות לעמוד.
import csv
import io
import json
import os
import time
import urllib.parse
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from dataviz.web import episodes as de

MAX_BYTES = 5 * 1024 * 1024   # לכל ההורדה, כל העמודים יחד
TIMEOUT = 30
USER_AGENT = "ClipForge/1.0"
MAX_PAGES = 20                # הלמ"ס: 100 קריאות לעמוד; מדד המחירים מ-1951 - 10 עמודים
# הכתובות הבסיסיות של כל ספק (קבועות; טסטים מחליפים אותן בשרת מקומי מזויף)
BASES: Dict[str, str] = {
    "worldbank": "https://api.worldbank.org/v2",
    "oecd": "https://sdmx.oecd.org/public/rest/data",
    "cbs": "https://api.cbs.gov.il/index/data",
}
PROVIDERS: Dict[str, Dict[str, str]] = {
    "worldbank": {"name": "הבנק העולמי", "license": "CC BY 4.0 (World Bank Open Data)"},
    "oecd": {"name": "OECD", "license": "OECD Terms and Conditions (CC BY 4.0)"},
    "cbs": {"name": "הלמ\"ס", "license": "הלשכה המרכזית לסטטיסטיקה - שימוש עם ציון המקור"},
}
# 30.10.2026 (לפני ההפצה): המדינות של העולם קודם, ישראל נשארת ברשימה
WB_COUNTRIES = "USA;GBR;DEU;FRA;JPN;ISR"
OECD_COUNTRIES = "USA+GBR+DEU+FRA+JPN+ISR"

# id -> סדרה. path = החלק הקבוע של הכתובת אחרי BASES[provider]. kind: level / amount (לפי מה שהערך הוא)
CATALOG: List[Dict[str, Any]] = [
    {"id": "wb_population", "provider": "worldbank", "title": "אוכלוסייה", "units": "אנשים", "period": "year", "kind": "level",
     "table": "SP.POP.TOTL", "path": f"/country/{WB_COUNTRIES}/indicator/SP.POP.TOTL?format=json&per_page=20000&date=1960:2030"},
    {"id": "wb_gdp_per_capita", "provider": "worldbank", "title": "תוצר לנפש (דולר שוטף)", "units": "דולר", "period": "year", "kind": "level",
     "table": "NY.GDP.PCAP.CD", "path": f"/country/{WB_COUNTRIES}/indicator/NY.GDP.PCAP.CD?format=json&per_page=20000&date=1960:2030"},
    {"id": "wb_life_expectancy", "provider": "worldbank", "title": "תוחלת חיים בלידה", "units": "שנים", "period": "year", "kind": "level",
     "table": "SP.DYN.LE00.IN", "path": f"/country/{WB_COUNTRIES}/indicator/SP.DYN.LE00.IN?format=json&per_page=20000&date=1960:2030"},
    {"id": "wb_fertility", "provider": "worldbank", "title": "פריון כולל (ילדים לאישה)", "units": "ילדים לאישה", "period": "year", "kind": "level",
     "table": "SP.DYN.TFRT.IN", "path": f"/country/{WB_COUNTRIES}/indicator/SP.DYN.TFRT.IN?format=json&per_page=20000&date=1960:2030"},
    {"id": "wb_internet", "provider": "worldbank", "title": "משתמשי אינטרנט (% מהאוכלוסייה)", "units": "%", "period": "year", "kind": "level",
     "table": "IT.NET.USER.ZS", "path": f"/country/{WB_COUNTRIES}/indicator/IT.NET.USER.ZS?format=json&per_page=20000&date=1960:2030"},
    {"id": "wb_unemployment", "provider": "worldbank", "title": "שיעור אבטלה (% מכוח העבודה)", "units": "%", "period": "year", "kind": "level",
     "table": "SL.UEM.TOTL.ZS", "path": f"/country/{WB_COUNTRIES}/indicator/SL.UEM.TOTL.ZS?format=json&per_page=20000&date=1960:2030"},
    {"id": "oecd_unemployment_monthly", "provider": "oecd", "title": "שיעור אבטלה חודשי (OECD)", "units": "%", "period": "month", "kind": "level",
     "table": "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M", "path": f"/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/{OECD_COUNTRIES}..._Z.Y._T.Y_GE15..M?format=csvfilewithlabels"},
    {"id": "oecd_cpi_annual", "provider": "oecd", "title": "אינפלציה שנתית - מדד המחירים לצרכן (OECD)", "units": "%", "period": "year", "kind": "level",
     "table": "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL", "path": f"/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/{OECD_COUNTRIES}.A.N.CPI.PA._T.N.GY?format=csvfilewithlabels"},
    {"id": "cbs_cpi", "provider": "cbs", "title": "מדד המחירים לצרכן - כללי", "units": "נקודות מדד", "period": "month", "kind": "level",
     "table": "120010", "path": "/price?id=120010&format=json&download=false&lang=he"},
]
_BY_ID = {item["id"]: item for item in CATALOG}


def url_of(item: Dict[str, Any], lang: str = "he") -> str:
    """30.10.2026: הלמ"ס בשפת הממשק (lang=en מחזיר את שמות הסדרות באנגלית); לשאר הספקים אין פרמטר שפה."""
    path = item["path"].replace("lang=he", "lang=en") if item["provider"] == "cbs" and lang == "en" else item["path"]
    return BASES[item["provider"]] + path


WORLD_FIRST = {"worldbank": 0, "oecd": 1, "cbs": 2}


def list_catalog(query: str = "", lang: str = "he") -> List[Dict[str, Any]]:
    """30.10.2026: בממשק באנגלית המקורות העולמיים קודם (WORLD_FIRST); בעברית - הסדר של הקטלוג, כמו קודם."""
    q = str(query or "").strip().lower()
    rows = []
    for item in sorted(CATALOG, key=lambda i: WORLD_FIRST[i["provider"]]) if lang == "en" else CATALOG:
        provider = PROVIDERS[item["provider"]]
        text = f"{item['title']} {item['units']} {item['table']} {provider['name']} {item['provider']}".lower()
        if q and q not in text:
            continue
        rows.append({k: item[k] for k in ("id", "provider", "title", "units", "period", "kind", "table")} |
                    {"provider_name": provider["name"], "license": provider["license"], "url": url_of(item, lang)})
    return rows


def _download(url: str, opener: Optional[Callable[[str], Any]] = None, limit: int = MAX_BYTES) -> bytes:
    if opener is None:
        import urllib.request
        opener = lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT)  # noqa: E731
    try:
        with opener(url) as response:
            raw = response.read(limit + 1)
    except OSError as e:
        raise de.EpisodeError(f"ההורדה נכשלה: {str(e)[:200]}") from None
    if len(raw) > limit:
        raise de.EpisodeError(f"הקובץ גדול מ-{MAX_BYTES // (1024 * 1024)}MB - לא נשמר.")
    return raw


def _cbs_pages(url: str, opener: Optional[Callable[[str], Any]] = None) -> List[Any]:
    """הלמ"ס מחזיר 100 קריאות לעמוד, ו-paging.next_url לעמוד הבא - עוברים עליהם רק באותו אתר, עד MAX_PAGES ועד
    MAX_BYTES לכל העמודים יחד."""
    origin = urllib.parse.urlsplit(url)[:2]
    pages: List[Any] = []
    used = 0
    next_url: Optional[str] = url
    while next_url:
        if len(pages) == MAX_PAGES:
            raise de.EpisodeError(f"יותר מ-{MAX_PAGES} עמודים בתשובה - לא נשמר.")
        if urllib.parse.urlsplit(next_url)[:2] != origin:
            raise de.EpisodeError("הכתובת של העמוד הבא לא באותו אתר - לא נשמר.")
        raw = _download(next_url, opener, MAX_BYTES - used)
        used += len(raw)
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise de.EpisodeError("הקובץ שהורד לא נקרא: התשובה של הלמ\"ס היא לא JSON") from None
        pages.append(data)
        next_url = ((data.get("paging") or {}).get("next_url") or None) if isinstance(data, dict) else None
    return pages


def _rows_worldbank(raw: bytes) -> List[List[str]]:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        raise ValueError("תשובה לא צפויה מהבנק העולמי")
    return [[str(r["date"]), str((r.get("country") or {}).get("value") or r.get("countryiso3code")), str(r["value"])]
            for r in data[1] if isinstance(r, dict) and r.get("value") is not None]


def _rows_oecd(raw: bytes) -> List[List[str]]:
    table = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not table or "TIME_PERIOD" not in table[0] or "OBS_VALUE" not in table[0]:
        raise ValueError("תשובה לא צפויה מה-OECD (חסרות העמודות TIME_PERIOD / OBS_VALUE)")
    area = "Reference area" if "Reference area" in table[0] else "REF_AREA"
    return [[r["TIME_PERIOD"], r.get(area) or "", r["OBS_VALUE"]] for r in table if r.get("OBS_VALUE") not in (None, "")]


def _plain(value: float) -> str:
    """6 ספרות משמעותיות, בלי כתיב מדעי - ערכים משורשרים מלפני עשרות שנים קטנים מאוד."""
    text = f"{value:.6g}"
    return format(Decimal(text), "f") if "e" in text else text


def _rows_cbs(pages: List[Any]) -> Tuple[List[List[str]], str]:
    """API המדדים: כל קריאה בבסיס שהיה בתוקף בזמנה (currBase), והבסיס מתחלף כל שנתיים - כמו שהם, הקו "נופל" בכל
    החלפה. משרשרים לבסיס האחרון: בתוך בסיס הערכים כמו שפורסמו, ובמעבר לבסיס קודם - השינוי החודשי שהלמ"ס מפרסם
    (percent) של החודש הראשון בבסיס החדש. בלי percent במעבר - עוצרים שם (לא מערבבים בסיסים). מחזיר שורות והערה."""
    readings, name = [], ""
    for data in pages:
        months = data.get("month") if isinstance(data, dict) else None
        if not isinstance(months, list):
            raise ValueError("תשובה לא צפויה מהלמ\"ס (חסר month)")
        for series in months:
            name = name or str(series.get("name") or series.get("code") or "")
            for d in series.get("date") or []:
                base = d.get("currBase") or {}
                if base.get("value") is not None:
                    readings.append((int(d["year"]), int(d["month"]), float(base["value"]), str(base.get("baseDesc") or ""), d.get("percent")))
    readings.sort(reverse=True)   # מהחדש לישן
    rows: List[List[str]] = []
    factor = 1.0
    for i, (year, month, value, base, _percent) in enumerate(readings):
        if i and base != readings[i - 1][3]:
            newer = readings[i - 1]
            if newer[4] is None:
                break
            factor = newer[2] * factor / (1 + float(newer[4]) / 100) / value
        rows.append([f"{year}-{month:02d}", name, _plain(value * factor)])
    note = f"משורשר לבסיס האחרון ({readings[0][3]} = 100)" if readings else ""
    return rows, note


PARSERS: Dict[str, Callable[[bytes], List[List[str]]]] = {"worldbank": _rows_worldbank, "oecd": _rows_oecd}


def fetch_csv(item_id: Any, opener: Optional[Callable[[str], Any]] = None, lang: str = "he") -> Dict[str, Any]:
    """מוריד את הסדרה מהכתובת הקבועה שלה ומחזיר CSV אחיד: date,entity,value (שנה או YYYY-MM)."""
    item = _BY_ID.get(str(item_id or ""))
    if item is None:
        raise de.EpisodeError("סדרה לא מוכרת בקטלוג.", status=404)
    url = url_of(item, lang)
    pages = _cbs_pages(url, opener) if item["provider"] == "cbs" else None
    raw = b"" if pages is not None else _download(url, opener)
    note = ""
    try:
        if pages is not None:
            rows, note = _rows_cbs(pages)
        else:
            rows = PARSERS[item["provider"]](raw)
    except (ValueError, KeyError, TypeError) as e:
        raise de.EpisodeError(f"הקובץ שהורד לא נקרא: {str(e)[:200]}") from None
    if not rows:
        raise de.EpisodeError("לא היו נתונים בקובץ שהורד.")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["date", "entity", "value"])
    writer.writerows(sorted(rows))
    return {"item": item, "csv": out.getvalue(), "rows": len(rows), "entities": sorted({r[1] for r in rows}),
            "range": [min(r[0] for r in rows), max(r[0] for r in rows)], "note": note, "url": url}


def sources_md(item: Dict[str, Any], rows: int, note: str = "", url: str = "") -> str:
    provider = PROVIDERS[item["provider"]]
    return "\n".join([
        f"## {item['title']}", "",
        f"- מקור: {provider['name']}",
        f"- כתובת: {url or url_of(item)}",
        f"- טבלה / מדד: {item['table']}",
        f"- תאריך גישה: {time.strftime('%Y-%m-%d')}",
        f"- יחידות: {item['units']}",
        f"- תקופה: {'שנה' if item['period'] == 'year' else 'חודש'} · {rows} שורות",
        *([f"- הערה: {note}"] if note else []),
        f"- רישיון: {provider['license']}", "", ""])


def _mapping(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"time_column": "date", "period": item["period"], "value_column": "value", "group_column": "entity",
            "kind": item["kind"], "legend": "", "filename": item["id"] + ".csv"}


def to_new_episode(data_dir: str, item_id: Any, name: Any, title: Any = "", opener: Optional[Callable[[str], Any]] = None,
                   lang: str = "he") -> Dict[str, Any]:
    """הורדה (בלחיצה) -> פרק חדש (line_race) עם SOURCES.md בתיקייה שלו. שם קיים = 409, כמו בכל פרק חדש."""
    fetched = fetch_csv(item_id, opener, lang)
    item = fetched["item"]
    summary = de.create_episode(data_dir, {**_mapping(item), "name": str(name or ""), "title": str(title or item["title"]),
                                           "chart": "line_race", "csv_text": fetched["csv"]})
    with open(os.path.join(de.episodes_root(data_dir), summary["name"], "SOURCES.md"), "x", encoding="utf-8") as f:
        f.write("# מקורות\n\n" + sources_md(item, fetched["rows"], fetched["note"], fetched["url"]))
    return {**summary, "rows": fetched["rows"], "range": fetched["range"]}


def to_source(data_dir: str, item_id: Any, episode: Any, opener: Optional[Callable[[str], Any]] = None, lang: str = "he") -> Dict[str, Any]:
    """הורדה (בלחיצה) -> מקור נוסף בפרק קיים (dataviz.web.data.add_source - קובץ חדש תחת data/dataviz_overrides/<פרק>/),
    ו-SOURCES.md באותה תיקייה מקבל את הסדרה (תיקיית הפרק ו-config.yaml לא נכתבים)."""
    from dataviz.web import data as dd
    fetched = fetch_csv(item_id, opener, lang)
    item = fetched["item"]
    name = str(episode or "")
    result = dd.add_source(data_dir, name, item["id"] + ".csv", fetched["csv"], _mapping(item), confirm=True)
    folder = os.path.join(data_dir, de.OVERRIDES_DIRNAME, name)
    path = os.path.join(folder, "SOURCES.md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(("# מקורות שנוספו מהקטלוג\n\n" if new else "") + sources_md(item, fetched["rows"], fetched["note"], fetched["url"]))
    return {**result, "rows": fetched["rows"], "range": fetched["range"]}
