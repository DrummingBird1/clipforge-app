# dataviz/web/data.py (עד 19.10.2026: utils/dataviz_data.py)
#
# גל 40: הנתונים של פרק בעורך הגרפים - מקורות הנתונים (עמודות, מיפוי ו-20 השורות הראשונות),
# בדיקת נתונים לפני ריצה (ימים חסרים, ערכים שליליים, ישויות דלות, שורות שנזרקו), טבלת המצטבר,
# גרף הקצב (פריימים ליום - כלל ה-STEP, האטות סביב אירועים ושיאים), פיזור סכום של חודש/שנה על
# הימים, המרת Excel/JSON ל-CSV לפרק חדש, ועדכון נתונים לפרק קיים עם השוואת סכומים לפני ואחרי.
# קובץ נתונים חדש לעולם לא דורס קובץ קיים: הוא נכתב כקובץ חדש תחת data/dataviz_overrides/<פרק>/,
# וה-override של הפרק מפנה אליו (הקובץ המקורי בתיקיית הפרק לא משתנה).

import base64
import io
import json
import os
import tempfile
import time
from typing import Any, Dict, List, Mapping

import numpy as np
import pandas as pd

from dataviz.web import episodes as de
from dataviz.web import preview as dp

PREVIEW_ROWS = 20
MAX_POINTS = 400
TABLE_MAX_BYTES = de.CSV_MAX_BYTES   # 18.10.2026: 25MB (היה 5MB)


def _episode(folder: str, overrides: Mapping[str, Any]) -> Any:
    with dp._lock:
        _key, episode, _plan = dp._episode(folder, overrides, dp.SCALES[0], "full")
    return episode


def _plain(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return value if isinstance(value, (int, float, str, bool)) else str(value)


def _base_source_count(folder: str) -> int:
    """כמה מקורות יש ב-config.yaml עצמו (בלי השינויים) - רק מקור שאחריהם נוסף מהדפדפן ואפשר להסיר אותו."""
    from dataviz.config import load_config
    from dataviz.sources import resolved_sources
    return len(resolved_sources(load_config(os.path.join(folder, "config.yaml"), {})))


def sources_overview(folder: str, overrides: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """כל מקור נתונים: סוג, מיפוי העמודות (זמן / ערך / ישות), העמודות בקובץ ו-20 השורות הראשונות."""
    from dataviz.config import load_config
    from dataviz.sources import read_raw, read_table, resolved_sources, source_type
    config = load_config(os.path.join(folder, "config.yaml"), dict(overrides))
    base_count = _base_source_count(folder) if overrides.get("sources") else None
    base_weights = [(s.get("spread") or {}).get("weights") for s in load_config(os.path.join(folder, "config.yaml"), {})["sources"]] if overrides.get("sources") else []
    result = []
    for index, spec in enumerate(resolved_sources(config)):
        raw = read_raw(spec, config["base_dir"])
        valid = read_table(spec, config["base_dir"])
        time_spec = spec.get("time") or {}
        if isinstance(time_spec, str):
            time_spec = {"column": time_spec}
        value = spec.get("value", "count")
        entity = spec.get("entity") or {"from_time": "year"}
        result.append({
            "index": index, "path": os.path.basename(str(spec["path"])) if not spec.get("url") else spec["url"], "type": source_type(spec),
            "url": str(spec.get("url") or ""), "missing": str(spec.get("missing") or ""),   # גל 52
            "time": {"column": time_spec.get("column", ""), "period": time_spec.get("period", "day")},
            "value": "count" if value == "count" else (value.get("column") if isinstance(value, Mapping) else str(value)),
            "entity": entity if isinstance(entity, str) else (entity.get("column") or f"from_time:{entity.get('from_time')}"),
            "legend": spec.get("legend", ""), "texture": spec.get("texture") or "solid", "spread": bool(spec.get("spread")),
            "kind": str(spec.get("kind") or "amount"),   # 19.10.2026
            "axis": str(spec.get("axis") or "left"),     # 20.10.2026
            "fill": str(spec.get("fill") or "none"),     # 20.10.2026
            "columns": [str(c) for c in raw.columns], "rows": [[_plain(v) for v in row] for row in raw.head(PREVIEW_ROWS).itertuples(index=False)],
            "total_rows": int(len(raw)), "valid_rows": int(len(valid)), "dropped_rows": int(len(raw) - len(valid)),
            "removable": base_count is not None and index >= base_count,   # 18.10.2026: נוסף מהדפדפן
            "weights": os.path.basename(_weights_path(spec)),   # 18.10.2026: קובץ המשקלות של המקור (אם יש)
            "weights_removable": bool(overrides.get("sources")) and bool(_weights_path(spec)) and _weights_path(spec) != _weights_path(
                {"spread": {"weights": base_weights[index] if index < len(base_weights) else None}}),
        })
    return result


GRID_MAX_ROWS = 5000   # 20.10.2026: עריכה בטבלה - מעל זה הטבלה לקריאה בלבד (עדכון נתונים מקובץ במקום)


def source_table(folder: str, overrides: Mapping[str, Any], source_index: int) -> Dict[str, Any]:
    """20.10.2026: כל השורות של מקור (כמו שהן בקובץ, כטקסט) - לעריכה בטבלה בדפדפן. השמירה עוברת דרך update_data
    (השוואה ואז קובץ חדש תחת data/dataviz_overrides/<פרק>/) - הקובץ המקורי לא נכתב."""
    from dataviz.config import load_config
    from dataviz.sources import read_raw, resolved_sources
    config = load_config(os.path.join(folder, "config.yaml"), dict(overrides))
    specs = resolved_sources(config)
    if not isinstance(source_index, int) or not 0 <= source_index < len(specs):
        raise de.EpisodeError("אין מקור כזה.", status=404)
    raw = read_raw(specs[source_index], config["base_dir"])
    cells = raw.head(GRID_MAX_ROWS).astype(object).where(raw.head(GRID_MAX_ROWS).notna(), "")
    rows = [["" if v == "" else (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)) for v in row] for row in cells.itertuples(index=False)]
    return {"index": source_index, "path": os.path.basename(str(specs[source_index].get("path") or "")), "columns": [str(c) for c in raw.columns],
            "rows": rows, "total": int(len(raw)), "editable": len(raw) <= GRID_MAX_ROWS}


def data_check(folder: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """מה כדאי לבדוק לפני ריצה: ימים בלי נתונים בכלל (והרצף הארוך ביותר), ערכים שליליים, ישויות דלות
    ושורות שנזרקו (תאריך לא תקין). כל ממצא עם רמה: warn (כדאי לתקן) או info."""
    episode = _episode(folder, overrides)
    daily = episode.daily
    dates = episode.dates
    totals = episode.cum[-1] if len(episode.cum) else np.zeros(len(episode.entities))
    grand = float(totals.sum()) or 1.0
    day_total = daily.sum(axis=1)
    empty = day_total == 0
    longest = run = 0
    longest_end = -1
    for i, is_empty in enumerate(empty):
        run = run + 1 if is_empty else 0
        if run > longest:
            longest, longest_end = run, i
    findings: List[Dict[str, Any]] = []
    if empty.any():
        start = dates[longest_end - longest + 1].strftime("%Y-%m-%d") if longest else ""
        findings.append({"level": "warn" if longest >= 30 else "info", "kind": "empty_days",
                         "text": f"{int(empty.sum())} ימים בלי נתונים בכלל; הרצף הארוך ביותר: {longest} ימים מ-{start}."})
    negative = int((daily < 0).sum())
    if negative:
        findings.append({"level": "warn", "kind": "negative", "text": f"{negative} ערכים שליליים (ירידה במצטבר)."})
    sparse = [str(e) for i, e in enumerate(episode.entities) if totals[i] < grand * 0.005 or int((daily[:, i] != 0).sum()) < 3]
    if sparse:
        findings.append({"level": "info", "kind": "sparse", "text": f"{len(sparse)} ישויות דלות (פחות מ-0.5% או פחות מ-3 ימים): " + ", ".join(sparse[:8])})
    dropped = sum(s["dropped_rows"] for s in sources_overview(folder, overrides))
    if dropped:
        findings.append({"level": "warn", "kind": "dropped", "text": f"{dropped} שורות נזרקו (תאריך לא תקין)."})
    for note in episode.shared:   # ק4: אותה ישות בכמה מקורות שלא מתחברים לסדרה אחת - ישות לכל מקור
        why = "באותם תאריכים" if note["reason"] == "overlap" else "בסוג או בציר אחר"
        findings.append({"level": "warn", "kind": "shared_entity",
                         "text": f"\"{note['entity']}\" מופיעה במקורות {', '.join(note['sources'])} {why} - מוצגת כ-{len(note['names'])} ישויות: "
                                 + ", ".join(note["names"])})
    findings.extend(_map_findings(episode))
    return {"days": int(len(dates)), "start": dates[0].strftime("%Y-%m-%d"), "end": dates[-1].strftime("%Y-%m-%d"),
            "entities": len(episode.entities), "total": float(grand), "findings": findings, "ok": not any(f["level"] == "warn" for f in findings)}


def _map_findings(episode: Any) -> List[Dict[str, Any]]:
    """גל 42: כשיש קובץ מפה - ישויות בלי אזור במפה (לא ייצבעו), או קובץ שאי אפשר לקרוא."""
    geo_cfg = episode.config.get("map") or {}
    if not geo_cfg.get("geojson"):
        return []
    from dataviz.geo import load_geojson, match_report
    try:
        geo = load_geojson(os.path.join(episode.config["base_dir"], str(geo_cfg["geojson"])), str(geo_cfg.get("key") or "name"))
    except (OSError, ValueError) as e:
        return [{"level": "warn", "kind": "map", "text": f"קובץ המפה לא נקרא: {str(e)[:160]}"}]
    report = match_report(geo, episode.entities)
    if not report["missing"]:
        return [{"level": "info", "kind": "map", "text": f"כל {len(report['found'])} הישויות נמצאו במפה."}]
    level = "warn" if len(report["missing"]) > len(report["found"]) else "info"
    return [{"level": level, "kind": "map", "text": f"{len(report['missing'])} ישויות בלי אזור במפה (רק בדירוג): " + ", ".join(report["missing"][:8])}]


def cumulative_table(folder: str, overrides: Mapping[str, Any], rows: int = 24, top: int = 8) -> Dict[str, Any]:
    """המצטבר לאורך הזמן (שורות מדגם + השורה האחרונה) של הישויות המובילות - לבדיקת היגיון."""
    episode = _episode(folder, overrides)
    cum = episode.cum
    order = np.argsort(-cum[-1])[:top]
    picks = sorted({int(i) for i in np.linspace(0, len(cum) - 1, min(rows, len(cum)))})
    return {"columns": [str(episode.entities[i]) for i in order],
            "rows": [[episode.dates[d].strftime("%Y-%m-%d"), *[float(cum[d, i]) for i in order]] for d in picks]}


def pacing(folder: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """גרף הקצב: פריימים לכל יום (כלל ה-STEP: אף עמודה לא מתקדמת ביותר מ-step מהציר בפריים), הימים
    שבהם הכלל האט את הסרטון, חלונות ההאטה סביב אירועים, והשיאים היומיים."""
    from dataviz.plan import pacing_weights
    episode = _episode(folder, overrides)
    cfg = episode.config
    timing, ranking = cfg["timing"], cfg["ranking"]
    slow = timing["event_slowdown"]
    weights = pacing_weights(episode.daily, episode.cum, [di for _, _, di in episode.events], step=timing["step"],
                             base=timing["base_frames_per_day"], axis_min=ranking["axis_min"], before=slow["before_days"],
                             after=slow["after_days"], extra=slow["extra"], window=timing["smooth_window"],
                             strict=bool(timing.get("strict_step", True)))
    n = len(weights)
    stride = max(1, int(np.ceil(n / MAX_POINTS)))
    points = [{"date": episode.dates[i].strftime("%Y-%m-%d"), "frames": round(float(weights[i:i + stride].mean()), 3)} for i in range(0, n, stride)]
    base = float(timing["base_frames_per_day"])
    day_total = episode.daily.sum(axis=1)
    peaks = [{"date": episode.dates[i].strftime("%Y-%m-%d"), "total": float(day_total[i])} for i in np.argsort(-day_total)[:5] if day_total[i] > 0]
    fps = int(cfg["video"]["fps"])
    return {
        "points": points, "base": base, "step": float(timing["step"]), "fps": fps,
        "total_frames": int(round(float(weights.sum()))), "seconds": round(float(weights.sum()) / fps, 1),
        "step_limited_days": int((weights > base * 1.01).sum()),
        "events": [{"date": d, "label": label} for d, label, _di in episode.events],
        "slowdowns": [{"from": episode.dates[max(di - slow["before_days"], 0)].strftime("%Y-%m-%d"),
                       "to": episode.dates[min(di + slow["after_days"], n - 1)].strftime("%Y-%m-%d")} for _d, _l, di in episode.events],
        "peaks": peaks,
    }


def spread_preview(folder: str, overrides: Mapping[str, Any], source_index: int) -> Dict[str, Any]:
    """לסכום של חודש או שנה: איך הוא מתפזר על הימים (התקופה הראשונה של המקור) - בשביל לראות שהפיזור הגיוני."""
    from dataviz.config import load_config
    from dataviz.sources import read_raw, read_table, resolved_sources
    from dataviz.sources.spread import spread_to_days
    config = load_config(os.path.join(folder, "config.yaml"), dict(overrides))
    specs = resolved_sources(config)
    if not 0 <= source_index < len(specs):
        raise de.EpisodeError("אין מקור כזה.")
    spec = specs[source_index]
    table = read_table(spec, config["base_dir"])
    period = table["period"].iloc[0] if len(table) else "day"
    if period == "day":
        return {"period": "day", "points": [], "note": "המקור יומי - אין פיזור."}
    first = table.iloc[0]
    weights = None
    weight_spec = (spec.get("spread") or {}).get("weights")
    if weight_spec:
        weights = read_raw(weight_spec, config["base_dir"])
    series = spread_to_days(pd.Timestamp(first["time"]), period, first["value"], spec.get("spread") or {}, weights)
    return {"period": period, "entity": str(first["entity"]), "total": float(first["value"]),
            "points": [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for d, v in series.items()]}


def table_to_csv(filename: str, data_base64: str) -> Dict[str, Any]:
    """Excel או JSON (או CSV) -> טקסט CSV ועמודות, בשביל פרק חדש מקובץ שנגרר למסך."""
    try:
        raw = base64.b64decode(data_base64 or "", validate=True)
    except ValueError:
        raise de.EpisodeError("הקובץ לא התקבל כמו שצריך.") from None
    if not raw or len(raw) > TABLE_MAX_BYTES:
        raise de.EpisodeError(f"קובץ ריק או גדול מ-{TABLE_MAX_BYTES // (1024 * 1024)}MB.")
    ext = os.path.splitext(str(filename).lower())[1]
    try:
        if ext in (".xlsx", ".xlsm", ".xls"):
            df = pd.read_excel(io.BytesIO(raw))
        elif ext == ".json":
            data = json.loads(raw.decode("utf-8-sig"))
            if isinstance(data, dict):   # {"records": [...]} או מילון של רשימות - הרשימה הראשונה של רשומות
                data = next((v for v in data.values() if isinstance(v, list)), [data])
            df = pd.json_normalize(data)
        elif ext in (".csv", ".tsv", ".txt"):
            df = pd.read_csv(io.BytesIO(raw), sep="\t" if ext == ".tsv" else ",", encoding="utf-8-sig")
        else:
            raise de.EpisodeError("סוג קובץ לא נתמך - CSV, Excel או JSON.")
    except de.EpisodeError:
        raise
    except Exception as e:
        raise de.EpisodeError(f"לא הצלחתי לקרוא את הקובץ: {str(e)[:200]}") from None
    if df.empty or len(df.columns) < 2:
        raise de.EpisodeError("הטבלה ריקה או עם עמודה אחת בלבד.")
    csv_text = df.to_csv(index=False)
    if len(csv_text.encode("utf-8")) > de.CSV_MAX_BYTES:
        raise de.EpisodeError("הטבלה גדולה מדי אחרי ההמרה.")
    return {"csv_text": csv_text, "columns": [str(c) for c in df.columns], "rows": int(len(df))}


def _totals(folder: str, overrides: Mapping[str, Any]) -> Dict[str, float]:
    from dataviz.episode import load_episode
    episode = load_episode(folder, dict(overrides))
    last = episode.cum[-1] if len(episode.cum) else []
    return {str(e): float(last[i]) for i, e in enumerate(episode.entities)}


def _with_source(config_sources: List[Any], index: int, path: str) -> List[Any]:
    """המקור מפנה לקובץ ה-CSV החדש. גל 43: מקור Excel / JSON הופך למקור CSV עם אותו מיפוי עמודות
    (גיליון / מסלול רשומות כבר לא רלוונטיים - הנתונים החדשים הגיעו כטבלה)."""
    sources = json.loads(json.dumps(config_sources, default=str))
    spec = sources[index]
    if spec.get("type") in ("excel", "json") or os.path.splitext(str(spec.get("path", "")))[1].lower() in (".xlsx", ".xls", ".xlsm", ".json"):
        for key in ("sheet", "records", "sep", "encoding"):
            spec.pop(key, None)
        spec["type"] = "csv"
    spec["path"] = path
    return sources


def compare_data(before: Dict[str, float], after: Dict[str, float]) -> Dict[str, Any]:
    names = sorted(set(before) | set(after), key=lambda n: -max(before.get(n, 0.0), after.get(n, 0.0)))
    rows = [{"entity": n, "before": before.get(n), "after": after.get(n),
             "diff": (after.get(n) or 0.0) - (before.get(n) or 0.0)} for n in names]
    return {"total_before": sum(before.values()), "total_after": sum(after.values()), "rows": rows[:60],
            "new": [n for n in names if n not in before], "gone": [n for n in names if n not in after]}


def _check_file(target_dir: str, stem: str, text: str) -> str:
    """19.10.2026: קובץ הבדיקה הזמני בשם ייחודי (שתי בקשות במקביל לא כותבות לאותו קובץ)."""
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=stem + "_", suffix=".csv.check", dir=target_dir)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return tmp


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _reserve_csv(target_dir: str, stem: str) -> str:
    """19.10.2026: שם חדש לקובץ שנשמר - <שם>_<זמן>.csv, ועם _2, _3... כשכבר יש כזה. השם נתפס ביצירה בלעדית (O_EXCL), כך
    ששתי שמירות באותה שנייה לא מקבלות אותו שם ולא דורסות זו את זו (קודם: שם לפי השנייה + os.replace)."""
    base = f"{stem}_{_stamp()}"
    for i in range(1, 1000):
        path = os.path.join(target_dir, base + (f"_{i}" if i > 1 else "") + ".csv")
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except FileExistsError:
            continue
    raise de.EpisodeError("לא נמצא שם פנוי לקובץ - נסה שוב.")


def update_data(data_dir: str, name: str, source_index: int, csv_text: str, confirm: bool) -> Dict[str, Any]:
    """עדכון נתונים לפרק קיים: הקובץ החדש נבדק (אותו מיפוי עמודות), ומוחזרת השוואת סכומים לפני/אחרי.
    רק עם confirm=True הוא נשמר - כקובץ חדש, וה-override מפנה אליו (הקובץ המקורי לא משתנה)."""
    from dataviz.config import ConfigError, load_config
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    if not isinstance(csv_text, str) or not csv_text.strip() or len(csv_text.encode("utf-8")) > de.CSV_MAX_BYTES:
        raise de.EpisodeError("נתונים ריקים או גדולים מדי.")
    overrides = de.load_overrides_for_path(folder)
    config = load_config(os.path.join(folder, "config.yaml"), overrides)
    if not 0 <= source_index < len(config["sources"]):
        raise de.EpisodeError("אין מקור כזה.")
    if not config["sources"][source_index].get("path"):   # 23.10.2026: מקור מכתובת - קודם KeyError 'path' (500)
        raise de.EpisodeError("מקור מכתובת מתעדכן ב\"רענן מהכתובת\", לא בהעלאת קובץ.")
    target_dir = os.path.join(data_dir, de.OVERRIDES_DIRNAME, name)
    stem = os.path.splitext(os.path.basename(str(config["sources"][source_index]["path"])))[0]
    tmp = _check_file(target_dir, stem, csv_text)
    try:
        after_overrides = dict(overrides, sources=_with_source(config["sources"], source_index, os.path.abspath(tmp)))
        try:
            before, after = _totals(folder, overrides), _totals(folder, after_overrides)
        except (ConfigError, KeyError, ValueError) as e:
            raise de.EpisodeError("הנתונים החדשים לא מתאימים למיפוי של המקור: " + str(e)[:200]) from None
        comparison = compare_data(before, after)
        if not confirm:
            return {"saved": False, **comparison}
        path = _reserve_csv(target_dir, stem)
        os.replace(tmp, path)   # על השם ששמרנו לעצמנו - לא דורס כלום
        saved = dict(overrides, sources=_with_source(config["sources"], source_index, os.path.abspath(path)))
        de._write_overrides(data_dir, name, folder, saved)
        return {"saved": True, "file": os.path.basename(path), **comparison}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)   # safe: קובץ הבדיקה הזמני שיצרנו כאן


def add_source(data_dir: str, name: str, filename: str, csv_text: str, mapping: Mapping[str, Any], confirm: bool) -> Dict[str, Any]:
    """18.10.2026: קובץ נתונים נוסף לפרק קיים - מקור חדש עם מיפוי משלו, לצד המקורות שכבר יש (כמו עדכון נתונים:
    בלי confirm - רק השוואת סכומים; עם confirm - קובץ חדש תחת data/dataviz_overrides/<פרק>/ וה-override מוסיף אותו)."""
    from dataviz.config import ConfigError, load_config
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    csv_text = de.clean_table_text(csv_text)
    clean = de.clean_mapping(mapping)
    de.check_mapping_columns(clean, de.csv_columns(csv_text))
    overrides = de.load_overrides_for_path(folder)
    config = load_config(os.path.join(folder, "config.yaml"), overrides)
    if len(config["sources"]) > de.MAX_EXTRA_SOURCES:
        raise de.EpisodeError(f"לפרק כבר יש {len(config['sources'])} מקורות - זה המקסימום.")
    target_dir = os.path.join(data_dir, de.OVERRIDES_DIRNAME, name)
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in os.path.splitext(os.path.basename(str(filename or "")))[0])[:40] or "source"
    tmp = _check_file(target_dir, stem, csv_text)
    try:
        current = json.loads(json.dumps(config["sources"], default=str))
        after_overrides = dict(overrides, sources=current + [de.source_spec(os.path.abspath(tmp), clean)])
        try:
            before, after = _totals(folder, overrides), _totals(folder, after_overrides)
        except (ConfigError, KeyError, ValueError) as e:
            raise de.EpisodeError("הקובץ לא נטען עם המיפוי שנבחר: " + str(e)[:200]) from None
        comparison = compare_data(before, after)
        if not confirm:
            return {"saved": False, **comparison}
        path = _reserve_csv(target_dir, stem)
        os.replace(tmp, path)   # על השם ששמרנו לעצמנו - לא דורס כלום
        de._write_overrides(data_dir, name, folder, dict(overrides, sources=current + [de.source_spec(os.path.abspath(path), clean)]))
        return {"saved": True, "file": os.path.basename(path), "sources": len(current) + 1, **comparison}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)   # safe: קובץ הבדיקה הזמני שיצרנו כאן


def update_source_mapping(data_dir: str, name: str, source_index: int, mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """19.10.2026: מיפוי חדש למקור קיים (עמודת תאריך, תקופה, ערך, קיבוץ, מקרא, כמות/רמה) מהדפדפן. נכתב רק ל-override של
    הפרק - config.yaml וקובץ הנתונים לא משתנים, ושאר ההגדרות של המקור (סינון, פיזור, משקלות) נשארות. הפרק נטען עם המיפוי
    החדש לפני השמירה; לא נטען = שגיאה ושום דבר לא נכתב."""
    from dataviz.config import ConfigError, load_config
    from dataviz.sources import read_raw
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    clean = de.clean_mapping(mapping)
    overrides = de.load_overrides_for_path(folder)
    config = load_config(os.path.join(folder, "config.yaml"), overrides)
    if not isinstance(source_index, int) or not 0 <= source_index < len(config["sources"]):
        raise de.EpisodeError("אין מקור כזה.")
    sources = json.loads(json.dumps(config["sources"], default=str))
    old = sources[source_index]
    from dataviz.sources import resolved_sources
    de.check_mapping_columns(clean, [str(c) for c in read_raw(resolved_sources(config)[source_index], config["base_dir"]).columns])
    fresh = de.source_spec(str(old.get("path") or ""), clean)
    time_spec = dict(old["time"]) if isinstance(old.get("time"), Mapping) else {}
    time_spec.update(fresh["time"])
    if "period" not in fresh["time"]:
        time_spec.pop("period", None)
    spec = dict(old, time=time_spec, entity=fresh["entity"])
    spec["value"] = dict(old["value"], column=clean["value_column"]) if isinstance(old.get("value"), Mapping) and clean["value_column"] else fresh["value"]
    for key in ("legend", "kind", "axis", "fill"):
        if key in fresh:
            spec[key] = fresh[key]
        else:
            spec.pop(key, None)
    sources[source_index] = spec
    saved = dict(overrides, sources=sources)
    try:
        _totals(folder, saved)
    except (ConfigError, KeyError, ValueError) as e:
        raise de.EpisodeError("הפרק לא נטען עם המיפוי החדש: " + str(e)[:200]) from None
    de._write_overrides(data_dir, name, folder, saved)
    return {"ok": True, "source": spec}


def remove_source(data_dir: str, name: str, source_index: int) -> Dict[str, Any]:
    """18.10.2026: מסיר מקור שנוסף מהדפדפן (קובץ נוסף) - רק מקור שאחרי המקורות של config.yaml; המקורות המקוריים
    לא מוסרים. המקור יוצא רק מה-override; הקובץ שלו (תחת data/dataviz_overrides/<פרק>/) נשאר בדיסק בלי שינוי -
    החלטת המשתמש: אף קובץ לא נמחק ולא עובר לסל המיחזור."""
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    overrides = de.load_overrides_for_path(folder)
    sources = list(overrides.get("sources") or [])
    if not sources or not _base_source_count(folder) <= source_index < len(sources):
        raise de.EpisodeError("אפשר להסיר רק מקור שנוסף מהדפדפן - המקורות המקוריים של הפרק לא מוסרים.")
    removed = sources.pop(source_index)
    de._write_overrides(data_dir, name, folder, dict(overrides, sources=sources))
    path = str(removed.get("path") or "") if isinstance(removed, Mapping) and not removed.get("url") else ""
    return {"ok": True, "sources": len(sources), "kept": os.path.basename(path)}


def _weights_path(spec: Any) -> str:
    weights = (spec.get("spread") or {}).get("weights") if isinstance(spec, Mapping) else None
    return str(weights.get("path") or "") if isinstance(weights, Mapping) else ""


def set_weights(data_dir: str, name: str, source_index: int, filename: str, csv_text: Any, mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """18.10.2026: קובץ משקלות (spread.weights) למקור של חודש/שנה - קובע איך הסכום של כל תקופה מתפזר על הימים
    (הסכום עצמו לא משתנה). הקובץ נבדק כקובץ זמני (עמודות, מספרים, שנים של המקור, טעינת הפרק), ורק אז נשמר כקובץ חדש
    תחת data/dataviz_overrides/<פרק>/ וה-override של המקור מפנה אליו. תיקיית הפרק ו-config.yaml לא נכתבים."""
    from dataviz.config import ConfigError, load_config
    from dataviz.episode import load_episode
    from dataviz.sources import read_table
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    csv_text = de.clean_table_text(csv_text)
    columns = de.csv_columns(csv_text)
    clean = {key: str(mapping.get(key) or "").strip() for key in ("period_column", "month_column", "value")}
    for key, label in (("period_column", "עמודת השנה"), ("month_column", "עמודת החודש"), ("value", "עמודת המשקל")):
        if clean[key] and clean[key] not in columns or not clean[key] and key != "month_column":
            raise de.EpisodeError(f"{label} '{clean[key]}' לא קיימת בקובץ (העמודות: {', '.join(columns)}).")
    if not clean["month_column"]:
        clean.pop("month_column")   # רק חלונות ימים (window_start / window_end)
    overrides = de.load_overrides_for_path(folder)
    config = load_config(os.path.join(folder, "config.yaml"), overrides)
    if not 0 <= source_index < len(config["sources"]):
        raise de.EpisodeError("אין מקור כזה.")
    table = read_table(config["sources"][source_index], config["base_dir"])
    if not len(table) or table["period"].iloc[0] == "day":
        raise de.EpisodeError("קובץ משקלות מתאים רק למקור של חודש או שנה - המקור הזה יומי.")
    weights = pd.read_csv(io.StringIO(csv_text))
    if pd.to_numeric(weights[clean["value"]], errors="coerce").isna().any():
        raise de.EpisodeError(f"עמודת המשקל '{clean['value']}' צריכה להכיל מספרים בלבד.")
    years = set(pd.to_numeric(weights[clean["period_column"]], errors="coerce").dropna().astype(int))
    periods = {pd.Timestamp(t).year for t in table["time"]}
    if not periods & years:
        raise de.EpisodeError(f"אף שורה בקובץ המשקלות לא שייכת לשנים של המקור ({min(periods)}-{max(periods)}).")
    target_dir = os.path.join(data_dir, de.OVERRIDES_DIRNAME, name)
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in os.path.splitext(os.path.basename(str(filename or "")))[0])[:40] or "weights"
    tmp = _check_file(target_dir, stem, csv_text)
    try:
        sources = json.loads(json.dumps(config["sources"], default=str))
        spread = dict(sources[source_index].get("spread") or {})
        sources[source_index]["spread"] = spread
        spread["weights"] = {"path": os.path.abspath(tmp), **clean}
        try:
            load_episode(folder, dict(overrides, sources=sources))
        except (ConfigError, KeyError, ValueError, TypeError) as e:
            raise de.EpisodeError("קובץ המשקלות לא נטען: " + str(e)[:200]) from None
        path = _reserve_csv(target_dir, stem)
        os.replace(tmp, path)   # על השם ששמרנו לעצמנו - לא דורס כלום
        spread["weights"] = {"path": os.path.abspath(path), **clean}
        de._write_overrides(data_dir, name, folder, dict(overrides, sources=sources))
        return {"saved": True, "file": os.path.basename(path), "periods": len(periods), "matched": len(periods & years)}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)   # safe: קובץ הבדיקה הזמני שיצרנו כאן


def _base_weights(folder: str, source_index: int) -> Any:
    """המשקלות של המקור ב-config.yaml עצמו (None למקור שנוסף מהדפדפן או בלי משקלות)."""
    from dataviz.config import load_config
    base = load_config(os.path.join(folder, "config.yaml"), {})["sources"]
    return (base[source_index].get("spread") or {}).get("weights") if source_index < len(base) else None


def remove_weights(data_dir: str, name: str, source_index: int) -> Dict[str, Any]:
    """18.10.2026: מסיר קובץ משקלות שנוסף מהדפדפן - רק מה-override (חזרה למשקלות של config.yaml, אם יש);
    הקובץ עצמו נשאר בדיסק בלי שינוי, כמו בהסרת מקור."""
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    overrides = de.load_overrides_for_path(folder)
    sources = json.loads(json.dumps(overrides.get("sources") or [], default=str))
    current = _weights_path(sources[source_index]) if 0 <= source_index < len(sources) else ""
    base = _base_weights(folder, source_index) if current else None
    if not current or _weights_path({"spread": {"weights": base}}) == current:
        raise de.EpisodeError("אפשר להסיר רק קובץ משקלות שנוסף מהדפדפן.")
    spread = dict(sources[source_index].get("spread") or {})
    if base:
        spread["weights"] = base
    else:
        spread.pop("weights", None)
    sources[source_index]["spread"] = spread
    if not spread:
        sources[source_index].pop("spread")
    de._write_overrides(data_dir, name, folder, dict(overrides, sources=sources))
    return {"ok": True, "kept": os.path.basename(current)}


# ---------- מוזיקה על גרף גלי הקול ----------
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac")
WAVE_POINTS = 600


def music_files(folder: str) -> List[str]:
    try:
        return sorted(n for n in os.listdir(folder) if n.lower().endswith(AUDIO_EXT) and os.path.isfile(os.path.join(folder, n)))
    except OSError:
        return []


def music_info(folder: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """קובצי המוזיקה בתיקיית הפרק, מה שנבחר, נקודת ההתחלה והדעיכות, ואורך הסרטון (לחלון על הגרף)."""
    with dp._lock:
        _key, episode, plan = dp._episode(folder, overrides, dp.SCALES[0], "full")
    audio = episode.config["audio"]
    return {"files": music_files(folder), "current": os.path.basename(str(audio.get("path") or "")),
            "start": float(audio.get("start") or 0), "fade_in": float(audio.get("fade_in") or 0),
            "fade_out": float(audio.get("fade_out") or 0), "video_seconds": round(len(plan) / int(episode.config["video"]["fps"]), 2)}


def waveform(folder: str, filename: str) -> Dict[str, Any]:
    """שיאי עוצמה (0-1) של קובץ מוזיקה מתיקיית הפרק. WAV נקרא ישירות (בלי ffmpeg); שאר הסוגים דרך pydub."""
    if filename not in music_files(folder):
        raise de.EpisodeError("קובץ המוזיקה לא נמצא בתיקיית הפרק.", status=404)
    path = os.path.join(folder, filename)
    if filename.lower().endswith(".wav"):
        import wave
        try:   # 23.10.2026: קובץ WAV פגום - הודעה, לא 500
            with wave.open(path, "rb") as w:
                frames, rate, width, channels = w.readframes(w.getnframes()), w.getframerate(), w.getsampwidth(), w.getnchannels()
        except (wave.Error, EOFError, OSError) as e:
            raise de.EpisodeError(f"קובץ ה-WAV פגום: {str(e)[:150]}") from None
        dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(width)
        if dtype is None:
            raise de.EpisodeError("פורמט WAV לא נתמך.")
        samples = np.frombuffer(frames, dtype=dtype).astype(float)
        if width == 1:
            samples -= 128
        samples = np.abs(samples.reshape(-1, channels).mean(axis=1)) if channels > 1 else np.abs(samples)
        duration = len(samples) / rate if rate else 0.0
    else:
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(path).set_channels(1)
        except Exception as e:
            raise de.EpisodeError(f"לא הצלחתי לפענח את הקובץ: {str(e)[:150]}") from None
        samples = np.abs(np.array(audio.get_array_of_samples(), dtype=float))
        duration = len(audio) / 1000.0
    if not len(samples):
        return {"peaks": [], "duration": 0.0}
    chunks = np.array_split(samples, min(WAVE_POINTS, len(samples)))
    peaks = np.array([c.max() if len(c) else 0.0 for c in chunks])
    top = peaks.max() or 1.0
    return {"peaks": [round(float(p / top), 3) for p in peaks], "duration": round(float(duration), 2)}


# ---------- גל 52: ניקוי נתונים ----------
def cleaning_report(folder: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """שמות דומים (לפני שמות חלופיים - כדי להציע מיזוג), קפיצות חשודות (לפני התיקונים שנשמרו - כדי לראות מה תוקן),
    התיקונים עצמם והגדרת הימים החסרים."""
    from dataviz.cleaning import find_outliers, similar_names
    from dataviz.config import load_config
    from dataviz.episode import apply_entity_rules
    from dataviz.sources import daily_matrix, read_table, resolved_sources
    config = load_config(os.path.join(folder, "config.yaml"), dict(overrides))
    specs = resolved_sources(config)
    data = config.get("data") or {}
    timeline = config.get("timeline") or {}
    matrix, origins = daily_matrix([read_table(spec, config["base_dir"]) for spec in specs], specs, config["base_dir"],
                                   timeline.get("start") or None, timeline.get("end") or None, missing=str(data.get("missing") or "zero"))
    entities = config.get("entities") or {}
    totals = {str(_plain(e)): float(matrix[e].sum()) for e in matrix.columns}
    ruled, ruled_origins = apply_entity_rules(matrix, origins, entities)
    levels = [e for e, i in ruled_origins.items() if specs[i].get("kind") == "level"]
    return {
        "similar": similar_names(totals, {str(k): str(v) for k, v in (entities.get("aliases") or {}).items()}),
        "outliers": find_outliers(ruled, levels=levels),
        "fixes": list(data.get("fixes") or []),
        "missing": str(data.get("missing") or "zero"),
        "aliases": dict(entities.get("aliases") or {}),
    }
