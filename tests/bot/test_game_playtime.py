# tests/bot/test_game_playtime.py
#
# בודק utils/media/game_playtime.py (item: personal stats dashboard's "hours played
# per game") - DB_PATH ממופתח ל-tmp_path בכל טסט (בדיוק כמו test_hardware_history.py)
# כדי לא לגעת ב-DB האמיתי של הפרויקט.
import datetime


from utils.shared import db
import utils.media.game_playtime as game_playtime
from utils.media.game_playtime import get_playtime_summary, get_playtime_summary_for_year, record_playtime_tick


def test_record_playtime_tick_creates_row_for_new_game(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("Rocket League", 5)

    summary = get_playtime_summary()
    assert summary == [("Rocket League", 5, summary[0][2])]


def test_record_playtime_tick_accumulates_across_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("Rocket League", 5)
    record_playtime_tick("Rocket League", 5)
    record_playtime_tick("Rocket League", 5)

    summary = get_playtime_summary()
    assert summary[0][1] == 15


def test_record_playtime_tick_keeps_separate_totals_per_game(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("Rocket League", 10)
    record_playtime_tick("Green", 20)

    summary = {name: total for name, total, _ in get_playtime_summary()}
    assert summary["Rocket League"] == 10
    assert summary["Minecraft"] == 20


def test_get_playtime_summary_sorted_by_total_seconds_descending(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("Green", 5)
    record_playtime_tick("Rocket League", 50)
    record_playtime_tick("Cyberpunk", 20)

    names = [name for name, _, _ in get_playtime_summary()]
    assert names == ["Rocket League", "GTA5 / FiveM", "Minecraft"]


def test_get_playtime_summary_translates_theme_keys_to_display_names(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("Cyberpunk", 5)
    record_playtime_tick("Green", 5)
    record_playtime_tick("Rocket League", 5)

    names = {name for name, _, _ in get_playtime_summary()}
    assert names == {"GTA5 / FiveM", "Minecraft", "Rocket League"}


def test_get_playtime_summary_empty_when_nothing_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    assert get_playtime_summary() == []


def test_get_playtime_summary_falls_back_to_raw_key_for_unknown_game(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("SomeFutureGame", 5)

    assert get_playtime_summary() == [("SomeFutureGame", 5, get_playtime_summary()[0][2])]


# --- game_playtime_daily / get_playtime_summary_for_year (item: annual "Wrapped" video) ---

def _insert_daily(db_path, game_key, day, seconds):
    with db.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS game_playtime_daily (game_key TEXT NOT NULL, day TEXT NOT NULL, "
            "seconds INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (game_key, day))"
        )
        conn.execute(
            "INSERT INTO game_playtime_daily (game_key, day, seconds) VALUES (?, ?, ?) "
            "ON CONFLICT(game_key, day) DO UPDATE SET seconds = seconds + excluded.seconds",
            (game_key, day, seconds),
        )


def test_record_playtime_tick_also_writes_to_daily_table(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    record_playtime_tick("Rocket League", 5)

    today = datetime.date.today().isoformat()
    with db.connect(str(tmp_path / "test.db")) as conn:
        row = conn.execute(
            "SELECT seconds FROM game_playtime_daily WHERE game_key = ? AND day = ?", ("Rocket League", today)
        ).fetchone()
    assert row == (5,)


def test_get_playtime_summary_for_year_sums_only_matching_year(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))
    _insert_daily(str(tmp_path / "test.db"), "Rocket League", "2026-03-01", 100)
    _insert_daily(str(tmp_path / "test.db"), "Rocket League", "2026-06-15", 50)
    _insert_daily(str(tmp_path / "test.db"), "Rocket League", "2025-12-31", 999)  # שנה אחרת - לא נספר

    summary = get_playtime_summary_for_year(2026)

    assert summary == [("Rocket League", 150)]


def test_get_playtime_summary_for_year_empty_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))

    assert get_playtime_summary_for_year(2026) == []


def test_get_playtime_summary_for_year_sorted_descending_across_games(tmp_path, monkeypatch):
    monkeypatch.setattr(game_playtime, "DB_PATH", str(tmp_path / "test.db"))
    _insert_daily(str(tmp_path / "test.db"), "Green", "2026-01-01", 10)
    _insert_daily(str(tmp_path / "test.db"), "Rocket League", "2026-01-01", 500)

    names = [name for name, _ in get_playtime_summary_for_year(2026)]

    assert names == ["Rocket League", "Minecraft"]
