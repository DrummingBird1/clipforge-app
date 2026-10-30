# dataviz/charts/stacked_area_race.py
#
# Stacked area race: כל הישויות הפעילות מוערמות זו על זו (מצטבר לאורך הזמן), בסדר קבוע
# (סדר הישויות - שכבה לא קופצת כשהדירוג משתנה), כך שהחלק העליון הוא הסך הכולל. ה-top_n
# של הדירוג המוחלק מקבלים תווית בקצה, באמצע השכבה שלהם; הישות הנוכחית מודגשת. הציר
# האנכי הולך לפי הסך הכולל של הפריים (מצטבר - עולה בהדרגה בלי החלקה נוספת).

import math
from typing import Any, List, Mapping

import numpy as np

from dataviz.charts.timeseries import TimeSeriesChart


class StackedAreaRace(TimeSeriesChart):
    ANNOTATES = True   # 20.10.2026: הערה על הגרף
    name = "stacked_area_race"
    HEADROOM = 1.08

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        x = float(frame["x"])
        right = self.set_time_axis(x)
        ymax = max(float(frame["total"]) * self.HEADROOM, float(frame["xmax"]))
        ax.set_ylim(0, ymax)
        i0 = int(math.floor(x))
        ranked = {e for e, _, p in frame["bars"] if p < top_n - 0.5}
        cur = frame.get("current")
        base: Any = None
        ends: List[List[Any]] = []
        for e in self.ctx["entities"]:
            col = self._index[e]
            if self._start[col] > i0:
                continue
            xs, ys = self.history(col, x, 0)
            base = np.zeros(len(xs)) if base is None else base
            top = base + ys
            is_cur = highlight_current and e == cur
            color = th.accent if is_cur else self.color(e)
            self.dyn(ax.fill_between(xs, base, top, facecolor=color, linewidth=0, alpha=0.92, zorder=3))
            if self.is_striped(e):
                self.dyn(ax.fill_between(xs, base, top, facecolor="none", edgecolor=(*th.hatch_rgb, th.hatch_alpha),
                                         hatch="////", linewidth=0, zorder=3.5))
            if e in ranked and ys[-1] > 0:
                ends.append([base[-1] + ys[-1] / 2, ys[-1], e, color, 1.0, is_cur])
            base = top
        if base is not None and float(base.max()) * self.HEADROOM > ymax * (1 + 1e-9):   # ב17: שיא מוקדם (rolling) - בתוך הציר
            ymax = float(base.max()) * self.HEADROOM
            ax.set_ylim(0, ymax)
        self.draw_end_labels(x, right, ymax, ends)
