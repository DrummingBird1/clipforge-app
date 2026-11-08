# utils/video/video_editor_layers.py
#
# גל 7ב של 102-ההצעות (items 79-82, 87, 88, 89): שכבות שמורכבות *מעל* הפריים
# הסופי (אחרי watermark/PiP, לפני ה-fade) - כמה שכבות טקסט/תמונה עם טווח-זמן לכל
# אחת (79), טקסט מונפש fade/typewriter/slide + טיימר/ספירה-לאחור (80), סרגל
# התקדמות שרוף (82), מסגרת (88) וחותמת-זמן (89). פונקציות טהורות שבונות מחרוזות
# filtergraph - הכתיבה לדיסק (קובצי הטקסט) מבודדת ב-write_layer_text_files, כדי
# שכל השאר ייבדק בלי ffmpeg.
#
# טקסט תמיד דרך textfile= (לא text=) - אותה סיבה בדיוק כמו build_drawtext_filter
# ב-utils/video/video_editor.py (escaping של תווים מיוחדים). טיימר/חותמת-זמן משתמשים
# ב-expansion=normal עם ביטויי %{eif}/%{pts} *בתוך הקובץ* - שם אין escaping של
# ה-filtergraph בכלל, רק של הביטוי עצמו (נבדק מול ffmpeg אמיתי).

import json
import math
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

LAYER_TYPES: Tuple[str, ...] = ("text", "image", "timer", "timestamp", "video", "filename")
# גל 26: שכבת וידאו (B-roll) - קליפ שני בטווח-זמן בתוך הפלט: מסך מלא (חיתוך למילוי),
# מותאם (שוליים) או חלון (PiP), מנקודת-התחלה בקליפ, ושמע מושתק/מעורבב/במקום הראשי.
VIDEO_LAYER_FITS: Tuple[str, ...] = ("fill", "fit", "pip")
VIDEO_LAYER_AUDIO: Tuple[str, ...] = ("mute", "mix", "replace")
LAYER_ANIMATIONS: Tuple[str, ...] = ("none", "fade", "typewriter", "slide")
LAYER_POSITIONS: Tuple[str, ...] = ("top-left", "top-center", "top-right", "center", "bottom-left", "bottom-center", "bottom-right", "custom")
TIMER_MODES: Tuple[str, ...] = ("countdown", "elapsed")
MAX_LAYERS = 20
MAX_TEXT_CHARS = 300
ANIMATION_SECONDS = 0.5
TYPEWRITER_MAX_STEPS = 60
MAX_KEYFRAMES = 30
EASINGS: Tuple[str, ...] = ("linear", "ease")
PROGRESS_BAR_POSITIONS: Tuple[str, ...] = ("bottom", "top")
_HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")
_FONT_RE = re.compile(r"^[\w .\-]{1,60}$")


def _num(value: Any, default: Optional[float], low: float, high: float) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number):
        return default
    return max(low, min(high, number))


def _color(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if not _HEX_COLOR_RE.match(text):
        return default
    return "#" + text.lstrip("#").upper()


def sanitize_layers(raw: Any, require_existing_images: bool = True) -> List[Dict[str, Any]]:
    """רשימת שכבות מהממשק/מקובץ JSON -> רשימה נקייה עם ערכי ברירת-מחדל. שכבה
    לא תקינה (סוג לא מוכר, טקסט ריק, תמונה חסרה) מושמטת - לא מפילה את הריצה."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            return []
    if not isinstance(raw, list):
        return []
    clean: List[Dict[str, Any]] = []
    for item in raw[:MAX_LAYERS]:
        if not isinstance(item, dict):
            continue
        # גל 29: 👁 ברשימת השכבות - שכבה מוסתרת נשמרת בפרויקט אבל לא מרונדרת
        if item.get("hidden") is True:
            continue
        kind = str(item.get("type") or "text")
        if kind not in LAYER_TYPES:
            continue
        start = _num(item.get("start"), 0.0, 0.0, 86400.0) or 0.0
        end = _num(item.get("end"), None, 0.0, 86400.0)
        if end is not None and end <= start:
            end = None
        layer: Dict[str, Any] = {
            "type": kind, "start": start, "end": end,
            "position": item.get("position") if item.get("position") in LAYER_POSITIONS else "bottom-center",
            "opacity": _num(item.get("opacity"), 1.0, 0.0, 1.0),
        }
        # גל 14: keyframes - מיקום/שקיפות/גודל לאורך זמן (זמן הפלט, בשניות)
        keyframes = sanitize_keyframes(item.get("keyframes"))
        if keyframes:
            layer["keyframes"] = keyframes
            layer["easing"] = item.get("easing") if item.get("easing") in EASINGS else "linear"
        # גל 10: מיקום חופשי (גרירה על התצוגה המקדימה) - מרכז השכבה בשברים 0-1 של
        # הפלט. "custom" בלי x/y תקינים חוזר למיקום ברירת-המחדל.
        if layer["position"] == "custom":
            cx, cy = _num(item.get("x"), None, 0.0, 1.0), _num(item.get("y"), None, 0.0, 1.0)
            if cx is None or cy is None:
                layer["position"] = "bottom-center"
            else:
                layer.update(x=cx, y=cy)
        if kind == "image":
            path = str(item.get("path") or "").strip()
            if not path or (require_existing_images and not os.path.isfile(path)):
                continue
            layer.update(path=path, scale=_num(item.get("scale"), 0.2, 0.02, 1.0))
        elif kind == "video":
            path = str(item.get("path") or "").strip().strip('"')
            if not path or (require_existing_images and not os.path.isfile(path)):
                continue
            layer.update(
                path=path, source_in=_num(item.get("source_in"), 0.0, 0.0, 86400.0) or 0.0,
                fit=item.get("fit") if item.get("fit") in VIDEO_LAYER_FITS else "fill",
                scale=_num(item.get("scale"), 0.35, 0.05, 1.0),
                audio=item.get("audio") if item.get("audio") in VIDEO_LAYER_AUDIO else "mute",
                volume=_num(item.get("volume"), 1.0, 0.0, 2.0),
            )
        else:
            text = str(item.get("text") or "").replace("\r", "")[:MAX_TEXT_CHARS]
            if kind == "text" and not text.strip():
                continue
            font = str(item.get("font") or "Arial").strip()
            layer.update(
                text=text, font=font if _FONT_RE.match(font) else "Arial",
                font_size=int(_num(item.get("font_size"), 48, 8, 300) or 48),
                color=_color(item.get("color"), "#FFFFFF"), box=bool(item.get("box")),
                animation=item.get("animation") if item.get("animation") in LAYER_ANIMATIONS else "none",
            )
            if kind == "timer":
                layer["timer_mode"] = item.get("timer_mode") if item.get("timer_mode") in TIMER_MODES else "countdown"
                layer["timer_seconds"] = _num(item.get("timer_seconds"), None, 1.0, 86400.0)
            if kind == "timestamp":
                layer["epoch"] = _num(item.get("epoch"), None, 0.0, 4.0e9)
        clean.append(layer)
    return clean


def _fmt(value: float) -> str:
    return ("%.3f" % value).rstrip("0").rstrip(".") or "0"


def sanitize_keyframes(raw: Any) -> List[Dict[str, float]]:
    """[{t, x?, y?, opacity?, scale?}] -> ממוין לפי t, ערכים מהודקים, עד MAX_KEYFRAMES.
    כל מאפיין מונפש רק אם לפחות שני מפתחות מגדירים אותו (אחרת אין מה לאנפש)."""
    if not isinstance(raw, list):
        return []
    frames: List[Dict[str, float]] = []
    for item in raw[:MAX_KEYFRAMES]:
        if not isinstance(item, dict):
            continue
        t = _num(item.get("t"), None, 0.0, 86400.0)
        if t is None:
            continue
        frame: Dict[str, float] = {"t": t}
        for key, low, high in (("x", 0.0, 1.0), ("y", 0.0, 1.0), ("opacity", 0.0, 1.0), ("scale", 0.1, 5.0)):
            value = _num(item.get(key), None, low, high)
            if value is not None:
                frame[key] = value
        frames.append(frame)
    frames.sort(key=lambda f: f["t"])
    return frames if len(frames) >= 2 else []


def keyframe_expr(frames: Sequence[Dict[str, float]], key: str, easing: str = "linear") -> Optional[str]:
    """ביטוי ffmpeg (תלוי t) לערך של key לאורך המפתחות - קבוע לפני הראשון ואחרי
    האחרון, אינטרפולציה ביניהם (ליניארית או smoothstep). None אם פחות משני מפתחות
    מגדירים את key."""
    points = [(f["t"], f[key]) for f in frames if key in f]
    if len(points) < 2:
        return None
    expr = _fmt(points[-1][1])
    for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
        span = max(t1 - t0, 1e-3)
        u = f"(t-{_fmt(t0)})/{_fmt(span)}"
        eased = f"({u})*({u})*(3-2*({u}))" if easing == "ease" else f"({u})"
        segment = f"{_fmt(v0)}+({_fmt(v1 - v0)})*{eased}" if v1 != v0 else _fmt(v0)
        expr = f"if(lt(t,{_fmt(t1)}),{segment},{expr})"
    return f"if(lt(t,{_fmt(points[0][0])}),{_fmt(points[0][1])},{expr})"


def _enable_expr(start: float, end: Optional[float]) -> str:
    if end is None:
        return f"gte(t,{_fmt(start)})"
    return f"between(t,{_fmt(start)},{_fmt(end)})"


def _text_xy(position: str, cx: Optional[float] = None, cy: Optional[float] = None) -> Tuple[str, str]:
    if position == "custom" and cx is not None and cy is not None:
        # מרכז הטקסט בנקודה, מוצמד לגבולות הפריים (לא יוצא מהמסך)
        return f"max(0,min(w-text_w,w*{_fmt(cx)}-text_w/2))", f"max(0,min(h-text_h,h*{_fmt(cy)}-text_h/2))"
    margin = "h*0.04"
    horizontal = position.split("-")[-1] if "-" in position else "center"
    vertical = position.split("-")[0] if "-" in position else "center"
    x = {"left": margin, "right": f"w-text_w-{margin}"}.get(horizontal, "(w-text_w)/2")
    y = {"top": margin, "bottom": f"h-text_h-{margin}"}.get(vertical, "(h-text_h)/2")
    return x, y


def _overlay_xy(position: str, cx: Optional[float] = None, cy: Optional[float] = None) -> Tuple[str, str]:
    if position == "custom" and cx is not None and cy is not None:
        return f"max(0,min(W-w,W*{_fmt(cx)}-w/2))", f"max(0,min(H-h,H*{_fmt(cy)}-h/2))"
    margin = "H*0.04"
    horizontal = position.split("-")[-1] if "-" in position else "center"
    vertical = position.split("-")[0] if "-" in position else "center"
    x = {"left": margin, "right": f"W-w-{margin}"}.get(horizontal, "(W-w)/2")
    y = {"top": margin, "bottom": f"H-h-{margin}"}.get(vertical, "(H-h)/2")
    return x, y


def _alpha_expr(layer: Dict[str, Any]) -> str:
    opacity = float(layer.get("opacity", 1.0))
    if layer.get("animation") != "fade":
        return _fmt(opacity)
    start, end, f = float(layer["start"]), layer.get("end"), ANIMATION_SECONDS
    fade_in = f"(t-{_fmt(start)})/{_fmt(f)}"
    if end is None:
        expr = f"if(lt(t,{_fmt(start + f)}),{fade_in},1)"
    else:
        fade_out = f"({_fmt(float(end))}-t)/{_fmt(f)}"
        expr = f"if(lt(t,{_fmt(start + f)}),{fade_in},if(gt(t,{_fmt(float(end) - f)}),{fade_out},1))"
    return f"{_fmt(opacity)}*{expr}" if opacity < 1.0 else expr


def timer_expansion(layer: Dict[str, Any], output_duration: Optional[float]) -> str:
    """תוכן קובץ-הטקסט של טיימר (mm:ss) - countdown יורד עד 0 בסוף הטווח (או אחרי
    timer_seconds), elapsed סופר מתחילת השכבה."""
    start = float(layer["start"])
    if layer.get("timer_mode") == "elapsed":
        seconds_expr = f"max(0,t-{_fmt(start)})"
    else:
        span = layer.get("timer_seconds")
        if span is None:
            end = layer.get("end") if layer.get("end") is not None else output_duration
            span = max(1.0, float(end or 60.0) - start)
        seconds_expr = f"max(0,{_fmt(start + float(span))}-t)"
    return f"%{{eif:floor({seconds_expr}/60):d:2}}:%{{eif:mod(floor({seconds_expr}),60):d:2}}"


def timestamp_expansion(layer: Dict[str, Any]) -> str:
    """חותמת-זמן אמיתית (תאריך+שעה) - epoch של תחילת הפלט + זמן-הפלט."""
    epoch = int(layer.get("epoch") or 0)
    return f"%{{pts:localtime:{epoch}:%Y-%m-%d %H\\:%M\\:%S}}"


def fill_filename_layers(layers: Sequence[Dict[str, Any]], source_path: str) -> None:
    """שכבות "שם הקובץ": הטקסט הוא שם קובץ המקור (בלי נתיב) של הקובץ שמרונדר עכשיו. משנה את השכבות במקום
    (הקורא מעתיק אותן לכל קובץ). הטקסט נכתב לקובץ-טקסט עם expansion=none, ולכן גרשיים, רווחים ו-% בשם
    נשארים תווים רגילים - בלי escaping של ה-filtergraph."""
    name = os.path.basename(str(source_path))[:MAX_TEXT_CHARS]
    for layer in layers:
        if layer.get("type") == "filename":
            layer["text"] = name


def layer_text_contents(layer: Dict[str, Any], output_duration: Optional[float]) -> List[str]:
    """התוכן לכל קובץ-טקסט שהשכבה צריכה: אחד לרוב, כמה (קידומות הולכות וגדלות)
    ל-typewriter. שכבות תמונה - רשימה ריקה."""
    kind = layer["type"]
    if kind == "timer":
        return [timer_expansion(layer, output_duration)]
    if kind == "timestamp":
        return [timestamp_expansion(layer)]
    if kind == "filename":
        return [layer["text"]] if layer.get("text") else []
    if kind != "text":
        return []
    text = layer["text"]
    if layer.get("animation") != "typewriter" or len(text) <= 1:
        return [text]
    step = max(1, math.ceil(len(text) / TYPEWRITER_MAX_STEPS))
    return [text[:i] for i in range(step, len(text), step)] + [text]


def write_layer_text_files(layers: Sequence[Dict[str, Any]], directory: str, output_duration: Optional[float]) -> Dict[int, List[str]]:
    """כותב את קובצי הטקסט של כל השכבות לתיקייה (זמנית, של הקורא) -> {index: [paths]}."""
    os.makedirs(directory, exist_ok=True)
    files: Dict[int, List[str]] = {}
    for index, layer in enumerate(layers):
        paths = []
        for n, content in enumerate(layer_text_contents(layer, output_duration)):
            path = os.path.join(directory, f"layer_{index}_{n}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            paths.append(path)
        if paths:
            files[index] = paths
    return files


def _escape_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:")


def _drawtext(text_file: str, layer: Dict[str, Any], enable: str, x: str, y: str, alpha: str, expansion: str) -> str:
    color = layer["color"].lstrip("#")
    box = ":box=1:boxcolor=black@0.5:boxborderw=12" if layer.get("box") else ""
    size = layer["font_size"]
    fontsize = f"'{size}'" if isinstance(size, str) else size
    return (
        f"drawtext=textfile='{_escape_path(text_file)}':font={layer['font']}:fontsize={fontsize}"
        f":fontcolor=0x{color}:expansion={expansion}{box}:x='{x}':y='{y}':alpha='{alpha}':enable='{enable}'"
    )


def build_text_layer_filters(layer: Dict[str, Any], text_files: Sequence[str]) -> List[str]:
    if not text_files:
        return []
    x, y = _text_xy(layer["position"], layer.get("x"), layer.get("y"))
    start, end = float(layer["start"]), layer.get("end")
    alpha = _alpha_expr(layer)
    frames, easing = layer.get("keyframes") or [], layer.get("easing", "linear")
    if frames:
        # גל 14: keyframes גוברים על המיקום/השקיפות הקבועים (והגודל - fontsize הוא ביטוי ב-drawtext)
        kx, ky = keyframe_expr(frames, "x", easing), keyframe_expr(frames, "y", easing)
        if kx:
            x = f"max(0,min(w-text_w,w*({kx})-text_w/2))"
        if ky:
            y = f"max(0,min(h-text_h,h*({ky})-text_h/2))"
        ko = keyframe_expr(frames, "opacity", easing)
        if ko:
            alpha = ko
        ks = keyframe_expr(frames, "scale", easing)
        if ks:
            layer = {**layer, "font_size": f"{int(layer['font_size'])}*({ks})"}
    expansion = "normal" if layer["type"] in ("timer", "timestamp") else "none"
    if layer.get("animation") == "slide":
        # מחליק פנימה משמאל אל המיקום הסופי במשך ANIMATION_SECONDS
        x = f"if(lt(t,{_fmt(start + ANIMATION_SECONDS)}),-text_w+(({x})+text_w)*(t-{_fmt(start)})/{_fmt(ANIMATION_SECONDS)},{x})"
    if layer.get("animation") == "typewriter" and len(text_files) > 1:
        # כל קידומה מוצגת בחלון-זמן משלה; האחרונה (הטקסט המלא) נשארת עד סוף השכבה
        steps = len(text_files)
        reveal = min(2.0, max(0.5, steps * 0.06))
        step_seconds = reveal / steps
        filters = []
        for n, path in enumerate(text_files):
            step_start = start + n * step_seconds
            step_end: Optional[float] = start + (n + 1) * step_seconds if n < steps - 1 else end
            filters.append(_drawtext(path, layer, _enable_expr(step_start, step_end), x, y, alpha, expansion))
        return filters
    return [_drawtext(text_files[0], layer, _enable_expr(start, end), x, y, alpha, expansion)]


def video_layer_end(layer: Dict[str, Any], clip_duration: Optional[float], output_duration: Optional[float]) -> Optional[float]:
    """גל 26: סוף שכבת וידאו בזמן הפלט - הסוף שנבחר, אחרת עד שהקליפ נגמר (מנקודת ההתחלה
    שלו), ולעולם לא אחרי סוף הפלט. None אם לא נשאר ממנה כלום."""
    start = float(layer.get("start") or 0.0)
    ends = [float(layer["end"])] if layer.get("end") is not None else []
    if clip_duration is not None and clip_duration > 0:
        ends.append(start + max(0.0, clip_duration - float(layer.get("source_in") or 0.0)))
    if output_duration is not None and output_duration > 0:
        ends.append(output_duration)
    if not ends:
        return None
    end = min(ends)
    return end if end - start > 0.04 else None


def build_video_layer_input_args(layer: Dict[str, Any]) -> List[str]:
    """קלט ה--i של שכבת וידאו: קפיצה מהירה לנקודת ההתחלה בקליפ וקריאה רק של האורך הדרוש."""
    duration = float(layer["end"]) - float(layer["start"])
    source_in = float(layer.get("source_in") or 0.0)
    args = ["-ss", _fmt(source_in)] if source_in > 0 else []
    return args + ["-t", _fmt(duration), "-i", str(layer["path"])]


def build_broll_audio_sources(layers: Sequence[Dict[str, Any]], media_inputs: Dict[int, int]) -> List[Dict[str, Any]]:
    """מקורות השמע של שכבות הווידאו (mix/replace) עבור build_edit_filter_complex. שכבה
    בלי פס-קול (has_audio=False) לא נכנסת - [N:a] של קובץ בלי שמע היה מפיל את ffmpeg."""
    sources = []
    for index, layer in enumerate(layers):
        if (layer.get("type") == "video" and layer.get("audio") in ("mix", "replace") and layer.get("has_audio")
                and layer.get("end") is not None and index in media_inputs):
            sources.append({"input": media_inputs[index], "start": float(layer["start"]), "end": float(layer["end"]),
                            "mode": layer["audio"], "volume": float(layer.get("volume", 1.0))})
    return sources


def build_broll_audio_parts(main_label: str, sources: Sequence[Dict[str, Any]], out_label: str = "outa") -> List[str]:
    """מערבב את שמע ה-B-roll מעל השמע הראשי: כל מקור מתחיל בזמן שלו בפלט (adelay), ומצב
    replace משתיק את הראשי באותו טווח. הראשי קובע את האורך (duration=first)."""
    parts: List[str] = []
    main = main_label
    silence = [f"between(t,{_fmt(s['start'])},{_fmt(s['end'])})" for s in sources if s["mode"] == "replace"]
    if silence:
        parts.append(f"[{main}]volume=0:enable='{'+'.join(silence)}'[__amain_duck]")
        main = "__amain_duck"
    labels = [f"[{main}]"]
    for n, source in enumerate(sources, 1):
        delay = int(round(source["start"] * 1000))
        duration = source["end"] - source["start"]
        parts.append(f"[{source['input']}:a]atrim=duration={_fmt(duration)},asetpts=PTS-STARTPTS,"
                     f"adelay={delay}:all=1,volume={_fmt(source['volume'])}[__broll_a{n}]")
        labels.append(f"[__broll_a{n}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:dropout_transition=0:normalize=0[{out_label}]")
    return parts


def build_rounded_frame_source(
    color: str, thickness: int, radius: int, width: int, height: int, fps: Union[int, str, None],
) -> Optional[str]:
    """מקור-filtergraph (בלי תווית-פלט) של מסגרת עם פינות פנימיות מעוגלות: "טבעת" RGBA בגודל
    הפלט שהשקופה בה היא רק חלון הווידאו המעוגל. הטבעת מחושבת ב-geq על פריים אחד בלבד
    (trim + loop שומרים אותו), כך שאין עלות לכל פריים. המרחק לחלון הוא מרחק-מסומן של
    מלבן מעוגל (בפיקסלים), והשקיפות מוחלקת על רוחב פיקסל אחד.

    radius נחתך לחצי הצד הקצר של החלון. מחזיר None כשאין מה לעגל (רדיוס 0, חלון קטן מדי או צבע
    לא תקין) - הקורא חוזר אז ל-drawbox הישר."""
    thickness, radius = int(thickness), int(radius)
    inner_width, inner_height = width - 2 * thickness, height - 2 * thickness
    hex_color = color.lstrip("#")
    if radius <= 0 or thickness <= 0 or inner_width < 2 or inner_height < 2 or not _HEX_COLOR_RE.match(hex_color):
        return None
    radius_value = min(float(radius), inner_width / 2, inner_height / 2)
    red, green, blue = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    half_width, half_height = width / 2, height / 2
    reach_x, reach_y = half_width - thickness - radius_value, half_height - thickness - radius_value
    alpha = (
        f"st(0,abs(X+0.5-{_fmt(half_width)})-{_fmt(reach_x)});st(1,abs(Y+0.5-{_fmt(half_height)})-{_fmt(reach_y)});"
        f"255*clip(hypot(max(ld(0),0),max(ld(1),0))+min(max(ld(0),ld(1)),0)-{_fmt(radius_value)}+0.5,0,1)"
    )
    try:
        fps_value = eval_fps(fps or 30)
    except (TypeError, ValueError, ZeroDivisionError):
        fps_value = 30.0
    return (
        f"color=c=black:s={width}x{height}:r={fps or 30},format=gbrap,geq=r={red}:g={green}:b={blue}:a='{alpha}',"
        f"trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/{_fmt(fps_value)}/TB"
    )


def build_layer_parts(
    in_label: str,
    layers: Sequence[Dict[str, Any]],
    text_files: Dict[int, List[str]],
    image_inputs: Dict[int, int],
    output_width: Optional[int],
    output_fps: Union[int, str, None],
    output_duration: Optional[float],
    progress_bar: Optional[Dict[str, Any]] = None,
    frame_border: Optional[Tuple[str, int]] = None,
    output_height: Optional[int] = None,
    frame_radius: int = 0,
) -> Tuple[List[str], str]:
    """חלקי filtergraph שמרכיבים את כל השכבות על in_label, לפי הסדר (שכבה מאוחרת
    מעל מוקדמת) -> (parts, תווית-הפלט). image_inputs: {index-שכבה: אינדקס -i} (תמונות
    ושכבות וידאו). סרגל-התקדמות ומסגרת תמיד עליונים (אחרונים). frame_radius > 0 מעגל את
    הפינות הפנימיות של המסגרת (דורש גודל פלט ידוע; אחרת המסגרת נשארת ישרה)."""
    parts: List[str] = []
    current = in_label
    chain: List[str] = []
    counter = 0

    def flush() -> None:
        nonlocal current, chain, counter
        if chain:
            counter += 1
            label = f"__lay{counter}"
            parts.append(f"[{current}]{','.join(chain)}[{label}]")
            current, chain = label, []

    for index, layer in enumerate(layers):
        if layer["type"] == "video":
            input_index = image_inputs.get(index)
            if input_index is None or layer.get("end") is None:
                continue
            flush()
            counter += 1
            start, end = float(layer["start"]), float(layer["end"])
            width = int(output_width or 1920)
            height = int(output_height or round(width * 9 / 16 / 2) * 2)
            video_chain = f"[{input_index}:v]trim=duration={_fmt(end - start)},setpts=PTS-STARTPTS+{_fmt(start)}/TB"
            fit = layer.get("fit", "fill")
            if fit == "fill":
                video_chain += f",scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1"
                x, y = "0", "0"
            elif fit == "fit":
                video_chain += f",scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
                x, y = "0", "0"
            else:
                pip_width = max(2, int(round(width * float(layer.get("scale", 0.35)) / 2)) * 2)
                video_chain += f",scale={pip_width}:-2,setsar=1"
                x, y = _overlay_xy(layer.get("position", "top-right"), layer.get("x"), layer.get("y"))
            if output_fps:
                video_chain += f",fps={output_fps}"
            opacity = float(layer.get("opacity", 1.0))
            video_chain += ",format=yuva420p" + (f",colorchannelmixer=aa={opacity:.2f}" if opacity < 1.0 else "")
            parts.append(f"{video_chain}[__vid{counter}]")
            label = f"__lay{counter}"
            parts.append(f"[{current}][__vid{counter}]overlay=x='{x}':y='{y}':eof_action=pass:enable='{_enable_expr(start, end)}'[{label}]")
            current = label
        elif layer["type"] == "image":
            input_index = image_inputs.get(index)
            if input_index is None:
                continue
            flush()
            counter += 1
            width = max(2, int(round((output_width or 1920) * float(layer.get("scale", 0.2)) / 2)) * 2)
            opacity = float(layer.get("opacity", 1.0))
            fade = f",colorchannelmixer=aa={opacity:.2f}" if opacity < 1.0 else ""
            parts.append(f"[{input_index}:v]format=rgba{fade},scale={width}:-2[__img{counter}]")
            x, y = _overlay_xy(layer["position"], layer.get("x"), layer.get("y"))
            frames, easing = layer.get("keyframes") or [], layer.get("easing", "linear")
            kx, ky = keyframe_expr(frames, "x", easing), keyframe_expr(frames, "y", easing)
            if kx:  # גל 14: תמונה עם keyframes - מיקום מונפש (שקיפות/גודל נשארים קבועים לתמונה)
                x = f"max(0,min(W-w,W*({kx})-w/2))"
            if ky:
                y = f"max(0,min(H-h,H*({ky})-h/2))"
            label = f"__lay{counter}"
            parts.append(f"[{current}][__img{counter}]overlay=x='{x}':y='{y}':enable='{_enable_expr(float(layer['start']), layer.get('end'))}'[{label}]")
            current = label
        else:
            chain += build_text_layer_filters(layer, text_files.get(index, []))
    if frame_border and frame_border[1] > 0:
        color, thickness = frame_border
        rounded = (
            build_rounded_frame_source(color, thickness, frame_radius, int(output_width), int(output_height), output_fps)
            if frame_radius > 0 and output_width and output_height else None
        )
        if rounded:
            flush()
            counter += 1
            label = f"__lay{counter}"
            parts.append(f"{rounded}[__fr{counter}]")
            parts.append(f"[{current}][__fr{counter}]overlay=x=0:y=0:shortest=1[{label}]")
            current = label
        else:
            chain.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{color.lstrip('#')}:t={int(thickness)}")
    flush()
    if progress_bar and output_width and output_duration and output_duration > 0:
        height = int(progress_bar.get("height") or 8)
        color = str(progress_bar.get("color") or "#FF0000").lstrip("#")
        y = "0" if progress_bar.get("position") == "top" else "H-h"
        counter += 1
        label = f"__lay{counter}"
        parts.append(f"color=c=0x{color}:s={output_width}x{height}:r={output_fps or 30}[__pb{counter}]")
        parts.append(f"[{current}][__pb{counter}]overlay=x='-w+W*t/{_fmt(output_duration)}':y={y}:shortest=1[{label}]")
        current = label
    return parts, current


# --- items 87-88: watermark נודד, Ken Burns, וינייטה ---

VIGNETTE_ANGLES: Dict[str, str] = {"light": "PI/6", "medium": "PI/5", "strong": "PI/4"}


def build_vignette_filter(level: Optional[str]) -> str:
    if not level or level == "none":
        return ""
    if level not in VIGNETTE_ANGLES:
        raise ValueError(f"עוצמת וינייטה לא מוכרת: {level!r}")
    return f"vignette=angle={VIGNETTE_ANGLES[level]}"


def build_ken_burns_filter(zoom_amount: float, output_width: int, output_height: int, output_fps: Union[int, str], duration: float) -> str:
    """זום-אין איטי לאורך כל הסרטון (Ken Burns) - zoompan עם d=1 (פריים-יוצא לכל
    פריים-נכנס), מ-1.0 עד 1+zoom_amount, ממורכז."""
    if zoom_amount <= 0 or duration <= 0:
        return ""
    try:
        fps_value = float(eval_fps(output_fps))
    except (ValueError, ZeroDivisionError):
        fps_value = 30.0
    frames = max(1, int(round(duration * fps_value)))
    return (f"zoompan=z='1+{_fmt(zoom_amount)}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d=1:s={output_width}x{output_height}:fps={output_fps}")


def eval_fps(value: Union[int, str]) -> float:
    text = str(value)
    if "/" in text:
        num, den = text.split("/", 1)
        return float(num) / float(den)
    return float(text)


def build_cycling_overlay_xy(positions: Sequence[Tuple[int, int]], cycle_seconds: float) -> Tuple[str, str]:
    """ביטויי x/y ל-overlay שעוברים בין המיקומים כל cycle_seconds (watermark נודד)."""
    if len(positions) < 2 or cycle_seconds <= 0:
        x, y = positions[0]
        return str(x), str(y)
    period = cycle_seconds * len(positions)
    phase = f"mod(t,{_fmt(period)})"

    def nested(values: Sequence[int]) -> str:
        expr = str(values[-1])
        for i in range(len(values) - 2, -1, -1):
            expr = f"if(lt({phase},{_fmt(cycle_seconds * (i + 1))}),{values[i]},{expr})"
        return expr
    return nested([p[0] for p in positions]), nested([p[1] for p in positions])
