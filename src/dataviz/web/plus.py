# dataviz/web/plus.py
#
# 27.10.2026: הצד של השרת ל-25 ההצעות של עורך הגרפים מהבדיקה הטכנית (25.10): תבניות שנשמרות מפרק קיים, דגלים למדינות
# (הורדה בלחיצה בלבד, מכתובת קבועה - כמו המפות המוכנות), מצב כרטיס המסך בזמן רינדור, ושימור הצופים מ-YouTube Analytics
# לציר הזמן של הפרק. data_dir כאן הוא של עורך הגרפים (data/ או data/dataviz/), כמו בשאר dataviz/web.

import json
import os
import re
import subprocess
import time
import urllib.request
from typing import Any, Callable, Dict, List, Mapping, Optional

from utils.shared import data_paths

TEMPLATE_RE = re.compile(r"^[\w\- ]{1,40}$")
MAX_TEMPLATES = 60
FLAG_URL = "https://flagcdn.com/w160/{code}.png"   # כתובת קבועה; ההורדה רק בלחיצה על "📥 הורד דגלים"
FLAG_MAX_BYTES = 200_000
_GPU: Dict[str, Any] = {"at": 0.0, "data": None}
GPU_CACHE_SECONDS = 2.0


# ---------- תבניות ----------
def templates_dir(data_dir: str) -> str:
    return os.path.join(data_dir, data_paths.DATAVIZ_TEMPLATES)


def _template_file(data_dir: str, title: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", title.strip()).strip("_") or "template"
    return os.path.join(templates_dir(data_dir), slug + ".json")


def save_template(data_dir: str, episode: str, title: str) -> Dict[str, Any]:
    """"💾 שמור כתבנית": העיצוב והקצב של הפרק (אותם מפתחות שפרק חדש יורש מפרק-תבנית - episodes.TEMPLATE_KEYS) נשמרים
    בשם משלהם. הפרק עצמו לא משתנה; תבנית באותו שם מתעדכנת."""
    from dataviz.config import ConfigError, load_config
    from dataviz.web import episodes as de
    title = str(title or "").strip()
    if not TEMPLATE_RE.match(title):
        raise de.EpisodeError("שם התבנית: עד 40 תווים - אותיות, ספרות, רווח, מקף וקו תחתון.")
    folder = de.episode_folder(data_dir, episode)
    if folder is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    try:
        config = load_config(os.path.join(folder, "config.yaml"), de.load_overrides_for_path(folder))
    except ConfigError as e:
        raise de.EpisodeError("הפרק לא תקין: " + "; ".join(e.errors[:3])) from e
    path = _template_file(data_dir, title)
    if not os.path.isfile(path) and len(list_templates(data_dir)) >= MAX_TEMPLATES:
        raise de.EpisodeError(f"עד {MAX_TEMPLATES} תבניות - מחק אחת קודם.")
    body: Dict[str, Any] = {}
    for key in de.TEMPLATE_KEYS:
        value = json.loads(json.dumps(config.get(key), default=str))
        if key == "video" and isinstance(value, dict):
            value.pop("output_name", None)
        if key == "logo" and isinstance(value, dict) and value.get("path"):
            value["path"] = os.path.join(folder, str(value["path"]))   # נתיב מלא - התבנית לא יושבת בתיקיית הפרק
        body[key] = value
    publish = config.get("publish") or {}
    body["publish"] = {k: publish[k] for k in ("enabled", "hashtags", "seo_ai", "thumbnail", "approval") if k in publish}
    os.makedirs(templates_dir(data_dir), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"title": title, "from": episode, "saved": time.strftime("%Y-%m-%d %H:%M"), "config": body}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    return {"ok": True, "id": "tpl:" + os.path.splitext(os.path.basename(path))[0], "title": title}


def list_templates(data_dir: str) -> List[Dict[str, Any]]:
    folder = templates_dir(data_dir)
    rows = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        rows.append({"id": "tpl:" + name[:-5], "title": str(data.get("title") or name[:-5]), "from": str(data.get("from") or ""),
                     "saved": str(data.get("saved") or "")})
    return rows


def load_template(data_dir: str, template_id: str) -> Optional[Dict[str, Any]]:
    """ה-config של תבנית שמורה ("tpl:<שם>"), או None."""
    name = str(template_id or "")[4:]
    if not str(template_id).startswith("tpl:") or not re.fullmatch(r"[\w\-]{1,60}", name):
        return None
    try:
        with open(os.path.join(templates_dir(data_dir), name + ".json"), encoding="utf-8") as f:
            return dict(json.load(f).get("config") or {})
    except (OSError, ValueError, AttributeError):
        return None


def delete_template(data_dir: str, template_id: str) -> bool:
    name = str(template_id or "")[4:]
    if not str(template_id).startswith("tpl:") or not re.fullmatch(r"[\w\-]{1,60}", name):
        return False
    path = os.path.join(templates_dir(data_dir), name + ".json")
    if not os.path.isfile(path):
        return False
    os.remove(path)   # safe: קובץ תבנית שהאפליקציה עצמה כתבה בתיקיית התבניות
    return True


# ---------- דגלים ----------
def flags_dir(data_dir: str) -> str:
    return os.path.join(data_dir, data_paths.DATAVIZ_FLAGS)


def flags_status(data_dir: str, entities: List[Any]) -> Dict[str, Any]:
    """אילו ישויות הן מדינות, ולאילו מהן כבר יש דגל בתיקייה."""
    from dataviz.countries import codes_for
    codes = codes_for(entities)
    folder = flags_dir(data_dir)
    have = {e for e, code in codes.items() if os.path.isfile(os.path.join(folder, code + ".png"))}
    return {"countries": [{"entity": e, "code": code, "have": e in have} for e, code in sorted(codes.items())],
            "missing": sorted({codes[e] for e in codes if e not in have})}


def download_flags(data_dir: str, codes: List[str], fetch: Optional[Callable[[str], bytes]] = None) -> Dict[str, Any]:
    """מוריד את הדגלים החסרים (PNG ברוחב 160) מ-FLAG_URL - רק קודים מהטבלה המקומית, וכל קובץ נבדק שהוא PNG.
    fetch - להחלפה בטסטים (בלי רשת)."""
    from dataviz.countries import COUNTRIES
    known = {c for c, *_ in COUNTRIES}
    folder = flags_dir(data_dir)
    os.makedirs(folder, exist_ok=True)

    def _fetch(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "ClipForge (dataviz flags)"})
        with urllib.request.urlopen(request, timeout=15) as response:   # noqa: S310 - כתובת קבועה ב-https
            return response.read(FLAG_MAX_BYTES + 1)

    fetch = fetch or _fetch
    saved, failed = [], []
    for code in sorted({str(c).lower() for c in codes if str(c).lower() in known}):
        path = os.path.join(folder, code + ".png")
        if os.path.isfile(path):
            continue
        try:
            data = fetch(FLAG_URL.format(code=code))
        except Exception:   # רשת / שרת - הדגל הזה נשאר חסר, השאר ממשיכים
            failed.append(code)
            continue
        if not data.startswith(b"\x89PNG") or len(data) > FLAG_MAX_BYTES:
            failed.append(code)
            continue
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
        saved.append(code)
    return {"saved": saved, "failed": failed}


# ---------- כרטיס המסך ----------
def gpu_status(runner: Callable[..., Any] = subprocess.run) -> Dict[str, Any]:
    """ניצול כרטיס המסך עכשיו (nvidia-smi): כללי, המקודד (NVENC), זיכרון וטמפרטורה. {"available": False} כשאין כרטיס
    של NVIDIA. נשמר GPU_CACHE_SECONDS - כמה לשוניות שמתעדכנות לא מריצות את nvidia-smi כל אחת בנפרד."""
    now = time.monotonic()
    if _GPU["data"] is not None and now - _GPU["at"] < GPU_CACHE_SECONDS:
        return _GPU["data"]
    data: Dict[str, Any] = {"available": False}
    try:
        result = runner(["nvidia-smi", "--query-gpu=name,utilization.gpu,utilization.encoder,memory.used,memory.total,temperature.gpu",
                         "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode == 0 and result.stdout.strip():
            name, gpu, enc, used, total, temp = [p.strip() for p in result.stdout.strip().splitlines()[0].split(",")][:6]
            number = lambda v: int(float(v)) if re.fullmatch(r"[\d.]+", v) else None   # noqa: E731 - "[N/A]" בכרטיסים מסוימים
            data = {"available": True, "name": name, "gpu": number(gpu), "encoder": number(enc), "memory_used": number(used),
                    "memory_total": number(total), "temperature": number(temp)}
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    _GPU.update({"at": now, "data": data})
    return data


# ---------- שימור צופים ----------
def video_id_for(package: Mapping[str, Any]) -> str:
    return str(((package.get("sent") or {}).get("youtube") or {}).get("video_id") or "")


def retention_points(rows: List[List[Any]]) -> List[Dict[str, Optional[float]]]:
    """שורות מ-YouTube Analytics ([elapsedVideoTimeRatio, audienceWatchRatio, relativeRetentionPerformance]) -> נקודות
    מסודרות לציר (0-1) עם כמה מהצופים עוד צופים (1 = כולם)."""
    points: List[Dict[str, Optional[float]]] = []
    for row in rows:
        try:
            points.append({"at": round(float(row[0]), 4), "watch": round(float(row[1]), 4),
                           "relative": round(float(row[2]), 4) if len(row) > 2 and row[2] is not None else None})
        except (TypeError, ValueError, IndexError):
            continue
    return sorted(points, key=lambda p: float(p["at"] or 0.0))


# ---------- הקלטה רציפה ----------
TRACK_MAX_BYTES = 40 * 1024 * 1024


def save_track(data_dir: str, episode: str, ext: str, data_base64: str, start: Any) -> Dict[str, Any]:
    """"🎙 הקלטה רציפה": קובץ חדש בתיקיית ההקלטות של הפרק (track_<זמן> - לא שם של תאריך, אז הוא לא נחשב הקלטה של
    אירוע), והפרק מפנה אליו (narration.track) מהשנייה start בסרטון. ההקלטה הקודמת נשארת בתיקייה."""
    import base64

    from dataviz.narration import RECORDING_EXT
    from dataviz.web import episodes as de
    from dataviz.web import library
    if de.episode_folder(data_dir, episode) is None:
        raise de.EpisodeError("הפרק לא נמצא.", status=404)
    ext = "." + str(ext or "").lower().lstrip(".")
    if ext not in RECORDING_EXT:
        raise de.EpisodeError("קובץ שמע לא נתמך.")
    try:
        seconds = max(0.0, min(36000.0, float(start)))
        raw = base64.b64decode(str(data_base64 or ""), validate=True)
    except (TypeError, ValueError):
        raise de.EpisodeError("ההקלטה לא הגיעה תקינה.") from None
    if not raw or len(raw) > TRACK_MAX_BYTES:
        raise de.EpisodeError("ההקלטה ריקה או גדולה מ-40MB.")
    folder = library.recordings_dir(data_dir, episode)
    os.makedirs(folder, exist_ok=True)
    name = library._write_new(folder, "track_" + time.strftime("%Y%m%d%H%M%S"), ext, raw)
    de.update_override_fields(data_dir, episode, {"narration.folder": os.path.abspath(folder), "narration.track": name,
                                                  "narration.track_start": round(seconds, 2)}, [])
    return {"ok": True, "name": name, "start": round(seconds, 2)}
