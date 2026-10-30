# scripts/docs_search.py
#
# חיפוש אישי בתיעוד/החלטות (item: אינדקס חיפוש אישי לתיעוד/החלטות) - ה-
# README.md הענק של הפרויקט הזה כבר משמש בפועל כ"יומן החלטות" (כל סעיף מסביר
# למה נבחרה גישה מסוימת, לא רק מה היא עושה) - קשה לזכור באיזה חלק בדיוק
# הוחלט "למה לא X". כלי טרמינל להרצה ישירה, לא סקריפט GUI (לא מתאים למודל
# "בחר תיקייה, הרץ" של worker.py/web_app.py's /api/run, שדורש --input_dir
# תקין לכל סקריפט - כאן אין תיקיית קלט בכלל, רק שאילתת טקסט), אותו עיקרון
# כמו scripts/build_exe.py/generate_app_icon.py.
#
# מפרק README.md (ו-docs/*.md) למקטעים לפי כותרות markdown
# (# עד ######), ומחפש תת-מחרוזת (case-insensitive) גם בכותרת וגם בגוף - לא
# full-text search אמיתי (embeddings/אינדקס הפוך) - LIKE-style פשוט מספיק
# למסמך יחיד בגודל הזה, אותו עיקרון בדיוק כמו utils/shared/job_history.py's
# search_jobs.

import argparse
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure") and sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_DOC_PATHS = [
    os.path.join(BASE_DIR, "README.md"),
]

# docs/*.md - README.md keeps the overview; the long per-feature sections live here (see "Detailed documentation" in README.md)
_DOCS_DIR = os.path.join(BASE_DIR, "docs")
if os.path.isdir(_DOCS_DIR):
    DEFAULT_DOC_PATHS += [os.path.join(_DOCS_DIR, name) for name in sorted(os.listdir(_DOCS_DIR)) if name.endswith(".md")]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UNTITLED_HEADING = "(תחילת המסמך)"


def parse_sections(text, source_name):
    """מפרק markdown למקטעים לפי כותרת - כל מקטע: {source, heading, level,
    body_lines, line_number}. טקסט לפני הכותרת הראשונה (למשל פסקת פתיחה)
    נכנס למקטע עם heading=_UNTITLED_HEADING, ומושמט אם ריק לגמרי."""
    sections = []
    current = {"source": source_name, "heading": _UNTITLED_HEADING, "level": 0, "body_lines": [], "line_number": 1}

    def _flush():
        if current["body_lines"] or current["heading"] != _UNTITLED_HEADING:
            sections.append(current)

    for i, line in enumerate(text.splitlines(), start=1):
        match = _HEADING_RE.match(line)
        if match:
            _flush()
            current = {
                "source": source_name, "heading": match.group(2).strip(),
                "level": len(match.group(1)), "body_lines": [], "line_number": i,
            }
        else:
            current["body_lines"].append(line)
    _flush()
    return sections


def load_all_sections(doc_paths=None):
    """קורא ומפרק את כל המסמכים ב-doc_paths (ברירת מחדל: DEFAULT_DOC_PATHS) -
    מסמך שלא קיים מדולג בשקט, לא שגיאה."""
    doc_paths = doc_paths if doc_paths is not None else DEFAULT_DOC_PATHS
    all_sections = []
    for path in doc_paths:
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        all_sections.extend(parse_sections(text, os.path.basename(path)))
    return all_sections


def _make_snippet(body_text, query_lower, context_chars):
    idx = body_text.lower().find(query_lower)
    if idx == -1:
        return body_text.strip()[:context_chars]
    start = max(0, idx - context_chars // 2)
    end = min(len(body_text), idx + len(query_lower) + context_chars // 2)
    snippet = " ".join(body_text[start:end].split())  # שורות/רווחים מרובים -> שורה אחת קריאה
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body_text) else ""
    return f"{prefix}{snippet}{suffix}"


def search_sections(sections, query, context_chars=200):
    """מחזיר [(section, score, snippet), ...] עבור מקטעים שתואמים query
    (case-insensitive) בכותרת ו/או בגוף - ממוין לפי score יורד. התאמה בכותרת
    נספרת פי 3 מהתאמה בגוף - סימן חזק יותר לרלוונטיות ממקרה בודד בתוך פסקה
    ארוכה. query ריק/רק-רווחים לא מחזיר כלום (לא "הכל תואם")."""
    query = query.strip()
    if not query:
        return []
    query_lower = query.lower()
    results = []
    for section in sections:
        body_text = "\n".join(section["body_lines"])
        heading_matches = section["heading"].lower().count(query_lower)
        body_matches = body_text.lower().count(query_lower)
        if heading_matches == 0 and body_matches == 0:
            continue
        score = heading_matches * 3 + body_matches
        snippet = _make_snippet(body_text, query_lower, context_chars) if body_matches else ""
        results.append((section, score, snippet))
    results.sort(key=lambda r: r[1], reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(description="חיפוש אישי בתיעוד/החלטות הפרויקט (README.md ו-docs/)")
    parser.add_argument("query", type=str, help="מילה/ביטוי לחיפוש")
    parser.add_argument("--limit", type=int, default=10, help="מספר תוצאות מקסימלי (ברירת מחדל: 10)")
    args = parser.parse_args()

    sections = load_all_sections()
    results = search_sections(sections, args.query)

    if not results:
        print(f'לא נמצאו תוצאות עבור "{args.query}".')
        return

    shown = results[:max(0, args.limit)]
    print(f'נמצאו {len(results)} תוצאות עבור "{args.query}" (מוצגות {len(shown)}):\n')
    for section, _score, snippet in shown:
        print(f"📄 {section['source']}:{section['line_number']} — {section['heading']}")
        if snippet:
            print(f"   {snippet}")
        print()


if __name__ == "__main__":
    main()
