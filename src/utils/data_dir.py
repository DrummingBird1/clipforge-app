# utils/data_dir.py - shim: המודול עבר ל-utils/shared/data_dir.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.data_dir.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.shared.data_dir.
import sys

from utils.shared import data_dir as _module
from utils.shared.data_dir import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
