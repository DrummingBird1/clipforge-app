# utils/gemini_quota.py - shim: המודול עבר ל-utils/media/gemini_quota.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.gemini_quota.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.media.gemini_quota.
import sys

from utils.media import gemini_quota as _module
from utils.media.gemini_quota import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
