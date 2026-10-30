# utils/workspace_dir.py - shim: המודול עבר ל-utils/shared/workspace_dir.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.workspace_dir.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.shared.workspace_dir.
import sys

from utils.shared import workspace_dir as _module
from utils.shared.workspace_dir import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
