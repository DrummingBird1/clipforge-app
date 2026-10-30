# utils/scheduler_store.py - shim: המודול עבר ל-utils/bot/scheduler_store.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.scheduler_store.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.bot.scheduler_store.
import sys

from utils.bot import scheduler_store as _module
from utils.bot.scheduler_store import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
