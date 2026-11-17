# utils/capture/orphans.py
#
# 17.11.2026 (ClipForge 2.0.1): ניקוי אחרי שרת שמת בזמן הקלטה. child_guard סוגר את ffmpeg יחד עם השרת; זה הגיבוי למה שנשאר
# מגרסה קודמת או משיוך שנכשל:
#   - כל ffmpeg שמנוע ההקלטה מפעיל נרשם בקובץ (pid + זמן יצירה, כדי לא להרוג תהליך אחר שקיבל אותו pid).
#   - בעלייה: מי שעדיין חי מהרשימה נסגר, ותיקיות ה-replay שנשארו במטמון נמחקות (מקטעים של המטמון שלנו, לא קבצים של המשתמש).
import json
import os
from typing import Any, Dict, List

from utils.capture import ring_buffer


def _load(path: str) -> List[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [e for e in data if isinstance(e, dict) and isinstance(e.get("pid"), int)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save(path: str, entries: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f)
    except OSError:
        pass


def _created(pid: int) -> float:
    try:
        import psutil
        return float(psutil.Process(pid).create_time())
    except Exception:
        return 0.0


def remember(path: str, pid: Any) -> None:
    if isinstance(pid, int) and pid > 0:
        _save(path, [e for e in _load(path) if e["pid"] != pid] + [{"pid": pid, "created": _created(pid)}])


def forget(path: str, pid: Any) -> None:
    if isinstance(pid, int):
        _save(path, [e for e in _load(path) if e["pid"] != pid])


def kill_leftovers(path: str) -> int:
    """סוגר תהליכי ffmpeg מהרשימה שעדיין חיים. מחזיר כמה נסגרו."""
    entries = _load(path)
    if not entries:
        return 0
    killed = 0
    try:
        import psutil
    except Exception:
        return 0
    for entry in entries:
        try:
            process = psutil.Process(entry["pid"])
            same = abs(float(process.create_time()) - float(entry.get("created") or 0)) < 2.0
            if same and "ffmpeg" in process.name().lower():
                process.kill()
                killed += 1
        except Exception:
            continue
    _save(path, [])
    return killed


def sweep_replay_cache(cache_dir: str) -> int:
    """מוחק תיקיות replay שנשארו במטמון מריצה קודמת. מחזיר כמה מקטעים נמחקו."""
    root = os.path.join(cache_dir, "replay")
    removed = 0
    try:
        folders = [os.path.join(root, name) for name in os.listdir(root)]
    except OSError:
        return 0
    for folder in folders:
        if not os.path.isdir(folder):
            continue
        for segment in ring_buffer.list_segments(folder):
            try:
                os.remove(segment.path)
                removed += 1
            except OSError:
                pass
        try:
            for name in os.listdir(folder):
                if name.startswith("save_") and name.endswith(".txt"):
                    os.remove(os.path.join(folder, name))
            os.rmdir(folder)
        except OSError:
            pass
    return removed
