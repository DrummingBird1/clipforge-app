# tests/infra/test_readme_screenshots.py
#
# 30.10.2026 (ClipForge מתחיל באנגלית): README.md מציג את צילומי המסך באנגלית (docs/images/), ו-README.he.md את העבריים
# (docs/images/he/). כל תמונה שמופיעה קיימת, ושני ה-README מציגים את אותם מסכים - dev/make_screenshots.py מייצר אותם.
# 8.11.2026: שבעה מסכים - נוספו המצב הפשוט של הסטודיו ותמונת המיתוג (מסגרת מעוגלת, שם הקובץ וכתוביות שנשברות).
import os
import re

from tests import PROJECT_ROOT

SCREENS = {"studio", "simple", "branding", "dataviz", "outputs", "notifications", "phone"}
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
# בשפה שלו. ה-badges של הגרסה וההורדות מצביעים על DrummingBird1/clipforge-app. ה-badge של CI בא מ-GitHub עצמו ולא מ-shields.io,
# ולכן הוא לא נספר כאן ונבדק בטסט נפרד, בסוף הקובץ.
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


# 8.11.2026 (1.2.0): ב-Actions של הריפו הציבורי פועלים, ואתר התיעוד מתפרסם ממנו (pages.yml). בראש כל README קישור לאתר
# (הכתובת היא site_url ב-mkdocs.yml) ו-badge של ה-workflow "CI" על main, שמקשר לדף שלו. ה-badge חייב להצביע על workflow שקיים.
def test_each_readme_links_the_docs_site_and_shows_the_ci_badge():
    with open(os.path.join(PROJECT_ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        site_url = re.search(r"^site_url:\s*(\S+)", f.read(), re.MULTILINE).group(1)
    with open(os.path.join(PROJECT_ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as f:
        assert f.read().startswith("name: CI\n")
    workflow = "https://github.com/DrummingBird1/clipforge-app/actions/workflows/ci.yml"
    for readme in ("README.md", "README.he.md"):
        with open(os.path.join(PROJECT_ROOT, readme), encoding="utf-8") as f:
            top = f.read().split("\n## ", 1)[0]
        assert f"]({site_url})" in top, readme
        assert f"[![CI]({workflow}/badge.svg?branch=main)]({workflow})" in top, readme


# 8.11.2026: בראש כל README ממורכז סמל ClipForge (docs/images/logo.svg - אותו עיצוב כמו assets/app_icon.png, בווקטור), וגם
# אתר התיעוד משתמש בו כלוגו וכ-favicon. ב-README האנגלי כל div ו-details נושאים markdown="1", כדי שאתר התיעוד (md_in_html)
# יעבד אותם; ב-GitHub התכונה הזו נעלמת בלי נזק. ושני ה-README מציגים את אותם 7 קטעי "פתרון בעיות" מתקפלים.
def test_each_readme_opens_with_the_logo_and_the_docs_site_uses_it():
    import xml.etree.ElementTree as ET

    logo = "docs/images/logo.svg"
    root = ET.parse(os.path.join(PROJECT_ROOT, logo)).getroot()
    assert root.get("viewBox") == "0 0 512 512" and root.get("width") == root.get("height")
    texts = {}
    for readme in ("README.md", "README.he.md"):
        with open(os.path.join(PROJECT_ROOT, readme), encoding="utf-8") as f:
            texts[readme] = f.read()
        top = texts[readme].split("\n## ", 1)[0]
        assert top.index(f"]({logo})") < top.index("\n# ClipForge\n"), readme
        assert texts[readme].count("<details") == texts[readme].count("</details>") == 7, readme
    english_blocks = re.findall(r"<(?:div|details)\b[^>]*>", texts["README.md"])
    assert english_blocks and all('markdown="1"' in tag for tag in english_blocks)
    with open(os.path.join(PROJECT_ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        mkdocs = f.read()
    assert "\n  logo: images/logo.svg\n" in mkdocs and "\n  favicon: images/logo.svg\n" in mkdocs
    assert "\n  - md_in_html\n" in mkdocs
