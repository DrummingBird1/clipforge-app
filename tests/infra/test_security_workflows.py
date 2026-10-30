# tests/infra/test_security_workflows.py
#
# 30.10.2026 (קבוצה ג', הריפו הציבורי): ‏CodeQL ו-OpenSSF Scorecard רצים רק בריפו ציבורי, ה-CI עם הרשאות קריאה בלבד,
# ה-Release חותם attestation על ה-zip, וכל action מוצמד ל-SHA מלא עם הגרסה בהערה (Scorecard בודק את זה). בלי להריץ workflow.
import os
import re

import yaml

from tests import PROJECT_ROOT

WORKFLOWS = os.path.join(PROJECT_ROOT, ".github", "workflows")
PUBLIC_ONLY = "github.event.repository.private == false"


def _load(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _triggers(wf):
    return wf.get("on", wf.get(True))   # yaml קורא את המפתח on כ-True


def test_every_action_in_every_workflow_is_pinned_to_a_full_sha_with_its_version():
    names = sorted(n for n in os.listdir(WORKFLOWS) if n.endswith(".yml"))
    assert {"ci.yml", "release.yml", "codeql.yml", "scorecard.yml", "pages.yml"} <= set(names)
    unpinned = []
    for name in names:
        _load(name)   # YAML תקין
        with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as f:
            for number, line in enumerate(f, 1):
                if re.match(r"\s*(-\s+)?uses:", line) and not re.search(r"uses:\s*[\w./-]+@[0-9a-f]{40} # v\d+(\.\d+)*\s*$", line):
                    unpinned.append(f"{name}:{number}: {line.strip()}")
    assert unpinned == []


def test_codeql_scans_python_and_javascript_only_in_a_public_repository():
    wf = _load("codeql.yml")
    triggers = _triggers(wf)
    assert {"push", "pull_request", "schedule"} <= set(triggers)
    job = wf["jobs"]["analyze"]
    assert job["if"] == PUBLIC_ONLY
    assert job["strategy"]["matrix"]["language"] == ["python", "javascript-typescript"]
    assert job["permissions"] == {"contents": "read", "security-events": "write"}
    assert wf["permissions"] == {"contents": "read"}


def test_scorecard_publishes_from_a_public_repository_with_minimal_permissions():
    wf = _load("scorecard.yml")
    assert wf["permissions"] == "read-all" and "env" not in wf and "defaults" not in wf
    job = wf["jobs"]["analysis"]
    assert job["if"] == PUBLIC_ONLY
    assert job["permissions"] == {"security-events": "write", "id-token": "write", "contents": "read", "actions": "read"}
    step = next(s for s in job["steps"] if s.get("uses", "").startswith("ossf/scorecard-action@"))
    assert step["with"]["publish_results"] is True and step["with"]["results_format"] == "sarif"
    assert any(s.get("uses", "").startswith("github/codeql-action/upload-sarif@") for s in job["steps"])


def test_ci_reads_only_and_runs_the_unit_tests_on_pushes_to_the_public_repository():
    wf = _load("ci.yml")
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["unit"]["if"] == f"github.event_name != 'push' || {PUBLIC_ONLY}"
    assert wf["jobs"]["tk"]["if"] == wf["jobs"]["browser"]["if"] == "github.event_name != 'push'"


def test_the_release_attests_the_zip_and_its_checksums():
    steps = _load("release.yml")["jobs"]["portable"]["steps"]
    attest = next(s for s in steps if s.get("uses", "").startswith("actions/attest-build-provenance@"))
    assert attest["with"]["subject-path"].split() == ["dist/ClipForge-*-win64.zip", "dist/SHA256SUMS.txt"]
    release = next(s for s in steps if "gh release create" in s.get("run", ""))
    assert "gh attestation verify" in release["run"] and "GITHUB_REPOSITORY" in release["run"]
    assert steps.index(attest) < steps.index(release)


def test_the_docs_site_builds_strictly_and_deploys_to_pages_only_from_the_public_repository():
    wf = _load("pages.yml")
    triggers = _triggers(wf)
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"]["branches"] == ["main"]
    assert {"docs/**", "mkdocs.yml", "README.md", "dev/mkdocs_hooks.py"} <= set(triggers["push"]["paths"])
    assert wf["permissions"] == {"contents": "read"}
    build, deploy = wf["jobs"]["build"], wf["jobs"]["deploy"]
    assert build["if"] == deploy["if"] == PUBLIC_ONLY
    assert build["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert deploy["needs"] == "build" and deploy["environment"]["name"] == "github-pages"
    assert any("mkdocs build --strict" in s.get("run", "") for s in build["steps"])
    upload = next(s for s in build["steps"] if s.get("uses", "").startswith("actions/upload-pages-artifact@"))
    assert upload["with"]["path"] == "site"
    assert any(s.get("uses", "").startswith("actions/deploy-pages@") for s in deploy["steps"])
