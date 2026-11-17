# utils/media/encoders.py
#
# 16.11.2026 (ClipForge 2.0): מקודד הווידאו לפי הכרטיס שיש במחשב - NVIDIA (NVENC), AMD (AMF), Intel (QSV) או CPU.
# עד עכשיו hevc/av1 היו תמיד *_nvenc, ומחשב עם AMD/Intel נפל בכל רינדור כזה.
#
# - הבחירה: data/encoder_settings.json {"backend": "auto"|"nvenc"|"amf"|"qsv"|"cpu"}; ברירת המחדל auto.
#   CLIPFORGE_ENCODER_BACKEND גובר על הקובץ, ודגל --encoder-backend של הסקריפט גובר על שניהם.
#   tests/conftest.py קובע nvenc לכל הריצה - פקודות הזהב (NVIDIA) לא תלויות בכרטיס של המחשב שמריץ את הטסטים.
# - auto: הבדיקה (detect_backends) מריצה קידוד זעיר אמיתי לכל מקודד - כמו nvenc_probe - ונשמרת במטמון
#   (workspace/.cache/encoders.json) לפי ffmpeg (נתיב, גודל, זמן שינוי). סדר העדיפות: nvenc, amf, qsv, ואז cpu.
#   כשהבדיקה לא הצליחה להריץ ffmpeg בכלל - nvenc, ההתנהגות הקודמת (הרינדור ייכשל ממילא בלי ffmpeg).
# - מקודד שנבחר במפורש ולא קיים במחשב: הבא בתור שקיים, עם הודעה (resolve_backend מחזיר גם את הסיבה).
# - h264 נשאר libx264 בכל מקרה: במסך הוא "תאימות מקסימלית (CPU)", ומי שבחר בו בחר CPU.
# - nvenc מחזיר בדיוק את CODEC_ARGS הקיים, בייט-בבייט (קובץ הזהב של עורך-העל).
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from utils.shared import data_paths
from utils.shared.atomic_write import atomic_write_json

BACKENDS = ("nvenc", "amf", "qsv", "cpu")
CHOICES = ("auto",) + BACKENDS
HARDWARE = ("nvenc", "amf", "qsv")
GPU_CODECS = ("hevc", "av1")
ENV_VAR = "CLIPFORGE_ENCODER_BACKEND"
LABELS = {"auto": "אוטומטי", "nvenc": "NVIDIA (NVENC)", "amf": "AMD (AMF)", "qsv": "Intel (Quick Sync)", "cpu": "CPU"}

_ENCODER_NAMES = {
    ("nvenc", "hevc"): "hevc_nvenc", ("nvenc", "av1"): "av1_nvenc",
    ("amf", "hevc"): "hevc_amf", ("amf", "av1"): "av1_amf",
    ("qsv", "hevc"): "hevc_qsv", ("qsv", "av1"): "av1_qsv",
    ("cpu", "hevc"): "libx265", ("cpu", "av1"): "libsvtav1",
}
# ברירות המחדל של הסטודיו: preset p5 ו-cq 19 (hevc) / 24 (av1) ב-NVENC. בשאר המקודדים - הערך המקביל באיכות.
_DEFAULT_CQ = {("nvenc", "hevc"): 19, ("nvenc", "av1"): 24, ("amf", "hevc"): 20, ("amf", "av1"): 26,
               ("qsv", "hevc"): 21, ("qsv", "av1"): 26, ("cpu", "hevc"): 22, ("cpu", "av1"): 32}
_AMF_QUALITY = {"p1": "speed", "p2": "speed", "p3": "speed", "p4": "balanced", "p5": "balanced", "p6": "quality", "p7": "quality"}
_X_PRESET = {"p1": "veryfast", "p2": "faster", "p3": "fast", "p4": "medium", "p5": "slow", "p6": "slower", "p7": "veryslow"}
_SVT_PRESET = {"p1": "12", "p2": "10", "p3": "8", "p4": "7", "p5": "6", "p6": "4", "p7": "2"}

_PROBE_SIZE = "256x144"   # מעל המינימום של NVENC/AMF/QSV (ראו nvenc_probe)
_PROBE_TIMEOUT_SECONDS = 20


def encoder_name(codec: str, backend: str) -> str:
    return _ENCODER_NAMES[(backend, codec)]


def codec_args(codec: str, backend: str = "nvenc", preset: Optional[str] = None, cq: Optional[int] = None) -> List[str]:
    """דגלי ffmpeg ל-hevc/av1 במקודד הנתון. preset - בסולם של NVENC (p1 מהיר עד p7 איכותי), מתורגם לכל מקודד.
    cq - יעד האיכות (נמוך = איכותי יותר), מוחל על הדגל של המקודד."""
    if codec not in GPU_CODECS or backend not in BACKENDS:
        raise ValueError(f"צירוף לא מוכר: {codec!r} / {backend!r}")
    name = encoder_name(codec, backend)
    level = preset or "p5"
    quality = str(cq if cq is not None else _DEFAULT_CQ[(backend, codec)])
    if backend == "nvenc":
        return ["-c:v", name, "-preset", level, "-cq", quality]
    if backend == "amf":
        return ["-c:v", name, "-quality", _AMF_QUALITY.get(level, "balanced"), "-rc", "cqp", "-qp_i", quality, "-qp_p", quality]
    if backend == "qsv":
        return ["-c:v", name, "-preset", _X_PRESET.get(level, "slow"), "-global_quality", quality]
    if codec == "hevc":
        return ["-c:v", name, "-preset", _X_PRESET.get(level, "slow"), "-crf", quality]
    return ["-c:v", name, "-preset", _SVT_PRESET.get(level, "6"), "-crf", quality]


def bitrate_args(codec: str, backend: str, bitrate_kbps: int, preset: Optional[str] = None) -> List[str]:
    """יעד גודל קובץ (VBR, קריאה אחת) ל-hevc/av1. nvenc - בדיוק כמו get_two_pass_codec_args הקיים."""
    if codec not in GPU_CODECS or backend not in BACKENDS:
        raise ValueError(f"צירוף לא מוכר: {codec!r} / {backend!r}")
    name = encoder_name(codec, backend)
    level = preset or "p5"
    rate, peak = f"{bitrate_kbps}k", f"{int(bitrate_kbps * 1.5)}k"
    if backend == "nvenc":
        return ["-c:v", name, "-preset", level, "-rc", "vbr", "-b:v", rate, "-maxrate", peak, "-multipass", "fullres"]
    if backend == "amf":
        return ["-c:v", name, "-quality", _AMF_QUALITY.get(level, "balanced"), "-rc", "vbr_peak", "-b:v", rate, "-maxrate", peak]
    if backend == "qsv":
        return ["-c:v", name, "-preset", _X_PRESET.get(level, "slow"), "-b:v", rate, "-maxrate", peak]
    if codec == "hevc":
        return ["-c:v", name, "-preset", _X_PRESET.get(level, "slow"), "-b:v", rate, "-maxrate", peak, "-bufsize", peak]
    return ["-c:v", name, "-preset", _SVT_PRESET.get(level, "6"), "-b:v", rate]


# --- ההגדרה ---

def settings_path() -> str:
    return data_paths.path(data_paths.ENCODER_SETTINGS)


def load_setting(path: Optional[str] = None) -> str:
    env = os.environ.get(ENV_VAR, "").strip().lower()
    if env in CHOICES:
        return env
    try:
        with open(path or settings_path(), encoding="utf-8") as f:
            value = str(json.load(f).get("backend", "auto")).lower()
    except (OSError, ValueError, AttributeError):
        return "auto"
    return value if value in CHOICES else "auto"


def save_setting(backend: str, path: Optional[str] = None) -> None:
    if backend not in CHOICES:
        raise ValueError(f"מקודד לא מוכר: {backend!r}")
    target = path or settings_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    atomic_write_json(target, {"backend": backend}, indent=2, ensure_ascii=False)


# --- הבדיקה ---

def _cache_path() -> str:
    workspace = os.environ.get("CLIPFORGE_WORKSPACE_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "workspace")
    return os.path.join(workspace, ".cache", "encoders.json")


def _ffmpeg_key(ffmpeg_exe: str) -> Optional[str]:
    try:
        st = os.stat(ffmpeg_exe)
    except OSError:
        return None   # "ffmpeg" מה-PATH - בלי מטמון, הבדיקה רצה בכל פעם
    return f"{os.path.normcase(os.path.abspath(ffmpeg_exe))}|{st.st_size}|{int(st.st_mtime)}"


def _probe(ffmpeg_exe: str, encoder: str, creationflags: int) -> Optional[bool]:
    """True/False - הקידוד הצליח או לא. None - ffmpeg לא רץ בכלל (לא מותקן / לא נמצא)."""
    cmd = [ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
           "-i", f"color=black:size={_PROBE_SIZE}:duration=0.4:rate=10", "-frames:v", "3", "-c:v", encoder, "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=_PROBE_TIMEOUT_SECONDS, creationflags=creationflags)
    except FileNotFoundError:
        return None
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def detect_backends(ffmpeg_exe: str, creationflags: int = 0, use_cache: bool = True) -> Optional[Dict[str, List[str]]]:
    """{מקודד: [קודקים שעובדים]} לכל מקודד חומרה, ו-"cpu" עם מה ש-ffmpeg הזה מכיר. None - ffmpeg לא רץ."""
    key = _ffmpeg_key(ffmpeg_exe)
    cache = _cache_path()
    if use_cache and key:
        try:
            with open(cache, encoding="utf-8") as f:
                stored = json.load(f)
            if stored.get("key") == key and isinstance(stored.get("backends"), dict):
                return {b: list(c) for b, c in stored["backends"].items()}
        except (OSError, ValueError, AttributeError):
            pass
    pairs = [(b, c) for b in BACKENDS for c in GPU_CODECS]
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        results = list(pool.map(lambda pair: _probe(ffmpeg_exe, encoder_name(pair[1], pair[0]), creationflags), pairs))
    if all(r is None for r in results):
        return None
    found: Dict[str, List[str]] = {b: [] for b in BACKENDS}
    for (backend, codec), ok in zip(pairs, results):
        if ok:
            found[backend].append(codec)
    if key:
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            atomic_write_json(cache, {"key": key, "backends": found}, indent=1)
        except OSError:
            pass
    return found


def resolve_backend(requested: str, codec: str, available: Optional[Dict[str, List[str]]]) -> Tuple[str, Optional[str]]:
    """(המקודד בפועל, הודעה או None). available=None (הבדיקה לא רצה / ffmpeg לא נמצא) - nvenc, כמו קודם."""
    requested = requested if requested in CHOICES else "auto"
    if available is None:
        return ("nvenc" if requested == "auto" else requested), None
    if requested != "auto" and codec in available.get(requested, []):
        return requested, None
    for backend in HARDWARE + ("cpu",):
        if codec in available.get(backend, []):
            if requested == "auto":
                return backend, None
            return backend, f"{LABELS[requested]} לא זמין במחשב הזה ל-{codec} - מקודד במקום זה עם {LABELS[backend]}"
    fallback = "cpu" if requested == "auto" else requested
    return fallback, f"לא נמצא מקודד {codec} שעובד במחשב הזה - מנסה {LABELS[fallback]}"
