# entrypoints/web/routes/devices.py
#
# צימוד מכשיר (22.10.2026, באישור המשתמש). המאגר: utils/shared/device_pairing.py; מי מורשה - ה-middleware ב-web_app.py:
# - /pair ו-/api/pair/token עובדים בלי טוקן - הקוד החד-פעמי (5 דקות) הוא האימות. דף /pair לא מממש את הקוד בטעינה
#   (סורקי QR ותצוגות מקדימות פותחים קישורים לבד) - רק הלחיצה על הכפתור (POST).
# - /api/devices/* - רק מהמחשב עצמו (טוקן המחשב + 127.0.0.1): יצירת קוד, הרשימה, ביטול, התפוגה.
import html
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from utils.shared import device_pairing

from entrypoints import web_app as W

router = APIRouter()

_FOREIGN_ORIGIN = "הבקשה נדחתה (Origin לא תואם)."
# הדף היחיד של האפליקציה שנפתח בלי טוקן - קטן ועצמאי, בלי ה-JS/CSS של הממשק (שדורשים טוקן)
_PAGE = """<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>ClipForge - צימוד מכשיר</title>
<style>body{{font-family:system-ui,sans-serif;background:#16161a;color:#ececf1;max-width:30rem;margin:2.5rem auto;padding:0 1rem;line-height:1.6}}
button{{font:inherit;font-size:1.1rem;padding:.7rem 1.4rem;border:0;border-radius:.5rem;background:#4f7cff;color:#fff;cursor:pointer}}</style>
</head><body><h1>📱 ClipForge</h1>{body}</body></html>"""
_NO_STORE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _page(body_html, status_code=200):
    return HTMLResponse(_PAGE.format(body=body_html), status_code=status_code, headers=_NO_STORE)


def _client_ip(request):
    return request.client.host if request.client else None


async def _json_body(request):
    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _pair_bases():
    """כתובות שמכשיר אחר יכול להגיע אליהן - Tailscale קודם, אחר כך --lan."""
    return [url for url in (W.TAILSCALE_BASE_URL, W.LAN_BASE_URL) if url]


# ---------- המכשיר: דף הצימוד ומימוש הקוד ----------
@router.get("/pair", response_class=HTMLResponse)
def pair_page(code: str = ""):
    name = W.device_store.peek_code(code)
    if name is None:
        return _page("<p>קוד הצימוד פג או כבר שומש. צור קוד חדש במחשב: הגדרות כלליות, 📱 גישה מהטלפון.</p>", 400)
    return _page(
        f"<p>לצמד את המכשיר הזה ל-ClipForge בשם <b>{html.escape(name)}</b>?</p>"
        "<p>אחרי הצימוד המכשיר נשאר מחובר גם כשהשרת מופעל מחדש, עד שמבטלים אותו מהמחשב.</p>"
        f'<form method="post" action="/pair"><input type="hidden" name="code" value="{html.escape(code)}">'
        "<button type=\"submit\">צמד את המכשיר</button></form>")


@router.post("/pair")
@W.limiter.limit("5/minute")
async def pair_redeem(request: Request):
    if not W._is_same_origin(request):
        return _page(f"<p>{_FOREIGN_ORIGIN}</p>", 403)
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    try:
        token, device = W.device_store.redeem((form.get("code") or [""])[0], kind="browser", ip=_client_ip(request))
    except device_pairing.PairingError as e:
        return _page(f"<p>{html.escape(str(e))}</p>", 400)
    W.audit_log.record_action("web", "device_paired", details=device["name"], username=_client_ip(request))
    response = RedirectResponse("/?screen=phone", status_code=303, headers=_NO_STORE)   # 23.10.2026: ישר למסך "📱 בטלפון"
    response.set_cookie(device_pairing.COOKIE_NAME, token, max_age=device_pairing.COOKIE_MAX_AGE_SECONDS,
                        httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return response


@router.post("/api/pair/token")
@W.limiter.limit("5/minute")
async def api_pair_token(request: Request):
    """לסקריפט (ZimaOS) בלי דפדפן: מממש את הקוד ומחזיר את הטוקן - פעם אחת בלבד. משם: Authorization: Bearer <טוקן>."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": _FOREIGN_ORIGIN}, status_code=403)
    payload = await _json_body(request)
    try:
        token, device = W.device_store.redeem(payload.get("code"), kind="script", ip=_client_ip(request))
    except device_pairing.PairingError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    W.audit_log.record_action("web", "device_paired", details=device["name"], username=_client_ip(request))
    return JSONResponse({"token": token, "device": device, "header": "Authorization: Bearer <token>"}, headers=_NO_STORE)


# ---------- המחשב: יצירת קוד, רשימה, ביטול (ה-middleware מגביל את /api/devices למחשב עצמו) ----------
@router.get("/api/devices")
def api_devices():
    return {"devices": W.device_store.list_devices(), "expire_unused": W.device_store.expire_unused,
            "expire_days": device_pairing.EXPIRE_UNUSED_DAYS, "pair_bases": _pair_bases()}


@router.post("/api/devices/pair")
@W.limiter.limit("10/minute")
async def api_devices_pair(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": _FOREIGN_ORIGIN}, status_code=403)
    bases = _pair_bases()
    if not bases:
        return JSONResponse({"error": "אין כתובת שמכשיר אחר יכול להגיע אליה. הפעל את הגישה מהטלפון (Tailscale) והפעל את "
                                      "השרת מחדש, או הפעל אותו עם --lan."}, status_code=409)
    payload = await _json_body(request)
    try:
        created = W.device_store.create_code(payload.get("name"))
    except device_pairing.PairingError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    W.audit_log.record_action("web", "device_pair_code", details=created["name"], username=_client_ip(request))
    links = [f"{base}/pair?code={created['code']}" for base in bases]
    return {"code": created["code"], "name": created["name"], "expires_at": created["expires_at"],
            "url": links[0], "urls": links, "token_url": f"{bases[0]}/api/pair/token"}


@router.get("/api/devices/pair/status")
def api_devices_pair_status(code: str = ""):
    state, device = W.device_store.code_state(code)
    return {"state": state, "device": device}


@router.post("/api/devices/revoke")
async def api_devices_revoke(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": _FOREIGN_ORIGIN}, status_code=403)
    device_id = str((await _json_body(request)).get("id") or "")
    if not W.device_store.revoke(device_id):
        return JSONResponse({"error": "המכשיר לא נמצא (אולי כבר בוטל)."}, status_code=404)
    W.audit_log.record_action("web", "device_revoked", details=device_id, username=_client_ip(request))
    return api_devices()


@router.post("/api/devices/revoke_all")
async def api_devices_revoke_all(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": _FOREIGN_ORIGIN}, status_code=403)
    count = W.device_store.revoke_all()
    W.audit_log.record_action("web", "devices_revoked_all", details=str(count), username=_client_ip(request))
    return api_devices()


@router.post("/api/devices/settings")
async def api_devices_settings(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": _FOREIGN_ORIGIN}, status_code=403)
    W.device_store.set_expire_unused(bool((await _json_body(request)).get("expire_unused")))
    return api_devices()
