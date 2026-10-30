# dataviz/charts/scatter_race.py
#
# Scatter race: כל ישות היא בועה - X = המצטבר עד עכשיו, Y = הקצב (כמה נוסף ב-window_days
# הימים האחרונים), גודל = המצטבר. אותה תכנית: הדירוג המוחלק קובע מי בתמונה ושקיפות
# כניסה/יציאה, ו-xmax המוחלק הוא ציר ה-X. ציר ה-Y מחושב מראש לכל יום (מקסימום מתגלגל
# ואז ממוצע) - כך שגם כאן הציור הוא פונקציה טהורה של הפריים, בלי מצב מפריים לפריים.

import math
from typing import Any, List, Mapping, Sequence

import numpy as np
import pandas as pd
from matplotlib.ticker import NullFormatter

from dataviz.charts.base import TEXT_EDGE, BaseChart, NumberTicks

AXIS_LOOK_DAYS = 60       # ציר Y מסתכל חודשיים קדימה ואחורה, כדי לפנות מקום לפני קפיצה
MIN_BUBBLE, MAX_BUBBLE = 30.0, 1500.0


def label_tiers(xs_px: Sequence[float], widths_px: Sequence[float]) -> List[int]:
    """שורה (0, 1, 2...) לכל תווית, כך שתוויות באותה שורה לא חופפות אופקית (ממוינות לפי x)."""
    tiers: List[int] = []
    ends: List[float] = []       # הקצה הימני האחרון בכל שורה
    for x, w in zip(xs_px, widths_px):
        left = x - w / 2
        tier = next((k for k, end in enumerate(ends) if left > end), len(ends))
        if tier == len(ends):
            ends.append(0.0)
        ends[tier] = x + w / 2 + 4
        tiers.append(tier)
    return tiers


class ScatterRace(BaseChart):
    name = "scatter_race"
    # הבועות הגדולות בצד ימין-למטה; למעלה-שמאל (קצב גבוה, מצטבר נמוך) כמעט תמיד ריק
    CARD_AT = (0.02, 0.97, "left", "top")
    TOAST_AT = (0.5, 0.97, "center", "top")
    OUTRO_AT = (0.02, 0.97, "left", "top")
    LABEL_PT = 11
    TIER_PT = 15

    def setup_data_axes(self) -> None:
        ax, th = self.ax, self.theme
        cfg = self.ctx.get("scatter") or {}
        ax.set_facecolor(th.bg)
        for spine in ax.spines.values():
            spine.set_visible(False)
        formatter = NumberTicks(self.numbers)   # ב18: שנתות compact בלי כפולות
        if self.log:   # גל 49: ציר X (המצטבר) לוגריתמי - בועות מתחת ל-1 נצמדות לתחילת הציר
            ax.set_xscale("log")
            ax.xaxis.set_minor_formatter(NullFormatter())
        ax.xaxis.set_major_formatter(formatter)
        ax.yaxis.set_major_formatter(formatter)
        if not self.log:
            self.whole_ticks(ax.xaxis)
        self.whole_ticks(ax.yaxis)
        ax.tick_params(axis="both", labelsize=10, colors=th.muted, length=0)
        if self.style["grid"]:   # גל 51
            ax.grid(color=th.grid, linewidth=0.9)
        ax.set_axisbelow(True)
        ax.set_xlabel(cfg.get("x_label", ""), fontsize=10, color=th.muted)
        ax.set_ylabel(cfg.get("y_label", ""), fontsize=10, color=th.muted)
        window = int(cfg.get("window_days", 30))
        cum = np.asarray(self.ctx["cum"])
        before = np.vstack([np.zeros((window, cum.shape[1])), cum[:-window]]) if len(cum) > window else np.zeros_like(cum)
        self._rate = cum - before
        top = pd.Series(self._rate.max(axis=1))
        self._yaxis = np.maximum(top.rolling(AXIS_LOOK_DAYS, center=True, min_periods=1).max()
                                 .rolling(window, center=True, min_periods=1).mean().to_numpy() * 1.25, 1.0)
        # ב19: קצב שלילי (ערכים יורדים, מצב rolling) - התחתית יורדת באותה דרך. קצב שלא יורד מתחת ל-0 - 0, כמו קודם
        low = pd.Series(self._rate.min(axis=1))
        self._ylow = np.minimum(low.rolling(AXIS_LOOK_DAYS, center=True, min_periods=1).min()
                                .rolling(window, center=True, min_periods=1).mean().to_numpy() * 1.25, 0.0)

    def _at(self, series: np.ndarray, x: float) -> Any:
        i0 = int(math.floor(x))
        i1 = min(i0 + 1, len(series) - 1)
        a = x - i0
        return series[i0] * (1 - a) + series[i1] * a

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        x = float(frame["x"])
        xmax = float(frame["xmax"])
        ymax = float(self._at(self._yaxis, x))
        rates = self._at(self._rate, x)
        ylow = min(float(self._at(self._ylow, x)), float(min(rates.min(), 0.0)) * 1.1)
        if self.log:
            ax.set_xlim(1, max(xmax, 10.0))
        else:
            ax.set_xlim(0, xmax)
        ax.set_ylim(ylow - ymax * 0.07, ymax)    # מרווח מתחת לאפס: בועות של קצב 0 לא מסתירות את ציר X
        cur = frame.get("current")
        shown: List[Any] = []
        for e, v, p in sorted(frame["bars"], key=lambda bar: -bar[1]):     # הגדולות מאחור
            al = min(1.0, max(0.0, top_n - p))
            if al <= 0.01:
                continue
            r = float(rates[self._index[e]])
            size = MIN_BUBBLE + (MAX_BUBBLE - MIN_BUBBLE) * min(max(v, 0.0) / xmax, 1.0) if xmax > 0 else MIN_BUBBLE   # ב14: ערך שלילי - הבועה הקטנה
            is_cur = highlight_current and e == cur
            color = th.accent if is_cur else self.color(e)
            v = max(v, 1.0) if self.log else v
            self.dyn(ax.scatter([v], [r], s=size, color=color, alpha=al * 0.88, edgecolors=th.bg, linewidths=1.2,
                                zorder=5 if is_cur else 4, clip_on=False))
            if self.is_striped(e):
                self.dyn(ax.scatter([v], [r], s=size, facecolors="none", edgecolors=[(*th.hatch_rgb, th.hatch_alpha * al)],
                                    hatch="////", linewidths=0, zorder=5 if is_cur else 4, clip_on=False))
            shown.append((v, r, size, e, color, al, is_cur))
        # תוויות מעל הבועות; תוויות שהיו חופפות אופקית עולות לשורה נוספת
        px_per_unit = ax.get_window_extent().width / xmax if xmax > 0 else 0.0
        pt_px = self.fig.dpi / 72
        shown.sort(key=lambda item: item[0])
        widths = [len(str(item[3])) * self.LABEL_PT * 0.62 * pt_px for item in shown]
        if self.log:   # בציר לוגריתמי המרחק בפיקסלים לא יחסי לערך - לוקחים אותו מהציר עצמו
            xs_px = [float(ax.transData.transform((item[0], 0))[0]) for item in shown]
        else:
            xs_px = [item[0] * px_per_unit for item in shown]
        lo, hi = self.fig.bbox.width * TEXT_EDGE, self.fig.bbox.width * (1 - TEXT_EDGE)
        for (v, r, size, e, color, al, is_cur), tier, width in zip(shown, label_tiers(xs_px, widths), widths):
            label = self.dyn(ax.annotate(str(e), (v, r), xytext=(0, math.sqrt(size) / 2 + 3 + tier * self.TIER_PT), textcoords="offset points",
                                         ha="center", va="bottom", fontsize=self.LABEL_PT, color=color if is_cur else th.ink, alpha=al,
                                         fontweight="bold" if is_cur else "normal", annotation_clip=False))
            middle = float(ax.transData.transform((v, r))[0])
            if middle - width * 0.6 < lo or middle + width * 0.6 > hi:   # ב16: רק תווית שקרובה לקצה הפריים נמדדת
                self.fit_text(label, lo, hi)
