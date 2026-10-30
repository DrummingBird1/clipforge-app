# utils/editor_runs.py - shim: המודול עבר ל-utils/video/editor_runs.py (19.10.2026).
# הנתיב הישן מצביע על אותו אובייקט מודול בדיוק (sys.modules), כך ש-import ישן, monkeypatch ו-mock.patch
# על "utils.editor_runs.X" פוגעים במודול האמיתי. קוד חדש מייבא מ-utils.video.editor_runs.
import sys

from utils.video import editor_runs as _module
from utils.video.editor_runs import *  # noqa: F401,F403 - לשמות שבדיקת הטיפוסים רואה


def __getattr__(name: str):  # לבדיקת הטיפוסים בלבד: שמות פרטיים (_x) שה-* לא מביא. בזמן ריצה המודול כבר הוחלף
    return getattr(_module, name)

sys.modules[__name__] = _module
