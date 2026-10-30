# dataviz/web/preview.py (עד 19.10.2026: utils/dataviz_preview.py)
#
# גל 38: תצוגה חיה בעורך הגרפים - פריים בודד של פרק בכל נקודה (0-1) של הסרטון, בלי לרנדר סרטון.
# המנוע (src/dataviz) בונה את הפרק (CSV -> מצטבר), את התכנית (פריים לכל רגע) ואת הדמות של
# matplotlib; כאן הם נשמרים בזיכרון לפי "טביעת אצבע" של קבצי הפרק, כך שהזזת סליידר מציירת פריים
# אחד בלבד. כל פריים נשמר גם כ-PNG בתיקיית מטמון (תמונות זהות לא מצוירות פעמיים), עם תקרה.
# matplotlib (pyplot) לא בטוח ל-threads - כל הציור תחת מנעול אחד.

import hashlib
import json
import os
import statistics
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Mapping, Optional, Tuple

SCALES = (0.2, 0.35, 0.5)
MAX_EPISODES = 3
MAX_CHARTS = 4
MAX_CACHE_FILES = 400
MODES = ("full", "test", "preview")
TARGETS = ("shorts", "tiktok")   # 27.10.2026: preview_frame?target= - תצוגה לאורך

_lock = threading.Lock()
_episodes: "OrderedDict[str, Tuple[Any, Any]]" = OrderedDict()
_charts: "OrderedDict[str, Any]" = OrderedDict()


def _fingerprint(folder: str, overrides: Mapping[str, Any]) -> str:
    """משתנה כשמשהו בתיקיית הפרק משתנה (הגדרות, נתונים, אירועים) או כשה-override משתנה - וגם כשתיקיית התמונות
    של הישויות משתנה (גל 51: היא מחוץ לתיקיית הפרק, והעלאה של תמונה לא משנה את ה-override)."""
    parts = [json.dumps(overrides, sort_keys=True, ensure_ascii=False, default=str)]
    images = str((overrides.get("images") or {}).get("folder") or "")
    folders = [folder] + ([images] if images and os.path.isabs(images) and os.path.isdir(images) else [])
    for root, _dirs, files in (entry for path in folders for entry in os.walk(path)):
        for name in sorted(files):
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            parts.append(f"{os.path.relpath(path, folder)}|{stat.st_size}|{stat.st_mtime_ns}")
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def _evict(cache: "OrderedDict[str, Any]", limit: int, close: bool = False) -> None:
    while len(cache) > limit:
        _key, value = cache.popitem(last=False)
        if close:
            try:
                value.close()
            except Exception:
                pass


def _episode(folder: str, overrides: Mapping[str, Any], scale: float, mode: str, target: str = "") -> Tuple[str, Any, Any]:
    from dataviz.config import load_config, preview_config
    from dataviz.episode import build_episode
    from dataviz.plan import build_plan

    target = target if target in TARGETS else ""
    key = f"{_fingerprint(folder, overrides)}|{scale}|{mode}|{target}"
    if key in _episodes:
        _episodes.move_to_end(key)
        episode, plan = _episodes[key]
        return key, episode, plan
    config = load_config(os.path.join(folder, "config.yaml"), dict(overrides))
    if target:   # 27.10.2026: התצוגה לאורך לצד הרגילה (Shorts / TikTok) - אותו פרק בגודל ובפריסה של היעד
        from dataviz.targets import apply_target
        config = apply_target(config, target)
    config = preview_config(config, scale)
    episode = build_episode(config)
    plan = build_plan(episode, mode)
    _episodes[key] = (episode, plan)
    _evict(_episodes, MAX_EPISODES)
    return key, episode, plan


def _chart(episode_key: str, episode: Any, chart: Optional[str], theme: Optional[str]) -> Any:
    from dataviz.charts import make_chart
    from dataviz.render import chart_context
    from dataviz.themes import get_theme, theme_to_dict

    key = f"{episode_key}|{chart or ''}|{theme or ''}"
    if key in _charts:
        _charts.move_to_end(key)
        return _charts[key]
    ctx = chart_context(episode, chart)
    if theme:
        ctx["theme"] = theme_to_dict(get_theme(theme, episode.config.get("theme_overrides")))
    _charts[key] = make_chart(ctx)
    _evict(_charts, MAX_CHARTS, close=True)
    return _charts[key]


def _prune(cache_dir: str) -> None:
    try:
        files = sorted((os.path.join(cache_dir, n) for n in os.listdir(cache_dir) if n.endswith((".png", ".gif", ".mp4"))), key=os.path.getmtime)
    except OSError:
        return
    for path in files[:max(0, len(files) - MAX_CACHE_FILES)]:
        for victim in (path, path[:-4] + ".json"):   # .gif (גל 53) / .mp4 (27.10.2026) - בלי קובץ json, ה-remove פשוט נכשל בשקט
            try:
                os.remove(victim)
            except OSError:
                pass


def _axes_meta(chart_obj: Any, episode: Any, frame: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """20.10.2026: איפה אזור הנתונים בתמונה (חלקים 0-1, מלמטה-שמאל) והטווחים שלו - כדי שלחיצה על התצוגה תהפוך
    לתאריך וערך (הערה על הגרף). רק בתרשים שמקבל הערות, בפריים של הגרף עצמו."""
    if not getattr(chart_obj, "ANNOTATES", False) or frame.get("k") != "main":
        return None
    box = chart_obj.ax.get_position()
    return {"box": [box.x0, box.y0, box.x1, box.y1], "xlim": list(chart_obj.ax.get_xlim()), "ylim": list(chart_obj.ax.get_ylim()),
            "start": episode.dates[0].strftime("%Y-%m-%d")}


def _frame_meta(chart_obj: Any, episode: Any, plan: List[Any], index: int) -> Dict[str, Any]:
    """27.10.2026: מה שהתצוגה צריכה כדי לערוך על הפריים: אזורי הלחיצה, התאריך ב-ISO (מצב במאי), מלבן אזור הנתונים
    (גרירת תיבת הסיום) והגודל בנקודות (גרירת הערה - dx/dy בנקודות, כמו ב-matplotlib)."""
    frame = plan[index] if plan else {}
    box = chart_obj.ax.get_position()
    width, height = chart_obj.fig.get_size_inches() * 72
    x = frame.get("x")
    iso = episode.dates[min(int(x), len(episode.dates) - 1)].strftime("%Y-%m-%d") if x is not None and len(episode.dates) else ""
    return {"hits": chart_obj.hit_regions(), "iso_date": iso, "axes_box": [box.x0, box.y0, box.x1, box.y1],
            "fig_pt": [round(float(width), 2), round(float(height), 2)]}


def preview_frame(folder: str, overrides: Mapping[str, Any], cache_dir: str, position: float, *,
                  chart: Optional[str] = None, theme: Optional[str] = None, scale: float = 0.35, mode: str = "full",
                  target: str = "") -> Dict[str, Any]:
    """PNG של הפריים בנקודה position (0 = ההתחלה, 1 = הסוף). מחזיר {path, index, frames, kind, ...}.
    target (27.10.2026): shorts / tiktok - אותו רגע בגודל לאורך של היעד."""
    scale = min(SCALES, key=lambda s: abs(s - float(scale)))
    mode = mode if mode in MODES else "full"
    position = max(0.0, min(1.0, float(position)))
    # מסלול מהיר: אותה נקודה כבר צוירה (למשל תמונת הכרטיס של פרק) - בלי לבנות את הפרק בכלל
    # גל 59: |m2 - במטא יש עכשיו גם תאריך וקצב פריימים; פריימים שנשמרו לפני כן (בלי שניהם) לא נטענים מהמטמון
    quick = hashlib.sha1(f"{_fingerprint(folder, overrides)}|{scale}|{mode}|{chart}|{theme}|{position:.3f}|{target}|m4".encode("utf-8")).hexdigest()[:24]   # 20.10.2026: m3 - גם הצירים; 27.10: m4 - אזורי לחיצה
    quick_png, quick_meta = os.path.join(cache_dir, quick + ".png"), os.path.join(cache_dir, quick + ".json")
    if os.path.isfile(quick_png) and os.path.isfile(quick_meta):
        try:
            with open(quick_meta, encoding="utf-8") as f:
                meta = json.load(f)
            os.utime(quick_png)
            return {"path": quick_png, **meta}
        except (OSError, ValueError):
            pass
    with _lock:
        episode_key, episode, plan = _episode(folder, overrides, scale, mode, target)
        index = int(round(position * (len(plan) - 1))) if plan else 0
        os.makedirs(cache_dir, exist_ok=True)
        chart_obj = _chart(episode_key, episode, chart, theme)
        chart_obj.render(plan[index])
        tmp = quick_png + ".tmp.png"
        chart_obj.save_png(tmp)
        os.replace(tmp, quick_png)
        meta = {"index": index, "frames": len(plan), "kind": plan[index]["k"] if plan else "",
                "date": str(plan[index].get("date") or "") if plan else "", "fps": float(episode.config["video"]["fps"]),   # גל 59
                "axes": _axes_meta(chart_obj, episode, plan[index]) if plan else None,
                **_frame_meta(chart_obj, episode, plan, index)}
        with open(quick_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        _prune(cache_dir)
    return {"path": quick_png, **meta}


# זמן רינדור משוער לפריים בגודל מלא (1920x1080) בתהליך אחד - הערכה גסה, לא מדידה
SECONDS_PER_FULL_HD_FRAME = 0.06


# סבב הייצוב (16.10.2026): האומדן הציג 23:47 דקות לרינדור שלקח 6:16. שתי סיבות: (1) לכל ריצה תקורה קבועה (הפעלת
# התהליכים והקידוד) - בריצה קצרה היא ניפחה את הקצב; (2) ריצות על מחשב עמוס (טסטים או רינדור אחר במקביל) נשארו בחשבון
# לתמיד. עומס רק מאט - לכן הבסיס הוא הריצה המהירה מבין האחרונות, וריצה איטית ממנה פי 2 ומעלה לא נספרת.
RUN_OVERHEAD_SECONDS = 12             # בתוך הזמן שנמדד (render_video), לא תלוי במספר הפריימים
START_SECONDS = 13                    # מחוץ לו: עליית התהליך, טעינת הנתונים ובניית התכנית
LEARN_MIN_SECONDS = 3 * RUN_OVERHEAD_SECONDS   # ריצה קצרה מזה היא בעיקר תקורה - לא לומדים ממנה
RECENT_RUNS = 5
SLOW_FACTOR = 2.0


def learned_rate(stats_path: str) -> Tuple[Optional[float], int]:
    """גל 54: שניות-תהליך לכל מגה-פיקסל של פריים, בלי התקורה הקבועה של ריצה - לפי RECENT_RUNS הריצות הארוכות
    האחרונות, בלי אלה שאיטיות פי SLOW_FACTOR מהמהירה שבהן (חציון של השאר). (None, 0) כשאין ריצות."""
    try:
        with open(stats_path, "r", encoding="utf-8") as f:
            runs = json.load(f).get("runs", [])
    except (OSError, ValueError, AttributeError):
        return None, 0
    usable = [r for r in runs if isinstance(r, dict) and int(r.get("rendered_frames") or 0) > 0 and int(r.get("pixels") or 0) > 0
              and float(r.get("seconds") or 0) >= LEARN_MIN_SECONDS]
    rates = [(float(r["seconds"]) - RUN_OVERHEAD_SECONDS) * int(r["workers"]) / (int(r["rendered_frames"]) * int(r["pixels"]) / 1e6)
             for r in usable[-RECENT_RUNS:]]
    if not rates:
        return None, 0
    kept = [rate for rate in rates if rate <= SLOW_FACTOR * min(rates)]
    return statistics.median(kept), len(kept)


def estimate(folder: str, overrides: Mapping[str, Any], workers: int = 4, stats_path: str = "") -> Dict[str, Any]:
    """אורך הסרטון ומשך רינדור משוער לכל מצב, לפני שמריצים - לפי הריצות האמיתיות כשיש (stats_path, גל 54)."""
    from dataviz.config import load_config

    config = load_config(os.path.join(folder, "config.yaml"), dict(overrides))
    fps = int(config["video"]["fps"])
    pixels = int(config["video"]["width"]) * int(config["video"]["height"])
    rate, runs = learned_rate(stats_path) if stats_path else (None, 0)
    per_frame = rate * pixels / 1e6 if rate else SECONDS_PER_FULL_HD_FRAME * max(0.25, pixels / (1920 * 1080))
    result: Dict[str, Any] = {"fps": fps, "width": config["video"]["width"], "height": config["video"]["height"], "modes": {}, "learned_runs": runs}
    for mode in MODES:
        with _lock:
            _key, _episode_obj, plan = _episode(folder, overrides, SCALES[0], mode)
        frames = len(plan)
        scale_factor = 0.25 if mode == "preview" else 1.0
        result["modes"][mode] = {
            "frames": frames,
            "seconds": round(frames / fps, 1),
            "render_seconds": round(frames * per_frame * scale_factor / max(1, workers) + RUN_OVERHEAD_SECONDS + START_SECONDS, 0),
        }
    result["modes"]["shorts"] = _shorts_estimate(folder, overrides, config, rate, workers)
    return result


def _shorts_estimate(folder: str, overrides: Mapping[str, Any], config: Mapping[str, Any], rate: Optional[float], workers: int) -> Dict[str, Any]:
    """23.10.2026 (המלצה 10): גם ל-Shorts - כמה ייצאו (הימים הדרמטיים), האורך של כל אחד, והרינדור בגודל לאורך; כל Short ריצה
    משלו (render_video לכל אחד), אז התקורה הקבועה לכל אחד."""
    from dataviz.shorts import build_shorts
    from dataviz.targets import apply_target

    fps = int(config["video"]["fps"])
    vertical = apply_target(config, "shorts")["video"]
    pixels = int(vertical["width"]) * int(vertical["height"])
    per_frame = rate * pixels / 1e6 if rate else SECONDS_PER_FULL_HD_FRAME * max(0.25, pixels / (1920 * 1080))
    with _lock:
        _key, episode_obj, plan = _episode(folder, overrides, SCALES[0], "full")
    shorts = build_shorts(episode_obj, plan)
    frames = sum(len(short) for short in shorts)
    return {"count": len(shorts), "frames": frames, "seconds": round(frames / max(len(shorts), 1) / fps, 1),
            "render_seconds": round(frames * per_frame / max(1, workers) + len(shorts) * RUN_OVERHEAD_SECONDS + START_SECONDS, 0)}


def episode_overview(folder: str, overrides: Mapping[str, Any]) -> Dict[str, Any]:
    """גל 39: הישויות (לפני שמות חלופיים והחרגה - כדי שאפשר יהיה לבטל אותם) עם הסכום של כל אחת,
    וטווח התאריכים - לעורך הישויות ולציר האירועים."""
    base = {k: v for k, v in overrides.items() if k != "entities"}
    with _lock:
        _key, episode, _plan = _episode(folder, base, SCALES[0], "preview")
    totals = episode.cum[-1] if len(episode.cum) else []
    entities: List[Dict[str, Any]] = [{"name": str(e), "total": float(totals[i]) if len(totals) else 0.0} for i, e in enumerate(episode.entities)]
    entities.sort(key=lambda e: -float(e["total"]))
    dates = episode.dates
    return {"entities": entities, "date_range": [dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d")] if len(dates) else []}


# ---------- גל 53: סימנים על הסליידר ותצוגה מונפשת ----------
def markers(folder: str, overrides: Mapping[str, Any], mode: str = "full") -> Dict[str, Any]:
    """איפה בסרטון (0-1, כמו הסליידר) מתחילים כרטיסי האירועים, הפרקים והעצירות, ואיפה נגמרים הטיזר והפתיח
    ומתחיל הסיום - מאותה תכנית שהתצוגה החיה מציירת ממנה."""
    mode = mode if mode in MODES else "full"
    with _lock:
        _key, _episode_obj, plan = _episode(folder, overrides, SCALES[0], mode)
    last = max(len(plan) - 1, 1)
    found: List[Dict[str, Any]] = []
    previous: Dict[str, Any] = {}
    for index, frame in enumerate(plan):
        kind = frame.get("k")
        card = (frame.get("card") or (None,))[0]
        hold = frame.get("hold") or {}
        hold_id = (hold.get("kind"), hold.get("title") or hold.get("text")) if hold else None
        if card and card != previous.get("card"):
            found.append({"pos": index / last, "kind": "event", "label": str(card)})
        if hold_id and hold_id != previous.get("hold"):
            found.append({"pos": index / last, "kind": str(hold.get("kind")), "label": str(hold_id[1] or "")})
        if previous.get("kind") == "intro" and kind != "intro":
            found.append({"pos": index / last, "kind": "start", "label": ""})
        if kind == "outro" and previous.get("kind") != "outro":
            found.append({"pos": index / last, "kind": "outro", "label": ""})
        previous = {"card": card, "hold": hold_id, "kind": kind}
    return {"frames": len(plan), "markers": found}


class PreviewCancelled(Exception):
    """20.10.2026: בקשת תצוגה חיה חדשה יותר הגיעה - הישנה מפסיקה בין פריימים (ומשחררת את המנעול)."""


def preview_clip(folder: str, overrides: Mapping[str, Any], cache_dir: str, position: float, *, seconds: float = 3.0, fps: int = 10,
                 chart: Optional[str] = None, theme: Optional[str] = None, scale: float = 0.2, mode: str = "full",
                 cancel: Optional[Any] = None, fmt: str = "gif", ffmpeg: str = "") -> Dict[str, Any]:
    """GIF קצר (seconds שניות ב-fps פריימים לשנייה) סביב הנקודה position - "לראות איך זה זז" בלי לרנדר סרטון.
    הפריימים נלקחים מהתכנית בצעדים של קצב הסרטון / fps, ונשמרים במטמון כמו הפריימים הבודדים.
    27.10.2026: fmt="mp4" (עם ffmpeg) - וידאו אמיתי במקום GIF: בלי הגבלת 128 הצבעים, חד יותר וקטן יותר, מקודד בכרטיס
    המסך (NVENC) כשאפשר. ffmpeg שנכשל - GIF כמו קודם."""
    from PIL import Image
    scale = min(SCALES, key=lambda s: abs(s - float(scale)))
    mode = mode if mode in MODES else "full"
    position = max(0.0, min(1.0, float(position)))
    seconds = max(1.0, min(6.0, float(seconds)))
    fps = max(4, min(20, int(fps)))
    key = hashlib.sha1(f"clip|{_fingerprint(folder, overrides)}|{scale}|{mode}|{chart}|{theme}|{position:.3f}|{seconds}|{fps}".encode("utf-8")).hexdigest()[:24]
    gif_path = os.path.join(cache_dir, key + ".gif")
    mp4_path = os.path.join(cache_dir, key + ".mp4")
    if fmt == "mp4" and ffmpeg and os.path.isfile(mp4_path):
        os.utime(mp4_path)
        return {"path": mp4_path, "format": "mp4"}
    if os.path.isfile(gif_path) and fmt != "mp4":
        os.utime(gif_path)
        return {"path": gif_path, "format": "gif"}
    with _lock:
        episode_key, episode, plan = _episode(folder, overrides, scale, mode)
        chart_obj = _chart(episode_key, episode, chart, theme)
        step = max(1, int(round(float(episode.config["video"]["fps"]) / fps)))
        count = int(seconds * fps)
        center = int(round(position * (len(plan) - 1)))
        start = max(0, min(center - count * step // 2, len(plan) - 1 - (count - 1) * step))
        indices = [min(start + k * step, len(plan) - 1) for k in range(count)]
        width, height = chart_obj.size
        raw = []
        for i in indices:
            if cancel is not None and cancel():   # 20.10.2026: בתצוגה החיה - יש כבר בקשה חדשה יותר
                raise PreviewCancelled()
            raw.append(chart_obj.render(plan[i]))
        os.makedirs(cache_dir, exist_ok=True)
        if fmt == "mp4" and ffmpeg and encode_mp4(ffmpeg, raw, (width, height), fps, mp4_path):
            _prune(cache_dir)
            return {"path": mp4_path, "format": "mp4", "start": indices[0], "frames": len(indices)}
        images = [Image.frombytes("RGBA", (width, height), frame).convert("RGB").quantize(colors=128) for frame in raw]
        tmp = gif_path + ".tmp.gif"
        images[0].save(tmp, save_all=True, append_images=images[1:], duration=int(round(1000 / fps)), loop=0, optimize=True)
        os.replace(tmp, gif_path)
        _prune(cache_dir)
    return {"path": gif_path, "format": "gif", "start": indices[0], "frames": len(indices)}


def encode_mp4(ffmpeg: str, frames: List[bytes], size: Tuple[int, int], fps: int, out_path: str) -> bool:
    """27.10.2026: פריימי RGBA -> MP4 קצר לתצוגה (h264, yuv420p, faststart) - בכרטיס המסך כשאפשר, אחרת במעבד. False
    כששני הניסיונות נכשלו (הקורא חוזר ל-GIF)."""
    import subprocess

    from dataviz.render import nvenc_available
    width, height = size
    base = [ffmpeg, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"]
    codecs = [["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26"]]
    if width >= 145 and height >= 49 and nvenc_available(ffmpeg):   # מתחת לזה NVENC מסרב
        codecs.insert(0, ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "27"])
    data = b"".join(frames)
    tmp = out_path + ".tmp.mp4"
    for codec in codecs:
        try:
            result = subprocess.run(base + codec + [tmp], input=data, capture_output=True, timeout=60,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, out_path)
            return True
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


# ---------- 27.10.2026: תאריך לכל מקום בסליידר, ו-sparkline לכל ישות ----------
def timeline(folder: str, overrides: Mapping[str, Any], mode: str = "full", samples: int = 240) -> Dict[str, Any]:
    """[מקום בסליידר (0-1), תאריך ISO] לאורך הקטע הראשי - מצב הבמאי ובלוקי הסיפור הנגררים ממירים בעזרתו מקום לתאריך
    ותאריך למקום (אינטרפולציה בין הדגימות). דגימה מכל פריים שהתאריך שלו משתנה, עד samples נקודות."""
    mode = mode if mode in MODES else "full"
    with _lock:
        _key, episode, plan = _episode(folder, overrides, SCALES[0], mode)
    last = max(len(plan) - 1, 1)
    points: List[List[Any]] = []
    previous = None
    for index, frame in enumerate(plan):
        if frame.get("k") != "main" or frame.get("teaser") or frame.get("x") is None:
            continue
        day = min(int(frame["x"]), len(episode.dates) - 1)
        if day != previous:
            points.append([round(index / last, 5), episode.dates[day].strftime("%Y-%m-%d")])
            previous = day
    if len(points) > samples:   # דגימה שווה, עם הראשונה והאחרונה
        step = (len(points) - 1) / (samples - 1)
        points = [points[round(k * step)] for k in range(samples)]
    return {"points": points, "start": episode.dates[0].strftime("%Y-%m-%d") if len(episode.dates) else "",
            "end": episode.dates[-1].strftime("%Y-%m-%d") if len(episode.dates) else ""}


def sparklines(folder: str, overrides: Mapping[str, Any], buckets: int = 40) -> Dict[str, Any]:
    """לכל ישות: הערך היומי מקובץ ל-buckets נקודות (סכום בכל קטע; לרמה - הממוצע), והקטעים שיש בהם קפיצה חשודה
    (dataviz/cleaning.find_outliers) - בשביל גרף קטן ליד השם בלשונית הישויות."""
    import numpy as np
    import pandas as pd

    from dataviz.cleaning import find_outliers
    base = {k: v for k, v in overrides.items() if k != "entities"}
    with _lock:
        _key, episode, _plan = _episode(folder, base, SCALES[0], "preview")
    days = len(episode.dates)
    if not days:
        return {"entities": {}}
    edges = np.linspace(0, days, min(buckets, days) + 1).astype(int)
    levels = {str(e) for e in episode.levels}
    matrix = pd.DataFrame(episode.daily, index=episode.dates, columns=[str(e) for e in episode.entities])
    jumps: Dict[str, set] = {}
    for found in find_outliers(matrix, limit=200, levels=list(levels)):
        day = int(episode.dates.searchsorted(pd.Timestamp(found["date"])))
        jumps.setdefault(found["entity"], set()).add(int(np.searchsorted(edges, day, side="right") - 1))
    result: Dict[str, Any] = {}
    for col, entity in enumerate(episode.entities):
        name = str(entity)
        series = episode.cum[:, col] if name in levels else episode.daily[:, col]
        values = [float(series[a:b].mean() if name in levels else series[a:b].sum()) for a, b in zip(edges[:-1], edges[1:]) if b > a]
        result[name] = {"values": [round(v, 4) for v in values], "jumps": sorted(jumps.get(name, set()))}
    return {"entities": result, "buckets": len(edges) - 1}
