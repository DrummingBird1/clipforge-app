# tests/infra/test_docs_search.py
#
# בודק scripts/docs_search.py (item: אינדקס חיפוש אישי לתיעוד/החלטות) - פירוק
# markdown למקטעים, חיפוש/דירוג, וקטע-הקשר (snippet) - עם מסמכים סינתטיים
# קטנים (לא README.md האמיתי, כדי שהטסטים לא יישברו כשה-README משתנה), חוץ
# מבדיקה אחת שכן קוראת את README.md האמיתי (מוודאת שהפירוק לא נופל על תוכן אמיתי).
import os


import dev.docs_search as docs_search

_SAMPLE_DOC = """# ClipForge

פסקת פתיחה לפני כל כותרת.

## Watermark

מוסיף לוגו לפינה - item: watermark placement, נבחר top-right כברירת מחדל
כי זה הכי פחות מפריע בגיימינג.

### Opacity

שקיפות בין 0 ל-1, ברירת מחדל 1.0 (אטום לגמרי).

## Rename profiles

item: שינוי שם לפרופיל - נבחר לזרוק שגיאה על התנגשות שם, לא לדרוס בשקט.
"""


def test_parse_sections_splits_by_heading():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    headings = [s["heading"] for s in sections]
    assert headings == ["ClipForge", "Watermark", "Opacity", "Rename profiles"]


def test_parse_sections_captures_body_lines():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    watermark = next(s for s in sections if s["heading"] == "Watermark")
    body = "\n".join(watermark["body_lines"])
    assert "top-right" in body


def test_parse_sections_tracks_line_numbers():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    watermark = next(s for s in sections if s["heading"] == "Watermark")
    # שורה 5 ב-_SAMPLE_DOC (1-indexed) - "## Watermark"
    assert watermark["line_number"] == 5


def test_parse_sections_records_heading_level():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    assert next(s for s in sections if s["heading"] == "ClipForge")["level"] == 1
    assert next(s for s in sections if s["heading"] == "Watermark")["level"] == 2
    assert next(s for s in sections if s["heading"] == "Opacity")["level"] == 3


def test_parse_sections_empty_document_returns_no_sections():
    assert docs_search.parse_sections("", "empty.md") == []


def test_parse_sections_document_with_no_headings_is_one_section():
    sections = docs_search.parse_sections("just some plain text\nmore text", "plain.md")
    assert len(sections) == 1
    assert sections[0]["heading"] == docs_search._UNTITLED_HEADING


# --- search_sections ---

def test_search_matches_in_heading_ranks_above_body_only_match():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    results = docs_search.search_sections(sections, "opacity")
    headings = [r[0]["heading"] for r in results]
    assert headings[0] == "Opacity"  # תואם בכותרת - ראשון


def test_search_matches_in_body_only():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    results = docs_search.search_sections(sections, "top-right")
    assert len(results) == 1
    assert results[0][0]["heading"] == "Watermark"


def test_search_is_case_insensitive():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    assert len(docs_search.search_sections(sections, "WATERMARK")) >= 1


def test_search_no_match_returns_empty():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    assert docs_search.search_sections(sections, "nonexistent_xyz_query") == []


def test_search_blank_query_returns_empty_not_everything():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    assert docs_search.search_sections(sections, "   ") == []


def test_search_snippet_contains_the_matched_text():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    results = docs_search.search_sections(sections, "top-right")
    assert "top-right" in results[0][2]


def test_search_result_includes_source_document_name():
    sections = docs_search.parse_sections(_SAMPLE_DOC, "sample.md")
    results = docs_search.search_sections(sections, "watermark")
    assert results[0][0]["source"] == "sample.md"


# --- load_all_sections ---

def test_load_all_sections_skips_missing_files(tmp_path):
    missing = str(tmp_path / "does_not_exist.md")
    assert docs_search.load_all_sections([missing]) == []


def test_load_all_sections_reads_a_real_file(tmp_path):
    doc_path = tmp_path / "doc.md"
    doc_path.write_text(_SAMPLE_DOC, encoding="utf-8")

    sections = docs_search.load_all_sections([str(doc_path)])

    assert any(s["heading"] == "Watermark" for s in sections)
    assert all(s["source"] == "doc.md" for s in sections)


def test_load_all_sections_combines_multiple_documents(tmp_path):
    doc_a = tmp_path / "a.md"
    doc_a.write_text("# A\n\ncontent a", encoding="utf-8")
    doc_b = tmp_path / "b.md"
    doc_b.write_text("# B\n\ncontent b", encoding="utf-8")

    sections = docs_search.load_all_sections([str(doc_a), str(doc_b)])

    assert {s["source"] for s in sections} == {"a.md", "b.md"}


# --- integration with the real README.md ---

def test_parses_and_searches_the_real_readme_without_crashing():
    readme_path = os.path.join(docs_search.BASE_DIR, "README.md")
    sections = docs_search.load_all_sections([readme_path])

    assert len(sections) > 5  # README.md אמיתי ומפורק, לא ריק/מסמך-אחד

    results = docs_search.search_sections(sections, "watermark")
    assert len(results) > 0  # README.md מתעד watermark בהרחבה - חייב למצוא משהו
