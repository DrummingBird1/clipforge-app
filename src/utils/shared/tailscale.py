# utils/shared/tailscale.py
#
# גישה מרחוק דרך Tailscale (19.10.2026): ממשק הדפדפן מאזין גם על כתובת ה-IPv4 של ממשק Tailscale (100.64.0.0/10) -
# לא על 0.0.0.0 - כדי שאפשר יהיה לפתוח אותו מהטלפון מכל מקום בלי לחשוף אותו לרשת המקומית. Tailscale כבר מצפין
# (WireGuard), אז HTTP רגיל מספיק שם; הטוקן עדיין נדרש. הכתובת מזוהה בהפעלה (לא קבועה בקוד), והשם ב-MagicDNS
# (pc.tailnet.ts.net) נקרא מ-`tailscale status --json` כשהכלי מותקן.
#
# ההגדרה: data/remote_access.json {"tailscale": true} (לא ב-config.json - ה-GUI השולחני שומר רק את המפתחות שהוא מכיר),
# או הדגל --tailscale של web_app.py.
import ipaddress
import json
import os
import shutil
import socket
import subprocess
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from utils.shared.atomic_write import atomic_write_json
from utils.shared.subprocess_flags import NO_WINDOW_FLAGS
from utils.shared import data_paths

TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")   # טווח ה-CGNAT ש-Tailscale נותן ממנו כתובות
SETTINGS_PATH = data_paths.path(data_paths.REMOTE_ACCESS)
_DEFAULT_CLI = r"C:\Program Files\Tailscale\tailscale.exe"


def _interfaces() -> Dict[str, List[str]]:
    import psutil
    return {name: [a.address for a in addrs if a.family == socket.AF_INET] for name, addrs in psutil.net_if_addrs().items()}


def find_tailscale_ipv4(interfaces: Optional[Dict[str, Iterable[str]]] = None) -> Optional[Tuple[str, str]]:
    """(שם הממשק, כתובת) של ממשק Tailscale, או None. כתובת בטווח 100.64.0.0/10 בלבד; ממשק ששמו "Tailscale" קודם."""
    current: Dict[str, Iterable[str]] = dict(_interfaces()) if interfaces is None else interfaces
    found = []
    for name, addresses in current.items():
        for address in addresses:
            try:
                if ipaddress.ip_address(address) in TAILSCALE_NET:
                    found.append((name, address))
            except ValueError:
                continue
    found.sort(key=lambda item: "tailscale" not in item[0].lower())
    return found[0] if found else None


def magicdns_name(ip: str, run: Callable = subprocess.run) -> Optional[str]:
    """השם ב-MagicDNS (בלי הנקודה בסוף) של המחשב הזה, אם `tailscale status --json` מחזיר אותו לאותה כתובת."""
    cli = shutil.which("tailscale") or (_DEFAULT_CLI if os.path.isfile(_DEFAULT_CLI) else None)
    if not cli:
        return None
    try:
        result = run([cli, "status", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                     timeout=5, creationflags=NO_WINDOW_FLAGS)
        me = json.loads(result.stdout or "{}").get("Self") or {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    name = str(me.get("DNSName") or "").rstrip(".")
    return name if name and ip in (me.get("TailscaleIPs") or []) else None


def load_enabled(path: str = "") -> bool:
    try:
        with open(path or SETTINGS_PATH, encoding="utf-8") as f:
            return bool(json.load(f).get("tailscale"))
    except (OSError, ValueError, AttributeError):
        return False


def save_enabled(enabled: bool, path: str = "") -> None:
    path = path or SETTINGS_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, {"tailscale": bool(enabled)}, ensure_ascii=False, indent=2)


def bind_hosts(want_tailscale: bool, lan: bool = False, interfaces: Optional[Dict[str, Iterable[str]]] = None):
    """הכתובות לקשירה ומה להדפיס: (hosts, tailscale_ip או None, הודעה או "").
    --lan: 0.0.0.0 כמו קודם (TLS). Tailscale: 127.0.0.1 ועוד כתובת Tailscale בלבד - אף פעם לא 0.0.0.0.
    בלי ממשק Tailscale: loopback בלבד, עם הודעה."""
    if lan:
        return ["0.0.0.0"], None, ""
    if not want_tailscale:
        return ["127.0.0.1"], None, ""
    found = find_tailscale_ipv4(interfaces)
    if not found:
        return ["127.0.0.1"], None, ("⚠️  גישה דרך Tailscale מופעלת, אבל לא נמצא ממשק Tailscale עם כתובת 100.x - האם Tailscale מחובר? "
                                     "השרת עולה רק על המחשב הזה (127.0.0.1).")
    return ["127.0.0.1", found[1]], found[1], ""
