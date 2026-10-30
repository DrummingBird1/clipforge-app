# dataviz/charts/timeseries.py
#
# בסיס לתרשימים עם ציר זמן אופקי (קו, שטח מוערם): היסטוריה מצטברת מתוך ה-ctx, ציר זמן
# שגדל עם הסרטון (לפחות שנה), תוויות שנה ב-1 בינואר (מדוללות כשיש הרבה), ותוויות בקצה
# בלי חפיפה. המיקומים של כרטיס/התראה/סיום עוברים לפינה השמאלית העליונה - בגרף מצטבר היא
# כמעט תמיד ריקה, והצד הימני תפוס בתוויות.

import math
from typing import Any, List

import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter

from dataviz.charts.base import BaseChart, NumberTicks, ltr_number

MAX_POINTS = 400          # נקודות לסדרה בפריים (דילול היסטוריה ארוכה - מהירות בלי הבדל נראה)
MIN_WINDOW_DAYS = 365     # ציר הזמן לא קטן משנה, כדי שההתחלה לא תהיה "זום" מוגזם
RIGHT_MARGIN = 0.16       # מקום לתוויות בקצה
LABEL_GAP = 0.055         # מרווח מינימלי בין תוויות (חלק מגובה הציר)
LABEL_EDGE = 0.995        # 18.10.2026: תווית בקצה לא עוברת את הגבול הזה (חלק מרוחב הפריים)


def spread_labels(values: List[float], gap: float, floor: float = 0.0) -> List[float]:
    """מיקומי תוויות (ערכים ממוינים מהגבוה לנמוך) בלי חפיפה: כל אחת לפחות gap מתחת לקודמת,
    ואם התחתונות נדחקו מתחת לרצפה - דוחפים מלמטה למעלה."""
    ys: List[float] = []
    for v in values:
        ys.append(min(v, ys[-1] - gap) if ys else v)
    low = floor
    for k in range(len(ys) - 1, -1, -1):
        ys[k] = max(ys[k], low)
        low = ys[k] + gap
    return ys


class TimeSeriesChart(BaseChart):
    CARD_AT = (0.02, 0.97, "left", "top")
    TOAST_AT = (0.36, 0.97, "left", "top")
    OUTRO_AT = (0.02, 0.97, "left", "top")
    log_y = False     # גל 49: ציר Y לוגריתמי - רק בתרשים הקווים (שטח מוערם, דירוגים ומפת חום לא)
    HAS_TIME_AXIS = True

    def draw_periods(self, x: float) -> None:
        """גל 50: תקופה מוצללת על ציר הזמן עצמו - מההתחלה שלה ועד היום הנוכחי, עם השם למעלה."""
        th = self.theme
        for start, end, label, color in self.ctx.get("periods") or []:
            if start > x:
                continue
            self.dyn(self.ax.axvspan(start, max(min(end, x), start + 0.5), color=color or th.accent, alpha=0.12, linewidth=0, zorder=1))
            self.dyn(self.ax.text(start, 0.985, " " + label, transform=self.ax.get_xaxis_transform(), ha="left", va="top",
                                  fontsize=9.5, color=th.muted, zorder=2, clip_on=True))

    def setup_data_axes(self) -> None:
        ax, th = self.ax, self.theme
        ax.set_facecolor(th.bg)
        for side, spine in ax.spines.items():
            spine.set_visible(side == "bottom")
        ax.spines["bottom"].set_color(th.grid)
        ax.yaxis.set_major_formatter(NumberTicks(self.numbers))   # ב18: שנתות compact בלי כפולות
        self.whole_ticks(ax.yaxis)   # ציר לוגריתמי (line_race) מחליף אותו אחר כך
        ax.tick_params(axis="both", labelsize=10, colors=th.muted, length=0)
        if self.style["grid"]:   # גל 51
            ax.grid(axis="y", color=th.grid, linewidth=0.9)
        ax.set_axisbelow(True)
        self._cum = np.asarray(self.ctx["cum"])
        self._start = list(self.ctx["start_idx"])
        dates = pd.DatetimeIndex(self.ctx["dates"])
        first_days = np.asarray(dates.is_year_start).copy()
        first_days[0] = True
        self._year_ticks = [(int(i), str(dates[i].year)) for i in np.flatnonzero(first_days)]
        if len(self._year_ticks) < 3:   # ב15: פרק של פחות משנתיים - שנתה בכל חודש (1/2024, 2/2024...)
            first_days = np.asarray(dates.is_month_start).copy()
            first_days[0] = True
            self._year_ticks = [(int(i), f"{dates[i].month}/{dates[i].year}") for i in np.flatnonzero(first_days)]
        self._tick_labels = dict(self._year_ticks)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: self._tick_labels.get(int(round(v)), "")))

    def set_time_axis(self, x: float) -> float:
        """ציר הזמן עד היום הנוכחי (עם מרווח לתוויות) - מחזיר את הקצה הימני של הנתונים. ב15: פרק קצר משנה - עד הסוף שלו."""
        right = max(x, min(MIN_WINDOW_DAYS, max(len(self._cum) - 1, 1)))
        self.ax.set_xlim(0, right * (1 + RIGHT_MARGIN))
        visible = [i for i, _ in self._year_ticks if i <= right]
        step = max(1, math.ceil(len(visible) / 10))
        self.ax.xaxis.set_major_locator(FixedLocator(visible[::step]))
        return right

    def history(self, col: int, x: float, start: int) -> tuple:
        """(ימים, ערכים מצטברים) של ישות מ-start ועד x (הנקודה האחרונה מאונטרפלת), מדולל."""
        i0 = int(math.floor(x))
        start = min(start, i0)
        idx = np.arange(start, i0 + 1)
        idx = idx[::max(1, math.ceil(len(idx) / MAX_POINTS))]
        a = x - i0
        i1 = min(i0 + 1, len(self._cum) - 1)
        last = self._cum[i0, col] * (1 - a) + self._cum[i1, col] * a
        return np.append(idx, x), np.append(self._cum[idx, col], last)

    def draw_end_labels(self, x: float, right: float, ymax: float, ends: List[List[Any]], arrows: Any = None, ymin: float = 0.0,
                        formats: Any = None) -> None:
        """ends = [y של הקצה, ערך לתווית, ישות, צבע, שקיפות, נוכחית?] - תוויות בקצה, בלי חפיפה.
        arrows (גל 49): ישות -> " ▲2" שנוסף לתווית. ymin (19.10.2026): תחתית הציר כשהוא לא מתחיל מ-0 (רמות).
        formats (20.10.2026): ישות -> פונקציית פורמט משלה (ציר y שני)."""
        ax, th = self.ax, self.theme
        ends = sorted(ends, key=lambda item: -item[0])
        if self.log_y:   # בציר לוגריתמי המרווח בין התוויות נמדד ב-log10, ואז חוזר לערכים
            gap = math.log10(max(ymax, 10.0)) * LABEL_GAP
            spread = [10 ** y for y in spread_labels([math.log10(max(item[0], 1.0)) for item in ends], gap)]
        else:
            gap = (ymax - ymin) * LABEL_GAP
            spread = spread_labels([item[0] for item in ends], gap, ymin)
        for (y_end, value, e, color, al, is_cur), y in zip(ends, spread):
            moved = abs(math.log10(max(y, 1.0)) - math.log10(max(y_end, 1.0))) if self.log_y else abs(y - y_end)
            if moved > gap * 0.3:      # תווית שנדחקה מהקצה שלה - קו מחבר דק
                self.dyn(ax.plot([x, x + right * 0.012], [y_end, y], color=th.muted, linewidth=0.8, alpha=al * 0.8,
                                 clip_on=False, zorder=2)[0])
            arrow = (arrows or {}).get(e, "")
            pad = right * (0.03 if self._images else 0.015)     # גל 51: מקום לתמונה בקצה הקו
            fmt = (formats or {}).get(e, self.fmt)
            self.fit_label(self.hit(self.dyn(ax.text(x + pad, y, f"{e}  {ltr_number(fmt(value) + arrow)}", ha="left", va="center", fontsize=11,
                                            color=color if is_cur else th.ink, alpha=al, fontweight="bold" if is_cur else "normal",
                                            clip_on=False)), f"entity:{e}"))

    def label_limit(self, renderer: Any) -> float:
        """עד איפה (פיקסלים מהשמאל) תווית בקצה יכולה להגיע. 20.10.2026: ציר y שני מחליף את זה בקצה אזור הנתונים."""
        return float(self.fig.bbox.width * LABEL_EDGE)

    def fit_label(self, label: Any) -> None:
        """18.10.2026: תווית שיוצאת מהצד הימני של הפריים (שם סדרה ארוך) נשברת לשורות עד הגבול, במקום להיחתך.
        תווית שנכנסת - בלי שום שינוי."""
        self.fit_text(label, hi=self.label_limit(self.fig.canvas.get_renderer()))   # type: ignore[attr-defined]  # Agg
