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
    assert config["contact_links"][0]["url"].startswith("https://github.com/DrummingBird1/clipforge-app/security/")


def test_the_social_preview_is_the_size_github_asks_for():
    with Image.open(os.path.join(PROJECT_ROOT, "docs", "images", "social-preview.png")) as img:
        assert img.size == (1280, 640)
    path = os.path.join(PROJECT_ROOT, "dev", "make_social_preview.py")
    loader = importlib.machinery.SourceFileLoader("make_social_preview", path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("make_social_preview", loader))
    loader.exec_module(module)
    assert module.render().size == (1280, 640)   # הסקריפט עדיין מצייר בלי רשת ובלי קבצים חסרים
