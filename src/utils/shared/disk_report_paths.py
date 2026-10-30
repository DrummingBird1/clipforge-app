# utils/shared/disk_report_paths.py
#
# איפה יושב דוח סריקת הדיסק (disk_scanner.py -> report.json/.html/.xlsx, ש-duplicate_cleaner.py
# ו-report_to_excel.py קוראים). זה תוצר, לא הגדרה - לכן workspace/reports/disk/ (ליד דוחות עורך-העל
# ב-workspace/reports/) ולא data/, שם הוא ישב עד 19.10.2026. דוח ישן שעוד יושב ב-data/report.json
# נקרא כגיבוי כשאין חדש - הקובץ הישן לא זז ולא נמחק (נתוני המשתמש).
import os

from utils.shared.workspace_dir import WORKSPACE_DIR
from utils.shared import data_paths

DISK_REPORTS_DIR = os.path.join(WORKSPACE_DIR, "reports", "disk")
DEFAULT_REPORT_JSON = os.path.join(DISK_REPORTS_DIR, "report.json")
LEGACY_REPORT_JSON = data_paths.path(data_paths.LEGACY_DISK_REPORT)
# duplicate_scene_detector.py - סצנות שחוזרות בתוך סרטון. אף אחד לא קורא אותו בקוד, אז בלי גיבוי לישן ב-data/
DUPLICATE_SCENES_REPORT_JSON = os.path.join(DISK_REPORTS_DIR, "duplicate_scenes_report.json")


def default_report_input() -> str:
    """הדוח לקריאה כשלא נתנו --input: החדש אם קיים, אחרת הישן מ-data/ אם קיים, אחרת החדש
    (כדי שהודעת "לא נמצא" תצביע על המקום שבו disk_scanner.py כותב עכשיו)."""
    if not os.path.exists(DEFAULT_REPORT_JSON) and os.path.exists(LEGACY_REPORT_JSON):
        return LEGACY_REPORT_JSON
    return DEFAULT_REPORT_JSON
