# utils/capture/loopback.py
#
# 16.11.2026 (2.0): שמע המשחק במחשב - WASAPI loopback (מה שיוצא לרמקולים) דרך pyaudiowpatch. ל-ffmpeg אין קלט wasapi,
# אז ה-PCM נשלח אליו בחיבור TCP מקומי: ffmpeg מאזין (-i tcp://127.0.0.1:<port>?listen=1) והשולח כאן מתחבר.
#
# מלכודת: WASAPI loopback לא מוסר כלום בזמן שקט. בלי תיקון, השמע "מתקצר" ונבלע מול הווידאו (פער שגדל עם כל הפסקה במשחק).
# PcmPacer קובע כמה בייטים *היו צריכים* לצאת לפי השעון, ומשלים שקט (אפסים) כשהתור ריק - הזרם נשאר צמוד לזמן אמת.
#
# 17.11.2026 (2.0.1), מהבדיקה המעמיקה:
#   - connected: אירוע שנדלק כשהחיבור ל-ffmpeg קם. המנוע מחכה לו, ולא מכריז "מקליט" על ffmpeg שעוד מחכה לשמע.
#   - ה-loopback נפתח במספר הערוצים של ההתקן עצמו (5.1 / 7.1 באוזניות סראונד ובמקלטי HDMI לא נפתחים כסטריאו),
#     וההמרה לסטריאו נעשית כאן (to_stereo). ffmpeg ממשיך לקבל סטריאו.
#   - אחרי החיבור ה-timeout של השליחה ארוך: ffmpeg שעדיין פותח מצלמה לא קורא את השמע כמה שניות, ו-2 שניות קטעו את
#     שמע המשחק לכל ההקלטה.
import collections
import socket
import threading
import time
from typing import Callable, Deque, Optional

SAMPLE_BYTES = 2           # s16le
TICK_SECONDS = 0.01
CONNECT_TIMEOUT_SECONDS = 10.0
SEND_TIMEOUT_SECONDS = 30.0
MAX_LEAD_SECONDS = 60.0


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

    def clear(self) -> None:
        """זורק את מה שבתור ומתחיל את השעון מחדש."""
        with self._lock:
            self._queue.clear()
            self._queued = 0
        self._start, self._sent = None, 0

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


def to_stereo(data: bytes, channels: int) -> bytes:
    """s16le עם channels ערוצים (סדר WASAPI: FL FR FC LFE BL BR SL SR) -> סטריאו. המרכז (דיבור) והאחוריים נכנסים לשני
    הצדדים ב-0.7, ה-LFE נזרק. סטריאו ומונו חוזרים כמו שהם."""
    if channels <= 2:
        return data
    import numpy as np
    frames = np.frombuffer(data[:len(data) // (SAMPLE_BYTES * channels) * SAMPLE_BYTES * channels], dtype="<i2").reshape(-1, channels).astype(np.float32)
    left, right = frames[:, 0].copy(), frames[:, 1].copy()
    if channels >= 3:
        left += 0.7 * frames[:, 2]
        right += 0.7 * frames[:, 2]
    for index in range(4, channels):             # אחוריים וצדדיים: זוגי = שמאל, אי-זוגי = ימין
        if index % 2 == 0:
            left += 0.7 * frames[:, index]
        else:
            right += 0.7 * frames[:, index]
    return np.clip(np.stack([left, right], axis=1), -32768, 32767).astype("<i2").tobytes()


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
        self.start_mono = 0.0     # רגע ההתחלה המשותף של ההקלטה (time.monotonic()); 0 = בלי יישור
        self.error: Optional[str] = None
        self.connected = threading.Event()
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
            device_channels = max(1, int(device.get("maxInputChannels") or self.channels))
            open_channels = device_channels if device_channels > 2 else self.channels   # סראונד נפתח כמו שהוא

            def on_audio(data, frame_count, time_info, status):
                pacer.push(to_stereo(data, open_channels) if open_channels > 2 else data)
                return (None, pa.paContinue)

            stream = audio.open(format=pa.paInt16, channels=open_channels, rate=self.rate, input=True,
                                input_device_index=device["index"], frames_per_buffer=int(self.rate * TICK_SECONDS),
                                stream_callback=on_audio)
            conn = self._connect()
            if conn is None:
                self.error = "ffmpeg לא קיבל את חיבור השמע"
                return
            conn.settimeout(SEND_TIMEOUT_SECONDS)
            if self.start_mono:
                # 17.11.2026: הזרם מתחיל ברגע ההתחלה המשותף. שקט באורך הזמן שעבר מאז (ffmpeg נפתח, התחברנו), ומה שנאסף
                # לפני החיבור נזרק - כך הדגימה הראשונה של השמע האמיתי יושבת בדיוק בזמן שבו היא הוקלטה.
                pacer.clear()
                lead = min(MAX_LEAD_SECONDS, max(0.0, time.monotonic() - self.start_mono))
                conn.sendall(bytes(int(lead * self.rate) * pacer.frame_bytes))
            self.connected.set()
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
