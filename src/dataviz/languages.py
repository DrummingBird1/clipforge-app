# dataviz/languages.py
#
# גל 55: גרסה בשפה אחרת לאותו פרק. translations.<שפה> בהגדרות מכיל רק את מה שמתורגם - כותרות, פתיח וסיום,
# תוויות, הערות ומקורות, פרקים / עצירות / הערות של הסיפור, ופרטי הפרסום - והוא נמזג מעל ההגדרות. שני מקרים מיוחדים:
# events = תאריך -> תיאור (הכרטיסים נשארים באותם תאריכים), ו-entities = שם הישות -> השם בשפה (רק התצוגה; הנתונים
# לא משתנים). הקובץ יוצא בשם משלו (<שם>_<שפה>.mp4), והמספרים "במילים" נכתבים בשפה הזו.

import copy
from typing import Any, Dict, List, Mapping

LANGUAGES = ("en",)
LTR_LANGUAGES = ("en",)   # סבב הייצוב: בגרסה בשפות האלה הכותרת והמקרא משמאל והתאריך מימין (dataviz/charts/base.py)
TRANSLATABLE = ("title", "subtitle", "intro", "outro", "labels", "notes", "story", "publish", "teaser", "end_screen", "narration")


def apply_language(config: Mapping[str, Any], lang: str) -> Dict[str, Any]:
    """עותק של ההגדרות בשפה lang. בלי תרגום לשפה הזו -> ValueError (לא מרנדרים בטעות סרטון שלא תורגם)."""
    from dataviz.config import merge
    if lang not in LANGUAGES:
        raise ValueError(f"שפה לא נתמכת: {lang!r} (קיימות: {', '.join(LANGUAGES)}).")
    texts = dict((config.get("translations") or {}).get(lang) or {})
    if not texts:
        raise ValueError(f"אין תרגום ל-{lang} בהגדרות הפרק (translations.{lang}).")
    result = merge(config, {k: v for k, v in texts.items() if k in TRANSLATABLE})
    labels = {str(date): str(label) for date, label in (texts.get("events") or {}).items() if str(label).strip()}
    if labels:
        result["events"] = translated_events(config, labels)
    # סבב הייצוב (16.10): המקרא של המקורות - שורה לכל מקור שיש לו מקרא, לפי הסדר (בלי זה נשאר בעברית בגרסה באנגלית)
    legends = [str(v).strip() for v in texts.get("legends") or [] if str(v).strip()]
    if legends:
        sources: List[Dict[str, Any]] = []
        k = 0
        for src in result.get("sources") or []:
            if src.get("legend") and k < len(legends):
                src = {**src, "legend": legends[k]}
                k += 1
            sources.append(src)
        result["sources"] = sources
    names = {str(k): str(v).strip() for k, v in (texts.get("entities") or {}).items() if str(v).strip()}
    if names:
        entities = copy.deepcopy(dict(result.get("entities") or {}))
        aliases = dict(entities.get("aliases") or {})
        # שם חלופי שכבר קיים (מיזוג) מתורגם דרך השם החדש; ישות בלי שם חלופי מקבלת את התרגום ישר
        for source, target in list(aliases.items()):
            aliases[source] = names.get(str(target), target)
        for source, target in names.items():
            aliases.setdefault(source, target)
        entities["aliases"] = aliases
        result["entities"] = entities
    result["numbers"] = dict(result.get("numbers") or {}, lang=lang)
    video = dict(result["video"])
    video["output_name"] = f"{video.get('output_name') or result.get('name', 'episode')}_{lang}"
    result["video"] = video
    result["language"] = lang
    from dataviz.config import ConfigError, validate
    errors = validate(result)
    if errors:
        raise ConfigError([f"התרגום ל-{lang}: {e}" for e in errors])
    return result


def translated_events(config: Mapping[str, Any], labels: Mapping[str, str]) -> List[Dict[str, str]]:
    from dataviz.episode import load_events
    return [{"date": date, "label": labels.get(date, label)} for date, label in load_events(config)]


def clean_translation(value: Any) -> Dict[str, Any]:
    """תרגום שמגיע מהמסך: רק המפתחות המותרים, טקסטים באורך סביר (ValueError על משהו אחר)."""
    if not isinstance(value, Mapping):
        raise ValueError("תרגום צריך להיות מילון.")

    def text(v: Any, limit: int = 200) -> str:
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError("טקסט ארוך מדי בתרגום.")
        return v.strip()

    def lines(v: Any, most: int = 10) -> List[str]:
        if not isinstance(v, list) or len(v) > most:
            raise ValueError("רשימת שורות לא תקינה בתרגום.")
        return [text(line, 160) for line in v if str(line).strip()]

    out: Dict[str, Any] = {}
    for key in ("title", "subtitle"):
        if key in value:
            out[key] = text(value[key])
    for key, fields in (("intro", ("title", "subtitle", "question")), ("labels", ("total", "leader", "record", "others", "date_format")),
                        ("teaser", ("label",)), ("end_screen", ("text",)), ("publish", ("title", "description"))):
        part = value.get(key)
        if isinstance(part, Mapping):
            cleaned = {f: text(part[f], 2000 if f == "description" else 200) for f in fields if f in part}
            if cleaned:
                out[key] = cleaned
    outro = value.get("outro")
    if isinstance(outro, Mapping):
        cleaned_outro: Dict[str, Any] = {}
        if "title" in outro:
            cleaned_outro["title"] = text(outro["title"])
        for key in ("places", "credits"):
            if key in outro:
                cleaned_outro[key] = lines(outro[key])
        if cleaned_outro:
            out["outro"] = cleaned_outro
    if "notes" in value:
        out["notes"] = lines(value["notes"])
    # סבב הייצוב: מקרא המקורות ותגיות לפרסום בשפה
    if "legends" in value:
        out["legends"] = lines(value["legends"])
    publish = value.get("publish")
    if isinstance(publish, Mapping) and "hashtags" in publish:
        hashtags = lines(publish["hashtags"], 30)
        if hashtags:
            out.setdefault("publish", {})["hashtags"] = hashtags
    for key in ("events", "entities"):
        mapping = value.get(key)
        if mapping is not None:
            if not isinstance(mapping, Mapping) or len(mapping) > 500:
                raise ValueError(f"{key} בתרגום צריך להיות מילון.")
            out[key] = {str(k)[:80]: text(v, 120) for k, v in mapping.items() if str(v).strip()}
    if "story" in value:
        story = value["story"]
        if not isinstance(story, Mapping):
            raise ValueError("story בתרגום צריך להיות מילון.")
        out["story"] = {k: v for k, v in story.items() if k in ("chapters", "pauses", "callouts", "periods")}
    return {k: v for k, v in out.items() if v not in ({}, [], "")}
