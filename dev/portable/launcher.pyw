# dev/portable/launcher.pyw -> <package>/launcher.pyw (dev/build_portable.py copies it; ClipForge.vbs runs it with pythonw)
#
# 30.10.2026: the portable package's launcher. Starts the browser app once (python\python.exe src\entrypoints\web_app.py,
# without a window) or reuses the one already running, then opens it in the browser with the access token - what
# dev/_web_launcher_impl.bat does for a git checkout. The package's Python is isolated from the user's PYTHONPATH,
# PYTHONHOME and user site-packages; the app and every script it runs inherit that environment.
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8878   # entrypoints/web/server_startup.DEFAULT_PORT
WAIT_SECONDS = 120
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200



sys.path.insert(0, os.path.join(ROOT, "src"))
from utils.shared import install_where  # noqa: E402 - בלי data_paths: עוד לא נקבע איפה הנתונים


def managed_data_dirs(root, environ, is_winget=None):
    """16.11.2026 (2.0): התקנת winget מחליפה את כל תיקיית ההתקנה בכל עדכון - data/ ו-workspace/ לידה היו נמחקים. שם הם עוברים
    ל-%LOCALAPPDATA%\\ClipForge. משתנה שכבר מוגדר (המשתמש, טסטים) גובר. Scoop שומר אותם בעצמו (persist), וה-zip הרגיל - לידו.
    17.11.2026: winget מזוהה גם לפי הרישום (install_where), לא רק לפי "\\winget\\packages\\" בנתיב - התקנה לתיקייה אחרת
    (winget install --location) זוהתה כ-zip רגיל, והנתונים נשארו בתוך התיקייה של הגרסה."""
    if not (install_where.is_winget if is_winget is None else is_winget)(root):
        return {}
    base = os.path.join(environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ClipForge")
    wanted = {"CLIPFORGE_DATA_DIR": os.path.join(base, "data"), "CLIPFORGE_WORKSPACE_DIR": os.path.join(base, "workspace")}
    return {key: value for key, value in wanted.items() if not environ.get(key)}


MANAGED_DIRS = managed_data_dirs(ROOT, os.environ)
os.environ.update(MANAGED_DIRS)   # לפני data_paths - הוא קורא את התיקייה בייבוא
from utils.shared import data_paths  # noqa: E402 - אחרי src ב-sys.path
from utils.shared import install_files  # noqa: E402


def adopt_managed_layout(managed, adopt=None):
    """17.11.2026: data_paths מדלג על המבנה לפי נושא כש-CLIPFORGE_DATA_DIR מוגדר (טסטים ושרת בדיקה בוחרים מבנה בעצמם). בהתקנת
    winget המשתנה מגיע מכאן ולא מהמשתמש, ולכן התקנה חדשה התחילה במבנה השטוח הישן. כשהלאנצ'ר בחר את התיקייה - הוא גם מסמן
    אותה כמבנה לפי נושא (רק כשהיא חדשה; תיקייה עם קבצים במבנה הישן לא משתנה). מחזיר True אם סומנה עכשיו."""
    folder = managed.get("CLIPFORGE_DATA_DIR")
    if not folder:
        return False
    try:
        os.makedirs(folder, exist_ok=True)
        return (adopt or data_paths.adopt_layout_if_new)(folder)
    except OSError:
        return False   # ממשיכים במבנה השטוח, כמו data_paths


adopt_managed_layout(MANAGED_DIRS)


def isolated_env(environ=None):
    """הסביבה של האפליקציה: בלי PYTHONPATH/PYTHONHOME של המשתמש ובלי site-packages של המשתמש."""
    env = {k: v for k, v in (os.environ if environ is None else environ).items()
           if k.upper() not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def port_open(port=PORT):
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def wait_for_server(token_path, before, timeout=WAIT_SECONDS, port=PORT):
    """עד שהשרת עונה בפורט וכתב טוקן חדש (web_app כותב טוקן חדש בכל עלייה). True אם הצליח."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port) and _mtime(token_path) not in (None, before):
            return True
        time.sleep(0.5)
    return False


def _message(text):
    ctypes.windll.user32.MessageBoxW(None, text, "ClipForge", 0x10)


def start_failed_text(language, log_path):
    """30.10.2026: ההודעה כשהשרת לא עלה - בשפת ההתקנה (ui_language.current), כמו תפריט המגש."""
    if language == "he":
        return f"ClipForge לא עלה תוך {WAIT_SECONDS} שניות.\nפרטים: {log_path}"
    return f"ClipForge did not start within {WAIT_SECONDS} seconds.\nDetails: {log_path}"


def package_version(root=ROOT):
    try:
        with open(os.path.join(root, "portable.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def running_app(port=PORT, timeout=3):
    """מי עונה בפורט: {"clipforge": bool, "version": str}. 17.11.2026: ב-2.0.0 ה-launcher פתח בדפדפן כל מה שענה בפורט -
    גם תוכנה אחרת, וגם ClipForge ישן שנשאר לרוץ אחרי עדכון (ואז הגרסה החדשה לא עלתה לעולם)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/manifest.json", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
        return {"clipforge": str(data.get("short_name") or "") == "ClipForge", "version": str(data.get("version") or "")}
    except Exception:
        return {"clipforge": False, "version": ""}


def already_running_text(language, running, wanted):
    """ההודעה כשבפורט רץ משהו שאינו הגרסה הזו, או None כשאפשר פשוט לפתוח אותו."""
    if running["clipforge"] and (not wanted or running["version"] == wanted):
        return None
    if running["clipforge"]:
        shown = running["version"] or ("קודמת" if language == "he" else "an earlier one")
        if language == "he":
            return f"גרסה אחרת של ClipForge ({shown}) עדיין רצה.\nסגור אותה מהאייקון במגש המערכת, והפעל שוב."
        return f"Another version of ClipForge ({shown}) is still running.\nClose it from the tray icon, then start again."
    if language == "he":
        return f"פורט {PORT} תפוס על ידי תוכנה אחרת, ולכן ClipForge לא יכול לעלות."
    return f"Port {PORT} is used by another program, so ClipForge cannot start."


def main():
    install_files.sync(ROOT, data_paths.DATA_DIR)   # קובצי החיבור (.env, יוטיוב) שורדים עדכון
    token_path = data_paths.path(data_paths.WEB_TOKEN)
    if port_open():
        from utils.shared import ui_language
        problem = already_running_text(ui_language.current(), running_app(), package_version())
        if problem:
            _message(problem)
            return 1
    if not port_open():
        log_dir = data_paths.path(data_paths.LOGS)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "portable_launcher.log")
        before = _mtime(token_path)
        with open(log_path, "a", encoding="utf-8") as log:
            subprocess.Popen([os.path.join(ROOT, "python", "python.exe"), os.path.join(ROOT, "src", "entrypoints", "web_app.py")],
                             cwd=ROOT, env=isolated_env(), stdout=log, stderr=subprocess.STDOUT,
                             creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)
        if not wait_for_server(token_path, before):
            from utils.shared import ui_language
            _message(start_failed_text(ui_language.current(), log_path))
            return 1
    try:
        with open(token_path, encoding="utf-8") as f:
            token = f.read().strip()
    except OSError:
        token = ""
    webbrowser.open(f"http://127.0.0.1:{PORT}/" + (f"?token={token}" if token else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
