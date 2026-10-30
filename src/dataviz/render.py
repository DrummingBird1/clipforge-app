# dataviz/render.py
#
# רינדור: תהליכים מקבילים (ProcessPoolExecutor עם spawn - הבטוח ב-Windows ועם matplotlib)
# שכל אחד בונה את הדמות פעם אחת (initializer) ומצייר פריימים מהתכנית, וצנרת של
# הפריימים הגולמיים (RGBA) ל-stdin של ffmpeg - בלי קובצי ביניים על הדיסק. המוזיקה
# נחתכת לאורך הסרטון, עם כניסה הדרגתית ודעיכה בסוף.

import contextlib
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
from collections import deque
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, Callable, Deque, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from dataviz.languages import LTR_LANGUAGES
from dataviz.themes import get_theme, theme_to_dict

ProgressFn = Callable[[int, int], None]
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_CHART: Any = None
FLAGS_DIR_ENV = "DATAVIZ_FLAGS_DIR"   # 27.10.2026: תיקיית הדגלים (images.flags) - ClipForge קובע אותה (המנוע לא יודע איפה data/)


def chart_context(episode: Any, chart: Optional[str] = None) -> Dict[str, Any]:
    """כל מה שתהליך רינדור צריך כדי לבנות את הדמות - טיפוסים פשוטים בלבד (נשלח ב-spawn)."""
    cfg = episode.config
    dates = episode.dates
    start = pd.Timestamp(dates[0])
    span = float((dates[-1] - dates[0]).days) or 1.0
    tick_step = int(cfg["timeline"]["tick_years"])
    ticks = []
    for year in range(start.year, pd.Timestamp(dates[-1]).year + 1, tick_step):
        xf = (pd.Timestamp(f"{year}-01-01") - start).days / span
        if 0 <= xf <= 1:
            ticks.append((xf, str(year)))
    entities = list(episode.entities)
    palette = cfg.get("palette", "auto")
    if palette == "auto":
        numeric = all(isinstance(e, (int, float)) and not isinstance(e, bool) for e in entities)
        palette = "ordinal" if numeric else "categorical"
    video = cfg["video"]
    return {
        "chart": chart or cfg["chart"],
        "theme": theme_to_dict(get_theme(cfg["theme"], cfg.get("theme_overrides"))),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "dpi": video["dpi"],
        "title": cfg["title"],
        "subtitle": cfg.get("subtitle", ""),
        "ltr": cfg.get("language") in LTR_LANGUAGES,   # סבב הייצוב: גרסה באנגלית - הכותרת משמאל
        "notes": list(cfg.get("notes") or []),
        "legend": list(episode.legend),
        "levels": bool(episode.levels),   # 18.10.2026: יש מקור kind: level - ראש ציר ה-y על שנתה מסומנת (line_race)
        # 19.10.2026: כל הישויות רמות - ציר ה-y של line_race לא מתחיל מ-0 (טמפרטורה 18-22 לא נמעכת בתחתית)
        "all_levels": bool(episode.levels) and len(episode.levels) == len(episode.entities),
        "axis_headroom": float(cfg["ranking"]["axis_headroom"]),
        "labels": dict(cfg["labels"]),
        "intro": dict(cfg["intro"]),
        "outro": dict(cfg["outro"]),
        "top_n": int(cfg["ranking"]["top_n"]),
        "entities": entities,
        "textures": dict(episode.textures),
        "palette": palette,
        "year_mark": cfg.get("year_mark", True),
        "timeline": {"ticks": ticks, "events": [(pd.Timestamp(d) - start).days / span for d, _, _ in episode.events]},
        # לתרשימים שמציירים היסטוריה (קו/שטח/פיזור): כל המצטבר, ואת השנה של כל יום
        "dates": dates.values,
        "cum": episode.cum,
        "daily": episode.daily,
        "start_idx": [int(i) for i in episode.start_idx],
        "scatter": dict(cfg.get("scatter") or {}),
        # גל 39: צבע קבוע לישות (לפי השם כטקסט) מעל הפלטה
        "colors": {str(k): str(v) for k, v in (cfg.get("colors") or {}).items()},
        # גל 41: לוגו בפינה - נתיב מלא (תהליכי הרינדור לא יודעים מה תיקיית הפרק)
        "logo": _logo_context(cfg),
        # גל 42: האזורים של תרשים המפה (רק כשהוא נבחר) - נקראים כאן פעם אחת ונשלחים לתהליכים
        "map": _map_context(cfg) if (chart or cfg["chart"]) == "map_race" else None,
        "map_style": {k: (cfg.get("map") or {}).get(k) for k in ("legend", "labels")},   # גל 51
        # גל 49: פורמט המספרים וציר לוגריתמי
        "numbers": numbers_context(cfg, episode),
        "auto_decimals": numbers_context(cfg, episode).get("decimals") != (cfg.get("numbers") or {}).get("decimals"),   # 19.10.2026
        **axes_context(cfg, episode),   # 20.10.2026: ציר y שני (רק כשיש מקור axis: right)
        "log_scale": bool((cfg.get("ranking") or {}).get("log_scale")),
        # גל 51: תמונות לישויות (נתיב מלא - תהליכי הרינדור לא יודעים מה תיקיית הפרק) וסגנון
        "images": _images_context(cfg),
        "style": dict(cfg.get("style") or {}),
        "chapter_transition": str((cfg.get("story") or {}).get("chapter_transition") or "fade"),   # 27.10.2026
        # גל 50: תקופות מוצללות (בימי הפרק), מסך הסיום ומקורות הנתונים
        "periods": periods_context(cfg, dates),
        "end_screen": dict(cfg.get("end_screen") or {}),
        "credits": [str(line) for line in (cfg.get("outro") or {}).get("credits") or []],
    }


def numbers_context(cfg: Mapping[str, Any], episode: Any) -> Dict[str, Any]:
    """פורמט המספרים. 19.10.2026: ברמות עם ערכים לא שלמים (18.3 מעלות) ספרה אחת אחרי הנקודה - אלא אם המשתמש קבע
    numbers.decimals בעצמו (numbers_set, מ-load_config). פרק בלי רמות - כמו שהוא."""
    numbers = dict(cfg.get("numbers") or {})
    if getattr(episode, "level_fractions", False) and "decimals" not in cfg.get("numbers_set", ["decimals"]) and not numbers.get("decimals"):
        numbers["decimals"] = 1
    return numbers


def axes_context(cfg: Mapping[str, Any], episode: Any) -> Dict[str, Any]:
    """20.10.2026: הישויות של הציר הימני, ולכל ציר כותרת ופורמט (numbers של הפרק + y_axes.<צד>.numbers). בלי ציר ימני -
    שום מפתח (ה-ctx, ולכן מפתח מטמון המקטעים, כמו קודם)."""
    right = list(getattr(episode, "right_axis", None) or [])
    if not right:
        return {}
    base = numbers_context(cfg, episode)
    axes = cfg.get("y_axes") or {}
    return {"right_axis": right, "y_axes": {side: {"label": str((axes.get(side) or {}).get("label") or ""),
                                                   "numbers": {**base, **dict((axes.get(side) or {}).get("numbers") or {})}}
                                            for side in ("left", "right")}}


def periods_context(cfg: Mapping[str, Any], dates: Any) -> List[tuple]:
    """(יום התחלה, יום סוף, שם, צבע) לכל תקופה מוצללת שחופפת לטווח של הפרק."""
    from dataviz.plan import day_index
    result = []
    for item in (cfg.get("story") or {}).get("periods") or []:
        start, end = day_index(dates, item["start"]), day_index(dates, item["end"], "right") - 1
        if end < 0 or start >= len(dates) or end < start:
            continue
        result.append((float(start), float(min(end, len(dates) - 1)), str(item["label"]), str(item.get("color") or "")))
    return result


def _map_context(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    from dataviz.geo import load_geojson
    geo = cfg.get("map") or {}
    if not geo.get("geojson"):
        raise ValueError("תרשים מפה (map_race) צריך קובץ GeoJSON (map.geojson) בהגדרות הפרק.")
    return load_geojson(os.path.join(cfg.get("base_dir", ""), str(geo["geojson"])), str(geo.get("key") or "name"),
                        str(geo.get("projection") or "mercator"))


def _images_context(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    images = dict(cfg.get("images") or {})
    images["folder"] = os.path.join(cfg.get("base_dir", ""), str(images["folder"])) if images.get("folder") else ""
    if images.get("flags"):
        images["flags_dir"] = os.environ.get(FLAGS_DIR_ENV, "")
    return images


def _logo_context(cfg: Mapping[str, Any]) -> Dict[str, Any]:
    logo = dict(cfg.get("logo") or {})
    if logo.get("path"):
        logo["path"] = os.path.join(cfg.get("base_dir", ""), str(logo["path"]))
    else:
        logo["path"] = ""
    return logo


def _init_worker(ctx: Mapping[str, Any]) -> None:
    global _CHART
    from dataviz.charts import make_chart
    _CHART = make_chart(ctx)


def _render_chunk(frames: Sequence[Mapping[str, Any]]) -> List[bytes]:
    return [_CHART.render(frame) for frame in frames]


class WorkerDiedError(RuntimeError):
    """תהליך ציור נסגר באמצע הרינדור (קרס, נהרג, או שה-venv הוחלף בזמן הריצה) - הפריימים שהיו אצלו לא יגיעו."""


# ProcessPoolExecutor ולא multiprocessing.Pool: כשתהליך ב-Pool מת, Pool מחליף אותו בשקט, ו-imap מחכה לנצח
# לפריימים שהיו אצלו - הרינדור נתקע בלי הודעה. כאן כל הפריימים שבדרך נכשלים מיד (BrokenProcessPool).
def _start_pool(workers: int, ctx: Mapping[str, Any]) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init_worker, initargs=(ctx,))


def _rendered(pool: ProcessPoolExecutor, frames: Sequence[Mapping[str, Any]], chunksize: int, ahead: int) -> Iterator[bytes]:
    """הפריימים המצוירים לפי הסדר, עם עד ahead חבילות בדרך - כש-ffmpeg איטי מהציור, הפריימים לא נערמים בזיכרון."""
    pending: Deque["Future[List[bytes]]"] = deque()
    try:
        for start in range(0, len(frames), chunksize):
            pending.append(pool.submit(_render_chunk, frames[start:start + chunksize]))
            if len(pending) >= ahead:
                yield from pending.popleft().result()
        while pending:
            yield from pending.popleft().result()
    except BrokenProcessPool as e:
        raise WorkerDiedError(f"תהליך ציור נסגר באמצע הרינדור (קרס או נהרג) - הרינדור נעצר: {e}") from e


def audio_filter(duration: float, fade_in: float, fade_out: float) -> str:
    return f"afade=t=in:st=0:d={fade_in:g},afade=t=out:st={max(duration - fade_out, 0):.2f}:d={fade_out:g}"


# גל 54: קידוד ב-GPU (NVENC) - video.encoder: cpu (libx264, ברירת המחדל), nvenc, או auto (NVENC אם הכרטיס ו-ffmpeg
# תומכים - נבדק פעם אחת בקידוד זעיר). נכשל באמצע? הרינדור חוזר על עצמו ב-libx264, כך שהסרטון תמיד נוצר.
ENCODERS = ("cpu", "nvenc", "auto")
NVENC_PRESETS = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "faster": "p4", "fast": "p5", "medium": "p6", "slow": "p7"}
_NVENC: Dict[str, bool] = {}


class FfmpegError(RuntimeError):
    """ffmpeg עצמו נכשל (לא הציור) - אפשר לנסות שוב במקודד אחר."""


def video_codec_args(video: Mapping[str, Any], encoder: str = "libx264") -> List[str]:
    preset = str(video.get("preset", "veryfast"))
    crf = int(video.get("crf", 18))
    if encoder == "nvenc":   # cq ב-NVENC קרוב ל-crf של x264; וידאו של גרפים (משטחים חלקים) נדחס טוב בשניהם
        return ["-c:v", "h264_nvenc", "-preset", NVENC_PRESETS.get(preset, "p4"), "-rc", "vbr", "-cq", str(crf + 1), "-b:v", "0",
                "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]


def nvenc_available(ffmpeg: str, runner: Callable[..., Any] = subprocess.run) -> bool:
    """האם ffmpeg מצליח לקודד ב-h264_nvenc (שבריר שנייה של מסך שחור, לא לקובץ). התשובה נשמרת לכל ffmpeg."""
    if ffmpeg not in _NVENC:
        try:
            result = runner([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                             "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True, timeout=20, creationflags=_NO_WINDOW)
            _NVENC[ffmpeg] = result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _NVENC[ffmpeg] = False
    return _NVENC[ffmpeg]


def resolve_encoder(video: Mapping[str, Any], ffmpeg: str) -> str:
    setting = str(video.get("encoder") or "cpu")
    if setting == "nvenc" or (setting == "auto" and nvenc_available(ffmpeg)):
        return "nvenc"
    return "libx264"


def ffmpeg_command(ffmpeg: str, size: Sequence[int], fps: int, duration: float, out_path: str, video: Mapping[str, Any],
                   audio: Optional[Mapping[str, Any]] = None, audio_path: str = "", encoder: str = "libx264") -> List[str]:
    w, h = size
    cmd = [ffmpeg, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
           "-r", str(fps), "-i", "-"]
    if audio_path:
        if audio and float(audio.get("start") or 0) > 0:
            cmd += ["-ss", f"{float(audio['start']):g}"]
        cmd += ["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0"]
    cmd += video_codec_args(video, encoder)
    if audio_path and audio is not None:
        cmd += ["-af", audio_filter(duration, float(audio["fade_in"]), float(audio["fade_out"])),
                "-c:a", "aac", "-b:a", str(audio.get("bitrate", "192k"))]
    cmd += ["-t", f"{duration:.3f}", out_path]
    return cmd


def concat_command(ffmpeg: str, list_path: str, duration: float, out_path: str, audio: Optional[Mapping[str, Any]] = None,
                   audio_path: str = "") -> List[str]:
    """גל 54: חיבור המקטעים מהמטמון בלי קידוד מחדש (-c:v copy), והמוזיקה מעליהם עם כניסה ודעיכה לפי האורך הכולל."""
    cmd = [ffmpeg, "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
    if audio_path:
        if audio and float(audio.get("start") or 0) > 0:
            cmd += ["-ss", f"{float(audio['start']):g}"]
        cmd += ["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0"]
    cmd += ["-c:v", "copy"]
    if audio_path and audio is not None:
        cmd += ["-af", audio_filter(duration, float(audio["fade_in"]), float(audio["fade_out"])),
                "-c:a", "aac", "-b:a", str(audio.get("bitrate", "192k"))]
    cmd += ["-t", f"{duration:.3f}", out_path]
    return cmd


def default_workers() -> int:
    return max(2, min(8, (os.cpu_count() or 4) - 2))


def lower_priority(setting: str = "low") -> bool:
    """27.10.2026: video.priority = low - התהליך הנוכחי יורד לעדיפות "מתחת לרגילה" לפני שתהליכי הציור ו-ffmpeg נפתחים.
    ב-Windows תהליך בן של תהליך בעדיפות כזו מקבל אותה עדיפות, אז כל הרינדור רץ בה - והמחשב נשאר זמין לגלישה ולצפייה.
    מחזיר True כשהעדיפות הורדה."""
    if setting != "low":
        return False
    try:
        import psutil
        process = psutil.Process()
        if os.name == "nt":
            process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            process.nice(max(process.nice(), 10))
        return True
    except Exception:   # psutil חסר, או מערכת שלא מרשה - הרינדור ממשיך בעדיפות הרגילה
        return False


# ---------- גל 54: מטמון רינדור ----------
# הסרטון מרונדר במקטעים (טיזר, פתיח, הקטע הראשי, סיום - רצפים של אותו סוג פריים), כל מקטע נשמר בתיקיית המטמון לפי
# טביעה של מה שמשפיע עליו בלבד: הפריימים שלו, ההקשר של התרשים (בלי הטקסטים של הפתיח בקטע הראשי, ובלי אלה של
# הסיום בפתיח), הגודל, הקצב, המקודד וקוד הציור עצמו. שינוי של הפתיח או הסיום מרנדר רק אותם; השאר מועתק כמו שהוא.
# 23.10.2026 (המלצה 9): רצף ארוך (הקטע הראשי) נחתך למקטעים של עד SEGMENT_SECONDS - רינדור מלא שנקטע (עצירה, דילוג, קריסה)
# ממשיך מהמקטע האחרון שהסתיים, ולא מתחילת הקטע הראשי. המטמון שומר אותו מספר פרקים כמו קודם (בערך 4-5)
SEGMENT_SECONDS = 60
MAX_SEGMENT_FILES = 48
_INTRO_ONLY = ("intro",)
_OUTRO_ONLY = ("outro", "end_screen", "credits")
_CODE_VERSION: List[str] = []


def _code_version() -> str:
    """טביעה של קוד הציור (תרשימים, ערכות ותוכנית) - קוד שהשתנה לא משתמש במקטעים ישנים."""
    if not _CODE_VERSION:
        root = os.path.dirname(os.path.abspath(__file__))
        digest = hashlib.sha1()
        for folder in ("charts", "themes", ""):
            path = os.path.join(root, folder)
            for name in sorted(os.listdir(path)):
                if name.endswith(".py"):
                    with open(os.path.join(path, name), "rb") as f:
                        digest.update(name.encode("utf-8") + f.read())
        _CODE_VERSION.append(digest.hexdigest()[:16])
    return _CODE_VERSION[0]


def _files_stamp(path: str) -> str:
    """שמות, גדלים וזמני שינוי של קובץ או תיקייה (לוגו, תמונות הישויות) - תוכן חדש באותו נתיב משנה את הטביעה."""
    if not path:
        return ""
    if os.path.isfile(path):
        stat = os.stat(path)
        return f"{stat.st_size}:{stat.st_mtime_ns}"
    if os.path.isdir(path):
        return "|".join(f"{n}:{os.stat(os.path.join(path, n)).st_size}:{os.stat(os.path.join(path, n)).st_mtime_ns}" for n in sorted(os.listdir(path)))
    return ""


def context_key(ctx: Mapping[str, Any], skip: Sequence[str] = ()) -> str:
    digest = hashlib.sha1()
    for key in sorted(k for k in ctx if k not in skip):
        value = ctx[key]
        digest.update(key.encode("utf-8"))
        if isinstance(value, np.ndarray):
            digest.update(np.ascontiguousarray(value).tobytes())
        else:
            digest.update(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"))
    digest.update(_files_stamp(str((ctx.get("logo") or {}).get("path") or "")).encode("utf-8"))
    digest.update(_files_stamp(str((ctx.get("images") or {}).get("folder") or "")).encode("utf-8"))
    return digest.hexdigest()


def plan_segments(plan: Sequence[Mapping[str, Any]], max_frames: int = 0) -> List[Tuple[int, int, str]]:
    """(התחלה, סוף, סוג) לכל רצף של פריימים מאותו סוג - הטיזר נפרד מהקטע הראשי. max_frames > 0: רצף ארוך נחתך לחתיכות
    של עד max_frames (המלצה 9)."""
    segments: List[Tuple[int, int, str]] = []
    for index, frame in enumerate(plan):
        kind = "teaser" if frame.get("teaser") else str(frame.get("k"))
        if segments and segments[-1][2] == kind and not (max_frames and segments[-1][1] - segments[-1][0] >= max_frames):
            segments[-1] = (segments[-1][0], index + 1, kind)
        else:
            segments.append((index, index + 1, kind))
    return segments


def segment_key(ctx: Mapping[str, Any], frames: Sequence[Mapping[str, Any]], kind: str, video: Mapping[str, Any], fps: int, encoder: str) -> str:
    skip = _OUTRO_ONLY if kind == "intro" else _INTRO_ONLY if kind == "outro" else _INTRO_ONLY + _OUTRO_ONLY
    digest = hashlib.sha1(context_key(ctx, skip).encode("utf-8"))
    digest.update(json.dumps(list(frames), sort_keys=True, default=str, ensure_ascii=False).encode("utf-8"))
    digest.update(json.dumps([kind, fps, video_codec_args(video, encoder), _code_version()]).encode("utf-8"))
    return digest.hexdigest()[:24]


def _prune_segments(folder: str, keep: Sequence[str]) -> None:
    try:
        files = sorted((os.path.join(folder, n) for n in os.listdir(folder) if n.startswith("seg_") and n.endswith(".mp4")), key=os.path.getmtime)
    except OSError:
        return
    for path in files[:max(0, len(files) - MAX_SEGMENT_FILES)]:
        if path not in keep:
            try:
                os.remove(path)   # safe: מקטע במטמון הרינדור של המנוע (workspace/.cache/dataviz_segments), לא קובץ של המשתמש
            except OSError:
                pass


def _encode(frames: Iterable[bytes], cmd: List[str], expected: int, on_frame: Optional[Callable[[], None]] = None) -> None:
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=_NO_WINDOW)
    try:
        for frame in frames:
            if len(frame) != expected:
                raise RuntimeError(f"גודל פריים {len(frame)} בתים במקום {expected} - בדוק את video.width/height/dpi.")
            assert ff.stdin is not None
            try:
                ff.stdin.write(frame)
            except OSError as e:   # ffmpeg נסגר באמצע (למשל NVENC שלא נפתח)
                raise FfmpegError(f"ffmpeg נסגר באמצע הכתיבה: {e}") from e
            if on_frame:
                on_frame()
    except BaseException:
        ff.kill()
        ff.wait()
        raise
    assert ff.stdin is not None
    try:
        ff.stdin.close()
    except OSError:
        pass
    if ff.wait() != 0:
        raise FfmpegError(f"ffmpeg נכשל (קוד {ff.returncode}) בכתיבת {cmd[-1]}.")


def render_video(episode: Any, plan: Sequence[Mapping[str, Any]], out_path: str, *, ffmpeg: str = "ffmpeg",
                 workers: Optional[int] = None, progress: Optional[ProgressFn] = None, chart: Optional[str] = None,
                 chunksize: int = 6, segment_cache: str = "") -> Dict[str, Any]:
    """מרנדר את כל התכנית לסרטון (עם מוזיקה אם הוגדרה). זורק RuntimeError אם ffmpeg נכשל.
    segment_cache (גל 54): תיקיית מטמון - מקטעים שכבר רונדרו עם אותם נתונים לא מרונדרים שוב.
    23.10.2026 (תיקיית הייצוא, גם בכונן רשת): נכתב ל-partial_path(out_path) באותה תיקייה ומקבל את השם רק בסוף - דילוג, כשל או
    ניתוק באמצע לא משאירים קובץ חלקי בשם של הסרטון ולא נוגעים בסרטון הקודם."""
    encoder = resolve_encoder(episode.config["video"], ffmpeg)
    partial = partial_path(out_path)
    try:
        try:
            result = _render(episode, plan, partial, ffmpeg, workers, progress, chart, chunksize, segment_cache, encoder)
        except FfmpegError:
            if encoder != "nvenc":
                raise
            result = _render(episode, plan, partial, ffmpeg, workers, progress, chart, chunksize, segment_cache, "libx264")
            encoder = "libx264"
        os.replace(partial, out_path)   # safe: הסרטון שהריצה הזו סיימה לכתוב, לשם הסופי באותה תיקייה
    except BaseException:   # גם QueueSkip של התור
        with contextlib.suppress(OSError):
            os.remove(partial)   # safe: הקובץ החלקי של הריצה הזו (partial_path), לא הסרטון עצמו
        raise
    result["path"] = out_path
    result["encoder"] = encoder
    return result


def partial_path(out_path: str) -> str:
    """.<שם>.partial.mp4 ליד הסרטון - מוסתר מרשימת התוצרים (שמות שמתחילים בנקודה), ו-ffmpeg מזהה את הפורמט מהסיומת."""
    folder, name = os.path.split(out_path)
    return os.path.join(folder, f".{name}.partial.mp4")


def _render(episode: Any, plan: Sequence[Mapping[str, Any]], out_path: str, ffmpeg: str, workers: Optional[int],
            progress: Optional[ProgressFn], chart: Optional[str], chunksize: int, segment_cache: str, encoder: str) -> Dict[str, Any]:
    cfg = episode.config
    video = cfg["video"]
    fps = int(video["fps"])
    size = (int(video["width"]), int(video["height"]))
    duration = len(plan) / fps
    audio = cfg.get("audio") or {}
    audio_path = os.path.join(cfg["base_dir"], str(audio["path"])) if audio.get("path") else ""
    ctx = chart_context(episode, chart)
    expected = size[0] * size[1] * 4
    total = len(plan)
    done = [0]

    def tick() -> None:
        done[0] += 1
        if progress:
            progress(done[0], total)

    workers = workers or default_workers()
    ahead = 2 * workers   # חבילה שמצוירת וחבילה שמחכה לכל תהליך
    pool: Optional[ProcessPoolExecutor] = None
    try:
        if not segment_cache:
            pool = _start_pool(workers, ctx)
            _encode(_rendered(pool, plan, chunksize, ahead), ffmpeg_command(ffmpeg, size, fps, duration, out_path, video, audio, audio_path, encoder),
                    expected, tick)
            return {"path": out_path, "frames": total, "seconds": round(duration, 2), "size": list(size), "cached_frames": 0}
        os.makedirs(segment_cache, exist_ok=True)
        paths, cached = [], 0
        for start, end, kind in plan_segments(plan, SEGMENT_SECONDS * fps):
            frames = plan[start:end]
            path = os.path.join(segment_cache, f"seg_{segment_key(ctx, frames, kind, video, fps, encoder)}.mp4")
            if os.path.isfile(path):
                os.utime(path)
                cached += len(frames)
                for _ in frames:
                    tick()
            else:
                if pool is None:
                    pool = _start_pool(workers, ctx)
                tmp = path + ".tmp.mp4"
                _encode(_rendered(pool, frames, chunksize, ahead), ffmpeg_command(ffmpeg, size, fps, len(frames) / fps, tmp, video, encoder=encoder),
                        expected, tick)
                os.replace(tmp, path)   # safe: מקטע חדש במטמון הרינדור
            paths.append(path)
        list_path = out_path + ".segments.txt"
        with open(list_path, "w", encoding="utf-8") as f:
            f.write("".join("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n" for p in paths))
        try:
            result = subprocess.run(concat_command(ffmpeg, list_path, duration, out_path, audio, audio_path), capture_output=True,
                                    creationflags=_NO_WINDOW)
        finally:
            os.remove(list_path)   # safe: רשימת המקטעים הזמנית שנכתבה כאן
        if result.returncode != 0:
            raise FfmpegError(f"חיבור המקטעים נכשל (קוד {result.returncode}): {result.stderr[-300:]!r}")
        _prune_segments(segment_cache, paths)
        return {"path": out_path, "frames": total, "seconds": round(duration, 2), "size": list(size), "cached_frames": cached}
    finally:
        if pool is not None:   # בשגיאה או בדילוג - החבילות שעוד לא התחילו מבוטלות, לא מצוירות עד הסוף
            pool.shutdown(wait=True, cancel_futures=True)


def still_indices(plan: Sequence[Mapping[str, Any]]) -> List[int]:
    """פריים מהאינטרו, שמונה לאורך הקטע הראשי והאחרון - לבדיקת עיצוב בלי לרנדר הכל."""
    intro = [i for i, f in enumerate(plan) if f["k"] == "intro"]
    main = [i for i, f in enumerate(plan) if f["k"] == "main" and "teaser" not in f]   # גל 50: הטיזר לפני הפתיח
    picks = ([intro[len(intro) // 2]] if intro else []) + ([main[int(len(main) * f)] for f in (0.04, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 0.99)] if main else [])
    picks.append(len(plan) - 1)
    return sorted({i for i in picks if 0 <= i < len(plan)})


def render_stills(episode: Any, plan: Sequence[Mapping[str, Any]], out_dir: str, *, picks: Optional[Sequence[int]] = None,
                  chart: Optional[str] = None, progress: Optional[ProgressFn] = None) -> List[str]:
    """פריימים בודדים כ-PNG (בתהליך הנוכחי) - still_00123.png לפי מספר הפריים בתכנית."""
    from dataviz.charts import make_chart

    os.makedirs(out_dir, exist_ok=True)
    chart_obj = make_chart(chart_context(episode, chart))
    picks = list(picks) if picks is not None else still_indices(plan)
    paths = []
    try:
        for n, i in enumerate(picks, start=1):
            chart_obj.render(plan[i])
            path = os.path.join(out_dir, f"still_{i:05d}.png")
            chart_obj.save_png(path)
            paths.append(path)
            if progress:
                progress(n, len(picks))
    finally:
        chart_obj.close()
    return paths
