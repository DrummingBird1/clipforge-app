# entrypoints/web/routes/pro.py
#
# גל 14 - כלים מקצועיים לעורך-העל:
#  * תור הרינדור: סדר/קדימות/הוצאה, השהיה (גם "עד שעה" - רינדור בלילה), והמתנה
#    כשהמחשב עסוק (משחק/סטרים/GPU בעומס).
#  * שגיאות עם פתרון בלחיצה (utils/video/editor_errors.py).
#  * חילופי-סצנה (להצמדה בציר-הזמן) ועוצמת-שמע לאורך הקובץ (LUFS, ebur128).

import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from utils.video import media_pool
from utils.video import video_editor_profiles as vep
from utils.shared.atomic_write import atomic_write_json
from utils.video.editor_errors import explain_error
from entrypoints import web_app as W

router = APIRouter()

DEFAULT_QUEUE_SETTINGS = {"wait_when_busy": False, "processes": ["obs64.exe", "Streamlabs OBS.exe"], "gpu_percent": None}
_resume_timer = {"timer": None, "at": None}
_analysis_lock = threading.Lock()


def _forbidden():
    return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)


def queue_settings_path():
    return os.path.join(os.path.dirname(vep.PROFILES_PATH), "render_queue.json")


def load_queue_settings():
    try:
        with open(queue_settings_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    settings = dict(DEFAULT_QUEUE_SETTINGS)
    if isinstance(data, dict):
        settings.update({k: data[k] for k in DEFAULT_QUEUE_SETTINGS if k in data})
    return settings


def busy_guard_for_run():
    """מה ש-worker.add_script_task מקבל כ-busy_guard, או None כשהאפשרות כבויה."""
    settings = load_queue_settings()
    if not settings.get("wait_when_busy"):
        return None
    return {"processes": settings.get("processes") or [], "gpu_percent": settings.get("gpu_percent")}


# --- תור הרינדור ---

@router.get("/api/render_queue")
def api_render_queue():
    queue = W.worker.heavy_queue
    running = None
    if W.worker.is_running:
        running = {"script": W._current_run.get("script_name"), "run_id": W._current_run.get("run_id"),
                   "started_at": W._current_run.get("started_at")}
    return {"paused": queue.paused, "resume_at": _resume_timer["at"], "running": running, "pending": queue.snapshot(),
            "settings": load_queue_settings()}


@router.post("/api/render_queue/move")
def api_render_queue_move(payload: dict, request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    direction = str(payload.get("direction") or "")
    if direction not in ("up", "down", "top", "bottom"):
        return JSONResponse({"error": "כיוון לא מוכר."}, status_code=400)
    return {"ok": W.worker.heavy_queue.move(int(payload.get("id") or 0), direction)}


@router.post("/api/render_queue/remove")
def api_render_queue_remove(payload: dict, request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    item = W.worker.heavy_queue.remove(int(payload.get("id") or 0))
    if item is None:
        return JSONResponse({"error": "המשימה כבר לא בתור."}, status_code=404)
    _func, _args, callback = item
    if callback:
        try:
            callback({"returncode": -1, "result": None, "removed_from_queue": True})
        except Exception:
            pass
    return {"ok": True}


def _cancel_resume_timer():
    timer = _resume_timer.get("timer")
    if timer:
        timer.cancel()
    _resume_timer.update(timer=None, at=None)


def _seconds_until(time_str):
    hour, minute = (int(part) for part in time_str.split(":"))
    now = _dt.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += _dt.timedelta(days=1)
    return (target - now).total_seconds(), target


@router.post("/api/render_queue/pause")
def api_render_queue_pause(payload: dict, request: Request):
    """paused: true/false. until: "HH:MM" - השהיה עד שעה (הלילה) ואז התור ממשיך לבד."""
    if not W._is_same_origin(request):
        return _forbidden()
    paused = bool(payload.get("paused"))
    until = str(payload.get("until") or "").strip()
    _cancel_resume_timer()
    W.worker.heavy_queue.set_paused(paused)
    if paused and until:
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", until):
            return JSONResponse({"error": "שעה לא תקינה (HH:MM)."}, status_code=400)
        seconds, target = _seconds_until(until)
        timer = threading.Timer(seconds, lambda: (W.worker.heavy_queue.set_paused(False), _resume_timer.update(timer=None, at=None)))
        timer.daemon = True
        timer.start()
        _resume_timer.update(timer=timer, at=target.isoformat(timespec="minutes"))
    return {"ok": True, "paused": paused, "resume_at": _resume_timer["at"]}


@router.post("/api/render_queue/settings")
def api_render_queue_settings(payload: dict, request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    settings = load_queue_settings()
    if "wait_when_busy" in payload:
        settings["wait_when_busy"] = bool(payload["wait_when_busy"])
    if "processes" in payload:
        raw = payload["processes"]
        items = raw.split(",") if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
        settings["processes"] = [str(p).strip()[:60] for p in items if str(p).strip()][:20]
    if "gpu_percent" in payload:
        try:
            value = payload["gpu_percent"]
            settings["gpu_percent"] = None if value in (None, "") else max(10, min(100, int(value)))
        except (TypeError, ValueError):
            pass
    atomic_write_json(queue_settings_path(), settings, ensure_ascii=False, indent=2)
    reason = W.worker.busy_reason({"processes": settings["processes"], "gpu_percent": settings["gpu_percent"]})
    return {"ok": True, "settings": settings, "busy_now": reason}


# --- שגיאות עם פתרון ---

@router.post("/api/video_editor/explain_error")
def api_video_editor_explain_error(payload: dict):
    return explain_error(str(payload.get("reason") or ""))


# --- ניתוח קובץ: חילופי-סצנה ועוצמת שמע ---

def _source(folder, file):
    folder, name = str(folder or ""), os.path.basename(str(file or ""))
    if not folder or not name or name != str(file) or not os.path.isdir(folder) or W._is_under_data_dir(folder):
        return None
    path = os.path.join(folder, name)
    return path if os.path.isfile(path) else None


def _cache_path(kind, path):
    stat = os.stat(path)
    key = hashlib.sha1(f"{kind}|{os.path.abspath(path)}|{stat.st_mtime}|{stat.st_size}".encode("utf-8")).hexdigest()[:16]
    return os.path.join(W.PREVIEWS_DIR, f"{kind}_{key}.json")


def _cached(kind, path, compute):
    cache = _cache_path(kind, path)
    try:
        with open(cache, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        pass
    with _analysis_lock:
        data = compute(path)
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    atomic_write_json(cache, data)
    return data


def _run_ffmpeg(args, timeout):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    return media_pool.run([get_ffmpeg_exe(), "-hide_banner", "-nostats", *args], lane="analysis", capture_output=True, text=True,
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW_FLAGS)


# קובץ ארוך מזה: זיהוי הסצנות מפענח רק פריימי מפתח (דיוק של שניות בודדות). פענוח מלא של הקלטת משחק של שעה ב-4K
# תפס את המעבד יותר מ-15 דק' - גם באמצע רינדור - ונפל על ה-timeout בלי מטמון, אז חזר בכל פתיחה (הרצה מקצה לקצה, 16.10)
SCENE_FULL_DECODE_MAX_SECONDS = 600


def compute_scene_cuts(path, threshold=0.3):
    from utils.media.ffprobe_cache import probe_video
    duration = (probe_video(path) or {}).get("duration") or 0
    keyframes_only = ["-skip_frame", "nokey"] if duration > SCENE_FULL_DECODE_MAX_SECONDS else []
    result = _run_ffmpeg([*keyframes_only, "-i", path, "-an", "-vf", f"scale=160:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"], timeout=900)
    times = [round(float(m), 2) for m in re.findall(r"pts_time:([0-9.]+)", result.stderr or "")]
    return {"cuts": times[:2000]}


def parse_ebur128(stderr):
    """ebur128 מדפיס שורה לכל 100ms: t: ... M: <momentary> S: <short-term> ... ובסוף I: <integrated>."""
    points = []
    for match in re.finditer(r"t:\s*([0-9.]+)\s+TARGET:[^\n]*?M:\s*(-?[0-9.]+|-inf)\s+S:\s*(-?[0-9.]+|-inf)", stderr or ""):
        t, m, s = match.groups()
        points.append([round(float(t), 2), None if "inf" in m else float(m), None if "inf" in s else float(s)])
    integrated = re.findall(r"I:\s*(-?[0-9.]+) LUFS", stderr or "")
    lra = re.findall(r"LRA:\s*([0-9.]+) LU", stderr or "")
    step = max(1, len(points) // 600)
    return {"points": points[::step], "integrated": float(integrated[-1]) if integrated else None, "lra": float(lra[-1]) if lra else None}


def compute_loudness(path):
    result = _run_ffmpeg(["-i", path, "-vn", "-af", "ebur128=framelog=info", "-f", "null", "-"], timeout=900)
    data = parse_ebur128(result.stderr)
    stderr = result.stderr or ""
    if not data["points"] and ("does not contain any stream" in stderr or "matches no streams" in stderr or "Output file does not contain" in stderr):
        data["no_audio"] = True
    return data


@router.get("/api/video_editor/scene_cuts")
def api_video_editor_scene_cuts(folder: str = "", file: str = ""):
    path = _source(folder, file)
    if not path:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    try:
        return _cached("scenes", path, compute_scene_cuts)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "זיהוי הסצנות לקח יותר מדי זמן."}, status_code=504)
    except OSError:  # אין ffmpeg - תשובה מסודרת במקום 500 עם traceback
        return JSONResponse({"error": "ffmpeg לא נמצא."}, status_code=503)


@router.get("/api/video_editor/loudness")
def api_video_editor_loudness(folder: str = "", file: str = ""):
    path = _source(folder, file)
    if not path:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    try:
        return _cached("loudness", path, compute_loudness)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "מדידת העוצמה לקחה יותר מדי זמן."}, status_code=504)
    except OSError:
        return JSONResponse({"error": "ffmpeg לא נמצא."}, status_code=503)
