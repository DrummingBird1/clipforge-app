# tests/web/test_web_app_system.py - REST endpoint tests for web_app.py, topic: system (split out of tests/test_web_app.py; shared helpers in tests/web_app_support.py).
from unittest.mock import MagicMock
import threading
from tests.web_app_support import (  # noqa: F401
    _reset_bot_state,
    client,
    web_app,
)


def test_api_hardware_history_returns_columnar_series(monkeypatch):
    monkeypatch.setattr(
        web_app.hardware_history, "get_recent_samples",
        lambda hours: [("t1", 10.0, 20.0, None, None, None), ("t2", 15.0, 25.0, None, None, None)],
    )

    resp = client.get("/api/hardware_history")

    assert resp.status_code == 200
    assert resp.json() == {
        "recorded_at": ["t1", "t2"], "cpu": [10.0, 15.0], "ram": [20.0, 25.0], "gpu": [None, None],
    }


def test_api_hardware_history_empty_when_no_samples(monkeypatch):
    monkeypatch.setattr(web_app.hardware_history, "get_recent_samples", lambda hours: [])

    resp = client.get("/api/hardware_history")

    assert resp.status_code == 200
    assert resp.json() == {"recorded_at": [], "cpu": [], "ram": [], "gpu": []}


def test_api_hardware_history_passes_through_hours_param(monkeypatch):
    captured = {}

    def _fake_get_recent_samples(hours):
        captured["hours"] = hours
        return []

    monkeypatch.setattr(web_app.hardware_history, "get_recent_samples", _fake_get_recent_samples)

    client.get("/api/hardware_history", params={"hours": 48})

    assert captured["hours"] == 48


# --- /api/game_playtime, /api/clips_captured_by_day (item: personal stats dashboard) ---

def test_api_game_playtime_reports_hours_per_game(monkeypatch):
    monkeypatch.setattr(
        web_app.game_playtime, "get_playtime_summary",
        lambda: [("Rocket League", 7200, "2026-01-01T10:00:00"), ("Minecraft", 3600, "2026-01-02T10:00:00")],
    )

    resp = client.get("/api/game_playtime")

    assert resp.status_code == 200
    assert resp.json() == [
        {"game": "Rocket League", "hours": 2.0, "last_played_at": "2026-01-01T10:00:00"},
        {"game": "Minecraft", "hours": 1.0, "last_played_at": "2026-01-02T10:00:00"},
    ]


def test_api_game_playtime_empty_when_nothing_recorded(monkeypatch):
    monkeypatch.setattr(web_app.game_playtime, "get_playtime_summary", lambda: [])

    resp = client.get("/api/game_playtime")

    assert resp.status_code == 200
    assert resp.json() == []


def test_api_hardware_stats_reports_cpu_ram_gpu_vram_encoder(monkeypatch):
    monkeypatch.setattr(web_app, "get_system_stats", lambda: (12.5, 40.0))
    monkeypatch.setattr(web_app, "get_gpu_stats", lambda: (7.0, 33.0, 91.0))

    resp = client.get("/api/hardware_stats")

    assert resp.status_code == 200
    assert resp.json() == {"cpu": 12.5, "ram": 40.0, "gpu": 7.0, "vram": 33.0, "encoder": 91.0}


def test_api_hardware_stats_handles_no_gpu(monkeypatch):
    monkeypatch.setattr(web_app, "get_system_stats", lambda: (5.0, 20.0))
    monkeypatch.setattr(web_app, "get_gpu_stats", lambda: (None, None, None))

    resp = client.get("/api/hardware_stats")

    assert resp.status_code == 200
    assert resp.json() == {"cpu": 5.0, "ram": 20.0, "gpu": None, "vram": None, "encoder": None}


def test_api_browse_lists_subdirectories(tmp_path):
    (tmp_path / "sub_a").mkdir()
    (tmp_path / "sub_b").mkdir()
    (tmp_path / "a_file.txt").write_text("x")

    resp = client.get("/api/browse", params={"path": str(tmp_path)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["folders"] == ["sub_a", "sub_b"]
    assert data["parent"] == str(tmp_path.parent)


def test_api_browse_always_includes_drives(tmp_path):
    # רגרסיה: קודם אי אפשר היה להגיע לכונן אחר מלבד זה שנתיב הבית נמצא בו -
    # "drives" חייב להופיע בכל תשובה, לא רק בהגעה לשורש כונן.
    resp = client.get("/api/browse", params={"path": str(tmp_path)})
    data = resp.json()
    assert len(data["drives"]) >= 1
    assert all(isinstance(d, str) and d for d in data["drives"])


def test_api_browse_lists_files_with_size(tmp_path):
    (tmp_path / "output.mp4").write_bytes(b"x" * 2048)
    resp = client.get("/api/browse", params={"path": str(tmp_path)})
    data = resp.json()
    assert data["files"] == [{"name": "output.mp4", "size": 2048}]


def test_api_browse_shows_the_real_size_of_a_file_another_process_is_writing(tmp_path):
    # סבב ייצוב: ב-Windows הגודל של scandir לא מתעדכן בזמן שתהליך אחר (ffmpeg) כותב - .partial.mp4 הוצג כ-0
    import subprocess
    import sys
    target = tmp_path / "clip.partial.mp4"
    writer = subprocess.Popen(
        [sys.executable, "-c", "import sys\nf = open(sys.argv[1], 'wb')\nfor _ in range(20):\n    f.write(b'x' * 50000); f.flush()\n"
         "print('ready', flush=True)\nsys.stdin.readline()", str(target)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    try:
        assert writer.stdout.readline().strip() == "ready"
        files = client.get("/api/browse", params={"path": str(tmp_path)}).json()["files"]
    finally:
        writer.communicate("\n", timeout=30)
    assert files == [{"name": "clip.partial.mp4", "size": 1_000_000}]


def test_api_browse_invalid_path_returns_400():
    resp = client.get("/api/browse", params={"path": "Z:\\this_path_should_not_exist_anywhere"})
    assert resp.status_code == 400


def _tray_language(monkeypatch, language):
    # 8.11.2026: תוויות המגש בשפת ההתקנה (ui_language.current). בלי config.json ההתקנה באנגלית - כמו ב-CI - ובמחשב של המפתח היא
    # בעברית, ולכן הטסטים נועלים את השפה במקום לסמוך על הסביבה.
    from utils.shared import ui_language
    monkeypatch.setattr(ui_language, "current", lambda *args, **kwargs: language)


def test_tray_icon_menu_open_browser_opens_the_given_url(monkeypatch):
    import pystray
    _tray_language(monkeypatch, "he")

    captured = {}

    class _FakeIcon:
        def __init__(self, name, image, title, menu):
            captured["menu"] = menu

        def run(self):
            pass  # לא חוסם - הטסט לא רוצה להמתין לאינטראקציה אמיתית עם מגש המערכת

    monkeypatch.setattr(pystray, "Icon", _FakeIcon)
    opened_urls = []
    monkeypatch.setattr(web_app.webbrowser, "open", lambda url: opened_urls.append(url))

    fake_server = type("FakeServer", (), {"should_exit": False})()
    web_app._run_tray_icon(fake_server, "http://127.0.0.1:8878/?token=abc")

    items = {item.text: item for item in captured["menu"]}
    assert set(items.keys()) == {"פתח בדפדפן", "כבה שרת"}

    items["פתח בדפדפן"](None)
    assert opened_urls == ["http://127.0.0.1:8878/?token=abc"]


def test_tray_icon_menu_quit_stops_icon_and_sets_should_exit(monkeypatch):
    import pystray
    _tray_language(monkeypatch, "he")

    captured = {}

    class _FakeIcon:
        def __init__(self, name, image, title, menu):
            captured["menu"] = menu
            self.stopped = False

        def run(self):
            pass

        def stop(self):
            self.stopped = True

    monkeypatch.setattr(pystray, "Icon", _FakeIcon)

    fake_server = type("FakeServer", (), {"should_exit": False})()
    web_app._run_tray_icon(fake_server, "http://127.0.0.1:8878/?token=abc")

    items = {item.text: item for item in captured["menu"]}
    fake_icon_instance = _FakeIcon("x", None, "x", captured["menu"])
    items["כבה שרת"](fake_icon_instance)

    assert fake_icon_instance.stopped is True
    assert fake_server.should_exit is True


def test_tray_icon_menu_follows_the_install_language(monkeypatch):
    import pystray

    captured = {}

    class _FakeIcon:
        def __init__(self, name, image, title, menu):
            captured["menu"] = menu

        def run(self):
            pass

    monkeypatch.setattr(pystray, "Icon", _FakeIcon)
    fake_server = type("FakeServer", (), {"should_exit": False})()
    for language, labels in (("en", {"Open ClipForge", "Stop server"}), ("he", {"פתח בדפדפן", "כבה שרת"})):
        _tray_language(monkeypatch, language)
        web_app._run_tray_icon(fake_server, "http://127.0.0.1:8878/?token=abc")
        assert {item.text for item in captured["menu"]} == labels


def test_tray_icon_falls_back_gracefully_when_pystray_import_fails(monkeypatch, capsys):
    # מדמה סביבה בלי pystray זמין בכלל - לא אמור לזרוק, רק להדפיס ולחזור.
    import builtins
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "pystray":
            raise ImportError("no pystray here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    fake_server = type("FakeServer", (), {"should_exit": False})()

    web_app._run_tray_icon(fake_server, "http://127.0.0.1:8878/?token=abc")  # לא אמור לזרוק

    assert "אייקון מגש המערכת לא זמין" in capsys.readouterr().out


def test_api_bot_status_reports_not_running_by_default():
    _reset_bot_state()
    resp = client.get("/api/bot/status")
    assert resp.status_code == 200
    assert resp.json() == {"running": False, "gave_up": False, "config_error": False}


def test_api_bot_start_launches_thread_and_updates_status(monkeypatch):
    # לא קוראים בפועל ל-subprocess.Popen (זה היה מריץ את הבוט האמיתי!) -
    # ממוקים את _run_bot_process_loop כולה בסטאב לא-מזיק.
    _reset_bot_state()
    started = threading.Event()
    monkeypatch.setattr(web_app, "_run_bot_process_loop", lambda: started.set())

    resp = client.post("/api/bot/start")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert started.wait(timeout=2), "ה-thread לא הופעל בכלל"
    assert client.get("/api/bot/status").json()["running"] is True


def test_api_bot_start_rejects_when_already_running():
    _reset_bot_state()
    with web_app._bot_state_lock:
        web_app._bot_state["is_running"] = True

    resp = client.post("/api/bot/start")

    assert resp.status_code == 409
    _reset_bot_state()


def test_api_bot_stop_terminates_process_and_updates_status():
    _reset_bot_state()
    fake_proc = MagicMock()
    with web_app._bot_state_lock:
        web_app._bot_state["is_running"] = True
        web_app._bot_state["process"] = fake_proc

    resp = client.post("/api/bot/stop")

    assert resp.status_code == 200
    fake_proc.terminate.assert_called_once()
    assert client.get("/api/bot/status").json()["running"] is False
    _reset_bot_state()


def test_api_bot_rss_add_list_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))

    add_resp = client.post("/api/bot/rss", json={"name": "My Feed", "url": "https://example.com/rss", "channel_id": "12345"})
    assert add_resp.status_code == 200

    list_resp = client.get("/api/bot/rss")
    feeds = list_resp.json()
    assert len(feeds) == 1
    assert feeds[0]["name"] == "My Feed"
    assert feeds[0]["channel_id"] == 12345

    del_resp = client.delete(f"/api/bot/rss/{feeds[0]['id']}")
    assert del_resp.status_code == 200
    assert client.get("/api/bot/rss").json() == []


def test_api_bot_rss_add_and_delete_record_audit_log_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    add_resp = client.post("/api/bot/rss", json={"name": "My Feed", "url": "https://example.com/rss", "channel_id": "12345"})
    assert add_resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "rss_feed_add")
    assert calls[0][1]["details"] == "My Feed"

    feed_id = client.get("/api/bot/rss").json()[0]["id"]
    del_resp = client.delete(f"/api/bot/rss/{feed_id}")
    assert del_resp.status_code == 200
    assert len(calls) == 2
    assert calls[1][0] == ("web", "rss_feed_delete")
    assert calls[1][1]["details"] == str(feed_id)


def test_api_bot_rss_add_rejects_non_numeric_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))
    resp = client.post("/api/bot/rss", json={"name": "x", "url": "y", "channel_id": "not-a-number"})
    assert resp.status_code == 400


def test_api_bot_rss_add_rejects_missing_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))
    resp = client.post("/api/bot/rss", json={"name": "", "url": "", "channel_id": "1"})
    assert resp.status_code == 400


def test_api_bot_steam_add_list_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))

    add_resp = client.post("/api/bot/steam", json={"name": "Some Game", "app_id": "730", "channel_id": "999"})
    assert add_resp.status_code == 200

    list_resp = client.get("/api/bot/steam")
    games = list_resp.json()
    assert len(games) == 1
    assert games[0]["name"] == "Some Game"
    assert games[0]["app_id"] == "730"

    del_resp = client.delete(f"/api/bot/steam/{games[0]['id']}")
    assert del_resp.status_code == 200
    assert client.get("/api/bot/steam").json() == []


def test_api_bot_steam_add_and_delete_record_audit_log_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))
    calls = []
    monkeypatch.setattr(web_app.audit_log, "record_action", lambda *a, **kw: calls.append((a, kw)))

    add_resp = client.post("/api/bot/steam", json={"name": "Some Game", "app_id": "730", "channel_id": "999"})
    assert add_resp.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == ("web", "steam_game_add")
    assert calls[0][1]["details"] == "Some Game"

    game_id = client.get("/api/bot/steam").json()[0]["id"]
    del_resp = client.delete(f"/api/bot/steam/{game_id}")
    assert del_resp.status_code == 200
    assert len(calls) == 2
    assert calls[1][0] == ("web", "steam_game_delete")
    assert calls[1][1]["details"] == str(game_id)


def test_api_bot_steam_add_rejects_non_numeric_channel(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "BOT_DB_PATH", str(tmp_path / "bot_test.db"))
    resp = client.post("/api/bot/steam", json={"name": "x", "app_id": "1", "channel_id": "not-a-number"})
    assert resp.status_code == 400


# --- Soundboard (6/N desktop-parity gaps): /api/soundboard/play ---

def test_api_soundboard_play_airhorn(monkeypatch):
    mock_play = MagicMock()
    monkeypatch.setattr(web_app, "play_board_sound", mock_play)

    resp = client.post("/api/soundboard/play", json={"sound": "airhorn"})

    assert resp.status_code == 200
    mock_play.assert_called_once_with(880, 400)


def test_api_soundboard_play_all_known_sounds_match_desktop(monkeypatch):
    mock_play = MagicMock()
    monkeypatch.setattr(web_app, "play_board_sound", mock_play)

    for sound, (freq, duration) in web_app.SOUNDBOARD_SOUNDS.items():
        resp = client.post("/api/soundboard/play", json={"sound": sound})
        assert resp.status_code == 200
        mock_play.assert_called_with(freq, duration)


def test_api_soundboard_play_rejects_unknown_sound(monkeypatch):
    mock_play = MagicMock()
    monkeypatch.setattr(web_app, "play_board_sound", mock_play)

    resp = client.post("/api/soundboard/play", json={"sound": "does-not-exist"})

    assert resp.status_code == 400
    mock_play.assert_not_called()


def test_api_soundboard_play_requires_same_origin(monkeypatch):
    mock_play = MagicMock()
    monkeypatch.setattr(web_app, "play_board_sound", mock_play)

    resp = client.post("/api/soundboard/play", json={"sound": "airhorn"}, headers={"origin": "https://evil.example.com"})

    assert resp.status_code == 403
    mock_play.assert_not_called()
