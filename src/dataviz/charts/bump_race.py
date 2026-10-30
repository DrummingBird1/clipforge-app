# dataviz/charts/bump_race.py
#
# Bump chart: ציר Y הוא *הדירוג* (1 למעלה), לא הערך. כל ישות היא קו שמראה איך המקום שלה השתנה לאורך הזמן, וראש הקו
# נע בצורה חלקה על ה-pos של התוכנית (אותה אנימציית עקיפות כמו ה-bar race). דירוג היסטורי מחושב פעם אחת מהמטריצה
# המצטברת (cum) ומוחלק קלות כדי שהקווים לא יקפצו מיום ליום.

import math
from typing import Any, List, Mapping

import numpy as np
from matplotlib.ticker import FixedLocator, FuncFormatter

from dataviz.charts.base import round_half_up
from dataviz.charts.timeseries import MAX_POINTS, TimeSeriesChart
from dataviz.plan import rank_matrix as plan_rank_matrix

SMOOTH_DAYS = 15


def rank_matrix(cum: Any, start_idx: List[int], smooth: int = SMOOTH_DAYS) -> Any:
    """[ימים x ישויות] דירוג (1 = הגבוה ביותר) בין הישויות שכבר התחילו; NaN לפני ההתחלה. מוחלק בממוצע נע.
    החישוב עצמו ב-plan.py (גל 49: גם חיצי הדירוג משתמשים בו)."""
    return plan_rank_matrix(cum, start_idx, smooth)


class BumpRace(TimeSeriesChart):
    name = "bump_race"

    def setup_data_axes(self) -> None:
        super().setup_data_axes()
        ax = self.ax
        ax.yaxis.set_major_locator(FixedLocator(list(range(1, self.top_n + 1))))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: str(int(round_half_up(v)))))
        ax.set_ylim(self.top_n + 0.5, 0.5)
        ax.spines["bottom"].set_visible(False)
        self._ranks = rank_matrix(self.ctx["cum"], list(self.ctx["start_idx"]))

    def legend_swatch(self, x_sw: float, color: Any, striped: bool, hatch_edge: Any) -> Any:
        (line,) = self.ax.plot([x_sw - 0.02, x_sw], [1.052, 1.052], transform=self.ax.transAxes, clip_on=False,
                               color=color, linewidth=2.6, linestyle=(0, (3, 2)) if striped else "-", solid_capstyle="round")
        return line

    def rank_history(self, col: int, x: float, head: float) -> tuple:
        i0 = int(math.floor(x))
        idx = np.arange(min(self._start[col], i0), i0 + 1)
        idx = idx[::max(1, math.ceil(len(idx) / MAX_POINTS))]
        ys = self._ranks[idx, col]
        return np.append(idx, x), np.append(ys, head)

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        x = float(frame["x"])
        right = self.set_time_axis(x)
        cur = frame.get("current")
        for e, _, p in frame["bars"]:
            al = min(1.0, max(0.0, top_n - p)) * self.focus(e, frame)   # 20.10.2026: מצב פוקוס
            if al <= 0.01:
                continue
            col = self._index[e]
            head = float(p) + 1.0
            xs, ys = self.rank_history(col, x, head)
            is_cur = highlight_current and e == cur
            color = th.accent if is_cur else self.color(e)
            self.dyn(ax.plot(xs, ys, color=color, alpha=al, linewidth=3.4 if is_cur else 2.4,
                             linestyle=(0, (3, 2)) if self.is_striped(e) else "-", solid_capstyle="round",
                             zorder=4 if is_cur else 3)[0])
            if not self.draw_image(e, (x, head), 28, align=(0.5, 0.5), alpha=al):   # גל 51: תמונה בראש הקו
                self.dyn(ax.scatter([x], [head], s=90 if is_cur else 60, color=color, alpha=al, zorder=5))
            self.fit_label(self.dyn(ax.text(x + right * (0.035 if self._images else 0.02), head, e, ha="left", va="center", fontsize=11,   # ב16
                                            color=color if is_cur else th.ink, alpha=al, fontweight="bold" if is_cur else "normal", clip_on=False)))