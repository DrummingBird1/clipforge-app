# utils/video/editor_runs.py
#
# גל 8 של 102-ההצעות (item 92): "ריצות אחרונות" בתוך עורך-העל - כל ריצה נשמרת עם
# התיקייה וההגדרות המלאות שלה, כדי שאפשר יהיה לטעון אותן מחדש לפאנל או "להריץ
# שוב" בלחיצה. הסטטוס/סיכום מתעדכנים בסיום. רק MAX_RUNS האחרונות נשמרות.

import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

MAX_RUNS = 30
# שדות-ריצה חולפים שלא שייכים ל"הגדרות" של ריצה חוזרת
# (פעולות סוף-ריצה/פרסום הן העדפות של מי שמריץ עכשיו - "הרץ שוב" לא מפרסם/מרדים בשקט)
TRANSIENT_KEYS = ("script", "folder", "only_files", "batch_overrides", "ve_profile_name", "rerun_of",
                  "finish_actions", "publish_after", "publish_dry_run")
_lock = threading.Lock()


def load_runs(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [run for run in data if isinstance(run, dict) and run.get("id")] if isinstance(data, list) else []


def _save(path: str, runs: List[Dict[str, Any]]) -> None:
    from utils.shared.atomic_write import atomic_write_json
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    atomic_write_json(path, runs[:MAX_RUNS], ensure_ascii=False, indent=2)


def record_start(path: str, folder: str, payload: Dict[str, Any], profile_name: Optional[str] = None,
                 extra: Optional[Dict[str, Any]] = None) -> str:
    """רושם ריצה חדשה (בראש הרשימה) ומחזיר את ה-id שלה."""
    run_id = uuid.uuid4().hex[:12]
    settings = {k: v for k, v in payload.items() if k not in TRANSIENT_KEYS}
    entry: Dict[str, Any] = {
        "id": run_id, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "folder": folder,
        "profile_name": profile_name or None, "settings": settings, "status": "running",
        "only_files": payload.get("only_files") if isinstance(payload.get("only_files"), list) else None,
        "batch_overrides": payload.get("batch_overrides") if isinstance(payload.get("batch_overrides"), dict) else None,
    }
    if extra:
        entry.update(extra)
    with _lock:
        runs = load_runs(path)
        runs.insert(0, entry)
        _save(path, runs)
    return run_id


def record_finish(path: str, run_id: str, success: bool, result: Optional[Dict[str, Any]], duration_seconds: Optional[float]) -> None:
    summary = {}
    if isinstance(result, dict):
        for key in ("files_created", "errors", "skipped", "cancelled", "manifest_path"):
            if key in result:
                summary[key] = result[key]
    with _lock:
        runs = load_runs(path)
        for run in runs:
            if run["id"] == run_id:
                run.update(status="success" if success else "failed", finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                           duration_seconds=round(duration_seconds, 1) if duration_seconds is not None else None, **summary)
                break
        _save(path, runs)


def get_run(path: str, run_id: str) -> Optional[Dict[str, Any]]:
    return next((run for run in load_runs(path) if run["id"] == run_id), None)


MAX_RUN_NAME = 60
MAX_RUN_TAGS = 8


def set_run_label(path: str, run_id: str, name: str, tags: List[str]) -> Optional[Dict[str, Any]]:
    """גל 36: שם ותגיות לריצה (להבדיל בין ריצות ולמצוא אותן). שם ריק מוחק את השם; תגיות בלי
    כפילויות ובלי '#'. מחזיר את הריצה המעודכנת, או None כשהיא לא בהיסטוריה."""
    clean_name = " ".join(str(name or "").split())[:MAX_RUN_NAME]
    clean_tags: List[str] = []
    for tag in tags or []:
        tag = str(tag).strip().lstrip("#").strip()[:24]
        if tag and tag not in clean_tags:
            clean_tags.append(tag)
    with _lock:
        runs = load_runs(path)
        run = next((r for r in runs if r["id"] == run_id), None)
        if run is None:
            return None
        if clean_name:
            run["name"] = clean_name
        else:
            run.pop("name", None)
        if clean_tags:
            run["tags"] = clean_tags[:MAX_RUN_TAGS]
        else:
            run.pop("tags", None)
        _save(path, runs)
    return run


def delete_run(path: str, run_id: str) -> bool:
    with _lock:
        runs = load_runs(path)
        kept = [run for run in runs if run["id"] != run_id]
        if len(kept) == len(runs):
            return False
        _save(path, kept)
    return True
