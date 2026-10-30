# utils/seo_generator.py - shim: המודול עבר ל-utils/bot/seo_generator.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.seo_generator.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.bot.seo_generator.
import sys

from utils.bot import seo_generator as _module
from utils.bot.seo_generator import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
