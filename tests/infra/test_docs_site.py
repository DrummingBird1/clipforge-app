# tests/infra/test_docs_site.py
#
# 30.10.2026 (אתר התיעוד): mkdocs.yml נבנה עם --strict (קישור שבור לעמוד או לכותרת = כישלון), ו-dev/mkdocs_hooks.py מפנה
# את הקישורים שנכתבו ל-GitHub: docs/x.md מה-README לעמוד באתר, ‏../README.md מ-docs/ לעמוד הבית, וקובץ מחוץ לאתר לריפו הציבורי.
import os
import sys

import pytest

from tests import PROJECT_ROOT

sys.path.insert(0, os.path.join(PROJECT_ROOT, "dev"))
import mkdocs_hooks  # noqa: E402

REPO = "https://github.com/DrummingBird1/clipforge-app"


@pytest.mark.parametrize("url, from_root, expected", [
    ("docs/dataviz.md", True, "dataviz.md"),
    ("docs/images/studio.png", True, "images/studio.png"),
    ("docs/development.md#ci-and-security-workflows", True, "development.md#ci-and-security-workflows"),
    ("CHANGELOG.md", True, "changelog.md"),
    ("README.he.md", True, f"{REPO}/blob/main/README.he.md"),
    ("../../releases/latest", True, f"{REPO}/releases/latest"),
    ("../README.md", False, "index.md"),
    ("../ROADMAP.md#next", False, "roadmap.md#next"),
    ("../CONTRIBUTING.md", False, f"{REPO}/blob/main/CONTRIBUTING.md"),
    ("video_editor.md", False, "video_editor.md"),
    ("#usage", True, "#usage"),
    ("https://example.com/a.md", True, "https://example.com/a.md"),
])
def test_links_written_for_github_point_to_the_site_or_the_public_repository(url, from_root, expected):
    assert mkdocs_hooks.site_link(url, from_root) == expected


def test_the_site_builds_in_strict_mode(tmp_path, monkeypatch):
    from mkdocs.commands.build import build
    from mkdocs.config import load_config

    monkeypatch.setenv("NO_MKDOCS_2_WARNING", "1")
    config = load_config(os.path.join(PROJECT_ROOT, "mkdocs.yml"), strict=True, site_dir=str(tmp_path / "site"))
    build(config)   # --strict: אזהרה אחת (קישור שבור, כותרת חסרה) זורקת Abort
    for page in ("index.html", "changelog/index.html", "roadmap/index.html", "dataviz/index.html"):
        assert (tmp_path / "site" / page).is_file()
    assert not (tmp_path / "site" / "handoff").exists() and not (tmp_path / "site" / "history").exists()
