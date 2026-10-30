# dataviz/smart/package.py
#
# 20.10.2026: חבילת יוטיוב לטיוטה - כותרת (מהאפשרויות של texts), תיאור עם הרגעים החזקים (עובדות מחושבות בלבד), תגיות,
# פרקים (story.chapters - המנוע כבר הופך אותם לפרקי יוטיוב עם הזמנים האמיתיים) וקרדיטים משורות המקור ב-SOURCES.md.
# הכל שדות בקובץ השינויים (publish.title / description / hashtags, outro.credits, story.chapters); publish.enabled לא משתנה.
import re
from typing import Any, Dict, List, Mapping

import pandas as pd

MAX_CHAPTERS = 5
MAX_CREDITS = 3
CHAPTER_TITLES = {"lead": "{entity} במקום הראשון", "record": "השיא", "trend": "המגמה מתהפכת", "cross": "{entity} עוקף", "round": "{text}"}


def credits(docs: str) -> List[str]:
    """שורות המקור מ-SOURCES.md ("Source:" / "מקור:"), בלי סימוני markdown."""
    lines = []
    for line in docs.splitlines():
        match = re.search(r"(?:\*\*)?(?:sources?|מקור(?:ות)?)\s*:?\s*(?:\*\*)?\s*:?\s*(.+)", line, re.I)
        if not match or not re.match(r"^\s*[-*]?\s*(?:\*\*)?(?:sources?|מקור)", line, re.I):
            continue
        text = re.sub(r"[*`_]", "", match.group(1)).strip(" .:-")
        text = re.sub(r"\(\s*\)", "", re.sub(r"https?://[^\s)]+", "", text)).strip(" ,;(")   # בלי כתובות ובלי סוגריים שנשארו ריקים
        if text and text not in lines:
            lines.append(text[:160])
    return lines[:MAX_CREDITS]


def chapters(moments: List[Mapping[str, Any]], start: str, end: str) -> List[Dict[str, str]]:
    """עד 5 רגעים חזקים, לפחות עשירית מהזמן אחד מהשני, ככותרות פרקים קצרות."""
    if not moments or not start or not end:
        return []
    span = max((pd.Timestamp(end) - pd.Timestamp(start)).days, 1)
    chosen: List[Mapping[str, Any]] = []
    for m in sorted(moments, key=lambda m: -m["strength"]):
        if all(abs((pd.Timestamp(m["date"]) - pd.Timestamp(c["date"])).days) >= span / 10 for c in chosen):
            chosen.append(m)
        if len(chosen) == MAX_CHAPTERS:
            break
    return [{"date": m["date"], "title": CHAPTER_TITLES.get(m["kind"], "{text}").format(entity=m.get("entity", ""), text=m["text"])[:60]}
            for m in sorted(chosen, key=lambda m: m["date"])]


def hashtags(f: Mapping[str, Any], israel: bool) -> List[str]:
    words = [f.get("topic_he", "").lstrip("ה"), "נתונים", "ישראל" if israel else "", f.get("topic_en", "").title().replace(" ", "")]
    return ["#" + re.sub(r"[^\w֐-׿]", "", w.replace(" ", "_")) for w in words if w][:5]


def build(f: Mapping[str, Any], texts: Mapping[str, Any], story: Mapping[str, Any], docs: str, israel: bool) -> Dict[str, Any]:
    """{title, description, hashtags, credits, chapters} - לשדות publish.*, outro.credits, story.chapters."""
    title = (texts.get("titles") or [{}])[0].get("he", "")
    subtitle = (texts.get("subtitles") or [{}])[0].get("he", "")
    facts = [m for m in sorted(f.get("moments") or [], key=lambda m: m["date"])][:5]
    description = subtitle + ("\n\nהרגעים בסרטון:\n" + "\n".join(f"• {m['date'][:4]}: {m['text']}" for m in facts) if facts else "")
    return {"title": title, "description": description.strip(), "hashtags": hashtags(f, israel), "credits": credits(docs),
            "chapters": chapters(list(story.get("moments") or []), str(story.get("start") or ""), str(story.get("end") or ""))}
