# dataviz/web/handoff.py (עד 19.10.2026: utils/dataviz_handoff.py)
#
# גל 56: סרטון גרפים מוכן -> הסטודיו. הסטודיו עובד על כל הסרטונים שבתיקייה (גם בתתי-תיקיות), ובתיקיית התוצרים של
# עורך הגרפים יש גם תצוגות מקדימות, בדיקות ו-Shorts - לכן כל סרטון מקבל תיקייה משלו:
# workspace/dataviz/studio_handoff/<כיוון>/<שם הסרטון>/<שם הסרטון>.mp4. הקובץ מקושר (hard link - בלי עותק נוסף על הדיסק),
# או מועתק כשאי אפשר לקשר. אותה תיקייה בכל פעם = הפרויקט של הסטודיו (לוגו, יעדים, עריכות) נשמר גם אחרי רינדור מחדש.
# התוצר עצמו לא זז ולא משתנה, וכלום לא נמחק: עותק ישן (התוצר רונדר מחדש מאז) עובר ל-studio_handoff/<כיוון>/_previous/ -
# מחוץ לתיקיית הסרטון, כדי שהסטודיו לא ירנדר גם אותו.

import os
import shutil
import time

STUDIO_DIR = "dataviz_studio"
PREVIOUS = "_previous"


def studio_root(workspace, orientation):
    """workspace/dataviz/studio_handoff/<כיוון> (עד 19.10.2026: workspace/<כיוון>/dataviz_studio)."""
    from utils.shared.workspace_dir import DATAVIZ, tool_output_dir
    return tool_output_dir(DATAVIZ, "studio_handoff", orientation, base=workspace)


def _same(a, b):
    try:
        if os.path.samefile(a, b):
            return True
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return sa.st_size == sb.st_size and int(sa.st_mtime) == int(sb.st_mtime)


def _unique(path):
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path


def studio_folder(source, root):
    """מכין לסרטון תיקייה משלו לסטודיו ומחזיר {"folder", "file", "state"}:
    state = "ready" (כבר שם ומעודכן), "linked" (קישור חדש) או "copied" (עותק - כשאי אפשר לקשר)."""
    name = os.path.basename(source)
    stem = os.path.splitext(name)[0]
    folder = os.path.join(root, stem if stem != PREVIOUS else stem + "_video")
    dest = os.path.join(folder, name)
    os.makedirs(folder, exist_ok=True)
    if os.path.exists(dest):
        if _same(source, dest):
            return {"folder": folder, "file": name, "state": "ready"}
        previous = os.path.join(root, PREVIOUS)
        os.makedirs(previous, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(os.path.getmtime(dest)))
        os.replace(dest, _unique(os.path.join(previous, f"{stem}_{stamp}.mp4")))  # safe: our own earlier link/copy inside dataviz_studio, moved aside (never deleted, never the dataviz output itself)
    try:
        os.link(source, dest)
        state = "linked"
    except OSError:
        shutil.copy2(source, dest)
        state = "copied"
    return {"folder": folder, "file": name, "state": state}
