# dataviz/web/history.py
#
# 20.10.2026: היסטוריית גרסאות לפרק - בכל שמירה של קובץ השינויים (episodes._write_overrides) נשמרת תמונת מצב:
# ה-override אחרי השמירה ו-config.yaml כפי שהוא באותו רגע (לצורך השוואה בלבד). הקבצים תחת
# data/dataviz_history/<פרק>/ - תיקייה של האפליקציה עצמה (עוברת לסל עם הפרק - trash.py). רשימה, השוואה לעכשיו ושחזור (רק של קובץ השינויים -
# config.yaml לעולם לא נכתב; שחזור הוא שמירה רגילה, אז גם הוא נכנס להיסטוריה וניתן לבטל אותו).
# תקרה: MAX_VERSIONS אחרונות (הישנות ביותר נמחקות - רק תמונות המצב שלנו), ותמונה גדולה מ-MAX_BYTES לא נשמרת.
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Mapping, Optional
from utils.shared import data_paths

HISTORY_ROOT = data_paths.DATAVIZ_HISTORY
MAX_VERSIONS = 40
MAX_BYTES = 512 * 1024          # תמונת מצב אחת
MAX_CONFIG_BYTES = 64 * 1024    # config.yaml גדול מזה - נשמרת רק טביעת האצבע שלו


def history_dir(data_dir: str, name: str) -> str:
    return os.path.join(data_dir, HISTORY_ROOT, name)


def _config_state(folder: str) -> Dict[str, Any]:
    try:
        with open(os.path.join(folder, "config.yaml"), "rb") as f:
            raw = f.read()
    except OSError:
        return {"config_sha1": "", "config": None}
    text = raw.decode("utf-8", errors="replace") if len(raw) <= MAX_CONFIG_BYTES else None
    return {"config_sha1": hashlib.sha1(raw).hexdigest(), "config": text}


def _ids(data_dir: str, name: str) -> List[str]:
    try:
        return sorted(n[:-5] for n in os.listdir(history_dir(data_dir, name)) if n.endswith(".json"))
    except OSError:
        return []


def _load(data_dir: str, name: str, version: str) -> Optional[Dict[str, Any]]:
    if not version or os.sep in version or "/" in version or ".." in version:
        return None
    try:
        with open(os.path.join(history_dir(data_dir, name), version + ".json"), encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def record(data_dir: str, name: str, folder: str, overrides: Mapping[str, Any], previous: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """תמונת מצב אחרי שמירה. previous = מה שהיה לפני (נשמר פעם אחת, כשאין עדיין היסטוריה - כדי שאפשר יהיה לחזור
    גם למצב שלפני השמירה הראשונה). מצב זהה לאחרון לא נשמר שוב. מחזיר את המזהה, או None."""
    ids = _ids(data_dir, name)
    if not ids and previous is not None and dict(previous) != dict(overrides):
        _write(data_dir, name, folder, previous, "לפני השמירה הראשונה")
        ids = _ids(data_dir, name)
    config = _config_state(folder)
    last = _load(data_dir, name, ids[-1]) if ids else None
    if last and last.get("overrides") == json.loads(json.dumps(dict(overrides))) and last.get("config_sha1") == config["config_sha1"]:
        return None
    version = _write(data_dir, name, folder, overrides, "")
    for old in _ids(data_dir, name)[:-MAX_VERSIONS]:
        try:
            os.remove(os.path.join(history_dir(data_dir, name), old + ".json"))   # safe: רק תמונות המצב שהאפליקציה כתבה
        except OSError:
            pass
    return version


def _write(data_dir: str, name: str, folder: str, overrides: Mapping[str, Any], note: str) -> Optional[str]:
    snapshot = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note, "overrides": dict(overrides), **_config_state(folder)}
    payload = json.dumps(snapshot, ensure_ascii=False, indent=1)
    if len(payload.encode("utf-8")) > MAX_BYTES:
        snapshot["config"] = None
        payload = json.dumps(snapshot, ensure_ascii=False, indent=1)
        if len(payload.encode("utf-8")) > MAX_BYTES:
            return None
    root = history_dir(data_dir, name)
    os.makedirs(root, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns() % 1_000_000_000:09d}"
    tmp = os.path.join(root, stamp + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
    os.replace(tmp, os.path.join(root, stamp + ".json"))
    return stamp


def _flat(node: Any, prefix: str = "") -> Dict[str, Any]:
    if isinstance(node, Mapping) and node:
        out: Dict[str, Any] = {}
        for key, value in node.items():
            out.update(_flat(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: node} if prefix else {}


def versions(data_dir: str, name: str) -> Dict[str, Any]:
    """הגרסאות מהחדשה לישנה: {id, time, note, changes (כמה הגדרות שונות מעכשיו), config_changed}."""
    from dataviz.web import episodes as de
    folder = de.episode_folder(data_dir, name)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    current = _flat(de.load_overrides_for_path(folder))
    sha = _config_state(folder)["config_sha1"]
    rows = []
    for version in reversed(_ids(data_dir, name)):
        snap = _load(data_dir, name, version)
        if snap is None:
            continue
        then = _flat(snap.get("overrides") or {})
        changes = sum(1 for p in set(then) | set(current) if then.get(p) != current.get(p))
        rows.append({"id": version, "time": snap.get("time", ""), "note": snap.get("note", ""), "changes": changes,
                     "config_changed": bool(sha) and snap.get("config_sha1") != sha})
    return {"versions": rows, "limit": MAX_VERSIONS}


def diff(data_dir: str, name: str, version: str) -> Dict[str, Any]:
    """מה ישתנה אם משחזרים: לכל הגדרה - עכשיו ובגרסה. config.yaml רק מדווח (לא משוחזר)."""
    from dataviz.web import episodes as de
    folder = de.episode_folder(data_dir, name)
    snap = _load(data_dir, name, version) if folder else None
    if folder is None or snap is None:
        raise de.EpisodeError("הגרסה לא נמצאה.", status=404)
    current = _flat(de.load_overrides_for_path(folder))
    then = _flat(snap.get("overrides") or {})
    rows = [{"path": p, "now": current.get(p), "then": then.get(p)} for p in sorted(set(then) | set(current)) if then.get(p) != current.get(p)]
    config = _config_state(folder)
    return {"id": version, "time": snap.get("time", ""), "changes": rows,
            "config_changed": bool(config["config_sha1"]) and snap.get("config_sha1") != config["config_sha1"]}


def restore(data_dir: str, name: str, version: str) -> Dict[str, Any]:
    """שחזור קובץ השינויים לגרסה (שמירה רגילה, עם בדיקת תקינות - ונכנסת להיסטוריה). config.yaml לא נכתב."""
    from dataviz.web import episodes as de
    folder = de.episode_folder(data_dir, name)
    snap = _load(data_dir, name, version) if folder else None
    if folder is None or snap is None:
        raise de.EpisodeError("הגרסה לא נמצאה.", status=404)
    de._write_overrides(data_dir, name, folder, dict(snap.get("overrides") or {}))
    return {"ok": True, "restored": version}
