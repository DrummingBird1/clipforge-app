# utils/capture/command.py
#
# 16.11.2026 (2.0): פקודת ffmpeg של מנוע ההקלטה המובנה - טהור, נבדק מול פקודות צפויות.
#
# מקורות:
#   - מסך / משחק במחשב: ddagrab (Desktop Duplication, על ה-GPU) -> hwdownload ל-CPU. נפילה: gdigrab (איטי, בלי GPU).
#   - קונסולה: כרטיס לכידה ב-DirectShow - וידאו והשמע של ה-HDMI באותו קלט (מסונכרנים), במצב שבחר devices.pick_mode.
#   - שמע המשחק במחשב: WASAPI loopback מ-loopback.py, כ-PCM גולמי ב-named pipe (ל-ffmpeg אין קלט wasapi).
#   - מיקרופון: DirectShow audio. Facecam: מצלמה ב-DirectShow, stream וידאו שני באותו קובץ (מסונכרן לאותו שעון).
# ערוצים: וידאו 0 = המשחק, וידאו 1 = facecam; שמע 0 = המשחק, שמע 1 = המיקרופון - העורך מאזן ביניהם (שלב 6).
# יעדים: הקלטה רגילה ל-MKV (לא נהרס בקריסה; remux ל-MP4 בסוף), או replay - קטעים קצרים לתיקייה (ring_buffer).
from dataclasses import dataclass, field
from typing import List, Optional

from utils.capture import ring_buffer

PCM_RATE = 48000
PCM_CHANNELS = 2
LISTEN_TIMEOUT_MS = 20000   # 17.11.2026: בלי זה ffmpeg מחכה לנצח לשולח שלא הגיע


@dataclass
class CaptureSpec:
    mode: str = "record"                       # record / replay
    source: str = "screen"                     # screen / device
    output: str = ""                           # record: קובץ .mkv | replay: תיקיית הקטעים
    fps: int = 60
    screen_index: int = 0                      # ddagrab output_idx (המסך)
    use_gdigrab: bool = False                  # נפילה כש-ddagrab לא עובד (משחק ב-exclusive fullscreen, מחשב ישן)
    device_video: str = ""                     # כרטיס לכידה (source=device)
    device_audio: str = ""                     # השמע של הכרטיס (HDMI) - בדרך כלל התקן אודיו נפרד באותו שם
    device_size: Optional[str] = None          # "1920x1080" ממצב שנבחר
    device_codec: Optional[str] = None         # pixel_format / vcodec של המצב
    device_fps: Optional[str] = None           # הקצב המדויק של המצב ("59.94") ל-dshow; fps נשאר שלם בשביל ה-GOP
    game_audio_port: int = 0                   # loopback של המחשב (source=screen): ffmpeg מאזין ב-tcp://127.0.0.1:<port>
    game_audio_rate: int = PCM_RATE
    game_audio_channels: int = PCM_CHANNELS
    mic: str = ""                              # התקן מיקרופון ב-DirectShow
    facecam: str = ""                          # מצלמה ב-DirectShow
    video_args: List[str] = field(default_factory=lambda: ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"])
    audio_bitrate: str = "192k"
    segment_seconds: int = ring_buffer.DEFAULT_SEGMENT_SECONDS


def _dshow_device(kind: str, name: str) -> str:
    return f"{kind}={name}"


def build_command(ffmpeg_exe: str, spec: CaptureSpec) -> List[str]:
    if spec.mode not in ("record", "replay") or spec.source not in ("screen", "device"):
        raise ValueError(f"מצב/מקור לא מוכר: {spec.mode} / {spec.source}")
    if not spec.output:
        raise ValueError("חסר יעד להקלטה")
    cmd = [ffmpeg_exe, "-hide_banner", "-y", "-loglevel", "warning", "-stats"]
    inputs = 0
    video_maps, audio_maps, filters = [], [], []

    if spec.source == "screen":
        if spec.use_gdigrab:
            cmd += ["-thread_queue_size", "512", "-f", "gdigrab", "-framerate", str(spec.fps), "-i", "desktop"]
            filters.append(f"[{inputs}:v]format=yuv420p[game]")
        else:
            cmd += ["-f", "lavfi", "-i", f"ddagrab=output_idx={spec.screen_index}:framerate={spec.fps}"]
            filters.append(f"[{inputs}:v]hwdownload,format=bgra,format=yuv420p[game]")
        video_maps.append("[game]")
        inputs += 1
        if spec.game_audio_port:
            cmd += ["-thread_queue_size", "1024", "-f", "s16le", "-ar", str(spec.game_audio_rate),
                    "-ac", str(spec.game_audio_channels), "-i",
                    f"tcp://127.0.0.1:{spec.game_audio_port}?listen=1&listen_timeout={LISTEN_TIMEOUT_MS}"]
            audio_maps.append(f"{inputs}:a")
            inputs += 1
    else:
        if not spec.device_video:
            raise ValueError("לא נבחר כרטיס לכידה")
        device = _dshow_device("video", spec.device_video)
        if spec.device_audio:
            device += ":" + _dshow_device("audio", spec.device_audio)
        cmd += ["-thread_queue_size", "1024", "-f", "dshow", "-rtbufsize", "512M"]
        if spec.device_size:
            cmd += ["-video_size", spec.device_size]
        if spec.device_codec:
            cmd += ["-vcodec" if spec.device_codec in ("mjpeg", "h264", "hevc") else "-pixel_format", spec.device_codec]
        cmd += ["-framerate", spec.device_fps or str(spec.fps), "-i", device]
        filters.append(f"[{inputs}:v]format=yuv420p[game]")
        video_maps.append("[game]")
        if spec.device_audio:
            audio_maps.append(f"{inputs}:a")
        inputs += 1

    if spec.mic:
        cmd += ["-thread_queue_size", "1024", "-f", "dshow", "-i", _dshow_device("audio", spec.mic)]
        audio_maps.append(f"{inputs}:a")
        inputs += 1
    if spec.facecam:
        cmd += ["-thread_queue_size", "512", "-f", "dshow", "-i", _dshow_device("video", spec.facecam)]
        filters.append(f"[{inputs}:v]format=yuv420p[cam]")
        video_maps.append("[cam]")
        inputs += 1

    cmd += ["-filter_complex", ";".join(filters)]
    for label in video_maps:
        cmd += ["-map", label]
    for stream in audio_maps:
        cmd += ["-map", stream]
    cmd += list(spec.video_args)
    cmd += ["-g", str(spec.fps * spec.segment_seconds), "-keyint_min", str(spec.fps * spec.segment_seconds)]
    if audio_maps:
        cmd += ["-c:a", "aac", "-b:a", spec.audio_bitrate, "-ar", str(PCM_RATE)]
    titles = ["game", "facecam"][:len(video_maps)]
    for i, title in enumerate(titles):
        cmd += [f"-metadata:s:v:{i}", f"title={title}"]
    has_game_audio = bool(spec.device_audio) if spec.source == "device" else bool(spec.game_audio_port)
    audio_titles = ["game", "mic"] if has_game_audio else ["mic"]
    for i, title in enumerate(audio_titles[:len(audio_maps)]):
        cmd += [f"-metadata:s:a:{i}", f"title={title}"]

    if spec.mode == "record":
        return cmd + ["-f", "matroska", spec.output]
    pattern = spec.output.rstrip("\\/") + "/" + ring_buffer.SEGMENT_PATTERN
    return cmd + ["-f", "segment", "-segment_time", str(spec.segment_seconds), "-segment_format", "mpegts",
                  "-reset_timestamps", "1", pattern]


def remux_command(ffmpeg_exe: str, mkv_path: str, mp4_path: str) -> List[str]:
    """סוף הקלטה: MKV (עמיד לקריסה) -> MP4 בלי קידוד מחדש, עם כל הערוצים והשמות שלהם."""
    return [ffmpeg_exe, "-hide_banner", "-y", "-i", mkv_path, "-map", "0", "-c", "copy", "-movflags", "+faststart", mp4_path]
