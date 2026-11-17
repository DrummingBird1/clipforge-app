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



def test_surround_is_folded_to_stereo_with_the_centre_in_both_sides():
    import struct

    from utils.capture import loopback
    frame = struct.pack("<6h", 1000, 2000, 500, 9999, 100, 200)        # FL FR FC LFE BL BR
    left, right = struct.unpack("<2h", loopback.to_stereo(frame, 6))
    assert (left, right) == (1420, 2490)                               # FL + 0.7*FC + 0.7*BL ; ה-LFE נזרק
    assert loopback.to_stereo(b"\x01\x02\x03\x04", 2) == b"\x01\x02\x03\x04"
    loud = struct.pack("<6h", 32000, 32000, 32000, 0, 32000, 32000)
    assert struct.unpack("<2h", loopback.to_stereo(loud, 6)) == (32767, 32767)      # בלי גלישה
    assert len(loopback.to_stereo(frame * 3 + b"\x00\x01", 6)) == 12   # שארית של פריים חלקי נזרקת


def test_the_sender_says_when_it_is_connected():
    from utils.capture import loopback
    sender = loopback.LoopbackSender(1, 48000, 2)
    assert not sender.connected.is_set() and sender.error is None


def test_clearing_the_pacer_drops_what_was_queued_and_restarts_its_clock():
    from utils.capture import loopback
    clock = Clock()
    pacer = loopback.PcmPacer(48000, 2, clock=clock)
    pacer.push(b"\x01" * 4000)
    pacer.pull()
    clock.now += 0.5
    pacer.clear()
    assert pacer.pull() == b""                                   # השעון התחיל מחדש: עוד לא עבר זמן
    clock.now += 0.01
    assert pacer.pull() == bytes(1920)                           # 10ms של שקט - מה שהיה בתור נזרק
