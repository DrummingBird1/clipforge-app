# entrypoints/web/routes/automation.py
#
# תזמון, הגדרות Rocket Shorts ו-soundboard.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import glob
import os
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from entrypoints import web_app as W
from utils.media import shorts_naming

router = APIRouter()


@router.post("/api/soundboard/play")
async def api_soundboard_play(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    sound = payload.get("sound")
    if sound not in W.SOUNDBOARD_SOUNDS:
        return JSONResponse({"error": "צליל לא מוכר."}, status_code=400)
    freq, duration = W.SOUNDBOARD_SOUNDS[sound]
    W.play_board_sound(freq, duration)
    return {"ok": True}


@router.get("/api/scheduler/tasks")
def api_scheduler_tasks_list():
    """זהה ל-ui/scheduler_tab.py/cogs/gui_schedule_cog.py - אותו
    utils/bot/scheduler_store.py בדיוק, כך שמשימה שנוספה מכאן מופיעה מיד גם
    ב-GUI וגם בפקודות /schedule_* בדיסקורד, בלי מקור אמת כפול."""
    tasks = W.scheduler_store.load_tasks()
    for task in tasks:
        task["script_name"] = W.get_script_metadata(task["script_path"])["name"]
    return tasks


@router.post("/api/scheduler/tasks")
async def api_scheduler_tasks_add(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()

    script_id = str(payload.get("script_id", ""))
    safe_name = os.path.basename(script_id)
    matches = glob.glob(os.path.join(W.SCRIPTS_DIR, "**", safe_name), recursive=True)
    script_path = os.path.abspath(matches[0]) if matches else ""
    if not script_path or not script_path.startswith(W.SCRIPTS_DIR + os.sep):
        return JSONResponse({"error": "סקריפט לא נמצא."}, status_code=400)

    schedule_type = str(payload.get("schedule_type", "daily"))
    if schedule_type not in W.scheduler_store.VALID_SCHEDULE_TYPES:
        return JSONResponse({"error": "סוג תזמון לא מוכר."}, status_code=400)

    try:
        interval_hours = max(1, int(payload.get("interval_hours", 24) or 24))
    except (TypeError, ValueError):
        interval_hours = 24

    task = W.scheduler_store.add_task(
        script_path, schedule_type,
        time_str=str(payload.get("time_str", "03:00")).strip() or "03:00",
        weekday=str(payload.get("weekday", "sun")),
        interval_hours=interval_hours,
    )
    W.audit_log.record_action("web", "scheduler_task_add", details=safe_name, username=request.client.host if request.client else None)
    return {"ok": True, "id": task["id"]}


@router.post("/api/scheduler/tasks/{task_id}/toggle")
async def api_scheduler_tasks_toggle(task_id: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    tasks = W.scheduler_store.load_tasks()
    if not any(t["id"] == task_id for t in tasks):
        return JSONResponse({"error": "משימה לא נמצאה."}, status_code=404)
    W.scheduler_store.set_enabled(task_id, bool(payload.get("enabled")))
    return {"ok": True}


def _wake_status():
    from utils.bot import wake_timer
    state = wake_timer.load_state()
    return {**state, "task_name": wake_timer.TASK_NAME, "windows_allows": wake_timer.windows_allows_wake_timers()}


@router.get("/api/scheduler/wake_timer")
def api_scheduler_wake_timer():
    """הערת המחשב למשימה הבאה: מופעל?, המועד הרשום, שגיאה אחרונה, ו-'Allow wake timers' של Windows (קריאה בלבד)."""
    return _wake_status()


@router.post("/api/scheduler/wake_timer")
async def api_scheduler_wake_timer_set(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    from utils.bot import wake_timer
    payload = await request.json()
    enabled = bool(payload.get("enabled"))
    wake_timer.set_enabled(enabled, W.scheduler_store.load_tasks())
    W.audit_log.record_action("web", "scheduler_wake_timer", details="on" if enabled else "off",
                              username=request.client.host if request.client else None)
    return _wake_status()


@router.delete("/api/scheduler/tasks/{task_id}")
def api_scheduler_tasks_delete(task_id: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W.scheduler_store.remove_task(task_id)
    W.audit_log.record_action("web", "scheduler_task_delete", details=task_id, username=request.client.host if request.client else None)
    return {"ok": True}


@router.get("/api/rocket_settings")
def api_rocket_settings_get():
    """זהה ל-ui/rocket_settings_tab.py - אותו data/rocket_settings.json ו-
    data/counter.txt בדיוק, כדי ש-rocket_shorts_publisher.py יתנהג זהה בין
    דסקטופ לווב. preset נגזר מהתאמת encoder/ffmpeg_preset/quality_cq לאחד
    מ-ROCKET_QUALITY_PRESETS (בדיוק אותה לוגיקת current_match)."""
    settings = W._load_rocket_settings()
    chain = W.auto_chain.settings_from(settings)
    naming = {**settings, **shorts_naming.missing_naming(settings)}
    input_dir = settings.get("input_dir", W.BASE_DIR)
    preset = next(
        (name for name, p in W.ROCKET_QUALITY_PRESETS.items()
         if p["encoder"] == settings.get("encoder") and p["ffmpeg_preset"] == settings.get("ffmpeg_preset")
         and p["quality_cq"] == settings.get("quality_cq")),
        None
    )
    return {
        "input_dir": input_dir,
        "output_dir": settings.get("output_dir", input_dir),
        # ריק כברירת מחדל, כמו ב-rocket_shorts_publisher.py: assets/overlay.png כבר לא בריפו
        "watermark_image_path": settings.get("watermark_image_path", ""),
        "preset": preset,
        "enable_weekly_recap": bool(settings.get("enable_weekly_recap", False)),
        "weekly_recap_period": settings.get("weekly_recap_period") if settings.get("weekly_recap_period") in ("week", "month", "year") else "week",
        "weekly_recap_day": min(max(int(settings.get("weekly_recap_day", 6)), 0), 6),
        "enable_captions": bool(settings.get("enable_captions", False)),
        "enable_captions_translate": bool(settings.get("enable_captions_translate", False)),
        "clip_hotkey": str(settings.get("clip_hotkey", "")),
        "capture_voice_channel_id": str(settings.get("capture_voice_channel_id", "")),
        "capture_watch_dir": str(settings.get("capture_watch_dir", "")),
        "max_concurrent_renders": max(1, int(settings.get("max_concurrent_renders", 1) or 1)),
        "counter": W._get_rocket_counter(),
        # 30.10.2026: "<title_prefix> #N", המשחק לכותרות ה-AI והרזולוציה - מה שבקובץ, או ברירת המחדל (utils/media/shorts_naming)
        "title_prefix": shorts_naming.clean_prefix(naming.get("title_prefix")),
        "game_name": str(naming.get("game_name") or ""),
        "output_resolution": shorts_naming.clean_resolution(naming.get("output_resolution")),
        # גל 32: מה קורה אחרי שקליפ נכנס מ-OBS/תיקיית לכידה, ו-SEO מ-Gemini
        "auto_chain": chain["mode"],
        "auto_chain_profile": chain["profile"],
        "auto_chain_dry_run": chain["dry_run"],
        "seo_ai": settings.get("seo_ai", True) is not False,
    }


@router.get("/api/auto_chain/recent")
def api_auto_chain_recent():
    """גל 32: מה קרה לקליפים האחרונים שנכנסו (בזיכרון, מאז שהשרת עלה)."""
    with W._auto_chain_lock:
        return {"recent": list(W._auto_chain_recent)}


@router.get("/api/rocket_settings/presets")
def api_rocket_settings_presets():
    return {"presets": list(W.ROCKET_QUALITY_PRESETS.keys()), "recap_days": W.ROCKET_RECAP_DAYS}


@router.post("/api/rocket_settings/probe_nvenc")
@W.limiter.limit("5/minute")
def api_rocket_settings_probe_nvenc(request: Request):
    """בדיקה אמיתית (item: מודעות למגבלת סשנים אמיתית של NVENC) - מריצה כמה
    קידודי NVENC זעירים בו-זמנית (utils/media/nvenc_probe.py) ומחזירה כמה הצליחו.
    לוקח כמה שניות בפועל - def רגיל (לא async), אז Starlette מריץ אותו
    ב-thread pool אוטומטית (אותו עיקרון בדיוק כמו /api/waveform), בלי לחסום
    בקשות אחרות בזמן שהוא רץ."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    detected = W.probe_max_concurrent_nvenc_sessions(W.get_ffmpeg_exe())
    return {"detected": detected}


@router.post("/api/rocket_settings")
async def api_rocket_settings_save(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()

    new_dir = str(payload.get("input_dir", "")).strip()
    new_output = str(payload.get("output_dir", "")).strip()
    new_overlay = str(payload.get("watermark_image_path", "")).strip()

    data = W._load_rocket_settings()
    data["input_dir"] = new_dir
    data["rocket_videos_directory"] = new_dir
    data["output_dir"] = new_output if new_output else new_dir
    data["watermark_image_path"] = new_overlay
    data["enable_weekly_recap"] = bool(payload.get("enable_weekly_recap"))
    data["weekly_recap_period"] = payload.get("weekly_recap_period") if payload.get("weekly_recap_period") in ("week", "month", "year") else "week"
    try:
        data["weekly_recap_day"] = min(max(int(payload.get("weekly_recap_day", 6)), 0), 6)
    except (TypeError, ValueError):
        data["weekly_recap_day"] = 6
    data["enable_captions"] = bool(payload.get("enable_captions"))
    data["enable_captions_translate"] = bool(payload.get("enable_captions_translate"))
    data["clip_hotkey"] = str(payload.get("clip_hotkey", "")).strip()
    data["capture_voice_channel_id"] = str(payload.get("capture_voice_channel_id", "")).strip()
    data["capture_watch_dir"] = str(payload.get("capture_watch_dir", "")).strip()
    try:
        data["max_concurrent_renders"] = max(1, int(payload.get("max_concurrent_renders", 1)))
    except (TypeError, ValueError):
        data["max_concurrent_renders"] = 1
    chain = W.auto_chain.settings_from(payload)
    data["auto_chain"] = chain["mode"]
    data["auto_chain_profile"] = chain["profile"]
    data["auto_chain_dry_run"] = chain["dry_run"]
    data["seo_ai"] = payload.get("seo_ai", True) is not False
    # רק כשהטופס שלח אותם - דף ישן מה-cache של ה-service worker לא שולח, ואסור שידרוס קידומת שנבחרה בברירת המחדל
    if "title_prefix" in payload:
        data["title_prefix"] = shorts_naming.clean_prefix(payload.get("title_prefix"))
    if "game_name" in payload:
        data["game_name"] = str(payload.get("game_name") or "").strip()
    if "output_resolution" in payload:
        data["output_resolution"] = shorts_naming.clean_resolution(payload.get("output_resolution"))

    preset = payload.get("preset")
    if preset in W.ROCKET_QUALITY_PRESETS:
        p_data = W.ROCKET_QUALITY_PRESETS[preset]
        data["encoder"] = p_data["encoder"]
        data["ffmpeg_preset"] = p_data["ffmpeg_preset"]
        data["quality_cq"] = p_data["quality_cq"]

    try:
        counter_val = int(payload.get("counter"))
        counter_val = max(1, counter_val)
        os.makedirs(W.DATA_DIR, exist_ok=True)
        with open(W.ROCKET_COUNTER_PATH, "w", encoding="utf-8") as f:
            f.write(str(counter_val))
    except (TypeError, ValueError):
        pass

    W._save_rocket_settings(data)
    return {"ok": True}
