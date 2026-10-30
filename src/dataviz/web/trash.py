# dataviz/web/trash.py
#
# 20.10.2026: מחיקת פרק מהמסך - בלי מחיקה אמיתית. הפרק (התיקייה ב-data/dataviz_episodes), השינויים שלו מהדפדפן
# (data/dataviz_overrides/<שם>.json ו-<שם>/), מטמון המקורות מכתובת (data/dataviz_cache/<שם>) והרשומות שלו בקבצים של
# האפליקציה (הסתרה, תגיות, תור) עוברים לסל של עורך הגרפים: data/dataviz_trash/<שם>_<זמן>/ - תיקייה חדשה תמיד, עם
# manifest.json שאומר מאיפה בא כל חלק. "♻️ שחזר" מחזיר הכל למקום (ומסרב כשהשם תפוס). רק "רוקן סל" מוחק באמת - בבקשה
# מפורשת. התוצרים (workspace/dataviz/outputs) לא נוגעים. "רץ עכשיו / בתור" נבדק בנתיב (routes/dataviz.py).
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional

from dataviz.web import episodes as de
from dataviz.smart.create import SMART_ROOT
from dataviz.web.history import HISTORY_ROOT
from dataviz.web.variants import VARIANTS_ROOT
from utils.shared import data_paths

TRASH_DIRNAME = data_paths.DATAVIZ_TRASH
CACHE_DIRNAME = data_paths.DATAVIZ_CACHE            # dataviz.web.remote - מטמון המקורות מכתובת, לכל פרק
QUEUE_FILENAME = data_paths.DATAVIZ_QUEUE      # routes/dataviz.py - מצב תור הפרקים של הריצה האחרונה
MANIFEST = "manifest.json"
EMPTY_CONFIRM = "empty"


def trash_root(data_dir: str) -> str:
    return os.path.join(data_dir, TRASH_DIRNAME)


def _inside(path: str, root: str) -> bool:
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root and path != root


def _write_json(path: str, value: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _pieces(data_dir: str, name: str) -> List[Dict[str, str]]:
    """החלקים של פרק שעוברים לסל: (יחסית ל-data/, ושם בתוך תיקיית הסל). רק מה שקיים."""
    candidates = [("episode", os.path.join(de.EPISODES_DIRNAME, name)),
                  ("overrides.json", os.path.join(de.OVERRIDES_DIRNAME, name + ".json")),
                  ("overrides", os.path.join(de.OVERRIDES_DIRNAME, name)),
                  ("cache", os.path.join(CACHE_DIRNAME, name)),
                  ("history", os.path.join(HISTORY_ROOT, name)),
                  ("variants", os.path.join(VARIANTS_ROOT, name)),
                  ("smart", os.path.join(SMART_ROOT, name + ".json")),   # 20.10.2026: הבחירות האוטומטיות (dataviz/smart/create.py)
                  ("smart_thumbnail", os.path.join(SMART_ROOT, name + "_thumbnail.png"))]   # 20.10.2026: הגרסאות של הפרק (dataviz/web/variants.py)   # 20.10.2026: היסטוריית הגרסאות (dataviz/web/history.py)
    return [{"to": to, "from": rel.replace(os.sep, "/")} for to, rel in candidates if os.path.exists(os.path.join(data_dir, rel))]


def _new_trash_dir(data_dir: str, name: str) -> str:
    root = trash_root(data_dir)
    os.makedirs(root, exist_ok=True)
    base = f"{name}_{time.strftime('%Y%m%d_%H%M%S')}"
    for i in range(1, 1000):
        path = os.path.join(root, base + (f"_{i}" if i > 1 else ""))
        try:
            os.mkdir(path)   # בלעדי - שני פרקים / שתי מחיקות באותה שנייה לא חולקים תיקייה
            return path
        except FileExistsError:
            continue
    raise de.EpisodeError("לא נמצא שם פנוי בסל - נסה שוב.", status=500)


def _move_all(data_dir: str, dest: str, pieces: List[Dict[str, str]], manifest: Dict[str, Any]) -> None:
    """23.10.2026: כל חלק עובר בשינוי שם בלבד. shutil.move נפל להעתקה + מחיקה כשקובץ בפרק היה פתוח (Excel, ffmpeg),
    מחק חלק מהקבצים ונכשל על הפתוח - חצי פרק נשאר, והסל קיבל רשימה ריקה. עכשיו כשל מחזיר את מה שכבר עבר, ושום
    דבר לא נמחק; מה שלא הצליח לחזור נשאר רשום בסל (אפשר לשחזר)."""
    moved: List[Dict[str, str]] = []
    try:
        for piece in pieces:
            os.rename(os.path.join(data_dir, piece["from"]), os.path.join(dest, piece["to"]))
            moved.append(piece)
    except OSError as e:
        for piece in reversed(moved):
            try:
                os.rename(os.path.join(dest, piece["to"]), os.path.join(data_dir, piece["from"]))
            except OSError:
                continue
        stuck = [p for p in moved if os.path.exists(os.path.join(dest, p["to"]))]
        if stuck:
            _write_json(os.path.join(dest, MANIFEST), dict(manifest, items=stuck))
        else:
            try:
                os.rmdir(dest)   # רק אם ריקה - תיקיית הסל שנוצרה לניסיון הזה
            except OSError:
                pass
        raise de.EpisodeError("קובץ של הפרק פתוח בתוכנה אחרת (למשל Excel או רינדור שרץ) - סגור אותו ונסה שוב.", status=409) from e
    manifest["items"].extend(moved)


def delete_episode(data_dir: str, name: Any) -> Dict[str, Any]:
    """הפרק וכל מה ששייך לו עוברים לתיקייה חדשה בסל, עם manifest. שום דבר לא נמחק."""
    name = str(name or "")
    folder = de.episode_folder(data_dir, name)
    if folder is None or not _inside(folder, de.episodes_root(data_dir)):
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    title = de._summary(name, folder).get("title") or name
    pieces = _pieces(data_dir, name)
    dest = _new_trash_dir(data_dir, name)
    manifest: Dict[str, Any] = {"name": name, "title": title, "deleted_at": time.strftime("%Y-%m-%d %H:%M:%S"), "items": [],
                                "hidden": False, "tags": None, "queue": []}
    _move_all(data_dir, dest, pieces, manifest)
    try:
        hidden = de.load_hidden(data_dir)
        if name in hidden:
            manifest["hidden"] = True
            _write_json(de.hidden_path(data_dir), {"hidden": [n for n in hidden if n != name]})
        tags = de.load_tags(data_dir)
        if name in tags:
            manifest["tags"] = tags.pop(name)
            _write_json(os.path.join(data_dir, de.TAGS_FILENAME), {"episodes": tags})
        queue_path = os.path.join(data_dir, QUEUE_FILENAME)
        queue = _read_json(queue_path, None)
        if isinstance(queue, dict) and isinstance(queue.get("episodes"), list):
            manifest["queue"] = [e for e in queue["episodes"] if isinstance(e, dict) and e.get("name") == name]
            if manifest["queue"]:
                _write_json(queue_path, dict(queue, episodes=[e for e in queue["episodes"] if e not in manifest["queue"]]))
    finally:
        _write_json(os.path.join(dest, MANIFEST), manifest)   # גם אם משהו נכשל באמצע - כתוב מה עבר ומאיפה
    return {"ok": True, "trash_id": os.path.basename(dest), "name": name, "moved": [p["from"] for p in manifest["items"]]}


def _trash_folder(data_dir: str, trash_id: Any) -> str:
    trash_id = str(trash_id or "")
    path = os.path.join(trash_root(data_dir), trash_id)
    if not trash_id or os.path.basename(trash_id) != trash_id or trash_id in (".", "..") or not _inside(path, trash_root(data_dir)) \
            or not os.path.isfile(os.path.join(path, MANIFEST)):
        raise de.EpisodeError("לא נמצא בסל.", status=404)
    return path


def list_trash(data_dir: str) -> List[Dict[str, Any]]:
    root = trash_root(data_dir)
    rows = []
    for trash_id in sorted(os.listdir(root), reverse=True) if os.path.isdir(root) else []:
        manifest = _read_json(os.path.join(root, trash_id, MANIFEST), None)
        if not isinstance(manifest, dict):
            continue
        name = str(manifest.get("name") or "")
        rows.append({"id": trash_id, "name": name, "title": str(manifest.get("title") or name), "deleted_at": str(manifest.get("deleted_at") or ""),
                     "taken": os.path.exists(os.path.join(de.episodes_root(data_dir), name))})
    return rows


def restore_episode(data_dir: str, trash_id: Any) -> Dict[str, Any]:
    """מחזיר את כל החלקים למקומם (ואת ההסתרה והתגיות). שם תפוס / קובץ שכבר קיים במקום = 409, ושום דבר לא זז."""
    path = _trash_folder(data_dir, trash_id)
    manifest = _read_json(os.path.join(path, MANIFEST), {})
    name = str(manifest.get("name") or "")
    if not de.NAME_RE.match(name):
        raise de.EpisodeError("רשומת הסל פגומה.", status=400)
    items = [i for i in manifest.get("items") or [] if isinstance(i, dict)]
    for item in items:
        target = os.path.join(data_dir, str(item.get("from") or ""))
        if not _inside(target, data_dir) or not os.path.exists(os.path.join(path, str(item.get("to") or ""))):
            raise de.EpisodeError("רשומת הסל פגומה.", status=400)
        if os.path.exists(target):
            raise de.EpisodeError(f"כבר יש פרק בשם '{name}' (או קובץ שלו במקום) - שנה את שמו או מחק אותו קודם.", status=409)
    for item in items:
        target = os.path.join(data_dir, str(item["from"]))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.move(os.path.join(path, str(item["to"])), target)
    if manifest.get("hidden"):
        _write_json(de.hidden_path(data_dir), {"hidden": sorted(set(de.load_hidden(data_dir)) | {name})})
    if isinstance(manifest.get("tags"), dict):
        tags = de.load_tags(data_dir)
        tags[name] = manifest["tags"]
        _write_json(os.path.join(data_dir, de.TAGS_FILENAME), {"episodes": tags})
    os.remove(os.path.join(path, MANIFEST))   # safe: ה-manifest שכתבנו - כל החלקים כבר חזרו למקומם
    if not os.listdir(path):
        os.rmdir(path)
    return {"ok": True, "name": name, "restored": [str(i["from"]) for i in items]}


def empty_trash(data_dir: str, confirm: Optional[str]) -> Dict[str, Any]:
    """מחיקה אמיתית של כל מה שבסל של עורך הגרפים - רק עם confirm="empty" (אישור שני במסך)."""
    if confirm != EMPTY_CONFIRM:
        raise de.EpisodeError("ריקון הסל דורש אישור מפורש.", status=400)
    root = trash_root(data_dir)
    removed = 0
    for trash_id in os.listdir(root) if os.path.isdir(root) else []:
        path = os.path.join(root, trash_id)
        if os.path.isdir(path) and _inside(path, root):
            shutil.rmtree(path)   # safe: רק תיקיות בסל של עורך הגרפים, אחרי שני אישורים של המשתמש
            removed += 1
    return {"ok": True, "removed": removed}
