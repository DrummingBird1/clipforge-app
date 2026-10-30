# dataviz/smart/create.py
#
# 20.10.2026: "📂→🎬 תיקייה ← טיוטת פרק" - בלחיצה אחת: ניתוח התיקייה (A-C), פרק חדש ב-data/dataviz_episodes/<שם> עם
# העתק של הקבצים הרלוונטיים (סדרות, אירועים, משקלות, מפה, מסמכים - לא הגולמיים ולא קובצי הבדיקה) ו-config.yaml של
# המיפוי בלבד (כמו "פרק חדש"), וכל הבחירות העריכתיות (תרשים, כותרות, יחידות, סיפור, חבילת יוטיוב, קריינות) כטיוטה בקובץ
# השינויים - כל אחת מאומתת, וכל אחת עם 🤖 סיבה וביטחון ב-data/dataviz_smart/<שם>.json. תיקיית המקור רק נקראת.
# ביטחון נמוך -> שאלה אחת ממוקדת (לא טופס). הצעות לאירועים ולניקוי - רק נשמרות להצגה; שום דבר מהן לא נכנס בלי לחיצה.
import json
import os
import re
import shutil
import tempfile
import time
from typing import Any, Dict, List, Mapping, Optional

import yaml
from utils.shared import data_paths

SMART_ROOT = data_paths.DATAVIZ_SMART
COPY_KINDS = ("series", "events", "weights", "docs")
QUESTION_BELOW = 0.65


def record_path(data_dir: str, name: str) -> str:
    # 23.10.2026: שם עם נתיב ("..\\..\\outside\\victim") כתב קובץ JSON מחוץ לתיקייה (smart/accept) - רק שם של פרק
    if not re.fullmatch(r"[\w\-]{1,60}", str(name or "")):
        from dataviz.web import episodes as de
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    return os.path.join(data_dir, SMART_ROOT, name + ".json")


def thumbnail_path(data_dir: str, name: str) -> str:
    return os.path.join(data_dir, SMART_ROOT, name + "_thumbnail.png")


def load_record(data_dir: str, name: str) -> Optional[Dict[str, Any]]:
    try:
        with open(record_path(data_dir, name), encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):   # EpisodeError (שם לא תקין) הוא ValueError - אין רשומה
        return None
    return value if isinstance(value, dict) else None


def save_record(data_dir: str, name: str, record: Mapping[str, Any]) -> None:
    path = record_path(data_dir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def _name(path: str, name: str) -> str:
    raw = str(name or "").strip() or os.path.basename(os.path.normpath(path))
    return re.sub(r"[^\w\-]", "_", raw).strip("_.")[:40] or "episode"


def _choice(choices: List[Dict[str, Any]], path: str, value: Any, label: str, reason: str, confidence: float, where: str = "override") -> None:
    choices.append({"path": path, "value": value, "label": label, "reason": reason, "confidence": round(float(confidence), 2), "where": where})


def _question(analysis: Mapping[str, Any], choices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """שאלה אחת - על הבחירה עם הביטחון הנמוך ביותר מבין סוג הערך והתרשים, אם הוא מתחת לסף."""
    main = analysis["series"][0]["roles"]
    kind = main.get("kind") or {}
    chart = analysis.get("chart") or {}
    candidates = []
    if kind and kind.get("confidence", 1) < QUESTION_BELOW:
        candidates.append((kind["confidence"], {"about": "kind", "question": "הערכים בקובץ - כמות שמצטברת (כל שורה מוסיפה), או מצב באותו זמן (לא מחברים)?",
                                                "options": [{"value": "amount", "label": "כמות שמצטברת"}, {"value": "level", "label": "מצב (רמה)"}],
                                                "current": kind.get("value"), "reason": kind.get("reason", "")}))
    if chart and chart.get("confidence", 1) < QUESTION_BELOW:
        options = [{"value": chart["value"], "label": chart["value"]}] + [{"value": a["value"], "label": a["value"]} for a in chart.get("alternatives") or []]
        candidates.append((chart["confidence"], {"about": "chart", "question": "איזה תרשים מספר את הסיפור הזה הכי טוב?", "options": options[:3],
                                                 "current": chart["value"], "reason": chart.get("reason", "")}))
    return min(candidates, key=lambda c: c[0])[1] if candidates else None


def events_list(folder: str, file_name: str, headerless: bool = False) -> List[Dict[str, str]]:
    """קובץ אירועים שהמנוע לא קורא ישירות (בלי שורת כותרת, או כותרות כמו "תאריך, אירוע") -> [{date, label}]: עמודת התאריך
    והעמודה הראשונה של טקסט. הקובץ לא משתנה."""
    import pandas as pd

    from dataviz.smart.columns import parse_times
    try:
        df = pd.read_csv(os.path.join(folder, file_name), header=None if headerless else 0, encoding="utf-8-sig")
    except (OSError, ValueError):
        return []
    parsed = {c: parse_times(df[c].astype(str)) for c in df.columns}
    date_col = max(parsed, key=lambda c: parsed[c].notna().mean())
    text_col = next((c for c in df.columns if c != date_col and not pd.api.types.is_numeric_dtype(df[c])), None)
    if text_col is None:
        return []
    dates = parsed[date_col]
    rows = [{"date": d.strftime("%Y-%m-%d"), "label": " ".join(str(t).split())[:120]} for d, t in zip(dates, df[text_col])
            if pd.notna(d) and str(t).strip()]
    unique = {(r["date"], r["label"]): r for r in rows}
    return sorted(unique.values(), key=lambda r: r["date"])[:100]


def build_draft(folder: str, name: str, analysis: Mapping[str, Any]) -> Dict[str, Any]:
    """{set: {נתיב: ערך}, choices: [...], texts, package, question} - מהניתוח, בלי לכתוב כלום."""
    from dataviz.smart.events import topics
    from dataviz.smart.package import build as build_package
    from dataviz.smart.texts import facts, suggest_texts
    series = analysis["series"]
    main = series[0]["roles"]
    plan = analysis["plan"]
    chart = analysis["chart"]
    story = analysis["story"]
    choices: List[Dict[str, Any]] = []
    for f, spec in zip(series, plan["sources"]):
        roles = f["roles"]
        _choice(choices, f"sources:{f['name']}:time", spec["time"], "עמודת הזמן", roles["time"]["reason"], roles["time"]["confidence"], "file")
        if roles.get("entity"):
            _choice(choices, f"sources:{f['name']}:entity", spec["entity"], "עמודת הישות", roles["entity"]["reason"], roles["entity"]["confidence"], "file")
        _choice(choices, f"sources:{f['name']}:value", spec["value"], "עמודת הערך", roles["value"]["reason"], roles["value"]["confidence"], "file")
        if roles.get("kind"):
            _choice(choices, f"sources:{f['name']}:kind", roles["kind"]["value"], "כמות או רמה", roles["kind"]["reason"], roles["kind"]["confidence"], "file")
    for decision in plan.get("decisions") or []:
        _choice(choices, f"plan:{decision['what']}", decision["value"], "איך הקבצים משתלבים", decision["reason"], decision["confidence"], "file")
    values: Dict[str, Any] = {}

    def put(path: str, value: Any, label: str, reason: str, confidence: float) -> None:
        if value in (None, "", [], {}):
            return
        values[path] = value
        _choice(choices, path, value, label, reason, confidence)

    for key, value in (chart.get("map") or {}).items():   # מפה: הקובץ והמאפיין שמתאים לשמות הישויות - לפני התרשים (נבדק שדה-שדה)
        put(f"map.{key}", value, "המפה" if key == "geojson" else "המאפיין במפה", chart["reason"], chart["confidence"])
    put("chart", chart["value"], "סוג התרשים", chart["reason"], chart["confidence"])
    put("ranking.top_n", chart["top_n"], "כמה ישויות על המסך", f"{chart['top_n']} - עד 10, לפי מספר הישויות", 0.7)
    f = facts(analysis, name, folder)
    texts = suggest_texts(f)
    put("title", texts["titles"][0]["he"], "כותרת", "מהעובדות שחושבו (יש עוד אפשרויות)", 0.6)
    put("subtitle", texts["subtitles"][0]["he"], "כותרת משנה", "נושא, ישויות וטווח שנים", 0.7)
    put("intro.question", texts["hooks"][0]["he"], "שאלת הפתיחה", "מהמוביל בהתחלה ובסוף / הנושא", 0.6)
    unit = main.get("unit") or {}
    if plan.get("layout") == "dual":
        put("y_axes.left.label", (series[0]["roles"].get("unit") or {}).get("label"), "תווית ציר שמאלי", "היחידה של הסדרה הראשונה", 0.7)
        put("y_axes.right.label", (series[1]["roles"].get("unit") or {}).get("label"), "תווית ציר ימני", "היחידה של הסדרה השנייה", 0.7)
    elif unit.get("label"):
        put("numbers.prefix", unit.get("prefix"), "תחילית למספרים", unit.get("reason", ""), unit.get("confidence", 0.5))
        put("numbers.suffix", (unit.get("suffix") or "") + (f" {unit['scale']}" if unit.get("scale") else ""), "סיומת למספרים",
            unit.get("reason", ""), unit.get("confidence", 0.5))
    cleaning = analysis.get("cleaning") or {}
    put("entities.aliases", cleaning.get("aliases"), "מיזוג שמות", "; ".join(x["detail"] for x in cleaning.get("fixed") or [])[:300], 0.85)
    put("story.pauses", story.get("pauses"), "עצירות עם הסבר", "הרגעים החזקים (מוצא הסיפור)", 0.6)
    put("story.callouts", story.get("callouts"), "הדגשות", "החלפות במקום הראשון ושיאים", 0.6)
    put("story.speed", story.get("speed"), "קטעי מהירות", "לאט סביב רגע חזק, מהר בקטע השקט", 0.55)
    put("story.script", [{"date": m["date"], "text": m["text"]} for m in sorted(story.get("moments") or [], key=lambda m: m["date"])][:8],
        "תסריט קריינות", "משפט לכל רגע חזק (עובדה מחושבת)", 0.55)
    pack = build_package(f, texts, story, analysis["scan"]["docs"], "israel" in topics(folder))
    put("story.chapters", pack["chapters"], "פרקים ליוטיוב", "עד 5 רגעים חזקים במרווחים", 0.6)
    put("publish.title", pack["title"], "כותרת ביוטיוב", "הכותרת הראשונה", 0.6)
    put("publish.description", pack["description"], "תיאור ביוטיוב", "כותרת המשנה והרגעים", 0.6)
    put("publish.hashtags", pack["hashtags"], "תגיות", "הנושא", 0.6)
    put("outro.credits", pack["credits"], "קרדיטים", "שורות המקור ב-SOURCES.md", 0.75)
    events = [f for f in analysis["scan"]["files"] if f["kind"] == "events"]
    standard = any(f["name"] == "events.csv" and not f.get("headerless") and {"date", "label"} <= {c.lower() for c in f["columns"]} for f in events)
    other = [f for f in events if not (f["name"] == "events.csv" and standard)]
    if other and not standard:   # המנוע קורא רק events.csv עם date,label - קובץ אחר נכנס כרשימה בטיוטה
        put("events", events_list(folder, other[0]["name"], bool(other[0].get("headerless"))), "אירועים",
            f"מ-{other[0]['name']}" + (" (בלי שורת כותרת)" if other[0].get("headerless") else ""), 0.7)
    return {"set": values, "choices": choices, "texts": texts, "package": pack, "question": _question(analysis, choices)}


def _overlay(draft: Dict[str, Any], values: Mapping[str, Any], label: str, reason: str, confidence: float) -> None:
    """ערכים מבחוץ (סדרה, ערכת ערוץ) מעל הטיוטה - עם הסיבה שלהם."""
    for path, value in values.items():
        if value in (None, "", [], {}):
            continue
        draft["set"][path] = value
        draft["choices"] = [c for c in draft["choices"] if c["path"] != path]
        _choice(draft["choices"], path, value, label, reason, confidence)


def create_from_folder(data_dir: str, path: Any, name: Any = "", thumbnail: bool = True, kit: Any = "") -> Dict[str, Any]:
    """פרק חדש מתיקייה + טיוטה אוטומטית. מחזיר את הרשומה (בחירות, שאלה, הצעות). kit = ערכת ערוץ (גם ההעדפות שלה)."""
    from dataviz.smart import learn
    from dataviz.config import ConfigError
    from dataviz.episode import load_episode
    from dataviz.smart.draft import analyze
    from dataviz.web import episodes as de
    source = os.path.abspath(str(path or "").strip().strip('"'))
    if not str(path or "").strip() or not os.path.isdir(source):
        raise de.EpisodeError("התיקייה לא נמצאה.", status=404)
    root = os.path.abspath(de.episodes_root(data_dir))
    try:
        inside = os.path.commonpath([source, root]) == root
    except ValueError:   # כוננים שונים (E: מול C:) - בטוח לא בתוך הפרקים
        inside = False
    if inside:
        raise de.EpisodeError("התיקייה כבר בתוך הפרקים של האפליקציה.")
    name = _name(source, str(name or ""))
    if not de.NAME_RE.match(name) or name.upper() in de.WINDOWS_RESERVED:
        raise de.EpisodeError("שם הפרק: עד 40 תווים - אותיות, ספרות, מקף וקו תחתון.")
    dest = os.path.join(root, name)
    if os.path.exists(dest):
        raise de.EpisodeError(f"כבר קיים פרק בשם '{name}' - בחר שם אחר (לא דורסים פרקים קיימים).", status=409)
    series_match = learn.find_series(data_dir, source)   # לפני שהפרק החדש קיים - שלא ימצא את עצמו
    analysis = analyze(source)
    if not analysis["series"]:
        raise de.EpisodeError("לא נמצאה בתיקייה סדרת נתונים (טבלה עם עמודת זמן ועמודת ערך).")
    files = [f for f in analysis["scan"]["files"] if f["kind"] in COPY_KINDS]
    chosen_map = str((analysis["chart"].get("map") or {}).get("geojson") or "")   # ב23: גם מפה ששמורה כ-.json (התרשים נבחר לפיה)
    files += [{"name": n, "kind": "map"} for n in os.listdir(source) if n.lower().endswith(".geojson") or (n == chosen_map and n not in {f["name"] for f in files})]
    total = sum(os.path.getsize(os.path.join(source, f["name"])) for f in files)
    if total > de.IMPORT_MAX_BYTES:
        raise de.EpisodeError(f"הקבצים גדולים מדי ({total // (1024 * 1024)}MB; עד {de.IMPORT_MAX_BYTES // (1024 * 1024)}MB).")
    config: Dict[str, Any] = {"title": name, "sources": analysis["plan"]["sources"]}
    has_events = any(f["kind"] == "events" and f["name"] == "events.csv" and f.get("rows") and not f.get("headerless")
                     and {"date", "label"} <= {str(c).lower() for c in f.get("columns") or []} for f in files)
    if has_events:
        config["events"] = "events.csv"
    os.makedirs(root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".smart_", dir=root)
    try:
        copy = os.path.join(staging, name)
        os.makedirs(copy)
        for f in files:
            shutil.copy2(os.path.join(source, f["name"]), os.path.join(copy, f["name"]))
        with open(os.path.join(copy, "config.yaml"), "w", encoding="utf-8") as fh:
            fh.write("# נוצר מתיקייה (עורך הגרפים החכם) - המיפוי בלבד; הבחירות האוטומטיות בקובץ השינויים\n")
            yaml.safe_dump(config, fh, allow_unicode=True, sort_keys=False)
        try:
            load_episode(copy)
        except ConfigError as e:
            raise de.EpisodeError("ההגדרות שזוהו לא תקינות: " + "; ".join(e.errors[:3])) from e
        except (KeyError, ValueError, OSError) as e:   # 23.10.2026: קובץ שהסריקה קראה והמנוע לא - הודעה, לא 500
            raise de.EpisodeError("הקבצים שזוהו לא נטענו: " + str(e)[:200]) from e
        try:
            os.rename(copy, dest)
        except FileExistsError as e:
            raise de.EpisodeError(f"כבר קיים פרק בשם '{name}'.", status=409) from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)   # safe: התיקייה הזמנית שיצרנו כאן
    draft = build_draft(dest, name, analysis)
    if series_match:   # פריט 17: דומה לפרק קיים - המראה והמבנה שלו
        _overlay(draft, learn.series_values(data_dir, series_match["episode"]), "כמו בסדרה",
                 f"דומה לפרק '{series_match['episode']}' ({series_match['why']})", 0.7)
    if kit:
        from dataviz.web.kits import kit_changes, load_kits
        chosen_kit = load_kits(data_dir).get(str(kit))
        if chosen_kit is None:
            raise de.EpisodeError("ערכת הערוץ לא נמצאה.", status=404)
        _overlay(draft, kit_changes(chosen_kit), "ערכת הערוץ", f"ערכת הערוץ '{kit}'", 0.9)
    learn.apply_prefs(data_dir, str(kit or "default"), draft["set"], draft["choices"])   # פריט 16: מה שהמשתמש העדיף בעבר
    applied, skipped = {}, []
    for key, value in draft["set"].items():   # כל שדה לבד - שדה שלא עובר אימות לא מפיל את השאר
        try:
            de.update_override_fields(data_dir, name, {key: value}, [])
            applied[key] = value
        except de.EpisodeError as e:
            skipped.append({"path": key, "error": str(e)[:200]})
    choices = [c for c in draft["choices"] if c["where"] == "file" or c["path"] in applied]
    record: Dict[str, Any] = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "source_folder": source, "episode": name,
                              "choices": choices, "skipped": skipped, "question": draft["question"], "texts": draft["texts"],
                              "events": analysis.get("events"), "cleaning": analysis.get("cleaning"),
                              "story_type": (analysis.get("story") or {}).get("type"), "thumbnail": "",
                              "kit": str(kit or ""), "series": series_match}
    if thumbnail:
        from dataviz.smart.thumb import make, strongest
        try:
            cache = os.path.join(data_dir, SMART_ROOT, ".cache")
            make(dest, de.load_overrides_for_path(dest), strongest(analysis["story"]["moments"]), applied.get("title", name),
                 thumbnail_path(data_dir, name), cache)
            shutil.rmtree(cache, ignore_errors=True)   # safe: מטמון הפריימים שיצרנו כאן
            record["thumbnail"] = os.path.basename(thumbnail_path(data_dir, name))
        except Exception as e:   # תמונה ממוזערת היא תוספת - בלעדיה הטיוטה עדיין שלמה
            record["thumbnail_error"] = str(e)[:200]
    save_record(data_dir, name, record)
    return record


def auto_marks(data_dir: str, name: str) -> Dict[str, Dict[str, Any]]:
    """נתיב -> {reason, confidence, value} לבחירות האוטומטיות שעדיין בתוקף (לסימון 🤖 בהגדרות הסופיות)."""
    record = load_record(data_dir, name) or {}
    return {c["path"]: {"reason": c["reason"], "confidence": c["confidence"], "value": c["value"], "label": c["label"]}
            for c in record.get("choices") or [] if c.get("where") == "override" and not c.get("undone")}


def undo(data_dir: str, name: str, path: str) -> Dict[str, Any]:
    """ביטול בחירה אוטומטית אחת: השדה חוזר לברירת המחדל / לקובץ (unset), והבחירה מסומנת כמבוטלת."""
    from dataviz.web import episodes as de
    record = load_record(data_dir, name)
    choice = next((c for c in (record or {}).get("choices") or [] if c["path"] == path and c.get("where") == "override"), None)
    if record is None or choice is None:
        raise de.EpisodeError("הבחירה לא נמצאה.", status=404)
    de.update_override_fields(data_dir, name, {}, [path])
    choice["undone"] = True
    save_record(data_dir, name, record)
    return {"ok": True, "path": path}


def accept(data_dir: str, name: str, path: str = "") -> Dict[str, Any]:
    """"✓ מאשר" במסך הסקירה: מסמן ברשומה שהבחירה נבדקה - הפרק עצמו לא משתנה. path ריק = כל הבחירות שעוד פתוחות."""
    from dataviz.web import episodes as de
    record = load_record(data_dir, name)
    choices = [c for c in (record or {}).get("choices") or [] if c.get("where") == "override" and not c.get("undone")
               and (not path or c["path"] == path)]
    if record is None or (path and not choices):
        raise de.EpisodeError("הבחירה לא נמצאה.", status=404)
    for choice in choices:
        choice["accepted"] = True
    save_record(data_dir, name, record)
    return {"ok": True, "accepted": [c["path"] for c in choices]}


def answer(data_dir: str, name: str, value: Any) -> Dict[str, Any]:
    """התשובה לשאלה האחת: תרשים -> chart בקובץ השינויים; כמות/רמה -> kind בכל המקורות (קובץ השינויים)."""
    from dataviz.config import ConfigError, load_config
    from dataviz.web import episodes as de
    record = load_record(data_dir, name)
    question = (record or {}).get("question")
    if record is None or not question:
        raise de.EpisodeError("אין שאלה פתוחה.", status=404)
    if str(value) not in [str(o["value"]) for o in question["options"]]:
        raise de.EpisodeError("תשובה לא מוכרת.")
    if question["about"] == "chart":
        de.update_override_fields(data_dir, name, {"chart": str(value)}, [])
    else:
        folder = de.episode_folder(data_dir, name) or ""
        overrides = de.load_overrides_for_path(folder)
        try:
            sources = [dict(s) for s in load_config(os.path.join(folder, "config.yaml"), overrides)["sources"]]
        except ConfigError as e:
            raise de.EpisodeError("; ".join(e.errors[:3])) from e
        for spec in sources:
            if value == "level":
                spec["kind"] = "level"
            else:
                spec.pop("kind", None)
                spec.pop("fill", None)
        de._write_overrides(data_dir, name, folder, dict(overrides, sources=[{k: v for k, v in s.items() if k != "base_dir"} for s in sources]))
        _redo_texts(data_dir, name, record, folder, str(value))
    question["answered"] = str(value)
    save_record(data_dir, name, record)
    return {"ok": True, "about": question["about"], "value": str(value)}


# ב21: הטקסטים שמחושבים מהנתונים (שיא, מוביל, רגעים) - תלויים בכמות / רמה
TEXT_PATHS = ("title", "subtitle", "intro.question", "story.pauses", "story.callouts", "story.speed", "story.script", "story.chapters",
              "publish.title", "publish.description", "publish.hashtags")


def _redo_texts(data_dir: str, name: str, record: Dict[str, Any], folder: str, kind: str) -> List[str]:
    """ב21: אחרי תשובה לשאלת כמות / רמה - הסיפור והטקסטים מחושבים מחדש (קודם נשאר "השיא: 459" כשהמקסימום ברמה הוא 134).
    רק בחירות אוטומטיות שעוד בתוקף ושהמשתמש לא שינה; בחירה שכבר אין לה ערך - מבוטלת. מחזיר מה השתנה."""
    from dataviz import schema
    from dataviz.smart.draft import analyze
    from dataviz.smart.story import find_story
    from dataviz.web import episodes as de
    analysis = analyze(folder)
    if not analysis["series"] or not analysis["plan"]:
        return []
    for f in analysis["series"]:
        f["roles"]["kind"] = {"value": kind, "confidence": 0.95, "reason": "התשובה שלך"}
    for spec in analysis["plan"]["sources"]:
        if kind == "level":
            spec["kind"] = "level"
        else:
            spec.pop("kind", None)
            spec.pop("fill", None)
    analysis["story"] = find_story(folder, analysis)
    draft = build_draft(folder, name, analysis)
    overrides = de.load_overrides_for_path(folder)
    changed = []
    for choice in record.get("choices") or []:
        path = choice["path"]
        if path not in TEXT_PATHS or choice.get("where") != "override" or choice.get("undone"):
            continue
        found, current = schema.get_path(overrides, path)
        if not found or current != choice["value"]:
            continue   # המשתמש שינה את זה בעצמו - נשאר
        new = draft["set"].get(path)
        if new == current:
            continue
        if new in (None, "", [], {}):
            de.update_override_fields(data_dir, name, {}, [path])
            choice["undone"] = True
        else:
            de.update_override_fields(data_dir, name, {path: new}, [])
            choice["value"] = new
            choice["reason"] = next((c["reason"] for c in draft["choices"] if c["path"] == path), choice["reason"])
        changed.append(path)
    record["texts"] = draft["texts"]
    return changed
