# tests/bot/test_ocr_highlights.py


from utils.media.ocr_highlights import merge_peaks_with_gap, text_matches_highlight_keywords
import utils.media.ocr_highlights as ocr_highlights_module


def test_text_matches_highlight_keywords_finds_known_keyword():
    assert text_matches_highlight_keywords("VICTORY ROYALE") == "victory"


def test_text_matches_highlight_keywords_finds_hebrew_keyword():
    assert text_matches_highlight_keywords("המשחק הסתיים - ניצחון מוחץ!") == "ניצחון"


def test_resolve_ocr_lang_includes_hebrew_when_installed(monkeypatch):
    monkeypatch.setattr(ocr_highlights_module, "_ocr_lang_cache", None)
    monkeypatch.setattr(ocr_highlights_module.pytesseract, "get_languages", lambda config="": ["eng", "heb"])
    assert ocr_highlights_module._resolve_ocr_lang() == "eng+heb"


def test_resolve_ocr_lang_falls_back_to_eng_when_hebrew_missing(monkeypatch):
    monkeypatch.setattr(ocr_highlights_module, "_ocr_lang_cache", None)
    monkeypatch.setattr(ocr_highlights_module.pytesseract, "get_languages", lambda config="": ["eng"])
    assert ocr_highlights_module._resolve_ocr_lang() == "eng"


def test_resolve_ocr_lang_falls_back_to_eng_when_tesseract_unavailable(monkeypatch):
    def _raise(config=""):
        raise RuntimeError("tesseract not installed")
    monkeypatch.setattr(ocr_highlights_module, "_ocr_lang_cache", None)
    monkeypatch.setattr(ocr_highlights_module.pytesseract, "get_languages", _raise)
    assert ocr_highlights_module._resolve_ocr_lang() == "eng"


def test_resolve_ocr_lang_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(ocr_highlights_module, "_ocr_lang_cache", None)
    monkeypatch.setattr(ocr_highlights_module.pytesseract, "get_languages", lambda config="": (calls.append(1), ["eng"])[1])
    ocr_highlights_module._resolve_ocr_lang()
    ocr_highlights_module._resolve_ocr_lang()
    assert len(calls) == 1


def test_text_matches_highlight_keywords_is_case_insensitive():
    assert text_matches_highlight_keywords("Enemy Eliminated") == "eliminated"


def test_text_matches_highlight_keywords_no_match_returns_none():
    assert text_matches_highlight_keywords("just some random HUD noise") is None


def test_text_matches_highlight_keywords_handles_empty_and_none():
    assert text_matches_highlight_keywords("") is None
    assert text_matches_highlight_keywords(None) is None


def test_text_matches_highlight_keywords_checks_extra_keywords_too():
    assert text_matches_highlight_keywords("Wheatley: Here she comes!", extra_keywords=["wheatley", "glados"]) == "wheatley"


def test_text_matches_highlight_keywords_extra_keywords_do_not_affect_other_calls():
    # רשימת ה-extra היא per-call, לא global state שדולף בין קריאות
    assert text_matches_highlight_keywords("Wheatley: hello", extra_keywords=["wheatley"]) == "wheatley"
    assert text_matches_highlight_keywords("Wheatley: hello") is None


def test_merge_peaks_with_gap_adds_non_overlapping_candidates():
    existing = [(10.0, "audio")]
    candidates = [(200.0, "ocr:victory")]

    merged = merge_peaks_with_gap(existing, candidates, min_gap_seconds=60)

    assert merged == [(10.0, "audio"), (200.0, "ocr:victory")]


def test_merge_peaks_with_gap_drops_candidates_too_close_to_existing():
    existing = [(100.0, "audio")]
    candidates = [(120.0, "ocr:kill")]  # only 20s away, below the 60s gap

    merged = merge_peaks_with_gap(existing, candidates, min_gap_seconds=60)

    assert merged == [(100.0, "audio")]


def test_merge_peaks_with_gap_keeps_chronological_order():
    existing = [(300.0, "audio")]
    candidates = [(10.0, "ocr:victory"), (600.0, "ocr:mvp")]

    merged = merge_peaks_with_gap(existing, candidates, min_gap_seconds=60)

    assert merged == [(10.0, "ocr:victory"), (300.0, "audio"), (600.0, "ocr:mvp")]


def test_merge_peaks_with_gap_dedups_multiple_candidates_against_each_other():
    existing = []
    candidates = [(10.0, "ocr:victory"), (20.0, "ocr:mvp"), (500.0, "ocr:kill")]

    merged = merge_peaks_with_gap(existing, candidates, min_gap_seconds=60)

    assert merged == [(10.0, "ocr:victory"), (500.0, "ocr:kill")]
