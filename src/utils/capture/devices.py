# utils/capture/devices.py
#
# 16.11.2026 (2.0): התקני DirectShow - כרטיסי לכידה (Elgato, AVerMedia...), מצלמות ומיקרופונים - מהפלט של ffmpeg:
#   ffmpeg -list_devices true -f dshow -i dummy            -> רשימת ההתקנים (וידאו / אודיו, עם השם החלופי)
#   ffmpeg -list_options true -f dshow -i video="<שם>"     -> המצבים שהכרטיס תומך בהם (רזולוציה, fps, פורמט)
# הפענוח טהור (טקסט -> רשימות), ונבדק מול פלט לדוגמה. פרופילי הקונסולות בוחרים מצב שמתאים לקונסולה מתוך מה שהכרטיס מציע.
import re
import subprocess
from typing import Callable, Dict, List, NamedTuple, Optional

_DEVICE_LINE = re.compile(r'\]\s+"(?P<name>.+)"\s+\((?P<kind>video|audio|none)\)\s*$')
_ALT_LINE = re.compile(r'\]\s+Alternative name\s+"(?P<alt>.+)"\s*$')
_OPTION_LINE = re.compile(
    r"(?:vcodec=(?P<vcodec>\S+)|pixel_format=(?P<pix>\S+))\s+"
    r"min\s+s=(?P<min_w>\d+)x(?P<min_h>\d+)\s+fps=(?P<min_fps>[\d.]+)\s+"
    r"max\s+s=(?P<max_w>\d+)x(?P<max_h>\d+)\s+fps=(?P<max_fps>[\d.]+)")
_LIST_TIMEOUT_SECONDS = 20


class Device(NamedTuple):
    name: str
    kind: str          # video / audio
    alternative: str   # ה-"Alternative name" (מזהה יציב גם כששני התקנים באותו שם)


class Mode(NamedTuple):
    codec: str         # pixel format (yuyv422, nv12...) או vcodec (mjpeg, h264)
    width: int
    height: int
    min_fps: float
    max_fps: float


class ConsoleProfile(NamedTuple):
    id: str
    label: str
    width: int
    height: int
    fps: int
    note: str


# מה שהקונסולה מוציאה ב-HDMI כברירת מחדל. הכרטיס יכול להציע פחות - pick_mode בוחר את הקרוב ביותר שהוא כן תומך בו.
CONSOLE_PROFILES = (
    ConsoleProfile("ps5", "PlayStation 5", 3840, 2160, 60,
                   "בהגדרות הקונסולה: מערכת > HDMI > כבה את 'הפעל HDCP', אחרת הכרטיס מקבל מסך שחור. HDR מומלץ לכבות."),
    ConsoleProfile("ps4", "PlayStation 4", 1920, 1080, 60,
                   "בהגדרות הקונסולה: מערכת > כבה את 'הפעל HDCP', אחרת הכרטיס מקבל מסך שחור."),
    ConsoleProfile("xbox_series", "Xbox Series X|S", 3840, 2160, 60,
                   "Xbox לא מצפין משחקים ב-HDCP; אפליקציות וידאו כן. HDR מומלץ לכבות להקלטה."),
    ConsoleProfile("xbox_one", "Xbox One", 1920, 1080, 60, "Xbox לא מצפין משחקים ב-HDCP; אפליקציות וידאו כן."),
    ConsoleProfile("switch2", "Nintendo Switch 2", 3840, 2160, 60, "בתחנת העגינה בלבד - במצב נייד אין יציאת HDMI."),
    ConsoleProfile("switch", "Nintendo Switch", 1920, 1080, 60, "בתחנת העגינה בלבד - במצב נייד אין יציאת HDMI."),
)


def parse_device_list(stderr: str) -> List[Device]:
    devices: List[Device] = []
    for line in (stderr or "").splitlines():
        match = _DEVICE_LINE.search(line)
        if match and match.group("kind") in ("video", "audio"):
            devices.append(Device(match.group("name"), match.group("kind"), ""))
            continue
        alt = _ALT_LINE.search(line)
        if alt and devices and not devices[-1].alternative:
            devices[-1] = devices[-1]._replace(alternative=alt.group("alt"))
    return devices


def parse_device_options(stderr: str) -> List[Mode]:
    modes: List[Mode] = []
    seen = set()
    for line in (stderr or "").splitlines():
        match = _OPTION_LINE.search(line)
        if not match:
            continue
        codec = match.group("vcodec") or match.group("pix")
        mode = Mode(codec, int(match.group("max_w")), int(match.group("max_h")),
                    float(match.group("min_fps")), float(match.group("max_fps")))
        if mode not in seen:
            seen.add(mode)
            modes.append(mode)
    return modes


def pick_mode(modes: List[Mode], width: int, height: int, fps: int, prefer: str = "resolution") -> Optional[Mode]:
    """המצב הקרוב ביותר ליעד, מתוך המצבים שלא עוברים אותו. prefer="resolution" (ברירת המחדל): קודם הרזולוציה הגדולה, אחר כך
    קצב שמגיע ליעד. prefer="fps": קודם מצב שמגיע לקצב היעד (1080p60 לפני 4K30), אחר כך רזולוציה. בשניהם - העדפה לפורמט
    לא דחוס (yuyv422/nv12 - בלי פענוח MJPEG על ה-CPU). בלי מצבים - None (ffmpeg יבחר בעצמו)."""
    if not modes:
        return None
    fitting = [m for m in modes if m.width <= width and m.height <= height] or modes

    def score(mode: Mode):
        uncompressed = mode.codec not in ("mjpeg", "h264", "hevc")
        reaches = min(mode.max_fps, fps) >= fps - 0.5
        area = mode.width * mode.height
        if prefer == "fps":
            return (reaches, area, min(mode.max_fps, fps), uncompressed)
        return (area, min(mode.max_fps, fps), uncompressed)

    return max(fitting, key=score)


# 17.11.2026 (2.0.1), מבדיקה על כרטיס אמיתי: כרטיסי USB זולים מכריזים על 1080p ב-60 פריימים ונותנים 30 - חצי מהחבילות
# מגיעות שבורות, וההקלטה יצאה ב-30 עם תווית של 60. לפני ההקלטה מודדים שנייה וחצי של המצב שנבחר; כשהכרטיס נותן פחות
# ממה שהכריז, המצב מתוקן לקצב האמיתי ובוחרים שוב.
MEASURE_SECONDS = 2.0
COMMON_RATES = (24.0, 25.0, 30.0, 50.0, 60.0, 120.0)
_FRAME_COUNT = re.compile(r"frame=\s*(\d+)")


def real_rate(measured: float) -> float:
    """הקצב הנפוץ הקרוב (29.6 -> 30), או המדידה עצמה כשהיא רחוקה מכולם."""
    nearest = min(COMMON_RATES, key=lambda rate: abs(rate - measured))
    return nearest if abs(nearest - measured) <= nearest * 0.08 else round(measured, 2)


def measure_mode(ffmpeg_exe: str, device_name: str, mode: Mode, fps: float, creationflags: int = 0,
                 seconds: float = MEASURE_SECONDS) -> Optional[float]:
    """כמה פריימים תקינים בשנייה הכרטיס באמת נותן במצב הזה (פענוח ל-null, בלי קידוד). None כשאי אפשר למדוד."""
    cmd = [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-stats", "-f", "dshow", "-rtbufsize", "256M",
           "-video_size", f"{mode.width}x{mode.height}", "-vcodec" if mode.codec in ("mjpeg", "h264", "hevc") else "-pixel_format", mode.codec,
           "-framerate", f"{fps:g}", "-i", f"video={device_name}", "-t", f"{seconds:g}", "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=_LIST_TIMEOUT_SECONDS, creationflags=creationflags)
    except (OSError, subprocess.SubprocessError):
        return None
    counts = _FRAME_COUNT.findall(result.stderr or "")
    if result.returncode != 0 or not counts:
        return None
    return int(counts[-1]) / seconds


def choose_mode(modes: List[Mode], width: int, height: int, fps: int, prefer: str,
                measure: Callable[[Mode, float], Optional[float]]) -> tuple:
    """(המצב, הקצב שבאמת מקליטים בו, הערה או None). measure(mode, fps) מחזיר את הקצב האמיתי או None."""
    note = None
    for _attempt in range(4):
        mode = pick_mode(modes, width, height, fps, prefer)
        if mode is None:
            return None, float(fps), note
        asked = min(float(fps), mode.max_fps)
        measured = measure(mode, asked)
        if measured is None or measured >= asked * 0.85:
            return mode, asked, note
        truth = real_rate(measured)
        note = (mode, asked, truth) if note is None else note      # מה שהכרטיס הכריז ומה שנתן - להודעה
        modes = [m._replace(max_fps=truth) if m == mode else m for m in modes]
    return mode, min(float(fps), mode.max_fps), note


def list_devices(ffmpeg_exe: str, creationflags: int = 0) -> List[Device]:
    try:
        result = subprocess.run([ffmpeg_exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=_LIST_TIMEOUT_SECONDS, creationflags=creationflags)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_device_list(result.stderr)


def list_modes(ffmpeg_exe: str, device_name: str, creationflags: int = 0) -> List[Mode]:
    try:
        result = subprocess.run([ffmpeg_exe, "-hide_banner", "-list_options", "true", "-f", "dshow", "-i", f"video={device_name}"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=_LIST_TIMEOUT_SECONDS, creationflags=creationflags)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_device_options(result.stderr)


def console_profile(profile_id: str) -> Optional[ConsoleProfile]:
    return next((p for p in CONSOLE_PROFILES if p.id == profile_id), None)


def as_dicts(devices: List[Device]) -> Dict[str, List[Dict[str, str]]]:
    return {kind: [{"name": d.name, "alternative": d.alternative} for d in devices if d.kind == kind] for kind in ("video", "audio")}
