# entrypoints/web/routes/editor_profiles.py
#
# פרופילים של עורך-העל: שמירה/טעינה/היסטוריה/השוואה/ייבוא-ייצוא/גיבויים/סל-מחזור/שיתוף.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from utils.video.video_editor import VIDEO_EDITOR_PRESETS
from utils.video.video_editor_profiles import (
    annotate_profile as annotate_video_editor_profile,
    delete_profile as delete_video_editor_profile,
    diff_profiles as diff_video_editor_profiles,
    duplicate_profile as duplicate_video_editor_profile,
    export_all_profiles as export_all_video_editor_profiles,
    export_profile as export_video_editor_profile,
    get_profile_history as get_video_editor_profile_history,
    import_all_profiles as import_all_video_editor_profiles,
    import_profile as import_video_editor_profile,
    list_profile_backups as list_video_editor_profile_backups,
    list_trash as list_video_editor_profile_trash,
    load_all_profile_meta as load_all_video_editor_profile_meta,
    load_profile_meta as load_video_editor_profile_meta,
    load_profiles as load_video_editor_profiles,
    pull_from_parent as pull_video_editor_profile_from_parent,
    purge_trash_entry as purge_video_editor_profile_trash_entry,
    rename_profile as rename_video_editor_profile,
    restore_from_trash as restore_video_editor_profile_from_trash,
    restore_profile_backup as restore_video_editor_profile_backup,
    revert_profile as revert_video_editor_profile,
    save_profile as save_video_editor_profile,
    save_template as save_video_editor_template,
    set_default_profile as set_default_video_editor_profile,
    set_profile_field as set_video_editor_profile_field,
    set_profile_parent as set_video_editor_profile_parent,
)

from utils.video.editor_model import migrate_profile
from entrypoints import web_app as W

router = APIRouter()


def _style_words(error) -> str:
    """גל 30: בממשק הווב "פרופיל" נקרא "סגנון". ההודעות מ-utils (משותפות לדסקטופ הקפוא) נשארות
    כמו שהן - רק מה שחוזר לדפדפן מתורגם למילה החדשה."""
    return str(error).replace("פרופילים", "סגנונות").replace("פרופיל", "סגנון")


@router.get("/api/video_editor_presets")
def api_video_editor_presets():
    """מקור אמת יחיד (utils/video/video_editor.py) - אותם פרופילים בדיוק כמו ה-GUI
    השולחני (ui/settings_tab.py), לא רשימה כפולה שעלולה להתבדר."""
    return VIDEO_EDITOR_PRESETS


@router.get("/api/video_editor_profiles")
def api_video_editor_profiles_list():
    """פרופילים אישיים ל-"עורך-העל" (item: פרופיל משלי - הגדרות/נתיבים/סליידרים
    ששמרתי) - להבדיל מ-VIDEO_EDITOR_PRESETS הקבועים למעלה, אלה נוצרים/נמחקים
    ע"י המשתמש עצמו (utils/video/video_editor_profiles.py, data/video_editor_profiles.json).
    גל 12: כל פרופיל עובר מיגרציה ל-v2 בדרך החוצה (טקסט/חותמת-זמן -> שכבות, פינת-
    מחיקה -> אזור) - הקובץ עצמו לא נכתב מחדש, הדסקטופ הקפוא עדיין קורא אותו כמו שהוא."""
    return {name: _strip_schema(migrate_profile(settings)) for name, settings in load_video_editor_profiles().items()}


def _strip_schema(settings):
    settings.pop("schema_version", None)
    return settings


@router.post("/api/video_editor_profiles")
@W.limiter.limit("10/minute")
async def api_video_editor_profiles_save(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    if not name:
        return JSONResponse({"error": "שם סגנון חסר."}, status_code=400)
    settings = payload.get("settings") or {}
    # 24.10.2026: kind=template - "שמור את הפרויקט כתבנית" (בלי הקבצים של התיקייה, ומסומן בקובץ המטא)
    saved = save_video_editor_template(name, settings) if payload.get("kind") == "template" else save_video_editor_profile(name, settings)
    return {"name": name, "settings": saved}


@router.delete("/api/video_editor_profiles/{name}")
@W.limiter.limit("10/minute")
def api_video_editor_profiles_delete(name: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    deleted = delete_video_editor_profile(name)
    return {"deleted": deleted}


@router.post("/api/video_editor_profiles/{name}/rename")
@W.limiter.limit("10/minute")
async def api_video_editor_profiles_rename(name: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    new_name = str(payload.get("new_name", "")).strip()
    try:
        renamed = rename_video_editor_profile(name, new_name)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    return {"name": new_name, "settings": renamed}


@router.post("/api/video_editor_profiles/{name}/duplicate")
@W.limiter.limit("10/minute")
async def api_video_editor_profiles_duplicate(name: str, request: Request):
    """item: שכפול פרופיל / "שמור בשם..." - יוצר עותק חדש בלי לגעת במקור."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    new_name = str(payload.get("new_name", "")).strip()
    try:
        duplicated = duplicate_video_editor_profile(name, new_name)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    return {"name": new_name, "settings": duplicated}


@router.get("/api/video_editor_profiles/diff")
def api_video_editor_profiles_diff(a: str, b: str):
    """item: השוואת שני פרופילים - {field: [value_a, value_b]} רק לשדות שונים."""
    try:
        diff = diff_video_editor_profiles(a, b)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=404)
    return {"diff": diff}


@router.get("/api/video_editor_profiles/{name}/export")
def api_video_editor_profiles_export(name: str):
    """item: ייצוא/ייבוא פרופיל - snapshot נקי (רק PROFILE_FIELDS) להורדה כ-JSON."""
    try:
        exported = export_video_editor_profile(name)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=404)
    return {"name": name, "settings": exported}


@router.post("/api/video_editor_profiles/import")
@W.limiter.limit("10/minute")
async def api_video_editor_profiles_import(request: Request):
    """item: ייצוא/ייבוא פרופיל - קובע overwrite=True במפורש רק אם המשתמש אישר
    דריסת פרופיל קיים באותו שם (ה-JS שואל לפני שליחה חוזרת עם overwrite)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    name = str(payload.get("name", "")).strip()
    settings = payload.get("settings") or {}
    overwrite = bool(payload.get("overwrite"))
    try:
        imported = import_video_editor_profile(name, settings, overwrite=overwrite)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    return {"name": name, "settings": imported}


@router.get("/api/video_editor_profiles/{name}/meta")
def api_video_editor_profiles_meta(name: str):
    """item: חותמת "בשימוש לאחרונה" + מספר הרצות + גרסת-סכימה."""
    return load_video_editor_profile_meta(name)


@router.get("/api/video_editor_profiles/{name}/history")
def api_video_editor_profiles_history(name: str):
    """item: היסטוריית-שינויים/undo לפרופיל - snapshot-ים קודמים, הישן ביותר ראשון."""
    return {"history": get_video_editor_profile_history(name)}


@router.post("/api/video_editor_profiles/{name}/revert")
@W.limiter.limit("10/minute")
async def api_video_editor_profiles_revert(name: str, request: Request):
    """item: היסטוריית-שינויים/undo לפרופיל - משחזר לגרסה קודמת (index שלילי
    סופר מהסוף, -1=האחרונה שנשמרה בהיסטוריה)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        index = int(payload.get("index"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "אינדקס לא תקין."}, status_code=400)
    try:
        reverted = revert_video_editor_profile(name, index)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    return {"name": name, "settings": reverted}


@router.get("/api/video_editor_profiles_meta_all")
def api_video_editor_profiles_meta_all():
    """item 60-63/68: מטא-דאטה של כל הפרופילים בבקשה אחת (מיון/צ'יפים/תגיות/ירושה)."""
    return {"meta": load_all_video_editor_profile_meta()}


@router.post("/api/video_editor_profiles/{name}/annotate")
@W.limiter.limit("60/minute")
async def api_video_editor_profiles_annotate(name: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    tags = payload.get("tags")
    if isinstance(tags, str):
        tags = [t for t in tags.replace("،", ",").split(",")]
    try:
        return annotate_video_editor_profile(name, tags=tags if isinstance(tags, list) else None, color=payload.get("color"), notes=payload.get("notes"))
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)


@router.post("/api/video_editor_profile_default")
@W.limiter.limit("30/minute")
async def api_video_editor_profile_default(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        set_default_video_editor_profile(payload.get("name") or None)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    return {"default": payload.get("name") or None}


@router.post("/api/video_editor_profiles/{name}/set_field")
@W.limiter.limit("60/minute")
async def api_video_editor_profiles_set_field(name: str, request: Request):
    """item 65: "מזג שדה" מתצוגת ההשוואה - מעתיק ערך של שדה בודד לפרופיל."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        settings = set_video_editor_profile_field(name, str(payload.get("field", "")), payload.get("value"))
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    return {"name": name, "settings": settings}


@router.get("/api/video_editor_profiles_export_all")
def api_video_editor_profiles_export_all():
    """item 66: ייצוא כל הפרופילים (כולל תגיות/צבע/הערות/ירושה) לקובץ JSON אחד."""
    return export_all_video_editor_profiles()


@router.post("/api/video_editor_profiles_import_all")
@W.limiter.limit("10/minute")
async def api_video_editor_profiles_import_all(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        result = import_all_video_editor_profiles(payload.get("data"), strategy=str(payload.get("strategy") or "skip"))
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    W.audit_log.record_action("web", "video_editor_profiles_import_all", details=json.dumps({k: len(v) for k, v in result.items()}), username=request.client.host if request.client else None)
    return result


@router.post("/api/video_editor_profiles/{name}/parent")
@W.limiter.limit("30/minute")
async def api_video_editor_profiles_set_parent(name: str, request: Request):
    """item 68: ירושה - קובע/מבטל את פרופיל-ההורה."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        return set_video_editor_profile_parent(name, payload.get("parent") or None)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)


@router.post("/api/video_editor_profiles/{name}/pull_parent")
@W.limiter.limit("30/minute")
def api_video_editor_profiles_pull_parent(name: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        return pull_video_editor_profile_from_parent(name)
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)


@router.get("/api/qr")
def api_qr(data: str = ""):
    if not data or len(data) > W.QR_MAX_DATA_LENGTH:
        return JSONResponse({"error": "הנתונים ריקים או ארוכים מדי לקוד QR."}, status_code=400)
    import io

    import qrcode
    import qrcode.image.svg
    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return Response(content=buffer.getvalue(), media_type="image/svg+xml")


@router.get("/api/lan_info")
def api_lan_info():
    return {"lan": W.LAN_BASE_URL is not None, "base_url": W.LAN_BASE_URL}


@router.get("/api/access_token")
def api_access_token():
    """item 67: "כלול טוקן גישה" בקישור-שיתוף - העוגייה היא HttpOnly (JS לא
    יכול לקרוא אותה, בכוונה), אז הטוקן מוחזר כאן למי שכבר מאומת בו ממילא
    (ה-middleware חוסם כל מי שלא) - לא חושף שום דבר שהקורא לא מחזיק כבר."""
    return {"token": W.ACCESS_TOKEN}


# item: גיבוי אוטומטי מסתובב + "שחזר מגיבוי" - prefix נפרד (לא /video_editor_profiles/...)
# כדי שלא יתנגש עם הנתיבים הקיימים /api/video_editor_profiles/{name}.
@router.get("/api/video_editor_profile_backups")
def api_video_editor_profile_backups_list():
    return {"backups": list_video_editor_profile_backups()}


@router.post("/api/video_editor_profile_backups/restore")
@W.limiter.limit("10/minute")
async def api_video_editor_profile_backups_restore(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    try:
        result = restore_video_editor_profile_backup(str(payload.get("id", "")), mode=str(payload.get("mode") or "merge_missing"))
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)
    W.audit_log.record_action("web", "video_editor_profiles_restore_backup", details=str(payload.get("id", "")), username=request.client.host if request.client else None)
    return result


# item: מחיקה רכה - סל מחזור לפרופילים.
@router.get("/api/video_editor_profile_trash")
def api_video_editor_profile_trash_list():
    return {"entries": list_video_editor_profile_trash()}


@router.post("/api/video_editor_profile_trash/{entry_id}/restore")
@W.limiter.limit("20/minute")
async def api_video_editor_profile_trash_restore(entry_id: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    try:
        return restore_video_editor_profile_from_trash(entry_id, new_name=(payload or {}).get("new_name"))
    except ValueError as e:
        return JSONResponse({"error": _style_words(e)}, status_code=400)


@router.delete("/api/video_editor_profile_trash/{entry_id}")
@W.limiter.limit("20/minute")
def api_video_editor_profile_trash_purge(entry_id: str, request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    if not purge_video_editor_profile_trash_entry(entry_id):
        return JSONResponse({"error": "הפריט לא נמצא בסל המחזור."}, status_code=404)
    W.audit_log.record_action("web", "video_editor_profile_trash_purge", details=entry_id, username=request.client.host if request.client else None)
    return {"ok": True}
