# utils/media/face_track.py
#
# 17.11.2026 (ClipForge 2.0.1): מסגרת ה-Facecam עוקבת אחרי הפנים. ב-Short אנכי המצלמה יושבת ברצועה העליונה; בלי מעקב היא
# חתוכה למרכז, ומי שיושב בצד או זז יוצא חתוך. כאן:
#   - sample_faces: דוגם את stream המצלמה (פעמיים בשנייה, בקטן) דרך ffmpeg ומזהה פנים עם YuNet (אותו מודל כמו smart_crop).
#   - plan: טהור. ממלא חורים, מחליק, מחזיק את המסגרת במקום עד שהפנים זזות יותר מ-DEADBAND (צלם שלא רועד), ובוחר זום
#     שבו הפנים תופסות בערך TARGET_FACE_W מרוחב המסגרת (עד MAX_ZOOM).
#   - crop_filter: טהור. מחזיר scale + crop עם ביטויי x/y לפי הזמן (מעבר ליניארי בין נקודות המפתח).
# כל כשל (אין מודל, אין פנים, ffmpeg נכשל) = None, והפריסה נשארת חיתוך למרכז כמו לפני.
import os
import subprocess
from statistics import median
from typing import List, NamedTuple, Optional, Sequence, Tuple

from utils.shared.subprocess_flags import NO_WINDOW_FLAGS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
FACE_MODEL_PATH = os.path.join(BASE_DIR, "assets", "face_detection_yunet_2023mar.onnx")

SAMPLE_FPS = 2.0
SAMPLE_W = 480
MIN_CONFIDENCE = 0.6
MIN_DETECTED = 0.2      # פחות מחמישית מהדגימות עם פנים = אין מעקב
TARGET_FACE_W = 0.22    # רוחב הפנים מתוך רוחב המסגרת אחרי הזום
MAX_ZOOM = 2.0
DEADBAND = 0.05         # חלק מרוחב / גובה תמונת המצלמה
FACE_Y = 0.42           # איפה מרכז הפנים יושב בגובה המסגרת (קצת מעל האמצע)
MAX_KEYS = 40           # שומר על שורת הפקודה קצרה

Sample = Optional[Tuple[float, float, float]]   # (מרכז x, מרכז y, רוחב) בחלקים מהתמונה, או None כשאין פנים


class Track(NamedTuple):
    zoom: float
    keys: List[Tuple[float, float, float]]   # (שניות מתחילת הקטע, מרכז x, מרכז y)


def sample_faces(path: str, start: float, duration: float, ffmpeg_exe: str, cam_w: int, cam_h: int,
                 stream: int = 1, timeout: float = 300.0) -> List[Sample]:
    """דגימה לכל חצי שנייה של הקטע. רשימה ריקה על כל כשל."""
    if cam_w <= 0 or cam_h <= 0 or duration <= 0 or not os.path.isfile(FACE_MODEL_PATH):
        return []
    height = max(2, int(round(SAMPLE_W * cam_h / cam_w / 2)) * 2)
    frame_bytes = SAMPLE_W * height * 3
    cmd = [ffmpeg_exe, "-hide_banner", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{duration:.2f}", "-i", path,
           "-map", f"0:v:{stream}", "-vf", f"fps={SAMPLE_FPS:g},scale={SAMPLE_W}:{height}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    try:
        import cv2
        import numpy as np
        raw = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW_FLAGS).stdout
        detector = cv2.FaceDetectorYN_create(FACE_MODEL_PATH, "", (SAMPLE_W, height))
        samples: List[Sample] = []
        for offset in range(0, len(raw) - frame_bytes + 1, frame_bytes):
            frame = np.frombuffer(raw, dtype=np.uint8, count=frame_bytes, offset=offset).reshape(height, SAMPLE_W, 3)
            _, faces = detector.detect(frame)
            best = None
            for face in (faces if faces is not None else []):
                if float(face[-1]) >= MIN_CONFIDENCE and (best is None or face[2] * face[3] > best[2] * best[3]):
                    best = face
            samples.append(None if best is None else (float(best[0] + best[2] / 2) / SAMPLE_W,
                                                      float(best[1] + best[3] / 2) / height, float(best[2]) / SAMPLE_W))
        return samples
    except Exception:
        return []


def _median3(values: Sequence[float]) -> List[float]:
    return [median(values[max(0, i - 1):i + 2]) for i in range(len(values))]


def plan(samples: Sequence[Sample], step: float = 1.0 / SAMPLE_FPS, deadband: float = DEADBAND) -> Optional[Track]:
    """נקודות מפתח למסגרת מתוך הדגימות, או None כשאין מספיק פנים."""
    found = [s for s in samples if s is not None]
    if len(found) < 2 or len(found) < len(samples) * MIN_DETECTED:
        return None
    filled: List[Tuple[float, float, float]] = []
    last = found[0]                       # חור בהתחלה מקבל את הזיהוי הראשון, חור אחר כך - את האחרון שלפניו
    for sample in samples:
        last = sample if sample is not None else last
        filled.append(last)
    xs, ys = _median3([s[0] for s in filled]), _median3([s[1] for s in filled])
    zoom = round(max(1.0, min(MAX_ZOOM, TARGET_FACE_W / max(0.01, median(s[2] for s in found)))), 2)
    while True:
        held_x, held_y = xs[0], ys[0]
        points = []
        for i, (x, y) in enumerate(zip(xs, ys)):
            if abs(x - held_x) > deadband or abs(y - held_y) > deadband:
                held_x, held_y = x, y
            points.append((round(i * step, 2), round(held_x, 4), round(held_y, 4)))
        keys = [p for i, p in enumerate(points)   # בריצה של אותו מיקום נשארים רק הקצוות, כדי שהמעבר יימשך צעד אחד
                if i in (0, len(points) - 1) or p[1:] != points[i - 1][1:] or p[1:] != points[i + 1][1:]]
        if len(keys) <= MAX_KEYS:
            return Track(zoom, keys)
        deadband *= 1.5


def _piecewise(times: Sequence[float], values: Sequence[float]) -> str:
    """ביטוי ffmpeg של t: קבוע לפני הנקודה הראשונה ואחרי האחרונה, ליניארי ביניהן."""
    if len(set(values)) == 1:
        return f"{values[0]:.4f}"
    parts = [f"{values[0]:.4f}*lt(t\\,{times[0]:.2f})"]
    for (ta, va), (tb, vb) in zip(zip(times, values), zip(times[1:], values[1:])):
        inside = f"gte(t\\,{ta:.2f})*lt(t\\,{tb:.2f})"
        parts.append(f"{inside}*{va:.4f}" if va == vb else f"{inside}*({va:.4f}+({vb - va:.4f})*(t-{ta:.2f})/{tb - ta:.2f})")
    parts.append(f"{values[-1]:.4f}*gte(t\\,{times[-1]:.2f})")
    return "+".join(parts)


def crop_filter(track: Track, out_w: int, out_h: int) -> str:
    """scale + crop לרצועת המצלמה: מגדיל לפי הזום וחותך out_w x out_h סביב הפנים, בלי לצאת מהתמונה."""
    scaled_w, scaled_h = int(out_w * track.zoom / 2) * 2, int(out_h * track.zoom / 2) * 2
    times = [k[0] for k in track.keys]
    center_x, center_y = _piecewise(times, [k[1] for k in track.keys]), _piecewise(times, [k[2] for k in track.keys])
    return (f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}"
            f":x='max(0\\,min(iw-ow\\,iw*({center_x})-ow/2))':y='max(0\\,min(ih-oh\\,ih*({center_y})-oh*{FACE_Y}))'")


def track(path: str, start: float, duration: float, ffmpeg_exe: str, cam_w: int, cam_h: int, stream: int = 1) -> Optional[Track]:
    return plan(sample_faces(path, start, duration, ffmpeg_exe, cam_w, cam_h, stream))
