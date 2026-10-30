# tests/infra/test_ci_workflow.py
#
# סבב ייצוב (16.10.2026): ה-CI עולה כסף (ריפו פרטי, windows-latest נספר פי 2) - ולכן יש בו מסנן paths,
# concurrency ותקרת זמן. הטסט שומר שהחיסכון לא יאכל כיסוי: כל שינוי בקוד מריץ את ה-CI, push של
# תיעוד בלבד לא, ושני קובצי התיעוד שטסטים קוראים (README.md, docs/video_editor.md) כן.
# 21.10.2026 (מכסה חינמית): lint על ubuntu, ושלושת ה-jobs של Windows ב-PR וידנית - כל קוד נבדק במלואו ב-PR שלו.
import os
from tests import PROJECT_ROOT
import re
import subprocess

import yaml

ROOT = PROJECT_ROOT
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")


def _workflow():
    with open(WORKFLOW, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _glob(pattern):
    """תבנית של מסנן paths ב-GitHub: ** = כל תו (גם /), * = כל תו חוץ מ-/."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def _triggers(files, patterns):
    """כמו GitHub: לכל קובץ התבנית האחרונה שמתאימה קובעת; ריצה אם לפחות קובץ אחד בפנים."""
    rules = [(not p.startswith("!"), _glob(p.lstrip("!"))) for p in patterns]
    for path in files:
        included = False
        for positive, rx in rules:
            if rx.match(path):
                included = positive
        if included:
            return True
    return False


def test_every_job_has_a_time_limit_and_only_lint_leaves_windows():
    jobs = _workflow()["jobs"]
    assert set(jobs) == {"lint", "unit", "tk", "browser"}
    for name, job in jobs.items():
        assert job["runs-on"] == ("ubuntu-latest" if name == "lint" else "windows-latest"), name
        assert 10 <= job["timeout-minutes"] <= 60, name
    # mypy בלינוקס בודק כמו ב-Windows (בלי --platform: subprocess.CREATE_NO_WINDOW לא קיים)
    commands = [step.get("run", "") for step in jobs["lint"]["steps"]]
    assert "uv run mypy --platform win32" in commands


def test_windows_jobs_run_on_pull_requests_and_by_hand_but_not_on_push():
    # 21.10.2026 (מכסה חינמית): push ל-master = קוד שכבר עבר את ה-PR שלו; שם רק lint הזול
    workflow = _workflow()
    on = workflow[True]
    assert set(on["pull_request"]["branches"]) == {"main", "master"}
    for name in ("unit", "tk", "browser"):
        job = workflow["jobs"][name]
        assert job["if"] == "github.event_name != 'push'", name
        assert job["needs"] == "lint", name
    assert "if" not in workflow["jobs"]["lint"]


def test_a_newer_push_cancels_the_older_run_on_the_same_ref():
    concurrency = _workflow()["concurrency"]
    assert "${{ github.ref }}" in concurrency["group"] and concurrency["cancel-in-progress"] is True


def test_code_changes_always_run_and_docs_only_changes_do_not():
    on = _workflow()[True]  # YAML 1.1: המפתח on נקרא כ-True
    assert "workflow_dispatch" in on
    patterns = on["push"]["paths"]
    assert on["pull_request"]["paths"] == patterns and "paths-ignore" not in on["push"]
    # כל קובץ בגיט שאינו תיעוד מריץ את ה-CI
    listed = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True, encoding="utf-8", check=True)
    tracked = [line for line in listed.stdout.splitlines() if line]
    code = [path for path in tracked if not path.endswith(".md") and not path.startswith("docs/")]
    assert len(code) > 500
    missed = [path for path in code if not _triggers([path], patterns)]
    assert missed == []
    # תיעוד בלבד - לא; חוץ ממה שטסטים קוראים
    assert not _triggers(["AGENTS.md"], patterns)
    assert not _triggers(["docs/history/ROADMAP_2026-10-10.md", "docs/dataviz.md", "docs/web_ui.md"], patterns)
    assert _triggers(["README.md"], patterns) and _triggers(["docs/video_editor.md"], patterns)
    assert _triggers(["AGENTS.md", "src/utils/shared/db.py"], patterns)
