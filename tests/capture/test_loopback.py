# tests/capture/test_loopback.py
#
# utils/capture/loopback.py: PcmPacer - שמע המשחק נשאר צמוד לשעון גם כש-WASAPI לא מוסר כלום בזמן שקט. שעון מדומה.
from utils.capture.loopback import PcmPacer


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_silence_is_padded_so_audio_keeps_pace_with_the_clock():
    clock = Clock()
    pacer = PcmPacer(rate=1000, channels=2, clock=clock)     # 4000 בייט לשנייה
    assert pacer.pull() == b""                               # רגע ההתחלה
    clock.now += 0.5
    out = pacer.pull()
    assert out == bytes(2000)                                # חצי שנייה של שקט, בלי שום PCM מ-WASAPI


def test_real_audio_is_sent_first_and_the_rest_of_the_tick_is_silence():
    clock = Clock()
    pacer = PcmPacer(rate=1000, channels=2, clock=clock)
    pacer.pull()
    pacer.push(b"\x01" * 400)
    clock.now += 0.25                                        # 1000 בייט "בזמן"
    out = pacer.pull()
    assert out[:400] == b"\x01" * 400 and out[400:] == bytes(600)


def test_audio_beyond_the_tick_waits_for_the_next_one():
    clock = Clock()
    pacer = PcmPacer(rate=1000, channels=2, clock=clock)
    pacer.pull()
    pacer.push(b"\x02" * 3000)
    clock.now += 0.5
    assert pacer.pull() == b"\x02" * 2000
    clock.now += 0.25
    assert pacer.pull() == b"\x02" * 1000


def test_a_backlog_is_trimmed_instead_of_drifting_behind():
    pacer = PcmPacer(rate=1000, channels=2, max_lag_seconds=0.5, clock=Clock())
    for _ in range(10):
        pacer.push(b"\x03" * 1000)
    assert pacer._queued <= 2000


def test_output_never_splits_a_frame():
    clock = Clock()
    pacer = PcmPacer(rate=1000, channels=2, clock=clock)
    pacer.pull()
    clock.now += 0.0013                                      # 5.2 בייט - נחתך ל-4 (פריים שלם)
    assert len(pacer.pull()) % 4 == 0
