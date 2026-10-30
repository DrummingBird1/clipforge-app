# utils/shared/tls_cert.py
#
# מנפיק תעודת TLS עצמית-חתומה (self-signed) לשימוש מקומי בלבד - קיים כדי
# ש-entrypoints/web_app.py יוכל להריץ במצב --lan תחת HTTPS במקום HTTP רגיל
# (הטוקן והתעבורה כולה עברו עד כה בטקסט גלוי ברשת המקומית - כל מי שמריח
# תעבורה ברשת יכול היה לגנוב את הטוקן). לא CA אמיתי - הדפדפן יציג אזהרת אמון
# פעם ראשונה ("החיבור אינו פרטי"), בדיוק כמו כל dev-server מקומי אחר
# (Jupyter, Vite --https וכו') - "אישור חד-פעמי" סביר בהרבה מהעדר הצפנה בכלל.
import datetime
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_VALIDITY_DAYS = 825  # התקרה שדפדפנים מודרניים (Chrome/Safari) עוד מקבלים לתעודות עצמיות-חתומות


def _required_sans(extra_hosts):
    return {"localhost", "127.0.0.1", *extra_hosts}


def _san_general_names(hosts):
    names = []
    for host in hosts:
        try:
            names.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            names.append(x509.DNSName(host))
    return names


def _existing_cert_covers(cert_path, required_hosts):
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
    except Exception:
        return False

    if cert.not_valid_after_utc <= datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1):
        return False

    try:
        san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False

    covered = set(san_ext.get_values_for_type(x509.DNSName))
    covered |= {str(ip) for ip in san_ext.get_values_for_type(x509.IPAddress)}
    return required_hosts.issubset(covered)


def ensure_self_signed_cert(cert_path, key_path, extra_hosts=()):
    """מוודא שתעודת TLS עצמית-חתומה תקפה קיימת ב-cert_path/key_path ומכסה
    את כל ה-hosts הנדרשים (localhost, 127.0.0.1, ועוד hosts שסופקו - למשל
    כתובת ה-IP ברשת המקומית, שיכולה להשתנות בין הפעלות עם --lan אם המחשב
    מתחבר לרשת אחרת). אם כן - לא עושה כלום (נמנע מ"לשרוף" אמון קיים בדפדפן
    בלי צורך). אם לא (חסרה, פגה, או לא מכסה host חדש) - מנפיקה תעודה חדשה.
    לא מחזירה כלום; קוראים בודקים את קיום הקבצים."""
    required_hosts = _required_sans(extra_hosts)
    if os.path.exists(cert_path) and os.path.exists(key_path) and _existing_cert_covers(cert_path, required_hosts):
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ClipForge Local")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=_VALIDITY_DAYS))
        .add_extension(x509.SubjectAlternativeName(_san_general_names(required_hosts)), critical=False)
        .sign(key, hashes.SHA256())
    )

    os.makedirs(os.path.dirname(cert_path) or ".", exist_ok=True)
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
