# utils/shared/docs_sections.py
#
# גל 33: "📖 בתיעוד" ליד כל הגדרה בעורך-העל - מוצא ב-docs/<doc>.md את הבלוק (סעיף רשימה או
# פסקה) שמזכיר את הדגל של ההגדרה, ומחזיר אותו עם כותרת קצרה. התיעוד בנוי כרשימת סעיפים
# ארוכים (שורה אחת לכל דגל), ולכן יחידת החיפוש היא בלוק ולא סעיף markdown שלם.
# רק מסמכים מרשימה סגורה - שם המסמך מגיע מהדפדפן, ואסור שיהפוך לנתיב חופשי.

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
ALLOWED_DOCS = ("video_editor", "dataviz", "web_ui", "scripts", "scheduling_and_conventions")
MAX_TEXT = 4000

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def split_blocks(text):
    """מפרק markdown לבלוקים: כל סעיף רשימה הוא בלוק, ופסקה רגילה (עד שורה ריקה) היא בלוק.
    מחזיר רשימת (כותרת_אחרונה, טקסט_הבלוק)."""
    blocks = []
    heading = ""
    current = []

    def _flush():
        if current:
            blocks.append((heading, "\n".join(current).strip()))
            current.clear()

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            _flush()
            heading = match.group(1).strip()
        elif not line.strip():
            _flush()
        elif _BULLET_RE.match(line):
            _flush()
            current.append(line.strip())
        else:
            current.append(line.strip())
    _flush()
    return blocks


def _term_pattern(term):
    # דגל (--pip) לא אמור להתאים ל---pip-position; מילה רגילה - תת-מחרוזת בלי תלות ברישיות
    if term.startswith("--"):
        return re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])")
    return re.compile(re.escape(term), re.IGNORECASE)


def find_section(doc, terms, docs_dir=None):
    """הבלוק הראשון ב-docs/<doc>.md שמזכיר את המונח הראשון שנמצא (לפי סדר העדיפות ב-terms).
    מחזיר {"doc", "title", "text"} או None (מסמך לא מורשה / חסר / אין התאמה)."""
    if doc not in ALLOWED_DOCS:
        return None
    path = os.path.join(docs_dir or DOCS_DIR, doc + ".md")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        blocks = split_blocks(f.read())
    for term in terms:
        term = str(term or "").strip()
        if len(term) < 2:
            continue
        pattern = _term_pattern(term)
        for heading, text in blocks:
            if pattern.search(text):
                bold = _BOLD_RE.search(text)
                title = bold.group(1) if bold else (heading or doc)
                body = _BULLET_RE.sub("", text, count=1)
                if len(body) > MAX_TEXT:
                    body = body[:MAX_TEXT].rstrip() + " …"
                return {"doc": doc, "title": title, "text": body}
    return None
