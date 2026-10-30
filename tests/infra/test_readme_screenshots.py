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


# 30.10.2026 (הריפו הציבורי): בראש כל README שורת badges מ-shields.io ומתחתיה GIF ההדגמה (dev/make_demo_gif.py), כל אחד
# בשפה שלו. ה-badges של הגרסה וההורדות מצביעים על DrummingBird1/clipforge-app, ואין badge של CI (‏Actions כבוי עד 1.11).
def test_each_readme_opens_with_badges_and_its_demo_gif():
    for readme, gif in (("README.md", "docs/images/demo.gif"), ("README.he.md", "docs/images/he/demo.gif")):
        with open(os.path.join(PROJECT_ROOT, readme), encoding="utf-8") as f:
            top = f.read().split("\n## ", 1)[0]
        assert f"]({gif})" in top and os.path.isfile(os.path.join(PROJECT_ROOT, gif)), readme
        assert os.path.getsize(os.path.join(PROJECT_ROOT, gif)) < 8 * 1024 * 1024
        badges = re.findall(r"\[!\[[^\]]*\]\(https://img\.shields\.io/[^)]+\)\]\(([^)]+)\)", top)
        assert "https://github.com/DrummingBird1/clipforge-app/releases/latest" in badges and "LICENSE" in badges, readme
        shields = re.findall(r"https://img\.shields\.io/[^)\s]+", top)
        assert all("clipforge-app" in s for s in shields if "/github/" in s) and len(shields) == 5, readme
        assert not any("workflow" in s or "actions" in s for s in shields)
        assert top.index("img.shields.io") < top.index(gif)                               # ה-badges מעל ה-GIF
