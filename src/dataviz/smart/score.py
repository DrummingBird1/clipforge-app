# dataviz/smart/score.py
#
# 20.10.2026: כמה הטיוטה האוטומטית קרובה ל-config.yaml שנכתב ביד - לכל פרק בתיקיית קורפוס: קובץ הסדרה, עמודת הזמן,
# הרזולוציה, הישות, הערך, סוג הערך (כמות / רמה), היחידות והתרשים. ב-config הידניים ערך delta_X עם kind ברירת מחדל
# (כמות) הוא סדרת רמה של X (הסכום המצטבר = הרמה) - שקול ל-X עם kind: level. קריאה בלבד.
#   uv run python -m dataviz.smart.score <תיקיית קורפוס>
import json
import os
import sys
from typing import Any, Callable, Dict, List, Mapping, Optional

import yaml

# היחידות הנכונות (מ-SOURCES.md של כל פרק, ביד) - ב-config אין יחידות. 30.10.2026: בקובץ _units.json בשורש הקורפוס
# ({"<תיקיית פרק>": "<יחידה>"}), ולא כאן - הקורפוס הוא נתוני משתמש, ושמות הפרקים שלו לא שייכים לקוד. בלעדיו היחידות לא נספרות
UNITS_FILE = "_units.json"


def _expected_units(corpus: str) -> Dict[str, str]:
    try:
        with open(os.path.join(corpus, UNITS_FILE), encoding="utf-8") as f:
            units = json.load(f)
    except (OSError, ValueError):
        return {}
    return units if isinstance(units, dict) else {}
METRICS = ("file", "time", "period", "entity", "value", "kind", "unit", "chart")


def expected(folder: str) -> Dict[str, Any]:
    with open(os.path.join(folder, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    src = (cfg.get("sources") or [{}])[0]
    value = str((src.get("value") or {}).get("column") or "")
    kind = src.get("kind") or "amount"
    if value.lower().startswith("delta_"):
        kind = "level"
    files = sorted(str(s.get("path")) for s in cfg.get("sources") or [] if s.get("path"))
    return {"file": files or None, "time": (src.get("time") or {}).get("column"), "period": (src.get("time") or {}).get("period"),
            "entity": (src.get("entity") or {}).get("column"), "value": value, "kind": kind, "chart": cfg.get("chart"),
            "unit": _expected_units(os.path.dirname(os.path.normpath(folder))).get(os.path.basename(os.path.normpath(folder))),
            "first_file": src.get("path")}


def _same_value(got: str, want: str, columns: List[str]) -> bool:
    """delta_X שקול ל-X (העמודה שמסתיימת ב-X)."""
    if got == want:
        return True
    if want.lower().startswith("delta_"):
        return got.lower().endswith(want[6:].lower()) and got in columns
    return False


def predicted(folder: str) -> Dict[str, Any]:
    """מה הטיוטה האוטומטית בוחרת (מה שקיים עד עכשיו בחבילה)."""
    from dataviz.smart import draft
    return draft.choices(folder)


def score_folder(folder: str, predict: Callable[[str], Mapping[str, Any]] = predicted) -> Dict[str, Any]:
    want = expected(folder)
    got = dict(predict(folder))
    if got.get("unit_by_file") and want.get("first_file") in got["unit_by_file"]:
        got["unit"] = got["unit_by_file"][want["first_file"]]   # כמה קבצים - היחידה של הסדרה הראשונה ב-config
    columns = list(got.get("columns") or [])
    hits: Dict[str, Optional[bool]] = {}
    for metric in METRICS:
        if want.get(metric) is None or got.get(metric) is None:
            hits[metric] = None if want.get(metric) is None else False
        elif metric == "value":
            hits[metric] = _same_value(str(got["value"]), str(want["value"]), columns)
        else:
            hits[metric] = str(got[metric]) == str(want[metric])
    scored = [v for v in hits.values() if v is not None]
    return {"episode": os.path.basename(os.path.normpath(folder)), "hits": hits, "want": want, "got": got,
            "score": round(sum(scored) / len(scored), 2) if scored else 0.0}


def score_corpus(root: str, predict: Callable[[str], Mapping[str, Any]] = predicted) -> List[Dict[str, Any]]:
    return [score_folder(os.path.join(root, name), predict) for name in sorted(os.listdir(root))
            if os.path.isfile(os.path.join(root, name, "config.yaml"))]


def table(rows: List[Dict[str, Any]]) -> str:
    mark = {True: "✓", False: "✗", None: "-"}
    lines = ["| פרק | " + " | ".join(METRICS) + " | ציון |", "|" + "---|" * (len(METRICS) + 2)]
    for row in rows:
        cells = []
        for metric in METRICS:
            hit = row["hits"][metric]
            cells.append(mark[hit] + ("" if hit is not False else f" ({row['got'].get(metric)} / {row['want'].get(metric)})"))
        lines.append(f"| {row['episode']} | " + " | ".join(cells) + f" | {row['score']:.0%} |")
    if rows:
        lines.append("| ממוצע | " + " | ".join("" for _ in METRICS) + f" | {sum(r['score'] for r in rows) / len(rows):.0%} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(table(score_corpus(sys.argv[1] if len(sys.argv) > 1 else ".")))
