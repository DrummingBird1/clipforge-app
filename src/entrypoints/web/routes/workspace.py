# entrypoints/web/routes/workspace.py
#
# גל 12: מודל הנתונים v2 של עורך-העל - תיאור המודל (אזורים/רמות/יעדים), פרויקטים
# (שמירה אוטומטית ושחזור לכל תיקייה) וערכות מותג. ראו utils/video/editor_model.py,
# utils/video/editor_projects.py, utils/video/brand_kits.py.

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from utils.video import brand_kits, editor_field_schema, editor_model, editor_projects
from entrypoints import web_app as W

router = APIRouter()


def _forbidden():
    return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)


@router.get("/api/video_editor/schema")
def api_video_editor_schema():
    return editor_model.schema_description()


@router.get("/api/video_editor/field_schema")
def api_video_editor_field_schema():
    """גל 37: סכימת השדות האחת - דגל, טיפוס, ברירת מחדל, מונח והסבר לכל שדה (utils/video/editor_field_schema.py)."""
    return {"fields": editor_field_schema.field_schema()}


# --- פרויקטים ---

@router.get("/api/editor_projects")
def api_editor_projects_list():
    return {"projects": editor_projects.list_projects()}


@router.get("/api/editor_projects/by_folder")
def api_editor_projects_by_folder(folder: str = ""):
    if not folder:
        return JSONResponse({"error": "תיקייה חסרה."}, status_code=400)
    return {"project": editor_projects.load_project(folder)}


@router.put("/api/editor_projects")
@W.limiter.limit("120/minute")
async def api_editor_projects_save(request: Request):
    """שמירה אוטומטית של הפרויקט (debounced בצד הלקוח)."""
    if not W._is_same_origin(request):
        return _forbidden()
    payload = await request.json()
    folder = str(payload.get("folder") or "")
    try:
        project = editor_projects.save_project(folder, payload)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "id": project["id"], "updated_at": project["updated_at"]}


@router.delete("/api/editor_projects")
def api_editor_projects_delete(request: Request, folder: str = ""):
    if not W._is_same_origin(request):
        return _forbidden()
    return {"ok": editor_projects.delete_project(folder)}


@router.get("/api/editor_projects/export")
def api_editor_projects_export(folder: str = ""):
    exported = editor_projects.export_project(folder)
    if exported is None:
        return JSONResponse({"error": "אין פרויקט שמור לתיקייה הזו."}, status_code=404)
    return exported


@router.post("/api/editor_projects/import")
async def api_editor_projects_import(request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    payload = await request.json()
    folder = payload.get("folder") or None
    if folder and not os.path.isdir(str(folder)):
        return JSONResponse({"error": "התיקייה לא קיימת."}, status_code=400)
    try:
        project = editor_projects.import_project(payload.get("data") or {}, folder=folder)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "project": project}


# --- ערכות מותג ---

@router.get("/api/brand_kits")
def api_brand_kits_list():
    return {"kits": brand_kits.load_kits()}


@router.post("/api/brand_kits")
@W.limiter.limit("30/minute")
async def api_brand_kits_save(request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    payload = await request.json()
    try:
        kit = brand_kits.save_kit(payload.get("name"), payload.get("fields") or {}, payload.get("templates"))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "kit": kit}


@router.post("/api/brand_kits/{name}/rename")
async def api_brand_kits_rename(name: str, request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    payload = await request.json()
    try:
        brand_kits.rename_kit(name, payload.get("new_name"))
    except KeyError:
        return JSONResponse({"error": "ערכת המותג לא נמצאה."}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True}


@router.delete("/api/brand_kits/{name}")
def api_brand_kits_delete(name: str, request: Request):
    if not W._is_same_origin(request):
        return _forbidden()
    if not brand_kits.delete_kit(name):
        return JSONResponse({"error": "ערכת המותג לא נמצאה."}, status_code=404)
    return {"ok": True}
