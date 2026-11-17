# dev/leak_check.py
#
# 17.11.2026: מ-2.0.1 הריפו הזה מפותח ישירות, בלי ריפו פיתוח נפרד ובלי שלב ייצוא. הסריקה שעצרה סודות ופרטים אישיים בזמן
# הייצוא (dev/export_public.py) רצה מעכשיו כאן, לפני push: כל מה שהענף מוסיף מאז <base> (ברירת מחדל origin/main) נבדק מול
# דפוסי הסודות, הדפוסים האישיים הכלליים (תיקיית משתמש, אימייל) והדפוסים המקומיים של הבעלים (dev/export_public.local.json -
# לא במעקב; נקרא מהעותק הזה או מהעותק הראשי כשרצים מ-worktree). בלי הקובץ המקומי הסריקה רצה עם הדפוסים הכלליים, ואומרת זאת.
#
# מה נסרק: שורות שנוספו (commits ושינויים שלא נשמרו), קבצים חדשים שלא במעקב, קבצים בינאריים שהשתנו (סודות בלבד), וגם
# הודעות ה-commit, המחברים וה-committers של הענף - כי בריפו ציבורי גם הם ציבוריים.
# הדפוסים ורשימת החריגים מוגדרים ב-dev/export_public.py, כדי שיהיה להם מקור אחד.
#
#   uv run python dev/leak_check.py                 # מה שנוסף מאז origin/main
#   uv run python dev/leak_check.py --base v2.0.0   # מול tag או ענף אחר
#   uv run python dev/leak_check.py --all           # כל הקבצים שבמעקב
# קוד יציאה: 0 נקי, 2 נמצא סוד, 3 נמצא פרט אישי, 1 אין base כזה. הטקסט של סוד לא מודפס.
import argparse
import importlib.util
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMITS = "(commits)"   # ה"קובץ" של ממצא בהודעת commit או בשם ובכתובת של מחבר


def _patterns_module():
    spec = importlib.util.spec_from_file_location("export_public", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                                "export_public.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exp = _patterns_module()


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def merge_base(repo, base):
    """ה-commit המשותף ל-base ול-HEAD, או None כשאין base כזה."""
    found = _git(repo, "merge-base", base, "HEAD", check=False)
    return found.stdout.strip() or None if found.returncode == 0 else None


def added_lines(repo, since):
    """(נתיב, מספר שורה, טקסט) לכל שורה שנוספה מאז since - כולל שינויים שלא נשמרו וקבצים חדשים שלא במעקב."""
    rel, number = None, 0
    for line in _git(repo, "diff", "--unified=0", "--no-color", "--no-ext-diff", since).stdout.splitlines():
        if line.startswith("+++ "):
            rel = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            match = re.match(r"@@ -\S+ \+(\d+)", line)
            number = int(match.group(1)) if match else 0
        elif line.startswith("+") and rel:
            yield rel, number, line[1:]
            number += 1
    for rel in _untracked(repo):
        path = os.path.join(repo, *rel.split("/"))
        if _is_binary(path) or os.path.getsize(path) > exp.TEXT_LIMIT:
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            for number, line in enumerate(f, 1):
                yield rel, number, line.rstrip("\r\n")


def _untracked(repo):
    return [rel for rel in _git(repo, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0") if rel]


def _is_binary(path):
    with open(path, "rb") as f:
        return b"\0" in f.read(8192)


def changed_binaries(repo, since):
    """קבצים בינאריים שנוספו או השתנו מאז since (במעקב ולא במעקב) ועדיין קיימים."""
    names = [line.split("\t", 2)[2] for line in _git(repo, "diff", "--numstat", "--no-renames", since).stdout.splitlines()
             if line.startswith("-\t-\t")]
    names += [rel for rel in _untracked(repo) if _is_binary(os.path.join(repo, *rel.split("/")))]
    return [rel for rel in names if os.path.isfile(os.path.join(repo, *rel.split("/")))]


def commit_lines(repo, since):
    """שורות ההודעות, המחברים וה-committers של ה-commits מאז since."""
    log = _git(repo, "log", "--format=%an <%ae>%n%cn <%ce>%n%B", f"{since}..HEAD").stdout
    return [(COMMITS, number, line) for number, line in enumerate(dict.fromkeys(log.splitlines()), 1) if line.strip()]


def scan_lines(lines, patterns):
    """(סוג, נתיב, שורה, דפוס, טקסט) לכל ממצא בשורות; סוג: secret / personal."""
    secret = {name: re.compile(pattern) for name, pattern in exp.SECRET_PATTERNS.items()}
    personal = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in patterns.items()}
    findings = []
    for rel, number, line in lines:
        for kind, group in (("secret", secret), ("personal", personal)):
            for name, pattern in group.items():
                for match in pattern.finditer(line):
                    if not exp._allowed(rel, name):
                        findings.append((kind, rel, number, name, match.group(0)[:80]))
    return findings


def scan_binaries(repo, names):
    secret = {name: re.compile(pattern.encode("ascii")) for name, pattern in exp.SECRET_PATTERNS.items()}
    findings = []
    for rel in names:
        path = os.path.join(repo, *rel.split("/"))
        if os.path.getsize(path) > exp.TEXT_LIMIT:
            continue
        with open(path, "rb") as f:
            data = f.read()
        findings += [("secret", rel, 0, name, "") for name, pattern in secret.items()
                     if pattern.search(data) and not exp._allowed(rel, name)]
    return findings


def check(repo=ROOT, base="origin/main", everything=False):
    """הממצאים, או None כשאין base כזה. everything: כל הקבצים שבמעקב במקום מה שנוסף."""
    patterns = exp.personal_patterns(exp.local_patterns_file(repo))
    if everything:
        files = [rel for rel in _git(repo, "ls-files", "-z").stdout.split("\0")
                 if rel and os.path.isfile(os.path.join(repo, *rel.split("/")))]
        return [finding for finding in exp.scan(repo, files, patterns) if finding[0] != "dangling"]
    since = merge_base(repo, base)
    if since is None:
        return None
    return (scan_lines(added_lines(repo, since), patterns) + scan_binaries(repo, changed_binaries(repo, since))
            + scan_lines(commit_lines(repo, since), patterns))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan what this branch adds for secrets and personal details, before a push")
    parser.add_argument("--base", default="origin/main", help="compare with this ref (default: origin/main)")
    parser.add_argument("--all", action="store_true", help="scan every tracked file instead of what the branch adds")
    parser.add_argument("--repo", default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not exp.local_patterns_file(args.repo):
        print(f"No {exp.LOCAL_PATTERNS_NAME}: scanning with the general patterns only (the owner's own patterns are in that file).")
    findings = check(args.repo, args.base, args.all)
    if findings is None:
        print(f"Cannot compare with {args.base}: no such ref here. Run 'git fetch', or pass --base.")
        return 1
    for kind, rel, number, name, text in findings:
        # את הסוד עצמו לא מדפיסים - המיקום ושם הדפוס מספיקים כדי למצוא אותו
        print(f"{kind}: {rel}:{number} [{name}] " + ("(hidden)" if kind == "secret" else text))
    secrets = sum(1 for finding in findings if finding[0] == "secret")
    scope = "all tracked files" if args.all else f"what was added since {args.base}"
    print(f"Scanned {scope}: {secrets} secret(s), {len(findings) - secrets} personal detail(s).")
    return 2 if secrets else 3 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
