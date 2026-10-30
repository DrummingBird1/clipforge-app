# dev/migrate_data_layout.py
#
# העברה חד-פעמית של data/ לתיקיות לפי נושא (24.10.2026, פריט 19 שלב ב'): settings/, security/, bot/, studio/, dataviz/ ו-cache/.
# ‏logs/ ו-backups/ נשארים במקומם, וכך גם קובצי הדוגמה שבגיט (*.example.json). המיפוי: utils/shared/data_paths.FOLDERS.
#
# הקוד קורא מהמבנה החדש רק כש-data/.data_layout (data_paths.LAYOUT_MARKER) קיים - והסקריפט כותב אותו רק אחרי שכל
# ההעברות הצליחו והנתיבים שוכתבו. העברה שנכשלה באמצע מוחזרת אחורה: מה שזז חוזר לשורש, ושום דבר לא נשאר חצי-חצי.
# עורך הגרפים עובר כולו ל-dataviz/ עם אותם שמות: הוא מוצא את ה-overrides שתי רמות מעל הפרק, והיחס הזה נשמר.
#
# ברירת המחדל היא הרצה יבשה: מדפיס כל העברה ("מקור -> יעד") וכל נתיב מוחלט שישוכתב בקובצי ה-JSON, בלי לגעת בכלום.
# ‏--apply: קודם zip של data/ (בלי logs/ ו-backups/) ל-backups/, ואז מזיזים. לא דורסים: יעד קיים = לא מזיזים כלום. לא
# מוחקים קבצים, ומזיזים רק באותו דיסק (os.replace). מסרב כש-render.lock קיים, כי אז רינדור כנראה רץ.
#
#   uv run python dev/migrate_data_layout.py                                  # יבש, על data/
#   uv run python dev/migrate_data_layout.py --data-dir <עותק> --stored-root E:\...\data   # יבש על עותק, עם נתיבים שנשמרו מול המקור
#   uv run python dev/migrate_data_layout.py --apply                          # כש-ClipForge סגור, אחרי שהמשתמש ראה את הרשימה
import argparse
import datetime
import json
import os
import sys
import zipfile

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from utils.shared import data_paths  # noqa: E402

# נשארים בשורש בכוונה. render.lock לא מוזז: כשהוא קיים, ההרצה בפועל מסרבת. ‏.web_launcher.lock - המנעול של ה-launcher.
STAY = {data_paths.LOGS, data_paths.BACKUPS, data_paths.RENDER_LOCK, data_paths.LAYOUT_MARKER, ".web_launcher.lock",
        "config.example.json", "rocket_settings.example.json"}
# מה שלא נכנס לגיבוי שלפני ההעברה, ולא נסרק לנתיבים שמורים: הלוגים והגיבויים עצמם (שניהם נשארים במקום)
_BACKUP_SKIP = {data_paths.LOGS, data_paths.BACKUPS}


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


class Plan:
    def __init__(self, data_dir, stored_roots):
        self.data_dir = data_dir
        self.stored_roots = stored_roots   # נתיבי data/ שמופיעים בנתיבים שנשמרו (data_dir עצמו, ומקור של עותק)
        self.moves = []          # (old, new) - קובץ או תיקייה שלמה
        self.conflicts = []      # (old, new) - היעד קיים, לא נוגעים
        self.left = []           # פריטים בשורש שלא שייכים לאף מיפוי
        self.rewrites = []       # (קובץ JSON במיקום החדש, מיקום בקובץ, ישן, חדש)


def _moved_name(rel_first):
    folder = data_paths.folder_of(rel_first)
    return os.path.join(folder, rel_first) if folder else None


def _replace_path(value, plan):
    """נתיב מוחלט שנשמר ומצביע לפריט שזז (או לתוכו) -> הנתיב החדש מול אותו שורש. None אם הוא לא מושפע."""
    if not os.path.isabs(value):
        return None
    for root in plan.stored_roots:
        if not _norm(value).startswith(_norm(root) + os.sep):
            continue
        rel = os.path.relpath(os.path.abspath(value), os.path.abspath(root))
        first, _, rest = rel.partition(os.sep)
        moved = _moved_name(first)
        if moved:
            return os.path.join(root, moved, rest) if rest else os.path.join(root, moved)
    return None


def _json_files(plan):
    """כל קובץ JSON תחת data/ (בלי logs/ ו-backups/), עם המיקום שלו אחרי ההעברה."""
    for current, dirs, files in os.walk(plan.data_dir):
        rel_dir = os.path.relpath(current, plan.data_dir)
        if rel_dir == ".":
            dirs[:] = [d for d in dirs if d not in _BACKUP_SKIP]
        for name in sorted(files):
            if not name.endswith(".json"):
                continue
            path = os.path.join(current, name)
            first = name if rel_dir == "." else rel_dir.split(os.sep)[0]
            moved = _moved_name(first)
            after = os.path.join(plan.data_dir, moved, os.path.relpath(path, os.path.join(plan.data_dir, first))) if moved else path
            yield path, os.path.normpath(after)


def _plan_rewrites(plan):
    for path, after in _json_files(plan):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue

        def walk(node, where, after=after):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{where}.{key}")
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    walk(value, f"{where}[{i}]")
            elif isinstance(node, str):
                new = _replace_path(node, plan)
                if new:
                    plan.rewrites.append((after, where, node, new))

        walk(data, "$")


def build_plan(data_dir, stored_roots=()):
    plan = Plan(data_dir, [data_dir, *stored_roots])
    for name in sorted(os.listdir(data_dir)):
        if name in STAY or name in set(data_paths.FOLDERS.values()):   # תיקיות היעד עצמן (הרצה חוזרת)
            continue
        folder = data_paths.folder_of(name)
        if not folder:
            plan.left.append(os.path.join(data_dir, name))
            continue
        old, new = os.path.join(data_dir, name), os.path.join(data_dir, folder, name)
        (plan.conflicts if os.path.exists(new) else plan.moves).append((old, new))
    _plan_rewrites(plan)
    return plan


def backup(data_dir, now=None):
    """zip של data/ לפני ההעברה, ב-backups/. מחזיר את הנתיב."""
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(data_dir, data_paths.BACKUPS)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"pre-data-layout-{stamp}.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for current, dirs, files in os.walk(data_dir):
            if os.path.relpath(current, data_dir) == ".":
                dirs[:] = [d for d in dirs if d not in _BACKUP_SKIP]
            for name in files:
                path = os.path.join(current, name)
                zf.write(path, os.path.relpath(path, data_dir))
    return target


def _rewrite_json(plan):
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
        os.replace(tmp, path)  # safe: rewrites the user's own JSON in place (same content, new data/ paths); backed up first


def apply_plan(plan):
    """מזיז הכל, משכתב את הנתיבים וכותב את הסימן. נכשל באמצע = מחזיר את מה שכבר זז, והסימן לא נכתב."""
    if plan.conflicts:   # יעד שכבר קיים - לא מזיזים כלום, כדי שלא יישאר חצי מבנה ישן וחצי חדש
        return 0, [(old, "היעד כבר קיים - לא הוזז כלום") for old, _new in plan.conflicts]
    done, failed = [], []
    for old, new in plan.moves:
        if os.path.exists(new):   # נוצר מאז התכנון - לא דורסים
            failed.append((old, "היעד כבר קיים"))
            break
        try:
            os.makedirs(os.path.dirname(new), exist_ok=True)
            os.replace(old, new)  # safe: moves a data/ entry into its topic folder on the same disk; target checked to not exist
            done.append((old, new))
        except OSError as e:
            failed.append((old, str(e)))
            break
    if not failed:
        try:
            _rewrite_json(plan)
            data_paths.ensure_folders(plan.data_dir)   # גם תיקייה שלא עבר אליה אף קובץ - הכותבים לא יוצרים אותה בעצמם
            with open(os.path.join(plan.data_dir, data_paths.LAYOUT_MARKER), "w", encoding="utf-8") as f:
                f.write("2\n")
            return len(done), []
        except OSError as e:
            failed.append((data_paths.LAYOUT_MARKER, str(e)))
    for old, new in reversed(done):   # חזרה אחורה - שום דבר לא נשאר חצי-חצי
        try:
            os.replace(new, old)  # safe: moves the entry this run just moved back to where it was; nothing is deleted
        except OSError as e:
            failed.append((new, f"לא חזר למקומו: {e}"))
    return 0, failed


def print_plan(plan, out=print):
    def rel(path):
        return os.path.relpath(path, plan.data_dir)

    out(f"data/: {plan.data_dir}")
    out(f"== העברות ({len(plan.moves)})")
    for old, new in plan.moves:
        kind = "תיקייה" if os.path.isdir(old) else "קובץ"
        out(f"  {rel(old)}  ->  {rel(new)}   ({kind})")
    out(f"== יעד קיים - מדלגים, לא דורסים ({len(plan.conflicts)})")
    for old, new in plan.conflicts:
        out(f"  {rel(old)}  X  {rel(new)}")
    out(f"== נתיבים מוחלטים שישוכתבו בקובצי JSON ({len(plan.rewrites)})")
    for path, where, old, new in plan.rewrites:
        out(f"  {rel(path)} {where}\n    {old}\n    -> {new}")
    out(f"== נשאר במקום - לא שייך לאף מיפוי ({len(plan.left)})")
    for path in plan.left:
        out(f"  {rel(path)}")
    out("== נשאר במקום בכוונה: " + ", ".join(sorted(STAY)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="העברת data/ לתיקיות לפי נושא (ברירת מחדל: הרצה יבשה)")
    parser.add_argument("--apply", action="store_true", help="לבצע בפועל, אחרי גיבוי. בלי הדגל - רק מדפיס מה היה קורה")
    parser.add_argument("--data-dir", default="", help="תיקיית data אחרת (ברירת מחדל: utils.shared.data_dir.DATA_DIR)")
    parser.add_argument("--stored-root", action="append", default=[],
                        help="נתיב data/ נוסף שמופיע בנתיבים שנשמרו - להרצה על עותק, כשה-JSON מצביע על המקור")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):   # עברית בקונסול של Windows (cp1255) ובצינור
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data_dir = os.path.abspath(args.data_dir or data_paths.DATA_DIR)
    plan = build_plan(data_dir, args.stored_root)
    print_plan(plan)
    if not args.apply:
        print("\nהרצה יבשה - שום דבר לא זז. להרצה בפועל: --apply")
        return 0
    if os.path.exists(os.path.join(data_dir, data_paths.RENDER_LOCK)):
        print("\nלא מזיז: render.lock קיים - רינדור כנראה רץ. לסגור את ClipForge ולנסות שוב.")
        return 2
    print(f"\nגיבוי: {backup(data_dir)}")
    moved, failed = apply_plan(plan)
    print(f"הועברו {moved} פריטים, שוכתבו {len(plan.rewrites) if not failed else 0} נתיבים; נכשלו {len(failed)}")
    for old, error in failed:
        print(f"  ! {old}: {error}")
    if failed:
        print("שום דבר לא הועבר: מה שזז הוחזר למקומו. ClipForge ממשיך לעבוד מהמבנה השטוח.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
