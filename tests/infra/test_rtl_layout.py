# tests/infra/test_rtl_layout.py


from utils.shared.rtl_layout import rtl_column, rtl_side
from utils.shared.state import state


def test_rtl_side_start_end_in_hebrew(monkeypatch):
    monkeypatch.setattr(state, "language", "he")
    assert rtl_side("start") == "right"
    assert rtl_side("end") == "left"


def test_rtl_side_start_end_in_english(monkeypatch):
    monkeypatch.setattr(state, "language", "en")
    assert rtl_side("start") == "left"
    assert rtl_side("end") == "right"


def test_rtl_side_passes_through_literal_left_right(monkeypatch):
    monkeypatch.setattr(state, "language", "he")
    assert rtl_side("left") == "left"
    assert rtl_side("right") == "right"


def test_rtl_column_mirrors_index_in_hebrew(monkeypatch):
    monkeypatch.setattr(state, "language", "he")
    assert rtl_column(0, 3) == 2
    assert rtl_column(2, 3) == 0
    assert rtl_column(1, 3) == 1


def test_rtl_column_identity_in_english(monkeypatch):
    monkeypatch.setattr(state, "language", "en")
    assert rtl_column(0, 3) == 0
    assert rtl_column(2, 3) == 2
