# dev/leak_check.py
#
# הריפו הזה מפותח ישירות, וכל מה שנדחף אליו ציבורי. לפני push: כל מה שהענף מוסיף מאז <base> (ברירת מחדל origin/main) נבדק
# מול דפוסי הסודות, הדפוסים האישיים הכלליים (תיקיית משתמש, אימייל) והדפוסים המקומיים של הבעלים.
# מה שמזהה את הבעלים לא כתוב כאן (הקובץ הזה ציבורי) - הוא ב-dev/leak_check.local.json, שלא במעקב:
#   {"personal_patterns": {"<שם>": "<regex>"}}
# נקרא מהעותק הזה או מהעותק הראשי כשרצים מ-worktree. בלעדיו הסריקה רצה עם הדפוסים הכלליים בלבד, ואומרת זאת.
#
# מה נסרק: שורות שנוספו (commits ושינויים שלא נשמרו), קבצים חדשים שלא במעקב, קבצים בינאריים שהשתנו (סודות בלבד), וגם
# הודעות ה-commit, המחברים וה-committers של הענף - כי בריפו ציבורי גם הם ציבוריים.
# 18.11.2026: עד 2.0.0 הריפו הזה יוצא מריפו פיתוח נפרד עם dev/export_public.py, והסריקה רצה שם. הכלי ההוא פרש, והדפוסים כאן.
#
#   uv run python dev/leak_check.py                 # מה שנוסף מאז origin/main
#   uv run python dev/leak_check.py --base v2.0.1   # מול tag או ענף אחר
#   uv run python dev/leak_check.py --all           # כל הקבצים שבמעקב
# קוד יציאה: 0 נקי, 2 נמצא סוד, 3 נמצא פרט אישי, 1 אין base כזה. הטקסט של סוד לא מודפס.
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMITS = "(commits)"   # ה"קובץ" של ממצא בהודעת commit או בשם ובכתובת של מחבר


LOCAL_PATTERNS_NAME = os.path.join("dev", "leak_check.local.json")

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
}
TEXT_LIMIT = 5 * 1024 * 1024


def local_patterns_file(repo=ROOT):
    """dev/leak_check.local.json בעותק הזה, או בעותק הראשי (מ-worktree: התיקייה של git-common-dir). None = אין."""
    candidates = [os.path.join(repo, LOCAL_PATTERNS_NAME)]
    common = subprocess.run(["git", "-C", repo, "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True).stdout.strip()
    if common:
        candidates.append(os.path.join(os.path.dirname(common), LOCAL_PATTERNS_NAME))
    return next((path for path in candidates if os.path.isfile(path)), None)


def personal_patterns(local_file=None):
    """PERSONAL_PATTERNS + הדפוסים מהקובץ המקומי (שמות הבעלים)."""
    patterns = dict(PERSONAL_PATTERNS)
    if local_file:
        with open(local_file, encoding="utf-8") as f:
            patterns.update(json.load(f).get("personal_patterns", {}))
    return patterns


def _allowed(rel, kind):
    return any(kind == k and (rel == p or (p.endswith("/") and rel.startswith(p))) for p, k in ALLOW)


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
        if _is_binary(path) or os.path.getsize(path) > TEXT_LIMIT:
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            for number, line in enumerate(f, 1):
                yield rel, number, line.rstrip("\r\n")


def file_lines(repo, files):
    """(נתיב, מספר שורה, טקסט) לכל שורה בקובצי הטקסט שברשימה."""
    for rel in files:
        path = os.path.join(repo, *rel.split("/"))
        if os.path.getsize(path) > TEXT_LIMIT:
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
    secret = {name: re.compile(pattern) for name, pattern in SECRET_PATTERNS.items()}
    personal = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in patterns.items()}
    findings = []
    for rel, number, line in lines:
        for kind, group in (("secret", secret), ("personal", personal)):
            for name, pattern in group.items():
                for match in pattern.finditer(line):
                    if not _allowed(rel, name):
                        findings.append((kind, rel, number, name, match.group(0)[:80]))
    return findings


def scan_binaries(repo, names):
    secret = {name: re.compile(pattern.encode("ascii")) for name, pattern in SECRET_PATTERNS.items()}
    findings = []
    for rel in names:
        path = os.path.join(repo, *rel.split("/"))
        if os.path.getsize(path) > TEXT_LIMIT:
            continue
        with open(path, "rb") as f:
            data = f.read()
        findings += [("secret", rel, 0, name, "") for name, pattern in secret.items()
                     if pattern.search(data) and not _allowed(rel, name)]
    return findings


def check(repo=ROOT, base="origin/main", everything=False):
    """הממצאים, או None כשאין base כזה. everything: כל הקבצים שבמעקב במקום מה שנוסף."""
    patterns = personal_patterns(local_patterns_file(repo))
    if everything:
        files = [rel for rel in _git(repo, "ls-files", "-z").stdout.split("\0")
                 if rel and os.path.isfile(os.path.join(repo, *rel.split("/")))]
        binaries = [rel for rel in files if _is_binary(os.path.join(repo, *rel.split("/")))]
        return scan_lines(file_lines(repo, sorted(set(files) - set(binaries))), patterns) + scan_binaries(repo, binaries)
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
    if not local_patterns_file(args.repo):
        print(f"No {LOCAL_PATTERNS_NAME}: scanning with the general patterns only (the owner's own patterns are in that file).")
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
