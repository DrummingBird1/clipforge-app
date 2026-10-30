# scripts/migrate_workspace_layout.py
#
# העברה חד-פעמית של תוצרים קיימים למבנה "לפי כלי" (19.10.2026): workspace/<כיוון>/<כלי> -> workspace/<כלי>/<כיוון>
# (המיפוי עצמו ב-utils/shared/workspace_dir.LAYOUT), ו-dataviz_israel_staging/ -> dataviz/staging/.
#
# ברירת המחדל היא הרצה יבשה: מדפיס כל העברה, כל נתיב שמור שישוכתב, וכל תיקייה ריקה שתוסר - בלי לגעת בכלום.
# --apply מבצע. בכל מקרה: לא דורסים (יעד קיים = מדלגים ומדווחים), לא מוחקים קבצים, הזזה רק באותו דיסק (os.replace),
# ומסירים רק תיקייה שהתרוקנה לגמרי אחרי ההעברות (os.rmdir נכשל על תיקייה עם תוכן). פריט שלא שייך לאף מיפוי נשאר במקומו.
#
#   uv run python dev/migrate_workspace_layout.py            # יבש
#   uv run python dev/migrate_workspace_layout.py --apply    # רק אחרי שהמשתמש ראה את הרשימה
import argparse
import json
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from utils.shared import workspace_dir as layout  # noqa: E402
from utils.shared import data_paths


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _same_disk(a, b):
    return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()


class Plan:
    def __init__(self):
        self.moves = []          # (old_file, new_file)
        self.conflicts = []      # (old_file, new_file) - היעד קיים, לא נוגעים
        self.left = []           # פריטים בתיקיות הישנות שלא שייכים לאף מיפוי
        self.dir_moves = []      # (old_dir, new_dir) - לשכתוב נתיבים שמורים
        self.rewrites = []       # (קובץ, מפתח/מיקום, ישן, חדש)
        self.empty_dirs = []     # תיקיות שיתרוקנו לגמרי ויוסרו
        self.skipped_disk = []   # (old, new) - דיסק אחר, לא מזיזים


def _plan_tree(plan, old_dir, new_dir, files_only=False):
    """כל קובץ תחת old_dir (או רק בשורש שלו, files_only) -> אותו נתיב יחסי תחת new_dir."""
    if not os.path.isdir(old_dir):
        return
    if not _same_disk(old_dir, new_dir):
        plan.skipped_disk.append((old_dir, new_dir))
        return
    plan.dir_moves.append((old_dir, new_dir))
    for root, dirs, files in os.walk(old_dir):
        if files_only:   # תתי-התיקיות שייכות למיפויים האחרים (או מדווחות ב"נשאר במקום")
            dirs[:] = []
        for name in sorted(files):
            old = os.path.join(root, name)
            new = os.path.join(new_dir, os.path.relpath(old, old_dir))
            (plan.conflicts if os.path.exists(new) else plan.moves).append((old, new))


def _bases(workspace):
    """ה-workspace, ובסיס הפלט של Rocket אם הוא אחר (output_dir ב-rocket_settings.json)."""
    bases = [workspace]
    try:
        with open(data_paths.path(data_paths.ROCKET_SETTINGS), encoding="utf-8") as f:
            rocket = json.load(f).get("output_dir") or ""
    except (OSError, ValueError):
        rocket = ""
    if rocket and os.path.isdir(rocket) and _norm(rocket) != _norm(workspace):
        bases.append(rocket)
    return bases


def build_plan(workspace, bases=None):
    plan = Plan()
    for base in bases or _bases(workspace):
        pairs = [(os.path.join(base, *old), os.path.join(base, *new), old in layout.FILES_ONLY_OLD) for new, old in layout.LAYOUT]
        if _norm(base) == _norm(workspace):
            pairs += [(os.path.join(base, *old), os.path.join(base, *new), False) for new, old in layout.STAGING_MOVES]
        claimed = {_norm(old) for old, _new, _files_only in pairs}
        for old, new, files_only in sorted(pairs, key=lambda p: -len(p[0])):   # הספציפי קודם (square/edited_videos לפני square/)
            _plan_tree(plan, old, new, files_only=files_only)
        # מה עוד יושב ישירות בתיקיות הכיוון הישנות ולא שייך לאף מיפוי
        for orientation in layout.ORIENTATIONS:
            parent = os.path.join(base, orientation)
            if os.path.isdir(parent):
                for name in sorted(os.listdir(parent)):
                    path = os.path.join(parent, name)
                    if os.path.isdir(path) and _norm(path) not in claimed:
                        plan.left.append(path)
        plan.empty_dirs += _dirs_left_empty(plan, [os.path.join(base, o) for o in layout.ORIENTATIONS]
                                            + [os.path.join(base, *old) for _new, old in layout.STAGING_MOVES])
    _plan_manifest_rewrites(plan, workspace)
    return plan


def _dirs_left_empty(plan, roots):
    """תיקיות שלא יישאר בהן כלום אחרי ההעברות (מלמטה למעלה) - רק אותן מסירים."""
    moving = {_norm(old) for old, _new in plan.moves}
    empty = []
    for top in roots:
        if not os.path.isdir(top):
            continue
        emptied = set()
        for root, dirs, files in os.walk(top, topdown=False):
            if all(_norm(os.path.join(root, f)) in moving for f in files) and all(_norm(os.path.join(root, d)) in emptied for d in dirs):
                emptied.add(_norm(root))
                empty.append(root)
    return empty


def _replace_path(value, plan):
    for old, new in plan.moves:
        if _norm(value) == _norm(old):
            return new
    for old_dir, new_dir in sorted(plan.dir_moves, key=lambda p: -len(p[0])):
        if _norm(value) == _norm(old_dir):
            return new_dir
        if _norm(value).startswith(_norm(old_dir) + os.sep):
            return os.path.join(new_dir, os.path.relpath(value, old_dir))
    return None


def _plan_manifest_rewrites(plan, workspace):
    """run manifests (workspace/.cache/run_manifests) שומרים נתיבי פלט מוחלטים - לפאנל התוצאות של הסטודיו."""
    folder = os.path.join(workspace, ".cache", "run_manifests")
    if not os.path.isdir(folder):
        return
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue

        def walk(node, where):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{where}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{where}[{i}]")
            elif isinstance(node, str) and os.path.isabs(node):
                new = _replace_path(node, plan)
                if new:
                    plan.rewrites.append((path, where, node, new))

        walk(data, "$")


def _rewrite_manifests(plan):
    by_file = {}
    for path, _where, old, new in plan.rewrites:
        by_file.setdefault(path, {})[old] = new
    for path, mapping in by_file.items():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        def fix(node):
            if isinstance(node, dict):
                return {k: fix(v) for k, v in node.items()}
            if isinstance(node, list):
                return [fix(v) for v in node]
            return mapping.get(node, node) if isinstance(node, str) else node

        tmp = path + ".migrate.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(fix(data), f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)  # safe: rewrites the app's own run-manifest cache file in place (same content, new paths)


def apply_plan(plan):
    moved, failed = 0, []
    for old, new in plan.moves:
        if os.path.exists(new):   # נוצר מאז התכנון - לא דורסים
            failed.append((old, "היעד כבר קיים"))
            continue
        try:
            os.makedirs(os.path.dirname(new), exist_ok=True)
            os.replace(old, new)  # safe: moves the user's output file to its new folder on the same disk; target checked to not exist
            moved += 1
        except OSError as e:
            failed.append((old, str(e)))
    _rewrite_manifests(plan)
    removed = 0
    for path in plan.empty_dirs:
        try:
            os.rmdir(path)  # safe: os.rmdir refuses a non-empty folder - only folders the moves left truly empty
            removed += 1
        except OSError:
            pass
    return moved, failed, removed


def print_plan(plan, out=print):
    out(f"== העברות ({len(plan.moves)})")
    for old, new in plan.moves:
        out(f"  {old}\n    -> {new}")
    out(f"== יעד קיים - מדלגים, לא דורסים ({len(plan.conflicts)})")
    for old, new in plan.conflicts:
        out(f"  {old}\n    X  {new}")
    out(f"== נתיבים שמורים שישוכתבו ({len(plan.rewrites)})")
    for path, where, old, new in plan.rewrites:
        out(f"  {path} {where}\n    {old}\n    -> {new}")
    out(f"== תיקיות ריקות שיוסרו אחרי ההעברות ({len(plan.empty_dirs)})")
    for path in plan.empty_dirs:
        out(f"  {path}")
    out(f"== נשאר במקום - לא שייך לאף מיפוי ({len(plan.left)})")
    for path in plan.left:
        out(f"  {path}")
    if plan.skipped_disk:
        out(f"== דיסק אחר - לא מזיזים ({len(plan.skipped_disk)})")
        for old, new in plan.skipped_disk:
            out(f"  {old} -> {new}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="העברת התוצרים הקיימים למבנה לפי כלי (ברירת מחדל: הרצה יבשה)")
    parser.add_argument("--apply", action="store_true", help="לבצע בפועל. בלי הדגל - רק מדפיס מה היה קורה")
    parser.add_argument("--workspace", default="", help="תיקיית workspace אחרת (ברירת מחדל: utils.shared.workspace_dir.WORKSPACE_DIR)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):   # עברית בקונסול של Windows (cp1255) ובצינור
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    workspace = args.workspace or layout.WORKSPACE_DIR
    plan = build_plan(workspace)
    print_plan(plan)
    if not args.apply:
        print("\nהרצה יבשה - שום דבר לא זז. להרצה בפועל: --apply")
        return 0
    moved, failed, removed = apply_plan(plan)
    print(f"\nהועברו {moved} קבצים, שוכתבו {len(plan.rewrites)} נתיבים, הוסרו {removed} תיקיות ריקות; נכשלו {len(failed)}")
    for old, error in failed:
        print(f"  ! {old}: {error}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
