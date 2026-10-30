# tests/infra/test_sound.py


from utils.shared import sound


def test_beep_thread_calls_winsound_beep_with_given_args(monkeypatch):
    calls = []
    monkeypatch.setattr(sound.winsound, "Beep", lambda freq, duration: calls.append((freq, duration)))

    sound._beep_thread(523, 80)

    assert calls == [(523, 80)]


def test_beep_thread_swallows_exceptions_from_winsound(monkeypatch):
    monkeypatch.setattr(sound.winsound, "Beep", lambda *a: (_ for _ in ()).throw(RuntimeError("no audio device")))

    sound._beep_thread(523, 80)  # לא אמור לזרוק - כשל בהשמעת צליל לא אמור להפיל את הריצה


def test_beep_thread_does_nothing_on_non_windows_platform(monkeypatch):
    monkeypatch.setattr(sound.sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(sound.winsound, "Beep", lambda freq, duration: calls.append((freq, duration)))

    sound._beep_thread(523, 80)

    assert calls == []


def test_play_board_sound_spawns_a_daemon_thread_targeting_beep_thread(monkeypatch):
    started = {}

    class _FakeThread:
        def __init__(self, target, args, daemon):
            started["target"] = target
            started["args"] = args
            started["daemon"] = daemon

        def start(self):
            started["started"] = True

    monkeypatch.setattr(sound.threading, "Thread", _FakeThread)

    sound.play_board_sound(523, 80)

    assert started["target"] is sound._beep_thread
    assert started["args"] == (523, 80)
    assert started["daemon"] is True
    assert started["started"] is True


def test_play_system_sound_success_plays_three_ascending_tones(monkeypatch):
    calls = []
    monkeypatch.setattr(sound, "play_board_sound", lambda freq, duration: calls.append((freq, duration)))

    sound.play_system_sound("success")

    assert calls == [(523, 80), (659, 80), (784, 80)]


def test_play_system_sound_error_plays_two_low_tones(monkeypatch):
    calls = []
    monkeypatch.setattr(sound, "play_board_sound", lambda freq, duration: calls.append((freq, duration)))

    sound.play_system_sound("error")

    assert calls == [(220, 120), (147, 250)]


def test_play_system_sound_start_plays_two_tones(monkeypatch):
    calls = []
    monkeypatch.setattr(sound, "play_board_sound", lambda freq, duration: calls.append((freq, duration)))

    sound.play_system_sound("start")

    assert calls == [(587, 80), (880, 100)]


def test_play_system_sound_unknown_type_plays_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(sound, "play_board_sound", lambda freq, duration: calls.append((freq, duration)))

    sound.play_system_sound("not-a-real-type")

    assert calls == []
