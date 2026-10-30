# dataviz/web/kits.py (עד 19.10.2026: utils/dataviz_kits.py)
#
# גל 41: ערכת ערוץ לעורך הגרפים - עיצוב קבוע שחוזר על עצמו בכל הפרקים של הערוץ: ערכה (בהיר / כהה),
# צבעי הרקע / הטקסט / ההדגשה, הפלטה, ולוגו בפינה. הערכות נשמרות ב-data/dataviz_kits.json (קובץ של
# האפליקציה), ונוצרות מפרק קיים או מ"מיתוג" של עורך-העל (הלוגו וצבע). החלה על פרק = שינויים בקובץ
# ה-override שלו, כמו כל עריכה מהדפדפן - config.yaml לא משתנה.

import json
import os
import re
from typing import Any, Dict, List, Mapping

from dataviz.web import episodes as de
from utils.shared import data_paths

KITS_FILENAME = data_paths.DATAVIZ_KITS
MAX_KITS = 50
NAME_RE = re.compile(r"^[\w\- א-ת]{1,40}$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def kits_path(data_dir: str) -> str:
    return os.path.join(data_dir, KITS_FILENAME)


def load_kits(data_dir: str) -> Dict[str, Dict[str, Any]]:
    try:
        with open(kits_path(data_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _write(data_dir: str, kits: Mapping[str, Any]) -> None:
    path = kits_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kits, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _clean_kit(kit: Mapping[str, Any]) -> Dict[str, Any]:
    """רק השדות של ערכה, מאומתים (אותם בודקים כמו בעריכה מהדפדפן)."""
    clean: Dict[str, Any] = {}
    if kit.get("theme") in de.THEMES:
        clean["theme"] = kit["theme"]
    colors: Dict[str, Any] = {k: str(v).lower() for k, v in (kit.get("theme_overrides") or {}).items()
              if k in de.THEME_COLOR_KEYS and isinstance(v, str) and _HEX.match(v)}
    for key in ("categorical", "ordinal"):
        palette = (kit.get("theme_overrides") or {}).get(key)
        if isinstance(palette, list) and 2 <= len(palette) <= 20 and all(isinstance(c, str) and _HEX.match(c) for c in palette):
            colors[key] = [c.lower() for c in palette]
    fonts = (kit.get("theme_overrides") or {}).get("fonts")
    if fonts:
        try:
            colors["fonts"] = de.clean_fonts(list(fonts))
        except de.EpisodeError:
            pass
    if colors:
        clean["theme_overrides"] = colors
    logo = kit.get("logo") or {}
    if isinstance(logo, Mapping) and logo.get("path") and os.path.isfile(str(logo["path"])):
        clean["logo"] = {"path": os.path.abspath(str(logo["path"])),
                         "position": logo.get("position") if logo.get("position") in ("bottom-right", "bottom-left", "top-right", "top-left") else "bottom-right",
                         "scale": min(0.3, max(0.02, float(logo.get("scale") or 0.05))),
                         "opacity": min(1.0, max(0.1, float(logo.get("opacity") or 0.95)))}
    bumpers = {k: os.path.abspath(str(v)) for k, v in (kit.get("bumpers") or {}).items()
               if k in ("intro", "outro") and v and os.path.isfile(str(v))}   # גל 43: אינטרו / אאוטרו מקליפ
    if bumpers:
        clean["bumpers"] = bumpers
    return clean


def save_kit(data_dir: str, name: str, kit: Mapping[str, Any]) -> Dict[str, Any]:
    name = str(name or "").strip()
    if not NAME_RE.match(name):
        raise de.EpisodeError("שם הערכה: עד 40 תווים - אותיות, ספרות, רווח ומקף.")
    clean = _clean_kit(kit)
    if not clean:
        raise de.EpisodeError("אין בערכה שום דבר לשמור (ערכה, צבעים או לוגו).")
    kits = load_kits(data_dir)
    if name not in kits and len(kits) >= MAX_KITS:
        raise de.EpisodeError(f"אפשר לשמור עד {MAX_KITS} ערכות.")
    kits[name] = clean
    _write(data_dir, kits)
    return clean


def delete_kit(data_dir: str, name: str) -> bool:
    kits = load_kits(data_dir)
    if name not in kits:
        return False
    del kits[name]
    _write(data_dir, kits)
    return True


def kit_from_episode(data_dir: str, episode: str) -> Dict[str, Any]:
    """הערכה של פרק קיים: הערכה, הצבעים והפלטה ששונו, והלוגו (בנתיב מלא)."""
    from dataviz.config import load_config
    folder = de.episode_folder(data_dir, episode)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    config = load_config(os.path.join(folder, "config.yaml"), de.load_overrides_for_path(folder))
    logo = dict(config.get("logo") or {})
    if logo.get("path"):
        logo["path"] = os.path.join(folder, str(logo["path"]))
    bumpers = {k: os.path.join(folder, str(v)) for k, v in (config.get("bumpers") or {}).items() if v}
    return {"theme": config["theme"], "theme_overrides": dict(config.get("theme_overrides") or {}), "logo": logo, "bumpers": bumpers}


def kit_from_brand(brand: Mapping[str, Any]) -> Dict[str, Any]:
    """"מיתוג" של עורך-העל -> ערכת ערוץ: סימן המים הופך ללוגו, וצבע מהמיתוג (אם יש) לצבע ההדגשה."""
    fields = brand.get("fields") or {}
    kit: Dict[str, Any] = {}
    if fields.get("watermark_path"):
        position = str(fields.get("watermark_position") or "bottom-right")
        kit["logo"] = {"path": fields["watermark_path"], "position": position, "scale": 0.05, "opacity": 0.95}
    for key in ("progress_bar_color", "frame_color", "text_color", "caption_color"):
        value = fields.get(key)
        if isinstance(value, str) and _HEX.match(value):
            kit["theme_overrides"] = {"accent": value.lower()}
            break
    # גל 43: גופן הכתוביות (כשהוא שם של גופן ולא קובץ) והאינטרו / האאוטרו של המיתוג
    font = str(fields.get("caption_font") or "").strip()
    if font and de.FONT_RE.match(font) and not font.lower().endswith((".ttf", ".otf")):
        kit.setdefault("theme_overrides", {})["fonts"] = [font, "Segoe UI", "Arial", "DejaVu Sans"]
    bumpers = {key: fields[f"{key}_path"] for key in ("intro", "outro") if fields.get(f"{key}_path")}
    if bumpers:
        kit["bumpers"] = bumpers
    return kit


def kit_changes(kit: Mapping[str, Any]) -> Dict[str, Any]:
    """ערכה -> שינויים (נתיב -> ערך) ל-update_override_fields של פרק."""
    changes: Dict[str, Any] = {}
    if kit.get("theme"):
        changes["theme"] = kit["theme"]
    for key, value in (kit.get("theme_overrides") or {}).items():
        changes[f"theme_overrides.{key}"] = value
    for key, value in (kit.get("logo") or {}).items():
        changes[f"logo.{key}"] = value
    for key, value in (kit.get("bumpers") or {}).items():
        changes[f"bumpers.{key}"] = value
    return changes


def apply_kit(data_dir: str, episode: str, name: str) -> Dict[str, Any]:
    kit = load_kits(data_dir).get(name)
    if kit is None:
        raise de.EpisodeError("הערכה לא נמצאה.", status=404)
    return de.update_override_fields(data_dir, episode, kit_changes(kit), [])


def kits_summary(data_dir: str) -> List[Dict[str, Any]]:
    return [{"name": name, "theme": kit.get("theme", ""), "accent": (kit.get("theme_overrides") or {}).get("accent", ""),
             "palette": (kit.get("theme_overrides") or {}).get("categorical", []), "logo": os.path.basename((kit.get("logo") or {}).get("path", "")),
             "font": ((kit.get("theme_overrides") or {}).get("fonts") or [""])[0],
             "bumpers": [os.path.basename(v) for v in (kit.get("bumpers") or {}).values()]}
            for name, kit in sorted(load_kits(data_dir).items())]
