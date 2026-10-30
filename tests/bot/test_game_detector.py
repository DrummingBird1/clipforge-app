# tests/bot/test_game_detector.py
from types import SimpleNamespace


import utils.media.game_detector as game_detector


class _FakeProc:
    def __init__(self, name, cmdline=None, exe=None):
        self.info = {"name": name, "cmdline": cmdline or [], "exe": exe}
        self._killed = False

    def kill(self):
        self._killed = True


def _fake_psutil(processes):
    return SimpleNamespace(process_iter=lambda _fields: iter(processes))


def test_returns_none_when_psutil_unavailable(monkeypatch):
    monkeypatch.setattr(game_detector, "psutil", None)
    assert game_detector.check_active_game() is None


def test_detects_known_game_process(monkeypatch):
    monkeypatch.setattr(game_detector, "psutil", _fake_psutil([_FakeProc("RocketLeague.exe")]))
    assert game_detector.check_active_game() == "Rocket League"


def test_no_game_process_returns_none(monkeypatch):
    monkeypatch.setattr(game_detector, "psutil", _fake_psutil([_FakeProc("explorer.exe"), _FakeProc("chrome.exe")]))
    assert game_detector.check_active_game() is None


def test_javaw_only_counts_as_minecraft_with_matching_cmdline(monkeypatch):
    # javaw.exe הוא ה-launcher הגנרי של כל אפליקציית Java - בלי "minecraft"
    # בשורת הפקודה זה IDE/כלי אחר, לא משחק.
    monkeypatch.setattr(game_detector, "psutil", _fake_psutil([_FakeProc("javaw.exe", cmdline=["javaw", "-jar", "idea.jar"])]))
    assert game_detector.check_active_game() is None

    monkeypatch.setattr(game_detector, "psutil", _fake_psutil([_FakeProc("javaw.exe", cmdline=["javaw", "-jar", "minecraft.jar"])]))
    assert game_detector.check_active_game() == "Green"


def test_turbo_mode_kills_banned_background_processes(monkeypatch):
    monkeypatch.setattr(game_detector, "killed_processes_paths", [])
    chrome = _FakeProc("chrome.exe", exe="C:/chrome.exe")
    game = _FakeProc("rocketleague.exe")

    call_count = {"n": 0}

    def process_iter(_fields):
        call_count["n"] += 1
        return iter([game] if call_count["n"] == 1 else [chrome])

    monkeypatch.setattr(game_detector, "psutil", SimpleNamespace(process_iter=process_iter))

    result = game_detector.check_active_game(turbo_mode_active=True)

    assert result == "Rocket League"
    assert chrome._killed is True
    assert "C:/chrome.exe" in game_detector.killed_processes_paths


def test_restore_background_processes_relaunches_and_clears(monkeypatch, tmp_path):
    fake_exe = tmp_path / "app.exe"
    fake_exe.write_text("")
    monkeypatch.setattr(game_detector, "killed_processes_paths", [str(fake_exe)])

    launched = []
    monkeypatch.setattr(game_detector.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    game_detector.restore_background_processes()

    assert launched == [[str(fake_exe)]]
    assert game_detector.killed_processes_paths == []


def test_restore_background_processes_skips_missing_files(monkeypatch):
    monkeypatch.setattr(game_detector, "killed_processes_paths", ["Z:/does/not/exist.exe"])
    launched = []
    monkeypatch.setattr(game_detector.subprocess, "Popen", lambda args, **kwargs: launched.append(args))

    game_detector.restore_background_processes()

    assert launched == []
    assert game_detector.killed_processes_paths == []
