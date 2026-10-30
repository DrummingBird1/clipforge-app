# web_dashboard.py
#
# דשבורד סטטוס מקומי - כדי לבדוק שהבוט/עבודות רצות בלי לפתוח את ה-GUI.
# מאזין רק ל-127.0.0.1 (המחשב המקומי בלבד). כדי לגשת אליו מהנייד/מרחוק צריך
# להקים בעצמך מנהרה (Tailscale / Cloudflare Tunnel וכו') - זו לא פעולה שמתבצעת
# כאן, כי היא דורשת חשבון חיצוני משלך.
#
# הרצה: python web_dashboard.py
# ואז גישה מהדפדפן: http://127.0.0.1:8877

import html
import json
import os
import sys
import time

# מונע UnicodeEncodeError בקונסולת Windows כשה-codepage לא UTF-8 (למשל cp1255/cp1252)
if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    import psutil
except ImportError:
    psutil = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# src/entrypoints/ תחת שורש הפרויקט - כל קוד המקור הראשוני (utils/וכו') יושב
# תחת src/, לא בשורש עצמו, אז זה מה שצריך להיות ב-sys.path כדי ש-"utils.*"
# למטה ייובא בהצלחה - לא BASE_DIR (שורש הפרויקט) עצמו.
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.shared.logging_setup import setup_persistent_logging
setup_persistent_logging("dashboard")

from utils.shared import db
from utils.shared.health_status import format_duration
from utils.shared import data_paths

DB_PATH = data_paths.path(data_paths.BOT_DB)
CONFIG_PATH = data_paths.path(data_paths.CONFIG)
ROCKET_SETTINGS_PATH = data_paths.path(data_paths.ROCKET_SETTINGS)

# item: "מרכז שליטה" כללי לכל הבוטים/שרתים המקומיים - גרסה קלה, קריאה-בלבד:
# סורקת תיקיות-קטגוריה מוכרות תחת PROJECTS_ROOT (ברירת המחדל - שתי רמות מעל
# הפרויקט הזה, למשל D:\Projects\ אם הפרויקט יושב תחת D:\Projects\clipforge)
# ומראה סטטוס תהליך-בסיסי לכל אחת, בלי לדעת שום דבר ספציפי על איך כל פרויקט
# מופעל/נעצר - זו תצוגת-מצב-מהירה בלבד, לא תחליף לכלי ניהול-פרויקטים מלא
# (אם קיים אצלך כלי כזה כבר - הפעל/עצור אמיתיים שייכים שם, לא כאן).
PROJECTS_ROOT = os.environ.get("CLIPFORGE_PROJECTS_ROOT") or os.path.dirname(os.path.dirname(BASE_DIR))
SIBLING_CATEGORY_FOLDERS = ("Bots", "Apps", "Tools", "Websites")

app = FastAPI(title="ClipForge - Status Dashboard")


def _is_project_folder_active(folder_path):
    """True אם נמצא תהליך חי שה-cwd/cmdline שלו מצביע לתוך folder_path - לא
    ספציפי לאיך כל פרויקט מופעל (Python/Node/וכו') בכוונה, כדי שזה יעבוד עם
    כל סוג פרויקט בלי קונפיגורציה נוספת לכל אחד. None (לא False) אם psutil
    לא מותקן בכלל - "לא ניתן לבדוק" שונה במפורש מ"בדקנו, לא רץ"."""
    if not psutil:
        return None
    normalized_folder = os.path.normcase(os.path.abspath(folder_path))
    try:
        for proc in psutil.process_iter(["cwd", "cmdline"]):
            try:
                cwd = proc.info.get("cwd")
                if cwd and os.path.normcase(os.path.abspath(cwd)).startswith(normalized_folder):
                    return True
                cmdline = proc.info.get("cmdline") or []
                if any(normalized_folder in os.path.normcase(str(part)) for part in cmdline):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def discover_sibling_projects(projects_root=None):
    """מחזיר [(שם, נתיב יחסי מ-PROJECTS_ROOT, is_active), ...] לכל תת-תיקייה
    תחת תיקיות-הקטגוריה המוכרות (Bots/Apps/Tools/Websites) - קריאה-בלבד
    לגמרי, לא נוגע/מפעיל/עוצר שום דבר. לא כולל את תיקיית הפרויקט הזה עצמו
    (ClipForge כבר מקבל כרטיס סטטוס משלו למעלה בדף)."""
    root = projects_root if projects_root is not None else PROJECTS_ROOT
    if not os.path.isdir(root):
        return []
    own_folder = os.path.normcase(os.path.abspath(BASE_DIR))
    results = []
    for category in SIBLING_CATEGORY_FOLDERS:
        category_path = os.path.join(root, category)
        if not os.path.isdir(category_path):
            continue
        try:
            entries = sorted(os.scandir(category_path), key=lambda e: e.name.lower())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if os.path.normcase(os.path.abspath(entry.path)) == own_folder:
                continue
            results.append((entry.name, f"{category}/{entry.name}", _is_project_folder_active(entry.path)))
    return results


def is_bot_running():
    if not psutil:
        return None
    try:
        for proc in psutil.process_iter(["name", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            if any("main.py" in str(part) for part in cmdline):
                return True
    except Exception:
        pass
    return False


def get_bot_uptime_seconds():
    if not psutil:
        return None
    try:
        for proc in psutil.process_iter(["name", "cmdline", "create_time"]):
            cmdline = proc.info.get("cmdline") or []
            if any("main.py" in str(part) for part in cmdline):
                return time.time() - proc.info["create_time"]
    except Exception:
        pass
    return None


def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def db_query(query, params=()):
    if not os.path.exists(DB_PATH):
        return []
    try:
        with db.connect(DB_PATH) as conn:
            return conn.execute(query, params).fetchall()
    except Exception:
        return []


def get_disk_free_gb():
    try:
        _, _, free = __import__("shutil").disk_usage(BASE_DIR)
        return round(free / (1024 ** 3), 1)
    except Exception:
        return None


def render_page():
    bot_running = is_bot_running()
    config = read_json(CONFIG_PATH, {})
    rocket_settings = read_json(ROCKET_SETTINGS_PATH, {})

    rss_feeds = db_query("SELECT name, url, channel_id FROM rss_feeds")
    steam_games = db_query("SELECT name, app_id, channel_id FROM steam_games")
    jobs = db_query(
        "SELECT script_name, status, started_at, duration_seconds FROM job_history ORDER BY id DESC LIMIT 20"
    )

    disk_free = get_disk_free_gb()
    uptime_seconds = get_bot_uptime_seconds()
    uptime_text = format_duration(uptime_seconds) if uptime_seconds is not None else "לא ידוע"

    bot_badge = (
        '<span class="badge ok">🟢 רץ</span>' if bot_running
        else '<span class="badge off">🔴 כבוי</span>' if bot_running is False
        else '<span class="badge unknown">⚪ לא ידוע (psutil חסר)</span>'
    )

    def jobs_rows():
        if not jobs:
            return '<tr><td colspan="4" class="muted">עוד לא בוצעו ריצות</td></tr>'
        out = []
        for script_name, status, started_at, duration in jobs:
            icon = "✅" if status == "success" else "❌"
            dur = f"{duration:.0f}s" if duration and duration < 60 else f"{(duration or 0) / 60:.1f}m"
            out.append(f"<tr><td>{icon}</td><td>{html.escape(str(script_name))}</td><td>{html.escape(str(started_at))}</td><td>{dur}</td></tr>")
        return "".join(out)

    def rss_rows():
        if not rss_feeds:
            return '<tr><td colspan="3" class="muted">אין מקורות RSS</td></tr>'
        return "".join(f"<tr><td>{html.escape(str(n))}</td><td>{html.escape(str(u))}</td><td>{html.escape(str(c))}</td></tr>" for n, u, c in rss_feeds)

    def steam_rows():
        if not steam_games:
            return '<tr><td colspan="3" class="muted">אין משחקים במעקב</td></tr>'
        return "".join(f"<tr><td>{html.escape(str(n))}</td><td>{html.escape(str(a))}</td><td>{html.escape(str(c))}</td></tr>" for n, a, c in steam_games)

    sibling_projects = discover_sibling_projects()

    def sibling_rows():
        if not sibling_projects:
            return f'<tr><td colspan="3" class="muted">לא נמצאו פרויקטים תחת {html.escape(PROJECTS_ROOT)}</td></tr>'
        out = []
        for name, rel_path, is_active in sibling_projects:
            badge = (
                '<span class="badge ok">🟢 נראה פעיל</span>' if is_active
                else '<span class="badge off">🔴 לא זוהה</span>' if is_active is False
                else '<span class="badge unknown">⚪ לא ידוע</span>'
            )
            out.append(f"<tr><td>{html.escape(name)}</td><td class=\"muted\">{html.escape(rel_path)}</td><td>{badge}</td></tr>")
        return "".join(out)

    return f"""
    <!doctype html>
    <html lang="he" dir="rtl">
    <head>
        <meta charset="utf-8">
        <meta http-equiv="refresh" content="30">
        <title>ClipForge - סטטוס</title>
        <style>
            body {{ background:#0c0c0e; color:#e7e7ee; font-family: "Segoe UI", sans-serif; padding: 24px; }}
            h1 {{ color:#00e5ff; }}
            .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }}
            .card {{ background:#141418; border:1px solid #22222b; border-radius: 12px; padding: 16px; }}
            table {{ width:100%; border-collapse: collapse; font-size: 13px; }}
            td, th {{ padding: 4px 8px; text-align: right; border-bottom: 1px solid #22222b; }}
            .muted {{ color:#8e8e9a; }}
            .badge {{ padding:3px 10px; border-radius: 100px; font-size: 13px; }}
            .badge.ok {{ background:#0f3d24; color:#4ade80; }}
            .badge.off {{ background:#3d1418; color:#f87171; }}
            .badge.unknown {{ background:#22222b; color:#8e8e9a; }}
            .stat {{ font-size: 22px; font-weight:bold; }}
        </style>
    </head>
    <body>
        <h1>🎬 ClipForge - סטטוס</h1>
        <div class="grid">
            <div class="card">
                <div>סטטוס בוט ClipForge</div>
                <div class="stat">{bot_badge}</div>
            </div>
            <div class="card">
                <div>שטח פנוי בדיסק</div>
                <div class="stat">{disk_free if disk_free is not None else "?"} GB</div>
            </div>
            <div class="card">
                <div>זמן פעילות הבוט</div>
                <div class="stat">{uptime_text}</div>
            </div>
            <div class="card">
                <div>תיקיית עבודה נוכחית</div>
                <div class="muted">{html.escape(str(rocket_settings.get("input_dir", "-")))}</div>
            </div>
            <div class="card">
                <div>ערכת נושא פעילה</div>
                <div class="muted">{html.escape(str(config.get("theme", "-")))}</div>
            </div>
        </div>

        <div class="card" style="margin-bottom:16px;">
            <h3>📜 היסטוריית ריצות אחרונות</h3>
            <table><tr><th></th><th>סקריפט</th><th>זמן התחלה</th><th>משך</th></tr>{jobs_rows()}</table>
        </div>

        <div class="grid">
            <div class="card">
                <h3>📰 מקורות RSS</h3>
                <table><tr><th>שם</th><th>URL</th><th>ערוץ</th></tr>{rss_rows()}</table>
            </div>
            <div class="card">
                <h3>🎮 משחקי Steam במעקב</h3>
                <table><tr><th>שם</th><th>App ID</th><th>ערוץ</th></tr>{steam_rows()}</table>
            </div>
        </div>

        <div class="card" style="margin-bottom:16px;">
            <h3>🗂️ פרויקטים אחרים תחת {html.escape(PROJECTS_ROOT)}</h3>
            <table><tr><th>שם</th><th>נתיב</th><th>סטטוס</th></tr>{sibling_rows()}</table>
            <p class="muted" style="margin-top:8px">תצוגת-מצב מהירה בלבד (זיהוי תהליך רץ שה-cwd/cmdline שלו מצביע לתוך התיקייה) - לא כלי ניהול: אין כאן הפעלה/עצירה מרחוק.</p>
        </div>

        <p class="muted">מתרענן אוטומטית כל 30 שניות · זמין רק במחשב המקומי (127.0.0.1)</p>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return render_page()


@app.get("/api/status")
def api_status():
    return {
        "bot_running": is_bot_running(),
        "disk_free_gb": get_disk_free_gb(),
        "uptime_seconds": get_bot_uptime_seconds(),
    }


@app.get("/api/sibling_projects")
def api_sibling_projects():
    return {
        "root": PROJECTS_ROOT,
        "projects": [
            {"name": name, "path": rel_path, "active": is_active}
            for name, rel_path, is_active in discover_sibling_projects()
        ],
    }


if __name__ == "__main__":
    print("🚀 דשבורד הסטטוס עולה על http://127.0.0.1:8877 (מקומי בלבד)")
    uvicorn.run(app, host="127.0.0.1", port=8877)
