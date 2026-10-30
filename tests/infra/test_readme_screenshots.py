# tests/infra/test_readme_screenshots.py
#
# 30.10.2026 (ClipForge מתחיל באנגלית): README.md מציג את צילומי המסך באנגלית (docs/images/), ו-README.he.md את העבריים
# (docs/images/he/). כל תמונה שמופיעה קיימת, ושני ה-README מציגים את אותם חמישה מסכים - dev/make_screenshots.py מייצר אותם.
import os
import re

from tests import PROJECT_ROOT

SCREENS = {"studio", "dataviz", "outputs", "notifications", "phone"}
IMAGE = re.compile(r"!\[[^\]]*\]\((docs/images/[^)]+\.png)\)")


def _images(readme):
    with open(os.path.join(PROJECT_ROOT, readme), encoding="utf-8") as f:
        return IMAGE.findall(f.read())


def test_the_english_readme_shows_the_english_screenshots():
    images = _images("README.md")
    assert {os.path.splitext(os.path.basename(p))[0] for p in images} == SCREENS
    assert all(os.path.dirname(p) == "docs/images" and os.path.isfile(os.path.join(PROJECT_ROOT, p)) for p in images)


def test_the_hebrew_readme_shows_the_hebrew_screenshots():
    images = _images("README.he.md")
    assert {os.path.splitext(os.path.basename(p))[0] for p in images} == SCREENS
    assert all(os.path.dirname(p) == "docs/images/he" and os.path.isfile(os.path.join(PROJECT_ROOT, p)) for p in images)
