# dataviz/charts/line_race.py
#
# Line race: קו מצטבר לכל ישות שבדירוג, מתחילתה ועד הרגע הנוכחי בתכנית, עם נקודה ותווית
# (שם + ערך) בקצה. אותה תכנית בדיוק כמו ב-bar race: הדירוג המוחלק (pos) קובע מי בתמונה
# והשקיפות של מי שנכנס/יוצא, ו-xmax המוחלק משמש כאן כגובה הציר. ציר הזמן גדל עם הסרטון,
# ונתונים ברמת דיוק אחרת (מרקם פסים בעמודות) מצוירים כקו מקווקו.

import math
from typing import Any, List, Mapping, Tuple

import numpy as np
from matplotlib.ticker import Formatter, FuncFormatter, NullFormatter

from dataviz.charts.base import MARGINS, format_number
from dataviz.charts.timeseries import TimeSeriesChart

DASHED = (0, (3, 2))
# 19.10.2026: איפה תיבת הסיום יכולה לשבת ברמות - הפינה הקבועה קודם, אחר כך שמאל למטה, באמצע הגובה ובאמצע הרוחב
OUTRO_SPOTS = ((0.02, 0.97, "left", "top"), (0.02, 0.03, "left", "bottom"), (0.02, 0.5, "left", "center"),
               (0.5, 0.97, "center", "top"), (0.5, 0.03, "center", "bottom"), (0.5, 0.5, "center", "center"))


class LevelTicks(Formatter):
    """19.10.2026: ציר ה-y כשהספרה העשרונית נוספה לבד (רמות): אם כל השנתות שלמות - בלי ".0" (0, 50, 100)."""

    def __init__(self, fmt: Any, whole: Any):
        self.fmt, self.whole = fmt, whole

    def __call__(self, x: float, pos: Any = None) -> str:
        return str(self.fmt(x))

    def format_ticks(self, values: Any) -> List[str]:
        whole = all(abs(v - round(v)) < 1e-9 for v in values)
        return [str(self.whole(v) if whole else self.fmt(v)) for v in values]


class LineRace(TimeSeriesChart):
    name = "line_race"
    ax2: Any = None   # 20.10.2026: הציר הימני (רק כשיש ישויות עם axis: right)
    ANNOTATES = True

    def setup_data_axes(self) -> None:
        super().setup_data_axes()
        self._right = set(self.ctx.get("right_axis") or [])
        if self._right and not self.log:
            self._setup_dual_axes()
            return
        if self.log:   # גל 49: ציר Y לוגריתמי - ערכים מתחת ל-1 נצמדים לתחתית
            self.log_y = True
            self.ax.set_yscale("log")
            self.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: self.fmt(v)))
            self.ax.yaxis.set_minor_formatter(NullFormatter())
        elif self.ctx.get("auto_decimals"):
            self.ax.yaxis.set_major_formatter(LevelTicks(self.fmt, lambda v: format_number(v, {**(self.numbers or {}), "decimals": 0})))

    def legend_swatch(self, x_sw: float, color: Any, striped: bool, hatch_edge: Any) -> Any:
        (line,) = self.ax.plot([x_sw - 0.02, x_sw], [1.052, 1.052], transform=self.ax.transAxes, clip_on=False,
                               color=color, linewidth=2.6, linestyle=DASHED if striped else "-", solid_capstyle="round")
        return line

    # ------------------------------------------------------------ 20.10.2026: ציר y שני
    def _setup_dual_axes(self) -> None:
        """שני צירים: שמאל לישויות הרגילות, ימין לישויות של מקור axis: right. לכל ציר טווח משלו (סביב הערכים של כל הפרק,
        כמו ברמות), פורמט מספרים משלו (y_axes.<צד>.numbers) וכותרת. שנתות כל ציר בצבע הקו הראשון שעליו."""
        th = self.theme
        axes = self.ctx.get("y_axes") or {}
        self._axis_numbers = {side: (axes.get(side) or {}).get("numbers") or self.numbers for side in ("left", "right")}
        self.numbers = self._axis_numbers["left"]
        self.fig.subplots_adjust(right=MARGINS["right"] - 0.05)   # מקום למספרי הציר הימני
        self.ax2 = self.ax.twinx()
        for spine in self.ax2.spines.values():
            spine.set_visible(False)
        self.ax2.tick_params(axis="y", labelsize=10, colors=th.muted, length=0)
        for side, ax in (("left", self.ax), ("right", self.ax2)):
            numbers = self._axis_numbers[side]
            ax.yaxis.set_major_formatter(LevelTicks(lambda v, n=numbers: format_number(v, n), lambda v, n=numbers: format_number(v, {**n, "decimals": 0})))
            label = (axes.get(side) or {}).get("label")
            if label:   # מעל הציר (כותרת מסובבת בצד מתנגשת בתוויות של הקווים)
                ax.text(0.0 if side == "left" else 1.0, 1.012, label, transform=ax.transAxes, ha="left" if side == "left" else "right",
                        va="bottom", fontsize=9.5, color=th.muted)
        entities = list(self.ctx["entities"])
        for side, ax in (("left", self.ax), ("right", self.ax2)):
            first = next((e for e in entities if (e in self._right) == (side == "right")), None)
            if first is not None:
                ax.tick_params(axis="y", labelcolor=self.color(first))

    def set_data_visible(self, visible: bool) -> None:
        if self.ax2 is not None:
            self.ax2.set_visible(visible)

    def label_limit(self, renderer: Any) -> float:
        if self.ax2 is None:
            return super().label_limit(renderer)
        return float(self.ax.get_window_extent(renderer).x1 - 4)   # המספרים של הציר הימני מעבר לקצה

    def _draw_dual(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        th, top_n = self.theme, self.top_n
        x = float(frame["x"])
        right = self.set_time_axis(x)
        visible = [(e, v, p) for e, v, p in frame["bars"] if top_n - p > 0.01]
        ranges = {}
        for side, ax in (("left", self.ax), ("right", self.ax2)):
            cols = [self._index[e] for e, _v, _p in visible if (e in self._right) == (side == "right")]
            ranges[side] = self.level_range(frame, cols=cols, ax=ax) if cols else (0.0, 1.0)
            ax.set_ylim(*ranges[side])
        (lo_l, hi_l), (lo_r, hi_r) = ranges["left"], ranges["right"]
        to_left = lambda v: lo_l + (v - lo_r) / ((hi_r - lo_r) or 1.0) * (hi_l - lo_l)  # noqa: E731
        right_fmt = lambda v: format_number(v, self._axis_numbers["right"])  # noqa: E731
        cur = frame.get("current")
        ends: List[List[Any]] = []
        for e, v, p in visible:
            al = min(1.0, max(0.0, top_n - p)) * self.focus(e, frame)
            col = self._index[e]
            on_right = e in self._right
            ax = self.ax2 if on_right else self.ax
            xs, ys = self.history(col, x, self._start[col])
            ys[-1] = v
            is_cur = highlight_current and e == cur
            color = th.accent if is_cur else self.color(e)
            self.dyn(ax.plot(xs, ys, color=color, alpha=al, linewidth=3.2 if is_cur else 2.2,
                             linestyle=DASHED if self.is_striped(e) else "-", solid_capstyle="round", zorder=4 if is_cur else 3)[0])
            self.dyn(ax.scatter([x], [v], s=36 if is_cur else 22, color=color, alpha=al, zorder=5))
            ends.append([to_left(v) if on_right else v, v, e, color, al, is_cur])
        self.draw_end_labels(x, right, hi_l, ends, None, ymin=lo_l, formats={e: right_fmt for e in self._right})

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        if self.ax2 is not None:
            self._draw_dual(frame, highlight_current)
            return
        ax, th, top_n = self.ax, self.theme, self.top_n
        x = float(frame["x"])
        right = self.set_time_axis(x)
        ymax = float(frame["xmax"])
        ymin = 0.0
        if self.log_y:
            ax.set_ylim(1, max(ymax, 10.0))
        else:
            ax.set_ylim(0, ymax)
            if self.ctx.get("all_levels"):
                ymin, ymax = self.level_range(frame)
                ax.set_ylim(ymin, ymax)
            elif self.ctx.get("levels"):
                # 18.10.2026: קו של רמה (טמפרטורה 18) לא מתחיל מ-0, אז הוא ישב מעל קו הרשת האחרון שיש לו מספר (15).
                # ראש הציר עולה לשנתה המסומנת הבאה - הקו תמיד מתחת לקו רשת עם מספר. פרק בלי רמות - בלי שינוי.
                # השנתה מכסה גם את היעד שהציר המוחלק מתקרב אליו (הערך הגבוה x axis_headroom): אחרת הציר מתחיל
                # ב-20 וקופץ ל-25 זמן קצר אחרי ההתחלה (18.3 x 1.13 = 20.7) - כך הוא מתחיל ב-25 ונשאר עד שנכנסת ישות חדשה.
                need = max([ymax] + [v * float(self.ctx.get("axis_headroom", 1.0)) for _e, v, _p in frame["bars"]])
                ymax = float(min(t for t in ax.yaxis.get_major_locator().tick_values(0, need) if t >= need))
                ax.set_ylim(0, ymax)
        gains = frame.get("gains") or {}
        arrows = {}
        cur = frame.get("current")
        ends: List[List[Any]] = []
        peak = -math.inf
        for e, v, p in frame["bars"]:
            al = min(1.0, max(0.0, top_n - p)) * self.focus(e, frame)   # 20.10.2026: מצב פוקוס
            if al <= 0.01:
                continue
            col = self._index[e]
            xs, ys = self.history(col, x, self._start[col])
            ys[-1] = v
            peak = max(peak, float(ys.max()))
            if self.log_y:
                ys = np.maximum(ys, 1.0)
            is_cur = highlight_current and e == cur
            color = th.accent if is_cur else self.color(e)
            self.dyn(ax.plot(xs, ys, color=color, alpha=al, linewidth=3.2 if is_cur else 2.2,
                             linestyle=DASHED if self.is_striped(e) else "-", solid_capstyle="round",
                             zorder=4 if is_cur else 3)[0])
            if not self.draw_image(e, (x, max(v, 1.0) if self.log_y else v), 26, align=(0.5, 0.5), alpha=al):   # גל 51: תמונה במקום הנקודה
                self.dyn(ax.scatter([x], [max(v, 1.0) if self.log_y else v], s=36 if is_cur else 22, color=color, alpha=al, zorder=5))
            if gains.get(e):   # גל 49: "+N" מעל הנקודה בקצה הקו
                self.dyn(ax.annotate("+" + self.fmt(gains[e]), (x, max(v, 1.0) if self.log_y else v), xytext=(0, 9),
                                     textcoords="offset points", ha="center", va="bottom", fontsize=9.5, fontweight="bold",
                                     color=th.accent, alpha=al, annotation_clip=False))
            arrow = self.move_text(e, frame)[0]
            if arrow:
                arrows[e] = "  " + arrow
            ends.append([max(v, 1.0) if self.log_y else v, v, e, color, al, is_cur])
        bottom, top = ax.get_ylim()
        if not self.ctx.get("levels") and peak > top:   # ב17: שיא מוקדם בהיסטוריה (rolling, ערכים יורדים) - בתוך הציר
            ymax = peak * float(self.ctx.get("axis_headroom", 1.0))
            ax.set_ylim(bottom, ymax)
        self.draw_end_labels(x, right, ymax, ends, arrows, ymin=ymin)

    def level_range(self, frame: Mapping[str, Any], cols: Any = None, ax: Any = None) -> Tuple[float, float]:
        """19.10.2026: כשכל הישויות רמות (טמפרטורה, מפלס) הציר לא מתחיל מ-0: מהשנתה המסומנת שמתחת לערך הנמוך ועד זו
        שמעל הגבוה, עם מרווח קטן - של כל הקווים שבתמונה לאורך כל הפרק, כך שהציר זז רק כשקו נכנס או יוצא."""
        if cols is None:
            cols = [self._index[e] for e, _v, p in frame["bars"] if self.top_n - p > 0.01]
        if not cols:
            return 0.0, float(frame["xmax"]) or 1.0
        lo = min(float(self._cum[self._start[c]:, c].min()) for c in cols)
        hi = max(float(self._cum[self._start[c]:, c].max()) for c in cols)
        pad = max((hi - lo) * 0.08, abs(hi) * 0.01, 1e-6)
        lo, hi = lo - pad, hi + pad
        if lo < 0 <= lo + pad:   # ערכים לא שליליים - הציר לא יורד מתחת ל-0 בגלל המרווח
            lo = 0.0
        locator = (ax or self.ax).yaxis.get_major_locator()
        for _ in range(4):   # ראש ותחתית על שנתות של הטווח עצמו - כדי שיופיעו עם מספר
            ticks = locator.tick_values(lo, hi)
            new_lo = float(max([t for t in ticks if t <= lo + 1e-9] or [lo]))
            new_hi = float(min([t for t in ticks if t >= hi - 1e-9] or [hi]))
            if (new_lo, new_hi) == (lo, hi):
                break
            lo, hi = new_lo, new_hi
        return lo, hi

    def draw_outro_box(self, frame: Mapping[str, Any]) -> None:
        """19.10.2026: ברמות הקווים ממלאים את הגובה, אז תיבת הסיום עוברת לפינה שבה הכי מעט מהקווים (שמאל למעלה, שמאל
        למטה, אמצע למעלה או למטה). פרק בלי רמות - בפינה הקבועה כמו קודם."""
        super().draw_outro_box(frame)
        if not self.ctx.get("levels") and self.ax2 is None:
            return
        text = self._dynamic[-1]
        renderer = self.fig.canvas.get_renderer()   # type: ignore[attr-defined]  # Agg
        text.update_bbox_position_size(renderer)
        box = text.get_bbox_patch().get_window_extent(renderer)
        w, h = box.width, box.height
        lines = list(self.ax.lines) + (list(self.ax2.lines) if self.ax2 is not None else [])   # 20.10.2026: גם הציר הימני
        points = [line.get_transform().transform(np.column_stack(line.get_data())) for line in lines if np.size(line.get_xdata())]
        if not points:
            return
        xy = np.vstack(points)
        area = self.ax.get_window_extent(renderer)
        fx0, fy0, _ha, _va = self.OUTRO_AT                       # התיבה צוירה בפינה הקבועה (שמאל למעלה)
        pad_x = box.x0 - (area.x0 + fx0 * area.width)            # הריפוד של התיבה מעבר לנקודת העיגון
        pad_y = box.y1 - (area.y0 + fy0 * area.height)
        best: Tuple[int, float, float, str, str] | None = None
        for fx, fy, ha, va in OUTRO_SPOTS:
            ax_, ay = area.x0 + fx * area.width, area.y0 + fy * area.height
            left = ax_ + pad_x if ha == "left" else ax_ - w / 2
            bottom = ay + pad_y - h if va == "top" else (ay - h / 2 if va == "center" else ay - pad_y)
            inside = int(((xy[:, 0] >= left) & (xy[:, 0] <= left + w) & (xy[:, 1] >= bottom) & (xy[:, 1] <= bottom + h)).sum())
            if best is None or inside < best[0]:
                best = (inside, fx, fy, ha, va)
        assert best is not None   # OUTRO_SPOTS לא ריק
        _inside, fx, fy, ha, va = best
        text.set_position((fx, fy))
        text.set_horizontalalignment(ha)
        text.set_verticalalignment(va)

    def callout_anchor(self, entity: Any, frame: Mapping[str, Any]) -> Any:
        """גל 50: הערה לישות מצביעה מקצה הקו שלה (משמאל-למעלה - מימין יש את התוויות)."""
        for e, v, p in frame["bars"]:
            if e == entity and p < self.top_n - 0.5:
                return (float(frame["x"]), max(v, 1.0) if self.log_y else v), (-40, 30), "right"
        return None
