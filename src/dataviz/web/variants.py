# dataviz/web/variants.py
#
# 20.10.2026: גרסאות של פרק (קצר/ארוך, עברית/אנגלית, יעד אחר) - שכבות עם שם מעל אותו בסיס, בלי להעתיק את התיקייה.
# כל גרסה היא קובץ data/dataviz_variants/<פרק>/<גרסה>.json: {label, target, lang, set: {נתיב: ערך}}. ההגדרות שהרינדור
# מקבל = config.yaml + קובץ השינויים של הפרק + ה-set של הגרסה (מאומת כמו כל שינוי מהדפדפן), ושם קובץ פלט משלה
# (<פרק>_<גרסה>) כדי לא לדרוס את הסרטון של הבסיס. הרינדור - דרך התור הקיים (routes/dataviz.py + dataviz_maker.py).
import json
import os
import re
import time
from typing import Any, Dict, List, Mapping, Optional
from utils.shared import data_paths

VARIANTS_ROOT = data_paths.DATAVIZ_VARIANTS
VARIANT_RE = re.compile(r"^[\w\-]{1,30}$")
TARGETS = ("", "youtube", "shorts", "tiktok")
LANGS = ("", "en")
MAX_VARIANTS = 12
MAX_SETTINGS = 200


def variants_dir(data_dir: str, name: str) -> str:
    return os.path.join(data_dir, VARIANTS_ROOT, name)


def _path(data_dir: str, name: str, variant: str) -> str:
    return os.path.join(variants_dir(data_dir, name), variant + ".json")


def _folder(data_dir: str, name: str) -> str:
    from dataviz.web import episodes as de
    folder = de.episode_folder(data_dir, str(name or ""))
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    return folder


# 23.10.2026: קובץ הפלט של גרסה הוא <פרק>_<גרסה> - והסיומות האלה הן כבר קבצים של הפרק עצמו (יעד, שפה, מצב), אז גרסה
# בשם כזה דרסה אותם (ואת חבילת הפרסום שלהם). גם <פרק>_<גרסה> ששווה לשם של פרק אחר דורס את הסרטון שלו.
RESERVED_SUFFIXES = ("shorts", "tiktok", "youtube", "en", "test", "preview", "stills", "share")
_SHORTS_PART_RE = re.compile(r"^shorts_\d+$", re.IGNORECASE)


def _output_clash(data_dir: str, name: str, variant: str) -> str:
    """מה ששם הגרסה היה דורס ("" = כלום)."""
    from dataviz.web import episodes as de
    if variant.lower() in RESERVED_SUFFIXES or _SHORTS_PART_RE.match(variant):
        return "קובץ של הפרק עצמו (יעד / שפה / מצב)"
    output = f"{name}_{variant}".casefold()
    try:
        others = os.listdir(de.episodes_root(data_dir))
    except OSError:
        others = []
    return next((f"הפרק '{other}'" for other in others if other.casefold() == output), "")


def load(data_dir: str, name: str, variant: str) -> Optional[Dict[str, Any]]:
    if not VARIANT_RE.match(str(variant or "")):
        return None
    try:
        with open(_path(data_dir, name, variant), encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def effective_overrides(data_dir: str, name: str, variant: str) -> Dict[str, Any]:
    """קובץ השינויים של הפרק + ה-set של הגרסה, ושם קובץ פלט משלה. EpisodeError אם הגרסה לא קיימת."""
    from dataviz.web import episodes as de
    folder = _folder(data_dir, name)
    record = load(data_dir, name, variant)
    if record is None:
        raise de.EpisodeError("הגרסה לא נמצאה.", status=404)
    overrides = de.draft_overrides(de.load_overrides_for_path(folder), record.get("set") or {})
    video = overrides.setdefault("video", {})
    if not video.get("output_name"):
        video["output_name"] = f"{name}_{variant}"
    return overrides


def list_variants(data_dir: str, name: str) -> Dict[str, Any]:
    _folder(data_dir, name)
    rows = []
    try:
        files = sorted(n for n in os.listdir(variants_dir(data_dir, name)) if n.endswith(".json"))
    except OSError:
        files = []
    for file_name in files:
        variant = file_name[:-5]
        record = load(data_dir, name, variant)
        if record is None:
            continue
        rows.append({"name": variant, "label": record.get("label") or variant, "target": record.get("target") or "",
                     "lang": record.get("lang") or "", "set": record.get("set") or {}, "time": record.get("time", "")})
    return {"variants": rows, "limit": MAX_VARIANTS}


def save(data_dir: str, name: str, variant: Any, label: Any = "", target: Any = "", lang: Any = "",
         set_values: Any = None) -> Dict[str, Any]:
    """יוצר או מחליף גרסה. כל ערך ב-set מאומת (כמו שינוי מהדפדפן) וגם התוצאה כולה (load_config)."""
    from dataviz.config import ConfigError, load_config
    from dataviz.web import episodes as de
    folder = _folder(data_dir, name)
    variant = str(variant or "").strip()
    if not VARIANT_RE.match(variant):
        raise de.EpisodeError("שם גרסה: אותיות, ספרות, _ או - (עד 30).")
    taken = _output_clash(data_dir, str(name), variant)
    if taken:
        raise de.EpisodeError(f"שם הגרסה '{variant}' יוצר קובץ פלט בשם של {taken} - בחר שם אחר.", status=409)
    if target not in TARGETS or lang not in LANGS:
        raise de.EpisodeError("יעד או שפה לא מוכרים.")
    if not isinstance(set_values, Mapping) or len(set_values) > MAX_SETTINGS:
        raise de.EpisodeError("השינויים של הגרסה צריכים להיות רשימה של הגדרות.")
    existing = list_variants(data_dir, name)["variants"]
    if load(data_dir, name, variant) is None and len(existing) >= MAX_VARIANTS:
        raise de.EpisodeError(f"עד {MAX_VARIANTS} גרסאות לפרק.")
    clean = {str(path): de._clean_special(str(path), value) for path, value in set_values.items()}
    merged = de.draft_overrides(de.load_overrides_for_path(folder), clean)
    try:   # 23.10.2026: גם הבדיקה של התרגום בתוך ה-try - קודם הגדרה לא תקינה בגרסה באנגלית נתנה 500
        final = load_config(os.path.join(folder, "config.yaml"), merged)
    except ConfigError as e:
        raise de.EpisodeError("ההגדרות של הגרסה לא תקינות: " + "; ".join(e.errors[:3])) from e
    if lang == "en" and not (final.get("translations") or {}).get("en"):
        raise de.EpisodeError("לגרסה באנגלית צריך תרגום (translations.en) בפרק.")
    record = {"label": " ".join(str(label or variant).split())[:60], "target": target, "lang": lang, "set": clean,
              "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    root = variants_dir(data_dir, name)
    os.makedirs(root, exist_ok=True)
    tmp = _path(data_dir, name, variant) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _path(data_dir, name, variant))
    return {"ok": True, "name": variant}


def remove(data_dir: str, name: str, variant: Any) -> Dict[str, Any]:
    """הגרסה עוברת לתיקייה .removed שלידה (לא נמחקת) - אפשר להחזיר ביד."""
    from dataviz.web import episodes as de
    _folder(data_dir, name)
    variant = str(variant or "")
    if load(data_dir, name, variant) is None:
        raise de.EpisodeError("הגרסה לא נמצאה.", status=404)
    removed = os.path.join(variants_dir(data_dir, name), ".removed")
    os.makedirs(removed, exist_ok=True)
    os.replace(_path(data_dir, name, variant), os.path.join(removed, f"{variant}_{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1000000:06d}.json"))
    return {"ok": True}


def run_settings(data_dir: str, name: str, variant: str) -> Dict[str, str]:
    """היעד והשפה של הגרסה (לרינדור) - ריקים = כמו הבסיס."""
    record = load(data_dir, name, variant) or {}
    target, lang = record.get("target") or "", record.get("lang") or ""
    return {"target": target if target in TARGETS else "", "lang": lang if lang in LANGS else ""}


def names(data_dir: str, name: str) -> List[str]:
    return [row["name"] for row in list_variants(data_dir, name)["variants"]]
