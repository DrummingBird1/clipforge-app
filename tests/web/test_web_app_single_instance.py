# tests/web/test_web_app_single_instance.py
#
# 19.10.2026: הפעלה שנייה של web_app.py (לחיצה כפולה על ה-launcher כשהשרת כבר רץ) כתבה טוקן חדש ל-data/web_app_token.txt
# לפני שבדקה את הפורט, נכשלה בקשירה - והשרת שרץ נשאר עם הטוקן הישן: הדפדפן וקישור ה-launcher קיבלו 401. עכשיו הפורט
# נתפס קודם: פורט תפוס = יציאה עם PORT_IN_USE_EXIT_CODE, וקובץ הטוקן לא נוגע. פורט אקראי ו-data זמני - לא 8878 ולא data/ האמיתי.
import os
import socket
import subprocess
import sys

import pytest

from entrypoints import web_app
from tests import PROJECT_ROOT
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

WEB_APP = os.path.join(PROJECT_ROOT, "src", "entrypoints", "web_app.py")


def _hold_port():
    """פורט פנוי אקראי שתהליך הטסט מחזיק (מאזין), כמו שרת שכבר רץ."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock


def test_a_second_launch_on_a_busy_port_leaves_the_token_file_untouched(tmp_path):
    data, workspace = tmp_path / "data", tmp_path / "workspace"
    data.mkdir()
    token_file = data / "web_app_token.txt"
    token_file.write_bytes(b"token-of-the-running-server")
    before = token_file.stat().st_mtime_ns
    held = _hold_port()
    try:
        port = held.getsockname()[1]
        env = dict(os.environ, CLIPFORGE_DATA_DIR=str(data), CLIPFORGE_WORKSPACE_DIR=str(workspace), PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, WEB_APP, "--port", str(port)], cwd=PROJECT_ROOT, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=NO_WINDOW_FLAGS)
    finally:
        held.close()
    assert token_file.read_bytes() == b"token-of-the-running-server", result.stdout[-2000:] + result.stderr[-2000:]
    assert token_file.stat().st_mtime_ns == before
    assert result.returncode == 3 == web_app.PORT_IN_USE_EXIT_CODE, result.stdout[-2000:] + result.stderr[-2000:]
    assert str(port) in result.stdout


def test_bind_takes_the_port_exclusively():
    first = web_app._bind_server_socket("127.0.0.1", 0)
    try:
        port = first.getsockname()[1]
        with pytest.raises(OSError):
            web_app._bind_server_socket("127.0.0.1", port).close()
    finally:
        first.close()
