# tests/gui/test_stats_tab_personal_stats.py
#
# בודק את שני החלקים החדשים ב-side_card של ui/stats_tab.py (item: personal
# stats dashboard) - "שעות משחק" (game_playtime_label, טקסט בלבד - נבדק ישירות)
# ו"קליפים שנלכדו" (clips_history_canvas - רק שהציור לא קורס, בלי לבדוק פיקסלים
# בפועל, כמו שגם גרף החומרה הקיים ב-hw_history_canvas לא נבדק ברמת פיקסלים
# בשום טסט קיים - חלון headless לא בהכרח נותן width/height אמיתיים לצייר לפיהם).


import utils.media.game_playtime as game_playtime
from utils.shared import hardware_history, job_history
from utils.shared.i18n import t
from ui.stats_tab import StatsTabComponent


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(job_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(hardware_history, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr("ui.stats_tab.CLIPS_DIR", str(tmp_path / "clips"))


def test_game_playtime_label_shows_no_data_message_when_empty(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = StatsTabComponent(shared_tk_root)
    try:
        assert comp.game_playtime_label.cget("text") == t("עוד לא נרשם זמן משחק.")
    finally:
        comp.destroy()


def test_game_playtime_label_shows_formatted_hours_sorted_by_total(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)
    game_playtime.record_playtime_tick("Green", 3600)
    game_playtime.record_playtime_tick("Rocket League", 7200)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._refresh_game_playtime_summary()
        text = comp.game_playtime_label.cget("text")
        lines = text.split("\n")
        assert lines[0].startswith("Rocket League: 2.0")
        assert lines[1].startswith("Minecraft: 1.0")
    finally:
        comp.destroy()


def test_refresh_clips_captured_graph_does_not_crash_with_no_clips(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._refresh_clips_captured_graph()
    finally:
        comp.destroy()


def test_draw_clips_captured_graph_handles_empty_list(tmp_path, monkeypatch, shared_tk_root):
    _setup(tmp_path, monkeypatch)

    comp = StatsTabComponent(shared_tk_root)
    try:
        comp._draw_clips_captured_graph([])
    finally:
        comp.destroy()
