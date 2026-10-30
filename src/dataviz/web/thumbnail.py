# dataviz/web/thumbnail.py (עד 19.10.2026: utils/dataviz_thumbnail.py)
#
# סבב הייצוב (16.10.2026): הכותרת על התמונה הממוזערת של סרטוני הנתונים. utils/thumbnail_generator מצייר אותה
# ב-Pillow, ובלי libraqm (כך ב-Windows) כותרת בעברית יצאה עם האותיות בסדר הפוך, וכותרת ארוכה נחתכה בשני הצדדים.
# כאן הכותרת מצוירת ב-matplotlib - 3.11 מסדר טקסט מימין לשמאל בעצמו, כמו הטקסט בתוך הסרטון - ומוקטנת או נשברת
# לשתי שורות עד שהיא נכנסת ברוחב. בחירת הפריים (התנועה הכי גדולה) נשארת של thumbnail_generator.
import os
import tempfile
from typing import List, Optional, Tuple

FONTS = ("Segoe UI", "Arial", "Tahoma", "DejaVu Sans")   # כמו בערכות של המנוע (dataviz/themes)
BAND = 0.22        # גובה הרצועה הכהה מגובה התמונה (כמו ב-thumbnail_generator); גדלה כשהכותרת בשתי שורות
MARGIN = 0.04      # שוליים מכל צד, מרוחב התמונה
DPI = 100


def _two_lines(text: str) -> Optional[List[str]]:
    """שבירה לשתי שורות במקום שבו הן הכי שוות באורך - או None למילה אחת."""
    words = text.split()
    if len(words) < 2:
        return None
    cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:cut]), " ".join(words[cut:])]


def _measure(fig, renderer, lines: List[str], size_pt: float) -> Tuple[float, float]:
    text = fig.text(0.5, 0.5, "\n".join(lines), fontsize=size_pt, fontweight="bold", family=list(FONTS),
                    ha="center", va="center", linespacing=1.15)
    box = text.get_window_extent(renderer)
    text.remove()
    return box.width, box.height


def _layout(fig, renderer, text: str, width: int, height: int) -> Tuple[List[str], float]:
    """(שורות, גודל בנקודות): שורה אחת כשהיא נכנסת בלי להקטין יותר מדי, אחרת שתי שורות; ובכל מקרה עד שזה נכנס."""
    base = max(36, width // 14) * 72 / DPI
    max_w, max_h = width * (1 - 2 * MARGIN), height * 0.4

    def fit(lines: List[str]) -> float:
        size = base
        while size > base * 0.35:
            w, h = _measure(fig, renderer, lines, size)
            if w <= max_w and h <= max_h:
                return size
            size *= 0.92
        return size

    one = [text]
    one_size = fit(one)
    two = _two_lines(text)
    if two is None or one_size >= base * 0.75:
        return one, one_size
    two_size = fit(two)
    return (two, two_size) if two_size > one_size else (one, one_size)


def draw_title(image_path: str, text: str, out_path: str) -> str:
    """כותרת לבנה עם קו מתאר על רצועה כהה בתחתית התמונה - אותה חתימה כמו thumbnail_generator._draw_title_text."""
    import numpy as np
    from matplotlib import patheffects
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Rectangle
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    fig = Figure(figsize=(width / DPI, height / DPI), dpi=DPI)
    canvas = FigureCanvasAgg(fig)
    renderer = canvas.get_renderer()
    lines, size = _layout(fig, renderer, " ".join(str(text).split()), width, height)
    _, text_h = _measure(fig, renderer, lines, size)
    band = min(height * 0.5, max(height * BAND, text_h + height * 0.06))

    ax = fig.add_axes((0, 0, 1, 1))
    ax.imshow(np.asarray(image), extent=(0, width, 0, height), interpolation="none")
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), width, band, color="black", alpha=160 / 255, linewidth=0))
    stroke = max(2.0, size / 9)
    ax.text(width / 2, band / 2, "\n".join(lines), fontsize=size, fontweight="bold", family=list(FONTS), color="white",
            ha="center", va="center", linespacing=1.15, path_effects=[patheffects.withStroke(linewidth=stroke, foreground="black")])
    canvas.draw()
    result = Image.fromarray(np.asarray(canvas.buffer_rgba())[..., :3])
    if result.size != (width, height):
        result = result.resize((width, height))
    result.save(out_path, quality=92)
    return out_path


def make_thumbnail(video_path: str, out_path: str, ffmpeg_exe: str = "ffmpeg", ffprobe_exe: str = "ffprobe",
                   title_text: Optional[str] = None) -> str:
    """כמו thumbnail_generator.generate_thumbnail (אותם פריימים מועמדים ואותה בחירה), עם הכותרת של draw_title."""
    from utils import thumbnail_generator as tg
    duration = tg.get_video_duration_via_ffprobe(video_path, ffprobe_exe)
    with tempfile.TemporaryDirectory() as tmp:
        frames = []
        for i, pct in enumerate(tg.CANDIDATE_TIMESTAMPS_PCT):
            frame = os.path.join(tmp, f"cand_{i}.jpg")
            if tg.extract_frame_at_timestamp(video_path, max(0.1, duration * pct), frame, ffmpeg_exe):
                frames.append(frame)
        if not frames:
            raise RuntimeError("לא הצליח לחלץ אף פריים מועמד מהסרטון")
        best = tg._motion_score(frames) if len(frames) > 1 else 0
        draw_title(frames[best], title_text or os.path.splitext(os.path.basename(video_path))[0], out_path)
    return out_path
