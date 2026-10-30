# utils/video/editor_projects.py
#
# גל 12 - "פרויקט" של עורך-העל: כל מה שנוגע לתיקייה אחת נשמר יחד ונפתח מחדש -
# המתכון (snapshot מלא + שם הפרופיל שממנו התחיל), היעדים, עריכות-הקליפ לכל קובץ,
# סדר/בחירת התור וערכת המותג. הממשק שומר אוטומטית (debounced) בכל שינוי, כך
# שרענון/סגירת טאב/קריסה לא מאבדים עבודה, ופתיחת אותה תיקייה משחזרת אותה.
#
# קובץ לכל פרויקט תחת data/editor_projects/ (מזהה = hash של הנתיב המנורמל), ליד
# קובץ הפרופילים ונגזר ממנו בזמן-קריאה - טסטים שמפנים את הפרופילים לתיקייה זמנית
# מפנים גם את זה. כתיבה אטומית בלבד (בלי גיבוי-מסתובב: זו טיוטה שנשמרת כל כמה
# שניות, לא נתון שנוצר ידנית פעם אחת).

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from utils.video import video_editor_profiles as vep
from utils.shared.atomic_write import atomic_write_json
from utils.shared import data_paths
from utils.video.editor_model import SCHEMA_VERSION, sanitize_targets

MAX_PROJECTS = 200
PROJECT_KEYS = ("recipe", "profile_name", "targets", "clip_edits", "queue", "brand_kit", "name", "last_run_id")
EXPORT_FORMAT = "clipforge-project"


def projects_dir() -> str:
    return os.path.join(os.path.dirname(vep.PROFILES_PATH), data_paths.EDITOR_PROJECTS)


def assets_dir(folder: str) -> str:
    """גל 29: קבצים שנגררו לנגן/לציר-הזמן (לוגו, B-roll, פס-קול) - ליד הפרויקטים, לא בתיקיית
    הקלט (שם הם היו נכנסים לתור ומרונדרים כקלט). תיקייה לכל פרויקט."""
    return os.path.join(os.path.dirname(vep.PROFILES_PATH), data_paths.EDITOR_ASSETS, project_id(folder))


def project_id(folder: str) -> str:
    normalized = os.path.normcase(os.path.realpath(os.path.abspath(str(folder or ""))))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _path(pid: str) -> str:
    if not pid.isalnum():
        raise ValueError("מזהה פרויקט לא תקין")
    return os.path.join(projects_dir(), f"{pid}.json")


def _read(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in PROJECT_KEYS:
        if key in data:
            out[key] = data[key]
    if "targets" in out:
        out["targets"] = sanitize_targets(out["targets"])
    if "clip_edits" in out and not isinstance(out["clip_edits"], dict):
        out["clip_edits"] = {}
    if "recipe" in out and not isinstance(out["recipe"], dict):
        out["recipe"] = {}
    return out


def load_project(folder: str) -> Optional[Dict[str, Any]]:
    return _read(_path(project_id(folder)))


def save_project(folder: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """שמירה (merge) - רק המפתחות שנשלחו מתעדכנים; folder/id/זמנים מנוהלים כאן."""
    if not folder or not os.path.isdir(folder):
        raise ValueError("תיקיית הפרויקט לא קיימת.")
    pid = project_id(folder)
    current = _read(_path(pid)) or {"created_at": datetime.now().isoformat(timespec="seconds")}
    current.update(_clean(data or {}))
    current.update({"id": pid, "folder": os.path.abspath(folder), "schema_version": SCHEMA_VERSION,
                    "updated_at": datetime.now().isoformat(timespec="seconds")})
    if not current.get("name"):
        current["name"] = os.path.basename(os.path.normpath(folder)) or folder
    os.makedirs(projects_dir(), exist_ok=True)
    atomic_write_json(_path(pid), current, ensure_ascii=False, indent=2)
    _prune()
    return current


def delete_project(folder: str) -> bool:
    path = _path(project_id(folder))
    if not os.path.isfile(path):
        return False
    os.remove(path)  # safe: this module's own project draft under data/editor_projects/, recreated by autosave
    return True


_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm")


def _first_video(folder: str, queue: Any) -> Optional[str]:
    """גל 19: הקובץ הראשון של הפרויקט (לתמונה הממוזערת במסך העבודות) - הראשון
    שמסומן בתור השמור, ואם אין תור - קובץ הווידאו הראשון (לפי שם) בשורש התיקייה."""
    if not os.path.isdir(folder):
        return None
    files = (queue or {}).get("files") if isinstance(queue, dict) else None
    for item in files or []:
        if isinstance(item, dict) and item.get("selected", True) and item.get("name"):
            path = os.path.join(folder, str(item["name"]))
            if os.path.isfile(path):
                return path
    try:
        names = sorted(entry.name for entry in os.scandir(folder)
                       if entry.is_file() and os.path.splitext(entry.name)[1].lower() in _VIDEO_EXTENSIONS)
    except OSError:
        return None
    return os.path.join(folder, names[0]) if names else None


def list_projects(limit: int = 50) -> List[Dict[str, Any]]:
    directory = projects_dir()
    if not os.path.isdir(directory):
        return []
    items = []
    for name in os.listdir(directory):
        if not name.endswith(".json"):
            continue
        data = _read(os.path.join(directory, name))
        if not data or not data.get("folder"):
            continue
        clip_edits = data.get("clip_edits") or {}
        items.append({
            "id": data.get("id"), "name": data.get("name"), "folder": data.get("folder"), "updated_at": data.get("updated_at"),
            "profile_name": data.get("profile_name"), "targets": data.get("targets") or [], "brand_kit": data.get("brand_kit") or "",
            "clip_edit_count": sum(1 for v in clip_edits.values() if v), "last_run_id": data.get("last_run_id"),
            "folder_exists": os.path.isdir(str(data.get("folder"))),
            "first_file": _first_video(str(data.get("folder")), data.get("queue")),
        })
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items[:limit]


def _prune() -> None:
    directory = projects_dir()
    files = [os.path.join(directory, n) for n in os.listdir(directory) if n.endswith(".json")]
    if len(files) <= MAX_PROJECTS:
        return
    files.sort(key=os.path.getmtime)
    for path in files[: len(files) - MAX_PROJECTS]:
        try:
            os.remove(path)  # safe: oldest of this module's own autosaved project drafts, beyond the MAX_PROJECTS cap
        except OSError:
            pass


def export_project(folder: str) -> Optional[Dict[str, Any]]:
    data = load_project(folder)
    if not data:
        return None
    return {"format": EXPORT_FORMAT, "version": SCHEMA_VERSION, "project": {k: data.get(k) for k in (*PROJECT_KEYS, "folder")}}


def import_project(payload: Dict[str, Any], folder: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != EXPORT_FORMAT or not isinstance(payload.get("project"), dict):
        raise ValueError("זה לא קובץ פרויקט של ClipForge.")
    project = payload["project"]
    target_folder = folder or project.get("folder")
    return save_project(str(target_folder or ""), project)
