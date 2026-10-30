# entrypoints/web/routes/page.py
#
# הדף עצמו, manifest/אייקונים ו-service worker של ה-PWA.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import gzip
import os

from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi import APIRouter, Request

from entrypoints.web import frontend_assembly as fa
from entrypoints.web.frontend_assembly import assemble_styleguide, dev_reload_enabled

from entrypoints import web_app as W

router = APIRouter()


def _accepts_gzip(request: Request) -> bool:
    return "gzip" in request.headers.get("accept-encoding", "").lower()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    # CLIPFORGE_DEV_RELOAD_PAGE=1: עריכת קובץ ב-web/frontend/ נראית ברענון, בלי הפעלה מחדש
    if dev_reload_enabled():
        html = W.assemble_page().encode("utf-8")
        compressed = gzip.compress(html, 6)
    else:
        html, compressed = W._PAGE_HTML.encode("utf-8"), W._PAGE_HTML_GZIP
    # גל 24: ה-HTML לא נשמר ב-cache (תמיד מפנה ל-bundles העדכניים), ה-bundles כן - לתמיד
    headers = {"Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
    if _accepts_gzip(request):
        headers["Content-Encoding"] = "gzip"
        return Response(content=compressed, media_type="text/html; charset=utf-8", headers=headers)
    return Response(content=html, media_type="text/html; charset=utf-8", headers=headers)


@router.get("/static/{name}")
def static_bundle(name: str, request: Request):
    """גל 24: ה-CSS/JS של הדף (app.<hash>.css|js). שם שלא קיים (למשל hash ישן) = 404 -
    לעולם לא מגישים תוכן אחר תחת שם שנשמר ב-cache לתמיד."""
    assets = fa.build_assets() if dev_reload_enabled() else W._PAGE_ASSETS
    asset = assets.get(name)
    if asset is None:
        return Response(status_code=404)
    headers = {"Cache-Control": "public, max-age=31536000, immutable", "Vary": "Accept-Encoding"}
    body = asset["body"]
    if _accepts_gzip(request):
        headers["Content-Encoding"] = "gzip"
        body = asset["gzip"]
    return Response(content=body, media_type=str(asset["media_type"]), headers=headers)


@router.get("/styleguide", response_class=HTMLResponse)
def styleguide():
    """גל 15: מערכת העיצוב - כל ה-tokens, האייקונים והרכיבים בעמוד אחד."""
    return assemble_styleguide()


@router.get("/manifest.json")
def manifest():
    """PWA manifest - מאפשר "הוסף למסך הבית" בנייד (רלוונטי בעיקר במצב --lan).
    item: התקנת PWA - אייקוני PNG אמיתיים (192/512, אותו סמל מותג ClipForge
    שכבר קיים ל-exe/מגש המערכת - dev/generate_app_icon.py) במקום
    ה-SVG-אימוג'י הזמני הקודם, שהיה מספיק בתור favicon אבל נראה גרוע כאייקון
    אפליקציה מותקנת על מסך הבית/taskbar."""
    return {
        "name": "ClipForge - Web",
        "short_name": "ClipForge",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0b0c0f",
        "theme_color": "#0b0c0f",
        "icons": [
            {"src": "/assets/app_icon_192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/app_icon.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


@router.get("/assets/app_icon_192.png")
def app_icon_192():
    return FileResponse(W.APP_ICON_192_PNG, media_type="image/png")


@router.get("/assets/app_icon.png")
def app_icon_512():
    return FileResponse(W.APP_ICON_PNG, media_type="image/png")


# גל 16: הפונטים של הממשק (Heebo + JetBrains Mono, OFL) - מקומיים, בלי תלות באינטרנט.
# רשימה סגורה: רק שמות קבצים ידועים, בלי נתיבים שנבנים מהבקשה.
_UI_FONTS = {"heebo-hebrew.woff2", "heebo-latin.woff2", "jetbrains-mono-latin.woff2"}


@router.get("/assets/fonts/{name}")
def ui_font(name: str):
    if name not in _UI_FONTS:
        return Response(status_code=404)
    return FileResponse(os.path.join(W.BASE_DIR, "assets", "fonts", name), media_type="font/woff2",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


# גל 21: מילון התרגום של הממשק (מפתח = הטקסט העברי בלי אימוג'י מוביל). רשימה סגורה.
_UI_LANGS = {"en"}
_I18N_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "i18n")


@router.get("/api/ui_strings/{lang}")
def ui_strings(lang: str):
    if lang not in _UI_LANGS:
        return Response(status_code=404)
    return FileResponse(os.path.join(_I18N_DIR, f"{lang}.json"), media_type="application/json")


@router.get("/sw.js")
def service_worker():
    """שירות-עובד מינימלי (item: התקנת PWA) - install/activate ריקים + fetch
    שרק מעביר הלאה (pass-through, בלי שום caching בפועל) - מספיק לקריטריון
    ההתקנה (beforeinstallprompt) של רוב הדפדפנים, בלי לסכן תוכן מיושן על
    אפליקציה חיה שמשתנה תדיר (אין שום דבר כאן שעלול "להיתקע" בגרסה ישנה)."""
    sw_code = (
        "self.addEventListener('install', () => self.skipWaiting());\n"
        "self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));\n"
        "self.addEventListener('fetch', (event) => event.respondWith(fetch(event.request)));\n"
    )
    return Response(content=sw_code, media_type="application/javascript")
