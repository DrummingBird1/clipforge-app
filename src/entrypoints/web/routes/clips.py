# entrypoints/web/routes/clips.py
#
# גלריית הקליפים: תגיות, ייצוא ל-TikTok/YouTube, אישורים ואנליטיקס.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import glob
import json
import os
import tempfile
import threading
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from utils.video import media_pool
from utils.media.clip_tagger import list_all_cached_tags, read_cached_tags

from entrypoints import web_app as W

router = APIRouter()


@router.get("/api/download")
def api_download(path: str = ""):
    """מוריד קובץ תוצר (סרטון מרונדר, thumbnail וכו') - אותה רמת גישה לדיסק
    שכבר קיימת דרך /api/browse (מקומי בלבד, מאחורי הטוקן), רק עם
    Content-Disposition: attachment כדי שהדפדפן ישמור אותו במקום להציג."""
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    if W._is_under_data_dir(path):
        return JSONResponse({"error": "גישה לנתיב הזה נדחתה."}, status_code=403)
    return FileResponse(path, filename=os.path.basename(path))


@router.get("/api/clips")
def api_clips():
    """זהה ל-ui/stats_tab.py's refresh_gallery - אותה workspace/clips/*.mp4
    בדיוק, ממוין מהחדש לישן (הפוך מ-glob הגולמי של הדסקטופ, נוח יותר לגלריה)."""
    clips = sorted(glob.glob(os.path.join(W.CLIPS_DIR, "*.mp4")), key=os.path.getmtime, reverse=True)
    return [
        {"name": os.path.basename(c), "path": c, "size": os.path.getsize(c), "mtime": os.path.getmtime(c)}
        for c in clips
    ]


@router.get("/api/clips/thumbnail")
def api_clips_thumbnail(path: str = ""):
    """תמונה ממוזערת קטנה לכל קליפ בגלריה (item: gallery thumbnails - עד כה
    הגלריה הייתה רשימת טקסט שטוחה בלי שום ייצוג חזותי). נחלצת פעם אחת (פריים
    ב-20% מאורך הקליפ, כמו utils/video/contact_sheet.py) ונשמרת תחת THUMBNAIL_CACHE_DIR,
    עם invalidation לפי mtime המקור בשם הקובץ עצמו - קליפ שהוחלף (אותו נתיב,
    תוכן חדש) מקבל thumbnail טרי בפעם הבאה, בלי לבדוק תאריכים בקוד."""
    validated = W._validate_clip_path(path)
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)

    os.makedirs(W.THUMBNAIL_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(W.THUMBNAIL_CACHE_DIR, f"{os.path.basename(validated)}.{int(os.path.getmtime(validated))}.jpg")

    with media_pool.single_flight(cache_path):  # גל 24: ffmpeg אחד לכל תמונה, בתוך תקרת הנתיב
        if not os.path.exists(cache_path):
            try:
                with media_pool.slot("thumbs"):
                    duration = W.get_video_duration_via_ffprobe(validated, W.get_ffprobe_exe())
                with media_pool.slot("thumbs"):
                    W.extract_frame_at_timestamp(validated, max(0.1, duration * 0.2), cache_path, W.get_ffmpeg_exe())
            except Exception:
                pass
    if not os.path.exists(cache_path):
        return JSONResponse({"error": "יצירת תמונה ממוזערת נכשלה."}, status_code=500)

    return FileResponse(cache_path, media_type="image/jpeg")


@router.get("/api/clips/tags")
def api_clips_tags(path: str = ""):
    """תגיות שכבר נוצרו בעבר לקליפ הזה (item: content-based auto-tagging) -
    None אם עוד לא הופעל תיוג עליו (הגלריה מציגה כפתור "🏷️ תייג" רק במצב הזה) -
    לעולם לא קורא ל-AI מעצמו, רק קורא מטמון קיים. ראו /api/clips/generate_tags
    לפעולה שבאמת קוראת ל-AI (על-פי-בקשה בלבד - לא אוטומטי בטעינת הגלריה,
    כדי לא לצרוך מכסת Gemini בלי שהמשתמש ביקש את זה במפורש)."""
    validated = W._validate_clip_path(path)
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    return {"tags": read_cached_tags(validated, W.TAGS_CACHE_DIR)}


@router.get("/api/clips/all_tags")
def api_clips_all_tags():
    """כל התגיות הייחודיות שנוצרו אי-פעם על-פני כל הקליפים בגלריה - למילוי
    ה-dropdown של סינון-לפי-תגית (item: clip gallery search/filter by tag).
    לעולם לא קורא ל-AI, רק סורק קבצי מטמון קיימים."""
    return {"tags": list_all_cached_tags(W.TAGS_CACHE_DIR)}


@router.get("/api/clips/friend_tags")
def api_clips_friend_tags(path: str = ""):
    """מי היה בערוץ הקול המוגדר בזמן שהקליפ נשמר (item: friend detection via
    Discord voice channel presence) - נכתב על-ידי cogs/approval_cog.py's
    _do_scan (תהליך הבוט), נקרא כאן בלבד (לא קורא לבוט/Discord API בכלל).
    None אם עוד לא נסרק (או שהתכונה כבויה - אין ערוץ קול מוגדר)."""
    validated = W._validate_clip_path(path)
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    return {"friends": read_cached_tags(validated, W.approval_store.FRIEND_TAGS_CACHE_DIR)}


@router.post("/api/clips/generate_tags")
async def api_clips_generate_tags(request: Request):
    """מפעיל בפועל תיוג AI על קליפ - קורא ל-Gemini/Ollama (utils/media/clip_tagger.py),
    לכן נקרא רק כשהמשתמש לוחץ במפורש על "🏷️ תייג" בגלריה, לא אוטומטית. שלושה
    פריימים (20%/50%/80% מהאורך, כמו utils/video/contact_sheet.py) בתיקייה זמנית
    שנמחקת מיד אחרי הקריאה. תוצאה נשמרת ל-TAGS_CACHE_DIR כדי שלא יקרא ל-AI
    שוב על אותו קליפ (אותו נתיב+mtime) בפעם הבאה."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    validated = W._validate_clip_path(payload.get("path", ""))
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)

    with tempfile.TemporaryDirectory() as tmp_dir:
        try:
            duration = W.get_video_duration_via_ffprobe(validated, W.get_ffprobe_exe())
            frame_paths = []
            for i, pct in enumerate((0.2, 0.5, 0.8)):
                frame_path = os.path.join(tmp_dir, f"frame_{i}.jpg")
                if W.extract_frame_at_timestamp(validated, max(0.1, duration * pct), frame_path, W.get_ffmpeg_exe()):
                    frame_paths.append(frame_path)
        except Exception:
            frame_paths = []
        if not frame_paths:
            return JSONResponse({"error": "לא הצלחתי לחלץ פריימים מהקליפ לצורך תיוג."}, status_code=500)
        tags = W.generate_clip_tags(frame_paths)

    os.makedirs(W.TAGS_CACHE_DIR, exist_ok=True)
    with open(W._tags_cache_path(validated), "w", encoding="utf-8") as f:
        json.dump({"tags": tags}, f, ensure_ascii=False)
    return {"tags": tags}


@router.get("/api/clips/stream")
def api_clips_stream(path: str = ""):
    """בניגוד ל-/api/download (Content-Disposition: attachment, כדי שהדפדפן
    ישמור לדיסק) - כאן בלי attachment, כדי ש-<video> יוכל להציג נגן תצוגה
    מקדימה בתוך העמוד עצמו, לא רק להוריד."""
    validated = W._validate_clip_path(path)
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    return FileResponse(validated, media_type="video/mp4")


@router.post("/api/clips/tiktok_export")
async def api_clips_tiktok_export(request: Request):
    """זהה ל-ui/stats_tab.py's export_wizard: מחולל SEO metadata (utils/bot/seo_generator.py)
    ומחזיר את קישור ה-TikTok Studio Upload - פתיחת הקישור בטאב חדש קורית בצד
    הלקוח (window.open), לא כאן. גל 32: ה-SEO (Gemini, כמה שניות) רץ ב-thread pool כדי
    לא לחסום את השרת, והכיתוב חוזר ללקוח - שמעתיק אותו ללוח לפני שנפתח TikTok."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    validated = W._validate_publishable_path(payload.get("path", ""))   # כל תוצר, לא רק קליפ (23.10.2026, באישור המפנה)
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)
    seo = await run_in_threadpool(_seo_or_none, validated)
    W.audit_log.record_action("web", "tiktok_export", details=os.path.basename(validated), username=request.client.host if request.client else None)
    return {"ok": True, "tiktok_url": W.TIKTOK_UPLOAD_URL, "metadata": seo["sheet"] if seo else "",
            "caption": seo["tiktok_caption"] if seo else "", "seo_source": seo["source"] if seo else None}


def _seo_or_none(path):
    """SEO שנכשל (למשל תיקייה בלי הרשאת כתיבה) לא עוצר יצוא - אותו עיקרון כמו generate_seo_metadata."""
    try:
        return W.generate_seo_with_sheet(path)
    except Exception as e:
        W.worker.log_queue.put((f"⚠️ יצירת SEO נכשלה: {e}\n", "red"))
        return None


@router.get("/api/clips/youtube_status")
def api_clips_youtube_status():
    """נבדק גם לפני התחלת יצוא (configured קובע אם ללחוץ מפעיל העלאה
    אוטומטית או רק פותח את עמוד ההעלאה הידני) וגם תוך כדי (polling מהלקוח
    בזמן in_progress, ראו JS)."""
    with W._youtube_upload_lock:
        state_copy = dict(W._youtube_upload_state)
    return {"configured": W.youtube_uploader.is_configured(), **state_copy}


@router.post("/api/clips/youtube_export")
async def api_clips_youtube_export(request: Request):
    """זהה ל-ui/stats_tab.py's export_youtube: אם client_secret.json לא מוגדר
    (youtube_uploader.is_configured()), מחזיר קישור נפילה-חזרה לעמוד ההעלאה
    הידני (פתיחה בצד הלקוח) - אחרת מפעיל את אותה youtube_uploader.upload_video
    ברקע (thread נפרד, לא חוסם את event loop של FastAPI תוך כדי העלאה
    שיכולה לקחת דקות), עם התקדמות שנקראת דרך /api/clips/youtube_status."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    validated = W._validate_publishable_path(payload.get("path", ""))   # כל תוצר, לא רק קליפ (23.10.2026, באישור המפנה)
    if not validated:
        return JSONResponse({"error": "קובץ לא נמצא."}, status_code=400)

    seo = await run_in_threadpool(_seo_or_none, validated)

    if not W.youtube_uploader.is_configured():
        return {"configured": False, "fallback_url": W.YOUTUBE_UPLOAD_FALLBACK_URL}

    with W._youtube_upload_lock:
        if W._youtube_upload_state["in_progress"]:
            return JSONResponse({"error": "כבר יש העלאה פעילה."}, status_code=409)
        W._youtube_upload_state.update({"in_progress": True, "percent": 0, "success": None, "video_id": None, "error": None})

    # גל 32: כותרת/תיאור/תגיות מ-Gemini כשיש; בלי - שם הקובץ (מערכת המונה) כמו קודם
    title = os.path.splitext(os.path.basename(validated))[0]
    description, tags = "", ["gaming", "shorts"]
    if seo and seo.get("source") == "ai":
        title = seo["youtube_title"]
        description = "\n\n".join(part for part in (seo["description"], " ".join(seo["hashtags"])) if part)
        tags = seo["youtube_tags"] or tags

    def _progress(pct):
        with W._youtube_upload_lock:
            W._youtube_upload_state["percent"] = pct

    def _do_upload():
        try:
            video_id = W.youtube_uploader.upload_video(
                validated, title=title, description=description, tags=tags,
                privacy_status="private", progress_callback=_progress,
            )
            W.youtube_publish_log.record_upload(video_id, os.path.basename(validated), title)
            W._generate_and_record_thumbnail_candidates(video_id, validated)
            with W._youtube_upload_lock:
                W._youtube_upload_state.update({"in_progress": False, "success": True, "video_id": video_id, "percent": 100})
        except Exception as e:
            with W._youtube_upload_lock:
                W._youtube_upload_state.update({"in_progress": False, "success": False, "error": str(e)})

    threading.Thread(target=_do_upload, daemon=True).start()
    W.audit_log.record_action("web", "youtube_export", details=os.path.basename(validated), username=request.client.host if request.client else None)
    return {"configured": True, "started": True}


@router.get("/api/youtube_analytics")
def api_youtube_analytics_list():
    """רשימת סרטונים שהועלו + הסטטיסטיקות המטמון-שלהם (views/likes/comments יכולים
    להיות None - "עוד לא רוענן בפועל", לא "0 אמיתי") - לא קורא ל-API בכלל,
    ראו /api/youtube_analytics/refresh לרענון בפועל. thumbnail_switch (item:
    A/B thumbnail testing) - None אם מעולם לא הוחלפה תמונה ממוזערת לסרטון הזה,
    אחרת views_gained_since_switch (יכול להיות None אם עוד לא רוענן מאז)."""
    rows = W.youtube_publish_log.get_published_videos()
    result = []
    for video_id, clip_filename, title, uploaded_at, views, likes, comments, stats_updated_at in rows:
        latest_switch = W.youtube_thumbnail_log.get_latest_switch(video_id)
        thumbnail_switch = None
        if latest_switch:
            candidate_index, set_at, views_at_switch = latest_switch
            thumbnail_switch = {
                "candidate_index": candidate_index, "set_at": set_at, "views_at_switch": views_at_switch,
                "views_gained_since_switch": (views - views_at_switch) if views is not None else None,
            }
        result.append({
            "video_id": video_id, "clip_filename": clip_filename, "title": title, "uploaded_at": uploaded_at,
            "views": views, "likes": likes, "comments": comments, "stats_updated_at": stats_updated_at,
            "thumbnail_switch": thumbnail_switch,
        })
    return result


@router.get("/api/youtube_analytics/{video_id}/thumbnail_candidates")
def api_youtube_thumbnail_candidates_list(video_id: str):
    """[{index, ...}] - התמונות עצמן נשלפות דרך .../image (לא מוטמעות כ-base64
    כאן) - זהה לדפוס הקיים כבר ב-/api/clips/thumbnail (תמונה = endpoint נפרד,
    לא שדה בתשובת JSON)."""
    return [{"index": index} for index, _image_path in W.youtube_thumbnail_log.get_candidates(video_id)]


@router.get("/api/youtube_analytics/{video_id}/thumbnail_candidates/{candidate_index}/image")
def api_youtube_thumbnail_candidate_image(video_id: str, candidate_index: int):
    candidates = dict(W.youtube_thumbnail_log.get_candidates(video_id))
    image_path = candidates.get(candidate_index)
    if not image_path or not os.path.isfile(image_path):
        return JSONResponse({"error": "תמונה מועמדת לא נמצאה."}, status_code=404)
    return FileResponse(image_path, media_type="image/jpeg")


@router.post("/api/youtube_analytics/{video_id}/set_thumbnail")
async def api_youtube_set_thumbnail(video_id: str, request: Request):
    """מגדיר תמונה מועמדת כתמונה הממוזערת בפועל ב-YouTube, ורושם את ה-views
    המצטבר *הידוע כרגע* (מהמטמון, לא קריאת API נוספת) כ-views_at_switch -
    זה מה שמאפשר מאוחר יותר לחשב "כמה צפיות נצברו מאז ההחלפה הזו" (item:
    A/B thumbnail testing)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        candidate_index = int(payload.get("candidate_index"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "candidate_index חייב להיות מספר."}, status_code=400)

    candidates = dict(W.youtube_thumbnail_log.get_candidates(video_id))
    image_path = candidates.get(candidate_index)
    if not image_path or not os.path.isfile(image_path):
        return JSONResponse({"error": "תמונה מועמדת לא נמצאה."}, status_code=400)

    try:
        W.youtube_analytics.set_video_thumbnail(video_id, image_path)
    except Exception as e:
        return JSONResponse({"error": f"הגדרת התמונה הממוזערת נכשלה: {e}"}, status_code=500)

    published = {row[0]: row[4] for row in W.youtube_publish_log.get_published_videos()}
    views_at_switch = published.get(video_id) or 0
    W.youtube_thumbnail_log.record_switch(video_id, candidate_index, views_at_switch)
    W.audit_log.record_action(
        "web", "youtube_set_thumbnail", details=f"{video_id}#{candidate_index}",
        username=request.client.host if request.client else None,
    )
    return {"ok": True}


@router.post("/api/youtube_analytics/refresh")
def api_youtube_analytics_refresh(request: Request):
    """מתחיל רענון ברקע (thread נפרד - ראו _youtube_analytics_refresh_state
    למעלה) לכל הסרטונים הרשומים בבת אחת - "רענן הכל" עדיף על ריענון-אחד-אחד,
    ורק על-פי-בקשה מפורשת (לא אוטומטי), כדי לא לצרוך quota בלי סיבה. ראו
    /api/youtube_analytics/refresh_status להתקדמות."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    if not W.youtube_uploader.is_configured():
        return JSONResponse({"error": "YouTube לא מוגדר (client_secret.json חסר)."}, status_code=400)

    with W._youtube_analytics_refresh_lock:
        if W._youtube_analytics_refresh_state["in_progress"]:
            return JSONResponse({"error": "כבר יש רענון פעיל."}, status_code=409)
        W._youtube_analytics_refresh_state.update({"in_progress": True, "updated": 0, "errors": [], "done": False})

    def _do_refresh():
        updated = 0
        errors = []
        for video_id, *_rest in W.youtube_publish_log.get_published_videos():
            try:
                stats = W.youtube_analytics.get_video_stats(video_id)
            except Exception as e:
                errors.append(f"{video_id}: {e}")
                continue
            if stats is None:
                continue
            W.youtube_publish_log.update_cached_stats(video_id, stats["views"], stats["likes"], stats["comments"])
            updated += 1
        with W._youtube_analytics_refresh_lock:
            W._youtube_analytics_refresh_state.update({"in_progress": False, "updated": updated, "errors": errors, "done": True})

    threading.Thread(target=_do_refresh, daemon=True).start()
    W.audit_log.record_action("web", "youtube_analytics_refresh", username=request.client.host if request.client else None)
    return {"started": True}


@router.get("/api/youtube_analytics/refresh_status")
def api_youtube_analytics_refresh_status():
    with W._youtube_analytics_refresh_lock:
        return dict(W._youtube_analytics_refresh_state)


@router.get("/api/approvals")
def api_approvals_list():
    """קליפים שממתינים לאישור (item: mobile-friendly clip-approval view) -
    אותה טבלת pending_approvals ש-cogs/approval_cog.py מזין דרך הבוט, נקרא כאן
    סינכרונית (utils/bot/approval_store.py) בלי תלות בזה שהבוט רץ. שורות שהקובץ
    שלהן כבר לא קיים בדיסק (אושר/נדחה במקביל מהדיסקורד, וכו') מסוננות כאן -
    לא נמחקות מה-DB, פשוט לא מוצגות."""
    rows = []
    for pending_id, video_path, created_at in W.approval_store.get_pending_approvals():
        if not os.path.isfile(video_path):
            continue
        rows.append({
            "id": pending_id, "path": video_path, "name": os.path.basename(video_path),
            "game": os.path.basename(os.path.dirname(video_path)), "created_at": created_at,
        })
    return rows


@router.post("/api/approvals/{pending_id}/decide")
async def api_approvals_decide(pending_id: int, request: Request):
    """מאשר/דוחה קליפ ממתין - זהה ל-ApprovalView's approve/reject בדיסקורד
    (מעביר את הקובץ ל-Import של rocket_shorts_publisher.py או לתיקיית הנדחים,
    ומעדכן status/resolved_at), רק דרך endpoint סינכרוני במקום כפתור דיסקורד."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    approved = bool(payload.get("approved"))

    pending = {row[0]: row[1] for row in W.approval_store.get_pending_approvals()}
    video_path = pending.get(pending_id)
    if not video_path or not W.approval_store.validate_pending_video_path(video_path):
        return JSONResponse({"error": "הקליפ לא נמצא או שכבר טופל."}, status_code=400)

    W.approval_store.resolve_pending(pending_id, video_path, approved)
    W.audit_log.record_action(
        "web", "approval_decide", details=f"{os.path.basename(video_path)}={'approved' if approved else 'rejected'}",
        username=request.client.host if request.client else None,
    )
    return {"ok": True}
