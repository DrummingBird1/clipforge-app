# utils/dataviz_handoff.py - shim: הקוד עבר ל-dataviz/web/handoff.py (19.10.2026).
# המודול הישן הוא אותו אובייקט כמו החדש (sys.modules), כך ש-import ישן, from-import ו-monkeypatch עובדים כמו קודם.
import sys

from dataviz.web import handoff as _module
from dataviz.web.handoff import *  # noqa: F401,F403  (לבודקי טיפוסים - בזמן ריצה השורה הבאה מחליפה את המודול כולו)

sys.modules[__name__] = _module
