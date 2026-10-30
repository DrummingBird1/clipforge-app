# utils/thumbnail_generator.py - shim: המודול עבר ל-utils/media/thumbnail_generator.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.thumbnail_generator.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.media.thumbnail_generator.
import sys

from utils.media import thumbnail_generator as _module
from utils.media.thumbnail_generator import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
