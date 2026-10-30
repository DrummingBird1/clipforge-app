# entrypoints/web/routes/editor.py
#
# עורך-העל: תצוגה מקדימה, בדיקה, הערכה, ציר-זמן, תור, תמלול, ריצות ושליטה בקבצים.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import glob
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import tempfile
import threading
import time
import urllib.parse
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional

from utils.video.video_editor import compute_watermark_geometry, resolve_output_dimensions
from utils.video.video_editor_field_help import field_help_as_json_dict

from utils.video.editor_errors import annotate_manifest
from utils.video import media_pool
from entrypoints import web_app as W

router = APIRouter()


@router.get("/api/watermark_preview")
def api_watermark_preview(
    path: str = "", vertical: bool = False, position: str = "bottom-right", scale: float = 0.15,
    custom_x: Optional[float] = None, custom_y: Optional[float] = None,
):
    """גיאומטריית ה-watermark (גודל+מיקום, ביחס לרזולוציית הפלט האמיתית) - כדי
    שהדפדפן יוכל לצייר תצוגה מקדימה אמינה לפני שמריצים בפועל, בלי לנחש.
    custom_x/custom_y (item: גרירת watermark חופשית) - שניהם ביחד גוברים על
    position כליל, אותו עיקרון בדיוק כמו --watermark_x/--watermark_y."""
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ תמונה לא נמצא."}, status_code=400)
    try:
        from PIL import Image
        with Image.open(path) as img:
            wm_width, wm_height = img.size
    except Exception as e:
        return JSONResponse({"error": f"לא ניתן לקרוא את התמונה: {e}"}, status_code=400)

    if position not in W.WATERMARK_POSITIONS:
        return JSONResponse({"error": "מיקום watermark לא מוכר."}, status_code=400)

    custom_center_fraction = (custom_x, custom_y) if custom_x is not None and custom_y is not None else None
    output_width, output_height = resolve_output_dimensions(vertical)
    target_w, target_h, x, y = compute_watermark_geometry(
        output_width, output_height, wm_width, wm_height, position,
        scale_fraction=scale, custom_center_fraction=custom_center_fraction,
    )
    return {"output_width": output_width, "output_height": output_height, "target_w": target_w, "target_h": target_h, "x": x, "y": y}


@router.get("/api/watermark_image")
def api_watermark_image(path: str = ""):
    """משרת את קובץ תמונת ה-watermark עצמו כדי שהתצוגה המקדימה תוכל להציג אותו -
    אותה רמת גישה לדיסק שכבר קיימת דרך /api/browse (מקומי בלבד, מאחורי הטוקן)."""
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    if os.path.splitext(path)[1].lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        return JSONResponse({"error": "סוג קובץ לא נתמך."}, status_code=400)
    return FileResponse(path)


@router.get("/api/video_editor/field_help")
def api_video_editor_field_help():
    """מקור-אמת יחיד למונח-קצר+הסבר של כל הגדרה בעורך-העל (item: מקראה) -
    אותו utils/video/video_editor_field_help.py בדיוק שגם הדסקטופ (ui/settings_tab.py)
    משתמש בו ישירות (הוא Python גם שם) - כאן זו הדרך היחידה להעביר את זה
    ל-JS בצד הלקוח, שמשתמש בזה לבניית דיאלוג ה"📖 מקראה"."""
    return field_help_as_json_dict()


@router.post("/api/video_editor/reset_counter")
@W.limiter.limit("10/minute")
async def api_video_editor_reset_counter(request: Request):
    """item: מספור סרטונים - איפוס ידני ומפורש של המונה (data/video_editor_counter.txt)
    ל-value, נקרא מה-JS ברגע שהמשתמש בעצמו עורך את שדה "מספר התחלתי" בהגדרות
    (לא בכל ריצה - --number-start שנשלח ל-video_editor.py בזמן ריצה מתעלם
    כליל אם קובץ המונה כבר קיים, ראו utils/video/video_editor_counter.py, אז זו
    הדרך היחידה בפועל "לשנות את המספור ידנית" אחרי הריצה הראשונה)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        value = max(1, int(payload.get("value")))
    except (TypeError, ValueError):
        return JSONResponse({"error": "ערך לא תקין."}, status_code=400)
    W.save_video_editor_counter(value)
    return {"value": value}


@router.post("/api/video_editor/transcribe")
async def api_video_editor_transcribe(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    path, error = W._validated_caption_source(payload.get("path"))
    if error:
        return error
    language = str(payload.get("language") or "").strip() or None
    if language and not re.fullmatch(r"[a-z]{2,3}", language):
        return JSONResponse({"error": "קוד שפה לא תקין."}, status_code=400)
    model_size = str(payload.get("model") or "small")
    if model_size not in W._CHOICES["captions_model"]:
        return JSONResponse({"error": "מודל Whisper לא מוכר."}, status_code=400)
    job_id = secrets.token_hex(8)
    with W._transcribe_jobs_lock:
        if len(W._transcribe_jobs) >= W._TRANSCRIBE_JOBS_MAX:
            for old_id in list(W._transcribe_jobs)[: len(W._transcribe_jobs) - W._TRANSCRIBE_JOBS_MAX + 1]:
                W._transcribe_jobs.pop(old_id, None)
        W._transcribe_jobs[job_id] = {"status": "running", "path": path, "started_at": time.time()}
    threading.Thread(target=W._run_transcribe_job, args=(job_id, path, language, model_size), daemon=True).start()
    return {"job_id": job_id}


@router.get("/api/video_editor/transcribe_status")
def api_video_editor_transcribe_status(job_id: str = ""):
    with W._transcribe_jobs_lock:
        job = dict(W._transcribe_jobs.get(job_id) or {})
    if not job:
        return JSONResponse({"error": "משימת התמלול לא נמצאה."}, status_code=404)
    return job


@router.get("/api/video_editor/captions_edit")
def api_video_editor_captions_edit_get(path: str = ""):
    source, error = W._validated_caption_source(path)
    if error:
        return error
    from utils.media.captions import edited_captions_path, parse_srt
    srt_path = edited_captions_path(W.CAPTIONS_EDITS_DIR, source)
    if not os.path.isfile(srt_path):
        return {"exists": False, "segments": []}
    with open(srt_path, encoding="utf-8") as f:
        return {"exists": True, "segments": parse_srt(f.read()), "srt_path": srt_path}


@router.post("/api/video_editor/captions_edit")
async def api_video_editor_captions_edit_save(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    source, error = W._validated_caption_source(payload.get("path"))
    if error:
        return error
    segments = W._sanitize_caption_segments(payload.get("segments"))
    if segments is None:
        return JSONResponse({"error": "שורות התמלול לא תקינות (זמן התחלה/סיום או טקסט)."}, status_code=400)
    if not segments:
        return JSONResponse({"error": "אין אף שורת טקסט לשמירה."}, status_code=400)
    from utils.media.captions import edited_captions_path, write_srt
    os.makedirs(W.CAPTIONS_EDITS_DIR, exist_ok=True)
    srt_path = edited_captions_path(W.CAPTIONS_EDITS_DIR, source)
    tmp_path = srt_path + ".tmp"
    write_srt(segments, tmp_path)
    os.replace(tmp_path, srt_path)
    return {"saved": True, "count": len(segments), "srt_path": srt_path}


@router.delete("/api/video_editor/captions_edit")
def api_video_editor_captions_edit_delete(request: Request, path: str = ""):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    source, error = W._validated_caption_source(path)
    if error:
        return error
    from utils.media.captions import edited_captions_path
    srt_path = edited_captions_path(W.CAPTIONS_EDITS_DIR, source)
    existed = os.path.isfile(srt_path)
    if existed:
        os.remove(srt_path)
    return {"deleted": existed}


# item 85: "זהה הייליטס" - שיאי עוצמת-שמע (אותו אלגוריתם כמו story_cutter, בלי AI)
# -> טווחים להסרה, שהממשק ממלא ל"חיתוך כמה טווחים". def רגיל = thread pool.
@router.post("/api/video_editor/detect_highlights")
def api_video_editor_detect_highlights(payload: dict):
    from utils.video.highlight_detect import detect_highlight_ranges
    folder = str(payload.get("folder", ""))
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "בחר תיקיית קלט קודם."}, status_code=400)
    filename = W._pick_editor_file(folder, payload.get("file"))
    if not filename:
        return JSONResponse({"error": "לא נמצא קובץ וידאו בתיקייה (או שהקובץ שנבחר לא קיים בה)."}, status_code=400)
    threshold = W._clamped_float(payload.get("threshold_db"), 3.0, 40.0) or 18.0
    before = W._clamped_float(payload.get("before"), 0.0, 120.0)
    after = W._clamped_float(payload.get("after"), 0.0, 60.0)
    min_gap = W._clamped_float(payload.get("min_gap"), 1.0, 600.0) or 15.0
    try:
        result = detect_highlight_ranges(
            os.path.join(folder, filename), W.get_ffmpeg_exe(), threshold_offset_db=threshold,
            before=20.0 if before is None else before, after=5.0 if after is None else after, min_gap_seconds=min_gap,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:  # ffmpeg חסר/קובץ פגום
        return JSONResponse({"error": f"זיהוי ההייליטס נכשל: {e}"}, status_code=500)
    return {"file": filename, **result}


# item: אימות נתיב חי - מטא-דאטה בלבד (קיים/קובץ/תיקייה/גודל/סיומת) לנתיב
# שהמשתמש מקליד בשדה-נתיב בעורך, כדי לסמן "הקובץ לא נמצא" לפני שמריצים.
# אותה רמת גישה לדיסק שכבר קיימת דרך /api/browse (מקומי, מאחורי הטוקן).
@router.get("/api/path_info")
def api_path_info(path: str = ""):
    path = path.strip().strip('"')
    if not path:
        return {"exists": False, "is_file": False, "is_dir": False, "size": None, "ext": ""}
    exists = os.path.exists(path)
    is_file = os.path.isfile(path)
    return {
        "exists": exists, "is_file": is_file, "is_dir": os.path.isdir(path),
        "size": os.path.getsize(path) if is_file else None,
        "ext": os.path.splitext(path)[1].lower(),
    }


@router.get("/api/system_fonts")
def api_system_fonts():
    # single-flight: כמה טאבים שנפתחים יחד לא סורקים את כל תיקיית הגופנים
    # במקביל (כל סריקה טוענת מאות קבצים ב-FreeType ומחזיקה את ה-GIL בינתיים).
    with W._system_fonts_lock:
        if W._system_fonts_cache is None:
            W._system_fonts_cache = W.list_system_font_families()
    return {"fonts": W._system_fonts_cache}


# item: סליידר חיתוך מקושר למשך הקובץ הראשון בתור (וגם שורות-תור עשירות) -
# probe_video (ffprobe ממוטמן, אותה פונקציה בדיוק שהרינדור עצמו משתמש בה).
@router.get("/api/video_editor/probe")
def api_video_editor_probe(path: str = ""):
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    from utils.media.ffprobe_cache import probe_video
    from utils.video.video_editor import is_hdr_source
    info = probe_video(path)
    return {
        "duration": info.get("duration"), "width": info.get("width"), "height": info.get("height"),
        "fps": info.get("fps"), "has_audio": info.get("has_audio"), "hdr": is_hdr_source(info.get("color_transfer")),
        "size": os.path.getsize(path), "mtime": os.path.getmtime(path),
    }


# item 40+41: תצוגה מקדימה מלאה (פריים עם קרופ/LUT/טקסט/watermark/כתובית-לדוגמה)
# + פריים המקור באותה נקודה ל"לפני/אחרי". רץ דרך video_editor.py עצמו
# (--preview-frame) - אותה שרשרת פילטרים *בדיוק* כמו הרינדור האמיתי, לא
# הדמיה מקבילה בדפדפן שיכולה להתפצל ממנו.
@router.post("/api/video_editor/preview_frame")
@W.limiter.limit("30/minute")
def api_video_editor_preview_frame(payload: dict, request: Request):
    folder = str(payload.get("folder", ""))
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "בחר תיקיית קלט קודם."}, status_code=400)
    if payload.get("concat_mode"):
        return JSONResponse({"error": "תצוגה מקדימה לא זמינה במצב איחוד קטעים (אין שרשרת-עריכה לקובץ בודד)."}, status_code=400)
    filename = W._pick_editor_file(folder, payload.get("file"))
    if not filename:
        return JSONResponse({"error": "לא נמצא קובץ וידאו בתיקייה (או שהקובץ שנבחר לא קיים בה)."}, status_code=400)
    seconds = W.parse_time_seconds(payload.get("time")) or 0.0
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    W._cleanup_old_previews()
    stamp = f"{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    after_path = os.path.join(W.PREVIEWS_DIR, f"after_{stamp}.png")
    before_path = os.path.join(W.PREVIEWS_DIR, f"before_{stamp}.png")
    payload = W._effective_editor_payload(payload, payload.get("preview_target"), pick_one_target=True)
    preview = W._preview_payload(payload)
    overrides = W.sanitize_batch_overrides(payload.get("batch_overrides"))
    overrides_path = W._write_batch_overrides_file(overrides) if overrides else None
    args = W._build_extra_args("video_editor.py", preview, batch_overrides_path=overrides_path, layers_path=W._write_layers_file(preview))
    args += [
        "--only-files", json.dumps([filename], ensure_ascii=False),
        "--preview-frame", W._fmt_num(seconds), "--preview-frame-out", after_path, "--preview-frame-before-out", before_path,
    ]
    try:
        result = W._run_editor_subprocess(folder, args, timeout=150)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "התצוגה המקדימה לקחה יותר מדי זמן (מעל 2.5 דקות)."}, status_code=504)
    info = None
    for line in result.stdout.splitlines():
        if line.startswith("PREVIEW_FRAME: "):
            try:
                info = json.loads(line[len("PREVIEW_FRAME: "):])
            except ValueError:
                info = None
    if result.returncode != 0 or not info or not os.path.exists(after_path):
        tail = "\n".join((result.stdout + "\n" + result.stderr).strip().splitlines()[-12:])
        return JSONResponse({"error": "יצירת התצוגה המקדימה נכשלה.", "detail": tail}, status_code=500)
    info["file"] = filename
    info["after_url"] = "/api/watermark_image?path=" + urllib.parse.quote(after_path)
    info["before_url"] = "/api/watermark_image?path=" + urllib.parse.quote(before_path) if os.path.exists(before_path) else None
    return info


# גל 10: קטע תצוגה מקדימה (3-5 שניות עם שמע) - אותה שרשרת בדיוק כמו
# preview_frame (video_editor.py --preview-frame + --preview-clip-seconds), וגם
# קטע מקור מקביל באותן מידות ל"לפני/אחרי" עם מחיצה נגררת על וידאו מתנגן.
@router.post("/api/video_editor/preview_clip")
@W.limiter.limit("12/minute")
def api_video_editor_preview_clip(payload: dict, request: Request):
    folder = str(payload.get("folder", ""))
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "בחר תיקיית קלט קודם."}, status_code=400)
    if payload.get("concat_mode"):
        return JSONResponse({"error": "תצוגה מקדימה לא זמינה במצב איחוד קטעים (אין שרשרת-עריכה לקובץ בודד)."}, status_code=400)
    filename = W._pick_editor_file(folder, payload.get("file"))
    if not filename:
        return JSONResponse({"error": "לא נמצא קובץ וידאו בתיקייה (או שהקובץ שנבחר לא קיים בה)."}, status_code=400)
    seconds = W.parse_time_seconds(payload.get("time")) or 0.0
    try:
        clip_seconds = min(10.0, max(1.0, float(payload.get("clip_seconds") or 4)))
    except (TypeError, ValueError):
        clip_seconds = 4.0
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    W._cleanup_old_previews()
    stamp = f"{int(time.time() * 1000)}_{secrets.token_hex(3)}"
    after_name, before_name = f"clip_after_{stamp}.mp4", f"clip_before_{stamp}.mp4"
    after_path, before_path = os.path.join(W.PREVIEWS_DIR, after_name), os.path.join(W.PREVIEWS_DIR, before_name)
    payload = W._effective_editor_payload(payload, payload.get("preview_target"), pick_one_target=True)
    preview = W._preview_payload(payload)
    overrides = W.sanitize_batch_overrides(payload.get("batch_overrides"))
    overrides_path = W._write_batch_overrides_file(overrides) if overrides else None
    args = W._build_extra_args("video_editor.py", preview, batch_overrides_path=overrides_path, layers_path=W._write_layers_file(preview))
    args += [
        "--only-files", json.dumps([filename], ensure_ascii=False),
        "--preview-frame", W._fmt_num(seconds), "--preview-clip-seconds", W._fmt_num(clip_seconds),
        "--preview-frame-out", after_path, "--preview-frame-before-out", before_path,
    ]
    try:
        result = W._run_editor_subprocess(folder, args, timeout=300)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "קטע התצוגה המקדימה לקח יותר מדי זמן (מעל 5 דקות)."}, status_code=504)
    info = None
    for line in result.stdout.splitlines():
        if line.startswith("PREVIEW_FRAME: "):
            try:
                info = json.loads(line[len("PREVIEW_FRAME: "):])
            except ValueError:
                info = None
    if result.returncode != 0 or not info or not os.path.exists(after_path):
        tail = "\n".join((result.stdout + "\n" + result.stderr).strip().splitlines()[-12:])
        return JSONResponse({"error": "יצירת קטע התצוגה המקדימה נכשלה.", "detail": tail}, status_code=500)
    info["file"] = filename
    info["after_url"] = "/api/video_editor/preview_media?name=" + urllib.parse.quote(after_name)
    info["before_url"] = "/api/video_editor/preview_media?name=" + urllib.parse.quote(before_name) if os.path.exists(before_path) else None
    return info


@router.get("/api/video_editor/preview_media")
def api_video_editor_preview_media(name: str = ""):
    """משרת רק קבצים שהאפליקציה עצמה יצרה תחת workspace/.cache/previews/ (לפי שם בלבד,
    בלי נתיב) - קטעי ה-MP4 של התצוגה המקדימה (גל 10)."""
    base = os.path.basename(name or "")
    if not base or base != name or not base.lower().endswith((".mp4", ".png", ".jpg")):
        return JSONResponse({"error": "שם קובץ לא תקין."}, status_code=400)
    path = os.path.join(W.PREVIEWS_DIR, base)
    if not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    return FileResponse(path)


# item 50: פריים מקור גולמי (ברזולוציית-מקור יחסית, מוקטן להעברה) - בחירת אזור
# מחיקת-watermark בגרירת מלבן נעשית בשברים (0-1) של המקור, בלי תלות בגודל התצוגה.
@router.get("/api/video_editor/source_frame")
def api_video_editor_source_frame(path: str = "", t: str = "0"):
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    from utils.media.ffprobe_cache import probe_video
    info = probe_video(path)
    seconds = min(W.parse_time_seconds(t) or 0.0, max(0.0, (info.get("duration") or 0) - 0.05))
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    W._cleanup_old_previews()
    out_path = os.path.join(W.PREVIEWS_DIR, f"source_{int(time.time() * 1000)}_{secrets.token_hex(3)}.png")
    cmd = [W.get_ffmpeg_exe(), "-y", "-ss", f"{seconds:.3f}", "-i", path, "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", out_path]
    result = media_pool.run(cmd, lane="interactive", capture_output=True, text=True, timeout=60, creationflags=W.NO_WINDOW_FLAGS)
    if result.returncode != 0 or not os.path.exists(out_path):
        return JSONResponse({"error": "חילוץ הפריים נכשל.", "detail": result.stderr[-400:]}, status_code=500)
    return {"url": "/api/watermark_image?path=" + urllib.parse.quote(out_path), "width": info.get("width"), "height": info.get("height"), "time": seconds}


@router.get("/api/video_editor/timeline")
def api_video_editor_timeline(path: str = "", count: int = 12):
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    count = max(2, min(40, int(count)))
    from utils.media.ffprobe_cache import probe_video
    duration = probe_video(path).get("duration") or 0
    if not duration:
        return JSONResponse({"error": "לא הצלחתי לקרוא את אורך הקובץ."}, status_code=400)
    stat = os.stat(path)
    key = hashlib.sha1(f"{os.path.realpath(path)}|{stat.st_size}|{stat.st_mtime_ns}|{count}".encode("utf-8")).hexdigest()[:20]
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    out_path = os.path.join(W.PREVIEWS_DIR, f"timeline_{key}.jpg")
    with media_pool.single_flight(out_path):
        if not os.path.exists(out_path):
            _build_timeline_strip(path, duration, count, out_path)
    return {"url": "/api/watermark_image?path=" + urllib.parse.quote(out_path), "duration": duration, "count": count}


def _build_timeline_strip(path, duration, count, out_path):
    """פס ה-thumbnails של ציר-הזמן - פריים לכל משבצת, כל ffmpeg במקום משלו בנתיב interactive."""
    from io import BytesIO
    from PIL import Image
    frames = []
    for i in range(count):
        t = (i + 0.5) * duration / count
        cmd = [W.get_ffmpeg_exe(), "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
               "-vf", f"scale={W.TIMELINE_THUMB_WIDTH}:-2", "-f", "image2pipe", "-vcodec", "png", "-"]
        result = media_pool.run(cmd, lane="interactive", capture_output=True, timeout=30, creationflags=W.NO_WINDOW_FLAGS)
        if result.returncode == 0 and result.stdout:
            try:
                frames.append(Image.open(BytesIO(result.stdout)).convert("RGB"))
                continue
            except Exception:
                pass
        frames.append(None)
    height = max((f.height for f in frames if f is not None), default=90)
    strip = Image.new("RGB", (W.TIMELINE_THUMB_WIDTH * count, height), (20, 20, 24))
    for i, frame in enumerate(frames):
        if frame is not None:
            strip.paste(frame, (i * W.TIMELINE_THUMB_WIDTH, 0))
    strip.save(out_path, "JPEG", quality=80)


# item 44: בדיקת הגדרות (validate-only) עם שגיאה ליד השדה - בדיקות סטטיות
# מיידיות (קבצים/פורמטים) + ריצת --validate-only אמיתית על הקובץ הראשון, כשכל
# שגיאת ffmpeg מתורגמת לשדה שכנראה גרם לה.
@router.post("/api/video_editor/validate")
@W.limiter.limit("20/minute")
def api_video_editor_validate(payload: dict, request: Request):
    from utils.video.video_editor_validation import map_ffmpeg_error_to_field, parse_validate_output, validate_fields
    known_fonts = W._system_fonts_cache if W._system_fonts_cache is not None else None
    field_errors = validate_fields(payload, known_fonts=known_fonts)
    general = []
    folder = str(payload.get("folder", ""))
    ffmpeg_checked = False
    hard_static_errors = {k: v for k, v in field_errors.items() if not v.startswith("⚠️")}
    if not folder or not os.path.isdir(folder):
        general.append("בחר תיקיית קלט כדי לבדוק גם את שרשרת הפילטרים מול ffmpeg.")
    elif payload.get("concat_mode"):
        general.append("במצב איחוד קטעים נבדקות רק ההגדרות הסטטיות.")
    elif hard_static_errors:
        general.append("תקן קודם את השגיאות המסומנות - בדיקת ffmpeg לא הורצה.")
    else:
        filename = W._pick_editor_file(folder, payload.get("file"))
        if not filename:
            general.append("אין קובץ וידאו בתיקייה לבדיקת שרשרת הפילטרים.")
        else:
            effective = W._effective_editor_payload(payload, payload.get("preview_target"), pick_one_target=True)
            validate_payload = {**W._preview_payload(effective), "validate_only": True}
            overrides_path = W._write_batch_overrides_file(effective["batch_overrides"]) if effective.get("batch_overrides") else None
            args = W._build_extra_args("video_editor.py", validate_payload, batch_overrides_path=overrides_path,
                                       layers_path=W._write_layers_file(validate_payload))
            args += ["--only-files", json.dumps([filename], ensure_ascii=False)]
            try:
                result = W._run_editor_subprocess(folder, args, timeout=120)
                ffmpeg_checked = True
                for item in parse_validate_output(result.stdout):
                    if item["status"] != "invalid":
                        continue
                    field = map_ffmpeg_error_to_field(item["detail"], payload)
                    tail_line = [ln for ln in item["detail"].splitlines() if ln.strip()][-1:] or [item["detail"]]
                    message = f"ffmpeg דחה את השרשרת: {tail_line[0][:220]}"
                    if field and field not in field_errors:
                        field_errors[field] = message
                    else:
                        general.append(message)
                if result.returncode != 0 and not parse_validate_output(result.stdout):
                    general.append("הבדיקה נכשלה: " + "\n".join((result.stdout + result.stderr).strip().splitlines()[-4:]))
            except subprocess.TimeoutExpired:
                general.append("בדיקת ffmpeg לקחה יותר מדי זמן.")
    return {
        "valid": not {k: v for k, v in field_errors.items() if not v.startswith("⚠️")} and not general,
        "field_errors": field_errors, "general": general, "ffmpeg_checked": ffmpeg_checked,
    }


# item 46: הערכת משך + גודל פלט לכל קובץ (לא רק ETA) - probe ממוטמן לכל קובץ
# בתור/תיקייה (עד 300), הערכה טהורה ב-utils/video/video_editor_estimate.py.
@router.post("/api/video_editor/estimate")
def api_video_editor_estimate(payload: dict):
    from utils.media.ffprobe_cache import probe_video
    from utils.video.video_editor_estimate import estimate_output_mb, estimate_output_seconds
    folder = str(payload.get("folder", ""))
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "בחר תיקיית קלט קודם."}, status_code=400)
    names = W._editor_root_videos(folder)
    only = payload.get("only_files")
    if isinstance(only, list):
        wanted = [str(n) for n in only]
        names = [n for n in wanted if n in set(names)]
    rows = []
    payload = W._effective_editor_payload(payload, payload.get("preview_target"), pick_one_target=True)
    overrides = W.sanitize_batch_overrides(payload.get("batch_overrides"))
    # גל 7ב: intro/outro מתווספים לכל פלט - האורך שלהם נמדד פעם אחת
    bumper_seconds = 0.0
    for key in ("intro_path", "outro_path"):
        bumper = str(payload.get(key) or "").strip()
        if bumper and os.path.isfile(bumper):
            bumper_seconds += probe_video(bumper).get("duration") or 0.0
    payload = {**payload, "_bumper_seconds": bumper_seconds}
    for name in names[:300]:
        info = probe_video(os.path.join(folder, name))
        source_seconds = info.get("duration") or 0.0
        file_opts = {**payload, **overrides.get(name, {})}
        if "remove_ranges" in overrides.get(name, {}):
            # עריכת קליפ עם טווחים קובעת את כל הזמן של הקובץ (כמו ברנדרר) - בלי חיתוך/שקט של המתכון
            file_opts.update(trim_start=0, trim_duration=None, trim_silence=False)
        seconds, exact = estimate_output_seconds(source_seconds, file_opts)
        size_mb = estimate_output_mb(seconds, info.get("width"), info.get("height"), info.get("fps"), file_opts)
        rows.append({"file": name, "source_seconds": round(source_seconds, 1), "output_seconds": round(seconds, 1), "exact": exact, "output_mb": size_mb})
    return {
        "files": rows, "truncated": len(names) > 300,
        "total_output_seconds": round(sum(r["output_seconds"] for r in rows), 1),
        "total_output_mb": round(sum(r["output_mb"] for r in rows), 1),
    }


# item 48: פאנל תוצאות בסוף ריצה - video_editor.py כותב run-manifest (קובץ לכל
# ריצה, כל קובץ עם סטטוס/סיבה/זמן/גודל/נתיב-פלט) ומדפיס את נתיבו ב-RESULT.
@router.get("/api/video_editor/run_manifest")
def api_video_editor_run_manifest(path: str = ""):
    real_path = os.path.realpath(path) if path else ""
    real_dir = os.path.realpath(W.RUN_MANIFESTS_DIR)
    if not real_path.startswith(real_dir + os.sep) or not os.path.isfile(real_path):
        return JSONResponse({"error": "קובץ תוצאות לא נמצא."}, status_code=404)
    with open(real_path, encoding="utf-8") as f:
        return annotate_manifest(json.load(f))  # גל 14: הסבר + פעולות תיקון לכל קובץ שנכשל


@router.get("/api/video_editor/latest_manifest")
def api_video_editor_latest_manifest(folder: str = "", quiet: bool = False):
    """ה-manifest האחרון (אופציונלית: של תיקיית-קלט מסוימת) - לשחזור פאנל
    התוצאות אחרי רענון-דף, ולסטטוס ✅/❌ בשורות התור (item 54). quiet: הסטטוס בתור נטען בכל פתיחת תיקייה -
    "אין עדיין ריצה" הוא מצב רגיל שם, לא שגיאה (קודם: 404 אדום בקונסול בכל תיקייה חדשה)."""
    candidates = sorted(glob.glob(os.path.join(W.RUN_MANIFESTS_DIR, "*.json")), key=os.path.getmtime, reverse=True)
    for candidate in candidates[:200]:
        try:
            with open(candidate, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not folder or os.path.normcase(os.path.normpath(data.get("input_dir") or "")) == os.path.normcase(os.path.normpath(folder)):
            data["manifest_path"] = candidate
            return annotate_manifest(data)
    if quiet:
        return {"files": [], "none": True}
    return JSONResponse({"error": "אין עדיין תוצאות ריצה."}, status_code=404)


@router.get("/api/video_editor/output_thumbnail")
def api_video_editor_output_thumbnail(path: str = ""):
    if not path or not os.path.isfile(path) or not W._is_under_workspace(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    stat = os.stat(path)
    key = hashlib.sha1(f"{os.path.realpath(path)}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")).hexdigest()[:20]
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    thumb = os.path.join(W.PREVIEWS_DIR, f"thumb_{key}.jpg")
    with media_pool.single_flight(thumb):
        if not os.path.exists(thumb):
            cmd = [W.get_ffmpeg_exe(), "-v", "error", "-ss", "1", "-i", path, "-frames:v", "1", "-vf", "scale=240:-2", thumb]
            result = media_pool.run(cmd, capture_output=True, timeout=30, creationflags=W.NO_WINDOW_FLAGS)
            if result.returncode != 0 or not os.path.exists(thumb):
                cmd[3] = "0"
                media_pool.run(cmd, capture_output=True, timeout=30, creationflags=W.NO_WINDOW_FLAGS)
    if not os.path.exists(thumb):
        return JSONResponse({"error": "יצירת תמונה ממוזערת נכשלה."}, status_code=500)
    return FileResponse(thumb, media_type="image/jpeg")


@router.get("/api/video_editor/stream")
def api_video_editor_stream(path: str = ""):
    """נגן לתוצרי הרינדור - רק מתוך workspace/ (בניגוד ל-/api/download הכללי)."""
    if not path or not os.path.isfile(path) or not W._is_under_workspace(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    return FileResponse(path)


# item 51: שורות תור עשירות - probe לקבוצת קבצים בבקשה אחת (הדפדפן שולח בנתחים
# קטנים ומעדכן שורות בהדרגה, כך שתור של מאות קבצים לא "נתקע" על ה-probe הראשון).
@router.post("/api/video_editor/probe_batch")
def api_video_editor_probe_batch(payload: dict):
    from utils.media.ffprobe_cache import probe_video
    from utils.video.video_editor import is_hdr_source
    folder = str(payload.get("folder", ""))
    if not folder or not os.path.isdir(folder) or W._is_under_data_dir(folder):
        return JSONResponse({"error": "תיקייה לא תקינה."}, status_code=400)
    result = {}
    for raw_name in (payload.get("names") or [])[:40]:
        name = os.path.basename(str(raw_name))
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            continue
        info = probe_video(path)
        stat = os.stat(path)
        result[name] = {
            "duration": info.get("duration"), "width": info.get("width"), "height": info.get("height"),
            "fps": info.get("fps"), "hdr": is_hdr_source(info.get("color_transfer")), "has_audio": info.get("has_audio"),
            "size": stat.st_size, "mtime": stat.st_mtime,
        }
    return {"files": result}


@router.get("/api/video_editor/file_thumbnail")
def api_video_editor_file_thumbnail(path: str = ""):
    """תמונה ממוזערת לקובץ מקור בתור (item 51) - ממוטמנת לפי נתיב+גודל+mtime."""
    if not path or not os.path.isfile(path) or W._is_under_data_dir(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=404)
    stat = os.stat(path)
    key = hashlib.sha1(f"{os.path.realpath(path)}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")).hexdigest()[:20]
    os.makedirs(W.PREVIEWS_DIR, exist_ok=True)
    thumb = os.path.join(W.PREVIEWS_DIR, f"src_{key}.jpg")
    # גל 24: אותה תמונה מהתור, ממסך העבודות ומהבית - ffmpeg אחד, והשאר מחכים לו
    with media_pool.single_flight(thumb):
        if not os.path.exists(thumb):
            for seek in ("1", "0"):
                cmd = [W.get_ffmpeg_exe(), "-v", "error", "-ss", seek, "-i", path, "-frames:v", "1", "-vf", "scale=128:-2", thumb]
                try:
                    media_pool.run(cmd, capture_output=True, timeout=30, creationflags=W.NO_WINDOW_FLAGS)
                except (OSError, subprocess.TimeoutExpired):  # אין ffmpeg / קובץ תקוע - בלי תמונה, לא 500 לא מטופל
                    break
                if os.path.exists(thumb):
                    break
    if not os.path.exists(thumb):
        return JSONResponse({"error": "יצירת תמונה ממוזערת נכשלה."}, status_code=500)
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


# item 53: גרירת קבצים מהמערכת לתוך התור - דפדפן לא חושף נתיב מלא של קובץ
# שנגרר (אבטחה), אז הקובץ עצמו מועלה לתיקיית הקלט הנבחרת (העתקה, המקור לא
# נגוע). גוף הבקשה הוא תוכן הקובץ הגולמי (בלי multipart), נכתב בהזרמה לקובץ
# זמני ומועבר לשמו הסופי רק בסיום מוצלח. לא דורס קובץ קיים באותו שם.
EDITOR_ASSET_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".png", ".jpg", ".jpeg", ".webp", ".gif",
                           ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac")


@router.post("/api/video_editor/upload_asset")
@W.limiter.limit("60/minute")
async def api_video_editor_upload_asset(request: Request, folder: str = "", name: str = ""):
    """גל 29: קובץ שנגרר מהמחשב לנגן או לציר-הזמן (תמונה ללוגו, וידאו ל-B-roll, שמע לפס-קול).
    הדפדפן לא חושף נתיב של קובץ מקומי, אז הוא מועתק לתיקיית הנכסים של הפרויקט ומוחזר הנתיב."""
    from utils.video.editor_projects import assets_dir
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    safe_name = os.path.basename(name.strip())
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "בחר קודם תיקייה (פרויקט)."}, status_code=400)
    if not safe_name or not safe_name.lower().endswith(EDITOR_ASSET_EXTENSIONS):
        return JSONResponse({"error": "רק וידאו, תמונה או שמע."}, status_code=400)
    directory = assets_dir(folder)
    os.makedirs(directory, exist_ok=True)
    stem, ext = os.path.splitext(safe_name)
    target = os.path.join(directory, safe_name)
    counter = 2
    while os.path.exists(target):
        target = os.path.join(directory, f"{stem}_{counter}{ext}")
        counter += 1
    fd, temp_path = tempfile.mkstemp(prefix=".upload_", suffix=".part", dir=directory)
    written = 0
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                written += len(chunk)
        if written == 0:
            raise ValueError("הקובץ ריק")
        os.replace(temp_path, target)  # safe: this upload's own temp file -> a new name in the project's assets folder (never overwrites)
    except Exception as e:
        try:
            os.remove(temp_path)  # safe: this request's own partial upload temp file
        except OSError:
            pass
        return JSONResponse({"error": f"ההעלאה נכשלה: {e}"}, status_code=400)
    W.audit_log.record_action("web", "video_editor_upload_asset", details=target, username=request.client.host if request.client else None)
    return {"ok": True, "path": target, "name": os.path.basename(target), "size": written}


@router.post("/api/video_editor/upload")
@W.limiter.limit("120/minute")
async def api_video_editor_upload(request: Request, folder: str = "", name: str = ""):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    safe_name = os.path.basename(name.strip())
    if not folder or not os.path.isdir(folder) or W._is_under_data_dir(folder):
        return JSONResponse({"error": "תיקיית יעד לא תקינה."}, status_code=400)
    if not safe_name or not safe_name.lower().endswith(W.EDITOR_VIDEO_EXTENSIONS):
        return JSONResponse({"error": "רק קבצי וידאו (mp4/mkv/mov/avi/webm) נתמכים."}, status_code=400)
    target = os.path.join(folder, safe_name)
    if os.path.exists(target):
        return JSONResponse({"error": f"כבר קיים קובץ בשם {safe_name} בתיקייה - לא נדרס.", "exists": True}, status_code=409)
    fd, temp_path = tempfile.mkstemp(prefix=".upload_", suffix=".part", dir=folder)
    written = 0
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                written += len(chunk)
        if written == 0:
            raise ValueError("הקובץ ריק")
        os.replace(temp_path, target)  # safe: moves this upload's own temp file to its final name inside the chosen input folder; target was verified not to exist
    except Exception as e:
        try:
            os.remove(temp_path)  # safe: this request's own partial upload temp file
        except OSError:
            pass
        return JSONResponse({"error": f"ההעלאה נכשלה: {e}"}, status_code=400)
    W.audit_log.record_action("web", "video_editor_upload", details=target, username=request.client.host if request.client else None)
    return {"ok": True, "name": safe_name, "size": written}


# item: תצוגת "הפקודה שתישלח בפועל" - קורא ל-_build_extra_args (אותה פונקציה
# בדיוק שמריצה את הרינדור האמיתי ב-/api/run) כדי שהתצוגה תמיד תשקף בדיוק את
# מה שבאמת ירוץ, לא מחרוזת-JS מקבילה שיכולה להתפצל ממנה עם הזמן.
@router.post("/api/video_editor/preview_command")
def api_video_editor_preview_command(payload: dict):
    args = W._build_extra_args("video_editor.py", payload)
    command = " ".join(["video_editor.py"] + [shlex.quote(a) for a in args])
    return {"args": args, "command": command}


# גל 9 (item 100): מתג אנגלית - מונחים+הסברים באנגלית לאותם מפתחות כמו FIELD_HELP
@router.get("/api/video_editor/field_help_en")
def api_video_editor_field_help_en():
    from utils.video.video_editor_field_help_en import CATEGORY_TITLES_EN, FIELD_HELP_EN
    return {"fields": {key: {"term": term, "tooltip": tip} for key, (term, tip) in FIELD_HELP_EN.items()}, "categories": CATEGORY_TITLES_EN}


@router.post("/api/video_editor/cancel_sleep")
def api_video_editor_cancel_sleep(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    return {"cancelled": W._cancel_pending_sleep()}


# --- items 95/96: השהיה/ביטול קובץ בודד + שינוי סדר תוך ריצה ---
@router.get("/api/video_editor/run_control")
def api_video_editor_run_control_get():
    path = W._current_run.get("control_file")
    if not path or not W.worker.is_running:
        return {"active": False, **W.run_control.EMPTY_STATE}
    return {"active": True, **W.run_control.RunControl(path).state()}


@router.post("/api/video_editor/run_control")
async def api_video_editor_run_control_set(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    path = W._current_run.get("control_file")
    if not path or not W.worker.is_running or not os.path.isfile(path):
        return JSONResponse({"error": "אין ריצה פעילה של עורך-העל."}, status_code=404)
    try:
        state = W.run_control.apply_action(W.run_control.RunControl(path).state(), str(payload.get("action", "")), str(payload.get("file", "")))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    W.run_control.write_state(path, state)
    return {"active": True, **state}


# --- item 92: ריצות אחרונות + "הרץ שוב" ---
@router.get("/api/video_editor/runs")
def api_video_editor_runs():
    return {"runs": W.editor_runs.load_runs(W._editor_runs_path())}


@router.post("/api/video_editor/runs/{run_id}/rerun")
@W.limiter.limit("10/minute")
async def api_video_editor_rerun(run_id: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    run = W.editor_runs.get_run(W._editor_runs_path(), run_id)
    if not run:
        return JSONResponse({"error": "הריצה לא נמצאה בהיסטוריה."}, status_code=404)
    if not os.path.isdir(run.get("folder") or ""):
        return JSONResponse({"error": "תיקיית הקלט של הריצה כבר לא קיימת."}, status_code=400)
    if W.worker.is_running:
        return JSONResponse({"error": "כבר יש ריצה פעילה - המתן לסיומה או עצור אותה."}, status_code=409)
    payload = dict(run.get("settings") or {})
    for key in ("only_files", "batch_overrides"):
        if run.get(key):
            payload[key] = run[key]
    if run.get("profile_name"):
        payload["ve_profile_name"] = run["profile_name"]
    # העדפות-הריצה של מי שלוחץ "הרץ שוב" עכשיו (פעולות סוף-ריצה/פרסום), לא של הריצה המקורית
    try:
        extras = await request.json()
    except ValueError:
        extras = {}
    if isinstance(extras, dict):
        for key in ("finish_actions", "publish_after", "publish_dry_run"):
            if key in extras:
                payload[key] = extras[key]
    return W._start_script_run(W.VIDEO_EDITOR_SCRIPT_PATH, run["folder"], payload, request.client.host if request.client else None)


@router.delete("/api/video_editor/runs/{run_id}")
def api_video_editor_run_delete(run_id: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    if not W.editor_runs.delete_run(W._editor_runs_path(), run_id):
        return JSONResponse({"error": "הריצה לא נמצאה."}, status_code=404)
    return {"ok": True}


@router.post("/api/video_editor/runs/{run_id}/label")
async def api_video_editor_run_label(run_id: str, request: Request):
    """גל 36: שם ותגיות לריצה בהיסטוריה (utils/editor_runs.set_run_label)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    body = await request.json()
    tags = body.get("tags") if isinstance(body.get("tags"), list) else []
    run = W.editor_runs.set_run_label(W._editor_runs_path(), run_id, str(body.get("name") or ""), tags)
    if run is None:
        return JSONResponse({"error": "הריצה לא נמצאה."}, status_code=404)
    return {"ok": True, "name": run.get("name", ""), "tags": run.get("tags", [])}


# --- item 91: תזמון ריצה מהעורך (אותו Scheduler בדיוק, עם תיקייה + דגלים) ---
@router.post("/api/video_editor/schedule")
async def api_video_editor_schedule(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    body = await request.json()
    payload = body.get("options") if isinstance(body.get("options"), dict) else {}
    folder = str(body.get("folder", ""))
    if not folder or not os.path.isdir(folder):
        return JSONResponse({"error": "בחר תיקיית קלט קודם."}, status_code=400)
    schedule_type = str(body.get("schedule_type", "daily"))
    if schedule_type not in W.scheduler_store.VALID_SCHEDULE_TYPES:
        return JSONResponse({"error": "סוג תזמון לא מוכר."}, status_code=400)
    time_str = str(body.get("time_str", "03:00")).strip() or "03:00"
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_str):
        return JSONResponse({"error": "שעה לא תקינה (HH:MM)."}, status_code=400)
    try:
        interval_hours = max(1, int(body.get("interval_hours", 24) or 24))
    except (TypeError, ValueError):
        interval_hours = 24
    layers_path = W._write_layers_file(payload)
    if layers_path:
        # שכבות של משימה מתוזמנת חייבות לשרוד את ניקוי ה-7 ימים (layers_*)
        persistent = os.path.join(W.LAYERS_DIR, "scheduled_" + os.path.basename(layers_path)[len("layers_"):])
        os.replace(layers_path, persistent)
        layers_path = persistent
    args = W._build_extra_args("video_editor.py", {k: v for k, v in payload.items() if k != "batch_overrides"}, layers_path=layers_path)
    task = W.scheduler_store.add_task(
        W.VIDEO_EDITOR_SCRIPT_PATH, schedule_type, time_str=time_str, weekday=str(body.get("weekday", "sun")),
        interval_hours=interval_hours, folder=folder, extra_args=args, label=str(body.get("label") or "").strip()[:80],
    )
    W.audit_log.record_action("web", "scheduler_task_add", details="video_editor.py (מהעורך)", username=request.client.host if request.client else None)
    return {"ok": True, "id": task["id"]}


@router.get("/api/waveform")
def api_waveform(path: str = ""):
    """זהה ל-ui/rocket_settings_tab.py's show_waveform_dialog - אותו אלגוריתם
    בדיוק (pydub, ~700 שיאי עוצמה) כדי לכוון את סף הרעש של story_cutter.py
    לפני ריצה. def רגיל (לא async) - Starlette מריץ handlers כאלה ב-thread
    pool אוטומטית, כך שפענוח שמע של קובץ גדול לא חוסם את שאר הבקשות/ה-WS
    בזמן שהוא רץ, בדיוק כמו שה-thread נפרד בגרסה השולחנית מונע קיפאון ה-UI."""
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(path).set_channels(1)
        samples = audio.get_array_of_samples()
        chunk_size = max(1, len(samples) // 700)
        peaks = [max(abs(s) for s in samples[i:i + chunk_size]) for i in range(0, len(samples) - chunk_size, chunk_size)]
        max_peak = max(peaks) if peaks else 1
        # full_scale/duration (item 43: סף שקט על ה-waveform) - כדי שהדפדפן ימיר
        # dB (silencedetect noise=-30dB) לגובה על הגרף ביחס לעוצמה-מלאה, לא ביחס לשיא.
        return {"peaks": peaks, "max_peak": max_peak, "full_scale": audio.max_possible_amplitude, "duration": audio.duration_seconds}
    except Exception as e:
        return JSONResponse({"error": f"שגיאה בטעינת השמע: {e}"}, status_code=500)


@router.get("/api/video_editor/eta")
def api_video_editor_eta(codec: str = "h264", hwaccel: bool = False, file_count: int = 1):
    """item: הערכת זמן-ריצה משוער - ממוצע שניות-לקובץ מריצות מוצלחות קודמות
    עם אותו codec+hwaccel בדיוק, כפול מספר הקבצים שעומדים להיכנס לריצה
    הנוכחית. null אם אין אף היסטוריה תואמת (עדיפות על הערכה מטעה)."""
    estimate = W.job_history.get_video_editor_eta_estimate(codec, hwaccel)
    if estimate is None:
        return None
    return {
        "avg_seconds_per_file": estimate["avg_seconds_per_file"],
        "run_count": estimate["run_count"],
        "estimated_total_seconds": estimate["avg_seconds_per_file"] * max(1, file_count),
    }
