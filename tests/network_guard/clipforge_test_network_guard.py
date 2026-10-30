# tests/network_guard/clipforge_test_network_guard.py
#
# 23.10.2026 (בקשת המשתמש): טסט לא יוצא לרשת - רק loopback. טסט דפדפן של הקטלוג יצא ל-api.worldbank.org דרך ה-service
# worker של הדף (page.route לא רואה בקשות של service worker), והפר את כלל 8. בלי שינוי בקוד האפליקציה:
# 1. פייתון בתהליך הטסט (tests/conftest.py מתקין): socket.getaddrinfo / gethostbyname(_ex), socket.connect(_ex) ו-sock_connect
#    של לולאת ה-asyncio נכשלים מיד לכל מה שאינו loopback - לפני ה-DNS - עם BlockedNetworkError. הוא תת-סוג של
#    ConnectionRefusedError, אז קוד שכבר מטפל בכשל רשת ממשיך כרגיל, וההודעה אומרת מי חסם ולמה.
# 2. תתי-תהליכי פייתון (שרת בתהליך נפרד, סקריפטים דרך worker, הורדות של השרת): ה-conftest שם את התיקייה הזו ב-PYTHONPATH,
#    ו-sitecustomize.py שלידה מתקין את אותה שמירה בעליית כל תהליך שיורש את הסביבה (כש-ENV_FLAG מוגדר).
# 3. Edge של Playwright (edge_browser ב-conftest) עולה עם proxy שהוא BlockingProxy למטה - שרת קטן על 127.0.0.1 שרושם כל
#    בקשה וסוגר אותה בלי תשובה. כך נחסמות גם בקשות של service worker; Chromium שולח loopback תמיד ישירות, לא דרך ה-proxy.
# opt-out: @pytest.mark.allow_network על טסט בודד (מסיר את 1 ואת 2 לזמן הטסט; הדפדפן נשאר מאחורי ה-proxy).
# הקובץ נטען בשם אחד בכל תהליך (clipforge_test_network_guard) - גם מה-conftest וגם מ-sitecustomize - כך שיש מצב אחד.
import asyncio.proactor_events
import errno
import ipaddress
import socket
import socketserver
import threading

ENV_FLAG = "CLIPFORGE_TEST_NETWORK_GUARD"
_LOCAL_NAMES = {"", "localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
# מה שהוחלף, כדי שאפשר יהיה להחזיר (opt-out); הפונקציות העוטפות קוראות את המקור מכאן בזמן הקריאה
_ORIGINALS: dict = {}


class BlockedNetworkError(ConnectionRefusedError):
    """ניסיון רשת מטסט לכתובת שאינה loopback."""


def is_local_host(host) -> bool:
    if host is None:
        return True
    if isinstance(host, (bytes, bytearray)):
        host = bytes(host).decode("ascii", "replace")
    name = str(host).strip().strip("[]").lower().rstrip(".")
    if name in _LOCAL_NAMES or name.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(name.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def _blocked(target) -> BlockedNetworkError:
    return BlockedNetworkError(
        errno.ECONNREFUSED,
        f"רשת חסומה בטסטים: {target} - רק localhost (tests/network_guard). טסט שבאמת צריך רשת: @pytest.mark.allow_network")


def _check_address(family, address) -> None:
    if family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and address and not is_local_host(address[0]):
        raise _blocked(f"{address[0]}:{address[1] if len(address) > 1 else ''}")


def _getaddrinfo(host, port, *args, **kwargs):
    if not is_local_host(host):
        raise _blocked(f"{host}:{port}")   # לפני ה-DNS
    return _ORIGINALS["getaddrinfo"](host, port, *args, **kwargs)


def _gethostbyname(host):
    if not is_local_host(host):
        raise _blocked(host)
    return _ORIGINALS["gethostbyname"](host)


def _gethostbyname_ex(host):
    if not is_local_host(host):
        raise _blocked(host)
    return _ORIGINALS["gethostbyname_ex"](host)


def _connect(self, address):
    _check_address(self.family, address)
    return _ORIGINALS["connect"](self, address)


def _connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and address and not is_local_host(address[0]):
        return errno.ECONNREFUSED
    return _ORIGINALS["connect_ex"](self, address)


async def _proactor_sock_connect(self, sock, address):
    # ב-Windows הלולאה מתחברת דרך ConnectEx ולא דרך sock.connect - כתובת מספרית לא עוברת ב-getaddrinfo
    _check_address(sock.family, address)
    return await _ORIGINALS["proactor_sock_connect"](self, sock, address)


_TARGETS = [
    (socket, "getaddrinfo", _getaddrinfo),
    (socket, "gethostbyname", _gethostbyname),
    (socket, "gethostbyname_ex", _gethostbyname_ex),
    (socket.socket, "connect", _connect),
    (socket.socket, "connect_ex", _connect_ex),
    (asyncio.proactor_events.BaseProactorEventLoop, "sock_connect", _proactor_sock_connect),
]
_KEYS = ["getaddrinfo", "gethostbyname", "gethostbyname_ex", "connect", "connect_ex", "proactor_sock_connect"]


def installed() -> bool:
    return bool(_ORIGINALS)


def install() -> None:
    if _ORIGINALS:
        return
    for key, (owner, attr, replacement) in zip(_KEYS, _TARGETS):
        _ORIGINALS[key] = getattr(owner, attr)
        setattr(owner, attr, replacement)


def uninstall() -> None:
    for key, (owner, attr, _replacement) in zip(_KEYS, _TARGETS):
        if key in _ORIGINALS:
            setattr(owner, attr, _ORIGINALS[key])
    _ORIGINALS.clear()


class _ProxyHandler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            line = self.rfile.readline(4096).decode("latin-1").strip()
        except OSError:
            return
        if line:
            with self.server.lock:
                self.server.requests.append(line)
        # בלי תשובה: אצל הלקוח זה כשל רשת (ERR_EMPTY_RESPONSE / fetch נדחה), לא תשובת HTTP שאפשר לטעות בה


class BlockingProxy(socketserver.ThreadingTCPServer):
    """proxy שלא מעביר כלום: רושם את שורת הבקשה (GET http://host/... או CONNECT host:443) וסוגר."""
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _ProxyHandler)
        self.lock = threading.Lock()
        self.requests: list = []
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    def seen(self, text: str) -> list:
        with self.lock:
            return [line for line in self.requests if text in line]
