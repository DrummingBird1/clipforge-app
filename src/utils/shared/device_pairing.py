# utils/shared/device_pairing.py
#
# צימוד מכשיר (22.10.2026, באישור המשתמש): טוקן הגישה של המחשב (web_app.ACCESS_TOKEN) נוצר מחדש בכל הפעלה - בכוונה,
# כדי שקישור שדלף ייפסל - ולכן טלפון דרך Tailscale או ZimaOS איבדו גישה אחרי כל הפעלה מחדש. כאן לכל מכשיר מצומד
# טוקן משלו שנשאר תקף בין הפעלות, עד שמבטלים אותו מהמסך (או 90 יום בלי שימוש).
#
# - הצימוד: קוד חד-פעמי, תקף 5 דקות, נשמר רק בזיכרון. המכשיר מממש אותו פעם אחת ומקבל טוקן אקראי.
# - data/paired_devices.json מחזיק רק SHA-256 של כל טוקן - עותק של data/ (גיבוי, NAS) לא נותן גישה.
# - "נראה לאחרונה" מתעדכן בזיכרון בכל בקשה, ונכתב לקובץ לכל היותר פעם ב-10 דקות לכל מכשיר.
# - קובץ פגום = אין מכשירים (נכשל סגור); הוא נדרס רק בשינוי הבא.
# מי מורשה לצמד ולבטל (רק המחשב עצמו) - web_app.py; כאן רק המאגר.
import hashlib
import json
import secrets
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from utils.shared.atomic_write import atomic_write_json
from utils.shared import data_paths

DEVICES_PATH = data_paths.path(data_paths.PAIRED_DEVICES)
COOKIE_NAME = "clipforge_device"
COOKIE_MAX_AGE_SECONDS = 400 * 24 * 3600   # התקרה שדפדפנים מקבלים לעוגייה
CODE_TTL_SECONDS = 5 * 60
EXPIRE_UNUSED_DAYS = 90
SEEN_WRITE_INTERVAL_SECONDS = 10 * 60
MAX_DEVICES = 20
MAX_PENDING_CODES = 10
NAME_MAX_LENGTH = 40
# 30.10.2026: שם ברירת המחדל בשפת ההתקנה (utils/shared/ui_language.py)
DEFAULT_NAMES = {"he": "מכשיר", "en": "Device"}
KINDS = ("browser", "script")


class PairingError(ValueError):
    """הודעה למשתמש (עברית) - קוד שפג / כבר שומש / יותר מדי מכשירים."""


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clean_name(name: object) -> str:
    text = " ".join(str(name or "").split())[:NAME_MAX_LENGTH].strip()
    return text or default_name()


def default_name() -> str:
    from utils.shared import ui_language
    return DEFAULT_NAMES[ui_language.current()]


class DeviceStore:
    def __init__(self, path: str = "", clock: Callable[[], float] = time.time):
        self.path = path or DEVICES_PATH
        self.clock = clock
        self._lock = threading.Lock()
        self._codes: Dict[str, dict] = {}       # קוד -> {"name", "expires_at", "device_id" אחרי מימוש}
        self._data: Optional[dict] = None       # נטען בפעם הראשונה שצריך
        self._seen_written: Dict[str, float] = {}

    # ---------- קובץ ----------
    def _load(self) -> dict:
        if self._data is None:
            try:
                with open(self.path, encoding="utf-8") as f:
                    raw = json.load(f)
                devices = [d for d in raw.get("devices", []) if isinstance(d, dict) and d.get("id") and d.get("token_sha256")]
                self._data = {"expire_unused": bool(raw.get("expire_unused", True)), "devices": devices}
            except (OSError, ValueError, AttributeError):
                self._data = {"expire_unused": True, "devices": []}
        return self._data

    def _save(self) -> None:
        atomic_write_json(self.path, self._load(), ensure_ascii=False, indent=2)

    def _expired(self, device: dict, now: float) -> bool:
        last = device.get("last_seen") or device.get("created_at") or 0
        return bool(self._load()["expire_unused"]) and now - float(last) > EXPIRE_UNUSED_DAYS * 24 * 3600

    def _prune(self, now: float) -> None:
        data = self._load()
        alive = [d for d in data["devices"] if not self._expired(d, now)]
        if len(alive) != len(data["devices"]):
            data["devices"] = alive
            self._save()

    @staticmethod
    def _public(device: dict) -> dict:
        return {key: device.get(key) for key in ("id", "name", "kind", "created_at", "last_seen", "last_ip")}

    # ---------- קודי צימוד ----------
    def _live_codes(self, now: float) -> Dict[str, dict]:
        self._codes = {code: entry for code, entry in self._codes.items() if entry["expires_at"] > now}
        return self._codes

    def create_code(self, name: object) -> dict:
        with self._lock:
            now = self.clock()
            self._prune(now)
            if len(self._load()["devices"]) >= MAX_DEVICES:
                raise PairingError(f"כבר יש {MAX_DEVICES} מכשירים מצומדים - בטל אחד לפני שמצמדים עוד.")
            codes = self._live_codes(now)
            pending = [code for code, entry in codes.items() if "device_id" not in entry]   # סדר היצירה
            for oldest in pending[: max(0, len(pending) - MAX_PENDING_CODES + 1)]:
                del codes[oldest]
            code = secrets.token_urlsafe(16)
            codes[code] = {"name": clean_name(name), "expires_at": now + CODE_TTL_SECONDS}
            return {"code": code, "name": codes[code]["name"], "expires_at": codes[code]["expires_at"]}

    def peek_code(self, code: str) -> Optional[str]:
        """שם המכשיר אם הקוד עדיין ממתין - בלי לממש אותו (דף הצימוד מציג אותו לפני הלחיצה)."""
        with self._lock:
            entry = self._live_codes(self.clock()).get(str(code or ""))
            return entry["name"] if entry and "device_id" not in entry else None

    def code_state(self, code: str) -> Tuple[str, Optional[dict]]:
        """("pending" | "paired" | "expired", המכשיר שנוצר) - בשביל המסך במחשב שמחכה לטלפון."""
        with self._lock:
            entry = self._live_codes(self.clock()).get(str(code or ""))
            if not entry:
                return "expired", None
            if "device_id" not in entry:
                return "pending", None
            device = next((d for d in self._load()["devices"] if d["id"] == entry["device_id"]), None)
            return "paired", self._public(device) if device else None

    def redeem(self, code: str, kind: str = "browser", ip: Optional[str] = None) -> Tuple[str, dict]:
        """מממש קוד פעם אחת: (הטוקן הגלוי - חוזר רק כאן, המכשיר)."""
        with self._lock:
            now = self.clock()
            entry = self._live_codes(now).get(str(code or ""))
            if not entry or "device_id" in entry:
                raise PairingError("קוד הצימוד פג או כבר שומש - צור קוד חדש במחשב.")
            self._prune(now)
            data = self._load()
            if len(data["devices"]) >= MAX_DEVICES:
                raise PairingError(f"כבר יש {MAX_DEVICES} מכשירים מצומדים - בטל אחד לפני שמצמדים עוד.")
            token = secrets.token_urlsafe(32)
            device = {"id": secrets.token_hex(6), "name": entry["name"], "kind": kind if kind in KINDS else "browser",
                      "token_sha256": token_hash(token), "created_at": now, "last_seen": now, "last_ip": ip}
            data["devices"].append(device)
            self._save()
            self._seen_written[device["id"]] = now
            entry["device_id"] = device["id"]
            return token, self._public(device)

    # ---------- בדיקה בכל בקשה ----------
    def verify(self, token: Optional[str], ip: Optional[str] = None) -> Optional[str]:
        """מזהה המכשיר אם הטוקן שייך למכשיר פעיל, אחרת None."""
        if not token:
            return None
        digest = token_hash(token)
        with self._lock:
            now = self.clock()
            device = next((d for d in self._load()["devices"] if secrets.compare_digest(d["token_sha256"], digest)), None)
            if device is None:
                return None
            if self._expired(device, now):
                self._prune(now)
                return None
            device["last_seen"] = now
            if ip:
                device["last_ip"] = ip
            if now - self._seen_written.get(device["id"], 0.0) >= SEEN_WRITE_INTERVAL_SECONDS:
                self._seen_written[device["id"]] = now
                try:
                    self._save()
                except OSError:
                    pass   # "נראה לאחרונה" לא שווה כישלון של הבקשה עצמה
            return str(device["id"])

    def is_active(self, device_id: Optional[str]) -> bool:
        with self._lock:
            now = self.clock()
            return any(d["id"] == device_id and not self._expired(d, now) for d in self._load()["devices"])

    # ---------- ניהול (מהמחשב בלבד - נאכף ב-web_app.py) ----------
    def list_devices(self) -> List[dict]:
        with self._lock:
            self._prune(self.clock())
            return [self._public(d) for d in sorted(self._load()["devices"], key=lambda d: d.get("created_at") or 0)]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            data = self._load()
            remaining = [d for d in data["devices"] if d["id"] != device_id]
            if len(remaining) == len(data["devices"]):
                return False
            data["devices"] = remaining
            self._save()
            return True

    def revoke_all(self) -> int:
        with self._lock:
            data = self._load()
            count = len(data["devices"])
            if count:
                data["devices"] = []
                self._save()
            return count

    @property
    def expire_unused(self) -> bool:
        with self._lock:
            return bool(self._load()["expire_unused"])

    def set_expire_unused(self, enabled: bool) -> None:
        with self._lock:
            self._load()["expire_unused"] = bool(enabled)
            self._save()
