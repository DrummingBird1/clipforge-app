# tests/infra/test_release_workflow.py
#
# 30.10.2026: ‏.github/workflows/release.yml - רק tag בצורת v* בונה את החבילה הניידת, ffmpeg נעול ל-hash, וה-tag חייב להתאים
# לגרסה. בלי להריץ את ה-workflow.
import os
import re

import yaml

from tests import PROJECT_ROOT

WORKFLOW = os.path.join(PROJECT_ROOT, ".github", "workflows", "release.yml")


def _workflow():
    with open(WORKFLOW, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_only_a_version_tag_runs_it():
    wf = _workflow()
    triggers = wf.get("on", wf.get(True))   # yaml קורא את המפתח on כ-True
    assert triggers == {"push": {"tags": ["v*"]}}
    assert wf["permissions"] == {"contents": "write"}
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_it_builds_on_windows_with_a_time_limit_and_checks_the_version_first():
    job = _workflow()["jobs"]["portable"]
    assert job["runs-on"] == "windows-latest" and 0 < job["timeout-minutes"] <= 60
    names = [step.get("name", step.get("uses", "")) for step in job["steps"]]
    assert names.index("The tag matches the app version") < names.index("Build the portable package")
    build = next(s for s in job["steps"] if s.get("name") == "Build the portable package")
    assert build["run"].startswith("python dev/build_portable.py --ffmpeg ")
    assert "uv run" not in build["run"]   # בלי .venv עם קבוצת dev


def test_ffmpeg_is_a_pinned_gpl_build_with_libx264():
    env = _workflow()["env"]
    assert re.fullmatch(r"[0-9a-f]{64}", env["FFMPEG_SHA256"])
    assert "essentials_build" in env["FFMPEG_URL"] or "-gpl" in env["FFMPEG_URL"]   # לא lgpl: הקוד צריך libx264 ו-vidstab
    download = next(s for s in _workflow()["jobs"]["portable"]["steps"] if s.get("name") == "Download FFmpeg (pinned)")
    assert "sha256sum -c" in download["run"]


def test_the_release_checks_and_attaches_sha256sums_and_puts_the_hash_in_the_notes(tmp_path):
    """30.10.2026: הצעד בודק את ה-zip מול dist/SHA256SUMS.txt, מצרף את הקובץ, וה-hash מופיע בהערות הגרסה."""
    import subprocess
    import sys
    steps = _workflow()["jobs"]["portable"]["steps"]
    check = next(s for s in steps if s.get("name") == "Check the zip against SHA256SUMS.txt")
    assert "sha256sum -c SHA256SUMS.txt" in check["run"]
    release = next(s for s in steps if "gh release create" in s.get("run", ""))
    assert "dist/SHA256SUMS.txt" in release["run"].split("gh release create", 1)[1]
    script = release["run"].split("<<'EOF' > release_notes.md\n", 1)[1].split("\nEOF\n", 1)[0]
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 9.9.9 - 2026-10-30\n\n### Security\n- a fix\n\n## 9.9.8\n- old\n",
                                           encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "SHA256SUMS.txt").write_text("ab" * 32 + "  ClipForge-9.9.9-win64.zip\n", encoding="utf-8")
    notes = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env={**os.environ, "GITHUB_REF_NAME": "v9.9.9"},
                           capture_output=True, text=True, check=True).stdout
    assert notes.startswith("### Security\n- a fix") and "old" not in notes
    assert "ab" * 32 in notes and "ClipForge-9.9.9-win64.zip" in notes
