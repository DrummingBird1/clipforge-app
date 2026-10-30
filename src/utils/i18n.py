# utils/i18n.py - shim: המודול עבר ל-utils/shared/i18n.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.i18n.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.shared.i18n.
import sys

from utils.shared import i18n as _module
from utils.shared.i18n import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
