# dataviz/web/episodes.py (עד 19.10.2026: utils/dataviz_episodes.py)
#
# הצד של ClipForge למסך סרטוני הנתונים בדפדפן: רשימת הפרקים תחת data/dataviz_episodes (קריאה בלבד),
# ויצירת פרק חדש מ-CSV. יצירה לעולם לא נוגעת בפרק קיים: התיקייה נוצרת ב-os.mkdir (נכשל אם קיימת),
# והבדיקה המלאה של ההגדרות והנתונים נעשית קודם בתיקייה זמנית - רק פרק שנטען בהצלחה נכתב ל-data/.

import io
import json
import os
import re
import tempfile
from typing import Any, Dict, List, Mapping

# pandas/matplotlib-תלויי מנוע ה-dataviz נטענים רק בפעולה עצמה: ייבוא ברמת המודול הוסיף ~0.2 שנ' להפעלת השרת (pandas)
import yaml
from utils.shared import data_paths

EPISODES_DIRNAME = data_paths.DATAVIZ_EPISODES
CSV_NAME = "data.csv"
MAX_HIDDEN = 500
HIDDEN_FILENAME = data_paths.DATAVIZ_HIDDEN   # ליד שאר קובצי ה-JSON של האפליקציה ב-data/, לא בתוך תיקיות הפרקים
CSV_MAX_MB = 25                 # 18.10.2026: היה 5MB - לכל קובץ (פרק חדש, קובץ נוסף, עדכון, המרה)
CSV_MAX_BYTES = CSV_MAX_MB * 1024 * 1024
MAX_EXTRA_SOURCES = 9            # פרק חדש: הקובץ הראשי ועד 9 קבצים נוספים (כל אחד עד CSV_MAX_BYTES)
NAME_RE = re.compile(r"^[\w\-]{1,40}$")
# 23.10.2026: שמות שמורים ב-Windows - פרק בשם "NUL" נפל על OSError / shutil.Error (500)
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def valid_new_name(name: str) -> bool:
    return bool(NAME_RE.match(name)) and not name.startswith((".", "_")) and name.upper() not in WINDOWS_RESERVED
THEMES = ("light", "dark")
PERIODS = ("day", "month", "year", "quarter")
OVERRIDES_DIRNAME = data_paths.DATAVIZ_OVERRIDES   # data/dataviz_overrides/<פרק>.json - שינויי הגדרות מהדפדפן, מחוץ לתיקיית הפרק


class EpisodeError(ValueError):
    """שגיאת קלט למשתמש (הודעה בעברית). status: 400 קלט לא תקין, 409 פרק בשם הזה כבר קיים."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def episodes_root(data_dir: str) -> str:
    return os.path.join(data_dir, EPISODES_DIRNAME)


def episode_folder(data_dir: str, name: str) -> str | None:
    """נתיב הפרק רק אם name הוא שם של תיקייה קיימת עם config.yaml ישירות תחת שורש הפרקים, אחרת None."""
    if not isinstance(name, str) or not name or name in (".", "..") or os.sep in name or "/" in name or "\\" in name:
        return None
    path = os.path.join(episodes_root(data_dir), name)
    if not os.path.isfile(os.path.join(path, "config.yaml")):
        return None
    # 23.10.2026: רק השם המדויק של התיקייה - ב-Windows גם "EP1" ו-"ep1." (נקודה או רווח בסוף) פותחים את "ep1", ומחיקה
    # דרכם השאירה את קובץ השינויים, ההסתרה והתגיות מאחור (הם לפי השם שנשלח)
    try:
        return path if name in os.listdir(episodes_root(data_dir)) else None
    except OSError:
        return None


def _summary(name: str, path: str) -> Dict[str, Any]:
    from dataviz.config import ConfigError, load_config
    overrides = load_overrides_for_path(path)
    try:
        config = load_config(os.path.join(path, "config.yaml"), overrides)
    except ConfigError as e:
        return {"name": name, "valid": False, "errors": e.errors[:5], "title": name}
    except Exception as e:  # קובץ שבור לא מפיל את כל הרשימה
        return {"name": name, "valid": False, "errors": [str(e)[:200]], "title": name}
    video = config["video"]
    return {
        "name": name, "valid": True, "errors": [], "title": config["title"], "subtitle": config.get("subtitle", ""),
        "chart": config["chart"], "theme": config["theme"], "width": video["width"], "height": video["height"],
        "fps": video["fps"], "sources": len(config["sources"]), "publish_enabled": bool(config["publish"]["enabled"]),
        "has_audio": bool(config["audio"].get("path")), "edited": bool(overrides),
        "series": dict(config.get("series") or {}),   # גל 41
        "has_map": bool((config.get("map") or {}).get("geojson")),   # גל 42: אפשר תרשים מפה
        "languages": sorted(str(k) for k in (config.get("translations") or {})),   # גל 55: גרסאות בשפות
    }


# ---------- עריכת הגדרות מהדפדפן ----------
# config.yaml של פרק הוא נתוני משתמש ב-data/ (לא דורסים אותם) - לכן העריכות נשמרות בקובץ override נפרד
# data/dataviz_overrides/<פרק>.json (קובץ חדש בלבד), והמנוע ממזג אותו מעל config.yaml בעת הטעינה (dataviz.config.load_config).
# רשימה סגורה של שדות; כל ערך מאומת. "איפוס" = מחיקת קובץ ה-override של עצמנו, לעולם לא נוגעים ב-config.yaml.
EDITABLE_TEXT = {"title": 200, "subtitle": 200}


def overrides_path(data_dir: str, name: str) -> str:
    return os.path.join(data_dir, OVERRIDES_DIRNAME, name + ".json")


def load_overrides_for_path(episode_path: str) -> Dict[str, Any]:
    """override של פרק לפי נתיב תיקיית הפרק (data/dataviz_episodes/<שם>). חסר/פגום = אין."""
    name = os.path.basename(os.path.normpath(episode_path))
    data_dir = os.path.dirname(os.path.dirname(os.path.normpath(episode_path)))
    try:
        with open(overrides_path(data_dir, name), "r", encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def clean_overrides(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """מאמת ומנקה את השינויים; מחזיר רק שדות מותרים. EpisodeError על ערך לא תקין."""
    from dataviz.charts import CHART_MODULES
    out: Dict[str, Any] = {}
    for key, limit in EDITABLE_TEXT.items():
        if key in raw:
            value = raw[key]
            if not isinstance(value, str) or len(value) > limit:
                raise EpisodeError(f"{key}: טקסט עד {limit} תווים.")
            out[key] = value.strip()
    if "chart" in raw:
        if raw["chart"] not in CHART_MODULES:
            raise EpisodeError("סוג תרשים לא מוכר.")
        out["chart"] = raw["chart"]
    if "theme" in raw:
        if raw["theme"] not in THEMES:
            raise EpisodeError("ערכת צבעים לא מוכרת.")
        out["theme"] = raw["theme"]
    if "top_n" in raw:
        top_n = raw["top_n"]
        if isinstance(top_n, bool) or not isinstance(top_n, int) or not 3 <= top_n <= 30:
            raise EpisodeError("מספר המקומות להצגה: מספר שלם בין 3 ל-30.")
        out["ranking"] = {"top_n": top_n}
    publish = raw.get("publish")
    if publish is not None:
        if not isinstance(publish, Mapping):
            raise EpisodeError("publish לא תקין.")
        pub: Dict[str, Any] = {}
        for key, limit in (("title", 200), ("description", 2000)):
            if key in publish:
                if not isinstance(publish[key], str) or len(publish[key]) > limit:
                    raise EpisodeError(f"publish.{key}: טקסט עד {limit} תווים.")
                pub[key] = publish[key].strip()
        if "hashtags" in publish:
            tags = publish["hashtags"]
            if not isinstance(tags, list) or len(tags) > 15 or not all(isinstance(t, str) and 0 < len(t.strip()) <= 40 for t in tags):
                raise EpisodeError("publish.hashtags: עד 15 תגיות (טקסט קצר).")
            pub["hashtags"] = [t.strip() for t in tags]
        if "enabled" in publish:
            if not isinstance(publish["enabled"], bool):
                raise EpisodeError("publish.enabled: כן/לא.")
            pub["enabled"] = publish["enabled"]
        if pub:
            out["publish"] = pub
    unknown = set(raw) - set(EDITABLE_TEXT) - {"chart", "theme", "top_n", "publish"}
    if unknown:
        raise EpisodeError("שדות לא נתמכים: " + ", ".join(sorted(str(k) for k in unknown)[:5]))
    return out


def set_overrides(data_dir: str, name: str, raw: Mapping[str, Any] | None) -> Dict[str, Any]:
    """שומר (או מאפס כש-raw ריק/None) את שינויי ההגדרות של הפרק. מאמת שהתוצאה עדיין הגדרה תקינה לפני הכתיבה.
    23.10.2026: דרך _write_overrides - גם הטופס הבסיסי וגם "↩️ אפס הכל" נכנסים להיסטוריית הגרסאות (קודם לא נשמרה
    אף גרסה, והאיפוס מחק את העריכות בלי דרך חזרה), ו-raw שאינו ריק לא מאפס יותר את מה שנערך בעורך המלא גם כשאחרי
    הניקוי לא נשאר בו שדה (למשל publish ריק)."""
    folder = episode_folder(data_dir, name)
    if folder is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    if not raw:
        return _write_overrides(data_dir, name, folder, {})
    # גל 39: הטופס הבסיסי לא מוחק שינויים שנעשו בעורך המלא (אירועים, קצב, צבעים...) - רק "איפוס" מוחק הכל
    from dataviz.config import merge
    kept = load_overrides_for_path(folder)
    for basic in BASIC_FORM_PATHS:
        _unset_path(kept, basic)
    return _write_overrides(data_dir, name, folder, merge(kept, clean_overrides(raw)))


def hidden_path(data_dir: str) -> str:
    return os.path.join(data_dir, HIDDEN_FILENAME)


def load_hidden(data_dir: str) -> List[str]:
    """שמות הפרקים שהוסתרו מהרשימה. קובץ חסר/פגום = אין מוסתרים (לא נכשלים)."""
    try:
        with open(hidden_path(data_dir), "r", encoding="utf-8") as f:
            names = json.load(f).get("hidden", [])
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(names, list):   # 23.10.2026: {"hidden": 5} הפיל את רשימת הפרקים (500)
        return []
    return sorted({n for n in names if isinstance(n, str)})


def set_hidden(data_dir: str, name: str, hidden: bool) -> List[str]:
    """מסתיר/מחזיר פרק לרשימה. כותב רק את קובץ ההסתרה עצמו - תיקיית הפרק וכל קובץ בה לא נוגעים.
    הכתיבה אטומית (קובץ זמני + החלפה של קובץ ההסתרה בלבד)."""
    if episode_folder(data_dir, name) is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    names = set(load_hidden(data_dir))
    names.add(name) if hidden else names.discard(name)
    # ניקוי: שמות של פרקים שכבר לא קיימים (נמחקו ידנית) נושרים מהקובץ, ויש תקרה קשיחה - הקובץ לא יכול לגדול בלי גבול
    names = {n for n in names if episode_folder(data_dir, n) is not None}
    names = set(sorted(names)[:MAX_HIDDEN])
    path = hidden_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"hidden": sorted(names)}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return sorted(names)


def list_episodes(data_dir: str, include_hidden: bool = False) -> List[Dict[str, Any]]:
    """הפרקים; מוסתרים לא מוצגים אלא אם include_hidden (ואז הם מסומנים hidden=True). גל 53: עם התגיות והתיקייה."""
    root = episodes_root(data_dir)
    if not os.path.isdir(root):
        return []
    hidden = set(load_hidden(data_dir))
    tags = load_tags(data_dir)
    rows = []
    for name in sorted(os.listdir(root)):
        if not os.path.isfile(os.path.join(root, name, "config.yaml")) or (name in hidden and not include_hidden):
            continue
        rows.append({**_summary(name, os.path.join(root, name)), "hidden": name in hidden,
                     "tags": list((tags.get(name) or {}).get("tags") or []), "folder": str((tags.get(name) or {}).get("folder") or "")})
    return rows


# ---------- גל 53: תגיות ותיקיות לפרקים ברשימה ----------
# קובץ של האפליקציה ליד קובץ ההסתרה (data/dataviz_tags.json) - תיקיות הפרקים לא משתנות. התיקייה היא רק קיבוץ ברשימה.
TAGS_FILENAME = data_paths.DATAVIZ_TAGS
MAX_TAGS = 12


def load_tags(data_dir: str) -> Dict[str, Dict[str, Any]]:
    try:
        with open(os.path.join(data_dir, TAGS_FILENAME), "r", encoding="utf-8") as f:
            value = json.load(f).get("episodes", {})
    except (OSError, ValueError, AttributeError):
        return {}
    # 23.10.2026: JSON תקין עם טיפוס שגוי ({"episodes": {"covid": "oops"}}) הפיל את רשימת הפרקים (500)
    return {str(k): v for k, v in value.items() if isinstance(v, dict)} if isinstance(value, dict) else {}


def set_tags(data_dir: str, name: str, tags: Any, folder: Any) -> Dict[str, Any]:
    if episode_folder(data_dir, name) is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(isinstance(t, str) and len(t.strip()) <= 30 for t in tags):
        raise EpisodeError(f"תגיות: עד {MAX_TAGS}, כל אחת עד 30 תווים.")
    folder_name = str(folder or "").strip()
    if len(folder_name) > 40 or any(c in folder_name for c in "\\/\n"):
        raise EpisodeError("תיקייה: שם עד 40 תווים, בלי לוכסנים.")
    clean = sorted({t.strip() for t in tags if t.strip()})
    all_tags = {n: v for n, v in load_tags(data_dir).items() if episode_folder(data_dir, n) is not None}
    if clean or folder_name:
        all_tags[name] = {"tags": clean, "folder": folder_name}
    else:
        all_tags.pop(name, None)
    path = os.path.join(data_dir, TAGS_FILENAME)
    os.makedirs(data_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"episodes": all_tags}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return {"tags": clean, "folder": folder_name}


def source_spec(path: str, mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """מקור אחד ל-config: מיפוי העמודות (time_column / period / value_column / group_column / legend) של קובץ."""
    time_spec: Dict[str, Any] = {"column": mapping["time_column"]}
    if mapping["period"] != "day":
        time_spec["period"] = mapping["period"]
    spec: Dict[str, Any] = {
        "path": path, "time": time_spec,
        "value": {"column": mapping["value_column"]} if mapping["value_column"] else "count",
        "entity": {"column": mapping["group_column"]} if mapping["group_column"] else {"from_time": "year"},
    }
    if mapping.get("legend"):
        spec["legend"] = mapping["legend"]
    if mapping.get("kind") == "level":   # 19.10.2026: רמות (טמפרטורה, מפלס) - לא מצטבר
        spec["kind"] = "level"
    if mapping.get("axis") == "right":   # 20.10.2026: ציר y ימני (מרוץ קווים)
        spec["axis"] = "right"
    if mapping.get("fill") in ("step", "linear"):   # 20.10.2026: השלמה לנתונים דלילים
        spec["fill"] = mapping["fill"]
    return spec


def extra_csv_name(index: int) -> str:
    """שם הקובץ בתיקיית הפרק לקובץ הנוסף ה-index (0 = השני): data_2.csv, data_3.csv..."""
    return f"data_{index + 2}.csv"


def safe_csv_name(filename: Any) -> str:
    """19.10.2026: שם קובץ מהמחשב של המשתמש לתיקיית הפרק - אותיות (גם עברית), ספרות, מקף וקו תחתון, תמיד .csv
    (Excel ו-JSON מומרים ל-CSV לפני השליחה). ריק = אין שם."""
    stem = os.path.splitext(os.path.basename(str(filename or "").replace("\\", "/")))[0]
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem).strip("_")[:60]
    return stem + ".csv" if stem else ""


def csv_file_names(form: Mapping[str, Any]) -> List[str]:
    """השמות של קובצי הנתונים בפרק חדש: השם המקורי של כל קובץ (נקי וייחודי - temp.csv, temp_2.csv), ובלי שם -
    data.csv / data_2.csv כמו קודם."""
    names: List[str] = []
    wanted = [form.get("filename")] + [extra.get("filename") for extra in form.get("extra_sources") or []]
    for i, filename in enumerate(wanted):
        name = safe_csv_name(filename) or (CSV_NAME if i == 0 else extra_csv_name(i - 1))
        stem, k = name[:-4], 2
        while name.lower() in {n.lower() for n in names}:
            name, k = f"{stem}_{k}.csv", k + 1
        names.append(name)
    return names


def build_config(form: Mapping[str, Any]) -> Dict[str, Any]:
    # 18.10.2026: כמה קבצים לפרק אחד - כל קובץ נוסף מקור משלו עם המיפוי שלו. 19.10.2026: בשם המקורי של הקובץ
    names = csv_file_names(form)
    config = {
        "title": form["title"], "subtitle": form["subtitle"], "chart": form["chart"], "theme": form["theme"],
        "sources": [source_spec(names[0], form)] + [source_spec(names[i + 1], extra)
                                                    for i, extra in enumerate(form.get("extra_sources") or [])],
    }
    if form.get("lang") == "en":
        config.update(json.loads(json.dumps(ENGLISH_DEFAULTS)))
    return config


# 30.10.2026 (לפני ההפצה): פרק שנוצר בממשק באנגלית מקבל תוויות ותבנית תאריך באנגלית - ברירות המחדל של dataviz/config.py
# בעברית ("שיא חדש", "אחרים", "מקום ראשון", התאריך יום/חודש/שנה). פרק בעברית - כמו קודם
ENGLISH_DEFAULTS: Dict[str, Any] = {
    "labels": {"date_format": "%b %d, %Y", "record": "New record: {entity}", "others": "Others"},
    "outro": {"places": ["1st place", "2nd place", "3rd place"]},
    "scatter": {"x_label": "Total", "y_label": "In the last 30 days"},
}


def clean_mapping(raw: Mapping[str, Any], label: str = "") -> Dict[str, Any]:
    """מיפוי העמודות של קובץ נוסף (פרק חדש מכמה קבצים, או קובץ שמתווסף לפרק קיים). זורק EpisodeError."""
    text = lambda key: str(raw.get(key) or "").strip()[:120]  # noqa: E731
    mapping = {"time_column": text("time_column"), "period": text("period") or "day", "value_column": text("value_column"),
               "group_column": text("group_column"), "legend": text("legend"), "kind": text("kind") or "amount",
               "axis": text("axis") or "left", "fill": text("fill") or "none", "filename": str(raw.get("filename") or "")[:200]}
    if mapping["axis"] not in ("left", "right"):
        raise EpisodeError(f"{label}הציר: שמאל או ימין.")
    if mapping["fill"] not in ("none", "step", "linear"):
        raise EpisodeError(f"{label}השלמה: בלי, מדרגות או קו ישר.")
    if mapping["period"] not in PERIODS:
        raise EpisodeError(f"{label}תקופת הזמן צריכה להיות יום, חודש או שנה.")
    if not mapping["time_column"]:
        raise EpisodeError(f"{label}בחר את עמודת התאריך.")
    _check_kind(mapping, label)
    return mapping


def _check_kind(mapping: Mapping[str, Any], label: str = "") -> None:
    if mapping["kind"] not in ("amount", "level"):
        raise EpisodeError(f"{label}סוג הערכים: כמות או רמה.")
    if mapping["kind"] == "level" and not mapping["value_column"]:
        raise EpisodeError(f"{label}רמה (טמפרטורה, מפלס) צריכה עמודת ערך - אין רמה בספירת שורות.")


def clean_table_text(csv_text: Any, label: str = "") -> str:
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise EpisodeError(f"{label}לא נבחר קובץ CSV (או שהוא ריק).")
    if len(csv_text.encode("utf-8")) > CSV_MAX_BYTES:
        raise EpisodeError(f"{label}קובץ ה-CSV גדול מ-{CSV_MAX_MB}MB.")
    return csv_text.lstrip("\ufeff")


def check_mapping_columns(mapping: Mapping[str, Any], columns: List[str], label: str = "") -> None:
    for key, name in (("time_column", "עמודת התאריך"), ("value_column", "עמודת הערך"), ("group_column", "עמודת הקיבוץ")):
        if mapping[key] and mapping[key] not in columns:
            raise EpisodeError(f"{label}{name} '{mapping[key]}' לא קיימת ב-CSV (העמודות: {', '.join(columns)}).")


def clean_form(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """מנקה ומאמת את טופס הפרק החדש (בלי לגעת בדיסק). זורק EpisodeError."""
    text = lambda key: str(raw.get(key) or "").strip()  # noqa: E731
    name = text("name")
    if not valid_new_name(name):
        raise EpisodeError("שם הפרק: עד 40 תווים - אותיות, ספרות, מקף וקו תחתון בלבד (בלי רווחים ובלי נקודות).")
    form: Dict[str, Any] = {"name": name, "title": text("title"), "subtitle": text("subtitle"), "chart": text("chart") or "bar_race",
            "theme": text("theme") or "light", "time_column": text("time_column"), "value_column": text("value_column"),
            "group_column": text("group_column"), "period": text("period") or "day", "template": text("template"),
            "kind": text("kind") or "amount", "filename": str(raw.get("filename") or "")[:200],
            "lang": "en" if raw.get("lang") == "en" else "he"}   # 30.10.2026: שפת הממשק שבה נוצר הפרק
    # 27.10.2026: גם תבנית שמורה ("tpl:<שם>", dataviz/web/plus.py) - לא רק פרק קיים
    if form["template"] and not (NAME_RE.match(form["template"]) or re.fullmatch(r"tpl:[\w\-]{1,60}", form["template"])):
        raise EpisodeError("תבנית לא תקינה.")
    if not form["title"]:
        raise EpisodeError("חסרה כותרת לפרק.")
    from dataviz.charts import CHART_MODULES
    if form["chart"] not in CHART_MODULES:
        raise EpisodeError("סוג תרשים לא מוכר.")
    if form["theme"] not in THEMES:
        raise EpisodeError("ערכת צבעים לא מוכרת (light או dark).")
    if form["period"] not in PERIODS:
        raise EpisodeError("תקופת הזמן צריכה להיות יום, חודש או שנה.")
    if not form["time_column"]:
        raise EpisodeError("בחר את עמודת התאריך.")
    _check_kind(form)
    form["csv_text"] = clean_table_text(raw.get("csv_text"))
    extras = raw.get("extra_sources") or []
    if not isinstance(extras, list) or len(extras) > MAX_EXTRA_SOURCES:
        raise EpisodeError(f"עד {MAX_EXTRA_SOURCES} קבצים נוספים לפרק.")
    form["extra_sources"] = []
    for i, extra in enumerate(extras):
        label = f"קובץ {i + 2}: "
        if not isinstance(extra, Mapping):
            raise EpisodeError(f"{label}בקשה לא תקינה.")
        form["extra_sources"].append(dict(clean_mapping(extra, label), csv_text=clean_table_text(extra.get("csv_text"), label)))
    return form


def csv_columns(csv_text: str) -> List[str]:
    import pandas as pd
    try:
        return [str(c) for c in pd.read_csv(io.StringIO(csv_text.lstrip("\ufeff")), nrows=5).columns]
    except Exception as e:
        raise EpisodeError(f"לא ניתן לקרוא את ה-CSV: {str(e)[:150]}") from e


def create_episode(data_dir: str, raw: Mapping[str, Any]) -> Dict[str, Any]:
    from dataviz.config import ConfigError
    from dataviz.episode import load_episode
    form = clean_form(raw)
    check_mapping_columns(form, csv_columns(form["csv_text"]))
    for i, extra in enumerate(form["extra_sources"]):
        check_mapping_columns(extra, csv_columns(extra["csv_text"]), f"קובץ {i + 2}: ")
    names = csv_file_names(form)
    files = [(names[0], form["csv_text"])] + [(names[i + 1], extra["csv_text"]) for i, extra in enumerate(form["extra_sources"])]
    config = build_config(form)
    if form["template"]:
        config = _inherit_template(data_dir, form["template"], config)   # גל 41: פרק חדש מתבנית של פרק קיים
    config_text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)

    # שלב 1: בדיקה מלאה בתיקייה זמנית - שום דבר לא נכתב ל-data/ עד שהפרק נטען בהצלחה
    with tempfile.TemporaryDirectory() as tmp:
        for filename, content in files:
            with open(os.path.join(tmp, filename), "w", encoding="utf-8", newline="") as f:
                f.write(content)
        with open(os.path.join(tmp, "config.yaml"), "w", encoding="utf-8") as f:
            f.write(config_text)
        try:
            episode = load_episode(tmp)
        except ConfigError as e:
            raise EpisodeError("ההגדרות לא תקינות: " + "; ".join(e.errors[:3])) from e
        except Exception as e:
            raise EpisodeError(f"הנתונים לא נטענו (בדוק את עמודת התאריך והערך): {str(e)[:150]}") from e
        if episode.n_days < 2 or not episode.entities:
            raise EpisodeError("אחרי הסינון נשארו פחות משני ימים או אין ישויות - בדוק את העמודות שנבחרו.")

    # שלב 2: יצירה אטומית בשם חדש - FileExistsError = פרק קיים, לא נוגעים בו
    root = episodes_root(data_dir)
    os.makedirs(root, exist_ok=True)
    dest = os.path.join(root, form["name"])
    try:
        os.mkdir(dest)
    except FileExistsError as e:
        raise EpisodeError(f"כבר קיים פרק בשם '{form['name']}' - בחר שם אחר (לא דורסים פרקים קיימים).", status=409) from e
    written = []
    try:
        for filename, content in files + [("config.yaml", config_text)]:
            path = os.path.join(dest, filename)
            with open(path, "x", encoding="utf-8", newline="") as f:
                f.write(content)
            written.append(path)
    except OSError as e:
        for path in written:        # מנקים רק מה שנוצר כאן, בתיקייה שנוצרה כאן
            os.remove(path)
        if not os.listdir(dest):
            os.rmdir(dest)
        raise EpisodeError(f"כתיבת הפרק נכשלה: {e}", status=500) from e
    return _summary(form["name"], dest)


# ---------- גל 39: עורך ההגדרות המלא (שדה-שדה), אירועים, צבעים וישויות ----------
# כל השינויים הולכים לאותו קובץ override (config.yaml לעולם לא נכתב). כל ערך מאומת לפי הסכימה
# (dataviz/schema.py) או לפי הבודק של השדה המיוחד, והתוצאה כולה נבדקת ב-load_config לפני הכתיבה.

BASIC_FORM_PATHS = ("title", "subtitle", "chart", "theme", "ranking.top_n", "publish.title", "publish.description",
                    "publish.hashtags", "publish.enabled")
THEME_COLOR_KEYS = ("bg", "ink", "muted", "grid", "accent", "card")
MAX_EVENTS = 300
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX_RE.match(value):
        raise EpisodeError(f"{label}: צבע בפורמט #rrggbb.")
    return value.lower()


# גל 50: רשימות הסיפור - השדות שכל פריט יכול להכיל (החובה והתאריכים לפי dataviz/config.STORY_ITEMS)
STORY_LISTS = {"story.chapters": ("date", "title", "subtitle", "seconds"), "story.pauses": ("date", "text", "seconds"),
               "story.callouts": ("date", "entity", "text", "days", "dx", "dy"),   # 27.10.2026: dx/dy - גרירה בתצוגה
               "story.periods": ("start", "end", "label", "color"),
               "story.speed": ("start", "end", "speed"),
               "story.annotations": ("date", "value", "text", "days", "dx", "dy", "style"),   # 20.10.2026
               "story.focus": ("date", "entities"),   # 20.10.2026: החלפת פוקוס
               "story.script": ("date", "text")}      # 20.10.2026: תסריט קריינות
_STORY_NUMBERS = {"seconds": (0.5, 30.0), "speed": (0.1, 20.0)}


def _clean_story(path: str, value: Any) -> List[Dict[str, Any]]:
    import pandas as pd

    from dataviz.config import MAX_STORY_ITEMS, STORY_ITEMS
    required, date_keys = STORY_ITEMS[path.split(".", 1)[1]]
    if not isinstance(value, list) or len(value) > MAX_STORY_ITEMS:
        raise EpisodeError(f"רשימה של עד {MAX_STORY_ITEMS} פריטים.")
    items: List[Dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise EpisodeError("פריט לא תקין ברשימה.")
        item: Dict[str, Any] = {}
        for key in STORY_LISTS[path]:
            v = raw.get(key)
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            try:
                if key in date_keys:
                    item[key] = pd.Timestamp(str(v)).strftime("%Y-%m-%d")
                elif key in _STORY_NUMBERS:
                    lo, hi = _STORY_NUMBERS[key]
                    number = float(v)
                    if not lo <= number <= hi:
                        raise EpisodeError(f"{key}: בין {lo:g} ל-{hi:g}.")
                    item[key] = number
                elif key == "days":
                    item[key] = max(1, min(3650, int(v)))
                elif key == "value":   # 20.10.2026: הערה על הגרף - ערך על ציר ה-y
                    item[key] = float(v)
                elif key in ("dx", "dy"):
                    item[key] = max(-400, min(400, int(v)))
                elif key == "entities":   # 20.10.2026: רשימה, או טקסט מופרד בפסיקים מהטבלה
                    names = v if isinstance(v, list) else str(v).split(",")
                    item[key] = [str(n).strip()[:80] for n in names if str(n).strip()][:20]
                    if not item[key]:
                        continue
                elif key == "style":
                    from dataviz.config import ANNOTATION_STYLES
                    if v not in ANNOTATION_STYLES:
                        raise EpisodeError("סגנון: רגיל, הדגשה או עמום.")
                    item[key] = v
                elif key == "color":
                    item[key] = _hex(v, "צבע התקופה")
                else:
                    item[key] = str(v).strip()[:160]
            except (ValueError, TypeError) as e:
                if isinstance(e, EpisodeError):
                    raise
                raise EpisodeError(f"ערך לא תקין ({key}): {v!r}") from None
        missing = [k for k in required if k not in item]
        if missing:
            raise EpisodeError("חסר: " + ", ".join(missing))
        items.append(item)
    return sorted(items, key=lambda i: i[date_keys[0]])


def _clean_fixes(value: Any) -> List[Dict[str, Any]]:
    """גל 52: תיקוני קפיצות חשודות - {entity, date, action: spread/smooth/set, value?, days?}."""
    import pandas as pd

    from dataviz.cleaning import FIX_ACTIONS
    if not isinstance(value, list) or len(value) > 500:
        raise EpisodeError("תיקונים: רשימה של עד 500.")
    fixes = []
    for raw in value:
        if not isinstance(raw, Mapping) or raw.get("action") not in FIX_ACTIONS or not str(raw.get("entity", "")).strip():
            raise EpisodeError("תיקון צריך ישות, תאריך ופעולה.")
        try:
            fix: Dict[str, Any] = {"entity": str(raw["entity"]).strip()[:80], "date": pd.Timestamp(str(raw.get("date"))).strftime("%Y-%m-%d"),
                                   "action": raw["action"]}
            if raw["action"] == "set":
                if raw.get("value") in (None, ""):
                    raise ValueError("set בלי ערך")
                fix["value"] = float(raw["value"])
            if raw.get("days") not in (None, ""):
                fix["days"] = max(1, min(365, int(raw["days"])))
        except (ValueError, TypeError):
            raise EpisodeError("תיקון לא תקין (תאריך או ערך).") from None
        fixes.append(fix)
    return fixes


def _clean_special(path: str, value: Any) -> Any:
    """ערך לשדה שאינו שדה פשוט בסכימה (אירועים, צבעים, ישויות, ערכת עיצוב) - או לשדה פשוט דרך הסכימה."""
    from dataviz import schema
    if path in STORY_LISTS:
        return _clean_story(path, value)
    if path == "data.fixes":
        return _clean_fixes(value)
    if path == "outro.position":   # 27.10.2026: תיבת הסיום שנגררה בתצוגה - [x, y] של אזור הנתונים, או [] (המקום האוטומטי)
        if value in (None, [], ""):
            return []
        if (not isinstance(value, list) or len(value) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and -0.5 <= v <= 1.5 for v in value)):
            raise EpisodeError("מיקום תיבת הסיום: [x, y] בין -0.5 ל-1.5.")
        return [round(float(v), 4) for v in value]
    if path == "focus.entities":   # 20.10.2026: מצב פוקוס - שמות ישויות
        if not isinstance(value, list) or len(value) > 20 or not all(isinstance(v, (str, int, float)) for v in value):
            raise EpisodeError("פוקוס: רשימה של עד 20 ישויות.")
        return [str(v).strip()[:80] for v in value if str(v).strip()]
    if path.startswith("translations."):   # גל 55: גרסה בשפה אחרת - רק השדות המותרים
        from dataviz.languages import LANGUAGES, clean_translation
        if path.split(".", 1)[1] not in LANGUAGES:
            raise EpisodeError("שפה לא נתמכת.")
        try:
            return clean_translation(value)
        except ValueError as e:
            raise EpisodeError(str(e)) from e
    if path == "events":
        if not isinstance(value, list) or len(value) > MAX_EVENTS:
            raise EpisodeError(f"אירועים: רשימה של עד {MAX_EVENTS}.")
        import pandas as pd
        events = []
        for item in value:
            if not isinstance(item, Mapping) or not str(item.get("label", "")).strip():
                raise EpisodeError("אירוע צריך תאריך ותיאור.")
            try:
                date = pd.Timestamp(str(item.get("date", ""))).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                raise EpisodeError(f"תאריך לא תקין לאירוע: {item.get('date')!r}") from None
            events.append({"date": date, "label": str(item["label"]).strip()[:120]})
        return sorted(events, key=lambda e: e["date"])
    if path == "colors":
        if not isinstance(value, Mapping) or len(value) > 200:
            raise EpisodeError("צבעים: ישות -> צבע.")
        return {str(k)[:80]: _hex(v, f"צבע של {k}") for k, v in value.items()}
    if path == "entities.aliases":
        if not isinstance(value, Mapping) or len(value) > 500:
            raise EpisodeError("שמות חלופיים: ישות -> שם.")
        return {str(k)[:80]: str(v).strip()[:80] for k, v in value.items() if str(v).strip() and str(v).strip() != str(k)}
    if path == "entities.exclude":
        if not isinstance(value, list) or len(value) > 500:
            raise EpisodeError("ישויות מוחרגות: רשימה.")
        return sorted({str(v)[:80] for v in value})
    if path == "theme":   # גל 41: ערכת ערוץ מחילה גם את הערכה
        if value not in THEMES:
            raise EpisodeError("ערכת צבעים לא מוכרת (light או dark).")
        return value
    if path == "audio.path":   # גל 40: קובץ מוזיקה מתיקיית הפרק (שם קובץ בלבד; ריק = בלי מוזיקה)
        name = str(value or "").strip()
        if name and (os.sep in name or "/" in name or "\\" in name or not name.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"))):
            raise EpisodeError("קובץ מוזיקה: שם של קובץ שמע מתיקיית הפרק.")
        return name
    if path.startswith("theme_overrides."):
        key = path.split(".", 1)[1]
        if key in THEME_COLOR_KEYS:
            return _hex(value, key)
        if key in ("categorical", "ordinal"):
            if not isinstance(value, list) or not 2 <= len(value) <= 20:
                raise EpisodeError("פלטה: 2 עד 20 צבעים.")
            return [_hex(v, "צבע בפלטה") for v in value]
        if key == "fonts":   # גל 43: גופן (שם משפחה מותקן), עם גופני הגיבוי אחריו
            return clean_fonts(value)
        raise EpisodeError(f"שדה עיצוב לא נתמך: {key}")
    try:
        return schema.clean_value(path, value)
    except schema.FieldError as e:
        raise EpisodeError(str(e)) from e


FONT_RE = re.compile(r"^[\w \-\.&']{1,60}$")


def clean_fonts(value: Any) -> List[str]:
    """רשימת שמות גופן (הראשון קובע, השאר גיבוי) - שמות משפחה בלבד, לא נתיבים."""
    if not isinstance(value, list) or not 1 <= len(value) <= 6 or not all(isinstance(v, str) and FONT_RE.match(v.strip()) for v in value):
        raise EpisodeError("גופן: עד 6 שמות של גופנים מותקנים.")
    return [v.strip() for v in value]


def _set_path(target: Dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    node = target
    for key in keys[:-1]:
        if not isinstance(node.get(key), dict):
            node[key] = {}
        node = node[key]
    node[keys[-1]] = value


def _unset_path(target: Dict[str, Any], path: str) -> None:
    keys = path.split(".")
    chain = [target]
    for key in keys[:-1]:
        node = chain[-1].get(key)
        if not isinstance(node, dict):
            return
        chain.append(node)
    chain[-1].pop(keys[-1], None)
    for depth in range(len(keys) - 1, 0, -1):   # מילונים שהתרוקנו נמחקים
        if not chain[depth]:
            chain[depth - 1].pop(keys[depth - 1], None)


def _write_overrides(data_dir: str, name: str, folder: str, overrides: Dict[str, Any], check: bool = True) -> Dict[str, Any]:
    """check=False (גל 52): רק כשמוסיפים מקור מכתובת - הבדיקה המלאה קורית אחרי שהוא הורד."""
    from dataviz.config import ConfigError, load_config
    path = overrides_path(data_dir, name)
    previous = load_overrides_for_path(folder) if folder else {}
    if not overrides:
        try:
            os.remove(path)   # safe: רק קובץ ה-override שהאפליקציה עצמה יצרה
        except FileNotFoundError:
            pass
        _remember(data_dir, name, folder, {}, previous)
        return {}
    try:
        if check:
            load_config(os.path.join(folder, "config.yaml"), overrides)
    except ConfigError as e:
        raise EpisodeError("ההגדרות לא תקינות: " + "; ".join(e.errors[:3])) from e
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    _remember(data_dir, name, folder, overrides, previous)
    return overrides


def _remember(data_dir: str, name: str, folder: str, overrides: Mapping[str, Any], previous: Mapping[str, Any]) -> None:
    """20.10.2026: תמונת מצב בהיסטוריית הגרסאות (dataviz/web/history.py). כשל בה לא מפיל שמירה."""
    if not folder:
        return
    from dataviz.smart import learn
    from dataviz.web import history
    try:
        history.record(data_dir, name, folder, overrides, previous)
        learn.observe(data_dir, name, overrides)   # 20.10.2026: בחירה אוטומטית שהוחלפה ביד -> העדפה לטיוטות הבאות
    except (OSError, ValueError, TypeError):
        pass


def draft_overrides(base: Mapping[str, Any], changes: Mapping[str, Any]) -> Dict[str, Any]:
    """שינויים שעוד לא נשמרו (לתצוגה החיה): נתיב -> ערך, מאומתים, מעל ה-override השמור. לא נכתב כלום."""
    result: Dict[str, Any] = json.loads(json.dumps(dict(base)))
    for path, value in (changes or {}).items():
        _set_path(result, str(path), _clean_special(str(path), value))
    return result


def update_override_fields(data_dir: str, name: str, set_values: Mapping[str, Any] | None, unset: List[str] | None) -> Dict[str, Any]:
    """משנה שדות בודדים ב-override של הפרק (ולא מחליף את כולו): set = נתיב -> ערך, unset = נתיבים שחוזרים
    לקובץ הפרק / לברירת המחדל."""
    folder = episode_folder(data_dir, name)
    if folder is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    overrides = load_overrides_for_path(folder)
    for path in unset or []:
        _unset_path(overrides, str(path))
    overrides = draft_overrides(overrides, set_values or {})
    return _write_overrides(data_dir, name, folder, overrides)


def _flatten(node: Mapping[str, Any], prefix: str = "") -> List[str]:
    paths: List[str] = []
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, Mapping) and value and path not in ("colors", "entities.aliases"):
            paths.extend(_flatten(value, path))
        else:
            paths.append(path)
    return paths


def editor_data(data_dir: str, name: str, entities: List[Dict[str, Any]] | None = None, date_range: List[str] | None = None,
                lang: str = "he") -> Dict[str, Any]:
    """כל מה שעורך ההגדרות צריך: הטופס לפי קבוצות (ערך / ברירת מחדל / בקובץ / שונה כאן), האירועים, הצבעים,
    כללי הישויות, ורשימת מה ששונה מול קובץ הפרק."""
    from dataviz import looks, schema
    from dataviz.config import ConfigError, load_config
    from dataviz.episode import load_events
    from dataviz.themes import get_theme
    folder = episode_folder(data_dir, name)
    if folder is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    with open(os.path.join(folder, "config.yaml"), "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    overrides = load_overrides_for_path(folder)
    try:
        config = load_config(os.path.join(folder, "config.yaml"), overrides)
    except ConfigError as e:
        raise EpisodeError("ההגדרות לא תקינות: " + "; ".join(e.errors[:3])) from e
    theme = get_theme(config["theme"], config.get("theme_overrides"))
    events_raw = config.get("events")
    changes = []
    for path in _flatten(overrides):
        from dataviz.i18n_en import tr
        label = tr((schema.FIELD_BY_PATH.get(path) or {}).get("label", path), lang)
        in_file, file_value = schema.get_path(raw, path)
        if not in_file:
            try:
                file_value = schema.default_value(path)
            except (KeyError, TypeError):
                file_value = None
        changes.append({"path": path, "label": label, "was": file_value, "now": schema.get_path(overrides, path)[1], "from_file": in_file})
    return {
        "episode": name,
        "groups": schema.form_groups(config, raw, overrides, lang),
        "events": [{"date": d, "label": label} for d, label in load_events(config)],
        "events_source": "override" if "events" in overrides else ("file" if isinstance(events_raw, str) else "config"),
        "events_file": events_raw if isinstance(events_raw, str) else "",
        "theme": {"name": theme.name, **{k: getattr(theme, k) for k in THEME_COLOR_KEYS},
                  "categorical": list(theme.categorical), "ordinal": list(theme.ordinal), "fonts": list(theme.fonts),
                  "overridden": sorted((overrides.get("theme_overrides") or {}).keys())},
        "colors": dict(config.get("colors") or {}),
        "entity_rules": {"aliases": dict((config.get("entities") or {}).get("aliases") or {}),
                         "exclude": list((config.get("entities") or {}).get("exclude") or [])},
        "entities": entities or [],
        "date_range": date_range or [],
        "changes": changes,
        # גל 55: התרגומים שנשמרו (לשונית "שפות")
        "translations": {str(k): dict(v) for k, v in (config.get("translations") or {}).items()},
        # גל 51: מראות מוכנים (לשונית הצבעים) - והנתיבים שכל מראה מחזיר לקובץ אם הוא לא קובע אותם
        "looks": looks.looks(lang),
        "look_paths": looks.all_paths(),
        # גל 50: רשימות הסיפור (לשונית "📖 סיפור")
        "story": {key.split(".", 1)[1]: list((config.get("story") or {}).get(key.split(".", 1)[1]) or []) for key in STORY_LISTS},
        "focus": {"entities": [str(n) for n in (config.get("focus") or {}).get("entities") or []]},   # 20.10.2026: מצב פוקוס
    }


def final_config(data_dir: str, name: str) -> Dict[str, Any]:
    """ההגדרות שהרינדור יקבל בפועל (19.10.2026): config.yaml + קובץ השינויים מהדפדפן + ברירות המחדל של המנוע,
    מאוחדות כמו ב-dataviz_maker, ולכל הגדרה מאיפה היא באה (override / file / default). לקריאה בלבד."""
    from dataviz import schema
    from dataviz.config import ConfigError, load_config
    folder = episode_folder(data_dir, name)
    if folder is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    with open(os.path.join(folder, "config.yaml"), "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    overrides = load_overrides_for_path(folder)
    try:
        config = load_config(os.path.join(folder, "config.yaml"), overrides)
    except ConfigError as e:
        raise EpisodeError("ההגדרות לא תקינות: " + "; ".join(e.errors[:3])) from e
    for key in ("base_dir", "name", "numbers_set"):   # נגזרים מהתיקייה ומהקובץ, לא הגדרות
        config.pop(key, None)
    from dataviz.smart.create import auto_marks
    marks = auto_marks(data_dir, name)   # 20.10.2026: בחירות של עורך הגרפים החכם - 🤖 עם סיבה וביטחון
    rows = []
    for path in _flatten(config):
        source = "override" if schema.get_path(overrides, path)[0] else ("file" if schema.get_path(raw, path)[0] else "default")
        row = {"path": path, "value": schema.get_path(config, path)[1], "source": source}
        mark = marks.get(path)
        if mark and source == "override" and row["value"] == mark["value"]:
            row["auto"] = {"reason": mark["reason"], "confidence": mark["confidence"]}
        rows.append(row)
    return {"episode": name, "rows": rows,
            "yaml": yaml.safe_dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False),
            "files": {"file": os.path.join(EPISODES_DIRNAME, name, "config.yaml"),
                      "override": os.path.join(OVERRIDES_DIRNAME, name + ".json")}}


# ---------- גל 41: שכפול פרק, תבנית וסדרה ----------
# מה שעובר מתבנית לפרק חדש: כל העיצוב והקצב - לא הכותרת, לא הנתונים ולא האירועים
TEMPLATE_KEYS = ("video", "timing", "ranking", "records", "cards", "labels", "outro", "scatter", "current_entity",
                 "theme_overrides", "logo", "series", "numbers", "style")


def _inherit_template(data_dir: str, template: str, config: Dict[str, Any]) -> Dict[str, Any]:
    from dataviz.config import ConfigError, load_config
    if template.startswith("tpl:"):   # 27.10.2026: תבנית שמורה - כבר מכילה רק את המפתחות שעוברים (ונתיב לוגו מלא)
        from dataviz.web.plus import load_template
        saved = load_template(data_dir, template)
        if saved is None:
            raise EpisodeError("התבנית לא נמצאה.", status=404)
        result = dict(config)
        for key, value in saved.items():
            if key in TEMPLATE_KEYS or key == "publish":
                result[key] = value
        series = result.get("series") or {}
        if isinstance(series, dict) and series.get("name"):
            series["number"] = int(series.get("number") or 0) + 1
        return result
    folder = episode_folder(data_dir, template)
    if folder is None:
        raise EpisodeError("פרק התבנית לא נמצא.", status=404)
    try:
        source = load_config(os.path.join(folder, "config.yaml"), load_overrides_for_path(folder))
    except ConfigError as e:
        raise EpisodeError("פרק התבנית לא תקין: " + "; ".join(e.errors[:3])) from e
    result = dict(config)
    for key in TEMPLATE_KEYS:
        value = json.loads(json.dumps(source.get(key), default=str))
        if key == "video":
            value.pop("output_name", None)
        if key == "logo" and value.get("path"):
            value["path"] = os.path.join(folder, str(value["path"]))
        if key == "series" and value.get("name"):
            value["number"] = int(value.get("number") or 0) + 1
        result[key] = value
    publish = source.get("publish") or {}
    result["publish"] = {k: publish[k] for k in ("enabled", "hashtags", "seo_ai", "thumbnail", "approval") if k in publish}
    return result


def duplicate_episode(data_dir: str, source: str, new_name: str, next_in_series: bool = False) -> Dict[str, Any]:
    """עותק של פרק בשם חדש - כל הקבצים, וגם השינויים מהדפדפן. הפרק המקורי לא משתנה; שם קיים = שגיאה.
    next_in_series: המספר בסדרה עולה באחד (ושם הסדרה = שם הפרק המקורי כשאין סדרה)."""
    import shutil
    from dataviz.config import load_config
    folder = episode_folder(data_dir, source)
    if folder is None:
        raise EpisodeError("הפרק לא נמצא.", status=404)
    new_name = str(new_name or "").strip()
    if not valid_new_name(new_name):
        raise EpisodeError("שם הפרק: עד 40 תווים - אותיות, ספרות, מקף וקו תחתון בלבד (בלי רווחים ובלי נקודות).")
    overrides = load_overrides_for_path(folder)
    if next_in_series:
        config = load_config(os.path.join(folder, "config.yaml"), overrides)
        series = dict(config.get("series") or {})
        overrides = dict(overrides, series={"name": series.get("name") or source, "number": int(series.get("number") or 1) + 1})
    dest = os.path.join(episodes_root(data_dir), new_name)
    try:
        shutil.copytree(folder, dest)   # נכשל אם התיקייה קיימת - לא דורסים פרק
    except FileExistsError as e:
        raise EpisodeError(f"כבר קיים פרק בשם '{new_name}' - בחר שם אחר.", status=409) from e
    # 23.10.2026: הקבצים שנוספו מהדפדפן (מקורות, משקלות, הקלטות, תמונות) ומטמון המקורות מכתובת יושבים מחוץ לתיקיית
    # הפרק, וה-override מצביע עליהם בנתיב מוחלט - העותק קיבל את אותם נתיבים, ונשבר כשהמקור נמחק. עכשיו הם מועתקים
    # לתיקיות של העותק, והנתיבים מתעדכנים
    for root in (OVERRIDES_DIRNAME, data_paths.DATAVIZ_CACHE):
        old, new = os.path.abspath(os.path.join(data_dir, root, source)), os.path.abspath(os.path.join(data_dir, root, new_name))
        if os.path.isdir(old):
            shutil.copytree(old, new, dirs_exist_ok=True)
            overrides = _repoint(overrides, old, new)
    if overrides:
        _write_overrides(data_dir, new_name, dest, overrides)
    return _summary(new_name, dest)


def _repoint(node: Any, old: str, new: str) -> Any:
    """כל נתיב מוחלט בתוך old (או old עצמו) עובר ל-new - בכל עומק של ה-override."""
    if isinstance(node, dict):
        return {key: _repoint(value, old, new) for key, value in node.items()}
    if isinstance(node, list):
        return [_repoint(value, old, new) for value in node]
    if isinstance(node, str) and os.path.isabs(node):
        path = os.path.normcase(os.path.normpath(node))
        prefix = os.path.normcase(old)
        if path == prefix or path.startswith(prefix + os.sep):
            return new + os.path.normpath(node)[len(old):]
    return node

# ---------- 19.10.2026: ייבוא תיקיית פרק (ColdData/Graphs, workspace/dataviz_israel_staging) ----------
IMPORT_MAX_BYTES = 300 * 1024 * 1024   # כל התיקייה
IMPORT_MAX_FILES = 2000
IMPORT_SKIP = (".git", "__pycache__", ".DS_Store", "Thumbs.db", "desktop.ini")


def import_episode_folder(data_dir: str, path: Any, name: Any = "") -> Dict[str, Any]:
    """מעתיק תיקיית פרק מוכנה (config.yaml, קובצי נתונים, אירועים, SOURCES.md...) ל-data/dataviz_episodes/<שם> - במקום
    העתקה ביד. תיקיית המקור רק נקראת. העותק נבדק קודם בתיקייה זמנית (load_episode, כמו פרק חדש), ורק אז עובר לשם הסופי
    בשינוי שם אחד; שם קיים = 409, ופרק קיים לא נדרס."""
    import shutil
    from dataviz.config import ConfigError
    from dataviz.episode import load_episode
    source = os.path.abspath(str(path or "").strip().strip('"'))
    if not str(path or "").strip() or not os.path.isdir(source):
        raise EpisodeError("התיקייה לא נמצאה.", status=404)
    if not os.path.isfile(os.path.join(source, "config.yaml")):
        raise EpisodeError("אין בתיקייה config.yaml - זו לא תיקיית פרק.")
    root = os.path.abspath(episodes_root(data_dir))
    try:
        inside = os.path.commonpath([source, root]) == root
    except ValueError:   # 20.10.2026: כוננים שונים (E: מול C:) - commonpath נכשל; בטוח לא בתוך הפרקים
        inside = False
    if inside:
        raise EpisodeError("התיקייה כבר בתוך הפרקים של האפליקציה.")
    name = str(name or "").strip() or os.path.basename(source)
    if not valid_new_name(name):
        raise EpisodeError("שם הפרק: עד 40 תווים - אותיות, ספרות, מקף וקו תחתון בלבד (בלי רווחים ובלי נקודות).")
    dest = os.path.join(root, name)
    if os.path.exists(dest):
        raise EpisodeError(f"כבר קיים פרק בשם '{name}' - בחר שם אחר (לא דורסים פרקים קיימים).", status=409)
    total = count = 0
    for folder, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if d not in IMPORT_SKIP]
        for filename in files:
            if filename in IMPORT_SKIP:
                continue
            total += os.path.getsize(os.path.join(folder, filename))
            count += 1
    if total > IMPORT_MAX_BYTES or count > IMPORT_MAX_FILES:
        raise EpisodeError(f"התיקייה גדולה מדי לייבוא ({count} קבצים, {total // (1024 * 1024)}MB; עד {IMPORT_MAX_FILES} קבצים ו-{IMPORT_MAX_BYTES // (1024 * 1024)}MB).")
    os.makedirs(root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".import_", dir=root)   # באותו כונן - המעבר לשם הסופי אטומי
    try:
        copy = os.path.join(staging, name)
        shutil.copytree(source, copy, ignore=shutil.ignore_patterns(*IMPORT_SKIP))
        try:
            episode = load_episode(copy)
        except ConfigError as e:
            raise EpisodeError("ההגדרות בתיקייה לא תקינות: " + "; ".join(e.errors[:3])) from e
        except Exception as e:
            raise EpisodeError(f"הנתונים בתיקייה לא נטענו: {str(e)[:200]}") from e
        if episode.n_days < 2 or not episode.entities:
            raise EpisodeError("בנתונים של התיקייה פחות משני ימים או אין ישויות.")
        try:
            os.rename(copy, dest)
        except FileExistsError as e:
            raise EpisodeError(f"כבר קיים פרק בשם '{name}' - בחר שם אחר (לא דורסים פרקים קיימים).", status=409) from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)   # safe: התיקייה הזמנית שיצרנו כאן (העותק כבר הועבר, או שהייבוא נכשל)
    return {**_summary(name, dest), "imported_from": source, "files": count}


def staging_folder(workspace_dir: str) -> str:
    """19.10.2026: תיקיית פרקי הטיוטה - workspace/dataviz/staging (תוצרים לפי כלי), ולפני ההעברה workspace/dataviz_israel_staging.
    הקוד לא כותב לשם - רק מציע אותה בייבוא. אין אף אחת = ""."""
    from utils.shared.workspace_dir import DATAVIZ, STAGING_MOVES, tool_output_dir
    new = tool_output_dir(DATAVIZ, "staging", base=workspace_dir)
    old = [os.path.join(workspace_dir, *old_parts) for new_parts, old_parts in STAGING_MOVES if new_parts == (DATAVIZ, "staging")]
    return next((path for path in [new, *old] if os.path.isdir(path)), "")


def import_suggestions(data_dir: str, workspace_dir: str) -> Dict[str, Any]:
    """פרקים מוכנים לייבוא: תתי-התיקיות של תיקיית הטיוטה שיש בהן config.yaml, עם הכותרת, ואם כבר יובאו (אותו שם בפרקים)."""
    folder = staging_folder(workspace_dir)
    items: List[Dict[str, Any]] = []
    if folder:
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            config = os.path.join(path, "config.yaml")
            if not os.path.isfile(config):
                continue
            try:
                with open(config, "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                title = str(raw.get("title") or "") if isinstance(raw, Mapping) else ""
            except (OSError, yaml.YAMLError):
                title = ""
            items.append({"name": name, "path": path, "title": title, "imported": os.path.isdir(os.path.join(episodes_root(data_dir), name))})
    return {"folder": folder, "episodes": items}
