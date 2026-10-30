# dataviz/web/story_templates.py
#
# 20.10.2026: אשף תבניות סיפור - מתחילים מהשאלה ("מי הוביל?", "איך זה השתנה?", "מי מול מי?", "מה השתנה אחרי?") ובוחרים
# סוג: מרוץ / מגמה לאורך זמן / השוואה של שניים / לפני-אחרי. כל סוג קובע תרשים, קצב וטקסטים, כשינויים רגילים בקובץ
# השינויים של הפרק (config.yaml לא משתנה). קודם מוצג מה ישתנה (לפני / אחרי לכל הגדרה), ורק אז מחילים - בפרק קיים או
# מיד אחרי "פרק חדש".
from typing import Any, Dict, List, Mapping, Optional

from dataviz.web import episodes as de

TEMPLATES: Dict[str, Dict[str, str]] = {
    "race": {"title": "🏁 מרוץ", "about": "מי מוביל ומתי התחלפו המקומות - עמודות שמתחלפות, עם התראת \"שיא חדש\"."},
    "trend": {"title": "📈 מגמה לאורך זמן", "about": "איך הערכים השתנו לאורך השנים - קווים, קצב רגוע, בלי התראות."},
    "compare": {"title": "⚖️ השוואה של שניים", "about": "שתי ישויות זו מול זו - שני קווים, השאר מעומעמות."},
    "before_after": {"title": "⏮⏭ לפני ואחרי", "about": "מה השתנה אחרי תאריך מסוים - עצירה עם הסבר בתאריך, ותקופות \"לפני\" ו\"אחרי\" מוצללות."},
}


def _changes(template: str, question: str, cfg: Mapping[str, Any], entities: List[Any], dates: Any, split: Optional[str],
             pick: List[str]) -> Dict[str, Any]:
    question = question.strip()[:200]
    common: Dict[str, Any] = {"intro.question": question} if question else {}
    if template == "race":
        return {**common, "chart": "bar_race", "ranking.top_n": min(10, max(3, len(entities))), "records.enabled": True,
                "labels.leader": "מוביל", "outro.title": "הדירוג הסופי"}
    if template == "trend":
        return {**common, "chart": "line_race", "ranking.top_n": min(5, max(1, len(entities))), "records.enabled": False,
                "outro.title": "המגמה עד היום", "labels.total": ""}
    if template == "compare":
        two = [str(e) for e in (pick or [str(e) for e in entities[:2]])][:2]
        if len(two) < 2:
            raise de.EpisodeError("השוואה צריכה שתי ישויות.")
        return {**common, "chart": "line_race", "ranking.top_n": max(2, min(len(entities), 10)), "records.enabled": False,
                "focus.entities": two, "outro.title": f"{two[0]} מול {two[1]}", "outro.places": ["ראשון", "שני"]}
    if template == "before_after":
        import pandas as pd
        if not split:
            raise de.EpisodeError("לפני ואחרי צריך תאריך.")
        try:
            day = pd.Timestamp(split)
        except (ValueError, TypeError):
            raise de.EpisodeError("תאריך לא תקין.") from None
        start, end = pd.Timestamp(dates[0]), pd.Timestamp(dates[-1])
        if not start < day < end:
            raise de.EpisodeError(f"התאריך צריך להיות בתוך הפרק ({start:%Y-%m-%d} - {end:%Y-%m-%d}).")
        mid = day.strftime("%Y-%m-%d")
        before_end = (day - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        return {**common, "chart": cfg["chart"] if cfg["chart"] in ("line_race", "stacked_area_race") else "line_race",
                "story.periods": [{"start": start.strftime("%Y-%m-%d"), "end": before_end, "label": "לפני"},
                                  {"start": mid, "end": end.strftime("%Y-%m-%d"), "label": "אחרי"}],
                "story.pauses": [{"date": mid, "text": question or "מכאן - אחרי"}], "outro.title": "לפני ואחרי"}
    raise de.EpisodeError("סוג סיפור לא מוכר.", status=404)


def preview(data_dir: str, name: str, template: Any, question: Any = "", split: Any = None, pick: Any = None) -> Dict[str, Any]:
    """מה התבנית תשנה בפרק: לכל הגדרה - לפני (הערך שהרינדור מקבל עכשיו) ואחרי. בלי לכתוב כלום."""
    from dataviz import schema
    from dataviz.episode import load_episode
    folder = de.episode_folder(data_dir, str(name or ""))
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    episode = load_episode(folder, de.load_overrides_for_path(folder))
    cfg = episode.config
    changes = _changes(str(template or ""), str(question or ""), cfg, list(episode.entities), episode.dates,
                       str(split) if split else None, [str(p) for p in (pick or []) if str(p).strip()])
    rows = []
    for path, after in changes.items():
        before = schema.get_path(cfg, path)[1]
        if before == after:
            continue
        label = (schema.FIELD_BY_PATH.get(path) or {}).get("label") or path
        rows.append({"path": path, "label": label, "before": before, "after": after})
    return {"template": template, "changes": rows, "set": {r["path"]: r["after"] for r in rows}}


def apply(data_dir: str, name: str, template: Any, question: Any = "", split: Any = None, pick: Any = None) -> Dict[str, Any]:
    """מחיל את מה ש-preview הראה - כשינויים בקובץ השינויים של הפרק (update_override_fields: כל ערך מאומת)."""
    result = preview(data_dir, name, template, question, split, pick)
    if result["set"]:
        de.update_override_fields(data_dir, str(name), result["set"], [])
    return {"ok": True, "applied": [r["path"] for r in result["changes"]]}


def suggest(data_dir: str, name: str) -> Dict[str, Any]:
    """21.10.2026 (סבב הפישוט): סוג הסיפור שמוצע אוטומטית - כלי סיפור אחד. פרק שנוצר מתיקייה: מה שהעורך החכם מצא אז (ברשומה);
    אחרת - אותו ניתוח (dataviz/smart/story.py) על קובצי הפרק. {} כשאין הצעה; לא כותב כלום."""
    from dataviz.smart import create
    folder = de.episode_folder(data_dir, str(name or ""))
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    found = (create.load_record(data_dir, str(name)) or {}).get("story_type")
    if found:
        return {**found, "source": "record"}
    from dataviz.smart.draft import analyze
    try:
        story = analyze(folder)["story"]
    except Exception:   # רק הצעה - קובץ שהניתוח לא מבין לא מפיל את הכלי, והסוגים נשארים לבחירה ביד
        return {}
    if not story.get("type"):
        return {}
    moments = sorted(story.get("moments") or [], key=lambda m: -m["strength"])[:3]
    return {**story["type"], "source": "analysis", "moments": [{"date": m["date"], "text": m["text"]} for m in moments]}


def templates() -> List[Dict[str, str]]:
    return [{"id": key, **value} for key, value in TEMPLATES.items()]
