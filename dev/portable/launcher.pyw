# dev/portable/launcher.pyw -> <package>/launcher.pyw (dev/build_portable.py copies it; ClipForge.vbs runs it with pythonw)
#
# 30.10.2026: the portable package's launcher. Starts the browser app once (python\python.exe src\entrypoints\web_app.py,
# without a window) or reuses the one already running, then opens it in the browser with the access token - what
# dev/_web_launcher_impl.bat does for a git checkout. The package's Python is isolated from the user's PYTHONPATH,
# PYTHONHOME and user site-packages; the app and every script it runs inherit that environment.
import ctypes
import os
import socket
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 8878   # entrypoints/web/server_startup.DEFAULT_PORT
WAIT_SECONDS = 120
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

sys.path.insert(0, os.path.join(ROOT, "src"))
from utils.shared import data_paths  # noqa: E402 - אחרי src ב-sys.path


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


def main():
    token_path = data_paths.path(data_paths.WEB_TOKEN)
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
