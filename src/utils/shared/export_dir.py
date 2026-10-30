# utils/shared/export_dir.py
#
# תיקיית ייצוא (23.10.2026, החלטת המשתמש): התוצרים הסופיים (סרטונים והקבצים שלידם - תמונה ממוזערת, כתוביות, gif) נכתבים
# ישירות לתיקייה שהמשתמש בחר, גם בכונן רשת - לא עותק, ולא רינדור מקומי והעברה (‏.partial ושינוי שם באותה תיקייה, כמו
# בסטודיו, נשארים). מטמונים, דוחות, run manifests וקליפים לאישור נשארים ב-workspace.
# - ההגדרה: data/export_settings.json {"root": "..."}. לא config.json - ה-GUI הקפוא כותב אותו מחדש רק עם המפתחות שלו.
# - ריק = workspace/, כמו קודם. תיקייה שלא קיימת או שאי אפשר לכתוב אליה ברגע הריצה = workspace, עם הודעה בלוג - הריצה
#   לא נעצרת.
# - CLIPFORGE_EXPORT_DIR גובר על הקובץ (הרצה בודדת). tests/conftest.py מוחק אותו, ו-data/ של הטסטים זמנית.
# - כלי עם תיקיית פלט משלו (output_dir של Rocket) גובר; ברירת המחדל שלו (workspace) עוקבת אחרי תיקיית הייצוא.
# - שלב 2: תיקייה לכלי - {"tools": {"studio": "D:\Studio"}} גוברת על התיקייה הכללית לאותו כלי, והתוצרים נכתבים ישירות
#   לתוכה (<תיקייה>/<כיוון>), בלי שכבת "<כלי>/" - התיקייה כבר שלו. CLIPFORGE_EXPORT_DIR גובר גם עליה. Rocket - בהגדרות שלו.
import json
import os
import uuid
from typing import List, NamedTuple, Optional, Tuple

from utils.shared import workspace_dir
from utils.shared.atomic_write import atomic_write_json
from utils.shared.data_dir import DATA_DIR
from utils.shared import data_paths

SETTINGS_PATH = data_paths.path(data_paths.EXPORT_SETTINGS)
ENV_VAR = "CLIPFORGE_EXPORT_DIR"
# כלים שאפשר לתת להם תיקייה משלהם (Rocket - output_dir בהגדרות שלו). עורך הגרפים: <תיקייה>/outputs/<כיוון> (dataviz_maker.py).
TOOL_FOLDERS = (workspace_dir.STUDIO, workspace_dir.TIMELAPSES, workspace_dir.HIGHLIGHT_REELS, workspace_dir.DATAVIZ)


class Resolution(NamedTuple):
    base: str                 # לשם נכתבים התוצרים עכשיו
    root: Optional[str]       # תיקיית הייצוא שהוגדרה, או None
    problem: Optional[str]    # למה root לא בשימוש עכשיו, או None


def _workspace() -> str:
    """workspace לפי הסביבה ברגע הקריאה - כמו WORKSPACE_ROOT של video_editor.py (טסט שטוען סקריפט בתהליך עם
    CLIPFORGE_WORKSPACE_DIR אחר מקבל את שלו, לא את זה שנקבע כשהמודול workspace_dir יובא לראשונה)."""
    return os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(workspace_dir.PROJECT_ROOT, "workspace")


def _norm(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _inside(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath([_norm(path), _norm(parent)]) == _norm(parent)
    except ValueError:   # כוננים שונים
        return False


def _read(path: str = "") -> dict:
    try:
        with open(path or SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_root(path: str = "") -> str:
    value = _read(path).get("root")
    return value.strip() if isinstance(value, str) else ""


def save_root(root: str, path: str = "") -> None:
    data = _read(path)
    data["root"] = root
    atomic_write_json(path or SETTINGS_PATH, data, ensure_ascii=False, indent=2)


def load_tool_root(tool: str, path: str = "") -> str:
    tools = _read(path).get("tools")
    value = tools.get(tool) if isinstance(tools, dict) else None
    return value.strip() if isinstance(value, str) else ""


def save_tool_root(tool: str, root: str, path: str = "") -> None:
    data = _read(path)
    current = data.get("tools")
    tools: dict = current if isinstance(current, dict) else {}
    if root:
        tools[tool] = root
    else:
        tools.pop(tool, None)
    data["tools"] = tools
    atomic_write_json(path or SETTINGS_PATH, data, ensure_ascii=False, indent=2)


def is_workspace(path: str) -> bool:
    return bool(path) and _norm(path) == _norm(_workspace())


def unusable_reason(root: str) -> Optional[str]:
    """None כשאפשר לכתוב לשם עכשיו; אחרת סיבה קצרה (עברית) - לשורת הלוג ולמסך ההגדרות."""
    if not os.path.isabs(root):
        return "הנתיב צריך להיות מלא (כונן ותיקייה)"
    if not os.path.isdir(root):
        return "התיקייה לא קיימת, או שהכונן לא מחובר"
    probe = os.path.join(root, f".clipforge_write_test_{uuid.uuid4().hex}")
    try:
        with open(probe, "w", encoding="utf-8"):
            pass
        os.remove(probe)
    except OSError as e:
        return f"אין הרשאת כתיבה ({e.strerror or e})"
    return None


def invalid_choice_reason(root: str) -> Optional[str]:
    """בשמירת ההגדרה: לא בתוך data/ (נתוני האפליקציה - וגם /api/download לא מגיש משם) ולא בתוך קוד הפרויקט."""
    if not os.path.isabs(root):
        return "הנתיב צריך להיות מלא (כונן ותיקייה)"
    if _inside(root, DATA_DIR):
        return "לא בתוך data/ - שם נתוני האפליקציה"
    if _inside(root, workspace_dir.PROJECT_ROOT) and not _inside(root, _workspace()):
        return "לא בתוך תיקיית הקוד של הפרויקט - workspace/ או תיקייה מחוצה לו"
    return unusable_reason(root)


def configured_root(settings_path: str = "") -> str:
    """התיקייה שהוגדרה (CLIPFORGE_EXPORT_DIR או ההגדרה), בלי לבדוק אם היא זמינה - "" = workspace."""
    env = os.environ.get(ENV_VAR)
    root = env.strip() if env is not None else load_root(settings_path)
    return "" if is_workspace(root) else root


def resolve(settings_path: str = "") -> Resolution:
    root = configured_root(settings_path)
    if not root:
        return Resolution(_workspace(), None, None)
    problem = unusable_reason(root)
    if problem:
        return Resolution(_workspace(), root, problem)
    return Resolution(root, root, None)


def configured_tool_root(tool: str, settings_path: str = "") -> str:
    """התיקייה של הכלי עצמו, אם הוגדרה ו-CLIPFORGE_EXPORT_DIR לא דורס - "" = לפי התיקייה הכללית."""
    if ENV_VAR in os.environ:
        return ""
    root = load_tool_root(tool, settings_path)
    return "" if is_workspace(root) else root


def resolve_tool(tool: str, settings_path: str = "") -> Resolution:
    """כמו resolve, אבל base היא כבר התיקייה של הכלי: התיקייה שלו, או <תיקיית הייצוא / workspace>/<כלי>."""
    own = configured_tool_root(tool, settings_path)
    if own:
        problem = unusable_reason(own)
        return Resolution(os.path.join(_workspace(), tool), own, problem) if problem else Resolution(own, own, None)
    general = resolve(settings_path)
    return Resolution(os.path.join(general.base, tool), general.root, general.problem)


def configured_folders(settings_path: str = "") -> List[Tuple[str, str]]:
    """(כלי, תיקייה) לכל תיקייה שהוגדרה, בלי workspace: <תיקייה כללית>/<כלי> לכל כלי, ותיקיות הכלים - להגשה, לפתיחה ולגיבוי."""
    root = configured_root(settings_path)
    folders = [(tool, os.path.join(root, tool)) for tool in workspace_dir.TOOLS] if root else []
    return folders + [(tool, own) for tool in TOOL_FOLDERS if (own := configured_tool_root(tool, settings_path))]


def fallback_note(resolution: Resolution) -> Optional[str]:
    if not resolution.problem:
        return None
    return f"⚠️ התוצרים נשמרים ב-workspace כי תיקיית הייצוא {resolution.root} לא זמינה: {resolution.problem}"


_announced = False


def _announce(resolution: Resolution) -> Resolution:
    global _announced
    note = fallback_note(resolution)
    if note and not _announced:
        _announced = True
        print(note, flush=True)
    return resolution


def output_base() -> str:
    """הבסיס הכללי של התוצרים (Rocket והריקאפ, דרך follow_global). כשתיקיית הייצוא לא זמינה - workspace, ושורה
    אחת בלוג של הריצה."""
    return _announce(resolve()).base


def output_dir(tool: str, *parts: str) -> str:
    """לסקריפטים: התיקייה לתוצר הסופי של כלי - <התיקייה של הכלי>/<parts>, או <תיקיית הייצוא / workspace>/<כלי>/<parts>."""
    return os.path.join(_announce(resolve_tool(tool)).base, *parts)


def follow_global(configured: Optional[str]) -> str:
    """כלי עם תיקיית פלט משלו (Rocket, הריקאפ, Wrapped): ריק או workspace (ברירת המחדל שלו) = תיקיית הייצוא; אחרת מה
    שהוגדר בו."""
    if not configured or is_workspace(configured):
        return output_base()
    return configured
