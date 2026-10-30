# dataviz/web/readability.py
#
# 20.10.2026: בדיקת קריאות לפי יעד (YouTube 16:9 / Shorts 9:16) - מציירים כמה פריימים של הגרף בגודל המלא של היעד
# ובודקים את הטקסטים שבאמת על המסך: טקסט קטן מדי, תוויות שעולות זו על זו, ניגודיות חלשה מול הרקע, ויותר מדי ישויות.
# לכל אזהרה הצעת "תיקון" - הגדרה וערך (video.dpi, ranking.top_n, colors) שהדפדפן שם בטיוטה, לא כאן. לא נכתב כלום.
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from dataviz.targets import TARGETS

# טקסט קריא: לפחות 1.8% מהצלע הקצרה (כ-19px ב-1080) - בטלפון (Shorts) זה כבר קטן
MIN_TEXT_SHARE = 0.018
MAX_ENTITIES = {False: 12, True: 8}   # לרוחב / לאורך
MIN_CONTRAST = 3.0                    # WCAG לטקסט גדול
MIN_ALPHA = 0.35                      # טקסט שקוף יותר (סימן המים של השנה, דהייה) לא נבדק
POSITIONS = (0.3, 0.65, 0.97)         # איפה בחלק הראשי של הסרטון בודקים


def _luminance(rgb: Sequence[float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(float(c)) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Sequence[float], b: Sequence[float]) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_color(rgb: Sequence[float], background: Sequence[float]) -> Tuple[float, float, float]:
    """הצבע הקרוב ביותר (מעורבב לכיוון שחור על רקע בהיר / לבן על כהה) שמגיע לניגודיות המינימלית."""
    target = 0.0 if _luminance(background) > 0.4 else 1.0
    color = (float(rgb[0]), float(rgb[1]), float(rgb[2]))
    for step in range(1, 21):
        t = step / 20
        mixed = (color[0] + (target - color[0]) * t, color[1] + (target - color[1]) * t, color[2] + (target - color[2]) * t)
        if contrast(mixed, background) >= MIN_CONTRAST + 0.2:
            return mixed
    return (target, target, target)


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{int(round(max(0.0, min(1.0, float(c))) * 255)):02x}" for c in rgb[:3])


def _overlap(a: Any, b: Any) -> float:
    """כמה מהתיבה הקטנה מכוסה על ידי השנייה (0-1)."""
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min(a.width * a.height, b.width * b.height) or 1.0
    return w * h / smaller


def _behind(pixels: Any, box: Any) -> Tuple[float, float, float]:
    """הצבע שמאחורי הטקסט: החציון של הפיקסלים במסגרת דקה מסביב לתיבה שלו (שם אין אותיות - רק עמודה, כרטיס או הרקע)."""
    import numpy as np
    height, width = pixels.shape[:2]
    x0, x1 = max(0, int(box.x0) - 2), min(width, int(math.ceil(box.x1)) + 2)
    y0, y1 = max(0, height - int(math.ceil(box.y1)) - 2), min(height, height - int(box.y0) + 2)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return (1.0, 1.0, 1.0)
    ring = np.concatenate([pixels[y0, x0:x1, :3], pixels[y1 - 1, x0:x1, :3], pixels[y0:y1, x0, :3], pixels[y0:y1, x1 - 1, :3]])
    median = np.median(ring, axis=0) / 255.0
    return (float(median[0]), float(median[1]), float(median[2]))


def _texts(fig: Any) -> List[Any]:
    from matplotlib.text import Text
    found = []
    for text in fig.findobj(Text):
        alpha = text.get_alpha()
        if text.get_visible() and str(text.get_text()).strip() and (alpha is None or alpha >= MIN_ALPHA):
            found.append(text)
    return found


def check(folder: str, overrides: Mapping[str, Any], target: str = "youtube") -> Dict[str, Any]:
    """{target, label, size, frames, warnings: [{kind, message, examples, fix: {path, value, label} | None}]}."""
    import os

    from dataviz.config import load_config
    from dataviz.episode import build_episode
    from dataviz.plan import build_plan
    from dataviz.targets import apply_target
    from dataviz.web.preview import _lock
    if target not in TARGETS:
        raise ValueError(f"יעד לא מוכר: {target!r}")
    config = apply_target(load_config(os.path.join(folder, "config.yaml"), dict(overrides)), target)
    vertical = bool(TARGETS[target]["vertical"])
    episode = build_episode(config)
    plan = build_plan(episode, "full")
    main = [i for i, f in enumerate(plan) if f.get("k") == "main"]
    cfg = episode.config
    video = cfg["video"]
    width, height, dpi = int(video["width"]), int(video["height"]), float(video["dpi"])
    min_px = MIN_TEXT_SHARE * min(width, height)
    small: Dict[str, float] = {}
    overlaps: List[str] = []
    weak: Dict[str, Tuple[str, Tuple[float, float, float], Tuple[float, float, float]]] = {}   # טקסט -> (צבע, rgb, רקע)
    palette: Dict[str, str] = {}
    theme_colors: Dict[str, str] = {}
    with _lock:   # matplotlib (ולא רק pyplot) רק בתוך המנעול של התצוגה
        import matplotlib.colors as mcolors
        import matplotlib.pyplot as plt

        from dataviz.charts import make_chart
        from dataviz.render import chart_context
        chart = make_chart(chart_context(episode))
        try:
            from dataclasses import fields
            theme_colors = {f.name: _hex(mcolors.to_rgb(getattr(chart.theme, f.name))) for f in fields(chart.theme)
                            if f.name in ("ink", "muted", "accent", "on_accent", "on_light")}
            palette = {str(e): _hex(mcolors.to_rgb(chart.color(e))) for e in episode.entities}
            for position in POSITIONS:
                if not main:
                    break
                chart.render(plan[main[min(len(main) - 1, int(position * (len(main) - 1)))]])
                chart.fig.canvas.draw()
                renderer = chart.fig.canvas.get_renderer()
                import numpy as np
                pixels = np.asarray(chart.fig.canvas.buffer_rgba())
                texts = _texts(chart.fig)
                boxes = []
                for text in texts:
                    box = text.get_window_extent(renderer)
                    if box.x1 <= 0 or box.y1 <= 0 or box.x0 >= width or box.y0 >= height:
                        continue   # מחוץ לפריים (תווית ציר שנחתכת) - לא על המסך
                    label = " ".join(str(text.get_text()).split())[:40]
                    px = float(text.get_fontsize()) * dpi / 72
                    if px < min_px:
                        small[label] = min(px, small.get(label, px))
                    rgb = mcolors.to_rgb(text.get_color())
                    behind = _behind(pixels, box)
                    if contrast(rgb, behind) < MIN_CONTRAST:
                        weak.setdefault(label, (_hex(rgb), rgb, behind))
                    boxes.append((label, box))
                for i, (label_a, a) in enumerate(boxes):
                    for label_b, b in boxes[i + 1:]:
                        if label_a != label_b and _overlap(a, b) > 0.3:
                            pair = f"{label_a} / {label_b}"
                            if pair not in overlaps:
                                overlaps.append(pair)
        finally:
            plt.close(chart.fig)
    warnings: List[Dict[str, Any]] = []
    if small:
        smallest = min(small.values())
        base_dpi = min(400, int(math.ceil(float(load_config(os.path.join(folder, "config.yaml"), dict(overrides))["video"]["dpi"]) * min_px / max(smallest, 1.0))))
        warnings.append({"kind": "small", "message": f"{len(small)} טקסטים קטנים מ-{min_px:.0f}px (הקטן: {smallest:.0f}px)",
                         "examples": sorted(small, key=lambda k: small[k])[:6],
                         "fix": {"path": "video.dpi", "value": base_dpi, "label": f"להגדיל את כל הטקסט (רזולוציית טקסט {base_dpi})"}})
    if overlaps:
        top_n = int(cfg["ranking"]["top_n"])
        warnings.append({"kind": "overlap", "message": f"{len(overlaps)} זוגות תוויות עולים זה על זה",
                         "examples": overlaps[:6],
                         "fix": {"path": "ranking.top_n", "value": top_n - 1, "label": f"פחות ישויות על המסך ({top_n - 1})"} if top_n > 3 else None})   # top_n מינימום 3
    if weak:
        colors = dict(cfg.get("colors") or {})
        fixed = dict(colors)
        fix: Optional[Dict[str, Any]] = None
        for _label, (hex_color, rgb, behind) in weak.items():
            field = next((name for name, color in theme_colors.items() if color == hex_color), None)
            if field and fix is None:   # צבע טקסט של ערכת העיצוב (למשל "מוביל" על העמודה) - דריסה של הצבע הזה
                fix = {"path": f"theme_overrides.{field}", "value": _hex(readable_color(rgb, behind)),
                       "label": f"צבע טקסט בולט יותר ({field})"}
            for entity, color in palette.items():
                if color == hex_color:
                    fixed[str(entity)] = _hex(readable_color(rgb, behind))
        if fix is None and fixed != colors:
            fix = {"path": "colors", "value": fixed, "label": "צבעים כהים / בהירים יותר לישויות האלה"}
        warnings.append({"kind": "contrast", "message": f"{len(weak)} טקסטים בניגודיות חלשה מול הרקע (פחות מ-{MIN_CONTRAST:g}:1)",
                         "examples": list(weak)[:6],
                         "fix": fix})
    shown = min(int(cfg["ranking"]["top_n"]), len(episode.entities))
    if shown > MAX_ENTITIES[vertical]:
        limit = MAX_ENTITIES[vertical]
        warnings.append({"kind": "crowded", "message": f"{shown} ישויות על המסך - ב{TARGETS[target]['label']} עד {limit} נקראות טוב",
                         "examples": [], "fix": {"path": "ranking.top_n", "value": limit, "label": f"להציג {limit}"}})
    return {"target": target, "label": TARGETS[target]["label"], "size": [width, height], "frames": min(len(main), len(POSITIONS)),
            "min_px": round(min_px), "warnings": warnings}


def targets() -> List[Dict[str, Any]]:
    return [{"id": key, "label": value["label"], "vertical": value["vertical"]} for key, value in TARGETS.items()]
