# utils/video/brand_kits.py
#
# גל 12 - "ערכת מותג": לוגו + מיקום/גודל/שקיפות, סגנון כתוביות, צבעי מסגרת/סרגל
# ו-intro/outro, ותבניות שכבות (lower-third וכו') - במקום אחד, משותף לכל המתכונים.
# מתכון מקושר לערכה בשם (שדה brand_kit), והערכים של הערכה מוחלים בזמן ריצה
# (apply_brand_kit) - כך שעדכון הערכה מגיע לכל מתכון שמשתמש בה, בלי לעדכן כל
# פרופיל בנפרד.
#
# הקובץ יושב ליד קובץ הפרופילים (data/brand_kits.json) ונגזר ממנו בזמן-קריאה,
# כך שטסטים שמפנים את הפרופילים לתיקייה זמנית מפנים אוטומטית גם את זה. כל כתיבה
# עוברת דרך אותו גיבוי-מסתובב + כתיבה אטומית של הפרופילים.

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.video import video_editor_profiles as vep
from utils.video.editor_model import BRAND_FIELDS

MAX_KITS = 50
MAX_TEMPLATES = 20
_NAME_RE = re.compile(r"^[^\\/:*?\"<>|]{1,60}$")


def kits_path() -> str:
    return os.path.join(os.path.dirname(vep.PROFILES_PATH), "brand_kits.json")


def load_kits() -> Dict[str, Dict[str, Any]]:
    data = vep._load_json_dict(kits_path())
    return {name: kit for name, kit in data.items() if isinstance(kit, dict)}


def _clean_name(name: Any) -> str:
    name = str(name or "").strip()
    if not _NAME_RE.match(name):
        raise ValueError("שם ערכת מותג לא תקין (1-60 תווים, בלי \\ / : * ? \" < > |).")
    return name


def _clean_templates(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    templates = []
    for item in raw[:MAX_TEMPLATES]:
        if isinstance(item, dict) and str(item.get("name") or "").strip() and isinstance(item.get("layer"), dict):
            templates.append({"name": str(item["name"]).strip()[:40], "layer": item["layer"]})
    return templates


def save_kit(name: Any, fields: Dict[str, Any], templates: Any = None) -> Dict[str, Any]:
    """שומר/מעדכן ערכה - רק שדות המותג (BRAND_FIELDS) נשמרים, השאר מתעלם."""
    name = _clean_name(name)
    kits = load_kits()
    if name not in kits and len(kits) >= MAX_KITS:
        raise ValueError(f"אפשר לשמור עד {MAX_KITS} ערכות מותג.")
    previous = kits.get(name, {})
    kit = {
        "fields": {key: fields[key] for key in BRAND_FIELDS if isinstance(fields, dict) and key in fields},
        "templates": _clean_templates(templates if templates is not None else previous.get("templates")),
        "created_at": previous.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    kits[name] = kit
    vep._write_json(kits_path(), kits)
    return kit


def delete_kit(name: str) -> bool:
    kits = load_kits()
    if name not in kits:
        return False
    del kits[name]
    vep._write_json(kits_path(), kits)
    return True


def rename_kit(old: str, new: Any) -> Dict[str, Any]:
    new = _clean_name(new)
    kits = load_kits()
    if old not in kits:
        raise KeyError(old)
    if new in kits and new != old:
        raise ValueError("כבר קיימת ערכת מותג בשם הזה.")
    kits[new] = kits.pop(old)
    vep._write_json(kits_path(), kits)
    return kits[new]


def apply_brand_kit(payload: Dict[str, Any], kits: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """payload לריצה/תצוגה -> עם ערכי הערכה המקושרת (הערכה גוברת על שדות המותג
    של המתכון - זו כל המטרה של "מקושר"). ערכה שנמחקה = המתכון רץ כמו שהוא."""
    name = str((payload or {}).get("brand_kit") or "").strip()
    if not name:
        return payload
    kit = (kits if kits is not None else load_kits()).get(name)
    if not kit:
        return payload
    merged = dict(payload)
    merged.update(kit.get("fields") or {})
    return merged
