# dataviz/smart/learn.py
#
# 20.10.2026: עורך הגרפים החכם לומד מהמשתמש.
#   העדפות (פריט 16): כשבחירה אוטומטית מוחלפת ביד (התרשים, כמה ישויות על המסך, ערכת הצבעים), נשמרת העדפה - לכל ערכת
#   ערוץ בנפרד ("default" כשאין) - ב-data/dataviz_smart/preferences.json, והטיוטה הבאה משתמשת בה (עם 🤖 "העדפה שלך").
#   מוצגות ומתאפסות בהגדרות. התרשים נשמר כמיפוי: "כשאני בוחר X - אתה מעדיף Y".
#   סדרות (פריט 17): תיקייה חדשה שדומה לפרק קיים (אותו מקור ב-SOURCES.md / אותן עמודות / אותו נושא) מקבלת את המראה
#   והמבנה שלו (ערכה, לוגו, תרשים, מספר ישויות) ואת שם הסדרה עם המספר הבא.
import json
import os
from typing import Any, Dict, List, Mapping, Optional

from dataviz.smart.create import SMART_ROOT

PREFS_FILE = "preferences.json"
LEARNABLE = ("chart", "ranking.top_n", "theme")
SERIES_KEYS = ("theme", "chart", "ranking.top_n")
SERIES_PREFIXES = ("theme_overrides.", "logo.")


def prefs_path(data_dir: str) -> str:
    return os.path.join(data_dir, SMART_ROOT, PREFS_FILE)


def load_prefs(data_dir: str) -> Dict[str, Dict[str, Any]]:
    try:
        with open(prefs_path(data_dir), encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _save(data_dir: str, prefs: Mapping[str, Any]) -> None:
    path = prefs_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _get(tree: Mapping[str, Any], path: str) -> Any:
    node: Any = tree
    for key in path.split("."):
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    return node


def observe(data_dir: str, name: str, overrides: Mapping[str, Any]) -> List[str]:
    """אחרי שמירה של פרק שנוצר מתיקייה: בחירה אוטומטית שהוחלפה ביד -> העדפה. מחזיר מה נלמד.
    ב24: מה שהפרק לימד נרשם ברשומה שלו (taught) - חזרה לבחירה האוטומטית (או הסרת השדה) מבטלת את מה שהוא לימד, אם
    ההעדפה עדיין אותה העדפה. קודם "ניסיון והחזרה" השאירו העדפה הפוכה להחלטה הסופית."""
    from dataviz.smart.create import load_record, save_record
    record = load_record(data_dir, name)
    if not record:
        return []
    scope = str(record.get("kit") or "default")
    prefs = load_prefs(data_dir)
    mine = dict(prefs.get(scope) or {})
    taught = dict(record.get("taught") or {})
    learned, forgotten = [], []
    chosen = {c["path"]: c for c in record.get("choices") or [] if c.get("where") == "override" and c["path"] in LEARNABLE}
    for path in LEARNABLE:
        current = _get(overrides, path)
        choice = chosen.get(path)
        if current is None or (choice and current == choice["value"]):
            if path in taught and _forget(mine, path, taught.pop(path)):
                forgotten.append(path)
            continue
        if choice and choice.get("undone"):
            continue
        if path == "chart":
            if not choice:
                continue
            mapping = dict(mine.get("chart") or {})
            if mapping.get(str(choice["value"])) != current:
                mapping[str(choice["value"])] = current
                mine["chart"] = mapping
                learned.append(path)
                taught[path] = [str(choice["value"]), current]
        elif mine.get(path) != current and (choice or path == "theme"):
            mine[path] = current
            learned.append(path)
            taught[path] = current
    if learned or forgotten:
        prefs[scope] = mine
        _save(data_dir, prefs)
    if taught != (record.get("taught") or {}):
        record["taught"] = taught
        save_record(data_dir, name, record)
    return learned


def _forget(mine: Dict[str, Any], path: str, value: Any) -> bool:
    """ב24: מבטל העדפה שהפרק לימד - רק אם היא עדיין מה שהוא לימד (פרק אחר אולי לימד אחרת אחריו)."""
    if path == "chart":
        mapping = dict(mine.get("chart") or {})
        auto, wanted = value
        if mapping.get(auto) != wanted:
            return False
        del mapping[auto]
        mine["chart"] = mapping
        return True
    if mine.get(path) != value:
        return False
    del mine[path]
    return True


def apply_prefs(data_dir: str, scope: str, values: Dict[str, Any], choices: List[Dict[str, Any]]) -> List[str]:
    """ההעדפות של הערכה (או default) על הטיוטה - משנה את values ואת הבחירות עם הסיבה. מחזיר אילו."""
    mine = load_prefs(data_dir).get(scope or "default") or {}
    applied = []
    for path in LEARNABLE:
        if path == "chart":
            wanted = (mine.get("chart") or {}).get(str(values.get("chart")))
        else:
            wanted = mine.get(path)
        if wanted is None or values.get(path) == wanted:
            continue
        before = values.get(path)
        values[path] = wanted
        choices[:] = [c for c in choices if c["path"] != path]
        choices.append({"path": path, "value": wanted, "label": {"chart": "סוג התרשים", "ranking.top_n": "כמה ישויות על המסך", "theme": "ערכת צבעים"}[path],
                        "reason": "העדפה שלך מפרקים קודמים" + (f" (במקום {before})" if before is not None else ""),
                        "confidence": 0.85, "where": "override"})
        applied.append(path)
    return applied


def reset_prefs(data_dir: str, scope: Optional[str] = None) -> Dict[str, Any]:
    prefs = load_prefs(data_dir)
    if scope:
        prefs.pop(scope, None)
    else:
        prefs = {}
    _save(data_dir, prefs)
    return prefs


# ---------- סדרות ----------
def _signature(folder: str) -> Dict[str, Any]:
    """מה מזהה סדרה: שורת המקור ב-SOURCES.md, העמודות של קובצי הנתונים (רק הכותרות - בלי לקרוא את כל הקבצים), הנושאים."""
    import re

    from dataviz.smart.events import topics
    from dataviz.smart.package import credits
    from dataviz.smart.scan import TABLE_EXT, load_table, read_docs
    if not os.path.isdir(folder):
        return {}
    columns: set = set()
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(TABLE_EXT) and not re.search(r"raw|unused|check|event|weight", name.lower()):
            df = load_table(folder, name, nrows=5)
            if df is not None:
                columns |= {str(c) for c in df.columns}
    return {"source": (credits(read_docs(folder)) or [""])[0].lower(), "columns": columns,
            "topics": topics(folder) - {"world", "israel"}}


def find_series(data_dir: str, folder: str) -> Optional[Dict[str, Any]]:
    """הפרק הקיים שהכי דומה לתיקייה החדשה - {episode, why, score} - או None. צריך לפחות שני סימנים: ב25 - מקור זהה לבד
    ("Source: CBS") הביא לתיקיות לא קשורות את התרשים, מספר הישויות ושם הסדרה של פרק אחר."""
    from dataviz.web import episodes as de
    new = _signature(folder)
    if not new:
        return None
    root = de.episodes_root(data_dir)
    best: Optional[Dict[str, Any]] = None
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        path = os.path.join(root, name)
        if not os.path.isfile(os.path.join(path, "config.yaml")):
            continue
        old = _signature(path)
        if not old:
            continue
        why, score = [], 0.0
        if new["source"] and new["source"] == old["source"]:
            why.append("אותו מקור ב-SOURCES.md")
            score += 2
        if new["columns"] and old["columns"]:
            overlap = len(new["columns"] & old["columns"]) / len(new["columns"] | old["columns"])
            if overlap >= 0.6:
                why.append(f"אותן עמודות ({overlap:.0%})")
                score += 1.5 * overlap
        if new["topics"] and new["topics"] == old["topics"]:
            why.append("אותו נושא")
            score += 1
        if len(why) >= 2 and score >= 2 and (best is None or score > best["score"]):
            best = {"episode": name, "why": ", ".join(why), "score": round(score, 2)}
    return best


def series_values(data_dir: str, episode: str) -> Dict[str, Any]:
    """המראה והמבנה של פרק קיים (מה שהרינדור מקבל): ערכה, צבעים, לוגו, תרשים, מספר ישויות, ושם הסדרה + המספר הבא."""
    from dataviz import schema
    from dataviz.config import load_config
    from dataviz.web import episodes as de
    folder = de.episode_folder(data_dir, episode)
    if folder is None:
        return {}
    config = load_config(os.path.join(folder, "config.yaml"), de.load_overrides_for_path(folder))
    overrides = de.load_overrides_for_path(folder)
    values: Dict[str, Any] = {}
    for path in SERIES_KEYS:
        values[path] = schema.get_path(config, path)[1]
    for path in de._flatten(overrides):
        if path.startswith(SERIES_PREFIXES):
            values[path] = schema.get_path(overrides, path)[1]
    series = config.get("series") or {}
    values["series.name"] = series.get("name") or str(config.get("title") or episode)[:60]
    values["series.number"] = int(series.get("number") or 1) + 1
    return values
