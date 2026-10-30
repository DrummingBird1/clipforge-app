# entrypoints/web/routes/player.py
#
# גל 13: נגן התצוגה החיה - הדפדפן מנגן את קובץ המקור עצמו (עם קפיצות/גלילה
# בזכות Range), והעריכה (קרופ/צבע/שכבות/חיתוך) מצוירת מעליו ב-JS בזמן אמת. קובץ
# שהדפדפן לא יודע לנגן (HEVC בלי תמיכת חומרה, MKV מסוים...) מקבל "פרוקסי" -
# עותק קל ב-480p H.264 שנוצר פעם אחת ברקע ונשמר במטמון התצוגה המקדימה.

import hashlib
import os
import threading

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from utils.video import media_pool
from entrypoints import web_app as W

router = APIRouter()

_proxy_jobs = {}  # key -> {"state": "working"|"ready"|"error", "error": str}
_proxy_lock = threading.Lock()
PROXY_HEIGHT = 480


def _source_path(folder, file):
    """רק קובץ וידאו בשם (בלי נתיב) בתוך תיקייה קיימת - לא data/ ולא נתיב חופשי."""
    folder = str(folder or "")
    name = os.path.basename(str(file or ""))
    if not folder or not name or name != str(file) or not os.path.isdir(folder) or W._is_under_data_dir(folder):
        return None
    if not name.lower().endswith(W.EDITOR_VIDEO_EXTENSIONS):
        return None
    path = os.path.join(folder, name)
    return path if os.path.isfile(path) else None


def _proxy_key(path):
    stat = os.stat(path)
    return hashlib.sha1(f"{os.path.abspath(path)}|{stat.st_mtime}|{stat.st_size}".encode("utf-8")).hexdigest()[:16]


def _proxy_path(key):
    return os.path.join(W.PREVIEWS_DIR, f"proxy_{key}.mp4")


@router.get("/api/video_editor/source_stream")
def api_video_editor_source_stream(folder: str = "", file: str = ""):
    path = _source_path(folder, file)
    if not path:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    return FileResponse(path)


def _build_proxy(path, key):
    from utils.shared.ffmpeg_locator import get_ffmpeg_exe
    from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    target = _proxy_path(key)
    partial = target + ".part.mp4"
    cmd = [
        get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", path,
        "-vf", f"scale=-2:{PROXY_HEIGHT}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", partial,
    ]
    try:
        result = media_pool.run(cmd, lane="analysis", capture_output=True, text=True, errors="replace", timeout=3600, creationflags=NO_WINDOW_FLAGS)
        if result.returncode != 0 or not os.path.isfile(partial):
            raise RuntimeError((result.stderr or "ffmpeg נכשל").strip()[-300:])
        os.replace(partial, target)
        state = {"state": "ready"}
    except Exception as e:  # כל כשל = הודעה לממשק, לא קריסה של השרת
        try:
            os.remove(partial)  # safe: this module's own half-written proxy under workspace/.cache/previews/
        except OSError:
            pass
        state = {"state": "error", "error": str(e)}
    with _proxy_lock:
        _proxy_jobs[key] = state


@router.post("/api/video_editor/proxy")
def api_video_editor_proxy(payload: dict):
    """מתחיל (או מחזיר מצב) פרוקסי לקובץ שהדפדפן לא מצליח לנגן."""
    path = _source_path(payload.get("folder"), payload.get("file"))
    if not path:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    key = _proxy_key(path)
    url = "/api/video_editor/preview_media?name=" + f"proxy_{key}.mp4"
    if os.path.isfile(_proxy_path(key)):
        return {"state": "ready", "url": url}
    with _proxy_lock:
        job = _proxy_jobs.get(key)
        if job is None or job["state"] == "error" and payload.get("retry"):
            _proxy_jobs[key] = {"state": "working"}
            threading.Thread(target=_build_proxy, args=(path, key), daemon=True).start()
            job = _proxy_jobs[key]
    return {**job, "url": url if job["state"] == "ready" else None}
