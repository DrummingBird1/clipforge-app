# dataviz/charts/bar_race.py
#
# Bar chart race: עמודות אופקיות לפי הדירוג המוחלק של התכנית (pos שבור = מעבר הדרגתי
# בין מקומות, ועמודה שנכנסת/יוצאת נעלמת בהדרגה מתחת למקום האחרון). כל עמודה עם פינות
# מעוגלות בצד ימין, הצללה עדינה לאורכה, ומרקם פסים לישויות שהנתונים שלהן ברמת דיוק אחרת.

import math
from typing import Any, List, Mapping, Tuple

import numpy as np
from matplotlib.colors import to_rgb
from matplotlib.patches import Polygon
from matplotlib.ticker import FuncFormatter, MaxNLocator

from dataviz.charts.base import TEXT_EDGE, BaseChart, NumberTicks


def rounded_bar(x0: float, x1: float, yc: float, h: float, rx: float, ry: float, n: int = 8) -> List[Tuple[float, float]]:
    """מלבן עם פינות מעוגלות בצד ימין (בקואורדינטות נתונים, רדיוס אליפטי כך שייראה עגול בפיקסלים)."""
    rx = min(rx, x1 - x0)
    th = np.linspace(-np.pi / 2, 0, n)
    top = [(x1 - rx + rx * np.cos(t), yc - h / 2 + ry + ry * np.sin(t)) for t in th]
    bot = [(x1 - rx + rx * np.cos(t), yc + h / 2 - ry + ry * np.sin(t)) for t in -th[::-1]]
    return [(x0, yc - h / 2)] + top + bot + [(x0, yc + h / 2)]


def blend(rgb: Tuple[float, ...], k: float) -> Tuple[float, ...]:
    """k=0 -> הצבע עצמו, k=1 -> לבן."""
    return tuple(c * (1 - k) + k for c in rgb)


def is_dark(rgb: Tuple[float, ...]) -> bool:
    r, g, b = rgb[:3]
    return (0.299 * r + 0.587 * g + 0.114 * b) < 0.55


class BarRace(BaseChart):
    name = "bar_race"
    # 25.10.2026: כשכל העמודות ארוכות התיבה בימין כיסתה את המספרים בקצה שלהן - למטה, ואז שמאלה על גוף העמודות
    OUTRO_SPOTS_FREE_OF_TEXT = ((0.985, 0.08, "right", "bottom"), (0.70, 0.30, "right", "center"), (0.50, 0.30, "center", "center"),
                                (0.35, 0.30, "center", "center"))

    def setup_data_axes(self) -> None:
        ax, th = self.ax, self.theme
        ax.set_facecolor(th.bg)
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        if self.log:   # גל 49: הציר מצויר במרחב log10 (העמודות, ההצללה והפינות נשארים כמו שהם) - התוויות בערכים
            ax.xaxis.set_major_locator(MaxNLocator(integer=True))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: self.fmt(10 ** v)))
        else:
            ax.xaxis.set_major_formatter(NumberTicks(self.numbers))   # ב18: שנתות compact בלי כפולות
            self.whole_ticks(ax.xaxis)
        ax.tick_params(axis="x", labelsize=10, colors=th.muted, length=0)
        if self.style["grid"]:   # גל 51: מראה "מינימלי" בלי רשת
            ax.grid(axis="x", color=th.grid, linewidth=0.9)
        ax.set_axisbelow(True)

    def bx(self, value: float) -> float:
        """מיקום על הציר: הערך עצמו, או log10 שלו בציר לוגריתמי (ערך 1 ומטה = תחילת הציר)."""
        return math.log10(max(value, 1.0)) if self.log else value

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        value_max = frame["xmax"]
        # בציר לוגריתמי המרווח לתווית נמדד ב-log10 (אחרת 13% של המוביל הם 2% מהציר והתווית נחתכת)
        xmax = max(self.bx(value_max) * 1.15, 1.0) if self.log else value_max
        # 25.10.2026: ערכים שליליים (מאזן, שינוי) - הציר נפתח שמאלה מ-0 והעמודה נמשכת שמאלה. עד עכשיו הציר התחיל
        # תמיד ב-0, העמודה השלילית לא צוירה בכלל ונשארו רק שם ומספר. בלי ערך שלילי xmin = 0 - אותו פריים בדיוק
        lowest = min([v for e, v, p in frame["bars"] if top_n - p > 0.01] or [0.0])
        xmin = lowest * 1.15 if lowest < 0 and not self.log else 0.0
        span = xmax - xmin
        gains = frame.get("gains") or {}
        ylim = (top_n - 0.45, -0.85)
        bb = ax.get_window_extent()
        rx = 6.0 * span / bb.width                       # רדיוס פינה של 6 פיקסלים
        ry = 6.0 * abs(ylim[0] - ylim[1]) / bb.height
        height = float(self.style["bar_height"])          # גל 51: עובי העמודה (ברירת מחדל 0.7 כמו בסרטון הראשון)
        bar_px = height * bb.height / abs(ylim[0] - ylim[1])
        cur = frame.get("current")
        leader_label = self.ctx["labels"].get("leader")
        zero = self.fmt(0)
        names: List[Tuple[Any, bool]] = []
        for e, v, p in frame["bars"]:
            al = min(1.0, max(0.0, top_n - p)) * self.focus(e, frame)   # 20.10.2026: מצב פוקוס
            if al <= 0.01:
                continue
            is_cur = highlight_current and e == cur
            base = to_rgb(th.accent if is_cur else self.color(e))
            end = self.bx(v)
            if (v > 0 and end > 0) or end < 0:   # ג5: גם ערך קטן (לנפש, אחוזים) - עד 23.10.2026 רק מעל 0.5
                if end < 0:   # שלילי: אותה עמודה במראה, הפינות המעוגלות בצד שמאל
                    pts = [(-x, y) for x, y in rounded_bar(0, -end, p, height, rx, ry)]
                else:
                    pts = rounded_bar(0, end, p, height, rx, ry)
                shade = np.array([blend(base, 0.16 * (1 - i / 15)) for i in range(16)])[:, None, :]
                im = self.dyn(ax.imshow(shade, extent=(min(0, end), max(0, end), p + height / 2, p - height / 2), aspect="auto",
                                        zorder=3, alpha=al, interpolation="bilinear"))
                im.set_clip_path(Polygon(pts, closed=True, transform=ax.transData))
                self.hit(im, f"entity:{e}")   # 27.10.2026: לחיצה על העמודה בתצוגה - הצבע של הישות
                if self.is_striped(e):
                    self.dyn(ax.add_patch(Polygon(pts, closed=True, facecolor="none",
                                                  edgecolor=(*th.hatch_rgb, th.hatch_alpha * al), hatch="////",
                                                  linewidth=0, zorder=3.5)))
            names.append((self.hit(self.dyn(ax.text(xmin - span * 0.012, p, str(e), ha="right", va="center", fontsize=12.5, color=th.ink, alpha=al,
                                                    fontweight="bold" if is_cur else "normal", clip_on=False)), f"entity:{e}"), is_cur))
            end = max(end, 0.0)   # ערך שלילי - התווית בתחילת הציר
            # גל 51: התמונה של הישות מיד אחרי קצה העמודה, ותווית הערך אחריה
            image_px = self.draw_image(e, (end + span * 0.006, p), bar_px * 0.95, align=(0, 0.5), alpha=al)
            label_x = end + span * 0.01 + (image_px + 4) * span / bb.width if image_px else end + span * 0.01
            value_text = self.fmt(v)
            if value_text != zero:   # ג5: כל ערך שלא יוצא 0 (גם שלילי) - עד 23.10.2026 רק מ-1
                self.dyn(ax.text(label_x, p, value_text, ha="left", va="center", fontsize=11, color=th.ink, alpha=al))
                self._draw_extras(e, label_x, p, value_text, gains.get(e), frame, al)
            if leader_label and e == frame.get("leader") and p < 0.4 and end > xmax * 0.22:
                self.dyn(ax.text(end - xmax * 0.012, p, leader_label, ha="right", va="center", fontsize=10.5,
                                 color=th.on_accent if is_dark(base) else th.on_light, fontweight="bold", zorder=4))
        ax.set_xlim(xmin, xmax)                           # imshow משנה גבולות - מחזירים
        ax.set_ylim(*ylim)
        for name, bold in names:   # ב16: שם ארוך נשבר לשורות בתוך הפריים (המקום שלו בפיקסלים קבוע - נמדד פעם אחת)
            self.fit_text(name, lo=self.fig.bbox.width * TEXT_EDGE, key=("bar_name", name.get_text(), bold))

    def _draw_extras(self, entity: Any, x: float, y: float, value_text: str, gain: Any, frame: Mapping[str, Any], al: float) -> None:
        """גל 49: אחרי תווית הערך - "+N" (קפיצה של היום שמונפש עכשיו) וחץ דירוג. המיקום בנקודות מסוף התווית
        (רוחב משוער לפי מספר התווים, כמו התוויות בתרשים הפיזור)."""
        offset = len(value_text) * 11 * 0.62 + 8
        if gain:
            text = "+" + self.fmt(gain)
            self.dyn(self.ax.annotate(text, (x, y), xytext=(offset, 0), textcoords="offset points", ha="left", va="center",
                                      fontsize=10, fontweight="bold", color=self.theme.accent, alpha=al, annotation_clip=False))
            offset += len(text) * 10 * 0.62 + 8
        arrow, color = self.move_text(entity, frame)
        if arrow:
            self.dyn(self.ax.annotate(arrow, (x, y), xytext=(offset, 0), textcoords="offset points", ha="left", va="center",
                                      fontsize=10, fontweight="bold", color=color, alpha=al, annotation_clip=False))

    def callout_anchor(self, entity: Any, frame: Mapping[str, Any]) -> Any:
        """גל 50: הערה לישות מצביעה מקצה העמודה שלה - למטה מהעמודות העליונות, למעלה מהשאר."""
        for e, v, p in frame["bars"]:
            if e == entity and p < self.top_n - 0.5:
                return (self.bx(v), p), (28, -30 if p < 1.5 else 30), "left"
        return None
