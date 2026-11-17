# entrypoints/web/routes/recording.py
#
# 16.11.2026 (ClipForge 2.0): מסך "הקלטה" - הקלטת מסך / משחק / קונסולה (כרטיס לכידה), replay buffer, ושליטה ב-OBS.
# הלוגיקה ב-utils/capture/ (manager.py). כאן: מנהל אחד לשרת, ההגדרות, ופעולות - כל POST בודק same-origin.
# קליפ replay שנשמר עובר ל-_on_clip_ready (השרשור האוטומטי של Rocket), כמו replay של OBS עד היום.
import atexit
import os
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from entrypoints import web_app as W

router = APIRouter()
_manager = None
_manager_lock = threading.Lock()


def _import_dir():
    configured = str(W._load_rocket_settings().get("input_dir") or "").strip()
    return configured or os.path.join(W.WORKSPACE_DIR, "imports")


def _on_clip(path, source):
    W._on_clip_ready({"script": "recording", "path": path, "source": source})


def _backend_args(codec, quality):
    from utils.media import encoders
    backend, _note = encoders.resolve_backend(encoders.load_setting(), codec,
                                              encoders.detect_backends(W.get_ffmpeg_exe(), creationflags=W.NO_WINDOW_FLAGS))
    args = encoders.codec_args(codec, backend, preset="p4", cq=quality)
    return args


def _obs_credentials():
    from utils.shared.secrets_vault import get_secret
    port = get_secret("OBS_WEBSOCKET_PORT") or "4455"
    return f"ws://localhost:{port}", get_secret("OBS_WEBSOCKET_PASSWORD") or ""


def get_manager():
    global _manager
    with _manager_lock:
        if _manager is None:
            from utils.capture.manager import RecorderManager
            from utils.shared import data_paths
            _manager = RecorderManager(data_paths.path(data_paths.RECORDING_SETTINGS), W.get_ffmpeg_exe(), W.WORKSPACE_DIR,
                                       _import_dir, on_clip=_on_clip, creationflags=W.NO_WINDOW_FLAGS,
                                       backend_args=_backend_args, obs_credentials=_obs_credentials)
            atexit.register(_manager.shutdown)
        return _manager


def _act(request: Request, action):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    from utils.capture.engine import CaptureError
    try:
        return action()
    except CaptureError as e:
        return JSONResponse({"error": str(e), "status": get_manager().status()}, status_code=400)


@router.get("/api/recording/status")
def api_recording_status():
    return get_manager().status()


@router.get("/api/recording/settings")
def api_recording_settings():
    from utils.capture import devices as dv
    from utils.capture import loopback
    return {"settings": get_manager().settings(), "loopback": loopback.available(),
            "consoles": [{"id": p.id, "label": p.label, "note": p.note} for p in dv.CONSOLE_PROFILES]}


@router.get("/api/recording/devices")
def api_recording_devices():
    """התקני DirectShow (כרטיסי לכידה, מצלמות, מיקרופונים). איטי (ffmpeg) - רק כשהמסך מבקש."""
    from utils.capture import devices as dv
    return dv.as_dicts(dv.list_devices(W.get_ffmpeg_exe(), creationflags=W.NO_WINDOW_FLAGS))


@router.post("/api/recording/settings")
async def api_recording_settings_save(request: Request):
    payload = await request.json()
    return _act(request, lambda: {"settings": get_manager().save_settings(payload if isinstance(payload, dict) else {})})


@router.post("/api/recording/record/start")
def api_recording_record_start(request: Request):
    return _act(request, lambda: get_manager().start_record())


@router.post("/api/recording/record/stop")
def api_recording_record_stop(request: Request):
    return _act(request, lambda: get_manager().stop_record())


@router.post("/api/recording/replay/start")
def api_recording_replay_start(request: Request):
    return _act(request, lambda: get_manager().start_replay())


@router.post("/api/recording/replay/save")
async def api_recording_replay_save(request: Request):
    payload = await request.json() if (request.headers.get("content-length") or "0") != "0" else {}
    seconds = payload.get("seconds") if isinstance(payload, dict) else None
    return _act(request, lambda: get_manager().save_replay(int(seconds) if seconds else None))


@router.post("/api/recording/replay/stop")
def api_recording_replay_stop(request: Request):
    return _act(request, lambda: get_manager().stop_replay())


@router.get("/api/recording/import/sources")
def api_recording_import_sources():
    """מאיפה אפשר לייבא עכשיו (תוכנות הקלטה, כונני USB / SD של קונסולות), עם מספר הקליפים החדשים בכל אחד."""
    return {"sources": get_manager().import_sources()}


@router.post("/api/recording/import")
async def api_recording_import(request: Request):
    payload = await request.json()
    preset = str((payload or {}).get("source") or "")
    return _act(request, lambda: get_manager().start_import(preset))


@router.get("/api/recording/obs/scenes")
def api_recording_obs_scenes():
    from utils.capture.engine import CaptureError
    try:
        return get_manager().scenes()
    except CaptureError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/api/recording/obs/scene")
async def api_recording_obs_scene(request: Request):
    payload = await request.json()
    scene = str((payload or {}).get("scene") or "")
    return _act(request, lambda: (get_manager().switch_scene(scene), get_manager().scenes())[1])
