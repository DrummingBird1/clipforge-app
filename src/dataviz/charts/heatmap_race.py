# dataviz/charts/heatmap_race.py
#
# Heatmap: שורה לכל ישות מהדירוג הנוכחי (הראשונה למעלה), עמודות = הזמן עד עכשיו, צבע = הערך המצטבר באותו יום
# (מנורמל לציר המקסימום החלק של התוכנית). מראה במבט אחד מי הובילה ומתי, ונבנה מחדש בכל פריים.

import math
from typing import Any, List, Mapping

import numpy as np
from matplotlib.colors import LogNorm
from matplotlib.ticker import NullLocator

from dataviz.charts.base import ltr_number
from dataviz.charts.timeseries import TimeSeriesChart

MAX_COLUMNS = 240


class HeatmapRace(TimeSeriesChart):
    name = "heatmap_race"

    def setup_data_axes(self) -> None:
        super().setup_data_axes()
        self.ax.yaxis.set_major_locator(NullLocator())
        self.ax.grid(False)
        self.ax.set_ylim(self.top_n + 0.5, 0.5)

    def legend_swatch(self, x_sw: float, color: Any, striped: bool, hatch_edge: Any) -> Any:
        return super(TimeSeriesChart, self).legend_swatch(x_sw, color, striped, hatch_edge)

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        x = float(frame["x"])
        right = self.set_time_axis(x)
        i0 = int(math.floor(x))
        ranked = sorted((b for b in frame["bars"] if b[2] < top_n - 0.5), key=lambda b: b[2])[:top_n]
        if not ranked:
            return
        cols = np.unique(np.linspace(0, i0, min(MAX_COLUMNS, i0 + 1)).astype(int))
        matrix = np.full((top_n, len(cols)), np.nan)
        for row, (e, _, _) in enumerate(ranked):
            col = self._index[e]
            values = np.asarray(self._cum[cols, col], dtype=float)
            values[cols < self._start[col]] = np.nan
            matrix[row] = values
        vmax = max(float(frame["xmax"]), 1.0)
        norm: Any = None
        if self.log:   # גל 49: צבע לוגריתמי - ערכים מתחת ל-1 נשארים ריקים
            matrix[matrix < 1] = np.nan
            norm = LogNorm(vmin=1.0, vmax=max(vmax, 10.0))
        image = ax.imshow(np.ma.masked_invalid(matrix), extent=(0, x, top_n + 0.5, 0.5), origin="upper", aspect="auto",
                          cmap=self._cmap, norm=norm, vmin=None if norm else 0, vmax=None if norm else vmax,
                          interpolation="nearest", zorder=3)
        self.dyn(image)
        ax.set_xlim(0, right * (1 + 0.16))
        ends: List[Any] = []
        cur = frame.get("current")
        for row, (e, v, _) in enumerate(ranked):
            is_cur = highlight_current and e == cur
            ends.append(self.hit(self.dyn(ax.text(x + right * 0.015, row + 1, f"{e}  {ltr_number(self.fmt(v))}", ha="left", va="center", fontsize=11,
                                         color=th.accent if is_cur else th.ink, fontweight="bold" if is_cur else "normal",
                                         clip_on=False)), f"entity:{e}"))
            self.fit_label(ends[-1])   # ב16: שם ארוך נשבר לשורות בתוך הפריים