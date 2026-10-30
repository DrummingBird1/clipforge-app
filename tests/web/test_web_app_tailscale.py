# tests/web/test_web_app_tailscale.py
#
# 19.10.2026: גישה מהטלפון דרך Tailscale. השרת מאזין גם על כתובת ה-IPv4 של ממשק Tailscale (100.64.0.0/10) - אף פעם לא
# 0.0.0.0 - ובדיקת ה-Origin מקבלת רק loopback, את הכתובת הזו ואת שם ה-MagicDNS שלה. רשימת ממשקים מזויפת, בלי רשת אמיתית.
import json
import socket
import subprocess

import pytest
from fastapi.testclient import TestClient

from entrypoints import web_app
from entrypoints.web_app import app
from utils.shared import tailscale

client = TestClient(app)
client.cookies.set("web_app_token", web_app.ACCESS_TOKEN)
web_app.limiter.enabled = False

FAKE_INTERFACES = {
    "‏‏Ethernet": ["10.0.0.29"],
    "vEthernet (WSL (Hyper-V firewall))": ["172.20.128.1"],
    "Tailscale": ["100.101.102.103"],
    "Loopback Pseudo-Interface 1": ["127.0.0.1"],
}


# ---------- זיהוי הממשק ובחירת הכתובות ----------
def test_finds_the_tailscale_ipv4_and_ignores_other_interfaces():
    assert tailscale.find_tailscale_ipv4(FAKE_INTERFACES) == ("Tailscale", "100.101.102.103")
    assert tailscale.find_tailscale_ipv4({"Ethernet": ["10.0.0.29", "100.200.0.1"]}) is None   # 100.200 מחוץ ל-100.64.0.0/10
    assert tailscale.find_tailscale_ipv4({"Other": ["100.100.1.1"], "Tailscale": ["100.70.0.5"]}) == ("Tailscale", "100.70.0.5")
    assert tailscale.find_tailscale_ipv4({"Ethernet": ["not-an-ip"]}) is None


def test_bind_selection_never_includes_0_0_0_0_in_tailscale_mode():
    hosts, ip, note = tailscale.bind_hosts(True, interfaces=FAKE_INTERFACES)
    assert hosts == ["127.0.0.1", "100.101.102.103"] and ip == "100.101.102.103" and note == ""
    assert "0.0.0.0" not in hosts and "10.0.0.29" not in hosts


def test_without_a_tailscale_interface_it_stays_on_loopback_with_a_message():
    hosts, ip, note = tailscale.bind_hosts(True, interfaces={"Ethernet": ["10.0.0.29"]})
    assert hosts == ["127.0.0.1"] and ip is None and "Tailscale" in note


def test_off_is_loopback_and_lan_is_unchanged():
    assert tailscale.bind_hosts(False, interfaces=FAKE_INTERFACES) == (["127.0.0.1"], None, "")
    assert tailscale.bind_hosts(True, lan=True, interfaces=FAKE_INTERFACES) == (["0.0.0.0"], None, "")   # --lan: TLS כמו קודם


def test_magicdns_name_comes_from_tailscale_status_for_the_same_ip(monkeypatch):
    monkeypatch.setattr(tailscale.shutil, "which", lambda name: "tailscale")
    status = {"Self": {"DNSName": "my-pc.tail1234ab.ts.net.", "TailscaleIPs": ["100.101.102.103", "fd7a::1"]}}
    fake = lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=json.dumps(status), stderr="")   # noqa: E731
    assert tailscale.magicdns_name("100.101.102.103", run=fake) == "my-pc.tail1234ab.ts.net"
    assert tailscale.magicdns_name("100.99.0.1", run=fake) is None


def test_the_setting_file_round_trips(tmp_path):
    path = str(tmp_path / "remote_access.json")
    assert tailscale.load_enabled(path) is False
    tailscale.save_enabled(True, path)
    assert tailscale.load_enabled(path) is True


# ---------- הקשירה: כל הכתובות או כלום ----------
def test_binding_all_hosts_is_all_or_nothing():
    holder = socket.socket()
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    holder.bind(("127.0.0.2", 0))
    port = holder.getsockname()[1]
    try:
        with pytest.raises(OSError, match="127.0.0.2"):
            web_app._bind_server_sockets(["127.0.0.1", "127.0.0.2"], port)
        free = web_app._bind_server_socket("127.0.0.1", port)   # הראשון שוחרר אחרי הכישלון
        free.close()
    finally:
        holder.close()


# ---------- Origin ----------
@pytest.fixture
def tailscale_mode(monkeypatch):
    monkeypatch.setattr(web_app, "TRUSTED_HOSTS", None)
    web_app.trust_tailscale_hosts("100.101.102.103", "My-PC.tail1234ab.ts.net.")
    yield


def _post(host, origin):
    return client.post("/api/remote_access", json={"tailscale": False}, headers={"host": host, "origin": origin})


def test_origin_accepts_the_tailscale_address_and_its_magicdns_name(tailscale_mode):
    assert _post("100.101.102.103:8878", "http://100.101.102.103:8878").status_code == 200
    assert _post("my-pc.tail1234ab.ts.net:8878", "http://my-pc.tail1234ab.ts.net:8878").status_code == 200
    assert _post("127.0.0.1:8878", "http://127.0.0.1:8878").status_code == 200


def test_origin_rejects_any_other_host_even_when_it_matches_the_host_header(tailscale_mode):
    # DNS rebinding: שם זר שמצביע על כתובת המחשב - Origin ו-Host זהים, ובכל זאת נדחה
    assert _post("evil.example:8878", "http://evil.example:8878").status_code == 403
    assert _post("10.0.0.29:8878", "http://10.0.0.29:8878").status_code == 403
    assert _post("100.101.102.103:8878", "http://evil.example").status_code == 403


def test_without_tailscale_mode_the_origin_check_is_as_before(monkeypatch):
    monkeypatch.setattr(web_app, "TRUSTED_HOSTS", None)
    assert _post("10.0.0.29:8878", "http://10.0.0.29:8878").status_code == 200     # --lan: Origin == Host, כמו קודם
    assert _post("127.0.0.1:8878", "http://evil.example").status_code == 403


def test_the_api_shows_the_phone_link_with_the_token_only_when_active(monkeypatch):
    monkeypatch.setattr(web_app, "TAILSCALE_BASE_URL", None)
    assert client.get("/api/remote_access").json()["token_url"] is None
    monkeypatch.setattr(web_app, "TAILSCALE_BASE_URL", "http://my-pc.tail1234ab.ts.net:8878")
    data = client.get("/api/remote_access").json()
    assert data["token_url"] == f"http://my-pc.tail1234ab.ts.net:8878/?token={web_app.ACCESS_TOKEN}"
