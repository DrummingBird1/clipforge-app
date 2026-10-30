# dev/mkdocs_hooks.py
#
# 30.10.2026 (אתר התיעוד, mkdocs.yml): README.md, ‏CHANGELOG.md ו-ROADMAP.md יושבים בשורש הריפו, מחוץ ל-docs/ - כאן הם
# נוספים לאתר בזמן הבנייה (index.md, changelog.md, roadmap.md), בלי להעתיק אותם לתוך docs/. והקישורים: מה שכתוב לקריאה
# ב-GitHub (docs/x.md מה-README, ‏../README.md מ-docs/) מופנה לעמוד שבאתר, וכל קובץ אחר מחוץ לאתר - לקובץ בריפו הציבורי.
import os
import re

from mkdocs.structure.files import File

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "https://github.com/DrummingBird1/clipforge-app"
ROOT_PAGES = {"README.md": "index.md", "CHANGELOG.md": "changelog.md", "ROADMAP.md": "roadmap.md"}
LINK = re.compile(r"(\]\()([^)\s]+)(\))")


def on_files(files, config):
    for source, page in ROOT_PAGES.items():
        with open(os.path.join(ROOT, source), encoding="utf-8") as f:
            files.append(File.generated(config, page, content=f.read()))
    return files


def site_link(url, from_root):
    """הקישור כפי שהוא באתר. from_root: העמוד נוצר מקובץ בשורש הריפו (README וכו'); אחרת הוא עמוד מתוך docs/."""
    if re.match(r"[a-z][a-z0-9+.-]*:|#|/", url):
        return url
    path, _, anchor = url.partition("#")
    if from_root:
        if path.startswith("docs/"):
            target = path[len("docs/"):]
        elif path.startswith("../../"):   # קישור יחסי של GitHub, למשל ../../releases/latest
            target = f"{REPO}/{path[len('../../'):]}"
        else:
            target = ROOT_PAGES.get(path) or f"{REPO}/blob/main/{path}"
    elif path.startswith("../"):
        rel = path[len("../"):]
        target = ROOT_PAGES.get(rel) or f"{REPO}/blob/main/{rel}"
    else:
        return url
    return target + (f"#{anchor}" if anchor else "")


def on_page_markdown(markdown, page, config, files):
    from_root = page.file.src_uri in ROOT_PAGES.values()
    return LINK.sub(lambda m: m.group(1) + site_link(m.group(2), from_root) + m.group(3), markdown)
