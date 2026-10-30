# tests/infra/test_network_guard.py
#
# 23.10.2026: רשת חסומה בטסטים (tests/network_guard) - בתהליך הטסט ובתתי-תהליכי פייתון. הכתובות כאן לא עונות בכל מקרה:
# example.invalid שם שמור שלא קיים, ו-192.0.2.1 כתובת לתיעוד (RFC 5737). השמירה חוסמת לפני ה-DNS ולפני ה-SYN; בלעדיה כל
# טסט כאן נכשל - מקבלים gaierror / timeout במקום BlockedNetworkError. טסט הדפדפן (service worker) - test_network_guard_browser.py.
import asyncio
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

import clipforge_test_network_guard as network_guard   # tests/conftest.py שם את tests/network_guard ב-sys.path
from tests import TESTS_DIR

UNANSWERED_IP = "192.0.2.1"


def test_python_in_the_test_process_is_blocked_before_dns(monkeypatch):
    dns = []
    monkeypatch.setitem(network_guard._ORIGINALS, "getaddrinfo", lambda *a, **k: dns.append(a))
    with pytest.raises(network_guard.BlockedNetworkError, match="example.invalid"):
        socket.create_connection(("example.invalid", 80), timeout=3)
    with pytest.raises(urllib.error.URLError) as raised:
        urllib.request.urlopen("http://example.invalid/", timeout=3)
    assert isinstance(raised.value.reason, network_guard.BlockedNetworkError)
    with pytest.raises(network_guard.BlockedNetworkError):
        socket.gethostbyname("example.invalid")
    assert dns == []   # אף שאילתת DNS לא יצאה


def test_a_numeric_address_is_blocked_before_connecting():
    with socket.socket() as sock:
        sock.settimeout(3)
        with pytest.raises(network_guard.BlockedNetworkError, match=UNANSWERED_IP):
            sock.connect((UNANSWERED_IP, 80))
        assert sock.connect_ex((UNANSWERED_IP, 80)) != 0


def test_asyncio_connections_are_blocked_too():
    # ב-Windows הלולאה מתחברת ב-ConnectEx, לא ב-sock.connect, וכתובת מספרית לא עוברת ב-getaddrinfo
    async def connect():
        await asyncio.wait_for(asyncio.open_connection(UNANSWERED_IP, 80), 3)

    with pytest.raises(network_guard.BlockedNetworkError):
        asyncio.run(connect())


def test_loopback_still_works():
    with socket.create_server(("127.0.0.1", 0)) as server:
        port = server.getsockname()[1]
        socket.create_connection(("127.0.0.1", port), timeout=3).close()
        socket.create_connection(("localhost", port), timeout=3).close()


_CHILD = r"""
import socket, urllib.request
out = []
try:
    urllib.request.urlopen("http://example.invalid/", timeout=3)
    out.append("urllib:reached")
except Exception as e:
    out.append("urllib:" + type(getattr(e, "reason", e)).__name__)
try:
    with socket.socket() as sock:
        sock.settimeout(3)
        sock.connect(("192.0.2.1", 80))
    out.append("socket:reached")
except Exception as e:
    out.append("socket:" + type(e).__name__)
print(";".join(out))
"""


def test_a_child_python_process_is_blocked_too():
    # שרת בתהליך נפרד, סקריפטים דרך worker, הורדות - כולם יורשים את PYTHONPATH ואת הדגל, ו-sitecustomize מתקין את השמירה
    result = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True, timeout=120)
    assert result.stdout.strip() == "urllib:BlockedNetworkError;socket:BlockedNetworkError", result.stderr


@pytest.mark.allow_network
def test_allow_network_lifts_the_guard_for_this_test_only():
    # טסט ה-opt-out עצמו - בלי שום גישה לרשת
    assert not network_guard.installed()
    assert network_guard.ENV_FLAG not in os.environ


def test_the_guard_is_back_after_an_opt_out_test():
    assert network_guard.installed() and os.environ.get(network_guard.ENV_FLAG) == "1"


def test_no_test_opts_out_of_the_guard():
    # opt-out הוא החלטה: טסט שבאמת צריך רשת נכנס לכאן עם הסיבה (היום אין אף אחד)
    allowed = {"infra/test_network_guard.py"}
    users = []
    for dirpath, _dirnames, filenames in os.walk(TESTS_DIR):
        for name in filenames:
            if name.startswith("test_") and name.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, name), TESTS_DIR).replace("\\", "/")
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    if "mark.allow_network" in f.read() and rel not in allowed:
                        users.append(rel)
    assert users == [], f"טסטים שמבטלים את חסימת הרשת: {users}"
