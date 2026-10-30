# dataviz/smart/watch.py
#
# 20.10.2026: תיקייה במעקב (פריט 15, כבוי כברירת מחדל) - תיקייה חדשה בתוך שורש שנבחר (למשל ColdData/Graphs - רק נקרא)
# -> טיוטת פרק אוטומטית (create.py) + דוח תמונות של הפרק (batch.py, בלי וידאו) + התראה (ה-hook הקיים: Discord אם הוגדר,
# notify.py). לעולם לא רינדור מלא בלי המשתמש. בהפעלה התיקיות שכבר קיימות נרשמות כ"נראו" - רק חדשות מתחילות טיוטה.
# ההגדרות ב-data/dataviz_smart/watch.json; בדיקה כל interval דקות ב-thread רקע של השרת (רק כשמופעל), או ב"בדוק עכשיו".
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional

from dataviz.smart.create import SMART_ROOT

WATCH_FILE = "watch.json"
MAX_LOG = 30
DEFAULTS: Dict[str, Any] = {"enabled": False, "root": "", "interval_minutes": 30, "kit": "", "seen": [], "log": []}
_lock = threading.Lock()
_thread: Optional[threading.Thread] = None


def watch_path(data_dir: str) -> str:
    return os.path.join(data_dir, SMART_ROOT, WATCH_FILE)


def load(data_dir: str) -> Dict[str, Any]:
    try:
        with open(watch_path(data_dir), encoding="utf-8") as f:
            value = json.load(f)
    except (OSError, ValueError):
        value = {}
    return {**DEFAULTS, **(value if isinstance(value, dict) else {})}


def _save(data_dir: str, settings: Mapping[str, Any]) -> None:
    path = watch_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _subfolders(root: str) -> List[str]:
    from dataviz.smart.scan import TABLE_EXT
    if not root or not os.path.isdir(root):
        return []
    found = []
    for n in sorted(os.listdir(root)):
        if n.startswith(".") or not os.path.isdir(os.path.join(root, n)):
            continue
        try:
            names = os.listdir(os.path.join(root, n))
        except OSError:   # ב27: שורש כונן - System Volume Information (PermissionError) הפיל את כל הבדיקה
            continue
        if any(f.lower().endswith(TABLE_EXT) for f in names):
            found.append(n)
    return found


def configure(data_dir: str, enabled: Any, root: Any, interval_minutes: Any = 30, kit: Any = "") -> Dict[str, Any]:
    """שמירת ההגדרות. בהפעלה (או בשורש חדש) - כל התיקיות שכבר שם נרשמות כ"נראו"."""
    from dataviz.web.episodes import EpisodeError
    root = os.path.abspath(str(root or "").strip().strip('"')) if str(root or "").strip() else ""
    if enabled and not os.path.isdir(root):
        raise EpisodeError("השורש לא נמצא.", status=404)
    try:
        interval = max(5, min(24 * 60, int(interval_minutes)))
    except (TypeError, ValueError):
        raise EpisodeError("כל כמה דקות - מספר.") from None
    with _lock:
        settings = load(data_dir)
        if enabled and (not settings["enabled"] or settings["root"] != root):
            settings["seen"] = _subfolders(root)
        settings.update({"enabled": bool(enabled), "root": root, "interval_minutes": interval, "kit": str(kit or "")})
        _save(data_dir, settings)
    if settings["enabled"]:
        start(data_dir, None)
    return status(data_dir)


def status(data_dir: str) -> Dict[str, Any]:
    settings = load(data_dir)
    return {k: settings[k] for k in ("enabled", "root", "interval_minutes", "kit", "log")} | {"seen": len(settings["seen"]),
                                                                                              "pending": [n for n in _subfolders(settings["root"]) if n not in settings["seen"]]}


def check(data_dir: str, workspace_dir: str, send: Optional[Callable[[str], bool]] = None) -> List[Dict[str, Any]]:
    """תיקיות חדשות בשורש -> טיוטה + דוח תמונות + התראה. מחזיר מה נעשה. תיקייה שנכשלה גם נרשמת (בלי ניסיון חוזר בלולאה)."""
    from dataviz.smart.create import _name, create_from_folder
    from dataviz.web import batch
    from dataviz.web import episodes as de
    with _lock:
        settings = load(data_dir)
        if not settings["enabled"]:
            return []
        new = [n for n in _subfolders(settings["root"]) if n not in settings["seen"]]
        settings["seen"] = list(settings["seen"]) + new
        _save(data_dir, settings)
    done = []
    for folder_name in new:
        entry: Dict[str, Any] = {"folder": folder_name, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        # ב26: השם של הפרק כמו ש-create_from_folder יקבע אותו ("my data" -> my_data) - קודם הבדיקה אם הוא תפוס והדוח
        # רצו על השם הגולמי: הדוח על נתיב ריק, ו-my_data קיים -> התיקייה נכשלה ונרשמה כ"נראתה" לתמיד
        base = _name(os.path.join(settings["root"], folder_name), "")
        name = base
        for i in range(2, 50):
            if de.episode_folder(data_dir, name) is None:
                break
            name = f"{base}_{i}"
        try:
            record = create_from_folder(data_dir, os.path.join(settings["root"], folder_name), name, kit=settings["kit"])
            entry["episode"] = name = record["episode"]
            out = batch._new_out_dir(workspace_dir)
            report = batch.run(data_dir, workspace_dir, [{"name": name, "path": de.episode_folder(data_dir, name) or "", "app": "1"}], out)
            entry["report"] = os.path.basename(out)
            entry["ok"] = report["failed"] == 0
        except Exception as e:   # תיקייה שבורה לא עוצרת את המעקב - נרשמת עם השגיאה
            entry["error"] = str(e)[:300]
        entry["notified"] = _notify(entry, send)
        done.append(entry)
    if done:
        with _lock:
            settings = load(data_dir)
            settings["log"] = (done + list(settings["log"]))[:MAX_LOG]
            _save(data_dir, settings)
    return done


def _notify(entry: Mapping[str, Any], send: Optional[Callable[[str], bool]]) -> bool:
    """ה-hook הקיים של ההתראות (Discord, אם הוגדר כתובת). send = מקבל מזויף בטסטים."""
    text = (f"🤖 עורך הגרפים: טיוטה חדשה מהתיקייה '{entry['folder']}' - הפרק {entry['episode']} מחכה לאישור (דוח תמונות {entry.get('report', '')})"
            if entry.get("episode") else f"⚠️ עורך הגרפים: התיקייה '{entry['folder']}' לא הפכה לטיוטה - {entry.get('error', '')}")
    if send is not None:
        return bool(send(text))
    from dataviz.web import notify
    url = notify.get_url()
    return notify.send(url, text) if url else False


def start(data_dir: str, workspace_dir: Optional[str]) -> None:
    """thread רקע אחד שבודק כל interval דקות, כל עוד המעקב מופעל (נעצר לבד כשמכבים)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    workspace = workspace_dir or os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(os.path.dirname(os.path.abspath(data_dir)), "workspace")

    def loop() -> None:
        while True:
            settings = load(data_dir)
            if not settings["enabled"]:
                return
            try:
                check(data_dir, workspace)
            except Exception:
                pass
            time.sleep(60 * int(settings["interval_minutes"]))

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return   # בטסטים - רק check() ישירות, בלי thread רקע
    _thread = threading.Thread(target=loop, name="dataviz-watch", daemon=True)
    _thread.start()
