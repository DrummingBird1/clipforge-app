# dataviz/web/narration_draft.py
#
# 20.10.2026: טיוטת תסריט קריינות מהנתונים - הרגעים החזקים (שיאים, החלפות מקום ראשון, הימים עם התוספת הגדולה, והסוף)
# עם הזמן שלהם בסרטון, ומשפט קצר לכל אחד מ-Gemini. התוצאה היא טקסט לעריכה (story.script - תאריך + משפט) שהקריינות
# הקיימת מקריאה ברגע הזה (dataviz/narration.py, "script"). Gemini לפי הכללים הקיימים: utils.media.gemini_quota (מפסק
# אחרי כשלי מכסה רצופים, צינון). בלי מפתח, עם מפסק פתוח או בכשל - טיוטה מקומית פשוטה מאותם רגעים.
import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from utils.media.gemini_quota import QuotaWatch

MODEL_NAME = "gemini-flash-latest"
MAX_MOMENTS = 12
_QUOTA = QuotaWatch()   # לכל השרת: אחרי 3 כשלי מכסה רצופים לא קוראים ל-Gemini 5 דקות

PROMPT = """אתה כותב קריינות קצרה לסרטון נתונים ביוטיוב, בעברית טבעית ומדוברת.
הסרטון: "{title}". השאלה שהוא עונה עליה: "{question}".
לכל רגע ברשימה כתוב משפט אחד (עד 18 מילים) שמספר מה קורה, בלי להמציא מספרים שלא ברשימה.
החזר JSON בלבד: רשימה של אובייקטים {{"date": "YYYY-MM-DD", "text": "..."}} - אותם תאריכים, באותו סדר.
הרגעים:
{moments}"""


def moments(episode: Any, plan: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """הרגעים החזקים של הפרק, לפי הזמן בסרטון: שיא חדש, החלפת המקום הראשון, שלושת הימים עם התוספת הגדולה, והסוף."""
    from dataviz.web.preview import _lock
    with _lock:   # matplotlib נטען רק בתוך המנעול של התצוגה (שני threads שמייבאים אותו יחד נתקעים)
        from dataviz.charts.base import format_number
    fps = float(episode.config["video"]["fps"]) or 1.0
    main = [(i, f) for i, f in enumerate(plan) if f.get("k") == "main"]
    if not main:
        return []
    found: Dict[str, Dict[str, Any]] = {}

    def add(index: int, frame: Mapping[str, Any], kind: str, fact: str, day: Optional[str] = None) -> None:
        """רגע אחד לתאריך, ולא שניים בטווח של שנייה וחצי (הראשון שנוסף נשאר - קודם הקפיצות, אחר כך שיאים ומקום ראשון)."""
        day = day or episode.dates[min(int(frame["x"]), len(episode.dates) - 1)].strftime("%Y-%m-%d")
        seconds = round(index / fps, 1)
        if day in found or any(abs(m["seconds"] - seconds) < 1.5 for m in found.values()):
            return
        found[day] = {"date": day, "seconds": seconds, "kind": kind, "fact": fact}

    last_index, last = main[-1]
    top = [f"{e} ({format_number(float(v))})" for e, v, _p in last["bars"][:3]]
    add(last_index, last, "end", "בסוף: " + ", ".join(top))
    totals = episode.daily.sum(axis=1)
    for day_index in sorted(range(len(totals)), key=lambda d: -float(totals[d]))[:3]:
        if float(totals[day_index]) <= 0:
            continue
        index, frame = next(((i, f) for i, f in main if float(f["x"]) >= day_index), main[-1])   # הפריים שמגיע ליום
        add(index, frame, "jump", f"קפיצה: נוספו {format_number(float(totals[day_index]))} ביום אחד",
            episode.dates[day_index].strftime("%Y-%m-%d"))
    previous_leader, previous_toast = None, None
    for index, frame in main:
        toast = (frame.get("toast") or [None])[0]
        if toast and toast != previous_toast:
            add(index, frame, "record", str(toast))
        previous_toast = toast
        leader = frame.get("leader")
        if leader is not None and previous_leader is not None and leader != previous_leader:
            add(index, frame, "lead", f"{leader} עוקף את {previous_leader} ועובר למקום הראשון")
        previous_leader = leader
    return sorted(found.values(), key=lambda m: m["seconds"])[:MAX_MOMENTS]


def from_story(episode: Any, plan: Sequence[Mapping[str, Any]], story_moments: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """20.10.2026 (עורך הגרפים החכם): הרגעים של "מוצא הסיפור" (dataviz/smart/story.py) - תאריך + עובדה - עם הזמן שלהם
    בסרטון: הפריים הראשון של הגרף שמגיע לתאריך."""
    import pandas as pd
    fps = float(episode.config["video"]["fps"]) or 1.0
    main = [(i, f) for i, f in enumerate(plan) if f.get("k") == "main"]
    if not main:
        return []
    found: List[Dict[str, Any]] = []
    for moment in sorted(story_moments, key=lambda m: m["date"])[:MAX_MOMENTS]:
        target = pd.Timestamp(moment["date"])
        index, frame = next(((i, f) for i, f in main
                             if episode.dates[min(int(f["x"]), len(episode.dates) - 1)] >= target), main[-1])
        day = episode.dates[min(int(frame["x"]), len(episode.dates) - 1)].strftime("%Y-%m-%d")
        if all(m["date"] != day for m in found):
            found.append({"date": day, "seconds": round(index / fps, 1), "kind": moment.get("kind", ""), "fact": str(moment["text"])})
    return found


def _gemini(prompt: str) -> str:
    from google import genai

    from utils.shared.secrets_vault import get_secret
    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY לא מוגדר")
    client = genai.Client(api_key=key)
    return str(client.models.generate_content(model=MODEL_NAME, contents=prompt).text or "")


def _parse(text: str, dates: List[str]) -> Dict[str, str]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    data = json.loads(text.strip())
    lines = {str(item.get("date")): " ".join(str(item.get("text") or "").split())[:200] for item in data if isinstance(item, dict)}
    return {d: t for d, t in lines.items() if d in dates and t}


def draft(folder: str, overrides: Mapping[str, Any], ask: Optional[Any] = None,
          story_moments: Optional[Sequence[Mapping[str, Any]]] = None) -> Dict[str, Any]:
    """{source: gemini / local, lines: [{date, seconds, kind, text}], warning}. ask = פונקציה שמקבלת prompt (טסטים).
    story_moments - הרגעים של "מוצא הסיפור" במקום החישוב המקומי (20.10.2026)."""
    from dataviz.episode import load_episode
    from dataviz.plan import build_plan
    episode = load_episode(folder, dict(overrides))
    plan = build_plan(episode, "full")
    found = from_story(episode, plan, story_moments) if story_moments else moments(episode, plan)
    lines = [{**m, "text": m["fact"]} for m in found]
    if not found:
        return {"source": "local", "lines": [], "warning": "אין רגעים בולטים בנתונים."}
    if _QUOTA.should_skip_gemini():
        return {"source": "local", "lines": lines, "warning": "Gemini בהפסקה אחרי כשלי מכסה - טיוטה מקומית."}
    cfg = episode.config
    prompt = PROMPT.format(title=cfg.get("title", ""), question=(cfg.get("intro") or {}).get("question", ""),
                           moments="\n".join(f"- {m['date']}: {m['fact']}" for m in found))
    warning = _QUOTA.gemini_called()
    try:
        texts = _parse((ask or _gemini)(prompt), [m["date"] for m in found])
    except Exception as e:   # כל כשל (מפתח, רשת, מכסה, JSON) - הטיוטה המקומית; הקריינות לא תלויה ב-Gemini
        return {"source": "local", "lines": lines, "warning": _QUOTA.gemini_failed(e) or f"Gemini לא זמין ({str(e)[:120]}) - טיוטה מקומית."}
    _QUOTA.gemini_succeeded()
    from dataviz.smart.texts import check_numbers, numbers
    result, invented = [], 0
    for line in lines:   # 20.10.2026: משפט עם מספר שלא בעובדה של הרגע - העובדה עצמה במקומו (בלי מספרים מומצאים)
        text = texts.get(line["date"], line["text"])
        if check_numbers(text, numbers(line["fact"]) + numbers(line["date"])):
            invented += 1
            text = line["fact"]
        result.append({**line, "text": text})
    if invented:
        warning = (warning + " " if warning else "") + f"{invented} משפטים של Gemini הוחלפו בעובדה - היה בהם מספר שלא בנתונים."
    return {"source": "gemini", "lines": result, "warning": warning}
