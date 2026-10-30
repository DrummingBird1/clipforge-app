# dataviz/bumpers.py
#
# גל 43: אינטרו / אאוטרו מקליפ (ערכת ערוץ) - קליפ קבוע של הערוץ לפני הסרטון ו/או אחריו. אחרי שהסרטון
# נוצר, ffmpeg מחבר את שלושת החלקים: כל קליפ מותאם לגודל ולקצב הפריימים של הסרטון (שוליים, בלי חיתוך),
# וקליפ בלי שמע מקבל שקט באורך שלו. הסרטון עצמו מוחלף רק אם החיבור הצליח. בלי bumpers.* - שום דבר לא רץ.

import json
import os
import subprocess
from typing import Any, Dict, List, Mapping, Optional, Sequence

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")


def resolve(base_dir: str, path: str) -> str:
    """נתיב הקליפ - יחסי לתיקיית הפרק או מלא. ריק = אין קליפ."""
    return os.path.join(base_dir, str(path)) if path else ""


def probe(path: str, ffprobe: str) -> Dict[str, Any]:
    """{duration, has_audio} של קובץ. RuntimeError כשאי אפשר לקרוא אותו."""
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", path]
    result = subprocess.run(cmd, capture_output=True, timeout=30, creationflags=_NO_WINDOW)
    try:
        data = json.loads(result.stdout.decode("utf-8", "replace") or "{}")
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (ValueError, TypeError):
        duration = 0.0
        data = {}
    if result.returncode != 0 or duration <= 0:
        raise RuntimeError(f"לא הצלחתי לקרוא את הקליפ: {os.path.basename(path)}")
    return {"duration": duration, "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams") or [])}


def concat_command(ffmpeg: str, segments: Sequence[Mapping[str, Any]], out_path: str, *, size: Sequence[int], fps: int,
                   video: Mapping[str, Any], bitrate: str = "192k") -> List[str]:
    """פקודת ffmpeg שמחברת קטעים (path, duration, has_audio) לסרטון אחד בגודל ובקצב של הסרטון."""
    w, h = (int(v) for v in size)
    cmd = [ffmpeg, "-loglevel", "error", "-y"]
    for seg in segments:
        cmd += ["-i", str(seg["path"])]
    parts, labels = [], []
    for k, seg in enumerate(segments):
        parts.append(f"[{k}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                     f"setsar=1,fps={fps},format=yuv420p[v{k}]")
        if seg.get("has_audio"):
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo[a{k}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{float(seg['duration']):.3f}[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    parts.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", str(video.get("preset", "veryfast")), "-crf", str(video.get("crf", 18)),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", bitrate, out_path]
    return cmd


def add_bumpers(video_path: str, config: Mapping[str, Any], *, ffmpeg: str, ffprobe: str,
                probe_fn: Optional[Any] = None, run: Optional[Any] = None) -> float:
    """מוסיף את האינטרו / האאוטרו של bumpers.* לסרטון. מחזיר את אורך האינטרו בשניות (כדי להזיז את הכתוביות),
    0 כשאין. RuntimeError כשהחיבור נכשל - הסרטון המקורי נשאר."""
    settings = config.get("bumpers") or {}
    base_dir = config.get("base_dir", "")
    intro, outro = resolve(base_dir, settings.get("intro") or ""), resolve(base_dir, settings.get("outro") or "")
    if not intro and not outro:
        return 0.0
    probe_fn = probe_fn or (lambda path: probe(path, ffprobe))
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW))
    segments = []
    intro_seconds = 0.0
    if intro:
        info = probe_fn(intro)
        intro_seconds = float(info["duration"])
        segments.append({"path": intro, **info})
    segments.append({"path": video_path, **probe_fn(video_path)})
    if outro:
        segments.append({"path": outro, **probe_fn(outro)})
    video = config.get("video") or {}
    tmp = os.path.splitext(video_path)[0] + ".bumpers.tmp.mp4"
    cmd = concat_command(ffmpeg, segments, tmp, size=(video.get("width", 1440), video.get("height", 888)), fps=int(video.get("fps", 60)),
                         video=video, bitrate=str((config.get("audio") or {}).get("bitrate", "192k")))
    result = run(cmd)
    if getattr(result, "returncode", 1) != 0 or not os.path.isfile(tmp):
        if os.path.isfile(tmp):
            os.remove(tmp)   # safe: הקובץ הזמני שיצרנו כאן
        stderr = getattr(result, "stderr", b"") or b""
        raise RuntimeError("חיבור האינטרו / האאוטרו נכשל: " + stderr.decode("utf-8", "replace").strip()[-300:])
    os.replace(tmp, video_path)
    return intro_seconds


def shift_spans(spans: Sequence[Mapping[str, Any]], seconds: float) -> List[Dict[str, Any]]:
    """הכתוביות זזות באורך האינטרו."""
    return [{**span, "start": float(span["start"]) + seconds, "end": float(span["end"]) + seconds} for span in spans]
