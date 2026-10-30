# entrypoints/web/routes/dataviz_plus.py
#
# 27.10.2026: ה-endpoints של 25 ההצעות לעורך הגרפים (dataviz/web/plus.py ו-dataviz/web/preview.py): התאריך של כל מקום
# בסליידר (מצב הבמאי ובלוקי הסיפור), sparkline לכל ישות, תבניות שמורות, דגלים למדינות (הורדה רק בלחיצה), מצב כרטיס
# המסך בזמן רינדור, שימור הצופים מיוטיוב (רק בלחיצה) והקלטה רציפה. כל השאר של המסך - ב-routes/dataviz.py.

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from dataviz.web import episodes as dataviz_episodes
from dataviz.web import plus as dataviz_plus
from dataviz.web import preview as dataviz_preview
from dataviz.web import publish as dataviz_publish
from entrypoints import web_app as W
from entrypoints.web.routes import dataviz as R

router = APIRouter()


@router.get("/api/dataviz/timeline")
def api_dataviz_timeline(episode: str = "", mode: str = "full", draft: str = ""):
    """[מקום בסליידר, תאריך] לאורך הקטע הראשי - מצב הבמאי ובלוקי הסיפור הנגררים."""
    from dataviz.config import ConfigError
    folder, overrides = R._preview_overrides(episode, draft=draft)
    if folder is None:
        return overrides
    try:
        return dataviz_preview.timeline(folder, overrides, mode)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (ValueError, KeyError, IndexError) as e:
        return JSONResponse({"error": str(e)[:300]}, status_code=400)


@router.get("/api/dataviz/episodes/sparklines")
def api_dataviz_sparklines(episode: str = ""):
    """גרף קטן לכל ישות בלשונית הישויות, עם הקטעים שיש בהם קפיצה חשודה."""
    from dataviz.config import ConfigError
    folder, overrides = R._episode_for_preview(episode)
    if folder is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    try:
        return dataviz_preview.sparklines(folder, overrides)
    except ConfigError as e:
        return JSONResponse({"error": "; ".join(e.errors[:3])}, status_code=400)
    except (ValueError, KeyError, IndexError, OSError) as e:
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)


# ---------- תבניות ----------
@router.get("/api/dataviz/templates")
def api_dataviz_templates():
    return {"templates": dataviz_plus.list_templates(R._dataviz_dir())}


@router.post("/api/dataviz/templates")
@W.limiter.limit("20/minute")
async def api_dataviz_save_template(request: Request):
    """"💾 שמור כתבנית" - העיצוב והקצב של הפרק בשם משלהם (הפרק לא משתנה)."""
    payload, error = await R._json_body(request)
    if error:
        return error
    try:
        return dataviz_plus.save_template(R._dataviz_dir(), str(payload.get("episode", "")), str(payload.get("title", "")))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)


@router.post("/api/dataviz/templates/delete")
async def api_dataviz_delete_template(request: Request):
    payload, error = await R._json_body(request)
    if error:
        return error
    if not dataviz_plus.delete_template(R._dataviz_dir(), str(payload.get("id", ""))):
        return JSONResponse({"error": "התבנית לא נמצאה."}, status_code=404)
    return {"ok": True}


# ---------- דגלים ----------
def _episode_entities(episode):
    """שמות הישויות של הפרק (לפני שמות חלופיים והחרגה), או None כשהפרק לא נמצא."""
    folder, overrides = R._episode_for_preview(episode)
    if folder is None:
        return None
    return [e["name"] for e in dataviz_preview.episode_overview(folder, overrides)["entities"]]


@router.get("/api/dataviz/flags")
def api_dataviz_flags(episode: str = ""):
    """אילו ישויות בפרק הן מדינות, ולאילו כבר יש דגל."""
    from dataviz.config import ConfigError
    try:
        entities = _episode_entities(episode)
    except (ConfigError, ValueError, KeyError, OSError) as e:
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)
    if entities is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    return dataviz_plus.flags_status(R._dataviz_dir(), entities)


@router.post("/api/dataviz/flags/download")
@W.limiter.limit("5/minute")
async def api_dataviz_flags_download(request: Request):
    """"📥 הורד דגלים" - רק בלחיצה, רק הדגלים החסרים לפרק, מכתובת קבועה (dataviz/web/plus.FLAG_URL)."""
    from starlette.concurrency import run_in_threadpool

    from dataviz.config import ConfigError
    payload, error = await R._json_body(request)
    if error:
        return error
    episode = str(payload.get("episode", ""))
    try:
        entities = _episode_entities(episode)
    except (ConfigError, ValueError, KeyError, OSError) as e:
        return JSONResponse({"error": "הנתונים של הפרק לא נטענו: " + str(e)[:200]}, status_code=400)
    if entities is None:
        return JSONResponse({"error": "הפרק לא נמצא."}, status_code=404)
    status = dataviz_plus.flags_status(R._dataviz_dir(), entities)
    result = await run_in_threadpool(dataviz_plus.download_flags, R._dataviz_dir(), status["missing"])
    W.audit_log.record_action("web", "dataviz_download_flags", details=f"{episode}: {len(result['saved'])}",
                              username=request.client.host if request.client else None)
    return {"ok": True, **result, **dataviz_plus.flags_status(R._dataviz_dir(), entities)}


# ---------- כרטיס המסך ----------
@router.get("/api/dataviz/gpu")
def api_dataviz_gpu():
    """ניצול כרטיס המסך עכשיו (כללי, NVENC, זיכרון) - לשבב שליד ההתקדמות בזמן רינדור."""
    return dataviz_plus.gpu_status()


# ---------- שימור צופים ----------
def _episode_package(episode):
    """חבילת הפרסום החדשה ביותר של הפרק שהסרטון שלה הועלה ליוטיוב: (נתיב, חבילה) או (None, None)."""
    best = (None, None, "")
    for orientation in R.ORIENTATIONS:
        for folder in R._folders(orientation):
            if not os.path.isdir(folder):
                continue
            for package in dataviz_publish.list_packages(folder):
                video = str(package.get("video") or "")
                if not (video == episode + ".mp4" or video.startswith(episode + "_") or video.startswith(episode + ".")):
                    continue
                if not dataviz_plus.video_id_for(package):
                    continue
                sent = str(((package.get("sent") or {}).get("youtube") or {}).get("at") or "")
                if sent >= best[2]:
                    best = (package["path"], package, sent)
    return best[0], best[1]


@router.get("/api/dataviz/retention")
def api_dataviz_retention(episode: str = ""):
    """השימור שכבר נמשך (נשמר בחבילה) - בלי לפנות ליוטיוב."""
    path, package = _episode_package(episode)
    if path is None:
        return {"points": [], "uploaded": False}
    return {"points": package.get("retention") or [], "uploaded": True, "at": package.get("retention_at") or ""}


@router.post("/api/dataviz/retention")
@W.limiter.limit("10/minute")
async def api_dataviz_retention_refresh(request: Request):
    """"📈 שימור צופים" - רק בלחיצה: כמה מהצופים עוד צופים בכל נקודה בסרטון (YouTube Analytics), ונשמר בחבילה."""
    import time

    from starlette.concurrency import run_in_threadpool
    payload, error = await R._json_body(request)
    if error:
        return error
    path, package = _episode_package(str(payload.get("episode", "")))
    if path is None:
        return JSONResponse({"error": "לפרק הזה עוד אין סרטון שהועלה ליוטיוב."}, status_code=400)
    from utils.bot import youtube_uploader
    if not os.path.isfile(youtube_uploader.TOKEN_FILE):
        return JSONResponse({"error": "אין חיבור ליוטיוב במחשב הזה."}, status_code=400)
    try:
        from utils.bot.youtube_analytics import get_audience_retention
        rows = await run_in_threadpool(get_audience_retention, dataviz_plus.video_id_for(package))
    except Exception as e:
        return JSONResponse({"error": "יוטיוב לא החזיר נתוני שימור: " + str(e)[:200]}, status_code=400)
    points = dataviz_plus.retention_points(rows)
    saved = dataviz_publish.load_package(path)
    saved.update({"retention": points, "retention_at": time.strftime("%Y-%m-%d %H:%M")})
    dataviz_publish._write_json(path, saved)
    return {"ok": True, "points": points, "at": saved["retention_at"]}


# ---------- הקלטה רציפה ----------
@router.post("/api/dataviz/narration_track")
@W.limiter.limit("10/minute")
async def api_dataviz_narration_track(request: Request):
    """"🎙 הקלטה רציפה" - הקלטה אחת לכל הסרטון, מהשנייה שבה התחילה."""
    payload, error = await R._json_body(request)
    if error:
        return error
    try:
        return dataviz_plus.save_track(R._dataviz_dir(), str(payload.get("episode", "")), str(payload.get("ext", "")),
                                       str(payload.get("data", "")), payload.get("start", 0))
    except dataviz_episodes.EpisodeError as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)

