# utils/shared/workspace_dir.py
#
# workspace/ = תיקיית העבודה והתוצרים (קליפים לאישור, יצוא, מטמונים) - מקור אחד לנתיב, כמו utils/shared/data_dir.py
# ל-data/. CLIPFORGE_WORKSPACE_DIR מפנה אותה למקום אחר (שרת בדיקה, הרצת ניסיון) - אותו משתנה ואותה ברירת מחדל
# כמו web_app.WORKSPACE_DIR, כך שכל מי שגוזר ממנו כותב לאותו מקום. בלי המשתנה - workspace/ בשורש הפרויקט.
#
# תוצרים לפי כלי ואז לפי כיוון/יעד (19.10.2026): workspace/<כלי>/<כיוון או יעד>/ - studio/horizontal, timelapses/vertical,
# dataviz/outputs/square, rocket_shorts/TikTok. קודם הפוך: workspace/<כיוון>/<כלי> (horizontal/edited_videos וכו').
# tool_output_dir בונה נתיב חדש; legacy_output_dir מחזיר את הנתיב הישן המקביל - לקוראים שצריכים למצוא תוצר ישן
# (קיים -> משתמשים בו) ולסקריפט ההעברה (dev/migrate_workspace_layout.py).
import os
from typing import List, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WORKSPACE_DIR = os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(PROJECT_ROOT, "workspace")

ORIENTATIONS = ("horizontal", "vertical", "square")
STUDIO = "studio"                      # עורך-העל (my_scripts/video/video_editor.py)
TIMELAPSES = "timelapses"              # timelapse_maker.py
HIGHLIGHT_REELS = "highlight_reels"    # highlight_reel_maker.py
DATAVIZ = "dataviz"                    # dataviz/outputs/<כיוון>, dataviz/studio_handoff/<כיוון>, dataviz/staging
ROCKET_SHORTS = "rocket_shorts"        # rocket_shorts_publisher.py (+ ריקאפ שבועי ו-Wrapped שנכתבים לידו)
ROCKET_TARGETS = ("YouTube", "TikTok", "Instagram", "square")
TOOLS = (STUDIO, TIMELAPSES, HIGHLIGHT_REELS, DATAVIZ, ROCKET_SHORTS)

# (נתיב חדש, נתיב ישן) יחסית לבסיס, מהספציפי לכללי. square/ הישנה של Rocket היא גם ההורה של square/edited_videos
# וכו' - לכן היא אחרונה, ומסומנת "רק קבצים" (תתי-התיקיות שלה שייכות למיפויים האחרים).
LAYOUT: List[Tuple[Tuple[str, ...], Tuple[str, ...]]] = (
    [((STUDIO, o), (o, "edited_videos")) for o in ORIENTATIONS]
    + [((TIMELAPSES, o), (o, "timelapses")) for o in ORIENTATIONS]
    + [((HIGHLIGHT_REELS, o), (o, "highlight_reels")) for o in ORIENTATIONS]
    + [((DATAVIZ, "outputs", o), (o, "dataviz")) for o in ORIENTATIONS]
    + [((DATAVIZ, "studio_handoff", o), (o, "dataviz_studio")) for o in ORIENTATIONS]
    + [((ROCKET_SHORTS, "YouTube"), ("horizontal", "YouTube")), ((ROCKET_SHORTS, "TikTok"), ("vertical", "TikTok")),
       ((ROCKET_SHORTS, "Instagram"), ("vertical", "Instagram")), ((ROCKET_SHORTS, "square"), ("square",))]
)
FILES_ONLY_OLD = {("square",)}
# תיקייה שהמשתמש יצר ביד (פרקי טיוטה לעורך הגרפים) - רק סקריפט ההעברה מזיז אותה, הקוד לא כותב לשם
STAGING_MOVES = [((DATAVIZ, "staging"), ("dataviz_israel_staging",))]


def tool_output_dir(tool: str, *parts: str, base: Optional[str] = None) -> str:
    """workspace/<כלי>/<חלקים...> (base: בסיס אחר - למשל output_dir של Rocket, או WORKSPACE_ROOT של סקריפט)."""
    return os.path.join(base or WORKSPACE_DIR, tool, *parts)


def legacy_output_dir(tool: str, *parts: str, base: Optional[str] = None) -> Optional[str]:
    """הנתיב הישן (לפי כיוון) שמקביל ל-tool_output_dir(tool, *parts), או None כשאין מקביל."""
    new = (tool, *parts)
    for new_parts, old_parts in LAYOUT:
        if new[:len(new_parts)] == new_parts:
            return os.path.join(base or WORKSPACE_DIR, *old_parts, *new[len(new_parts):])
    return None


def existing_output_dir(tool: str, *parts: str, base: Optional[str] = None) -> str:
    """לקוראים: החדש אם קיים; אחרת הישן אם קיים (לפני ההעברה); אחרת החדש."""
    new = tool_output_dir(tool, *parts, base=base)
    old = legacy_output_dir(tool, *parts, base=base)
    if not os.path.isdir(new) and old and os.path.isdir(old):
        return old
    return new
