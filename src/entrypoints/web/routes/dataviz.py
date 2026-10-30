# entrypoints/web/routes/dataviz.py
#
# חבילות הפרסום של סרטוני נתונים (utils/dataviz_publish.py): רשימת *.publish.json ב-
# workspace/<כיוון>/dataviz/, תמונה ממוזערת, ודף ה-SEO, ואישור/דחייה. אותה לוגיקה בדיוק כמו
# dataviz_maker.py --decide (set_decision). בכוונה אין כאן שום העלאה: אישור רק מסמן סטטוס.

import json
import os
import re
import shutil
import threading

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse

from dataviz.web import catalog as dataviz_catalog
from dataviz.web import narration_draft as dataviz_narration_draft
from dataviz.web import readability as dataviz_readability
from dataviz.web import history as dataviz_history
from dataviz.web import variants as dataviz_variants
from dataviz.web import batch as dataviz_batch
from dataviz.web import notify as dataviz_notify
from dataviz.web import story_templates as dataviz_story_templates
from dataviz.web import factcheck as dataviz_factcheck
from dataviz.web import trash as dataviz_trash
from dataviz.web import data as dataviz_data, episodes as dataviz_episodes, handoff as dataviz_handoff, kits as dataviz_kits, preview as dataviz_preview, publish as dataviz_publish

from entrypoints import web_app as W
from utils.shared import export_dir
from utils.shared import workspace_dir as layout
from utils.shared import data_paths

router = APIRouter()

ORIENTATIONS = ("horizontal", "vertical", "square")
MAX_OUTPUTS = 60
MAX_STILLS_LISTED = 60
_VIDEO_SUFFIXES = (("_test.mp4", "test"), ("_preview.mp4", "preview"))
_SHORT_RE = re.compile(r"_shorts_\d+\.mp4$")   # גל 55: <שם>_shorts_1.mp4...
SCRIPT_ID = "video/dataviz_maker.py"
SHEET_MAX_CHARS = 4000
_SAFE_NAME = re.compile(r"^[^\\/:*?\"<>|\x00-\x1f]+$")


def _dataviz_dir():
    """24.10.2026: ה-data_dir של עורך הגרפים - data/ במבנה השטוח, data/dataviz/ אחרי ההעברה לתיקיות לפי נושא
    (utils/shared/data_paths.dataviz_root). נקרא בכל פעם, כי טסטים מחליפים את web_app.DATA_DIR."""
    return data_paths.dataviz_root(W.DATA_DIR)


def _folder(orientation):
    """workspace/dataviz/outputs/<כיוון> (עד 19.10.2026: workspace/<כיוון>/dataviz) - לשם dataviz_maker.py כותב כשאין תיקיית ייצוא."""
    return layout.tool_output_dir(layout.DATAVIZ, "outputs", orientation, base=W.WORKSPACE_DIR)


def _export_bases():
    """23.10.2026: התיקיות של עורך הגרפים בתיקיית הייצוא (utils/shared/export_dir.py) - התיקייה שלו (לשם נכתבים התוצרים כשהוגדרה),
    ואחריה <תיקיית הייצוא>/dataviz (תוצרים מלפני שהוגדרה) - כמו export_dir.resolve_tool, אבל בלי לבדוק אם אפשר לכתוב לשם
    (קריאה בלבד)."""
    own = export_dir.configured_tool_root(layout.DATAVIZ)
    root = export_dir.configured_root()
    return [base for base in (own, os.path.join(root, layout.DATAVIZ) if root else "") if base]


def _same_dir(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _folders(orientation):
    """תיקיות הייצוא של _export_bases (כשהוגדרו - לראשונה נכתבים התוצרים החדשים), workspace (תוצרים מלפניה, או מריצה שבה היא לא הייתה זמינה), ואחריהן
    הישנה כל עוד היא קיימת (תוצרים מלפני סקריפט ההעברה) - קוראים מחפשים בכולן, לפי הסדר."""
    workspace = _folder(orientation)
    folders = []
    for base in _export_bases():
        folder = os.path.join(base, "outputs", orientation)
        if not any(_same_dir(folder, f) for f in folders + [workspace]):
            folders.append(folder)
    old = layout.legacy_output_dir(layout.DATAVIZ, "outputs", orientation, base=W.WORKSPACE_DIR)
    return folders + [workspace] + ([old] if old and os.path.isdir(old) else [])


def _save_to():
    """לשורה "נשמר ב-..." במסך: לאן dataviz_maker.py יכתוב עכשיו (‏outputs/<כיוון> מתחת), ולמה לא לתיקיית הייצוא אם לא."""
    resolution = export_dir.resolve_tool(layout.DATAVIZ)
    usable = resolution.root and not resolution.problem
    base = resolution.base if usable else layout.tool_output_dir(layout.DATAVIZ, base=W.WORKSPACE_DIR)
    return {"folder": os.path.join(base, "outputs"), "root": resolution.root, "problem": resolution.problem}


def _sidecar(orientation, name):
    """נתיב ה-.publish.json אחרי אימות: כיוון מתוך רשימה סגורה, שם בלי מפרידי נתיב, והתוצאה בתוך התיקייה."""
    if orientation not in ORIENTATIONS or not name or name.startswith(".") or not _SAFE_NAME.match(name):
        return None
    for candidate in _folders(orientation):
        folder = os.path.realpath(candidate)
        path = os.path.realpath(os.path.join(folder, name + dataviz_publish.SIDECAR_SUFFIX))
        if os.path.dirname(path) == folder and os.path.isfile(path):
            return path
    return None


def _read_text(folder, filename):
    if not filename or os.path.basename(filename) != filename:
        return ""
    try:
        with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
            return f.read(SHEET_MAX_CHARS)
    except OSError:
        return ""


def _summary(orientation, package, path):
    folder = os.path.dirname(path)
    name = os.path.basename(path)[: -len(dataviz_publish.SIDECAR_SUFFIX)]
    meta = package.get("metadata") or {}
    thumb = package.get("thumbnail") or ""
    return {
        "id": f"{orientation}/{name}", "orientation": orientation, "name": name,
        "status": package["status"], "video": package.get("video", ""),
        "video_exists": os.path.isfile(os.path.join(folder, os.path.basename(package.get("video", "")))),
        "has_thumbnail": bool(thumb) and os.path.isfile(os.path.join(folder, os.path.basename(thumb))),
        "title": meta.get("title", ""), "youtube_title": meta.get("youtube_title", ""),
        "tiktok_caption": meta.get("tiktok_caption", ""), "description": meta.get("description", ""),
        "hashtags": meta.get("hashtags", []), "source": meta.get("source", ""),
        "steps": package.get("steps", {}), "created_at": package.get("created_at", ""),
        "decided_at": package.get("decided_at", ""), "sent": sorted((package.get("sent") or {}).keys()),
        # גל 41: פרטי השליחה (מזהה הסרטון ביוטיוב, זמן פרסום מתוזמן) - לקישור לסרטון שפורסם
        "sent_info": {target: {k: v for k, v in (info or {}).items() if k in ("at", "video_id", "publish_at")}
                      for target, info in (package.get("sent") or {}).items() if isinstance(info, dict)},
        "stats": package.get("stats") or None,   # גל 44: צפיות אחרונות שנמשכו מיוטיוב
    }


@router.get("/api/dataviz/packages")
def api_dataviz_packages():
    """כל חבילות הפרסום (ממתינות קודם, אחר כך החדשות ביותר)."""
    rows = []
    for orientation in ORIENTATIONS:
        for folder in _folders(orientation):
            for package in dataviz_publish.list_packages(folder):
                rows.append(_summary(orientation, package, package["path"]))
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    rows.sort(key=lambda r: r["status"] != dataviz_publish.PENDING)
    return rows


@router.get("/api/dataviz/packages/{orientation}/{name}")
def api_dataviz_package(orientation: str, name: str):
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        package = dataviz_publish.load_package(path)
    except (OSError, ValueError):
        return JSONResponse({"error": "קובץ הפרסום פגום."}, status_code=400)
    return {**_summary(orientation, package, path), "sheet": _read_text(os.path.dirname(path), package.get("seo_sheet", ""))}


@router.post("/api/dataviz/packages/{orientation}/{name}/send")
async def api_dataviz_send(orientation: str, name: str, request: Request):
    """שליחה של חבילה *שאושרה* - רק בלחיצה מפורשת: target=dry_run (ברירת מחדל, לא עושה כלום, מחזיר מה היה נשלח),
    rocket (מעתיק את הסרטון לתיקיית הקלט של Rocket Shorts, לא דורס) או youtube (העלאה פרטית דרך החשבון שכבר הוגדר).
    rocket/youtube דורשים confirm=true. כל שליחה נרשמת בקובץ החבילה (sent) ומונעת שליחה כפולה."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    target = str(payload.get("target") or "dry_run")
    folder = os.path.dirname(path)
    # גל 41: פרסום מתוזמן ביוטיוב - זמן עתידי בפורמט ISO (YouTube מפרסם בעצמו)
    publish_at = None
    if payload.get("publish_at"):
        from datetime import datetime, timezone
        try:
            when = datetime.fromisoformat(str(payload["publish_at"]))
        except ValueError:
            return JSONResponse({"error": "זמן הפרסום לא תקין."}, status_code=400)
        when = when.astimezone(timezone.utc) if when.tzinfo else when.astimezone().astimezone(timezone.utc)
        if when <= datetime.now(timezone.utc):
            return JSONResponse({"error": "זמן הפרסום צריך להיות בעתיד."}, status_code=400)
        if target != "youtube":
            return JSONResponse({"error": "תזמון אפשרי רק בהעלאה ליוטיוב."}, status_code=400)
        publish_at = when.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        package = dataviz_publish.load_package(path)
        plan = dataviz_publish.send_plan(package, folder, target)
    except (OSError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    shown = {k: v for k, v in plan.items() if k not in ("video", "thumbnail")}
    shown["video"] = os.path.basename(plan["video"])
    shown["thumbnail"] = os.path.basename(plan.get("thumbnail") or "")
    if target == "dry_run":
        return {"ok": True, "dry_run": True, "plan": shown}
    if payload.get("confirm") is not True:
        return JSONResponse({"error": "נדרש אישור מפורש (confirm)."}, status_code=400)
    user = request.client.host if request.client else None
    if target == "rocket":
        dest_dir = W.approval_store.get_rocket_input_dir()
        dest = os.path.join(dest_dir, os.path.basename(plan["video"]))
        if os.path.exists(dest):
            return JSONResponse({"error": "בתיקיית הקלט של Shorts כבר יש קובץ בשם הזה - לא דורסים."}, status_code=409)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(plan["video"], dest)
        dataviz_publish.record_send(path, "rocket", {"dest": dest})
        W.audit_log.record_action("web", "dataviz_send_rocket", details=f"{orientation}/{name}", username=user)
        return {"ok": True, "sent": "rocket", "dest": dest}
    # youtube
    if not W.youtube_uploader.is_configured():
        return JSONResponse({"error": "חשבון YouTube לא הוגדר (client_secret.json) - אפשר להשתמש ב-dry_run או Rocket."}, status_code=409)
    with W._youtube_upload_lock:
        if W._youtube_upload_state["in_progress"]:
            return JSONResponse({"error": "כבר רצה העלאה אחרת."}, status_code=409)
        W._youtube_upload_state.update({"in_progress": True, "percent": 0, "success": None, "video_id": None, "error": None})

    def _progress(pct):
        with W._youtube_upload_lock:
            W._youtube_upload_state["percent"] = pct

    def _do_upload():
        try:
            extra = {"publish_at": publish_at} if publish_at else {}
            video_id = W.youtube_uploader.upload_video(plan["video"], title=plan["title"], description=plan["description"],
                                                       tags=plan["tags"], privacy_status="private", progress_callback=_progress, **extra)
            if plan.get("thumbnail"):   # גל 55: התמונה הממוזערת שנבחרה עולה יחד עם הסרטון
                try:
                    W.youtube_uploader.set_thumbnail(video_id, plan["thumbnail"])
                    extra["thumbnail"] = "set"
                except Exception as e:   # ערוץ לא מאומת / מכסה - הסרטון עצמו כבר עלה
                    extra["thumbnail"] = f"failed: {str(e)[:200]}"
            dataviz_publish.record_send(path, "youtube", {"video_id": video_id, **extra})
            W.youtube_publish_log.record_upload(video_id, os.path.basename(plan["video"]), plan["title"])
            with W._youtube_upload_lock:
                W._youtube_upload_state.update({"in_progress": False, "success": True, "video_id": video_id, "percent": 100})
        except Exception as e:
            with W._youtube_upload_lock:
                W._youtube_upload_state.update({"in_progress": False, "success": False, "error": str(e)})

    threading.Thread(target=_do_upload, daemon=True).start()
    W.audit_log.record_action("web", "dataviz_send_youtube", details=f"{orientation}/{name}", username=user)
    return {"ok": True, "sent": "youtube", "started": True}


@router.get("/api/dataviz/packages/{orientation}/{name}/thumbnail")
def api_dataviz_thumbnail(orientation: str, name: str):
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        package = dataviz_publish.load_package(path)
    except (OSError, ValueError):
        return JSONResponse({"error": "קובץ הפרסום פגום."}, status_code=400)
    thumb = package.get("thumbnail") or ""
    full = os.path.join(os.path.dirname(path), os.path.basename(thumb))
    if not thumb or not os.path.isfile(full):
        return JSONResponse({"error": "אין תמונה ממוזערת."}, status_code=404)
    return FileResponse(full, media_type="image/jpeg")


@router.post("/api/dataviz/packages/{orientation}/{name}/metadata")
async def api_dataviz_package_metadata(orientation: str, name: str, request: Request):
    """גל 41: עריכת הכותרות, התיאור והתגיות של חבילה שעוד לא נשלחה (אשף הפרסום)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    try:
        package = dataviz_publish.update_metadata(path, payload)
    except (OSError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "metadata": package.get("metadata", {})}


@router.post("/api/dataviz/packages/{orientation}/{name}/decide")
async def api_dataviz_decide(orientation: str, name: str, request: Request):
    """approved/rejected בלבד, ורק מ-pending_approval (כמו --decide). לא מעלה ולא מזיז שום קובץ."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    decision = payload.get("decision") if isinstance(payload, dict) else None
    try:
        package = dataviz_publish.set_decision(path, str(decision))
    except (OSError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    W.audit_log.record_action(
        "web", "dataviz_decide", details=f"{orientation}/{name}={package['status']}",
        username=request.client.host if request.client else None,
    )
    return _summary(orientation, package, path)

# ---------------------------------------------------------------------------
# מסך "סרטוני נתונים": פרקים, הרצה, תוצרים ויצירת פרק חדש
# ---------------------------------------------------------------------------

def _inside_outputs(orientation, *parts, exists=os.path.isfile):
    """(תיקיית פלט, נתיב) של תוצר שקיים באחת מתיקיות הפלט (החדשה קודם), אחרי שהנתיב נבדק שנשאר בתוכה."""
    for candidate in _folders(orientation):
        base = os.path.realpath(candidate)
        path = os.path.realpath(os.path.join(base, *parts))
        if os.path.commonpath([base, path]) == base and path != base and exists(path):
            return base, path
    return None, None


def _safe_file(orientation, *parts):
    """נתיב קובץ תוצר אחרי אימות: כיוון מרשימה סגורה, כל חלק בלי מפרידים, והתוצאה בתוך תיקיית הפלט."""
    if orientation not in ORIENTATIONS or not parts:
        return None
    for part in parts:
        if not part or part.startswith(".") or not _SAFE_NAME.match(part):
            return None
    return _inside_outputs(orientation, *parts)[1]


def _video_mode(filename):
    if _SHORT_RE.search(filename):
        return "shorts"
    for suffix, mode in _VIDEO_SUFFIXES:
        if filename.endswith(suffix):
            return mode
    return "full"


@router.get("/api/dataviz/episodes")
def api_dataviz_episodes(show_hidden: int = 0):
    """הפרקים תחת data/dataviz_episodes - קריאה בלבד (ההגדרות נטענות ומאומתות, שום דבר לא נכתב)."""
    from dataviz.charts import CHART_MODULES
    from dataviz.smart import watch as smart_watch
    if smart_watch.load(_dataviz_dir())["enabled"]:   # 20.10.2026: התיקייה במעקב - ה-thread מתחיל כשהמסך נפתח (אם הופעל)
        smart_watch.start(_dataviz_dir(), W.WORKSPACE_DIR)
    return {"episodes": dataviz_episodes.list_episodes(_dataviz_dir(), include_hidden=bool(show_hidden)),
            "hidden_count": len(dataviz_episodes.load_hidden(_dataviz_dir())), "charts": list(CHART_MODULES),
            "modes": list(W.DATAVIZ_MODES), "running": bool(W.worker.is_running)}


# 20.10.2026: הפרקים של הריצה האחרונה מהמסך - כל עוד ה-worker רץ הם "רצים או בתור", ואסור למחוק אותם
_RUN_EPISODES: set = set()


def _episode_busy(name: str) -> bool:
    if not W.worker.is_running:
        return False
    if name in _RUN_EPISODES:
        return True
    running = _maker_episodes_running()
    if "*" in running or name in running:
        return True
    status = _read_json_file(_queue_paths()[0], {})
    return any(isinstance(e, dict) and e.get("name") == name and e.get("state") in ("pending", "running")
               for e in (status.get("episodes") or [] if isinstance(status, dict) else []))


def _maker_episodes_running() -> set:
    """23.10.2026: הפרקים ש-dataviz_maker.py מרנדר עכשיו, לפי שורת הפקודה שלו - גם ריצה שלא התחילה מהמסך (משימה
    מתוזמנת), שלא נרשמת ב-_RUN_EPISODES ונמחקה באמצע. "*" = כל תיקיית הפרקים (בלי --episode / --episodes)."""
    import psutil
    names: set = set()
    root = os.path.normcase(os.path.abspath(dataviz_episodes.episodes_root(_dataviz_dir())))
    try:
        children = psutil.Process().children(recursive=True)
    except psutil.Error:
        return names
    for proc in children:
        try:
            cmd = proc.cmdline()
        except psutil.Error:
            continue
        if not any(os.path.basename(part) == "dataviz_maker.py" for part in cmd):
            continue
        value = lambda flag: cmd[cmd.index(flag) + 1] if flag in cmd and cmd.index(flag) + 1 < len(cmd) else ""  # noqa: E731
        listed = [n for n in (value("--episode"), *value("--episodes").split(",")) if n.strip()]
        if listed:
            names.update(n.strip() for n in listed)
        elif value("--input_dir"):
            folder = os.path.normcase(os.path.abspath(value("--input_dir")))
            names.add("*" if folder == root else os.path.basename(folder))
    return names


@router.post("/api/dataviz/narration_draft")
@W.limiter.limit("10/minute")
async def api_dataviz_narration_draft(request: Request):
    """20.10.2026: טיוטת תסריט קריינות מהנתונים (Gemini לפי כללי המכסה; בלעדיו - טיוטה מקומית). לא כותב כלום -
    הדפדפן שם את השורות בטיוטה של story.script."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.config import ConfigError
    folder = dataviz_episodes.episode_folder(_dataviz_dir(), str(payload.get("episode", "")))
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    overrides = dataviz_episodes.load_overrides_for_path(folder)
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    try:
        if draft:
            overrides = dataviz_episodes.draft_overrides(overrides, draft)
        return await run_in_threadpool(dataviz_narration_draft.draft, folder, overrides)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (KeyError, ValueError, OSError) as e:   # 23.10.2026: נתונים שעוברים את הקונפיג ונכשלים בבנייה - 400 עם הסבר, לא 500
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)


@router.get("/api/dataviz/readability/targets")
async def api_dataviz_readability_targets():
    return {"targets": dataviz_readability.targets()}


@router.post("/api/dataviz/readability")
@W.limiter.limit("20/minute")
async def api_dataviz_readability(request: Request):
    """20.10.2026: בדיקת קריאות לפי יעד - כמה פריימים בגודל המלא של היעד; אזהרות עם הצעת תיקון. לא כותב כלום."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.config import ConfigError
    folder = dataviz_episodes.episode_folder(_dataviz_dir(), str(payload.get("episode", "")))
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    target = str(payload.get("target") or "youtube")
    if target not in {t["id"] for t in dataviz_readability.targets()}:
        return JSONResponse({"error": "יעד לא מוכר."}, status_code=400)
    overrides = dataviz_episodes.load_overrides_for_path(folder)
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    try:
        if draft:
            overrides = dataviz_episodes.draft_overrides(overrides, draft)
        return await run_in_threadpool(dataviz_readability.check, folder, overrides, target)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (KeyError, ValueError, OSError) as e:   # 23.10.2026: נתונים שעוברים את הקונפיג ונכשלים בבנייה - 400 עם הסבר, לא 500
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)


@router.get("/api/dataviz/history")
def api_dataviz_history(episode: str = ""):
    """20.10.2026: היסטוריית הגרסאות של הפרק (תמונת מצב בכל שמירה), מהחדשה לישנה."""
    try:
        return dataviz_history.versions(_dataviz_dir(), episode)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/dataviz/history/diff")
def api_dataviz_history_diff(episode: str = "", id: str = ""):
    try:
        return dataviz_history.diff(_dataviz_dir(), episode, id)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/history/restore")
@W.limiter.limit("20/minute")
async def api_dataviz_history_restore(request: Request):
    """שחזור קובץ השינויים לגרסה - config.yaml לא נכתב; השחזור עצמו נכנס להיסטוריה."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        return dataviz_history.restore(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("id", "")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/dataviz/variants")
def api_dataviz_variants(episode: str = ""):
    """20.10.2026: הגרסאות של הפרק (שכבות עם שם מעל אותו בסיס)."""
    try:
        return dataviz_variants.list_variants(_dataviz_dir(), episode)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/variants/{action}")
@W.limiter.limit("30/minute")
async def api_dataviz_variants_action(request: Request, action: str):
    """save: יוצר / מחליף גרסה (name, label, target, lang, set); remove: הגרסה עוברת ל-.removed (לא נמחקת)."""
    payload, error = await _json_body(request)
    if error:
        return error
    episode = str(payload.get("episode", ""))
    try:
        if action == "save":
            return dataviz_variants.save(_dataviz_dir(), episode, payload.get("name"), payload.get("label"), payload.get("target") or "",
                                         payload.get("lang") or "", payload.get("set") or {})
        if action == "remove":
            return dataviz_variants.remove(_dataviz_dir(), episode, payload.get("name"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    return JSONResponse({"error": "פעולה לא מוכרת."}, status_code=404)


@router.get("/api/dataviz/batch/sources")
def api_dataviz_batch_sources():
    """20.10.2026: מקורות לדוח התמונות - תיקיית הטיוטה (אם יש) והתיקיות בתגיות של הפרקים."""
    tags = dataviz_episodes.load_tags(_dataviz_dir())
    folders = sorted({str(t.get("folder")) for t in tags.values() if isinstance(t, dict) and t.get("folder")})
    return {"staging": dataviz_episodes.staging_folder(W.WORKSPACE_DIR), "folders": folders, **dataviz_batch.status()}


@router.post("/api/dataviz/batch/start")
@W.limiter.limit("6/minute")
async def api_dataviz_batch_start(request: Request):
    """20.10.2026: דוח תמונות לכל הפרקים במקור (staging / folder + path / app + folder) - ברקע, ריצה אחת בכל פעם."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        return dataviz_batch.start(_dataviz_dir(), W.WORKSPACE_DIR, str(payload.get("source") or ""), str(payload.get("path") or ""),
                                   str(payload.get("folder") or ""))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/dataviz/batch/status")
def api_dataviz_batch_status():
    return dataviz_batch.status()


@router.get("/api/dataviz/batch/report/{batch_id}/{name}")
def api_dataviz_batch_report(batch_id: str, name: str):
    """קבצי הדוח (index.html, report.json, PNG) - רק מתוך תיקיית הדוח."""
    path = dataviz_batch.report_file(W.WORKSPACE_DIR, batch_id, name)
    if path is None:
        return JSONResponse({"error": "הקובץ לא נמצא."}, status_code=404)
    kind = {".png": "image/png", ".html": "text/html; charset=utf-8", ".json": "application/json"}[os.path.splitext(path)[1]]
    return FileResponse(path, media_type=kind)


@router.get("/api/dataviz/notify")
def api_dataviz_notify_status():
    """20.10.2026: האם מוגדר Discord webhook לסיום רינדור - בלי הכתובת עצמה."""
    return dataviz_notify.status()


@router.post("/api/dataviz/notify")
@W.limiter.limit("10/minute")
async def api_dataviz_notify_set(request: Request):
    """שומר את הכתובת כסוד (Credential Manager); ריק = מוחק."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        return dataviz_notify.set_url(payload.get("url"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/notify/test")
@W.limiter.limit("3/minute")
async def api_dataviz_notify_test(request: Request):
    """הודעת בדיקה לכתובת השמורה - רק בלחיצה של המשתמש."""
    payload, error = await _json_body(request)
    if error:
        return error
    url = dataviz_notify.get_url()
    if not url:
        return JSONResponse({"error": "לא הוגדרה כתובת."}, status_code=400)
    sent = await run_in_threadpool(dataviz_notify.send, url, "🔔 בדיקה מעורך הגרפים של ClipForge - ההתראות עובדות.")
    return {"ok": sent} if sent else JSONResponse({"error": "השליחה נכשלה - בדוק את הכתובת."}, status_code=502)


@router.get("/api/dataviz/story_templates")
def api_dataviz_story_templates():
    """20.10.2026: סוגי הסיפור לאשף (מרוץ, מגמה, השוואה, לפני-אחרי)."""
    return {"templates": dataviz_story_templates.templates()}


@router.get("/api/dataviz/story_suggest")
async def api_dataviz_story_suggest(episode: str = ""):
    """21.10.2026: סוג הסיפור שמוצע לפרק (העורך החכם) - הכלי נפתח עליו, ואפשר להחליף."""
    try:
        return await run_in_threadpool(dataviz_story_templates.suggest, _dataviz_dir(), episode)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/story_templates/{action}")
@W.limiter.limit("30/minute")
async def api_dataviz_story_template(request: Request, action: str):
    """20.10.2026: preview - מה התבנית תשנה (לפני / אחרי), בלי לכתוב; apply - מחיל לקובץ השינויים של הפרק."""
    payload, error = await _json_body(request)
    if error:
        return error
    if action not in ("preview", "apply"):
        return JSONResponse({"error": "פעולה לא מוכרת."}, status_code=404)
    args = (_dataviz_dir(), str(payload.get("episode", "")), payload.get("template"), payload.get("question") or "",
            payload.get("split"), payload.get("pick") if isinstance(payload.get("pick"), list) else None)
    try:
        return (dataviz_story_templates.preview if action == "preview" else dataviz_story_templates.apply)(*args)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    except (KeyError, ValueError, OSError) as e:   # 23.10.2026: נתונים שעוברים את הקונפיג ונכשלים בבנייה - 400 עם הסבר, לא 500
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)


@router.get("/api/dataviz/catalog")
def api_dataviz_catalog(q: str = "", lang: str = "he"):
    """20.10.2026: קטלוג מקורות הנתונים (למ"ס, הבנק העולמי, OECD) - רשימה קבועה עם חיפוש. בלי הורדה."""
    return {"items": dataviz_catalog.list_catalog(q, "en" if lang == "en" else "he")}   # 30.10.2026: בשפת הממשק


@router.post("/api/dataviz/catalog/fetch")
@W.limiter.limit("10/minute")
async def api_dataviz_catalog_fetch(request: Request):
    """20.10.2026: הורדה של סדרה מהקטלוג - רק בלחיצה, רק מהכתובת הקבועה שלה (לא מהבקשה), עד 5MB - לפרק חדש
    (target=new, עם SOURCES.md) או כמקור נוסף לפרק קיים (target=source, ל-data/dataviz_overrides/<פרק>/)."""
    payload, error = await _json_body(request)
    if error:
        return error
    lang = "en" if payload.get("lang") == "en" else "he"   # 30.10.2026: הלמ"ס בשפת הממשק
    try:
        if payload.get("target") == "source":
            result = dataviz_catalog.to_source(_dataviz_dir(), payload.get("id"), payload.get("episode"), lang=lang)
        else:
            result = dataviz_catalog.to_new_episode(_dataviz_dir(), payload.get("id"), payload.get("name"), payload.get("title"), lang=lang)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_catalog_fetch", details=f"{payload.get('id')} -> {payload.get('target') or 'new'}",
                              username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/delete")
@W.limiter.limit("20/minute")
async def api_dataviz_delete_episode(request: Request):
    """20.10.2026: "🗑️ מחק פרק" - הפרק, השינויים שלו, המטמון והרשומות שלו עוברים לסל של עורך הגרפים
    (data/dataviz_trash/<שם>_<זמן>/ עם manifest) - שום דבר לא נמחק. פרק שרץ או בתור - לא."""
    payload, error = await _json_body(request)
    if error:
        return error
    name = str(payload.get("episode", ""))
    if _episode_busy(name):
        return JSONResponse({"error": "הפרק רץ עכשיו או מחכה בתור - אפשר למחוק אחרי שהריצה מסתיימת."}, status_code=409)
    try:
        result = dataviz_trash.delete_episode(_dataviz_dir(), name)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_delete_episode", details=f"{name} -> {result['trash_id']}",
                              username=request.client.host if request.client else None)
    return result


@router.get("/api/dataviz/trash")
def api_dataviz_trash():
    """20.10.2026: הפרקים שבסל של עורך הגרפים (לשחזור)."""
    return {"items": dataviz_trash.list_trash(_dataviz_dir())}


@router.post("/api/dataviz/trash/restore")
@W.limiter.limit("20/minute")
async def api_dataviz_trash_restore(request: Request):
    """20.10.2026: "♻️ שחזר" - הכל חוזר למקום; שם תפוס = 409 ושום דבר לא זז."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        result = dataviz_trash.restore_episode(_dataviz_dir(), payload.get("id"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_restore_episode", details=result["name"], username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/trash/empty")
@W.limiter.limit("5/minute")
async def api_dataviz_trash_empty(request: Request):
    """20.10.2026: ריקון הסל - מחיקה אמיתית, רק עם confirm="empty" (אישור שני במסך)."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        result = dataviz_trash.empty_trash(_dataviz_dir(), payload.get("confirm"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_empty_trash", details=str(result["removed"]), username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/run")
@W.limiter.limit("10/minute")
async def api_dataviz_run(request: Request):
    """מריץ את dataviz_maker.py דרך אותו נתיב של /api/run (תור הרינדור, התקדמות, היסטוריית ריצות)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    from dataviz.charts import CHART_MODULES
    # גל 41: תור של כמה פרקים בריצה אחת (episodes), ויעד (youtube / shorts / tiktok)
    many = payload.get("episodes")
    if many is not None:
        if not isinstance(many, list) or not 1 <= len(many) <= 30 or not all(dataviz_episodes.episode_folder(_dataviz_dir(), str(n)) for n in many):
            return JSONResponse({"error": "רשימת פרקים לא תקינה."}, status_code=400)
        payload["episode"] = many[0]
    # 20.10.2026: גרסה של הפרק (dataviz/web/variants.py) - תמיד דרך התור (קובץ הבקרה אומר ל-dataviz_maker איזו גרסה),
    # עם היעד והשפה שלה אם לא נבחרו אחרים
    variant = str(payload.get("variant") or "")
    if variant:
        if many is not None:
            return JSONResponse({"error": "גרסה - פרק אחד בכל פעם."}, status_code=400)
        if dataviz_variants.load(_dataviz_dir(), str(payload.get("episode", "")), variant) is None:
            return JSONResponse({"error": "הגרסה לא נמצאה."}, status_code=404)
        settings = dataviz_variants.run_settings(_dataviz_dir(), str(payload.get("episode", "")), variant)
        payload["target"] = payload.get("target") or settings["target"]
        payload["lang"] = payload.get("lang") or settings["lang"]
        many = [str(payload.get("episode", ""))]
    target = payload.get("target") or ""
    if target and target not in ("youtube", "shorts", "tiktok"):
        return JSONResponse({"error": "יעד לא מוכר."}, status_code=400)
    lang = payload.get("lang") or ""
    if lang and lang not in ("en", "both"):
        return JSONResponse({"error": "שפה לא מוכרת."}, status_code=400)
    folder = dataviz_episodes.episode_folder(_dataviz_dir(), str(payload.get("episode", "")))
    mode = payload.get("mode")
    chart = payload.get("chart") or ""
    publish = payload.get("publish") or "default"
    if not folder:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    if mode not in W.DATAVIZ_MODES:
        return JSONResponse({"error": "מצב הרצה לא מוכר."}, status_code=400)
    if chart and chart not in CHART_MODULES:
        return JSONResponse({"error": "סוג תרשים לא מוכר."}, status_code=400)
    if publish not in ("default", "on", "off"):
        return JSONResponse({"error": "ערך פרסום לא מוכר."}, status_code=400)
    script_path = os.path.join(W.SCRIPTS_DIR, *SCRIPT_ID.split("/"))
    if not os.path.isfile(script_path):
        return JSONResponse({"error": "סקריפט סרטוני הנתונים לא נמצא."}, status_code=500)
    if W.worker.is_running:
        return JSONResponse({"error": "כבר יש ריצה פעילה - המתן לסיומה או עצור אותה."}, status_code=409)
    _RUN_EPISODES.clear()   # 20.10.2026: פרק שרץ (או בתור של הריצה) לא נמחק
    _RUN_EPISODES.update(str(n) for n in (many or [payload.get("episode")]))
    run_payload = {"dv_mode": mode, "dv_chart": chart, "dv_publish": publish, "run_label": f"📊 {payload.get('episode')} ({mode})"}
    if target:
        run_payload["dv_target"] = target
    if lang:
        run_payload["dv_lang"] = lang
    span = str(payload.get("range") or "")   # 27.10.2026: רינדור טווח - "START,END" (YYYY-MM-DD), רק במצב מלא או בדיקה
    if span:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2},\d{4}-\d{2}-\d{2}", span) or mode not in ("full", "test") or many:
            return JSONResponse({"error": "טווח לא תקין (שני תאריכים, פרק אחד, מצב מלא או בדיקה)."}, status_code=400)
        run_payload["dv_range"] = span
        run_payload["run_label"] = f"📊 {payload.get('episode')} ({span.replace(',', ' - ')})"
    if many:
        run_payload["dv_episodes"] = [str(n) for n in many]
        run_payload["run_label"] = f"📊 {len(many)} פרקים ({mode})"
        folder = dataviz_episodes.episodes_root(_dataviz_dir())
        # גל 44: התקדמות וביטול לכל פרק - הסקריפט כותב את המצב, המסך כותב מה לדלג
        status_path, control_path = _queue_paths()
        _write_queue_file(status_path, {"episodes": [{"name": str(n), "state": "pending", "pct": 0} for n in many]})
        _write_queue_file(control_path, {"skip": [], **({"variants": {many[0]: variant}} if variant else {})})
        if variant:
            run_payload["run_label"] = f"📊 {payload.get('episode')} · {variant} ({mode})"
        run_payload["dv_queue_file"] = status_path
    return W._start_script_run(script_path, folder, run_payload, request.client.host if request.client else None)


@router.get("/api/dataviz/outputs")
def api_dataviz_outputs(episode: str = ""):
    """התוצרים בתיקיות של _folders (תיקיית הייצוא, workspace והישנה): סרטונים (מלא/בדיקה/תצוגה מקדימה) ותיקיות סטילס, החדשים ראשונים.
    folder לכל תוצר (ל"פתח תיקייה"), ו-save_to - לאן נכתבים תוצרים חדשים עכשיו (שורת "נשמר ב-...").
    episode (אופציונלי) מסנן לשם הפרק (output_name של הפרק אינו נבדק - רק קידומת השם)."""
    rows = []
    folders = {}
    seen = set()
    for orientation, folder in ((o, f) for o in ORIENTATIONS for f in _folders(o)):
        if not os.path.isdir(folder):
            continue
        folders.setdefault(orientation, folder)
        for entry in os.scandir(folder):
            name = entry.name
            if name.startswith(".") or (episode and not (name == episode or name.startswith(episode + "_") or name.startswith(episode + "."))):
                continue
            if (orientation, name) in seen:   # אותו שם בתיקיית הייצוא וב-workspace - מגישים את הראשון (_inside_outputs), אז מציגים רק אותו
                continue
            seen.add((orientation, name))
            try:
                stat = entry.stat()
            except OSError:
                continue
            if entry.is_file(follow_symlinks=False) and name.endswith(".mp4"):
                package = os.path.isfile(os.path.join(folder, os.path.splitext(name)[0] + dataviz_publish.SIDECAR_SUFFIX))
                rows.append({"kind": "video", "orientation": orientation, "name": name, "mode": _video_mode(name),
                             "size": stat.st_size, "mtime": stat.st_mtime, "has_package": package, "folder": folder})
            elif entry.is_dir(follow_symlinks=False) and name.endswith(("_stills", "_share")):
                share = name.endswith("_share")   # גל 42: תמונה ו-GIF לשיתוף
                pngs = sorted(f for f in os.listdir(entry.path) if f.lower().endswith((".png", ".gif") if share else ".png"))
                rows.append({"kind": "stills", "orientation": orientation, "name": name, "mode": "share" if share else "stills",
                             "count": len(pngs), "files": pngs[:MAX_STILLS_LISTED], "mtime": stat.st_mtime, "folder": folder})
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return {"outputs": rows[:MAX_OUTPUTS], "folders": folders, "save_to": _save_to()}


def _serve(path, download):
    kind = "image/png" if path.lower().endswith(".png") else "image/gif" if path.lower().endswith(".gif") else "video/mp4"
    if download:
        return FileResponse(path, media_type=kind, filename=os.path.basename(path))
    return FileResponse(path, media_type=kind)


@router.get("/api/dataviz/episodes/captions")
def api_dataviz_captions(episode: str = "", mode: str = "full", download: int = 0):
    """גל 42: כתוביות SRT לפרק (אירועים ושיאים בזמנים של הסרטון) - מחושבות מהתכנית, בלי לרנדר."""
    from fastapi.responses import Response

    from dataviz.captions import episode_spans, to_srt
    from dataviz.config import ConfigError
    from dataviz.episode import load_episode
    from dataviz.plan import build_plan

    folder = dataviz_episodes.episode_folder(_dataviz_dir(), episode)
    if not folder:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    if mode not in ("full", "test", "preview"):
        return JSONResponse({"error": "מצב לא מוכר."}, status_code=400)
    try:
        loaded = load_episode(folder, dataviz_episodes.load_overrides_for_path(folder))
        config = loaded.config
        if mode == "preview":
            from dataviz.config import preview_config
            config = loaded.config = preview_config(config)
        spans = episode_spans(config, build_plan(loaded, mode), settings={**(config.get("captions") or {})})
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (OSError, ValueError, KeyError) as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=400)
    # 23.10.2026: שם פרק בעברית בכותרת נפל (רק latin-1 מותר) - 500. שם ASCII לגיבוי, והשם המלא ב-filename*
    from urllib.parse import quote
    fallback = re.sub(r"[^A-Za-z0-9_\-]", "_", episode) or "captions"
    headers = {"Content-Disposition": f"attachment; filename=\"{fallback}.srt\"; filename*=UTF-8''{quote(episode)}.srt"} if download else {}
    return Response(to_srt(spans), media_type="application/x-subrip; charset=utf-8", headers=headers)


_fonts_cache: dict = {}


@router.get("/api/dataviz/fonts")
def api_dataviz_fonts():
    """גל 43: הגופנים המותקנים שהמנוע (matplotlib) מכיר - לבחירת גופן בעורך הצבעים ובערכה."""
    if "fonts" not in _fonts_cache:
        from matplotlib import font_manager
        _fonts_cache["fonts"] = sorted({f.name for f in font_manager.fontManager.ttflist if f.name and not f.name.startswith(".")}, key=str.lower)
    return {"fonts": _fonts_cache["fonts"]}


_voices_cache: dict = {}


@router.get("/api/dataviz/voices")
def api_dataviz_voices():
    """גל 42: הקולות של Windows לקריינות (נבדק פעם אחת לכל הפעלה של השרת)."""
    if "voices" not in _voices_cache:
        from dataviz.narration import list_voices
        _voices_cache["voices"] = list_voices()
    return {"voices": _voices_cache["voices"]}


@router.get("/api/dataviz/help")
def api_dataviz_help(lang: str = "he"):
    """גל 42: מדריך המנוע - תרשימים, מצבים, יעדים, תוספות, כל ההגדרות ושורת הפקודה (dataviz/help.py).
    lang=en (גל 47) - באנגלית."""
    from dataviz.help import help_sections
    return {"sections": help_sections("en" if lang == "en" else "he")}


@router.get("/api/dataviz/media/{orientation}/{name}")
def api_dataviz_media(orientation: str, name: str, download: int = 0):
    """סרטון תוצר (תומך בטווחי בייטים לנגן, וב-download=1 להורדה)."""
    path = _safe_file(orientation, name) if name.endswith(".mp4") else None
    if not path:
        return JSONResponse({"error": "הקובץ לא נמצא."}, status_code=404)
    return _serve(path, download)


@router.get("/api/dataviz/media/{orientation}/{folder}/{name}")
def api_dataviz_still(orientation: str, folder: str, name: str, download: int = 0):
    """פריים סטילס (PNG) מתוך תיקיית <שם>_stills."""
    allowed = (folder.endswith("_stills") and name.lower().endswith(".png")) or (folder.endswith("_share") and name.lower().endswith((".png", ".gif")))
    path = _safe_file(orientation, folder, name) if allowed else None
    if not path:
        return JSONResponse({"error": "הקובץ לא נמצא."}, status_code=404)
    return _serve(path, download)


@router.post("/api/dataviz/episodes/create")
@W.limiter.limit("10/minute")
async def api_dataviz_create_episode(request: Request):
    """פרק חדש מ-CSV וטופס. מסרב לשם שכבר קיים (409) ולעולם לא דורס/מוחק פרק קיים."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    try:
        summary = dataviz_episodes.create_episode(_dataviz_dir(), payload)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_create_episode", details=summary["name"],
                              username=request.client.host if request.client else None)
    return summary


@router.get("/api/dataviz/episodes/import_suggestions")
def api_dataviz_import_suggestions():
    """19.10.2026: הפרקים המוכנים בתיקיית הטיוטה (workspace/dataviz/staging, או הישנה לפני ההעברה) - הצעות לייבוא."""
    return dataviz_episodes.import_suggestions(_dataviz_dir(), W.WORKSPACE_DIR)


@router.post("/api/dataviz/episodes/import_folder")
@W.limiter.limit("10/minute")
async def api_dataviz_import_folder(request: Request):
    """19.10.2026: "📂 ייבא תיקיית פרק" - עותק של תיקיית פרק מוכנה ל-data/dataviz_episodes (המקור רק נקרא, שם קיים = 409)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    try:
        summary = dataviz_episodes.import_episode_folder(_dataviz_dir(), payload.get("path"), payload.get("name"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_import_folder", details=summary["name"],
                              username=request.client.host if request.client else None)
    return summary


@router.post("/api/dataviz/smart/draft")
@W.limiter.limit("6/minute")
async def api_dataviz_smart_draft(request: Request):
    """20.10.2026: "📂→🎬 תיקייה ← טיוטת פרק" - פרק חדש מתיקייה (העתק של הקבצים הרלוונטיים; המקור רק נקרא) וטיוטה
    אוטומטית בקובץ השינויים: כל בחירה עם 🤖 סיבה וביטחון, ושאלה אחת כשהביטחון נמוך (dataviz/smart/create.py)."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.smart import create as smart_create
    path = str(payload.get("path") or "").strip().strip('"')
    if payload.get("use_config") and path and os.path.isfile(os.path.join(path, "config.yaml")):
        # 21.10.2026: "➕ פרק חדש" -> "📂 מתיקייה" עם config.yaml - הפרק המוכן מיובא כמו שהוא (מה שהיה "📂 ייבא תיקייה")
        try:
            summary = dataviz_episodes.import_episode_folder(_dataviz_dir(), path, payload.get("name"))
        except dataviz_episodes.EpisodeError as e:
            return JSONResponse({"error": str(e)}, status_code=e.status)
        W.audit_log.record_action("web", "dataviz_import_folder", details=summary["name"], username=request.client.host if request.client else None)
        return {"episode": summary["name"], "imported": True, "files": summary["files"]}
    try:
        record = await run_in_threadpool(smart_create.create_from_folder, _dataviz_dir(), payload.get("path"), payload.get("name"), True,
                                         payload.get("kit") or "")
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_smart_draft", details=record["episode"], username=request.client.host if request.client else None)
    return record


@router.get("/api/dataviz/smart/record")
def api_dataviz_smart_record(episode: str = ""):
    """הבחירות האוטומטיות של פרק (או {} כשהפרק לא נוצר מתיקייה)."""
    from dataviz.smart import create as smart_create
    if dataviz_episodes.episode_folder(_dataviz_dir(), episode) is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    return smart_create.load_record(_dataviz_dir(), episode) or {}


@router.post("/api/dataviz/smart/{action}")
@W.limiter.limit("60/minute")
async def api_dataviz_smart_action(request: Request, action: str):
    """undo {episode, path}: בחירה אוטומטית חוזרת לברירת המחדל; answer {episode, value}: התשובה לשאלה האחת."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.smart import create as smart_create
    from dataviz.smart import learn as smart_learn
    from dataviz.smart import watch as smart_watch
    episode = str(payload.get("episode", ""))
    try:
        if action == "watch":   # פריט 15: תיקייה במעקב (כבוי כברירת מחדל)
            return smart_watch.configure(_dataviz_dir(), bool(payload.get("enabled")), payload.get("root"), payload.get("interval_minutes", 30),
                                         payload.get("kit") or "")
        if action == "watch_check":
            done = await run_in_threadpool(smart_watch.check, _dataviz_dir(), W.WORKSPACE_DIR)
            return {"done": done, **smart_watch.status(_dataviz_dir())}
        if action == "prefs_reset":   # פריט 16
            return {"prefs": smart_learn.reset_prefs(_dataviz_dir(), str(payload.get("scope") or "") or None)}
        if action == "accept":   # 21.10.2026: "✓ מאשר" במסך הסקירה (path ריק = כל מה שעוד פתוח)
            return smart_create.accept(_dataviz_dir(), episode, str(payload.get("path", "")))
        if action == "undo":
            return smart_create.undo(_dataviz_dir(), episode, str(payload.get("path", "")))
        if action == "answer":
            return smart_create.answer(_dataviz_dir(), episode, payload.get("value"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    return JSONResponse({"error": "פעולה לא מוכרת."}, status_code=404)


@router.get("/api/dataviz/smart/settings")
def api_dataviz_smart_settings():
    """20.10.2026: התיקייה במעקב (פריט 15) וההעדפות שנלמדו (פריט 16)."""
    from dataviz.smart import learn as smart_learn
    from dataviz.smart import watch as smart_watch
    from dataviz.web.kits import load_kits
    return {"watch": smart_watch.status(_dataviz_dir()), "prefs": smart_learn.load_prefs(_dataviz_dir()), "kits": sorted(load_kits(_dataviz_dir()))}


@router.get("/api/dataviz/smart/thumbnail")
def api_dataviz_smart_thumbnail(episode: str = ""):
    from dataviz.smart import create as smart_create
    if dataviz_episodes.episode_folder(_dataviz_dir(), episode) is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    path = smart_create.thumbnail_path(_dataviz_dir(), episode)
    if not os.path.isfile(path):
        return JSONResponse({"error": "אין תמונה."}, status_code=404)
    return FileResponse(path, media_type="image/png")


@router.post("/api/dataviz/episodes/source_mapping")
@W.limiter.limit("30/minute")
async def api_dataviz_source_mapping(request: Request):
    """19.10.2026: מיפוי חדש למקור קיים - נכתב ל-override בלבד (config.yaml לא משתנה)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("mapping"), dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    name = str(payload.get("episode", ""))
    try:
        result = dataviz_data.update_source_mapping(_dataviz_dir(), name, payload.get("source"), payload["mapping"])
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_source_mapping", details=name, username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/hide")
@W.limiter.limit("30/minute")
async def api_dataviz_hide_episode(request: Request):
    """מסתיר פרק מהרשימה (או מחזיר אותו) - הפרק עצמו לא נמחק ולא זז, נשמר רק סימון בקובץ הסתרה נפרד."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("hidden"), bool):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    name = str(payload.get("episode", ""))
    try:
        hidden = dataviz_episodes.set_hidden(_dataviz_dir(), name, payload["hidden"])
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_hide_episode" if payload["hidden"] else "dataviz_unhide_episode", details=name,
                              username=request.client.host if request.client else None)
    return {"ok": True, "hidden": hidden}


@router.get("/api/dataviz/episodes/settings")
def api_dataviz_episode_settings(episode: str = ""):
    """ההגדרות הניתנות לעריכה של פרק: הערכים האפקטיביים + האם יש שינויים שמורים (קובץ override נפרד)."""
    folder = dataviz_episodes.episode_folder(_dataviz_dir(), episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    summary = next((e for e in dataviz_episodes.list_episodes(_dataviz_dir(), include_hidden=True) if e["name"] == episode), None)
    overrides = dataviz_episodes.load_overrides_for_path(folder)
    from dataviz.config import ConfigError, load_config
    try:
        config = load_config(os.path.join(folder, "config.yaml"), overrides)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    publish = config["publish"]
    return {"episode": episode, "edited": bool(overrides), "valid": bool(summary and summary.get("valid")),
            "settings": {"title": config["title"], "subtitle": config.get("subtitle", ""), "chart": config["chart"],
                         "theme": config["theme"], "top_n": config["ranking"]["top_n"],
                         "publish": {"enabled": bool(publish["enabled"]), "title": publish["title"],
                                     "description": publish["description"], "hashtags": list(publish["hashtags"])}}}


@router.post("/api/dataviz/episodes/settings")
@W.limiter.limit("30/minute")
async def api_dataviz_save_episode_settings(request: Request):
    """שומר שינויי הגדרות לפרק בקובץ override נפרד (config.yaml לא משתנה); settings=null מאפס."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not (payload.get("settings") is None or isinstance(payload.get("settings"), dict)):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    name = str(payload.get("episode", ""))
    try:
        saved = dataviz_episodes.set_overrides(_dataviz_dir(), name, payload.get("settings"))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_edit_episode" if saved else "dataviz_reset_episode", details=name,
                              username=request.client.host if request.client else None)
    return {"ok": True, "edited": bool(saved)}


# ---------- גל 38: תצוגה חיה ואומדן ----------

def _episode_for_preview(episode):
    folder = dataviz_episodes.episode_folder(_dataviz_dir(), episode)
    if folder is None:
        return None, None
    return folder, dataviz_episodes.load_overrides_for_path(folder)


def _preview_overrides(episode, chart="", theme="", title=None, subtitle=None, top_n=None, draft=""):
    """(תיקיית הפרק, השינויים כולל מה שעוד לא נשמר) לתצוגה החיה - או (None, תשובת שגיאה)."""
    from dataviz.charts import CHART_MODULES
    from dataviz.config import merge
    from dataviz.render import FLAGS_DIR_ENV
    # 27.10.2026: תיקיית הדגלים (images.flags) - המנוע קורא אותה ממשתנה סביבה; לפי ה-data_dir של עכשיו (טסטים מחליפים אותו)
    os.environ[FLAGS_DIR_ENV] = os.path.join(_dataviz_dir(), data_paths.DATAVIZ_FLAGS)
    folder, overrides = _episode_for_preview(episode)
    if folder is None:
        return None, JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    if (chart and chart not in CHART_MODULES) or (theme and theme not in dataviz_episodes.THEMES):
        return None, JSONResponse({"error": "סוג תרשים או ערכת צבעים לא מוכרים."}, status_code=400)
    basic = {key: value for key, value in (("title", title), ("subtitle", subtitle), ("top_n", top_n)) if value is not None}
    try:
        if basic:
            overrides = merge(overrides, dataviz_episodes.clean_overrides(basic))
        if draft:
            # גל 39: שינויים מהעורך המלא שעוד לא נשמרו - JSON של נתיב -> ערך, מאומתים כמו בשמירה
            changes = json.loads(draft)
            if not isinstance(changes, dict):
                raise dataviz_episodes.EpisodeError("טיוטה לא תקינה.")
            overrides = dataviz_episodes.draft_overrides(overrides, changes)
    except ValueError as e:
        return None, JSONResponse({"error": str(e) or "טיוטה לא תקינה."}, status_code=400)
    return folder, overrides


@router.get("/api/dataviz/preview_frame")
def api_dataviz_preview_frame(episode: str = "", pos: float = 0.6, chart: str = "", theme: str = "", scale: float = 0.35, mode: str = "full",
                              title: str | None = None, subtitle: str | None = None, top_n: int | None = None, draft: str = "",
                              target: str = "", version: str = "", meta: int = 0):
    """פריים בודד של הפרק בנקודה pos (0-1) - בלי לרנדר סרטון (utils/dataviz_preview.py). chart/theme
    מאפשרים להשוות סוגי תרשים וערכות צבע על אותו רגע; title/subtitle/top_n הם שינויים שעוד לא נשמרו
    (התצוגה מתעדכנת בזמן העריכה). שום דבר בתיקיית הפרק לא משתנה.
    27.10.2026: target (shorts / tiktok) - אותו רגע לאורך; version - גרסה מההיסטוריה (תמונה ממוזערת לכל גרסה);
    meta=1 - במקום התמונה, ה-JSON שלה: אזורי הלחיצה, התאריך ב-ISO, מלבן אזור הנתונים והגודל בנקודות."""
    from dataviz.config import ConfigError
    if target and target not in dataviz_preview.TARGETS:
        return JSONResponse({"error": "יעד לא מוכר."}, status_code=400)
    if version:
        folder, overrides = _version_overrides(episode, version)
    else:
        folder, overrides = _preview_overrides(episode, chart, theme, title, subtitle, top_n, draft)
    if folder is None:
        return overrides
    try:
        frame = dataviz_preview.preview_frame(folder, overrides, os.path.join(W.WORKSPACE_DIR, ".cache", "dataviz_previews"), pos,
                                              chart=chart or None, theme=theme or None, scale=scale, mode=mode, target=target)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (ValueError, KeyError, IndexError) as e:
        return JSONResponse({"error": f"התצוגה נכשלה: {e}"[:300]}, status_code=400)
    if meta:
        return {k: frame.get(k) for k in ("index", "frames", "kind", "date", "iso_date", "fps", "hits", "axes_box", "fig_pt", "axes")}
    from urllib.parse import quote
    return FileResponse(frame["path"], media_type="image/png", headers={
        "Cache-Control": "no-cache", "X-Frame-Index": str(frame["index"]), "X-Frame-Count": str(frame["frames"]), "X-Frame-Kind": frame["kind"],
        "X-Frame-Date": quote(str(frame.get("date") or "")), "X-Frame-Fps": str(frame.get("fps") or ""),   # גל 59: התאריך והזמן בסרטון
        "X-Frame-Axes": quote(json.dumps(frame.get("axes")))})   # 20.10.2026: לחיצה על התצוגה -> תאריך וערך


def _version_overrides(episode, version):
    """27.10.2026: (תיקיית הפרק, השינויים של גרסה מההיסטוריה) - לתמונה הממוזערת של הגרסה. או (None, תשובת שגיאה)."""
    folder, _current = _episode_for_preview(episode)
    if folder is None:
        return None, JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    if not re.fullmatch(r"[\w\-.]{1,80}", version):
        return None, JSONResponse({"error": "גרסה לא תקינה."}, status_code=400)
    snap = dataviz_history._load(_dataviz_dir(), episode, version)
    if snap is None:
        return None, JSONResponse({"error": "הגרסה לא נמצאה."}, status_code=404)
    return folder, dict(snap.get("overrides") or {})


# 20.10.2026: התצוגה החיה - מספר הבקשה האחרונה לכל פרק. בקשה ישנה רואה שיש חדשה יותר ומפסיקה בין פריימים
_LIVE_GENERATION: dict = {}
_LIVE = {"scale": 0.35, "fps": 12, "seconds": 3.0}   # כ-500 פיקסלים ברוחב, 12 פריימים לשנייה


@router.get("/api/dataviz/preview_clip")
def api_dataviz_preview_clip(episode: str = "", pos: float = 0.5, chart: str = "", theme: str = "", mode: str = "full",
                             title: str | None = None, subtitle: str | None = None, top_n: int | None = None, draft: str = "",
                             live: int = 0, format: str = "gif"):
    """גל 53: תצוגה מונפשת - GIF של 3 שניות ברזולוציה נמוכה סביב pos, מאותה תכנית (בלי לרנדר סרטון).
    20.10.2026: live=1 - הנגן החי בזמן עריכה: חד יותר (_LIVE), ובקשה שהוחלפה בחדשה נעצרת באמצע (409, superseded)."""
    from dataviz.config import ConfigError
    folder, overrides = _preview_overrides(episode, chart, theme, title, subtitle, top_n, draft)
    if folder is None:
        return overrides
    options: dict = {}
    if live:
        generation = _LIVE_GENERATION[episode] = _LIVE_GENERATION.get(episode, 0) + 1
        options = {**_LIVE, "cancel": lambda: _LIVE_GENERATION.get(episode) != generation}
    try:
        # 27.10.2026: format=mp4 - וידאו קצר (בכרטיס המסך כשאפשר) במקום GIF
        clip = dataviz_preview.preview_clip(folder, overrides, os.path.join(W.WORKSPACE_DIR, ".cache", "dataviz_previews"), pos,
                                            chart=chart or None, theme=theme or None, mode=mode,
                                            fmt="mp4" if format == "mp4" else "gif", ffmpeg=W.get_ffmpeg_exe() if format == "mp4" else "",
                                            **options)
    except dataviz_preview.PreviewCancelled:
        return JSONResponse({"error": "יש בקשה חדשה יותר.", "superseded": True}, status_code=409)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (ValueError, KeyError, IndexError) as e:
        return JSONResponse({"error": f"התצוגה נכשלה: {e}"[:300]}, status_code=400)
    return FileResponse(clip["path"], media_type="video/mp4" if clip.get("format") == "mp4" else "image/gif", headers={"Cache-Control": "no-cache"})


@router.get("/api/dataviz/preview_markers")
def api_dataviz_preview_markers(episode: str = "", mode: str = "full", draft: str = ""):
    """גל 53: הסימנים על הסליידר - אירועים, פרקים, עצירות, סוף הפתיח ותחילת הסיום (0-1)."""
    from dataviz.config import ConfigError
    folder, overrides = _preview_overrides(episode, draft=draft)
    if folder is None:
        return overrides
    try:
        return dataviz_preview.markers(folder, overrides, mode)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (ValueError, KeyError) as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=400)


@router.post("/api/dataviz/episodes/tags")
async def api_dataviz_episode_tags(request: Request):
    """גל 53: תגיות ותיקייה לפרק ברשימה (data/dataviz_tags.json - תיקיית הפרק לא משתנה)."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        return {"ok": True, **dataviz_episodes.set_tags(_dataviz_dir(), str(payload.get("episode", "")), payload.get("tags", []), payload.get("folder", ""))}
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/api/dataviz/estimate")
def api_dataviz_estimate(episode: str = ""):
    """אורך הסרטון וזמן רינדור משוער לכל מצב (מלא / בדיקה / תצוגה מקדימה), לפני שמריצים."""
    from dataviz.config import ConfigError
    from dataviz.render import default_workers
    folder, overrides = _episode_for_preview(episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    try:
        return dataviz_preview.estimate(folder, overrides, workers=default_workers(), stats_path=data_paths.path(data_paths.DATAVIZ_RENDER_STATS, _dataviz_dir()))
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (KeyError, ValueError, OSError) as e:   # 23.10.2026: נתונים שעוברים את הקונפיג ונכשלים בבנייה - 400 עם הסבר, לא 500
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)


# ---------- גל 39: עורך ההגדרות המלא ----------

@router.get("/api/dataviz/config_schema")
def api_dataviz_config_schema():
    """JSON Schema של config.yaml (dataviz/schema.py) - לכלים חיצוניים ולעורכים."""
    from dataviz import schema
    return schema.json_schema()


@router.get("/api/dataviz/episodes/editor")
def api_dataviz_episode_editor(episode: str = "", lang: str = "he"):
    """הכל לעורך: הטופס לפי קבוצות (ערך / ברירת מחדל / בקובץ / שונה כאן), אירועים, צבעים, ישויות ומה ששונה."""
    from dataviz.config import ConfigError
    folder, overrides = _episode_for_preview(episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    try:
        overview = dataviz_preview.episode_overview(folder, overrides)
        return dataviz_episodes.editor_data(_dataviz_dir(), episode, overview["entities"], overview["date_range"], "en" if lang == "en" else "he")
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    except (ConfigError, ValueError, KeyError, OSError) as e:   # 23.10.2026: גם KeyError / OSError מנתונים שלא נבנים - 400
        return JSONResponse({"error": str(e)[:300]}, status_code=400)


@router.get("/api/dataviz/episodes/final_config")
def api_dataviz_episode_final_config(episode: str = ""):
    """ההגדרות הסופיות שהרינדור יקבל (config.yaml + שינויים מהדפדפן + ברירות מחדל), ולכל הגדרה מאיפה היא - לקריאה בלבד."""
    try:
        return dataviz_episodes.final_config(_dataviz_dir(), episode)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/episodes/override")
@W.limiter.limit("60/minute")
async def api_dataviz_episode_override(request: Request):
    """שינוי שדות בודדים (set: נתיב -> ערך, unset: נתיבים) בקובץ ה-override של הפרק - config.yaml לא משתנה."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or not isinstance(payload.get("set") or {}, dict) or not isinstance(payload.get("unset") or [], list):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    name = str(payload.get("episode", ""))
    try:
        saved = dataviz_episodes.update_override_fields(_dataviz_dir(), name, payload.get("set") or {}, payload.get("unset") or [])
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_edit_episode", details=name, username=request.client.host if request.client else None)
    return {"ok": True, "edited": bool(saved)}


# ---------- גל 40: נתונים, בדיקות, קצב ומוזיקה ----------

_DATA_PARTS = {
    "sources": lambda folder, ov, source: dataviz_data.sources_overview(folder, ov),
    "check": lambda folder, ov, source: dataviz_data.data_check(folder, ov),
    "cumulative": lambda folder, ov, source: dataviz_data.cumulative_table(folder, ov),
    "pacing": lambda folder, ov, source: dataviz_data.pacing(folder, ov),
    "spread": lambda folder, ov, source: dataviz_data.spread_preview(folder, ov, source),
    "music": lambda folder, ov, source: dataviz_data.music_info(folder, ov),
    "clean": lambda folder, ov, source: dataviz_data.cleaning_report(folder, ov),   # גל 52
    "table": lambda folder, ov, source: dataviz_data.source_table(folder, ov, source),   # 20.10.2026: עריכה בטבלה
    "facts": lambda folder, ov, source: dataviz_factcheck.fact_check(folder, ov),   # 20.10.2026: בדיקת עובדות
}


@router.get("/api/dataviz/episodes/data")
def api_dataviz_episode_data(episode: str = "", part: str = "sources", source: int = 0):
    """הנתונים של פרק לפי חלק: מקורות (מיפוי ו-20 שורות), בדיקה, מצטבר, קצב, פיזור או מוזיקה."""
    from dataviz.config import ConfigError
    folder, overrides = _episode_for_preview(episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    if part not in _DATA_PARTS:
        return JSONResponse({"error": "חלק לא מוכר."}, status_code=400)
    try:
        return {"part": part, "data": _DATA_PARTS[part](folder, overrides, source)}
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    except (ConfigError, KeyError, ValueError, OSError) as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=400)


@router.get("/api/dataviz/episodes/waveform")
def api_dataviz_episode_waveform(episode: str = "", file: str = ""):
    """גרף גלי הקול של קובץ מוזיקה מתיקיית הפרק - לבחירת נקודת ההתחלה."""
    folder, _overrides = _episode_for_preview(episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    try:
        return dataviz_data.waveform(folder, file)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/convert_table")
@W.limiter.limit("30/minute")
async def api_dataviz_convert_table(request: Request):
    """Excel / JSON / CSV (base64) -> טקסט CSV ועמודות, לפרק חדש מקובץ (גם כשגוררים קובץ למסך)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    try:
        return dataviz_data.table_to_csv(str(payload.get("filename", "")), str(payload.get("data_base64", "")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/episodes/update_data")
@W.limiter.limit("20/minute")
async def api_dataviz_update_data(request: Request):
    """נתונים חדשים לפרק קיים: בלי confirm - רק השוואת סכומים לפני/אחרי; עם confirm - נשמר כקובץ חדש
    (הקובץ המקורי בתיקיית הפרק לא משתנה) וה-override מפנה אליו."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    name = str(payload.get("episode", ""))
    try:
        source = int(payload.get("source", 0) or 0)
    except (TypeError, ValueError):   # 23.10.2026: קודם int() מחוץ ל-try - 500
        return JSONResponse({"error": "מקור לא תקין."}, status_code=400)
    try:
        result = dataviz_data.update_data(_dataviz_dir(), name, source, str(payload.get("csv_text", "")), bool(payload.get("confirm")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    if result.get("saved"):
        W.audit_log.record_action("web", "dataviz_update_data", details=f"{name}: {result.get('file')}",
                                  username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/add_source")
@W.limiter.limit("20/minute")
async def api_dataviz_add_source(request: Request):
    """18.10.2026: קובץ נתונים נוסף לפרק קיים (מקור חדש עם מיפוי משלו). בלי confirm - רק השוואת סכומים;
    עם confirm - נשמר כקובץ חדש וה-override מוסיף אותו (תיקיית הפרק ו-config.yaml לא משתנים)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    name = str(payload.get("episode", ""))
    try:
        result = dataviz_data.add_source(_dataviz_dir(), name, str(payload.get("filename", "")), payload.get("csv_text"), payload, bool(payload.get("confirm")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    if result.get("saved"):
        W.audit_log.record_action("web", "dataviz_add_source", details=f"{name}: {result.get('file')}",
                                  username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/remove_source")
@W.limiter.limit("20/minute")
async def api_dataviz_remove_source(request: Request):
    """18.10.2026: מסיר מקור שנוסף מהדפדפן - רק מה-override; הקובץ שלו נשאר בדיסק בלי שינוי."""
    payload, error = await _json_body(request)
    if error:
        return error
    name = str(payload.get("episode", ""))
    try:
        index = int(payload.get("source", -1))
    except (TypeError, ValueError):
        return JSONResponse({"error": "מקור לא תקין."}, status_code=400)
    try:
        result = dataviz_data.remove_source(_dataviz_dir(), name, index)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_remove_source", details=f"{name}: {index + 1} {result.get('kept')}",
                              username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/set_weights")
@W.limiter.limit("20/minute")
async def api_dataviz_set_weights(request: Request):
    """18.10.2026: קובץ משקלות (spread.weights) למקור של חודש/שנה - נבדק, נשמר כקובץ חדש וה-override מפנה אליו."""
    payload, error = await _json_body(request)
    if error:
        return error
    name = str(payload.get("episode", ""))
    try:
        index = int(payload.get("source", -1))
    except (TypeError, ValueError):
        return JSONResponse({"error": "מקור לא תקין."}, status_code=400)
    try:
        result = dataviz_data.set_weights(_dataviz_dir(), name, index, str(payload.get("filename", "")), payload.get("csv_text"), payload)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_set_weights", details=f"{name}: {index + 1} {result.get('file')}",
                              username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/remove_weights")
@W.limiter.limit("20/minute")
async def api_dataviz_remove_weights(request: Request):
    """18.10.2026: מסיר קובץ משקלות שנוסף מהדפדפן - רק מה-override; הקובץ נשאר בדיסק בלי שינוי."""
    payload, error = await _json_body(request)
    if error:
        return error
    name = str(payload.get("episode", ""))
    try:
        index = int(payload.get("source", -1))
    except (TypeError, ValueError):
        return JSONResponse({"error": "מקור לא תקין."}, status_code=400)
    try:
        result = dataviz_data.remove_weights(_dataviz_dir(), name, index)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_remove_weights", details=f"{name}: {index + 1} {result.get('kept')}",
                              username=request.client.host if request.client else None)
    return result


# ---------- גל 41: שכפול וסדרה, ערכות ערוץ, סל מיחזור לתוצרים ----------

async def _json_body(request: Request):
    if not W._is_same_origin(request):
        return None, JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        return None, JSONResponse({"error": "בקשה לא תקינה."}, status_code=400)
    return payload, None


@router.post("/api/dataviz/episodes/duplicate")
@W.limiter.limit("20/minute")
async def api_dataviz_duplicate(request: Request):
    """עותק של פרק בשם חדש (next=true: הפרק הבא בסדרה). הפרק המקורי לא משתנה."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        summary = dataviz_episodes.duplicate_episode(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("name", "")), bool(payload.get("next")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    W.audit_log.record_action("web", "dataviz_duplicate_episode", details=f"{payload.get('episode')} -> {summary['name']}",
                              username=request.client.host if request.client else None)
    return summary


@router.get("/api/dataviz/kits")
def api_dataviz_kits():
    """ערכות הערוץ, ושמות ה"מיתוג" של עורך-העל שאפשר לייבא מהם."""
    from utils import brand_kits
    return {"kits": dataviz_kits.kits_summary(_dataviz_dir()), "brand_kits": sorted(brand_kits.load_kits().keys())}


@router.post("/api/dataviz/kits/save")
async def api_dataviz_kit_save(request: Request):
    """ערכה חדשה (או עדכון) - מפרק קיים (episode) או ממיתוג של עורך-העל (brand_kit)."""
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        if payload.get("brand_kit"):
            from utils import brand_kits
            brand = brand_kits.load_kits().get(str(payload["brand_kit"]))
            if brand is None:
                return JSONResponse({"error": "המיתוג לא נמצא."}, status_code=404)
            kit = dataviz_kits.kit_from_brand(brand)
        else:
            kit = dataviz_kits.kit_from_episode(_dataviz_dir(), str(payload.get("episode", "")))
        saved = dataviz_kits.save_kit(_dataviz_dir(), str(payload.get("name", "")), kit)
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    return {"ok": True, "kit": saved}


@router.post("/api/dataviz/kits/apply")
async def api_dataviz_kit_apply(request: Request):
    payload, error = await _json_body(request)
    if error:
        return error
    try:
        dataviz_kits.apply_kit(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("name", "")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    return {"ok": True}


@router.post("/api/dataviz/kits/delete")
async def api_dataviz_kit_delete(request: Request):
    payload, error = await _json_body(request)
    if error:
        return error
    if not dataviz_kits.delete_kit(_dataviz_dir(), str(payload.get("name", ""))):
        return JSONResponse({"error": "הערכה לא נמצאה."}, status_code=404)
    return {"ok": True}


@router.post("/api/dataviz/outputs/trash")
@W.limiter.limit("30/minute")
async def api_dataviz_output_trash(request: Request):
    """תוצר (סרטון עם החבילה והתמונה שלו, או תיקיית סטילס) עובר לסל המיחזור של המחשב - אפשר לשחזר משם."""
    payload, error = await _json_body(request)
    if error:
        return error
    orientation, name = str(payload.get("orientation", "")), str(payload.get("name", ""))
    if orientation not in ORIENTATIONS or not name or name.startswith(".") or not _SAFE_NAME.match(name):
        return JSONResponse({"error": "תוצר לא תקין."}, status_code=400)
    _base, target = _inside_outputs(orientation, name, exists=os.path.exists)
    if not target:
        return JSONResponse({"error": "התוצר לא נמצא."}, status_code=404)
    if os.path.isdir(target) and not name.endswith(("_stills", "_share")):
        return JSONResponse({"error": "תוצר לא תקין."}, status_code=400)
    from send2trash import send2trash
    victims = [target]
    if name.endswith(".mp4"):
        stem = target[:-4]
        companions = (stem + dataviz_publish.SIDECAR_SUFFIX, stem + "_metadata_seo.txt", stem + "_thumb.jpg", stem + ".srt", stem + ".chapters.txt",
                      stem + "_thumb_original.jpg", *(f"{stem}_thumb_c{i}.jpg" for i in range(1, 4)))
        victims += [p for p in companions if os.path.exists(p)]
    for victim in victims:
        send2trash(victim)
    W.audit_log.record_action("web", "dataviz_trash_output", details=f"{orientation}/{name}", username=request.client.host if request.client else None)
    return {"ok": True, "trashed": [os.path.basename(v) for v in victims]}


@router.post("/api/dataviz/outputs/studio")
@W.limiter.limit("30/minute")
async def api_dataviz_output_to_studio(request: Request):
    """גל 56: סרטון מוכן נפתח בסטודיו - בתיקייה משלו (utils/dataviz_handoff.py). התוצר עצמו לא זז ולא משתנה."""
    payload, error = await _json_body(request)
    if error:
        return error
    orientation, name = str(payload.get("orientation", "")), str(payload.get("name", ""))
    source = _safe_file(orientation, name) if name.endswith(".mp4") else None
    if not source:
        return JSONResponse({"error": "הסרטון לא נמצא."}, status_code=404)
    try:
        result = dataviz_handoff.studio_folder(source, dataviz_handoff.studio_root(W.WORKSPACE_DIR, orientation))
    except OSError as e:
        return JSONResponse({"error": f"הכנת התיקייה לסטודיו נכשלה: {e}"}, status_code=500)
    W.audit_log.record_action("web", "dataviz_to_studio", details=f"{orientation}/{name}", username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/csv_columns")
async def api_dataviz_csv_columns(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    """כותרות העמודות של CSV שנבחר בדפדפן (לא נכתב דבר) - למילוי רשימות הבחירה בטופס."""
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    text = payload.get("csv_text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > dataviz_episodes.CSV_MAX_BYTES:
        return JSONResponse({"error": f"קובץ CSV ריק או גדול מ-{dataviz_episodes.CSV_MAX_MB}MB."}, status_code=400)
    try:
        return {"columns": dataviz_episodes.csv_columns(text)}
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/api/dataviz/episodes/smart_guess")
async def api_dataviz_smart_guess(request: Request):
    """23.10.2026 (המלצה 5): הניחוש של העורך החכם לטופס "מקבצים" - כמות / רמה, ציר, תרשים וכותרת (לא נכתב דבר)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = None
    files = payload.get("files") if isinstance(payload, dict) else None
    if (not isinstance(files, list) or not 1 <= len(files) <= dataviz_episodes.MAX_EXTRA_SOURCES + 1
            or not all(isinstance(f, dict) and isinstance(f.get("csv_text"), str) and f["csv_text"].strip()
                       and len(f["csv_text"].encode("utf-8")) <= dataviz_episodes.CSV_MAX_BYTES for f in files)):
        return JSONResponse({"error": f"קובץ CSV ריק או גדול מ-{dataviz_episodes.CSV_MAX_MB}MB."}, status_code=400)
    from dataviz.smart.draft import guess_files
    try:
        return await run_in_threadpool(guess_files, files)
    except Exception as e:   # ניחוש הוא תוספת - הטופס עובד גם בלעדיו
        return JSONResponse({"error": f"הניחוש נכשל: {str(e)[:200]}"}, status_code=400)


# ---------- גל 44: תמונות מועמדות, הצעה מ-Gemini, צפיות ותור פרקים ----------
@router.post("/api/dataviz/packages/{orientation}/{name}/thumbnail_candidates")
@W.limiter.limit("10/minute")
async def api_dataviz_thumb_candidates(orientation: str, name: str, request: Request):
    """שלוש תמונות ממוזערות מועמדות מהסרטון (ffmpeg, פריים אחד לכל אחת) - לבחירה באשף."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    from utils.ffmpeg_locator import get_ffmpeg_exe, get_ffprobe_exe
    try:
        names = dataviz_publish.thumbnail_candidates(path, ffmpeg=get_ffmpeg_exe(), ffprobe=get_ffprobe_exe())
    except (OSError, ValueError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "candidates": [int(n.rsplit("_c", 1)[1][0]) for n in names]}


@router.get("/api/dataviz/packages/{orientation}/{name}/thumbnail_candidate/{k}")
def api_dataviz_thumb_candidate(orientation: str, name: str, k: int):
    path = _sidecar(orientation, name)
    if not path or k not in (1, 2, 3):
        return JSONResponse({"error": "לא נמצא."}, status_code=404)
    full = os.path.join(os.path.dirname(path), dataviz_publish.candidate_name(name, k))
    if not os.path.isfile(full):
        return JSONResponse({"error": "לא נמצא."}, status_code=404)
    return FileResponse(full, media_type="image/jpeg", headers={"Cache-Control": "no-cache"})


@router.post("/api/dataviz/packages/{orientation}/{name}/thumbnail_choose")
async def api_dataviz_thumb_choose(orientation: str, name: str, request: Request):
    payload, error = await _json_body(request)
    if error:
        return error
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        dataviz_publish.choose_thumbnail(path, int(payload.get("candidate") or 0))
    except (OSError, ValueError, TypeError) as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True}


@router.post("/api/dataviz/packages/{orientation}/{name}/suggest")
@W.limiter.limit("6/minute")
async def api_dataviz_suggest(orientation: str, name: str, request: Request):
    """הצעת כותרת, תיאור ותגיות מ-Gemini לסרטון (לא נשמר - האשף ממלא את השדות)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        return {"ok": True, "suggestion": dataviz_publish.suggest_metadata(path)}
    except Exception as e:   # בלי מפתח / מכסה / רשת - הודעה ברורה במקום קריסה
        return JSONResponse({"error": "Gemini לא החזיר הצעה: " + str(e)[:200]}, status_code=400)


@router.post("/api/dataviz/packages/{orientation}/{name}/stats")
@W.limiter.limit("20/minute")
async def api_dataviz_stats(orientation: str, name: str, request: Request):
    """צפיות, לייקים ותגובות של הסרטון שהועלה ליוטיוב - רק בלחיצה, ונשמר בחבילה."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    path = _sidecar(orientation, name)
    if not path:
        return JSONResponse({"error": "החבילה לא נמצאה."}, status_code=404)
    try:
        package = dataviz_publish.load_package(path)
    except (OSError, ValueError):
        return JSONResponse({"error": "קובץ הפרסום פגום."}, status_code=400)
    video_id = ((package.get("sent") or {}).get("youtube") or {}).get("video_id")
    if not video_id:
        return JSONResponse({"error": "הסרטון עוד לא הועלה ליוטיוב."}, status_code=400)
    from utils import youtube_uploader
    if not os.path.isfile(youtube_uploader.TOKEN_FILE):
        return JSONResponse({"error": "אין חיבור ליוטיוב במחשב הזה."}, status_code=400)
    try:
        from utils.youtube_analytics import get_video_stats
        stats = get_video_stats(video_id)
    except Exception as e:
        return JSONResponse({"error": "יוטיוב לא החזיר נתונים: " + str(e)[:200]}, status_code=400)
    if stats is None:
        return JSONResponse({"error": "הסרטון לא נמצא ביוטיוב."}, status_code=404)
    package = dataviz_publish.record_stats(path, stats)
    return {"ok": True, "stats": package["stats"]}


@router.get("/api/dataviz/series_board")
def api_dataviz_series_board():
    """גל 55: לוח צפיות לפי סדרה - לכל פרק: המספר בסדרה, הצפיות / לייקים / תגובות האחרונים, וההיסטוריה (כל
    "רענן צפיות"). מחבילות הפרסום של הסרטונים המלאים - שום דבר לא נשלח ליוטיוב מכאן."""
    episodes = dataviz_episodes.list_episodes(_dataviz_dir())
    packages = []
    for orientation in ORIENTATIONS:
        for folder in _folders(orientation):
            for package in dataviz_publish.list_packages(folder) if os.path.isdir(folder) else []:
                packages.append({**package, "orientation": orientation})
    series: dict = {}
    for ep in episodes:
        uploaded = lambda p: bool(((p.get("sent") or {}).get("youtube") or {}).get("video_id"))  # noqa: E731
        mine = [p for p in packages if str(p.get("video") or "").startswith(ep["name"]) and (p.get("stats") or uploaded(p))]
        if not mine:
            continue
        latest = max(mine, key=lambda p: str((p.get("stats") or {}).get("at") or ""))
        name = str((ep.get("series") or {}).get("name") or "")
        series.setdefault(name, []).append({
            "episode": ep["name"], "title": ep.get("title") or ep["name"], "number": int((ep.get("series") or {}).get("number") or 0),
            "stats": latest.get("stats") or {}, "history": [[h.get("at"), int(h.get("views") or 0)] for h in latest.get("stats_history") or []],
            "package": {"orientation": latest["orientation"], "name": os.path.basename(latest["path"])[: -len(dataviz_publish.SIDECAR_SUFFIX)]}})
    return {"series": [{"name": name, "episodes": sorted(items, key=lambda e: (e["number"], e["title"]))}
                       for name, items in sorted(series.items(), key=lambda kv: (kv[0] == "", kv[0]))]}


QUEUE_FILENAME = data_paths.DATAVIZ_QUEUE


def _queue_paths():
    status = os.path.join(_dataviz_dir(), QUEUE_FILENAME)
    return status, status[: -len(".json")] + ".control.json"


def _read_json_file(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


@router.get("/api/dataviz/queue")
def api_dataviz_queue():
    """גל 44: מצב תור הפרקים של הריצה האחרונה - לכל פרק: ממתין / רץ (עם אחוז) / הסתיים / דולג / נכשל."""
    status_path, control_path = _queue_paths()
    status = _read_json_file(status_path, {})
    control = _read_json_file(control_path, {})
    return {"episodes": status.get("episodes", []) if isinstance(status, dict) else [],
            "skip": control.get("skip", []) if isinstance(control, dict) else []}


@router.post("/api/dataviz/queue/skip")
async def api_dataviz_queue_skip(request: Request):
    """פרק בתור שלא ירונדר (ואם הוא רץ עכשיו - נעצר והתוצר החלקי נמחק); שאר התור ממשיך."""
    payload, error = await _json_body(request)
    if error:
        return error
    name = str(payload.get("episode", ""))
    status_path, control_path = _queue_paths()
    status = _read_json_file(status_path, {})
    names = [e.get("name") for e in (status.get("episodes", []) if isinstance(status, dict) else [])]
    if name not in names:
        return JSONResponse({"error": "הפרק לא בתור."}, status_code=404)
    control = _read_json_file(control_path, {})
    skip = sorted(set((control.get("skip") or []) if isinstance(control, dict) else []) | {name})
    _write_queue_file(control_path, {"skip": skip})
    return {"ok": True, "skip": skip}


def _write_queue_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


# ---------- גל 45: ספריית מפות והקלטות קריינות ----------
def _library_error(e):
    return JSONResponse({"error": str(e)}, status_code=getattr(e, "status", 400))


@router.get("/api/dataviz/maps")
def api_dataviz_maps():
    """המפות בספרייה (data/dataviz_maps/), עם המאפיינים של האזורים וערכים לדוגמה."""
    from dataviz.web import library as lib
    return {"maps": [{k: v for k, v in m.items() if k != "path"} for m in lib.list_maps(_dataviz_dir())]}


@router.post("/api/dataviz/maps/upload")
@W.limiter.limit("10/minute")
async def api_dataviz_maps_upload(request: Request):
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        saved = lib.save_map(_dataviz_dir(), str(payload.get("filename", "")), payload.get("text"))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    return {"ok": True, "name": saved["name"]}


@router.get("/api/dataviz/maps/match")
def api_dataviz_maps_match(episode: str = "", name: str = "", key: str = "name", projection: str = "mercator"):
    from dataviz.web import library as lib
    if projection not in ("mercator", "equirect"):
        return JSONResponse({"error": "הטלה לא מוכרת."}, status_code=400)
    try:
        return lib.map_match(_dataviz_dir(), episode, name, key, projection)
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)


@router.post("/api/dataviz/maps/use")
async def api_dataviz_maps_use(request: Request):
    """הפרק משתמש במפה מהספרייה (נשמר בקובץ השינויים שלו: map.geojson ו-map.key)."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        lib.use_map(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("name", "")), str(payload.get("key", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    return {"ok": True}


@router.get("/api/dataviz/episodes/recordings")
def api_dataviz_recordings(episode: str = ""):
    from dataviz.web import library as lib
    try:
        return {"recordings": lib.list_recordings(_dataviz_dir(), episode)}
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)


@router.post("/api/dataviz/episodes/recordings")
@W.limiter.limit("30/minute")
async def api_dataviz_recordings_save(request: Request):
    """הקלטת קריינות לאירוע (מהמיקרופון בדפדפן) - קובץ חדש תחת data/dataviz_overrides/<פרק>/narration/."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        saved = lib.save_recording(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("date", "")),
                                   str(payload.get("ext", "")), str(payload.get("data_base64", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    return {"ok": True, **saved}


@router.get("/api/dataviz/episodes/recording")
def api_dataviz_recording(episode: str = "", name: str = ""):
    from dataviz.web import library as lib
    try:
        path = lib.recording_path(_dataviz_dir(), episode, name)
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    kinds = {".webm": "audio/webm", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav",
             ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac"}
    return FileResponse(path, media_type=kinds.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))


@router.post("/api/dataviz/episodes/recordings/trash")
async def api_dataviz_recordings_trash(request: Request):
    """הקלטה עוברת לסל המיחזור (אפשר לשחזר) - האירוע חוזר להקלטה הקודמת או לקול של Windows."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        path = lib.recording_path(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("name", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    from send2trash import send2trash
    send2trash(path)
    return {"ok": True}


# ---------- גל 52: מקורות מכתובת, רענון ותזמון ----------
@router.get("/api/dataviz/episodes/remote")
def api_dataviz_remote(episode: str = ""):
    from dataviz.web import remote as dataviz_remote
    try:
        return dataviz_remote.remote_overview(_dataviz_dir(), episode)
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)


@router.post("/api/dataviz/episodes/url_source")
@W.limiter.limit("10/minute")
async def api_dataviz_url_source(request: Request):
    """מקור נתונים חדש מכתובת (או Google Sheets משותף) - מורד עכשיו, בלחיצה הזו, ונשמר בקובץ השינויים של הפרק."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import remote as dataviz_remote
    try:
        result = dataviz_remote.add_url_source(_dataviz_dir(), str(payload.get("episode", "")), payload)
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    W.audit_log.record_action("web", "dataviz_url_source", details=str(payload.get("episode", ""))[:80], username=request.client.host if request.client else None)
    return result


@router.post("/api/dataviz/episodes/refresh")
@W.limiter.limit("20/minute")
async def api_dataviz_refresh(request: Request):
    """מוריד מחדש את המקורות מכתובת של הפרק (רק בלחיצה) ומחזיר מה השתנה."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import remote as dataviz_remote
    try:
        return dataviz_remote.refresh_sources(_dataviz_dir(), str(payload.get("episode", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)


@router.post("/api/dataviz/schedule")
async def api_dataviz_schedule(request: Request):
    """משימה מתוזמנת לפרק (מנוהלת במסך ה-Scheduler): רינדור בשעה קבועה, ואם רוצים - רענון הנתונים קודם, ודילוג
    כשהם לא השתנו. הארגומנטים מרשימה סגורה בלבד."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import remote as dataviz_remote
    episode = str(payload.get("episode", ""))
    folder = dataviz_episodes.episode_folder(_dataviz_dir(), episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    schedule_type = str(payload.get("schedule_type", "daily"))
    if schedule_type not in W.scheduler_store.VALID_SCHEDULE_TYPES:
        return JSONResponse({"error": "סוג תזמון לא מוכר."}, status_code=400)
    time_str = str(payload.get("time_str", "03:00")).strip() or "03:00"
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_str):
        return JSONResponse({"error": "שעה לא תקינה (HH:MM)."}, status_code=400)
    weekday = str(payload.get("weekday", "sun"))
    if weekday not in W.scheduler_store.WEEKDAYS:
        return JSONResponse({"error": "יום לא תקין."}, status_code=400)
    try:
        interval_hours = max(1, min(24 * 30, int(payload.get("interval_hours", 24) or 24)))
        args = dataviz_remote.schedule_args(episode, str(payload.get("mode", "full")), payload.get("refresh") is True, payload.get("only_if_changed") is True)
    except (TypeError, ValueError) as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=400)
    script_path = os.path.join(W.SCRIPTS_DIR, *SCRIPT_ID.split("/"))
    task = W.scheduler_store.add_task(script_path, schedule_type, time_str=time_str, weekday=weekday, interval_hours=interval_hours,
                                      folder=dataviz_episodes.episodes_root(_dataviz_dir()), extra_args=args, label=f"📊 {episode}")
    W.audit_log.record_action("web", "scheduler_task_add", details=f"dataviz {episode}", username=request.client.host if request.client else None)
    return {"ok": True, "id": task["id"], "schedules": dataviz_remote.schedules_for(episode)}


# ---------- גל 51: תמונה לכל ישות ----------
@router.get("/api/dataviz/episodes/images")
def api_dataviz_images(episode: str = ""):
    from dataviz.web import library as lib
    try:
        return {"images": lib.list_images(_dataviz_dir(), episode)}
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)


@router.post("/api/dataviz/episodes/images")
@W.limiter.limit("60/minute")
async def api_dataviz_images_save(request: Request):
    """תמונה לישות (מהדפדפן) - קובץ חדש תחת data/dataviz_overrides/<פרק>/images/."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        saved = lib.save_image(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("entity", "")),
                               str(payload.get("ext", "")), str(payload.get("data_base64", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    return {"ok": True, **saved}


@router.get("/api/dataviz/episodes/image")
def api_dataviz_image(episode: str = "", name: str = ""):
    from dataviz.web import library as lib
    try:
        path = lib.image_path(_dataviz_dir(), episode, name)
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    kinds = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return FileResponse(path, media_type=kinds.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))


@router.post("/api/dataviz/episodes/images/trash")
async def api_dataviz_images_trash(request: Request):
    """תמונה עוברת לסל המיחזור (אפשר לשחזר) - הישות חוזרת לתמונה הקודמת או לבלי תמונה."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        path = lib.image_path(_dataviz_dir(), str(payload.get("episode", "")), str(payload.get("name", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    from send2trash import send2trash
    send2trash(path)
    return {"ok": True}


@router.get("/api/dataviz/maps/ready")
def api_dataviz_maps_ready():
    """גל 46: קטלוג המפות המוכנות (מחוזות ונפות בישראל, מדינות העולם) ומה מהן כבר בספרייה."""
    from dataviz.web import library as lib
    return {"maps": lib.ready_maps(_dataviz_dir())}


@router.post("/api/dataviz/maps/ready")
@W.limiter.limit("6/minute")
async def api_dataviz_maps_fetch(request: Request):
    """מוריד מפה מוכנה לספרייה - רק מכתובת קבועה בקטלוג, רק בלחיצה במסך."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        saved = lib.fetch_ready_map(_dataviz_dir(), str(payload.get("id", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    return {"ok": True, "name": saved["name"]}


@router.post("/api/dataviz/maps/upload_shapefile")
@W.limiter.limit("6/minute")
async def api_dataviz_maps_upload_shapefile(request: Request):
    """גל 47: shapefile דחוס (למשל גבולות שיפוט ממשרד הפנים) -> מפה חדשה בספרייה."""
    payload, error = await _json_body(request)
    if error:
        return error
    from dataviz.web import library as lib
    try:
        saved = lib.save_shapefile_zip(_dataviz_dir(), str(payload.get("filename", "")), str(payload.get("data_base64", "")))
    except dataviz_episodes.EpisodeError as e:
        return _library_error(e)
    return {"ok": True, "name": saved["name"]}

