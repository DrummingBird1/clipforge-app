# dataviz/share.py
#
# גל 42: "תמונה ו-GIF לשיתוף" (מצב share) - הרגע החזק בסרטון הוא היום עם התוספת הגדולה ביותר
# (הקפיצה שכולם זוכרים). ממנו נוצרים share.png (פריים אחד ברזולוציה מלאה) ו-share.gif קצר סביבו
# (ברזולוציה מוקטנת, share.gif_fps פריימים בשנייה) בתיקייה <שם>_share - בלי ffmpeg ובלי לרנדר סרטון.

import dataclasses
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from dataviz.render import ProgressFn, chart_context

SHARE_PNG = "share.png"
SHARE_GIF = "share.gif"


def strongest_day(episode: Any) -> int:
    """היום (אינדקס) עם התוספת הכוללת הגדולה ביותר."""
    totals = episode.daily.sum(axis=1)
    return int(totals.argmax()) if len(totals) else 0


def strongest_frame(plan: Sequence[Mapping[str, Any]], day: int) -> int:
    """הפריים האחרון של הקטע הראשי שעדיין מראה את היום הזה (העמודות כבר גדלו), או הקרוב אליו."""
    best, best_gap = -1, None
    for index, frame in enumerate(plan):
        if frame.get("k") != "main" or "hold" in frame or "teaser" in frame:   # גל 50: לא פריים קפוא ולא הטיזר
            continue
        x = float(frame["x"])
        if int(x) == day:
            best, best_gap = index, 0.0
        elif best_gap != 0.0:
            gap = abs(x - day)
            if best_gap is None or gap < best_gap:
                best, best_gap = index, gap
    if best < 0:
        return max(0, len(plan) - 1)
    return best


def gif_indices(plan_len: int, center: int, *, video_fps: float, seconds: float, gif_fps: float) -> List[int]:
    """הפריימים של ה-GIF: seconds שניות שמסתיימות קצת אחרי הרגע (שני שליש לפני, שליש אחרי), בקצב gif_fps."""
    count = max(2, int(round(seconds * gif_fps)))
    step = max(1.0, float(video_fps) / float(gif_fps))
    first = center - step * count * 2 / 3
    indices = [int(round(first + step * k)) for k in range(count)]
    lo, hi = min(indices), max(indices)
    if lo < 0:
        indices = [i - lo for i in indices]
    if hi >= plan_len:
        indices = [i - (hi - plan_len + 1) for i in indices]
    return sorted({min(max(i, 0), plan_len - 1) for i in indices})


def render_share(episode: Any, plan: Sequence[Mapping[str, Any]], out_dir: str, *, chart: Optional[str] = None,
                 progress: Optional[ProgressFn] = None) -> Dict[str, Any]:
    """share.png + share.gif בתיקייה out_dir. מחזיר {png, gif, frame, day}."""
    from PIL import Image

    from dataviz.charts import make_chart
    from dataviz.config import preview_config

    os.makedirs(out_dir, exist_ok=True)
    config = episode.config
    settings = config.get("share") or {}
    day = strongest_day(episode)
    center = strongest_frame(plan, day)
    indices = gif_indices(len(plan), center, video_fps=float(config["video"]["fps"]), seconds=float(settings.get("gif_seconds", 3)),
                          gif_fps=float(settings.get("gif_fps", 12)))
    total = len(indices) + 1
    png_path = os.path.join(out_dir, SHARE_PNG)
    full = make_chart(chart_context(episode, chart))
    try:
        full.render(plan[center])
        full.save_png(png_path)
    finally:
        full.close()
    if progress:
        progress(1, total)

    small_episode = dataclasses.replace(episode, config=preview_config(config, float(settings.get("gif_scale", 0.5))))
    small = make_chart(chart_context(small_episode, chart))
    images = []
    try:
        width, height = small.size
        for n, index in enumerate(indices, start=2):
            rgba = small.render(plan[index])
            images.append(Image.frombytes("RGBA", (width, height), rgba).convert("RGB").quantize(colors=128))
            if progress:
                progress(n, total)
    finally:
        small.close()
    gif_path = os.path.join(out_dir, SHARE_GIF)
    duration_ms = int(round(1000 / float(settings.get("gif_fps", 12))))
    images[0].save(gif_path, save_all=True, append_images=images[1:], duration=duration_ms, loop=0, optimize=True)
    return {"png": png_path, "gif": gif_path, "frame": center, "day": day, "frames": len(images)}
