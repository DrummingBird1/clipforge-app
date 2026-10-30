# dataviz/smart/texts.py
#
# 20.10.2026: טקסטים לטיוטה - כמה אפשרויות לכותרת, כותרת משנה ופתיח (שאלה), בעברית ובאנגלית, רק מעובדות שחושבו מהנתונים
# (שנים, מובילים, ערכים). בלי Gemini - כללים (פריט 20); Gemini רק ליטוש, דרך כללי המכסה, ורק עם העובדות (פריט 18).
# check_numbers: כל מספר בטקסט שנוצר חייב להופיע בעובדות - טקסט עם מספר שלא חושב נזרק.
import json
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from utils.media.gemini_quota import QuotaWatch

MODEL_NAME = "gemini-flash-latest"
_QUOTA = QuotaWatch()

# נושא הפרק לפי עמודת הערך / היחידות / שם התיקייה: (תבנית, עברית, אנגלית)
TOPICS = [
    (r"immigra|aliyah|עולים|עלייה", "העלייה לישראל", "immigration to Israel"),
    (r"medal|מדלי", "המדליות האולימפיות", "Olympic medals"),
    (r"seats|knesset|מושבים", "המושבים בכנסת", "Knesset seats"),
    (r"dwelling|housing|דירות", "מחירי הדירות", "home prices"),
    (r"gdp|per_capita|תמ\"ג", "התמ\"ג לנפש", "GDP per capita"),
    (r"expectancy|תוחלת", "תוחלת החיים", "life expectancy"),
    (r"export|יצוא", "היצוא", "exports"),
    (r"vehicle|רכב", "כלי הרכב", "vehicles"),
    (r"population|אוכלוסי|תושבים", "האוכלוסייה", "population"),
    (r"temperature|טמפרטורה|climate|אקלים", "האקלים", "the climate"),
    (r"price|מחיר", "המחירים", "prices"),
]
# מה הישויות: (תבנית בשם הקובץ / העמודה, עברית, אנגלית)
ENTITY_WORDS = [
    (r"countr|oecd|noc|iso3|מדינ", "מדינות", "countries"),
    (r"city|cities|locality|עיר|ערים", "ערים", "cities"),
    (r"party|knesset|מפלג", "מפלגות", "parties"),
    (r"continent|יבשת", "יבשות", "continents"),
    (r"district|region|מחוז", "מחוזות", "districts"),
    (r"product|prices|מוצר", "מוצרים", "products"),
    (r"branch|category|type|ענף|סוג", "סוגים", "types"),
]


def with_prefix(letter: str, topic: str) -> str:
    """ב/ל + נושא עם ה' הידיעה: "במחירים" ולא "בהמחירים"."""
    return letter + (topic[1:] if topic.startswith("ה") else topic)


def cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def english_names(folder: str, f: Mapping[str, Any]) -> Dict[str, str]:
    """שם עברי -> אנגלי מעמודה *_en באותו קובץ (country_en, locality_en, party_en), כשהיא אחד-לאחד."""
    from dataviz.smart.scan import load_table
    entity = (f["roles"].get("entity") or {}).get("column")
    columns = [c for c in f["columns"] if c.lower().endswith("_en") and c != entity]
    if not entity or not columns:
        return {}
    df = load_table(folder, f["name"])
    if df is None:
        return {}
    pairs = df[[entity, columns[0]]].dropna().astype(str).drop_duplicates()
    if pairs[entity].duplicated().any():
        return {}
    return dict(zip(pairs[entity], pairs[columns[0]]))


def _match(text: str, table: Sequence[tuple]) -> tuple:
    low = text.lower()
    return next(((he, en) for pattern, he, en in table if re.search(pattern, low)), ("", ""))


def facts(analysis: Mapping[str, Any], folder_name: str = "", folder: str = "") -> Dict[str, Any]:
    """העובדות שמהן נבנים הטקסטים - שנים, מובילים, ערכים, נושא - ורשימת המספרים המותרים בטקסט."""
    from dataviz.smart.story import unit_parts
    series = analysis.get("series") or []
    story = analysis.get("story") or {}
    main = series[0]["roles"] if series else {}
    blob = " ".join([folder_name] + [f["name"] for f in series] + [str((main.get("value") or {}).get("column") or "")]
                    + list(series[0]["columns"] if series else []))
    topic_he, topic_en = _match(blob, TOPICS)
    if not topic_he and series:
        topic_he = topic_en = str((main.get("value") or {}).get("column") or "").replace("_", " ")
    entity_he, entity_en = _match(blob, ENTITY_WORDS)
    start, end = str(story.get("start") or "")[:4], str(story.get("end") or "")[:4]
    leads = [m for m in story.get("moments") or [] if m["kind"] == "lead"]
    n_entities = sum(max(1, (f["roles"].get("entity") or {}).get("unique", 1)) for f in series)
    prefix, suffix = unit_parts(main.get("unit"))
    result = {"topic_he": topic_he, "topic_en": topic_en, "entity_he": entity_he, "entity_en": entity_en,
              "start": start, "end": end, "entities": n_entities, "leads": len(leads),
              "first_leader": story.get("leader_start") or "", "last_leader": story.get("leader_end") or "",
              "race": (story.get("type") or {}).get("value") == "race", "moments": story.get("moments") or [],
              "prefix": prefix, "suffix": suffix}
    names_en = english_names(folder, series[0]) if folder and series else {}
    result["first_leader_en"] = names_en.get(result["first_leader"], "")
    result["last_leader_en"] = names_en.get(result["last_leader"], "")
    allowed = {start, end, str(n_entities), str(len(leads))}
    for m in story.get("moments") or []:
        allowed |= set(numbers(m["text"]))
        allowed.add(m["date"][:4])
    result["allowed"] = sorted(n for n in allowed if n)
    return result


NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> List[str]:
    return [n.replace(",", "") for n in NUMBER_RE.findall(str(text))]


def check_numbers(text: str, allowed: Sequence[str]) -> List[str]:
    """המספרים בטקסט שלא חושבו מהנתונים (ריק = תקין). 1-2 ספרות בודדות (מספרים סידוריים קטנים) לא נבדקים כשהם ברשימה."""
    pool = {a.replace(",", "") for a in allowed}
    return [n for n in numbers(text) if n not in pool]


def rule_texts(f: Mapping[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    """{titles, subtitles, hooks}: לכל אחת [{he, en}] - רק מהעובדות."""
    topic_he, topic_en = f["topic_he"] or "הנתונים", f["topic_en"] or "the data"
    span = f"{f['start']}-{f['end']}" if f["start"] and f["end"] else ""
    titles = [{"he": f"{topic_he}, {span}".strip(", "), "en": f"{cap(topic_en)}, {span}".strip(", ")}]
    if f.get("race") and f["entity_he"]:
        titles.insert(0, {"he": f"מי מוביל {with_prefix('ב', topic_he)}?", "en": f"Who leads in {topic_en}?"})
        titles.append({"he": f"{f['entities']} {f['entity_he']} במרוץ על {topic_he}", "en": f"{f['entities']} {f['entity_en']} racing for {topic_en}"})
    elif f["entities"] <= 2:
        titles.append({"he": f"{topic_he}: מה השתנה מאז {f['start']}?", "en": f"{cap(topic_en)}: what changed since {f['start']}?"})
    subtitles = [{"he": (f"{topic_he} לפי {f['entity_he']}, {span}" if f["entity_he"] else f"{topic_he}, {span}").strip(", "),
                  "en": (f"{cap(topic_en)} by {f['entity_en']}, {span}" if f["entity_en"] else f"{cap(topic_en)}, {span}").strip(", ")}]
    hooks = []
    if f.get("race") and f["first_leader"] and f["last_leader"] and f["first_leader"] != f["last_leader"]:
        en = (f"In {f['start']}, {f['first_leader_en']} was first. And in {f['end']}?" if f.get("first_leader_en")
              else f"Who was first in {f['start']} - and who is first in {f['end']}?")
        hooks.append({"he": f"ב-{f['start']} במקום הראשון: {f['first_leader']}. ומה ב-{f['end']}?", "en": en})
    hooks.append({"he": f"מה קרה {with_prefix('ל', topic_he)} מאז {f['start']}?", "en": f"What happened to {topic_en} since {f['start']}?"})
    return {"titles": titles, "subtitles": subtitles, "hooks": hooks}


def _gemini(prompt: str) -> str:
    from google import genai

    from utils.shared.secrets_vault import get_secret
    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY לא מוגדר")
    return str(genai.Client(api_key=key).models.generate_content(model=MODEL_NAME, contents=prompt).text or "")


PROMPT = """כתוב כותרות לסרטון נתונים ביוטיוב. מותר להשתמש רק בעובדות שלמטה - בלי להמציא מספרים, שמות או אירועים.
החזר JSON בלבד: {{"titles": [{{"he": "...", "en": "..."}}], "hooks": [{{"he": "...", "en": "..."}}]}} - עד 3 מכל אחד.
העובדות:
- נושא: {topic_he} / {topic_en}
- טווח: {start}-{end}; {entities} ישויות ({entity_he})
{moments}"""


def suggest_texts(f: Mapping[str, Any], ask: Optional[Callable[[str], str]] = None, use_gemini: bool = False) -> Dict[str, Any]:
    """{titles, subtitles, hooks, source: rules/gemini, warning}. Gemini מוסיף אפשרויות; כל אפשרות עם מספר שלא חושב נזרקת."""
    base = rule_texts(f)
    result: Dict[str, Any] = {**base, "source": "rules", "warning": ""}
    if not use_gemini:
        return result
    if _QUOTA.should_skip_gemini():
        result["warning"] = "Gemini בהפסקה אחרי כשלי מכסה - רק כותרות מכללים."
        return result
    prompt = PROMPT.format(**{k: f[k] for k in ("topic_he", "topic_en", "start", "end", "entities", "entity_he")},
                           moments="\n".join(f"- {m['date']}: {m['text']}" for m in f["moments"][:8]))
    result["warning"] = _QUOTA.gemini_called() or ""
    try:
        text = (ask or _gemini)(prompt).strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.startswith("json") else text
        data = json.loads(text.strip())
        _QUOTA.gemini_succeeded()
    except Exception as e:   # כל כשל - הכותרות מהכללים נשארות
        result["warning"] = _QUOTA.gemini_failed(e) or f"Gemini לא זמין ({str(e)[:100]}) - רק כותרות מכללים."
        return result
    dropped = 0
    for key in ("titles", "hooks"):
        for option in (data.get(key) or [])[:3] if isinstance(data, dict) else []:
            if not isinstance(option, dict) or not option.get("he"):
                continue
            if check_numbers(f"{option.get('he', '')} {option.get('en', '')}", f["allowed"]):
                dropped += 1
                continue
            result[key].insert(0, {"he": " ".join(str(option["he"]).split())[:100], "en": " ".join(str(option.get("en", "")).split())[:100], "ai": "1"})
    result["source"] = "gemini"
    if dropped:
        result["warning"] = f"{dropped} הצעות של Gemini נזרקו - היה בהן מספר שלא מופיע בנתונים."
    return result
