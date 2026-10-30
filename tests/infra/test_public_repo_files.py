# tests/infra/test_public_repo_files.py
#
# 30.10.2026 (הכנה להפצה ציבורית): קובצי הקהילה של הריפו הציבורי (CONTRIBUTING, ‏SECURITY, ‏CODE_OF_CONDUCT, תבניות ה-issues
# וה-PR) קיימים ותקינים, ותמונת ה-social preview בגודל ש-GitHub מבקש - בלי רשת.
import importlib.machinery
import importlib.util
import os

import yaml
from PIL import Image

from tests import PROJECT_ROOT

ROOT_FILES = ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", ".github/pull_request_template.md")
TEMPLATES = os.path.join(PROJECT_ROOT, ".github", "ISSUE_TEMPLATE")


def test_the_community_files_are_there():
    for rel in ROOT_FILES:
        assert os.path.getsize(os.path.join(PROJECT_ROOT, *rel.split("/"))) > 200, rel


def test_the_issue_forms_are_valid_and_security_goes_to_the_private_form():
    for name in ("bug_report.yml", "feature_request.yml"):
        with open(os.path.join(TEMPLATES, name), encoding="utf-8") as f:
            form = yaml.safe_load(f)
        assert form["name"] and form["description"] and form["body"], name
        ids = [item["id"] for item in form["body"] if "id" in item]
        assert len(ids) == len(set(ids)), name
    with open(os.path.join(TEMPLATES, "config.yml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config["blank_issues_enabled"] is False
    links = {link["name"]: link["url"] for link in config["contact_links"]}
    assert links["Report a security problem"].startswith("https://github.com/DrummingBird1/clipforge-app/security/")
    assert links["Questions and ideas"] == "https://github.com/DrummingBird1/clipforge-app/discussions"   # שאלות ורעיונות -> Discussions


def test_the_social_preview_is_the_size_github_asks_for():
    with Image.open(os.path.join(PROJECT_ROOT, "docs", "images", "social-preview.png")) as img:
        assert img.size == (1280, 640)
    path = os.path.join(PROJECT_ROOT, "dev", "make_social_preview.py")
    loader = importlib.machinery.SourceFileLoader("make_social_preview", path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("make_social_preview", loader))
    loader.exec_module(module)
    assert module.render().size == (1280, 640)   # הסקריפט עדיין מצייר בלי רשת ובלי קבצים חסרים


def test_the_roadmap_is_there_points_to_the_public_repository_and_the_readmes_link_it():
    """30.10.2026: ROADMAP.md לפי נושאים, עם הקישורים ל-milestone, ל-Discussions ול-good first issue של הריפו הציבורי."""
    import re
    with open(os.path.join(PROJECT_ROOT, "ROADMAP.md"), encoding="utf-8") as f:
        roadmap = f.read()
    for heading in ("## Next: 1.2", "## Studio", "## Data videos", "## Performance", "## Distribution"):
        assert heading in roadmap, heading
    github_links = re.findall(r"https://github\.com/[^\s)]+", roadmap)
    assert github_links and all(link.startswith("https://github.com/DrummingBird1/clipforge-app/") for link in github_links)
    assert "/milestone/1" in roadmap and "/discussions/categories/ideas" in roadmap and "good+first+issue" in roadmap
    for readme in ("README.md", "README.he.md"):
        with open(os.path.join(PROJECT_ROOT, readme), encoding="utf-8") as f:
            assert "[ROADMAP.md](ROADMAP.md)" in f.read(), readme


def test_the_readmes_install_from_the_scoop_bucket_and_releasing_updates_it():
    """30.10.2026: התקנה עם Scoop מה-bucket הציבורי DrummingBird1/scoop-clipforge, ו-Releasing כולל את עדכון ה-manifest."""
    bucket = "https://github.com/DrummingBird1/scoop-clipforge"
    for readme in ("README.md", "README.he.md"):
        with open(os.path.join(PROJECT_ROOT, readme), encoding="utf-8") as f:
            text = f.read()
        install = text[text.index("```powershell", text.index("Scoop")):]
        assert install.startswith(f"```powershell\nscoop bucket add clipforge {bucket}\nscoop install clipforge\n```"), readme
        assert "`data`" in text and "`workspace`" in text, readme
    with open(os.path.join(PROJECT_ROOT, "docs", "development.md"), encoding="utf-8") as f:
        development = f.read()
    releasing = development[development.index("### Releasing a new version"):development.index("### CI and security workflows")]
    assert f"({bucket})" in releasing and "bucket/clipforge.json" in releasing and "SHA256SUMS.txt" in releasing
