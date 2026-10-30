# dataviz/charts/small_multiples.py
#
# 20.10.2026: "גרפים קטנים" (small multiples) - רשת של גרפי קו קטנים, אחד לכל ישות, כל אחד עם ציר y משלו (סביב
# הערכים שלו לאורך כל הפרק, כמו ברמות) וציר זמן משותף שגדל עם הסרטון. לסדרות ביחידות שונות (טמפרטורה ומפלס) - כל
# אחת נראית במלואה, בלי שאחת תמעך את השנייה. אותה תכנית כמו בשאר התרשימים; הדירוג לא משנה כאן את הסדר (קבוע).

import math
from typing import Any, List, Mapping, Tuple

import numpy as np
from matplotlib.ticker import FixedLocator, FuncFormatter, MaxNLocator

from dataviz.charts.base import format_number
from dataviz.charts.line_race import LevelTicks, LineRace

MAX_PANELS = 12
GAP_X, GAP_Y = 0.035, 0.07     # רווח בין הגרפים (חלק מהשטח)


class SmallMultiples(LineRace):
    name = "small_multiples"
    ANNOTATES = False   # הערה על הגרף (תאריך + ערך) - לא כאן: לכל גרף קטן ציר y משלו
    CARD_AT = (0.5, 0.99, "center", "top")
    TOAST_AT = (0.5, 0.86, "center", "top")
    OUTRO_AT = (0.5, 0.5, "center", "center")

    def setup_data_axes(self) -> None:
        super(LineRace, self).setup_data_axes()   # ההיסטוריה ותוויות השנים (TimeSeriesChart), בלי הציר הכפול של LineRace
        self.ax.set_axis_off()
        self.ax.set_zorder(10)               # כרטיסים, התראות ותיבת הסיום (על הציר הראשי) מעל הגרפים הקטנים
        self.ax.patch.set_visible(False)
        th = self.theme
        entities = list(self.ctx["entities"])[:MAX_PANELS]
        n = max(1, len(entities))
        wide = self.ctx["width"] >= self.ctx["height"]
        cols = max(1, min(n, math.ceil(math.sqrt(n * (1.6 if wide else 0.6)))))
        rows = math.ceil(n / cols)
        box = self.ax.get_position()
        w = (box.width - GAP_X * box.width * (cols - 1)) / cols
        h = (box.height - GAP_Y * box.height * (rows - 1)) / rows
        self._panels: List[Tuple[Any, int, Any]] = []
        for k, e in enumerate(entities):
            r, c = divmod(k, cols)
            c = cols - 1 - c if not self.ctx.get("ltr") else c    # בעברית - מימין לשמאל, כמו קריאה
            left = box.x0 + c * (w + GAP_X * box.width)
            bottom = box.y1 - (r + 1) * h - r * GAP_Y * box.height
            ax = self.fig.add_axes((left, bottom, w, h))
            ax.set_facecolor(th.bg)
            for side, spine in ax.spines.items():
                spine.set_visible(side == "bottom")
            ax.spines["bottom"].set_color(th.grid)
            ax.tick_params(axis="both", labelsize=8, colors=th.muted, length=0)
            if self.style["grid"]:
                ax.grid(axis="y", color=th.grid, linewidth=0.8)
            ax.set_axisbelow(True)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
            ax.yaxis.set_major_formatter(LevelTicks(self.fmt, lambda v: format_number(v, {**(self.numbers or {}), "decimals": 0})))
            ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: self._tick_labels.get(int(round(v)), "")))
            if r < rows - 1 and k + cols < n:
                ax.tick_params(axis="x", labelbottom=False)     # שנים רק בשורה התחתונה
            col = self._index[e]
            ax.set_ylim(*self._panel_range(col, ax))
            ax.set_title(str(e), loc="right" if not self.ctx.get("ltr") else "left", fontsize=10.5, color=th.ink, pad=3)
            self._panels.append((ax, col, e))

    def _panel_range(self, col: int, ax: Any) -> Tuple[float, float]:
        """הטווח של גרף אחד: מהשנתה שמתחת לערך הנמוך של הישות בכל הפרק עד זו שמעל הגבוה (עם מרווח קטן), כך שהוא לא זז."""
        values = self._cum[self._start[col]:, col] if self._start[col] < len(self._cum) else np.zeros(1)
        lo, hi = float(values.min()), float(values.max())
        pad = max((hi - lo) * 0.08, abs(hi) * 0.01, 1e-6)
        lo, hi = (0.0 if 0 <= lo < pad else lo - pad), hi + pad
        ticks = ax.yaxis.get_major_locator().tick_values(lo, hi)
        return float(max([t for t in ticks if t <= lo + 1e-9] or [lo])), float(min([t for t in ticks if t >= hi - 1e-9] or [hi]))

    def set_data_visible(self, visible: bool) -> None:
        for ax, _col, _e in self._panels:
            ax.set_visible(visible)

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        th = self.theme
        x = float(frame["x"])
        right = self.set_time_axis(x)       # גם הציר הראשי (המוסתר) - לתקופות ולהערות
        self.ax.set_axis_off()              # render() מדליק אותו בכל פריים
        visible_ticks = [i for i, _ in self._year_ticks if i <= right]
        ticks = visible_ticks[::max(1, math.ceil(len(visible_ticks) / 4))]
        values = {e: v for e, v, _p in frame["bars"]}
        for ax, col, e in self._panels:
            ax.set_xlim(0, right * 1.06)
            ax.xaxis.set_major_locator(FixedLocator(ticks))
            if self._start[col] > x:
                continue
            xs, ys = self.history(col, x, self._start[col])
            v = float(values.get(e, ys[-1]))
            ys[-1] = v
            color = self.color(e)
            self.dyn(ax.plot(xs, ys, color=color, linewidth=2.0, linestyle=(0, (3, 2)) if self.is_striped(e) else "-",
                             solid_capstyle="round", zorder=3)[0])
            self.dyn(ax.scatter([x], [v], s=18, color=color, zorder=4))
            self.dyn(ax.text(0.02 if not self.ctx.get("ltr") else 0.98, 0.96, self.fmt(v), transform=ax.transAxes,
                             ha="left" if not self.ctx.get("ltr") else "right", va="top", fontsize=11, fontweight="bold", color=color))
            for start, end, _label, pcolor in self.ctx.get("periods") or []:
                if start <= x:
                    self.dyn(ax.axvspan(start, max(min(end, x), start + 0.5), color=pcolor or th.accent, alpha=0.12, linewidth=0, zorder=1))

    def draw_periods(self, x: float) -> None:
        """התקופות מוצללות בתוך כל גרף קטן (draw_data), לא על הציר הראשי המוסתר."""

    def draw_outro_box(self, frame: Mapping[str, Any]) -> None:
        super(LineRace, self).draw_outro_box(frame)   # במרכז הרשת (OUTRO_AT), בלי החיפוש של LineRace

    def callout_anchor(self, entity: Any, frame: Mapping[str, Any]) -> Any:
        return None   # הערה לישות - בפינה (לכל גרף ציר משלו)
