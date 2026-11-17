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
# 17.11.2026 (2.0.1), מהבדיקה המעמיקה:
# - av1_amf: ה-QP שלו בסולם 0-255 (hevc_amf: 0-51). נשלח אותו ערך כמו ל-hevc, והקבצים יצאו כמעט בלי דחיסה. עכשיו כפול 4.
# - AV1 ב-CPU: libsvtav1 לא קיים ב-build של ffmpeg שהחבילה מביאה (essentials); שם יש libaom-av1. הבדיקה בוחרת את מי שעובד.
# - המטמון: נשמר גם לפי כרטיסי המסך והדרייברים שלהם (דרייבר חדש או כרטיס אחר = בדיקה מחדש), בדיקה שנגמר לה הזמן לא נשמרת,
#   ו-use_cache=False (הכפתור "בדוק את הכרטיס") באמת בודק מחדש. הבדיקה מריצה את הדגלים האמיתיים של הקידוד, לא רק את שם המקודד.
# - forced_by_env: רק משתנה הסביבה מדלג על הבדיקה (הטסטים). "NVIDIA" שנבחר בהגדרות במחשב בלי NVIDIA עובר למקודד שקיים.
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
CPU_AV1_ENCODERS = ("libsvtav1", "libaom-av1")   # לפי סדר העדיפות: SVT מהיר בהרבה, aom קיים בכל build
_cpu_av1 = CPU_AV1_ENCODERS[0]                   # detect_backends מעדכן לפי מה שעובד ב-ffmpeg הזה
AMF_AV1_QP_SCALE = 4                             # av1_amf: 0-255, מול 0-51 בשאר
# ברירות המחדל של הסטודיו: preset p5 ו-cq 19 (hevc) / 24 (av1) ב-NVENC. בשאר המקודדים - הערך המקביל באיכות.
_DEFAULT_CQ = {("nvenc", "hevc"): 19, ("nvenc", "av1"): 24, ("amf", "hevc"): 20, ("amf", "av1"): 26,
               ("qsv", "hevc"): 21, ("qsv", "av1"): 26, ("cpu", "hevc"): 22, ("cpu", "av1"): 32}
_AMF_QUALITY = {"p1": "speed", "p2": "speed", "p3": "speed", "p4": "balanced", "p5": "balanced", "p6": "quality", "p7": "quality"}
_X_PRESET = {"p1": "veryfast", "p2": "faster", "p3": "fast", "p4": "medium", "p5": "slow", "p6": "slower", "p7": "veryslow"}
_SVT_PRESET = {"p1": "12", "p2": "10", "p3": "8", "p4": "7", "p5": "6", "p6": "4", "p7": "2"}
_AOM_CPU_USED = {"p1": "8", "p2": "7", "p3": "6", "p4": "5", "p5": "4", "p6": "3", "p7": "2"}

_PROBE_SIZE = "256x144"   # מעל המינימום של NVENC/AMF/QSV (ראו nvenc_probe)
_PROBE_TIMEOUT_SECONDS = 20


def encoder_name(codec: str, backend: str) -> str:
    if (backend, codec) == ("cpu", "av1"):
        return _cpu_av1
    return _ENCODER_NAMES[(backend, codec)]


def forced_by_env() -> Optional[str]:
    """המקודד שמשתנה הסביבה כופה (הטסטים, או מי שהגדיר ידנית), או None."""
    env = os.environ.get(ENV_VAR, "").strip().lower()
    return env if env in CHOICES else None


# 17.11.2026: סימנים ב-stderr של ffmpeg לכך שהמקודד של הכרטיס הוא שנכשל (ולא פילטר, קובץ חסר או דיסק מלא)
ENCODER_FAILURE_MARKERS = ("error while opening encoder", "could not open encoder", "no capable devices found",
                           "error initializing output stream", "encoder not found", "cannot load", "driver does not support",
                           "failed to create", "not supported by the device")


def is_encoder_failure(stderr_tail: str, codec: str, backend: str) -> bool:
    """True כשהכישלון נראה כמו כישלון של מקודד החומרה עצמו: הבדיקה לפני הרינדור עברה (256x144, 8 ביט), והרינדור האמיתי
    (רזולוציה, 10 ביט, דרייבר שנתקע) נפל. אז שווה לנסות שוב במעבד, במקום לסמן את הקובץ כנכשל."""
    if backend not in HARDWARE or codec not in GPU_CODECS:
        return False
    text = (stderr_tail or "").lower()
    return f"[{_ENCODER_NAMES[(backend, codec)]} @" in text or any(marker in text for marker in ENCODER_FAILURE_MARKERS)


def swap_args(cmd: List[str], old: List[str], new: List[str]) -> Optional[List[str]]:
    """cmd עם new במקום הרצף old, או None כש-old לא נמצא בו."""
    for index in range(len(cmd) - len(old) + 1):
        if old and cmd[index:index + len(old)] == old:
            return cmd[:index] + list(new) + cmd[index + len(old):]
    return None


def _amf_qp(codec: str, quality: str) -> str:
    return str(min(255, int(quality) * AMF_AV1_QP_SCALE)) if codec == "av1" else quality


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
        qp = _amf_qp(codec, quality)
        return ["-c:v", name, "-quality", _AMF_QUALITY.get(level, "balanced"), "-rc", "cqp", "-qp_i", qp, "-qp_p", qp]
    if backend == "qsv":
        return ["-c:v", name, "-preset", _X_PRESET.get(level, "slow"), "-global_quality", quality]
    if codec == "hevc":
        return ["-c:v", name, "-preset", _X_PRESET.get(level, "slow"), "-crf", quality]
    if name == "libaom-av1":
        return ["-c:v", name, "-cpu-used", _AOM_CPU_USED.get(level, "4"), "-row-mt", "1", "-crf", quality, "-b:v", "0"]
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
    if name == "libaom-av1":
        return ["-c:v", name, "-cpu-used", _AOM_CPU_USED.get(level, "4"), "-row-mt", "1", "-b:v", rate]
    return ["-c:v", name, "-preset", _SVT_PRESET.get(level, "6"), "-b:v", rate]


# --- ההגדרה ---

def settings_path() -> str:
    return data_paths.path(data_paths.ENCODER_SETTINGS)


def load_setting(path: Optional[str] = None) -> str:
    env = forced_by_env()
    if env:
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


def _gpu_signature() -> str:
    """שמות כרטיסי המסך וגרסאות הדרייברים שלהם (מהרישום, בלי תהליך נוסף). "" כשאי אפשר לקרוא."""
    try:
        import winreg
    except ImportError:
        return ""
    found = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            "SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}") as root:
            for index in range(64):
                try:
                    with winreg.OpenKey(root, f"{index:04d}") as key:
                        found.append(f"{winreg.QueryValueEx(key, 'DriverDesc')[0]}@{winreg.QueryValueEx(key, 'DriverVersion')[0]}")
                except OSError:
                    continue
    except OSError:
        return ""
    return ";".join(sorted(found))


def _ffmpeg_key(ffmpeg_exe: str) -> Optional[str]:
    try:
        st = os.stat(ffmpeg_exe)
    except OSError:
        return None   # "ffmpeg" מה-PATH - בלי מטמון, הבדיקה רצה בכל פעם
    return f"{os.path.normcase(os.path.abspath(ffmpeg_exe))}|{st.st_size}|{int(st.st_mtime)}|{_gpu_signature()}"


def _probe(ffmpeg_exe: str, args: List[str], creationflags: int) -> Optional[bool]:
    """True/False - הקידוד הצליח או לא. None - אי אפשר לדעת: ffmpeg לא רץ בכלל, או שהזמן נגמר (מחשב עמוס)."""
    cmd = ([ffmpeg_exe, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", f"color=black:size={_PROBE_SIZE}:duration=0.4:rate=10", "-frames:v", "3"] + args + ["-f", "null", "-"])
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=_PROBE_TIMEOUT_SECONDS, creationflags=creationflags)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _probe_args(codec: str, backend: str, name: Optional[str] = None) -> List[str]:
    """הדגלים האמיתיים של הקידוד (לא רק שם המקודד): מקודד שלא מכיר דגל שאנחנו שולחים נופל כבר בבדיקה."""
    args = codec_args(codec, backend)
    if name is not None and args[1] != name:      # AV1 ב-CPU: בודקים כל מקודד בשמו, לא את זה שנבחר כרגע
        args = ["-c:v", name] + (["-cpu-used", "4", "-row-mt", "1", "-crf", "32", "-b:v", "0"] if name == "libaom-av1"
                                 else ["-preset", "6", "-crf", "32"])
    return args


def detect_backends(ffmpeg_exe: str, creationflags: int = 0, use_cache: bool = True) -> Optional[Dict[str, List[str]]]:
    """{מקודד: [קודקים שעובדים]} לכל מקודד חומרה, ו-"cpu" עם מה ש-ffmpeg הזה מכיר. None - ffmpeg לא רץ."""
    global _cpu_av1
    key = _ffmpeg_key(ffmpeg_exe)
    cache = _cache_path()
    if use_cache and key:
        try:
            with open(cache, encoding="utf-8") as f:
                stored = json.load(f)
            if stored.get("key") == key and isinstance(stored.get("backends"), dict):
                if stored.get("cpu_av1") in CPU_AV1_ENCODERS:
                    _cpu_av1 = stored["cpu_av1"]
                return {b: list(c) for b, c in stored["backends"].items()}
        except (OSError, ValueError, AttributeError):
            pass
    pairs = ([(b, c, None) for b in HARDWARE for c in GPU_CODECS] + [("cpu", "hevc", None)]
             + [("cpu", "av1", name) for name in CPU_AV1_ENCODERS])
    with ThreadPoolExecutor(max_workers=len(pairs)) as pool:
        results = list(pool.map(lambda pair: _probe(ffmpeg_exe, _probe_args(pair[1], pair[0], pair[2]), creationflags), pairs))
    if all(r is None for r in results):
        return None
    found: Dict[str, List[str]] = {b: [] for b in BACKENDS}
    cpu_av1 = None
    for (backend, codec, name), ok in zip(pairs, results):
        if not ok:
            continue
        if name is not None:
            cpu_av1 = cpu_av1 or name      # הראשון שעובד, לפי סדר העדיפות
        if codec not in found[backend]:
            found[backend].append(codec)
    _cpu_av1 = cpu_av1 or CPU_AV1_ENCODERS[0]
    if key and not any(r is None for r in results):   # בדיקה שנגמר לה הזמן לא נשמרת - בפעם הבאה בודקים שוב
        try:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            atomic_write_json(cache, {"key": key, "backends": found, "cpu_av1": _cpu_av1}, indent=1)
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
