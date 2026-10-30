# dataviz/smart/events.py
#
# 20.10.2026: הצעות לאירועים בתאריכים החזקים - כל הצעה "צריכה אישור" ועם מקור, ושום דבר לא נכנס לפרק בלי לחיצה של
# המשתמש. שלושה מקורות: (1) events.csv שכבר בתיקייה (נכתב ביד - מוצג כמו שהוא); (2) ספרייה קטנה של אירועים ידועים עם
# מקור, ליד רגע חזק (עד שנה וחצי); (3) Gemini - רק דרך כללי המכסה הקיימים (QuotaWatch: מפסק אחרי כשלי מכסה), ורק עם
# העובדות שחושבו - הצעה בלי מקור או רחוקה מהרגע נזרקת. בלי Gemini - רק (1) ו-(2).
import json
import os
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from utils.media.gemini_quota import QuotaWatch

MODEL_NAME = "gemini-flash-latest"
NEAR_DAYS = 550
_QUOTA = QuotaWatch()

# אירועים ידועים (תאריך, תווית, מקור, נושאים) - רק עובדות מוכרות; הצעה רק כשהנושא של הפרק מתאים, ועדיין צריכה אישור.
# "israel" - אירוע ישראלי: רק לפרק על ישראל
LIBRARY = [
    ("1948-05-14", "הקמת מדינת ישראל", "ויקיפדיה: הכרזת העצמאות", {"israel", "immigration", "population", "politics"}),
    ("1950-07-05", "חוק השבות", "ויקיפדיה: חוק השבות", {"israel", "immigration"}),
    ("1967-06-05", "מלחמת ששת הימים", "ויקיפדיה: מלחמת ששת הימים", {"israel", "population", "politics", "economy"}),
    ("1973-10-06", "מלחמת יום כיפור", "ויקיפדיה: מלחמת יום הכיפורים", {"israel", "politics", "economy"}),
    ("1977-05-17", "המהפך - הליכוד עולה לשלטון", "ויקיפדיה: הבחירות לכנסת התשיעית", {"israel", "politics"}),
    ("1985-07-01", "התוכנית לייצוב המשק", "ויקיפדיה: התוכנית לייצוב המשק", {"israel", "economy", "prices"}),
    ("1989-11-09", "נפילת חומת ברלין", "ויקיפדיה: נפילת חומת ברלין", {"world", "politics", "sports"}),
    ("1990-01-01", "העלייה הגדולה מברית המועצות", "ויקיפדיה: העלייה מברית המועצות בשנות ה-90", {"israel", "immigration", "population", "housing"}),
    ("1991-12-26", "פירוק ברית המועצות", "ויקיפדיה: פירוק ברית המועצות", {"world", "immigration", "sports", "politics"}),
    ("2000-03-10", "התפוצצות בועת הדוט-קום", "ויקיפדיה: בועת הדוט-קום", {"world", "tech", "economy"}),
    ("2000-09-28", "האינתיפאדה השנייה", "ויקיפדיה: האינתיפאדה השנייה", {"israel", "economy", "politics"}),
    ("2008-09-15", "קריסת ליהמן ברדרס - המשבר הפיננסי העולמי", "ויקיפדיה: המשבר הפיננסי העולמי", {"world", "economy", "tech", "housing", "prices", "transport"}),
    ("2011-07-14", "מחאת האוהלים", "ויקיפדיה: המחאה החברתית בישראל", {"israel", "housing", "prices"}),
    ("2020-03-11", "הכרזת ארגון הבריאות העולמי על מגפת הקורונה", "WHO: הכרזת מגפה, 11.3.2020",
     {"world", "economy", "health", "tech", "housing", "prices", "transport", "sports", "immigration"}),
    ("2022-02-24", "פלישת רוסיה לאוקראינה", "ויקיפדיה: הפלישה הרוסית לאוקראינה", {"world", "prices", "economy", "immigration"}),
    ("2023-10-07", "מלחמת חרבות ברזל", "ויקיפדיה: מלחמת חרבות ברזל", {"israel", "economy", "housing", "politics", "population"}),
]
TOPIC_RULES = {
    "israel": r"israel|ישראל|knesset|כנסת|aliyah|עלייה|עולים|הלמ\"ס|\bcbs\b|district|מחוז|city_population|regulated_prices",
    "economy": r"gdp|economy|export|wage|income|תמ\"ג|כלכל|יצוא|שכר",
    "prices": r"price|cost|inflation|מחיר|יוקר|מדד",
    "housing": r"housing|dwelling|דיור|דירות",
    "politics": r"knesset|election|seats|party|כנסת|בחירות|מפלג",
    "immigration": r"aliyah|immigra|עלייה|עולים",
    "population": r"population|אוכלוסי|תושבים",
    "health": r"health|life_expectancy|expectancy|תוחלת|בריאות",
    "tech": r"hightech|high-tech|\btech|הייטק|טכנולוגי",
    "sports": r"olymp|medal|אולימפ|מדלי",
    "transport": r"vehicle|transport|rail|רכב|תחבורה",
}


def topics(folder: str, text: str = "") -> set:
    """הנושאים של הפרק - משם התיקייה, שמות הקבצים והעמודות, ו-SOURCES.md."""
    from dataviz.smart.scan import read_docs
    names = " ".join(os.listdir(folder)) if os.path.isdir(folder) else ""
    blob = f"{os.path.basename(os.path.normpath(folder))} {names} {text} {read_docs(folder)[:3000]}".lower()
    found = {tag for tag, pattern in TOPIC_RULES.items() if re.search(pattern, blob)}
    return found | ({"world"} if found - {"israel"} else set())

PROMPT = """אתה עוזר מחקר לסרטון נתונים. הנושא: "{topic}".
ברשימה רגעים חזקים בנתונים (תאריך ועובדה שחושבה). לכל רגע שיש לו הסבר היסטורי ידוע - הצע אירוע אמיתי אחד קרוב אליו
(עד שנה וחצי), עם מקור (שם האתר או המסמך). אל תמציא מספרים, ואל תציע אירוע כשאינך בטוח.
החזר JSON בלבד: [{{"date": "YYYY-MM-DD", "label": "...", "source": "...", "moment": "YYYY-MM-DD"}}].
הרגעים:
{moments}"""


def _near(date: str, moments: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    t = pd.Timestamp(date)
    close = [m for m in moments if abs((pd.Timestamp(m["date"]) - t).days) <= NEAR_DAYS]
    return min(close, key=lambda m: abs((pd.Timestamp(m["date"]) - t).days)) if close else None


def folder_events(folder: str) -> List[Dict[str, Any]]:
    """events.csv שכבר בתיקייה."""
    from dataviz.smart.scan import read_csv
    path = os.path.join(folder, "events.csv")
    df = read_csv(path) if os.path.isfile(path) else None
    if df is None or df.empty or not {"date", "label"} <= set(df.columns):
        return []
    return [{"date": str(r["date"]), "label": str(r["label"]), "source": "events.csv בתיקייה", "origin": "folder"} for _, r in df.iterrows()]


def _gemini(prompt: str) -> str:
    from google import genai

    from utils.shared.secrets_vault import get_secret
    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY לא מוגדר")
    return str(genai.Client(api_key=key).models.generate_content(model=MODEL_NAME, contents=prompt).text or "")


def _parse(text: str) -> List[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    data = json.loads(text.strip())
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def suggest(folder: str, moments: Sequence[Mapping[str, Any]], start: str, end: str, topic: str = "",
            ask: Optional[Callable[[str], str]] = None, use_gemini: bool = True, text: str = "") -> Dict[str, Any]:
    """{existing: [...], suggestions: [{date, label, source, moment, origin, needs_approval}], source: library/gemini, warning}."""
    existing = folder_events(folder)
    taken = {e["date"][:7] for e in existing}
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    strong = [m for m in moments if m.get("strength", 0) >= 1.5]
    suggestions: List[Dict[str, Any]] = []

    def add(date: str, label: str, source: str, origin: str) -> None:
        try:
            t = pd.Timestamp(date)
        except (ValueError, TypeError):
            return
        moment = _near(date, strong)
        if not (lo <= t <= hi) or moment is None or not str(source).strip() or date[:7] in taken:
            return
        taken.add(date[:7])
        suggestions.append({"date": t.strftime("%Y-%m-%d"), "label": " ".join(str(label).split())[:120], "source": str(source)[:200],
                            "moment": moment["date"], "moment_text": moment["text"], "origin": origin, "needs_approval": True})

    tags = topics(folder, text)
    for date, label, source, event_tags in LIBRARY:
        subject = event_tags - {"israel", "world"}
        if ("israel" in event_tags and "israel" not in tags) or not (subject & tags):
            continue   # אירוע ישראלי לפרק לא על ישראל, או נושא אחר
        add(date, label, source, "library")
    warning = ""
    origin = "library"
    if use_gemini and strong:
        if _QUOTA.should_skip_gemini():
            warning = "Gemini בהפסקה אחרי כשלי מכסה - רק הספרייה."
        else:
            prompt = PROMPT.format(topic=topic, moments="\n".join(f"- {m['date']}: {m['text']}" for m in strong[:8]))
            warning = _QUOTA.gemini_called() or ""
            try:
                items = _parse((ask or _gemini)(prompt))
                _QUOTA.gemini_succeeded()
                origin = "gemini"
                for item in items:
                    add(str(item.get("date") or ""), str(item.get("label") or ""), str(item.get("source") or ""), "gemini")
            except Exception as e:   # כל כשל - רק הספרייה; האירועים לא תלויים ב-Gemini
                warning = _QUOTA.gemini_failed(e) or f"Gemini לא זמין ({str(e)[:100]}) - רק הספרייה."
    suggestions.sort(key=lambda s: s["date"])
    return {"existing": existing, "suggestions": suggestions, "source": origin, "warning": warning}
