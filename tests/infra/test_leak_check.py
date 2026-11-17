# tests/infra/test_leak_check.py
#
# 17.11.2026: dev/leak_check.py - הסריקה שרצה לפני push מאז שהריפו מפותח ישירות: מה שהענף מוסיף מאז ה-base נבדק לסודות
# ולפרטים אישיים, כולל קבצים שלא במעקב, הודעות commit ומחברים. על ריפו git זמני - לא על הריפו האמיתי.
# הסוד והנתיב המזויפים מורכבים בזמן הריצה, כדי שהקובץ הזה עצמו לא ייתפס בסריקה.
import importlib.util
import json
import os
import subprocess

from tests import PROJECT_ROOT

_spec = importlib.util.spec_from_file_location("leak_check", os.path.join(PROJECT_ROOT, "dev", "leak_check.py"))
leak = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(leak)

FAKE_KEY = "AIza" + "B" * 35
FAKE_FOLDER = "C:" + "\\Users\\" + "somebody" + "\\Videos"


def _git(repo, *args, email="t@users.noreply.github.com"):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", f"user.email={email}", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def _write(repo, rel, text):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path):
    """ריפו עם commit אחד על main, שכבר יש בו סוד ונתיב אישי (ישנים - לא חלק ממה שהענף מוסיף), וענף עבודה ממנו."""
    repo = tmp_path / "repo"
    _write(repo, "src/app.py", "print('hi')\n")
    _write(repo, "src/old.py", f'KEY = "{FAKE_KEY}"\nHOME = r"{FAKE_FOLDER}"\n')
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    _git(repo, "switch", "-q", "-c", "feat/x")
    return repo


def _kinds(findings):
    return sorted((kind, rel, name) for kind, rel, _number, name, _text in findings)


def test_a_clean_branch_passes_and_what_was_there_before_is_not_reported(tmp_path, capsys):
    repo = _repo(tmp_path)
    _write(repo, "src/app.py", "print('hi')\nprint('more')\n")
    _git(repo, "commit", "-q", "-am", "more")
    assert leak.check(str(repo), "main") == []
    assert leak.main(["--repo", str(repo), "--base", "main"]) == 0
    assert "0 secret(s), 0 personal detail(s)" in capsys.readouterr().out


def test_a_secret_in_a_commit_is_found_with_its_line_and_never_printed(tmp_path, capsys):
    repo = _repo(tmp_path)
    _write(repo, "src/app.py", f"print('hi')\nprint('more')\nKEY = '{FAKE_KEY}'\n")
    _git(repo, "commit", "-q", "-am", "a key")
    assert [(f[0], f[1], f[2], f[3]) for f in leak.check(str(repo), "main")] == [("secret", "src/app.py", 3, "google-api-key")]
    assert leak.main(["--repo", str(repo), "--base", "main"]) == 2
    out = capsys.readouterr().out
    assert "src/app.py:3 [google-api-key] (hidden)" in out and FAKE_KEY not in out


def test_unsaved_changes_and_untracked_files_are_scanned_too(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "src/app.py", f"print('hi')\nFOLDER = r'{FAKE_FOLDER}'\n")   # שינוי שלא נשמר
    _write(repo, "notes/new.md", f"the key is {FAKE_KEY}\n")                   # קובץ שלא במעקב
    assert _kinds(leak.check(str(repo), "main")) == [("personal", "src/app.py", "windows-user-folder"),
                                                     ("secret", "notes/new.md", "google-api-key")]
    assert leak.main(["--repo", str(repo), "--base", "main"]) == 2   # סוד גובר על פרט אישי


def test_a_personal_detail_alone_exits_with_3(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "docs/guide.md", f"open {FAKE_FOLDER}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "guide")
    assert leak.main(["--repo", str(repo), "--base", "main"]) == 3


def test_commit_messages_and_authors_are_scanned(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "src/app.py", "print('hi')\nprint('more')\n")
    _git(repo, "commit", "-q", "-am", f"copied from {FAKE_FOLDER}", email="someone@private-mail.invalid")
    assert _kinds(leak.check(str(repo), "main")) == [("personal", leak.COMMITS, "email"),
                                                     ("personal", leak.COMMITS, "windows-user-folder")]


def test_the_owners_local_patterns_are_used(tmp_path):
    repo = _repo(tmp_path)
    _write(repo, "dev/leak_check.local.json", json.dumps({"personal_patterns": {"owner-name": r"\bzorblax\b"}}))
    _write(repo, "docs/guide.md", "written by Zorblax\n")
    findings = [f for f in leak.check(str(repo), "main") if f[1] == "docs/guide.md"]
    assert [(f[0], f[3], f[4]) for f in findings] == [("personal", "owner-name", "Zorblax")]


def test_a_changed_binary_file_is_scanned_for_secrets_only(tmp_path):
    repo = _repo(tmp_path)
    (repo / "assets").mkdir()
    (repo / "assets" / "blob.bin").write_bytes(b"\0\1\2" + FAKE_KEY.encode() + b"\0" + FAKE_FOLDER.encode())
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "a blob")
    assert _kinds(leak.check(str(repo), "main")) == [("secret", "assets/blob.bin", "google-api-key")]


def test_all_scans_every_tracked_file(tmp_path):
    repo = _repo(tmp_path)
    assert leak.check(str(repo), "main") == []
    assert _kinds(leak.check(str(repo), everything=True)) == [("personal", "src/old.py", "windows-user-folder"),
                                                              ("secret", "src/old.py", "google-api-key")]


def test_a_missing_base_is_an_error_not_a_pass(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert leak.check(str(repo), "origin/main") is None
    assert leak.main(["--repo", str(repo)]) == 1
    assert "Cannot compare with origin/main" in capsys.readouterr().out
