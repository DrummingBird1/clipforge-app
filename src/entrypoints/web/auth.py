# entrypoints/web/auth.py
#
# 24.10.2026 (פיצול web_app.py, קבוצה 1): מי רשאי - הטוקן של המחשב, מכשירים מצומדים, loopback ובדיקת ה-Origin. עבר מ-web_app.py
# בלי שינוי התנהגות. web_app מייבא את השמות האלה בחזרה (web_app.<שם> נשאר), וה-middleware (_require_access_token) נשאר שם -
# הסדר שבו middlewares נרשמים קובע. יצירת הטוקן (_generate_token, ACCESS_TOKEN) נשארה שם: היא רצה כש-web_app נטען.
# כל שם שקיים גם ב-web_app נקרא דרך W. - טסטים מחליפים את web_app.<שם> (ACCESS_TOKEN, device_store, TRUSTED_HOSTS...), והקוד
# כאן צריך לראות את ההחלפה. משתנים שמשתנים (ACCESS_TOKEN אחרי רוטציה, TRUSTED_HOSTS) נשארים מוגדרים ב-web_app ונכתבים דרך W.
import ipaddress
import secrets

from entrypoints import web_app as W


def _same_token(supplied, expected):
    """השוואה בזמן קבוע (secrets.compare_digest) - לא `!=`."""
    if not supplied or not expected:
        return False
    return secrets.compare_digest(str(supplied).encode("utf-8"), str(expected).encode("utf-8"))


def _bearer_token(conn):
    scheme, _, value = (conn.headers.get("authorization") or "").partition(" ")
    return value.strip() if scheme.lower() == "bearer" else None


def _authenticate(conn):
    """("computer", None) / ("device", מזהה) / None - לבקשת HTTP ול-WebSocket (שניהם HTTPConnection).
    טוקן המחשב: ?token= קודם (ראו _require_access_token), עוגייה או Bearer. טוקן מכשיר: Bearer או עוגיית המכשיר -
    אף פעם לא ב-?token=, כדי שלא יישאר בכתובות ובלוגים."""
    bearer = W._bearer_token(conn)
    for supplied in (conn.query_params.get("token"), conn.cookies.get(W._AUTH_COOKIE_NAME), bearer):
        if W._same_token(supplied, W.ACCESS_TOKEN):
            return "computer", None
    ip = conn.client.host if conn.client else None
    for supplied in (bearer, conn.cookies.get(W.device_pairing.COOKIE_NAME)):
        device_id = W.device_store.verify(supplied, ip=ip)
        if device_id:
            return "device", device_id
    return None


def _is_loopback_client(conn):
    try:
        return ipaddress.ip_address(conn.client.host if conn.client else "").is_loopback
    except ValueError:
        return False


def _is_local_computer(conn):
    """המחשב עצמו: נכנס עם טוקן המחשב, והבקשה הגיעה מ-127.0.0.1 / ::1 (לא דרך Tailscale או הרשת)."""
    return getattr(conn.state, "auth_kind", None) == "computer" and W._is_loopback_client(conn)


def _authorize_websocket(websocket):
    """אותה בדיקה כמו _require_access_token, שלא חל על WebSocket. שומר את מזהה המכשיר - _watch_ws_disconnect סוגר
    את החיבור כשמבטלים אותו."""
    auth = W._authenticate(websocket)
    if auth is None:
        return False
    websocket.state.auth_kind, websocket.state.device_id = auth
    return True


# הגנה מפני CSRF נגד שירות מקומי: בלי בדיקת Origin, כל אתר זדוני שנפתח בטאב
# אחר של אותו דפדפן יכול לשלוח fetch(POST) ל-127.0.0.1:8878/api/run - הבקשה
# חוצה-המקור נשלחת ומבוצעת בפועל בצד השרת גם אם ה-JS של האתר הזדוני לא יכול
# *לקרוא* את התשובה (CORS חוסם רק קריאת תשובה, לא שליחת הבקשה) - זו קטגוריית
# פגיעות ידועה נגד שירותי localhost (אותה בעיה שיש לכלי dev-server רבים).
# נבדק רק אם Origin בכלל קיים בבקשה - קריאה ישירה בלי דפדפן (curl/סקריפט) לא
# שולחת Origin כלל, וזו לא הבעיה שההגנה הזו נועדה למנוע.
#
# משווים את המארח בפועל שאליו הבקשה הגיעה (Host header) ולא רשימה קבועה של
# 127.0.0.1/localhost - כדי שזה ימשיך לעבוד נכון גם במצב --lan (השרת נגיש
# מכתובת IP ברשת המקומית, לא רק loopback - ראו _get_lan_ip/__main__).
def _is_same_origin(request):
    origin = request.headers.get("origin")
    if not origin:
        return True
    try:
        origin_host = origin.split("://", 1)[1].split("/", 1)[0]
    except IndexError:
        return False
    if origin_host != request.headers.get("host", ""):
        return False
    return W.TRUSTED_HOSTS is None or W._host_name(origin_host) in W.TRUSTED_HOSTS


def _host_name(host_and_port):
    """'100.1.2.3:8878' -> '100.1.2.3', '[::1]:8878' -> '::1', 'Pc.Tail.ts.net' -> 'pc.tail.ts.net'."""
    host = host_and_port.strip().lower()
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def trust_tailscale_hosts(ip, dns_name=None):
    """מצב Tailscale: בדיקת ה-Origin מקבלת loopback, את כתובת ה-Tailscale ואת שם ה-MagicDNS שלה - ושום מארח אחר."""
    W.TRUSTED_HOSTS = set(W.LOOPBACK_HOSTS) | {ip.lower()} | ({dns_name.lower().rstrip(".")} if dns_name else set())
