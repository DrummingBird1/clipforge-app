# entrypoints/web/routes/notifications.py
#
# 23.10.2026: מרכז ההתראות (utils/shared/notification_log.py). המונה בדף הראשי שואל את /unread; הרשימה נטענת כשפותחים
# אותה, ו"נקרא" מסומן עד ההתראה האחרונה שהוצגה.
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from utils.shared import notification_log

from entrypoints import web_app as W

router = APIRouter()


@router.get("/api/notifications")
def api_notifications(limit: int = 50):
    return {"items": notification_log.recent(limit), **notification_log.unread()}


@router.get("/api/notifications/unread")
def api_notifications_unread():
    return notification_log.unread()


@router.post("/api/notifications/read")
async def api_notifications_read(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    up_to = payload.get("up_to") if isinstance(payload, dict) else None
    if not isinstance(up_to, int) or isinstance(up_to, bool):
        return JSONResponse({"error": "חסר up_to (המזהה של ההתראה האחרונה שהוצגה)."}, status_code=400)
    notification_log.mark_read(up_to)
    return notification_log.unread()
