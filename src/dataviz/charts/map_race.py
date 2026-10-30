# dataviz/charts/map_race.py
#
# גל 42: מפה (choropleth) - כל אזור בקובץ ה-GeoJSON של הפרק נצבע לפי הערך המצטבר של הישות באותו שם,
# ומתחזק ככל שהיא גדלה; לצד המפה - הדירוג (top_n) עם הערכים. האזורים נבנים פעם אחת (מצולע לכל חלק של
# אזור, עם החורים שלו - גל 45) ובכל פריים משתנים רק הצבעים והדירוג. ישות בלי אזור במפה מופיעה רק בדירוג.

import math
from typing import Any, Dict, List, Mapping, Sequence

import numpy as np
from matplotlib.collections import PatchCollection
from matplotlib.patches import PathPatch
from matplotlib.path import Path

from dataviz.charts.base import BaseChart

MAP_SHARE = 0.58      # החלק של אזור הנתונים שהמפה תופסת (משמאל); מימין - הדירוג
LIST_X = 0.64
MAX_MAP_LABELS = 40   # גל 51: שמות על המפה - לא יותר מזה (מפת העולם הייתה נקברת בטקסט)
LEGEND_RECT = (0.03, 0.05, 0.22, 0.03)   # סקאלת הצבעים - פינה שמאלית תחתונה של המפה (חלק מאזור הנתונים)


def ring_centroid(ring: Sequence[Sequence[float]]) -> tuple:
    """מרכז הכובד של טבעת (נוסחת השרוך); טבעת מנוונת - ממוצע הנקודות."""
    area = _signed_area(ring)
    if abs(area) < 1e-12:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, list(ring[1:]) + [ring[0]]):
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return cx / (6 * area), cy / (6 * area)


def _signed_area(ring: Sequence[Sequence[float]]) -> float:
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, list(ring[1:]) + [ring[0]])) / 2


def polygon_path(rings: Sequence[Sequence[Sequence[float]]]) -> Path:
    """מצולע עם חורים כ-Path אחד: הטבעת החיצונית נגד כיוון השעון והחורים עם כיוון השעון - כך כלל המילוי
    (nonzero) של matplotlib משאיר את החורים ריקים, בלי תלות בכיוון שבקובץ."""
    vertices: List[Sequence[float]] = []
    codes: List[int] = []
    for k, ring in enumerate(rings):
        ring = list(ring)
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        outer = k == 0
        if (_signed_area(ring) > 0) != outer:
            ring = ring[::-1]
        vertices += ring + [ring[0]]
        codes += [int(Path.MOVETO)] + [int(Path.LINETO)] * (len(ring) - 1) + [int(Path.CLOSEPOLY)]
    return Path(np.asarray(vertices, dtype=float), codes)


class MapRace(BaseChart):
    name = "map_race"
    CARD_AT = (0.985, 0.03, "right", "bottom")
    TOAST_AT = (0.29, 0.06, "center", "center")
    OUTRO_AT = (0.985, 0.03, "right", "bottom")

    def setup_data_axes(self) -> None:
        ax, th, ctx = self.ax, self.theme, self.ctx
        geo = ctx.get("map")
        if not geo:
            raise ValueError("תרשים מפה (map_race) צריך קובץ GeoJSON (map.geojson).")
        self._cum = np.asarray(ctx["cum"], dtype=float)
        self._n_days = len(self._cum)
        columns: Dict[str, int] = {str(e): i for i, e in enumerate(ctx["entities"])}
        patches: List[Any] = []
        self._owner: List[int] = []           # לכל מצולע - העמודה של הישות (-1 = אזור בלי ישות)
        self._names: List[str] = []
        for feature in geo["features"]:
            column = columns.get(feature["name"], -1)
            for polygon in feature.get("polygons") or [[ring] for ring in feature["rings"]]:
                patches.append(PathPatch(polygon_path(polygon)))
                self._owner.append(column)
                self._names.append(feature["name"])
        self._owner_arr = np.asarray(self._owner)
        self._polys = PatchCollection(patches, facecolors=th.grid, edgecolors=th.bg, linewidths=0.6, zorder=3)
        ax.add_collection(self._polys)
        # גל 51: שמות על המפה (במרכז החלק הגדול של כל אזור) וסקאלת צבעים
        style = ctx.get("map_style") or {}
        self._label_mode = str(style.get("labels") or "none")
        self._label_at: Dict[str, Any] = {}
        for feature in geo["features"]:
            polygons = feature.get("polygons") or [[ring] for ring in feature["rings"]]
            biggest = max(polygons, key=lambda polygon: abs(_signed_area(polygon[0])))
            self._label_at[feature["name"]] = ring_centroid(biggest[0])
        self._legend_ax = None
        if style.get("legend"):
            legend = ax.inset_axes(LEGEND_RECT, zorder=6)
            legend.imshow(np.linspace(0.12, 1.0, 256)[None, :], aspect="auto", cmap=self._cmap, vmin=0, vmax=1)
            legend.set_xticks([])
            legend.set_yticks([])
            for spine in legend.spines.values():
                spine.set_edgecolor(th.muted)
            self._legend_ax = legend
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        for spine in ax.spines.values():
            spine.set_visible(False)
        self._fit(geo["bounds"])

    def _fit(self, bounds: Any) -> None:
        """גבולות הציר כך שהמפה נשמרת ביחס הנכון ותופסת את MAP_SHARE השמאלי של אזור הנתונים."""
        x0, y0, x1, y1 = (float(v) for v in bounds)
        box = self.ax.get_position()
        fig_w, fig_h = self.fig.get_size_inches()
        width_px, height_px = box.width * fig_w, box.height * fig_h
        span_x, span_y = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        scale = min(MAP_SHARE * 0.96 * width_px / span_x, 0.94 * height_px / span_y)
        left = x0 - 0.02 * width_px / scale
        self.ax.set_xlim(left, left + width_px / scale)
        middle = (y0 + y1) / 2
        half = height_px / scale / 2
        self.ax.set_ylim(middle - half, middle + half)

    def set_data_visible(self, visible: bool) -> None:
        self._polys.set_visible(visible)
        if self._legend_ax is not None:
            self._legend_ax.set_visible(visible)

    def draw_map_labels(self, values: np.ndarray, order: Sequence[int]) -> None:
        """גל 51: שמות האזורים על המפה - top: רק של ה-top_n בדירוג; all: כל אזור עם ערך (עד MAX_MAP_LABELS)."""
        if self._label_mode == "none":
            return
        from matplotlib import patheffects
        entities = self.ctx["entities"]
        if self._label_mode == "top":
            names = [str(entities[column]) for column in order]
        else:
            names = [str(entities[int(i)]) for i in np.argsort(-values, kind="stable") if values[int(i)] > 0]
        th = self.theme
        outline = [patheffects.withStroke(linewidth=2.6, foreground=th.bg)]
        for name in names[:MAX_MAP_LABELS]:
            if name in self._label_at:
                x, y = self._label_at[name]
                self.dyn(self.ax.text(x, y, name, ha="center", va="center", fontsize=8.5, color=th.ink, zorder=4,
                                      path_effects=outline, clip_on=True))

    def draw_legend_values(self, vmax: float) -> None:
        if self._legend_ax is None:
            return
        x0, y0, width, _height = LEGEND_RECT
        th = self.theme
        low = self.fmt(1) if self.log else self.fmt(0)
        for x, text, ha in ((x0, low, "left"), (x0 + width, self.fmt(vmax), "right")):
            self.dyn(self.ax.text(x, y0 - 0.01, text, transform=self.ax.transAxes, ha=ha, va="top", fontsize=8.5, color=th.muted, zorder=6))

    def legend_swatch(self, x_sw: float, color: Any, striped: bool, hatch_edge: Any) -> Any:
        return super().legend_swatch(x_sw, self._cmap(0.8), striped, hatch_edge)

    def _values(self, x: float) -> np.ndarray:
        i0 = int(math.floor(x))
        i0 = min(max(i0, 0), self._n_days - 1)
        i1 = min(i0 + 1, self._n_days - 1)
        a = x - i0
        return self._cum[i0] * (1 - a) + self._cum[i1] * a

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        ax, th, top_n = self.ax, self.theme, self.top_n
        values = self._values(float(frame["x"]))
        matched = self._owner_arr[self._owner_arr >= 0]
        vmax = float(values[matched].max()) if len(matched) else 0.0
        vmax = vmax if vmax > 0 else 1.0
        current = frame.get("current") if highlight_current else None
        faces, edges, widths = [], [], []
        for owner, name in zip(self._owner, self._names):
            value = float(values[owner]) if owner >= 0 else 0.0
            share = (math.log1p(value) / math.log1p(vmax) if self.log else value / vmax) if value > 0 else 0.0   # גל 49: צבע לוגריתמי; ב13: שלילי - בלי צבע
            faces.append(self._cmap(0.12 + 0.88 * min(share, 1.0)) if value > 0 else th.grid)
            is_current = current is not None and owner >= 0 and name == str(current)
            edges.append(th.accent if is_current else th.bg)
            widths.append(2.2 if is_current else 0.6)
        self._polys.set_facecolor(faces)
        self._polys.set_edgecolor(edges)
        self._polys.set_linewidth(widths)

        entities = self.ctx["entities"]
        order = [int(i) for i in np.argsort(-values, kind="stable") if values[int(i)] > 0][:top_n]
        self.draw_map_labels(values, order)
        self.draw_legend_values(vmax)
        step = min(0.085, 0.86 / max(top_n, 1))
        for rank, column in enumerate(order):
            entity = entities[column]
            is_current = current is not None and entity == current
            y = 0.95 - step * rank
            self.dyn(ax.text(LIST_X, y, f"{rank + 1}.", transform=ax.transAxes, ha="left", va="center", fontsize=11,
                             color=th.muted, zorder=5))
            self.dyn(ax.text(LIST_X + 0.04, y, str(entity), transform=ax.transAxes, ha="left", va="center", fontsize=12,
                             color=th.accent if is_current else th.ink, fontweight="bold" if is_current or rank == 0 else "normal", zorder=5))
            self.dyn(ax.text(0.985, y, self.fmt(values[column]), transform=ax.transAxes, ha="right", va="center", fontsize=12,
                             color=th.ink, fontweight="bold" if rank == 0 else "normal", zorder=5))
