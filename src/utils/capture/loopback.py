# utils/capture/loopback.py
#
# 16.11.2026 (2.0): שמע המשחק במחשב - WASAPI loopback (מה שיוצא לרמקולים) דרך pyaudiowpatch. ל-ffmpeg אין קלט wasapi,
# אז ה-PCM נשלח אליו בחיבור TCP מקומי: ffmpeg מאזין (-i tcp://127.0.0.1:<port>?listen=1) והשולח כאן מתחבר.
#
# מלכודת: WASAPI loopback לא מוסר כלום בזמן שקט. בלי תיקון, השמע "מתקצר" ונבלע מול הווידאו (פער שגדל עם כל הפסקה במשחק).
# PcmPacer קובע כמה בייטים *היו צריכים* לצאת לפי השעון, ומשלים שקט (אפסים) כשהתור ריק - הזרם נשאר צמוד לזמן אמת.
import collections
import socket
import threading
import time
from typing import Callable, Deque, Optional

SAMPLE_BYTES = 2           # s16le
TICK_SECONDS = 0.01
CONNECT_TIMEOUT_SECONDS = 10.0


class PcmPacer:
    """מקבל חתיכות PCM כשהן מגיעות (push), ומוציא בדיוק את מה שהשעון דורש (pull): מהתור, ושקט כשהוא ריק.
    יותר מדי בתור (מעל max_lag_seconds) - הישן נזרק, כדי שהשמע לא ייגרר מאחור."""

    def __init__(self, rate: int, channels: int, max_lag_seconds: float = 0.5, clock: Callable[[], float] = time.monotonic):
        self.frame_bytes = SAMPLE_BYTES * channels
        self.bytes_per_second = rate * self.frame_bytes
        self.max_lag_bytes = int(max_lag_seconds * self.bytes_per_second) // self.frame_bytes * self.frame_bytes
        self._clock = clock
        self._start: Optional[float] = None
        self._sent = 0
        self._queue: Deque[bytes] = collections.deque()
        self._queued = 0
        self._lock = threading.Lock()

    def push(self, data: bytes) -> None:
        with self._lock:
            self._queue.append(data)
            self._queued += len(data)
            while self._queued > self.max_lag_bytes and len(self._queue) > 1:
                self._queued -= len(self._queue.popleft())

    def pull(self) -> bytes:
        now = self._clock()
        if self._start is None:
            self._start = now
        due = int((now - self._start) * self.bytes_per_second) // self.frame_bytes * self.frame_bytes - self._sent
        if due <= 0:
            return b""
        out = bytearray()
        with self._lock:
            while self._queue and len(out) < due:
                chunk = self._queue.popleft()
                take = due - len(out)
                out += chunk[:take]
                if len(chunk) > take:
                    self._queue.appendleft(chunk[take:])
                self._queued -= min(len(chunk), take)
        if len(out) < due:
            out += bytes(due - len(out))      # שקט
        self._sent += len(out)
        return bytes(out)


def available() -> bool:
    try:
        import pyaudiowpatch  # noqa: F401
        return True
    except Exception:
        return False


def default_format() -> Optional[tuple]:
    """(rate, channels) של ה-loopback של התקן ההשמעה הנוכחי, או None כשאין."""
    try:
        import pyaudiowpatch as pa
        audio = pa.PyAudio()
        try:
            device = audio.get_default_wasapi_loopback()
            return int(device["defaultSampleRate"]), max(1, min(2, int(device["maxInputChannels"])))
        finally:
            audio.terminate()
    except Exception:
        return None


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LoopbackSender:
    """thread אחד: פותח את ה-loopback, מתחבר ל-ffmpeg ושולח PCM צמוד לשעון עד stop(). שגיאה - נשמרת ב-error."""

    def __init__(self, port: int, rate: int, channels: int):
        self.port, self.rate, self.channels = port, rate, channels
        self.error: Optional[str] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="clipforge-loopback", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _connect(self) -> Optional[socket.socket]:
        deadline = time.monotonic() + CONNECT_TIMEOUT_SECONDS
        while not self._stop.is_set() and time.monotonic() < deadline:
            try:
                return socket.create_connection(("127.0.0.1", self.port), timeout=2)
            except OSError:
                time.sleep(0.1)   # ffmpeg עוד לא מאזין
        return None

    def _run(self) -> None:
        try:
            import pyaudiowpatch as pa
        except Exception as e:
            self.error = f"pyaudiowpatch לא זמין: {e}"
            return
        pacer = PcmPacer(self.rate, self.channels)
        audio = pa.PyAudio()
        stream = None
        conn = None
        try:
            device = audio.get_default_wasapi_loopback()

            def on_audio(data, frame_count, time_info, status):
                pacer.push(data)
                return (None, pa.paContinue)

            stream = audio.open(format=pa.paInt16, channels=self.channels, rate=self.rate, input=True,
                                input_device_index=device["index"], frames_per_buffer=int(self.rate * TICK_SECONDS),
                                stream_callback=on_audio)
            conn = self._connect()
            if conn is None:
                self.error = "ffmpeg לא קיבל את חיבור השמע"
                return
            while not self._stop.is_set():
                chunk = pacer.pull()
                if chunk:
                    conn.sendall(chunk)
                time.sleep(TICK_SECONDS)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass   # ffmpeg סגר את הקלט - סוף רגיל של ההקלטה, לא שגיאה
        except OSError as e:
            if not self._stop.is_set():
                self.error = f"שמע המשחק נקטע: {e}"
        except Exception as e:
            self.error = f"שמע המשחק: {e}"
        finally:
            for closer in (lambda: stream and stream.stop_stream(), lambda: stream and stream.close(),
                           lambda: conn and conn.close(), audio.terminate):
                try:
                    closer()
                except Exception:
                    pass
