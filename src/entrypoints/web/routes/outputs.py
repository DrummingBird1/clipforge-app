# entrypoints/web/routes/outputs.py
#
# 23.10.2026: מסך "תוצרים" - הרשימה (utils/shared/outputs_index.py) ופתיחה בסטודיו. השאר דרך routes שכבר קיימים, וכל אחד
# בודק את הנתיב בעצמו: ניגון ותמונה ממוזערת - /api/video_editor/stream ו-output_thumbnail; התיקייה - /api/open_folder;
# פרסום - /api/clips/tiktok_export ו-youtube_export.
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from dataviz.web import handoff as dataviz_handoff
from utils.shared import outputs_index, workspace_dir

from entrypoints import web_app as W

router = APIRouter()


@router.get("/api/outputs")
def api_outputs():
    return {"outputs": outputs_index.scan(W.WORKSPACE_DIR), "tools": list(workspace_dir.TOOLS), "limit": outputs_index.LIMIT}


@router.post("/api/outputs/studio")
@W.limiter.limit("30/minute")
async def api_output_to_studio(request: Request):
    """תוצר נפתח בסטודיו בתיקייה משלו - כמו "פתח בסטודיו" של עורך הגרפים (dataviz/web/handoff.py): קישור או עותק תחת
    workspace/<כלי>/studio_handoff/<כיוון>/<שם>, והתוצר עצמו לא זז ולא משתנה. בעורך הגרפים זו אותה תיקייה בדיוק."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    found = outputs_index.locate(str(payload.get("path", "")) if isinstance(payload, dict) else "", W.WORKSPACE_DIR)
    if not found or W._is_under_data_dir(found["path"]):
        return JSONResponse({"error": "הסרטון לא נמצא בין התוצרים."}, status_code=404)
    orientation = found["folder"].split("/")[0]
    root = workspace_dir.tool_output_dir(found["tool"], "studio_handoff", *([orientation] if orientation else []), base=W.WORKSPACE_DIR)
    try:
        result = await run_in_threadpool(dataviz_handoff.studio_folder, found["path"], root)
    except OSError as e:
        return JSONResponse({"error": f"הכנת התיקייה לסטודיו נכשלה: {e}"}, status_code=500)
    W.audit_log.record_action("web", "output_to_studio", details=f"{found['tool']}/{result['file']}",
                              username=request.client.host if request.client else None)
    return result
