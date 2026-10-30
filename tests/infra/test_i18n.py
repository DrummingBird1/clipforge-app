# tests/infra/test_i18n.py


from utils.shared.i18n import fix_hebrew_word_order, t
from utils.shared.state import state


def test_hebrew_mode_returns_original_text(monkeypatch):
    monkeypatch.setattr(state, "language", "he")
    assert t("שלום") == "שלום"


def test_english_mode_uses_translation_dict(monkeypatch):
    monkeypatch.setattr(state, "language", "en")
    assert t("🚀 הסטודיו שלי") == "🚀 My Studio"


def test_english_mode_falls_back_to_original_when_untranslated(monkeypatch):
    monkeypatch.setattr(state, "language", "en")
    assert t("מחרוזת שלא קיימת במילון") == "מחרוזת שלא קיימת במילון"


def test_format_placeholder_substitution(monkeypatch):
    monkeypatch.setattr(state, "language", "en")
    assert t("CPU: {pct}%", pct=42) == "CPU: 42%"


def test_kwarg_named_text_does_not_crash():
    # רגרסיה: t()'s הפרמטר הראשון גם נקרא text - קריאה עם kwarg בשם text היה
    # קורס עם "t() got multiple values for argument 'text'" (gui_manager.pyw's
    # update_led_indicator). text/ עכשיו positional-only מונע את ההתנגשות.
    result = t("status: {text}", text="hello")
    assert "hello" in result


def test_fix_hebrew_word_order_reverses_pure_hebrew_multiword():
    assert fix_hebrew_word_order("זיהוי וחיתוך קליפים אוטומטי") == "אוטומטי קליפים וחיתוך זיהוי"


def test_fix_hebrew_word_order_leaves_mixed_text_untouched():
    assert fix_hebrew_word_order("פרסום Rocket Shorts (רינדור 4K)") == "פרסום Rocket Shorts (רינדור 4K)"


def test_fix_hebrew_word_order_leaves_single_word_untouched():
    assert fix_hebrew_word_order("הגדרות") == "הגדרות"


def test_fix_hebrew_word_order_handles_empty_string():
    assert fix_hebrew_word_order("") == ""


def test_t_applies_word_order_fix_only_in_hebrew_mode(monkeypatch):
    monkeypatch.setattr(state, "language", "he")
    assert t("זיהוי וחיתוך קליפים") == "קליפים וחיתוך זיהוי"

    monkeypatch.setattr(state, "language", "en")
    # באנגלית אין תרגום למחרוזת הזו (לא במילון) - חוזרת כמו שהיא, בלי היפוך
    assert t("זיהוי וחיתוך קליפים") == "זיהוי וחיתוך קליפים"


def test_t_fix_word_order_false_skips_reversal_for_composable_fragments(monkeypatch):
    # רגרסיה: get_script_metadata() ו-utils/shared/diagnostics.py היו הופכים "אבני
    # בניין" (שם/תיאור) בזמן היצירה - עבד כשמוצג לבד, שבר כל מקום שמרכיב את זה
    # לתוך מחרוזת גדולה יותר (icon+name). _fix_word_order=False מאפשר לקבל את
    # הטקסט המתורגם בלי ההיפוך, כדי שהקורא יפעיל אותו בעצמו על התוצאה הסופית.
    monkeypatch.setattr(state, "language", "he")
    assert t("זיהוי וחיתוך קליפים", _fix_word_order=False) == "זיהוי וחיתוך קליפים"


def test_t_fix_word_order_false_still_translates_in_english_mode(monkeypatch):
    monkeypatch.setattr(state, "language", "en")
    assert t("🚀 הסטודיו שלי", _fix_word_order=False) == "🚀 My Studio"
