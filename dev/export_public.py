# dev/export_public.py
#
# 30.10.2026 (הכנה להפצה ציבורית, פריט 5): עותק נקי של הריפו לתיקייה מקומית, עם commit ראשון אחד - בלי היסטוריה, בלי קבצי
# העבודה הפנימיים (AGENTS.md, ‏docs/handoff/, ‏docs/history/, ‏.claude/, ‏HANDOFF.local.md), ואחרי סריקת סודות ונתיבים אישיים.
# לא יוצר ריפו ב-GitHub ולא מוסיף remote - את זה המשתמש עושה בעצמו, אחרי שראה את התוצאה.
#
# מה נכנס: בדיוק הקבצים שבמעקב ב-<ref> (git archive) - שום קובץ לא-במעקב, שום data/ אמיתי. לא מוחק כלום: מה שלא נכנס מסונן
# בזמן החילוץ, ותיקיית יעד שכבר קיימת עם תוכן = מסרב.
# הסריקה: סוד (טוקן, מפתח, webhook) = אין commit, קוד יציאה 2. ממצא אישי (נתיב של המחשב הזה, אימייל, שם) = אין commit, קוד 3,
# אלא אם --allow-personal. קישור לקובץ שלא יוצא = אזהרה בלבד.
# 30.10.2026: מה שמזהה את הבעלים לא כתוב כאן (הקובץ הזה יוצא לציבור) - הוא ב-dev/export_public.local.json, שלא במעקב:
#   {"personal_patterns": {"<שם>": "<regex>"}, "public_rewrites": {"<קובץ>": [["<טקסט>", "<תחליף בעותק הציבורי>"]]}}
# נקרא מהעותק הזה או מהעותק הראשי של הריפו (worktree). בלעדיו הסריקה רצה עם הדפוסים הכלליים בלבד ובלי החלפות, ומודיעה על כך.
# גם: קבצים שנשארים רק בריפו הפרטי (EXCLUDE).
#
# 30.10.2026: --update <clone של הריפו הציבורי> - הגרסה הבאה כ-commit חדש מעל main הקיים, בלי force-push. הקבצים מחולצים
# ונסרקים בתיקייה זמנית; רק אם הסריקה נקייה הם נכנסים ל-clone: מה שבמעקב מוחלף, מה שכבר לא מיוצא נמחק, ו-.git, ‏dist/ וכל
# מה שב-.gitignore לא נוגעים בהם. clone עם שינויים לא שמורים = מסרב (קוד 1). אין הבדל = אין commit. לא דוחף - push, ‏tag
# ו-Release הם צעד ידני (docs/development.md, "Releasing a new version"). ה-commit: "ClipForge <גרסה>" ו-"Source: <hash מקוצר>"
# של הריפו הפרטי (או <קודם>..<חדש>) - בלי הודעות commit פרטיות.
#
#   uv run python dev/export_public.py                          # origin/master -> clipforge-public, ליד תיקיית הריפו
#   uv run python dev/export_public.py --ref HEAD --dest <תיקייה>
#   uv run python dev/export_public.py --update ..\clipforge-app   # הגרסה הבאה, ל-clone קיים של הריפו הציבורי
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEST = os.path.join(os.path.dirname(ROOT), "clipforge-public")

# קבצי העבודה הפנימיים - לא יוצאים (קובץ, או תיקייה עם "/" בסוף)
EXCLUDE = ("AGENTS.md", "CLAUDE.md", "HANDOFF.local.md", "docs/handoff/", "docs/history/", ".claude/", ".cursor/",
           "docs/github-about.md",   # טיוטה פנימית להגדרות הריפו הציבורי
           # הקוד מגיע לריפו הציבורי רק מהייצוא - PRs של Dependabot שם לא ימוזגו; עדכוני ספריות נעשים בריפו הפרטי
           ".github/dependabot.yml",
           # כלי פיתוח פרטיים (הסתרת משחקי Steam בלי הישגים, מאתר מיקום עכבר) - נשארים בריפו הפרטי
           "my_scripts/steam/steam_check.py", "my_scripts/tools/check_pos.py")
LOCAL_PATTERNS_NAME = os.path.join("dev", "export_public.local.json")

SECRET_PATTERNS = {
    "discord-token": r"\b[MN][A-Za-z\d]{23,27}\.[\w-]{6}\.[\w-]{27,}",
    "discord-webhook": r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}",
    "google-api-key": r"AIza[0-9A-Za-z_-]{35}",
    "google-oauth-secret": r"GOCSPX-[\w-]{20,}",
    "google-refresh-token": r"\b1//0[\w-]{40,}",
    "github-token": r"\bgh[pousr]_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}",
    "aws-key-id": r"\bAKIA[0-9A-Z]{16}\b",
    "slack-token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    "openai-or-anthropic-key": r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}",
    "private-key": r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----",
}
PERSONAL_PATTERNS = {
    "windows-user-folder": r"[A-Za-z]:[\\/]+Users[\\/]+(?!<|\{|%|\$|Public\b|Default\b|you\b|me\b|USER(?:NAME)?\b)[\w.-]{2,}",
    "this-machine-ai-shelf": r"\b[A-Za-z]:[\\/]+AI[\\/]",
    "email": r"[\w.+-]+@(?!example\.(?:com|org)|users\.noreply\.github\.com|anthropic\.com\b)[\w-]+\.[A-Za-z]{2,}",
}
# ממצאים ידועים שאינם סוד אמיתי: (נתיב יחסי, שם הדפוס). נתיב שמסתיים ב-"/" = כל התיקייה.
ALLOW = {
    ("tests/", "email"),   # כתובות מזויפות בטסטים (user@host)
    ("tests/dataviz/test_dataviz_notify.py", "discord-webhook"),   # webhook מזויף (abcdef...) - בודק את ההסתרה שלו
    ("tests/dataviz/test_web_app_dataviz_notify_browser.py", "discord-webhook"),
    ("tests/infra/test_export_public.py", "windows-user-folder"),   # הנתיב המזויף שהטסט של הסריקה מחפש
}
TEXT_LIMIT = 5 * 1024 * 1024


def local_patterns_file(repo=ROOT):
    """dev/export_public.local.json בעותק הזה, או בעותק הראשי (מ-worktree: התיקייה של git-common-dir). None = אין."""
    candidates = [os.path.join(repo, LOCAL_PATTERNS_NAME)]
    common = subprocess.run(["git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True).stdout.strip()
    if common:
        candidates.append(os.path.join(os.path.dirname(common), LOCAL_PATTERNS_NAME))
    return next((path for path in candidates if os.path.isfile(path)), None)


def public_rewrites(local_file=None):
    """בעותק הציבורי בלבד: {קובץ: [(טקסט, תחליף)]}, מהקובץ המקומי. כל החלפה חייבת להימצא - אחרת הייצוא נכשל, כדי שלא
    תישכח בשקט כשהטקסט משתנה במקור."""
    if not local_file:
        return {}
    with open(local_file, encoding="utf-8") as f:
        rewrites = json.load(f).get("public_rewrites", {})
    return {path: [tuple(pair) for pair in pairs] for path, pairs in rewrites.items()}


def personal_patterns(local_file=None):
    """PERSONAL_PATTERNS + הדפוסים מהקובץ המקומי (שמות הבעלים)."""
    patterns = dict(PERSONAL_PATTERNS)
    if local_file:
        with open(local_file, encoding="utf-8") as f:
            patterns.update(json.load(f).get("personal_patterns", {}))
    return patterns


def _excluded(rel):
    rel = rel.replace("\\", "/")
    return any(rel == e or (e.endswith("/") and rel.startswith(e)) for e in EXCLUDE)


def _allowed(rel, kind):
    return any(kind == k and (rel == p or (p.endswith("/") and rel.startswith(p))) for p, k in ALLOW)


def extract(ref, dest, repo=ROOT, rewrites=None):
    """הקבצים שבמעקב ב-ref, בלי EXCLUDE, לתוך dest. מחזיר את הנתיבים היחסיים שנכתבו."""
    archive = subprocess.run(["git", "-C", repo, "archive", "--format=tar", ref], capture_output=True, check=True).stdout
    written = []
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            if not member.isfile() or _excluded(member.name):
                continue
            target = os.path.normpath(os.path.join(dest, member.name))
            if not target.startswith(os.path.normpath(dest) + os.sep):
                raise ValueError(f"נתיב מחוץ ליעד בארכיון: {member.name}")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with tar.extractfile(member) as src:
                data = src.read()
            for old, new in (rewrites or {}).get(member.name, ()):
                if old.encode("utf-8") not in data:
                    raise ValueError(f"public_rewrites: לא נמצא {old!r} ב-{member.name} - לעדכן את ההחלפה בקובץ המקומי")
                data = data.replace(old.encode("utf-8"), new.encode("utf-8"))
            with open(target, "wb") as out:
                out.write(data)
            written.append(member.name)
    return written


def scan(dest, files, patterns=None):
    """(סוג, נתיב, שורה, דפוס, טקסט) לכל ממצא. סוג: secret / personal / dangling. patterns: הדפוסים האישיים (ברירת מחדל -
    PERSONAL_PATTERNS בלבד)."""
    secret = {k: re.compile(v) for k, v in SECRET_PATTERNS.items()}
    personal = {k: re.compile(v, re.IGNORECASE) for k, v in (patterns or PERSONAL_PATTERNS).items()}
    dangling = re.compile(r"(?<![\w/.-])(" + "|".join(re.escape(e.rstrip("/")) for e in EXCLUDE) + r")(?![\w.-])")
    findings = []
    for rel in files:
        path = os.path.join(dest, rel)
        if os.path.getsize(path) > TEXT_LIMIT:
            continue
        with open(path, "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8", errors="ignore")
        binary = b"\0" in raw[:8192]
        for lineno, line in enumerate(text.splitlines(), 1):
            for kind, patterns in (("secret", secret), ("personal", personal)):
                if binary and kind == "personal":
                    continue
                for name, pattern in patterns.items():
                    for m in pattern.finditer(line):
                        if not _allowed(rel, name):
                            findings.append((kind, rel, lineno, name, m.group(0)[:80]))
            if not binary and dangling.search(line):
                findings.append(("dangling", rel, lineno, "excluded-file", dangling.search(line).group(0)))
    return findings


def _git_out(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def commit(dest, version, author, source=None, init=True):
    """commit אחד ב-dest: "ClipForge <גרסה>", ו-"Source: <hash>" של הריפו הפרטי. init=False - מעל ה-main הקיים (--update)."""
    def git(*args):
        subprocess.run(["git", "-C", dest, *args], check=True, capture_output=True)
    if init:
        git("init", "-q", "-b", "main")
    git("add", "-A")
    name, _, email = author.partition(" <")
    message = f"ClipForge {version}" + (f"\n\nSource: {source}" if source else "")
    git("-c", f"user.name={name}", "-c", f"user.email={email.rstrip('>')}", "commit", "-q", "-m", message)


def _source(ref, repo):
    return _git_out(repo, "rev-parse", "--short", ref).strip()


def _previous_source(clone):
    """ה-hash הפרטי של הייצוא האחרון ב-clone (שורת "Source:"), או None."""
    match = re.search(r"^Source: (?:\w+\.\.)?(\w+)\s*$", _git_out(clone, "log", "-1", "--format=%B"), re.M)
    return match.group(1) if match else None


def check_clone(clone):
    """סיבה לסרב, או None: לא תיקיית שורש של ריפו git, בלי commit, או עם שינויים שלא נשמרו (כולל קבצים לא-במעקב)."""
    try:
        top = _git_out(clone, "rev-parse", "--show-toplevel").strip()
        _git_out(clone, "rev-parse", "--verify", "HEAD")
    except (subprocess.CalledProcessError, OSError):
        return f"{clone} הוא לא clone של git עם commit (צריך clone של הריפו הציבורי)"
    if os.path.normcase(os.path.abspath(top)) != os.path.normcase(os.path.abspath(clone)):
        return f"{clone} הוא לא תיקיית השורש של הריפו ({top})"
    if _git_out(clone, "status", "--porcelain"):
        return f"ב-{clone} יש שינויים שלא נשמרו או קבצים לא-במעקב - לנקות או לעשות להם commit לפני העדכון"
    return None


def sync_into(clone, staged, files):
    """הקבצים המיוצאים (staged) -> clone: מוחלפים ונוספים, ומה שבמעקב ב-clone ולא יוצא עוד - נמחק (עם תיקיות שהתרוקנו).
    .git וקבצים שלא במעקב (dist/, מה שב-.gitignore) לא נוגעים בהם. מחזיר את הנתיבים שנמחקו."""
    tracked = {rel for rel in _git_out(clone, "ls-files", "-z").split("\0") if rel}
    removed = sorted(tracked - set(files))
    for rel in removed:
        path = os.path.join(clone, *rel.split("/"))
        if os.path.isfile(path):
            os.remove(path)  # safe: a file git tracks in the public clone that the new export no longer has (git keeps it)
        parent = os.path.dirname(path)
        while os.path.normcase(parent) != os.path.normcase(clone) and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
            parent = os.path.dirname(parent)
    for rel in files:
        target = os.path.join(clone, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(staged, *rel.split("/")), target)
    return removed


def _version(dest):
    match = re.search(r'^version = "([^"]+)"', open(os.path.join(dest, "pyproject.toml"), encoding="utf-8").read(), re.M)
    return match.group(1) if match else "?"


def _report(files, findings, ref, where):
    counts = {k: sum(1 for f in findings if f[0] == k) for k in ("secret", "personal", "dangling")}
    print(f"יוצאו {len(files)} קבצים מ-{ref} אל {where}")
    for kind, title in (("secret", "סודות"), ("personal", "נתיבים ופרטים אישיים"), ("dangling", "קישורים לקבצים שלא יצאו (אזהרה)")):
        print(f"== {title}: {counts[kind]}")
        for _k, rel, lineno, name, text in (f for f in findings if f[0] == kind):
            print(f"  {rel}:{lineno} [{name}] {text}")
    return counts


def update(args, patterns, rewrites=None):
    """--update: הגרסה הבאה כ-commit חדש ב-clone קיים של הריפו הציבורי. קודי היציאה כמו בייצוא הרגיל."""
    clone = os.path.abspath(args.update)
    problem = check_clone(clone)
    if problem:
        print(f"לא מעדכן: {problem}.")
        return 1
    with tempfile.TemporaryDirectory(prefix="clipforge_export_") as staged:
        files = extract(args.ref, staged, args.repo, rewrites)
        counts = _report(files, scan(staged, files, patterns), args.ref, f"{clone} (דרך תיקייה זמנית)")
        if counts["secret"]:
            print("\nלא עודכן: נמצאו סודות. ה-clone לא השתנה - לתקן במקור ולהריץ שוב.")
            return 2
        if counts["personal"] and not args.allow_personal:
            print("\nלא עודכן: נמצאו פרטים אישיים. ה-clone לא השתנה - לתקן במקור (או --allow-personal אחרי שבדקת) ולהריץ שוב.")
            return 3
        removed = sync_into(clone, staged, files)
    if not _git_out(clone, "status", "--porcelain"):
        print(f"\nאין שינוי מול ה-commit האחרון ב-{clone} - אין commit.")
        return 0
    source, previous = _source(args.ref, args.repo), _previous_source(clone)
    commit(clone, _version(clone), args.author, f"{previous}..{source}" if previous and previous != source else source, init=False)
    print(f"\ncommit חדש ב-{clone} ({len(removed)} קבצים נמחקו), בלי push. הצעד הבא: לבדוק את ה-commit, git push, ואז tag v<גרסה>.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="ייצוא עותק נקי של ClipForge לריפו ציבורי מקומי (commit אחד, בלי היסטוריה)")
    parser.add_argument("--ref", default="origin/master", help="מאיזה commit (ברירת מחדל: origin/master)")
    parser.add_argument("--dest", default=DEFAULT_DEST, help=f"תיקיית היעד (ברירת מחדל: {DEFAULT_DEST})")
    parser.add_argument("--author", default="DrummingBird1 <DrummingBird1@users.noreply.github.com>",
                        help="שם <אימייל> ל-commit. ברירת המחדל היא כתובת noreply של GitHub, לא האימייל הפרטי מ-git config")
    parser.add_argument("--allow-personal", action="store_true", help="לעשות commit גם כשנמצאו ממצאים אישיים (לא סודות)")
    parser.add_argument("--update", metavar="CLONE", help="clone קיים של הריפו הציבורי: commit חדש מעל main במקום ריפו חדש")
    parser.add_argument("--repo", default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    local_file = local_patterns_file(args.repo)
    print(f"דפוסים אישיים מקומיים: {local_file}" if local_file else
          f"אין {LOCAL_PATTERNS_NAME} - הסריקה בלי הדפוסים המקומיים ובלי החלפות (רק הדפוסים הכלליים)")
    if args.update:
        return update(args, personal_patterns(local_file), public_rewrites(local_file))
    dest = os.path.abspath(args.dest)
    if os.path.isdir(dest) and os.listdir(dest):
        print(f"לא מייצא: {dest} כבר קיים ויש בו קבצים. לבחור --dest אחר, או --update ל-clone קיים של הריפו הציבורי.")
        return 1
    os.makedirs(dest, exist_ok=True)
    files = extract(args.ref, dest, args.repo, public_rewrites(local_file))
    counts = _report(files, scan(dest, files, personal_patterns(local_file)), args.ref, dest)
    if counts["secret"]:
        print("\nאין commit: נמצאו סודות. לתקן במקור, ואז לייצא מחדש לתיקייה ריקה.")
        return 2
    if counts["personal"] and not args.allow_personal:
        print("\nאין commit: נמצאו פרטים אישיים. לתקן במקור (או --allow-personal אחרי שבדקת שזה בסדר), ולייצא מחדש.")
        return 3
    commit(dest, _version(dest), args.author, _source(args.ref, args.repo))
    print(f"\ncommit ראשון אחד ב-{dest} (ענף main), בלי remote. הצעד הבא - של המשתמש: ליצור ריפו ב-GitHub ולדחוף.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
