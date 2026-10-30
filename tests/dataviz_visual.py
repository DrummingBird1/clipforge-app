# tests/dataviz_visual.py
#
# גל 54: בדיקת רגרסיה חזותית לסרטוני הנתונים - פריים קטן מכל סוג תרשים (ועוד כמה עם התוספות של גלים 49-51)
# מול תמונות "זהב" ב-tests/data/dataviz_golden. הגופן קבוע (DejaVu Sans - מגיע עם matplotlib, כך שהציור לא תלוי
# במחשב), והפרק סינתטי (tests/dataviz_helpers.py). שינוי מכוון בציור: לכתוב מחדש את התמונות עם
#     uv run python -m tests.dataviz_visual --write
# ולבדוק בעין את מה שהשתנה (git diff של קבצי ה-PNG).
import json
import os
import sys
import tempfile
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))   # כשמריצים עם -m, בלי pytest

import numpy as np

from tests.dataviz_helpers import write_episode

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dataviz_golden")
BASE = {"video": {"width": 320, "height": 200, "fps": 10, "dpi": 40}, "theme_overrides": {"fonts": ["DejaVu Sans"]}}
GEO = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"name": str(y)}, "geometry": {"type": "Polygon", "coordinates": [[[34 + i, 31], [35 + i, 31], [35 + i, 32], [34 + i, 32], [34 + i, 31]]]}}
    for i, y in enumerate((2019, 2020, 2021, 2023))]}

# (שם, הגדרות נוספות, איזה פריים: מספר בין 0 ל-1 לאורך התכנית)
SCENARIOS: List[Dict[str, Any]] = [
    {"name": chart, "config": {"chart": chart}, "at": 0.6}
    for chart in ("bar_race", "line_race", "stacked_area_race", "scatter_race", "bump_race", "heatmap_race", "pie_race", "small_multiples")
] + [
    {"name": "map_race", "config": {"chart": "map_race", "map": {"geojson": "regions.geojson", "legend": True, "labels": "top"}}, "at": 0.6},
    {"name": "bar_numbers", "config": {"numbers": {"style": "compact", "decimals": 1, "prefix": "$"}, "ranking": {"top_n": 3, "log_scale": True},
                                       "labels": {"rank_arrows": True, "gains": True, "gains_min": 0.0}}, "at": 0.85},
    {"name": "bar_dark_style", "config": {"theme": "dark", "style": {"bar_height": 0.5, "grid": False, "title_size": 26}}, "at": 0.6},
    # 20.10.2026: ציר y שני - המקור היומי על הציר הימני
    {"name": "line_dual_axis", "config": {"chart": "line_race", "y_axes": {"left": {"label": "שנתי"}, "right": {"label": "יומי", "numbers": {"suffix": "!"}}},
                                          "sources": "DUAL"}, "at": 0.6},
    # 20.10.2026: הערה על הגרף - חץ וטקסט בנקודה (תאריך + ערך)
    {"name": "line_annotation", "config": {"chart": "line_race", "story": {"annotations": [
        {"date": "2021-01-01", "value": 300, "text": "כאן", "dx": -40, "dy": 30, "style": "accent"}]}}, "at": 0.6},
    {"name": "bar_outro", "config": {"outro": {"title": "המובילות", "places": ["ראשון", "שני"], "credits": ["מקור: בדיקה"]}}, "at": 1.0},
]


def render_scenario(scenario: Dict[str, Any], tmp: str) -> np.ndarray:
    """הפריים של התרחיש כמערך RGB."""
    from dataviz.charts import make_chart
    from dataviz.episode import load_episode
    from dataviz.plan import build_plan
    from dataviz.render import chart_context
    config = {**BASE, **scenario["config"]}
    if config.get("sources") == "DUAL":
        from tests.dataviz_helpers import write_episode as _plain_episode
        with tempfile.TemporaryDirectory() as probe:
            import yaml
            sources = yaml.safe_load(open(os.path.join(_plain_episode(probe), "config.yaml"), encoding="utf-8"))["sources"]
        sources[1]["axis"] = "right"
        config["sources"] = sources
    folder = write_episode(tmp, overrides=config, name=scenario["name"])
    if config.get("chart") == "map_race":
        with open(os.path.join(folder, "regions.geojson"), "w", encoding="utf-8") as f:
            json.dump(GEO, f)
    episode = load_episode(folder)
    plan = build_plan(episode, "full")
    chart = make_chart(chart_context(episode))
    try:
        rgba = chart.render(plan[int(round(scenario["at"] * (len(plan) - 1)))])
        width, height = chart.size
    finally:
        chart.close()
    return np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)[:, :, :3].copy()


def golden_path(name: str) -> str:
    return os.path.join(GOLDEN_DIR, f"{name}.png")


def write_all() -> None:
    from PIL import Image
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dataviz_visual_") as tmp:
        for scenario in SCENARIOS:
            Image.fromarray(render_scenario(scenario, tmp)).save(golden_path(scenario["name"]), optimize=True)
    print(f"wrote {len(SCENARIOS)} images to {GOLDEN_DIR}")


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_all()
