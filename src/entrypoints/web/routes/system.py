# entrypoints/web/routes/system.py
#
# הגדרות, גיבויים, סודות, עדכונים, דפדפן-קבצים וסטטיסטיקות מערכת.
# גל 11: הועבר כמו שהוא מ-web_app.py - המצב המשותף (נתיבים, helpers, מנעולים) נשאר
# שם ונגיש כ-W.<שם>, כך ש-monkeypatch.setattr(web_app, ...) חל גם על ה-endpoints כאן.

import json
import os
import shutil
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from utils.shared import docs_sections, encrypted_backup
from utils.media.clip_stats import get_clips_captured_by_day
from utils.shared.credential_health import CREDENTIAL_NAMES
from utils.shared.file_lock import file_lock
from utils.shared.state import CONFIG_LOCK_FILE, DEFAULT_CUSTOM_ACCENT, THEMES, derive_theme_from_accent
from utils.shared.ui_language import ensure_language

from entrypoints import web_app as W

router = APIRouter()


@router.post("/api/rotate_token")
@W.limiter.limit("10/minute")
def api_rotate_token(request: Request):
    """מבטל מיידית את הטוקן הנוכחי ומנפיק אחד חדש - בלי לסגור את השרת בכלל.
    מוגן כבר ע"י ה-middleware למעלה (חייב טוקן תקף כדי להגיע לפה) - כלומר
    רק מי שכבר מחובר יכול לבצע רוטציה, בדיוק כמו "sign out everywhere else"
    בשירותים אחרים: הטאב/מכשיר שביקש את הרוטציה ממשיך לעבוד (מקבל עוגייה
    מעודכנת בתגובה הזו עצמה), וכל קישור/עוגייה ישנים אחרים נפסלים מיד."""
    if not W._is_same_origin(request):   # הגנה לעומק: גם בלי זה ה-cookie הוא SameSite=Lax, אבל כאן מחליפים את מפתח הגישה
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    W.ACCESS_TOKEN = W._generate_token()
    W._persist_token(W.ACCESS_TOKEN)
    W.audit_log.record_action("web", "rotate_token", username=request.client.host if request.client else None)
    response = JSONResponse({"token": W.ACCESS_TOKEN})
    response.set_cookie(W._AUTH_COOKIE_NAME, W.ACCESS_TOKEN, httponly=True, samesite="lax")
    return response


def _remote_access_status(request):
    from utils.shared import tailscale
    found = tailscale.find_tailscale_ipv4()
    # token_url: הקישור המלא לטלפון - רק למי שנכנס עם טוקן המחשב (מכשיר מצומד לא מקבל אותו), ומתעדכן ברוטציה
    with_token = W.TAILSCALE_BASE_URL and getattr(request.state, "auth_kind", None) == "computer"
    return {"tailscale": tailscale.load_enabled(), "active_url": W.TAILSCALE_BASE_URL,
            "token_url": f"{W.TAILSCALE_BASE_URL}/?token={W.ACCESS_TOKEN}" if with_token else None,
            "detected_ip": found[1] if found else None}


@router.get("/api/remote_access")
def api_remote_access(request: Request):
    """גישה מהטלפון דרך Tailscale: ההגדרה השמורה, הכתובת שהשרת מאזין עליה עכשיו (או None), והכתובת שזוהתה כרגע."""
    return _remote_access_status(request)


@router.post("/api/remote_access")
async def api_remote_access_set(request: Request):
    """שומר את ההגדרה (data/remote_access.json) - חל מההפעלה הבאה של השרת, כי ה-sockets נקשרים לפני הטוקן."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    from utils.shared import tailscale
    payload = await request.json()
    tailscale.save_enabled(bool(payload.get("tailscale")))
    W.audit_log.record_action("web", "remote_access_tailscale", details="on" if payload.get("tailscale") else "off",
                              username=request.client.host if request.client else None)
    return _remote_access_status(request)


def _export_dir_status():
    """תיקיית הייצוא (utils/shared/export_dir.py): מה הוגדר, לאן נכתבים התוצרים עכשיו, למה לא לשם (אם לא), ומקום פנוי."""
    from utils.shared import export_dir
    resolution = export_dir.resolve()
    try:
        free_bytes = shutil.disk_usage(resolution.base).free
    except OSError:
        free_bytes = None
    tools = []
    for tool in export_dir.TOOL_FOLDERS:   # שלב 2: תיקייה לכלי ("" = לפי הכללית)
        own = export_dir.resolve_tool(tool)
        tools.append({"tool": tool, "root": export_dir.configured_tool_root(tool), "effective": own.base, "problem": own.problem})
    return {"root": export_dir.configured_root(), "effective": resolution.base, "problem": resolution.problem,
            "workspace": W.WORKSPACE_DIR, "free_bytes": free_bytes, "env_override": export_dir.ENV_VAR in os.environ,
            "tools": tools}


@router.get("/api/export_dir")
def api_export_dir():
    return _export_dir_status()


@router.post("/api/export_dir")
async def api_export_dir_set(request: Request):
    """שומר את תיקיית הייצוא (data/export_settings.json). ריק או workspace = ברירת המחדל. תיקייה שלא קיימת: 400 עם
    missing, והדף שואל אם ליצור אותה (create: true). תיקייה בתוך data/ או בתוך קוד הפרויקט, או שאי אפשר לכתוב אליה - 400.
    tool (שלב 2): התיקייה של כלי אחד - ריק = לפי התיקייה הכללית."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    from utils.shared import export_dir
    payload = await request.json()
    root = str(payload.get("root") or "").strip()
    tool = str(payload.get("tool") or "")
    if tool and tool not in export_dir.TOOL_FOLDERS:
        return JSONResponse({"error": "כלי לא מוכר."}, status_code=400)
    if root and not export_dir.is_workspace(root):
        root = os.path.normpath(root)
        if os.path.isabs(root) and not os.path.exists(root) and payload.get("create"):
            try:
                os.makedirs(root)
            except OSError as e:
                return JSONResponse({"error": f"יצירת התיקייה נכשלה: {e.strerror or e}"}, status_code=400)
        reason = export_dir.invalid_choice_reason(root)
        if reason:
            return JSONResponse({"error": reason, "missing": os.path.isabs(root) and not os.path.exists(root)}, status_code=400)
    else:
        root = ""
    if tool:
        export_dir.save_tool_root(tool, root)
    else:
        export_dir.save_root(root)
    W.audit_log.record_action("web", "export_dir", details=f"{tool or 'all'}: {root or 'workspace'}",
                              username=request.client.host if request.client else None)
    return _export_dir_status()


@router.get("/api/scripts")
def api_scripts():
    favorite_names = W._get_favorite_script_names(W._load_raw_config())
    result = []
    for path in W._find_scripts():
        meta = W.get_script_metadata(path)
        script_id = os.path.relpath(path, W.SCRIPTS_DIR).replace("\\", "/")
        result.append({
            "id": script_id,
            "name": meta["name"],
            "description": meta["description"],
            "concurrency": meta["concurrency"],
            "safety": meta["safety"],
            "category": W._category_for(path),
            "category_key": next((key for key, label in W.CATEGORY_LABELS.items() if label == W._category_for(path)), "tools"),
            "is_favorite": os.path.basename(path) in favorite_names,
            "archived": os.path.basename(path) in W.ARCHIVED_SCRIPTS,
        })
    return result


# POST /api/scripts/favorite הוסר (16.10.2026): המועדפים בדפדפן נשמרים ב-localStorage (קטלוג הסקריפטים של Grok),
# והאפליקציה השולחנית כותבת את favorite_scripts בעצמה (ui/sidebar.py). כאן נשאר רק הקריאה - is_favorite למעלה.


@router.get("/api/scripts/recent")
def api_scripts_recent():
    """קיצור-דרך "הורצו לאחרונה" - זהה ל-ui/sidebar.py, מבוסס על אותו
    utils/shared/job_history.py. מחזיר basenames בלבד (לא ids מלאים) - הצד הלקוח
    (state.scripts, שכבר יש לו) עושה את ההתאמה."""
    return {"names": W.job_history.get_recently_run_script_names(limit=5)}


@router.get("/api/diagnostics")
def api_diagnostics():
    """זהה ל-gui_manager.pyw's open_diagnostics_dialog - אותו utils/shared/diagnostics.py
    בדיוק (FFmpeg/FFprobe/פרשן Python/DB/תחביר my_scripts/שטח פנוי/workspace/
    מנעול רינדור), רק כרשימת JSON במקום דיאלוג Tkinter."""
    return [{"name": name, "ok": ok, "detail": detail} for name, ok, detail in W.run_diagnostics()]


@router.post("/api/credentials/check_validity")
@W.limiter.limit("5/minute")
async def api_credentials_check_validity(request: Request):
    """בדיקת תוקף credential vault בפועל (item: credential vault health-check) -
    קריאות רשת אמיתיות ל-Gemini/Twitch/Discord (utils/shared/credential_health.py's
    check_validity()), לכן POST על-פי-בקשה מפורשת בלבד - לא אוטומטי כמו
    /api/diagnostics (שרק בודק נוכחות, בלי רשת בכלל)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    results = W.check_credential_validity()
    W.audit_log.record_action("web", "credentials_check_validity", username=request.client.host if request.client else None)
    return [{"name": name, "configured": configured, "valid": valid, "detail": detail} for name, configured, valid, detail in results]


@router.get("/api/credentials/rotation_status")
def api_credentials_rotation_status():
    """גיל כל credential (item: key-age tracking) - כמו /api/diagnostics, בלי
    שום קריאת רשת (utils/shared/credential_rotation.py, קובץ JSON מקומי בלבד)."""
    return [
        {"name": name, "configured": configured, "age_days": age_days, "stale": stale}
        for name, configured, age_days, stale in W.get_rotation_status()
    ]


@router.post("/api/credentials/rotate")
@W.limiter.limit("10/minute")
async def api_credentials_rotate(request: Request):
    """מעדכן credential ל-Windows Credential Manager (item: key-age tracking -
    סבב בפועל, לא רק צפייה בגיל) - זהה בעיקרון ל-migrate_secrets_to_vault.py,
    רק דרך שדה בממשק במקום סקריפט חד-פעמי. הערך עצמו אף פעם לא נכתב ל-audit
    log (רק שם ה-credential שהוחלף)."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    if not W.is_vault_available():
        return JSONResponse({"error": "חבילת keyring אינה מותקנת - לא ניתן לשמור ל-Credential Manager."}, status_code=400)
    payload = await request.json()
    name = str(payload.get("name", ""))
    value = str(payload.get("value", ""))
    if name not in CREDENTIAL_NAMES:
        return JSONResponse({"error": "שם credential לא מוכר."}, status_code=400)
    if not value:
        return JSONResponse({"error": "ערך חדש לא יכול להיות ריק."}, status_code=400)
    W.set_vault_secret(name, value)
    W.audit_log.record_action("web", "credential_rotate", details=name, username=request.client.host if request.client else None)
    return {"ok": True}


@router.get("/api/update_check")
def api_update_check(request: Request):
    """זהה ל-gui_manager.pyw's check_for_updates_async - אותו utils/shared/update_checker.py
    בדיוק (GitHub Releases API בלבד, לבדיקה). latest_version הוא None כשאין
    עדכון/כשל רשת/timeout - כל המקרים האלה שקטים בכוונה גם ב-utils/shared/update_checker.py
    עצמו, זו בדיקה לא-קריטית ברקע.
    can_rotate_token (22.10.2026): הבקשה היחידה שהדף שולח בעלייה - "🔑 החלף טוקן" מוסתר כשהוא לא המחשב עצמו
    (מכשיר מצומד / קישור הטוקן דרך Tailscale), כי שם /api/rotate_token עונה 403."""
    return {
        "current_version": W.APP_VERSION,
        "latest_version": W.check_for_update(W.APP_VERSION),
        "releases_url": W.RELEASES_PAGE_URL,
        "portable": W.is_portable(W.BASE_DIR),   # 30.10.2026: בחבילה הניידת - רק קישור להורדה, בלי git pull
        "can_rotate_token": W._is_local_computer(request),
    }


@router.post("/api/update_check/apply")
@W.limiter.limit("3/minute")
def api_update_apply(request: Request):
    """מחיל את העדכון בפועל (item: true auto-update) - git pull --ff-only +
    uv sync (utils/update_checker.apply_update), זהה ל-gui_manager.pyw's
    _do_apply_update. def רגיל (לא async) - Starlette מריץ ב-thread pool
    אוטומטית (אותו עיקרון כמו /api/waveform/probe_nvenc), כי זה יכול לקחת
    יותר מכמה שניות. לעולם לא רץ אוטומטית - רק על-פי אישור מפורש בצד הלקוח."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    if W.is_portable(W.BASE_DIR):
        return JSONResponse({"error": W.PORTABLE_UPDATE_REFUSAL}, status_code=400)
    ok, message = W.apply_update(W.BASE_DIR)
    W.audit_log.record_action("web", "update_apply", details=f"ok={ok}", username=request.client.host if request.client else None)
    return {"ok": ok, "message": message}


@router.get("/api/browse")
def api_browse(path: str = ""):
    """דפדוף תיקיות בצד השרת - דפדפן לא יכול לתת לנו נתיב אמיתי בדיסק מ-<input
    type=file>/גרירה (רק תוכן קובץ, מטעמי אבטחת דפדפן), אבל השרת הזה רץ מקומית
    על אותו מחשב בדיוק כמו gui_manager.pyw ורואה את הדיסק במלואו - אז בחירת
    התיקייה קורית כאן, לא ב-JS של הדפדפן."""
    target = os.path.abspath(path) if path else os.path.expanduser("~")
    if not os.path.isdir(target):
        return JSONResponse({"error": f"הנתיב לא קיים: {target}"}, status_code=400)

    folders = []
    files = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    if entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(entry.name)
                    elif entry.is_file(follow_symlinks=False):
                        # סבב ייצוב: ב-Windows הגודל של scandir בא מרשומת התיקייה, שלא מתעדכנת בזמן שתהליך אחר
                        # כותב לקובץ (.partial.mp4 של ffmpeg הוצג כ-0) - os.stat פותח את הקובץ ומחזיר את הגודל האמיתי
                        size = entry.stat().st_size or os.stat(entry.path).st_size
                        files.append({"name": entry.name, "size": size})
                except OSError:
                    continue
    except PermissionError:
        pass

    parent = os.path.dirname(target)
    return {
        "path": target,
        "parent": parent if parent != target else None,
        "folders": sorted(folders, key=str.lower),
        "files": sorted(files, key=lambda f: f["name"].lower()),
        # רשימת כוננים תמיד מוחזרת (לא רק כשמגיעים לשורש) - כדי שקפיצה לכונן
        # אחר תהיה זמינה מכל נקודה בדפדוף, לא רק אחרי לחיצות "עלייה" חוזרות.
        "drives": W._list_drives(),
    }


@router.post("/api/open_folder")
@W.limiter.limit("20/minute")
async def api_open_folder(request: Request):
    """פותח את תיקיית התוצרים בסייר-הקבצים של המחשב שמריץ את השרת (item 48/93).
    מוגבל ל-workspace/ - זה לא "פתח כל נתיב שרירותי"."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    path = str(payload.get("path", ""))
    target = path if os.path.isdir(path) else os.path.dirname(path)
    if not target or not os.path.isdir(target) or not W._is_under_workspace(target):
        return JSONResponse({"error": "תיקייה לא נמצאה."}, status_code=404)
    try:
        os.startfile(target)  # type: ignore[attr-defined]  # Windows בלבד - בדיוק כמו שאר האפליקציה
    except (AttributeError, OSError) as e:
        return JSONResponse({"error": f"פתיחת התיקייה נכשלה: {e}"}, status_code=500)
    return {"ok": True}


@router.get("/health")
def api_health():
    """בדיקת בריאות (item 28) עבור ניטור זמינות חיצוני - חסינה מהדרישה לטוקן
    גישה (ראו _require_access_token). מכוונת "חי/מגיב" בלבד ומהירה בכוונה -
    בלי לגעת בדיסק/DB/worker - כדי שהיא עצמה לעולם לא תהיה הסיבה לכשל
    (או להאטה) בבדיקת זמינות."""
    return {"status": "ok"}


@router.get("/api/docs/section")
def api_docs_section(doc: str = "", q: str = ""):
    """גל 33: "📖 בתיעוד" ליד הגדרה בעורך-העל - q הוא רשימת מונחים מופרדת ב-| לפי סדר עדיפות
    (דגל, מפתח, שם בעברית); מחזיר את הבלוק הראשון שמזכיר אחד מהם (utils/shared/docs_sections.py)."""
    terms = [t for t in q.split("|") if t.strip()][:6]
    found = docs_sections.find_section(doc, terms)
    if not found:
        return JSONResponse({"error": "לא נמצא סעיף מתאים בתיעוד."}, status_code=404)
    return found


@router.get("/api/settings/global")
def api_settings_global_get():
    """שדות "🌐 כללי" ב-ui/global_settings_tab.py - webhook/turbo/גיבוי
    אוטומטי/מצב לילה. לא כולל את מתגי Docker/סנכרון-סטטוס-בוט (תלויים
    ב-runtime הספציפי של ה-GUI השולחני, לא רק דגלים ב-config.json)."""
    config = W._load_raw_config()
    return {
        "webhook": config.get("webhook", ""),
        "turbo_active": bool(config.get("turbo_active", False)),
        "nas_folder": config.get("nas_folder", ""),
        "auto_backup_active": bool(config.get("auto_backup_active", False)),
        "night_active": bool(config.get("night_active", False)),
    }


@router.post("/api/settings/global")
async def api_settings_global_save(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    with file_lock(CONFIG_LOCK_FILE):
        config = W._load_raw_config()
        config["webhook"] = str(payload.get("webhook", "")).strip()
        config["turbo_active"] = bool(payload.get("turbo_active"))
        config["nas_folder"] = str(payload.get("nas_folder", "")).strip()
        config["auto_backup_active"] = bool(payload.get("auto_backup_active"))
        config["night_active"] = bool(payload.get("night_active"))
        W._save_raw_config(config)
    return {"ok": True}


@router.post("/api/settings/reset")
@W.limiter.limit("10/minute")
def api_settings_reset(request: Request):
    """זהה ל-ui/global_settings_tab.py's reset_settings - מגבה ל-.bak קודם,
    אז מאפס. הפעלה מחדש של ה-GUI/הבוט נדרשת כדי שהשינוי ייכנס לתוקף אצלם
    (יש להם עותק בזיכרון), בדיוק כמו ב-/api/settings/import."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    try:
        with file_lock(CONFIG_LOCK_FILE):
            if os.path.exists(W.CONFIG_FILE):
                shutil.copy2(W.CONFIG_FILE, W.CONFIG_FILE + ".bak")
            W._save_raw_config(W._default_config_dict())
    except Exception as e:
        return JSONResponse({"error": f"האיפוס נכשל: {e}"}, status_code=500)
    W.audit_log.record_action("web", "settings_reset", username=request.client.host if request.client else None)
    return {"ok": True}


@router.get("/api/settings/themes")
def api_settings_themes():
    """כל פרופילי ה-THEMES (מקור אמת יחיד ב-utils/shared/state.py) - כדי שבורר
    ערכת הנושא בדפדפן יבנה את הסוואצ'ים מאותם צבעים בדיוק כמו ה-GUI השולחני,
    לא רשימה כפולה שעלולה להתבדר.
    30.10.2026 (לפני ההפצה): label - השם שמוצג בבורר. המפתח "Rocket League" נשאר כמו שהוא ב-config.json, כדי שערכת הנושא
    השמורה לא תישבר; רק התווית כללית."""
    return {name: {**colors, "label": THEME_LABELS.get(name, name)} for name, colors in THEMES.items()}


THEME_LABELS = {"Rocket League": "כתום"}


@router.get("/api/settings/style")
def api_settings_style_get():
    """theme/custom_accent_hex/language - ראו ui/style_settings_tab.py.
    בכוונה *לא* כולל theme_mode (בהיר/כהה): לזה כבר יש בורר עצמאי משלו
    בדפדפן (toggleTheme, per-browser ב-localStorage) - סנכרון עם ה-GUI
    השולחני היה מבלבל, שני משטחים שונים רשאים להעדיף מצב תצוגה שונה.
    30.10.2026: language - "en" בהתקנה חדשה, "he" נשמר בהתקנה קיימת (ensure_language); הדף שואל כאן כשבדפדפן אין בחירה."""
    language = ensure_language(W.CONFIG_FILE, CONFIG_LOCK_FILE)
    config = W._load_raw_config()
    return {
        "theme": config.get("theme", "Green"),
        "custom_accent_hex": config.get("custom_accent_hex", DEFAULT_CUSTOM_ACCENT),
        "language": language,
    }


@router.post("/api/settings/style")
async def api_settings_style_save(request: Request):
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    with file_lock(CONFIG_LOCK_FILE):
        config = W._load_raw_config()

        theme = str(payload.get("theme", "Green"))
        config["theme"] = theme if theme in THEMES else "Green"

        custom_hex = str(payload.get("custom_accent_hex", "")).strip()
        if custom_hex:
            config["custom_accent_hex"] = custom_hex
            # THEMES הוא dict גלובלי-לתהליך (לא נשמר ב-config.json עצמו) - בלי
            # לעדכן את THEMES["Custom"] כאן, api_settings_themes (ולכן swatch ה-
            # "מותאם אישית" בדפדפן) היה ממשיך להראות את הצבע הישן עד הפעלה מחדש
            # של תהליך השרת, גם אחרי שהמשתמש בחר צבע חדש.
            THEMES["Custom"] = derive_theme_from_accent(custom_hex)

        language = str(payload.get("language", "he"))
        config["language"] = language if language in ("he", "en") else "he"

        W._save_raw_config(config)
    return {"ok": True}


@router.get("/api/hardware_stats")
def api_hardware_stats():
    """CPU/RAM/GPU/VRAM/Encoder - אותו utils/shared/hardware.py בדיוק כמו ui/sidebar.py
    השולחני (מקור אמת יחיד), כדי שממשק הדפדפן לא יישאר "עיוור" למה שקורה
    בפועל על המחשב בזמן רינדור, בניגוד לסיידבר השולחני. encoder הוא ניצולת
    ה-NVENC הייעודית - נפרדת מ-gpu (CUDA/shader כללי בלבד), שיכולה להישאר
    נמוכה גם כשה-NVENC עסוק לגמרי (הפילטרים שלפני הקידוד רצים ב-CPU)."""
    cpu, ram = W.get_system_stats()
    gpu, vram, encoder = W.get_gpu_stats()
    return {"cpu": cpu, "ram": ram, "gpu": gpu, "vram": vram, "encoder": encoder}


@router.get("/api/render_stats")
def api_render_stats():
    """זמן רינדור ממוצע לכל סקריפט, מבוסס על היסטוריית ריצות מוצלחות - אותו
    utils/job_history.get_average_render_durations() בדיוק כמו פקודת
    /render_stats בדיסקורד; עד כה זה היה מידע זמין רק דרך הבוט, לא דרך
    ממשק הדפדפן בכלל."""
    rows = W.job_history.get_average_render_durations()
    return [
        {"script": script_name, "avg_seconds": avg_seconds, "run_count": run_count}
        for script_name, avg_seconds, run_count in rows
    ]


@router.get("/api/hwaccel_savings")
def api_hwaccel_savings():
    """השוואת זמן רינדור ממוצע-לקובץ בין ריצות video_editor.py עם/בלי
    --hwaccel (item: "time saved with --hwaccel" metric) - null אם אין
    מספיק היסטוריה (חסרה קבוצה שלמה) להשוואה משמעותית."""
    return W.job_history.get_hwaccel_time_comparison()


@router.get("/api/hardware_history")
def api_hardware_history(hours: int = 24):
    """היסטוריית CPU/RAM/GPU מעבר לדגימה הרגעית (item: historical hardware usage
    graph) - utils/shared/hardware_history.py, נשמר ל-DB (לא רק בזיכרון כמו hw-panel
    החי בסיידבר) כדי לשרוד restart של השרת."""
    rows = W.hardware_history.get_recent_samples(hours=hours)
    return {
        "recorded_at": [row[0] for row in rows],
        "cpu": [row[1] for row in rows],
        "ram": [row[2] for row in rows],
        "gpu": [row[3] for row in rows],
    }


@router.get("/api/game_playtime")
def api_game_playtime():
    """סך שעות משחק מצטבר לכל משחק (item: personal stats dashboard) -
    utils/media/game_playtime.py, נצבר רק כש-gui_manager.pyw רץ (ראו שם), אבל נקרא
    מכאן על אותו DB משותף (data_paths.BOT_DB) - כך שתיעוד שנצבר מהדסקטופ מוצג גם כאן."""
    return [
        {"game": name, "hours": total_seconds / 3600, "last_played_at": last_played_at}
        for name, total_seconds, last_played_at in W.game_playtime.get_playtime_summary()
    ]


@router.get("/api/clips_captured_by_day")
def api_clips_captured_by_day(days: int = 30):
    """קליפים שנלכדו ליום, days האחרונים (item: personal stats dashboard) -
    utils/media/clip_stats.py, נגזר מ-mtime של workspace/clips בפועל - בכוונה בלי
    פירוק לפי משחק (ראו utils/media/clip_stats.py's הערת הראש)."""
    counts = get_clips_captured_by_day(W.CLIPS_DIR, days=days)
    return {"dates": list(counts.keys()), "counts": list(counts.values())}


@router.get("/api/settings/export")
def api_settings_export():
    """מוריד את data/config.json הגולמי כמות שהוא - עד כה הדרך היחידה להעביר
    הגדרות בין מחשבים (או לגבות ידנית לפני ניסוי) הייתה העתקת הקובץ ידנית."""
    if not os.path.exists(W.CONFIG_FILE):
        return JSONResponse({"error": "עדיין אין קובץ הגדרות - שמור הגדרה כלשהי מה-GUI קודם."}, status_code=404)
    return FileResponse(W.CONFIG_FILE, filename="clipforge_settings.json", media_type="application/json")


@router.post("/api/settings/import")
@W.limiter.limit("10/minute")
async def api_settings_import(request: Request):
    """מייבא config.json חדש - מגבה את הקיים ל-.bak קודם (אותו עיקרון בדיוק
    כמו איפוס הגדרות ב-ui/global_settings_tab.py, כדי שאפשר יהיה לשחזר אם
    הייבוא היה טעות). הקובץ נכתב לדיסק בלבד - אין GUI/בוט חי בתהליך הזה
    לרענן, אז השינוי נכנס לתוקף רק אחרי הפעלה מחדש שלהם."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "קובץ JSON לא תקין."}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "תוכן ה-JSON חייב להיות אובייקט (dict), לא רשימה/ערך בודד."}, status_code=400)

    try:
        if os.path.exists(W.CONFIG_FILE):
            shutil.copy2(W.CONFIG_FILE, W.CONFIG_FILE + ".bak")
        os.makedirs(os.path.dirname(W.CONFIG_FILE), exist_ok=True)
        with open(W.CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
    except Exception as e:
        return JSONResponse({"error": f"הייבוא נכשל: {e}"}, status_code=500)
    W.audit_log.record_action("web", "settings_import", username=request.client.host if request.client else None)
    return {"ok": True}


@router.post("/api/backup/create_encrypted")
@W.limiter.limit("5/minute")
async def api_backup_create_encrypted(request: Request):
    """יוצר קובץ גיבוי מוצפן יחיד (utils/shared/encrypted_backup.py) של כל data/ -
    בניגוד לגיבוי היומי האוטומטי הקיים (cogs/scheduler_cog.py), שכותב zip/DB
    גלויים לגמרי תחת data/backups/, זה מיועד להוצאה בטוחה מהמכונה (דיסק חיצוני/
    ענן) - הסיסמה נדרשת בכל קריאה ולא נשמרת בשום מקום."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    passphrase = str(payload.get("passphrase", ""))

    filename = f"encrypted_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ibkp"
    output_path = os.path.join(W.BACKUPS_DIR, filename)
    try:
        result = encrypted_backup.create_backup_bundle(passphrase, output_path, data_dir=W.DATA_DIR)
    except encrypted_backup.BackupError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    W.audit_log.record_action("web", "backup_create", details=filename, username=request.client.host if request.client else None)
    return {"filename": filename, "included_files": result["included_files"], "size_bytes": result["size_bytes"]}


@router.get("/api/backup/list")
def api_backup_list():
    if not os.path.isdir(W.BACKUPS_DIR):
        return []
    entries = []
    for name in sorted(os.listdir(W.BACKUPS_DIR), reverse=True):
        if not name.endswith(".ibkp"):
            continue
        full_path = os.path.join(W.BACKUPS_DIR, name)
        entries.append({"filename": name, "size_bytes": os.path.getsize(full_path), "modified_at": os.path.getmtime(full_path)})
    return entries


@router.get("/api/backup/download/{filename}")
def api_backup_download(filename: str):
    validated = W._validate_backup_filename(filename)
    if not validated:
        return JSONResponse({"error": "קובץ גיבוי לא נמצא."}, status_code=404)
    return FileResponse(validated, filename=os.path.basename(validated), media_type="application/octet-stream")


@router.post("/api/backup/restore")
@W.limiter.limit("5/minute")
async def api_backup_restore(request: Request):
    """משחזר גיבוי מוצפן ישירות לתוך data/ - כל קובץ קיים שעומד להידרס מגובה
    קודם ל-<name>.bak (אותו עיקרון כמו api_settings_reset/api_settings_import).
    מומלץ לעצור את הבוט/ה-GUI לפני שחזור, כדי לא לדרוס קובץ DB שמישהו אחר
    מחזיק פתוח לכתיבה כרגע."""
    if not W._is_same_origin(request):
        return JSONResponse({"error": "הבקשה נדחתה (Origin לא תואם)."}, status_code=403)
    payload = await request.json()
    passphrase = str(payload.get("passphrase", ""))
    validated = W._validate_backup_filename(payload.get("filename", ""))
    if not validated:
        return JSONResponse({"error": "קובץ גיבוי לא נמצא."}, status_code=404)

    try:
        result = encrypted_backup.restore_backup_bundle(passphrase, validated, data_dir=W.DATA_DIR)
    except encrypted_backup.BackupError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    W.audit_log.record_action("web", "backup_restore", details=os.path.basename(validated), username=request.client.host if request.client else None)
    return {"restored_files": result["restored_files"]}
