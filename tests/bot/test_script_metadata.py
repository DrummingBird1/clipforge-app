# tests/bot/test_script_metadata.py
#
# רגרסיה: get_script_metadata() היה מפעיל fix_hebrew_word_order() על name_he/
# desc_he בזמן טעינה. זה עבד כשהשם מוצג *לבד* (למשל בסיידבר), אבל שבר כל מקום
# שמרכיב את השם לתוך מחרוזת t() גדולה יותר עם טקסט לועזי (כמו כותרת עם שם
# קובץ: "סקריפט: {name} ({filename})") - t() מדלג על fix_hebrew_word_order
# כשיש תווים לועזיים במחרוזת המורכבת (בגלל ה-filename), כך שקטע השם שכבר הפוך
# נשאר הפוך על המסך. עכשיו get_script_metadata() מחזיר גולמי, וכל קורא שמציג
# את זה לבד אחראי להפעיל fix_hebrew_word_order() בעצמו על הטקסט הסופי.


from utils.shared.i18n import fix_hebrew_word_order, t
from utils.shared.script_metadata import get_script_metadata
from utils.shared.state import state


def _write_script(tmp_path, name_he):
    path = tmp_path / "fake_script.py"
    path.write_text(
        f"# Name: {name_he}\n"
        "# Name (EN): Fake Script\n"
        "# Description: תיאור כלשהו\n"
        "# Description (EN): Some description\n"
        "# Safety: read-only\n",
        encoding="utf-8",
    )
    return str(path)


def test_get_script_metadata_returns_raw_unreversed_name(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "language", "he")
    path = _write_script(tmp_path, "זיהוי וחיתוך קליפים אוטומטי")

    metadata = get_script_metadata(path)

    assert metadata["name"] == "זיהוי וחיתוך קליפים אוטומטי"  # לא הפוך


def test_name_embedded_in_mixed_title_stays_in_correct_order(tmp_path, monkeypatch):
    # בדיוק התרחיש שהיה שבור: כותרת שמשלבת את השם עם שם קובץ (טקסט לועזי)
    monkeypatch.setattr(state, "language", "he")
    path = _write_script(tmp_path, "זיהוי וחיתוך קליפים אוטומטי")
    metadata = get_script_metadata(path)

    title = t("סקריפט: {name} ({filename})", name=metadata["name"], filename="story_cutter.py")

    assert title == "סקריפט: זיהוי וחיתוך קליפים אוטומטי (story_cutter.py)"


def test_name_shown_alone_still_gets_word_order_fix(tmp_path, monkeypatch):
    # כשהשם מוצג *לבד* (כמו בסיידבר), הקורא עדיין צריך להפעיל את התיקון בעצמו -
    # fix_hebrew_word_order מחזיר את המחרוזת ה"מפוצה" (הפוכה) שנמסרת בפועל
    # ל-Tk, כדי ש-Tk (שהופך שוב בעצמו בזמן רינדור) יציג אותה נכון על המסך.
    monkeypatch.setattr(state, "language", "he")
    path = _write_script(tmp_path, "זיהוי וחיתוך קליפים אוטומטי")
    metadata = get_script_metadata(path)

    displayed = fix_hebrew_word_order(f"⚠️ {metadata['name']}")

    assert displayed == "אוטומטי קליפים וחיתוך זיהוי ⚠️"


def test_the_shorts_publisher_has_a_general_name_in_both_languages(monkeypatch):
    """30.10.2026 (לפני ההפצה): בלי Rocket ובלי 4K - הוא מרנדר כל משחק, ובהתקנה חדשה ברזולוציית המקור."""
    import json
    import os

    from tests import PROJECT_ROOT
    path = os.path.join(PROJECT_ROOT, "my_scripts", "video", "rocket_shorts_publisher.py")
    for language, expected in (("he", "🎬 פרסום Shorts"), ("en", "🎬 Shorts Publisher")):
        monkeypatch.setattr(state, "language", language)
        assert get_script_metadata(path)["name"] == expected
    with open(os.path.join(PROJECT_ROOT, "src", "entrypoints", "web", "i18n", "en.json"), encoding="utf-8") as f:
        assert json.load(f)["exact"]["פרסום Shorts"] == "Shorts Publisher"   # הדף מתרגם את השם העברי באנגלית
