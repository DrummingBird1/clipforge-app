# dataviz/charts/pie_race.py
#
# גל 51: עוגה / דונאט מתחלף - הנתח של כל ישות מהסכום הכולל ברגע הנוכחי. ה-top_n של הדירוג המוחלק הן פרוסות
# (לפי הדירוג, מלמעלה עם כיוון השעון), כל השאר מתאחדות ל"אחרים" (labels.others), והסכום במרכז. אותה תכנית כמו
# בשאר התרשימים - הפרוסות זזות כשהדירוג משתנה, והישות הנוכחית בולטת החוצה.

import math
from typing import Any, Mapping

from matplotlib.patches import Wedge

from dataviz.charts.base import BaseChart, round_half_up

RADIUS, RING = 1.0, 0.42       # רדיוס הטבעת ועובייה (דונאט)
LABEL_MIN_SHARE = 0.025        # פרוסה קטנה מזה בלי תווית - התוויות היו נדחסות
EXPLODE = 0.07                 # כמה הישות הנוכחית יוצאת מהטבעת
HALF_HEIGHT = 1.5


class PieRace(BaseChart):
    name = "pie_race"
    CARD_AT = (0.02, 0.97, "left", "top")
    TOAST_AT = (0.02, 0.06, "left", "bottom")
    OUTRO_AT = (0.02, 0.97, "left", "top")

    def setup_data_axes(self) -> None:
        ax = self.ax
        ax.set_facecolor(self.theme.bg)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        # עיגול עגול באמת: הציר האופקי רחב לפי היחס של אזור הנתונים
        box = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        aspect = (box.width * fig_w) / max(box.height * fig_h, 1e-9)
        ax.set_xlim(-HALF_HEIGHT * aspect, HALF_HEIGHT * aspect)
        ax.set_ylim(-HALF_HEIGHT, HALF_HEIGHT)

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        total = float(frame["total"])
        ranked = sorted((bar for bar in frame["bars"] if bar[2] < top_n - 0.5), key=lambda bar: bar[2])
        if total <= 0 or not ranked:
            return
        slices: list = [(e, max(float(v), 0.0)) for e, v, _ in ranked]
        others = total - sum(v for _, v in slices)
        if others > total * 0.001:
            slices.append((None, others))
        # נ12: ישות שלילית לא נכנסת לעוגה (0) - אז הסך שלה קטן מהפרוסות; העוגה והאחוזים מתוך הפרוסות עצמן
        whole = total if others >= 0 else sum(v for _, v in slices)
        current = frame.get("current") if highlight_current else None
        angle = 90.0
        for entity, value in slices:
            sweep = 360.0 * value / whole
            if sweep <= 0:
                continue
            is_cur = entity is not None and entity == current
            middle = math.radians(angle - sweep / 2)
            shift = EXPLODE if is_cur else 0.0
            center = (shift * math.cos(middle), shift * math.sin(middle))
            color = th.grid if entity is None else (th.accent if is_cur else self.color(entity))
            self.dyn(ax.add_patch(Wedge(center, RADIUS, angle - sweep, angle, width=RING, facecolor=color, edgecolor=th.bg,
                                        linewidth=1.5, zorder=3)))
            if entity is not None and self.is_striped(entity):
                self.dyn(ax.add_patch(Wedge(center, RADIUS, angle - sweep, angle, width=RING, facecolor="none",
                                            edgecolor=(*th.hatch_rgb, th.hatch_alpha), hatch="////", linewidth=0, zorder=3.5)))
            share = value / whole
            if share >= LABEL_MIN_SHARE:
                name = str(self.ctx["labels"].get("others") or "") if entity is None else str(entity)
                cos, sin = math.cos(middle), math.sin(middle)
                at = RADIUS + 0.12 + shift
                self.dyn(ax.text(at * cos, at * sin, f"{name}\n{self.fmt(value)} · {round_half_up(share * 100):.0f}%", ha="left" if cos >= 0 else "right",
                                 va="center", fontsize=11, color=th.ink, fontweight="bold" if is_cur else "normal", zorder=4,
                                 linespacing=1.3))
                if entity is not None:   # גל 51: התמונה של הישות על הפרוסה
                    ring_middle = RADIUS - RING / 2 + shift
                    self.draw_image(entity, (ring_middle * cos, ring_middle * sin), 30, align=(0.5, 0.5))
            angle -= sweep
        self.dyn(ax.text(0, 0.06, self.fmt(total), ha="center", va="center", fontsize=26, fontweight="bold", color=th.ink, zorder=4))
        if self.ctx["labels"].get("total"):
            self.dyn(ax.text(0, -0.2, self.ctx["labels"]["total"], ha="center", va="center", fontsize=11, color=th.muted, zorder=4))
