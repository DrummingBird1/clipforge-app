# utils/capture/devices.py
#
# 16.11.2026 (2.0): התקני DirectShow - כרטיסי לכידה (Elgato, AVerMedia...), מצלמות ומיקרופונים - מהפלט של ffmpeg:
#   ffmpeg -list_devices true -f dshow -i dummy            -> רשימת ההתקנים (וידאו / אודיו, עם השם החלופי)
#   ffmpeg -list_options true -f dshow -i video="<שם>"     -> המצבים שהכרטיס תומך בהם (רזולוציה, fps, פורמט)
# הפענוח טהור (טקסט -> רשימות), ונבדק מול פלט לדוגמה. פרופילי הקונסולות בוחרים מצב שמתאים לקונסולה מתוך מה שהכרטיס מציע.
import re
import subprocess
from typing import Dict, List, NamedTuple, Optional

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


def pick_mode(modes: List[Mode], width: int, height: int, fps: int) -> Optional[Mode]:
    """המצב הקרוב ביותר ליעד: קודם רזולוציה שלא עוברת את היעד (הכי גדולה), אחר כך fps שמגיע ליעד, ואז העדפה לפורמט
    לא דחוס (yuyv422/nv12 - בלי פענוח MJPEG על ה-CPU). בלי מצבים - None (ffmpeg יבחר בעצמו)."""
    if not modes:
        return None
    fitting = [m for m in modes if m.width <= width and m.height <= height] or modes

    def score(mode: Mode):
        uncompressed = mode.codec not in ("mjpeg", "h264", "hevc")
        return (mode.width * mode.height, min(mode.max_fps, fps), uncompressed)

    return max(fitting, key=score)


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
