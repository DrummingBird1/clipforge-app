# utils/shared/outputs_index.py
#
# 23.10.2026: מסך "תוצרים" - כל הסרטונים הסופיים שכל הכלים ייצרו, במקום אחד. השורשים: <workspace>/<כלי>, <תיקיית
# הייצוא>/<כלי> ותיקייה משלו לכלי (utils/shared/export_dir.py); בעורך הגרפים רק outputs/ (בלי studio_handoff ו-staging).
# Rocket עם output_dir משלו מחוץ לאלה עוד לא נכלל - הסטודיו לא מגיש ולא פותח משם (_is_under_workspace).
# התיקיות הישנות (workspace/<כיוון>/<כלי>, לפני 19.10) לא נסרקות - dev/migrate_workspace_layout.py העביר אותן.
# קריאה בלבד: הסורק לא יוצר, לא מזיז ולא מוחק כלום.
import os
from typing import Dict, List, NamedTuple, Optional

from utils.shared import export_dir, workspace_dir

VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".webm")
# תיקיות פנימיות בתוך תיקיות התוצרים: חתימות, גרסאות קודמות, תיקיות לסטודיו, סטילס ושיתוף
SKIP_DIRS = {"_sig", "_previous", "studio_handoff", "staging"}
SKIP_DIR_SUFFIXES = ("_stills", "_share")
# רינדור בדיקה ותצוגה מקדימה של עורך הגרפים - לא תוצר; .partial - רינדור שעוד לא נגמר
SKIP_NAME_PARTS = (".partial.",)
SKIP_NAME_SUFFIXES = ("_test.mp4", "_preview.mp4")
MAX_DEPTH = 3
LIMIT = 500
_TOOL_SUBDIR = {workspace_dir.DATAVIZ: ("outputs",)}


class Root(NamedTuple):
    tool: str
    path: str


def tool_dir(base: str, tool: str) -> str:
    return os.path.join(base, tool, *_TOOL_SUBDIR.get(tool, ()))


def roots(workspace: str) -> List[Root]:
    """כל השורשים, בלי כפילויות (אותה תיקייה דרך שני נתיבים - פעם אחת)."""
    found = [Root(tool, tool_dir(workspace, tool)) for tool in workspace_dir.TOOLS]
    general = export_dir.configured_root()
    if general:
        found += [Root(tool, tool_dir(general, tool)) for tool in workspace_dir.TOOLS]
    found += [Root(tool, own) for tool in export_dir.TOOL_FOLDERS if (own := export_dir.configured_tool_root(tool))]
    unique: Dict[str, Root] = {}
    for root in found:
        unique.setdefault(_key(root.path), root)
    return list(unique.values())


def _key(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _is_output(name: str) -> bool:
    lower = name.lower()
    return (lower.endswith(VIDEO_EXTENSIONS) and not lower.startswith(".")
            and not any(part in lower for part in SKIP_NAME_PARTS) and not lower.endswith(SKIP_NAME_SUFFIXES))


def _skip_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIP_DIRS or name.endswith(SKIP_DIR_SUFFIXES)


def _walk(root: Root):
    stack = [(root.path, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    # junction (ב-Windows is_dir אומר עליו כן) יכול להוביל אל מחוץ לשורש - כמו symlink, לא נכנסים
                    if depth < MAX_DEPTH and not _skip_dir(entry.name) and not entry.is_junction():
                        stack.append((entry.path, depth + 1))
                elif entry.is_file(follow_symlinks=False) and _is_output(entry.name):
                    yield entry, entry.stat()
            except OSError:
                continue


def scan(workspace: str, limit: int = LIMIT) -> List[dict]:
    """התוצרים, החדשים ראשונים: path, name, tool, folder (יחסית לשורש הכלי, "" בשורש), size, mtime."""
    items: Dict[str, dict] = {}
    for root in roots(workspace):
        for entry, stat in _walk(root):
            relative = os.path.relpath(os.path.dirname(entry.path), root.path)
            items.setdefault(_key(entry.path), {
                "path": os.path.normpath(entry.path), "name": entry.name, "tool": root.tool,
                "folder": "" if relative == "." else relative.replace(os.sep, "/"),
                "size": stat.st_size, "mtime": stat.st_mtime,
            })
    return sorted(items.values(), key=lambda item: item["mtime"], reverse=True)[:limit]


def locate(path: str, workspace: str) -> Optional[dict]:
    """הכלי והתיקייה של תוצר (לפתיחה בסטודיו), אחרי realpath - או None כשזה לא סרטון קיים בתוך אחד השורשים."""
    if not path or not _is_output(os.path.basename(path)):
        return None
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        return None
    for root in roots(workspace):
        real_root = os.path.realpath(root.path)
        if os.path.normcase(real).startswith(os.path.normcase(real_root) + os.sep):
            parts = os.path.relpath(os.path.dirname(real), real_root).split(os.sep)
            if any(_skip_dir(part) for part in parts if part != "."):
                return None
            return {"path": real, "tool": root.tool, "folder": "" if parts == ["."] else "/".join(parts)}
    return None
