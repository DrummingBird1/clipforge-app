# tests/infra/test_tls_cert.py
#
# בודק utils/shared/tls_cert.py - הנפקת תעודת TLS עצמית-חתומה עבור --lan ב-web_app.py
# (item 7/28: התעבורה, כולל הטוקן, עברה עד כה בטקסט גלוי ברשת המקומית).
import datetime
import os


from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import utils.shared.tls_cert as tls_cert


def _read_cert(cert_path):
    with open(cert_path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def _san_hosts(cert):
    san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    hosts = set(san_ext.get_values_for_type(x509.DNSName))
    hosts |= {str(ip) for ip in san_ext.get_values_for_type(x509.IPAddress)}
    return hosts


def _write_cert_with_sans(cert_path, key_path, hosts, not_valid_after=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    not_valid_after = not_valid_after or datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=825)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_valid_after - datetime.timedelta(days=30))
        .not_valid_after(not_valid_after)
        .add_extension(x509.SubjectAlternativeName(tls_cert._san_general_names(hosts)), critical=False)
    )
    cert = builder.sign(key, hashes.SHA256())
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))


def test_ensure_self_signed_cert_creates_files_when_missing(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")

    tls_cert.ensure_self_signed_cert(cert_path, key_path, extra_hosts=["192.168.1.50"])

    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    cert = _read_cert(cert_path)
    hosts = _san_hosts(cert)
    assert "localhost" in hosts
    assert "127.0.0.1" in hosts
    assert "192.168.1.50" in hosts


def test_ensure_self_signed_cert_does_not_regenerate_when_already_valid(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    tls_cert.ensure_self_signed_cert(cert_path, key_path, extra_hosts=["192.168.1.50"])
    original_cert_bytes = open(cert_path, "rb").read()

    tls_cert.ensure_self_signed_cert(cert_path, key_path, extra_hosts=["192.168.1.50"])

    assert open(cert_path, "rb").read() == original_cert_bytes


def test_ensure_self_signed_cert_regenerates_when_a_new_host_is_needed(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    tls_cert.ensure_self_signed_cert(cert_path, key_path, extra_hosts=["192.168.1.50"])
    original_cert_bytes = open(cert_path, "rb").read()

    # מחשב שהתחבר לרשת אחרת - IP חדש שהתעודה הקיימת לא מכסה
    tls_cert.ensure_self_signed_cert(cert_path, key_path, extra_hosts=["10.0.0.7"])

    new_bytes = open(cert_path, "rb").read()
    assert new_bytes != original_cert_bytes
    hosts = _san_hosts(_read_cert(cert_path))
    assert "10.0.0.7" in hosts


def test_ensure_self_signed_cert_regenerates_an_expired_cert(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    expired = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    _write_cert_with_sans(cert_path, key_path, {"localhost", "127.0.0.1", "192.168.1.50"}, not_valid_after=expired)

    tls_cert.ensure_self_signed_cert(cert_path, key_path, extra_hosts=["192.168.1.50"])

    cert = _read_cert(cert_path)
    assert cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc)


def test_ensure_self_signed_cert_produces_a_usable_rsa_key(tmp_path):
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")

    tls_cert.ensure_self_signed_cert(cert_path, key_path)

    with open(key_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    assert key.key_size == 2048
