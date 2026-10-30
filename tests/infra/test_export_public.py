# tests/infra/test_export_public.py
#
# dev/export_public.py: עותק נקי לריפו ציבורי - רק קבצים שבמעקב, בלי קבצי העבודה הפנימיים, commit אחד, ובלי commit כשהסריקה
# מוצאת סוד או פרט אישי. על ריפו git זמני - לא על הריפו האמיתי.
import importlib.util
import json
import os
import subprocess

from tests import PROJECT_ROOT

_spec = importlib.util.spec_from_file_location("export_public", os.path.join(PROJECT_ROOT, "dev", "export_public.py"))
exp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exp)


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args],
                          capture_output=True, text=True, encoding="utf-8", check=True).stdout


def _repo(tmp_path, extra=None):
    repo = tmp_path / "src_repo"
    files = {
        "README.md": "# ClipForge\n", "pyproject.toml": '[project]\nname = "clipforge"\nversion = "9.9.9"\n',
        "src/app.py": "print('hi')\n", "AGENTS.md": "internal\n", "docs/guide.md": "guide\n",
        "docs/handoff/2026-10-30-x.md": "log\n", "docs/history/old.md": "old\n", **(extra or {}),
    }
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "first")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "second - history that must not travel")
    (repo / "untracked.txt").write_text("not in git\n", encoding="utf-8")
    return repo


def _export(repo, dest, *extra):
    return exp.main(["--repo", str(repo), "--ref", "HEAD", "--dest", str(dest), *extra])


def test_a_clean_tree_exports_with_one_commit_and_without_the_internal_files(tmp_path):
    repo, dest = _repo(tmp_path), tmp_path / "public"
    assert _export(repo, dest) == 0
    files = sorted(str(p.relative_to(dest)).replace(os.sep, "/") for p in dest.rglob("*") if p.is_file() and ".git" not in p.parts)
    assert files == ["README.md", "docs/guide.md", "pyproject.toml", "src/app.py"]
    log = subprocess.run(["git", "-C", str(dest), "log", "--format=%an <%ae>|%s"], capture_output=True, text=True, check=True)
    assert log.stdout.strip().splitlines() == ["DrummingBird1 <DrummingBird1@users.noreply.github.com>|ClipForge 9.9.9"]
    assert subprocess.run(["git", "-C", str(dest), "remote"], capture_output=True, text=True).stdout == ""
    assert (repo / "AGENTS.md").is_file() and (repo / "docs" / "handoff").is_dir()   # המקור לא נגע


def test_a_secret_means_no_commit(tmp_path):
    repo = _repo(tmp_path, {"src/keys.py": 'KEY = "AIza' + "B" * 35 + '"\n'})
    dest = tmp_path / "public"
    assert _export(repo, dest) == 2
    assert not (dest / ".git").exists()


def test_a_personal_path_needs_an_explicit_ok(tmp_path, capsys):
    repo = _repo(tmp_path, {"src/paths.py": 'ROOT = r"C:\\Users\\someone\\clipforge"\n'})
    assert _export(repo, tmp_path / "public") == 3
    assert "src/paths.py:1 [windows-user-folder]" in capsys.readouterr().out
    assert not (tmp_path / "public" / ".git").exists()
    assert _export(repo, tmp_path / "public2", "--allow-personal") == 0


def test_an_existing_folder_with_files_is_left_alone(tmp_path):
    repo, dest = _repo(tmp_path), tmp_path / "public"
    dest.mkdir()
    (dest / "mine.txt").write_text("keep\n", encoding="utf-8")
    assert _export(repo, dest) == 1
    assert sorted(p.name for p in dest.iterdir()) == ["mine.txt"]


def test_links_to_files_that_stay_behind_are_reported_but_do_not_block(tmp_path, capsys):
    repo = _repo(tmp_path, {"docs/guide.md": "see AGENTS.md for the rules\n"})
    assert _export(repo, tmp_path / "public") == 0
    assert "docs/guide.md:1 [excluded-file] AGENTS.md" in capsys.readouterr().out


def test_owner_names_come_from_a_local_file_that_stays_out_of_the_export(tmp_path, capsys):
    """30.10.2026: שמות הבעלים לא כתובים בקוד הציבורי - הם ב-dev/export_public.local.json, שלא במעקב."""
    repo = _repo(tmp_path, {"src/credits.py": "# made by Zorro\n"})
    assert _export(repo, tmp_path / "without") == 0
    assert "אין dev" in capsys.readouterr().out.replace(os.sep, "/")
    (repo / "dev").mkdir(exist_ok=True)
    (repo / "dev" / "export_public.local.json").write_text('{"personal_patterns": {"owner-name": "zorro"}}', encoding="utf-8")
    assert _export(repo, tmp_path / "with") == 3
    assert "[owner-name] Zorro" in capsys.readouterr().out
    assert not (tmp_path / "with" / "dev" / "export_public.local.json").exists()


def _local_rewrites(repo, rewrites):
    (repo / "dev").mkdir(exist_ok=True)
    (repo / "dev" / "export_public.local.json").write_text(json.dumps({"public_rewrites": rewrites}), encoding="utf-8")


def test_private_files_stay_behind_and_public_labels_come_from_the_local_file(tmp_path):
    """ההחלפות לעותק הציבורי בקובץ המקומי (public_rewrites), לא בקוד; קבצים פרטיים ב-EXCLUDE."""
    repo = _repo(tmp_path, {"my_scripts/steam/steam_check.py": "x\n", "my_scripts/tools/check_pos.py": "x\n",
                            "docs/github-about.md": "draft\n", "docs/web_ui.md": "effects (Airhorn, Internal Name, Game Over)\n",
                            ".github/dependabot.yml": "version: 2\n", ".github/workflows/ci.yml": "name: CI\n"})
    _local_rewrites(repo, {"docs/web_ui.md": [["Internal Name", "Public Name"]]})
    dest = tmp_path / "public"
    assert _export(repo, dest) == 0
    assert not (dest / "my_scripts").exists() and not (dest / "docs" / "github-about.md").exists()
    assert not (dest / ".github" / "dependabot.yml").exists() and (dest / ".github" / "workflows" / "ci.yml").exists()
    assert (dest / "docs" / "web_ui.md").read_text(encoding="utf-8") == "effects (Airhorn, Public Name, Game Over)\n"


def test_a_rewrite_that_no_longer_matches_stops_the_export(tmp_path):
    import pytest
    repo = _repo(tmp_path, {"docs/web_ui.md": "the label was renamed\n"})
    _local_rewrites(repo, {"docs/web_ui.md": [["Internal Name", "Public Name"]]})
    with pytest.raises(ValueError, match="public_rewrites"):
        exp.extract("HEAD", str(tmp_path / "public"), str(repo), exp.public_rewrites(exp.local_patterns_file(str(repo))))


# --- 30.10.2026: --update - הגרסה הבאה כ-commit חדש מעל ה-main של clone קיים, בלי force-push ---

def _commit_count(repo):
    return int(_git(repo, "rev-list", "--count", "HEAD").strip())


def _published(tmp_path):
    """ריפו פרטי + הייצוא הראשון שלו (כמו הריפו הציבורי אחרי ה-push הראשון), עם dist/ שב-.gitignore."""
    repo = _repo(tmp_path, {".gitignore": "dist/\n", "docs/old.md": "old page\n"})
    clone = tmp_path / "public"
    assert _export(repo, clone) == 0
    (clone / "dist").mkdir()
    (clone / "dist" / "ClipForge-9.9.9-win64.zip").write_bytes(b"zip")
    return repo, clone


def test_update_adds_changes_and_deletes_files_in_one_new_commit(tmp_path):
    repo, clone = _published(tmp_path)
    first = _git(clone, "rev-parse", "HEAD").strip()
    (repo / "src" / "new.py").write_text("print('new')\n", encoding="utf-8")
    (repo / "README.md").write_text("# ClipForge 2\n", encoding="utf-8")
    (repo / "docs" / "old.md").unlink()
    (repo / "pyproject.toml").write_text('[project]\nname = "clipforge"\nversion = "9.9.10"\n', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "private message that must not travel")

    assert _export(repo, tmp_path / "unused", "--update", str(clone)) == 0
    assert (clone / "src" / "new.py").read_text(encoding="utf-8") == "print('new')\n"
    assert (clone / "README.md").read_text(encoding="utf-8") == "# ClipForge 2\n"
    assert not (clone / "docs" / "old.md").exists() and (clone / "docs" / "guide.md").exists()
    assert (clone / "dist" / "ClipForge-9.9.9-win64.zip").read_bytes() == b"zip"   # dist/ ב-.gitignore - לא נגעו
    assert _commit_count(clone) == 2 and _git(clone, "rev-parse", "HEAD~1").strip() == first   # מעל ה-main הקיים
    log = _git(clone, "log", "-1", "--format=%an <%ae>|%B")
    source = _git(repo, "rev-parse", "--short", "HEAD").strip()
    previous = _git(repo, "rev-parse", "--short", "HEAD~1").strip()   # ה-commit שיוצא בפעם הראשונה
    assert log.startswith("DrummingBird1 <DrummingBird1@users.noreply.github.com>|ClipForge 9.9.10\n")
    assert f"Source: {previous}..{source}" in log and "private message" not in log
    assert _git(clone, "status", "--porcelain") == ""


def test_update_without_changes_makes_no_commit(tmp_path, capsys):
    repo, clone = _published(tmp_path)
    assert _export(repo, tmp_path / "unused", "--update", str(clone)) == 0
    assert _commit_count(clone) == 1
    assert "אין commit" in capsys.readouterr().out


def test_a_personal_finding_stops_the_update_and_leaves_the_clone_as_it_was(tmp_path):
    repo, clone = _published(tmp_path)
    (repo / "src" / "paths.py").write_text('ROOT = "C:\\Users\\someone\\clips"\n', encoding="utf-8")
    (repo / "README.md").write_text("# changed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "a personal path")
    assert _export(repo, tmp_path / "unused", "--update", str(clone)) == 3
    assert _commit_count(clone) == 1 and _git(clone, "status", "--porcelain") == ""
    assert (clone / "README.md").read_text(encoding="utf-8") == "# ClipForge\n" and not (clone / "src" / "paths.py").exists()


def test_update_refuses_a_clone_with_unsaved_work(tmp_path, capsys):
    repo, clone = _published(tmp_path)
    (clone / "notes.txt").write_text("mine\n", encoding="utf-8")
    assert _export(repo, tmp_path / "unused", "--update", str(clone)) == 1
    assert (clone / "notes.txt").exists() and _commit_count(clone) == 1
    assert _export(repo, tmp_path / "unused", "--update", str(tmp_path / "not_a_repo")) == 1
