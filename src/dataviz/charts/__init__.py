# dataviz/charts/__init__.py
#
# רישום סוגי התרשימים. כולם מקבלים את אותה תכנית (plan.py) ואת אותו הקשר (ctx) -
# סוג חדש = מודול עם מחלקה שיורשת מ-BaseChart ושורה אחת כאן.

import importlib
from typing import Any, Dict, Mapping, Tuple

CHART_MODULES: Dict[str, Tuple[str, str]] = {
    "bar_race": ("dataviz.charts.bar_race", "BarRace"),
    "line_race": ("dataviz.charts.line_race", "LineRace"),
    "stacked_area_race": ("dataviz.charts.stacked_area_race", "StackedAreaRace"),
    "scatter_race": ("dataviz.charts.scatter_race", "ScatterRace"),
    "bump_race": ("dataviz.charts.bump_race", "BumpRace"),
    "heatmap_race": ("dataviz.charts.heatmap_race", "HeatmapRace"),
    "map_race": ("dataviz.charts.map_race", "MapRace"),   # גל 42: צריך map.geojson
    "pie_race": ("dataviz.charts.pie_race", "PieRace"),   # גל 51
    "small_multiples": ("dataviz.charts.small_multiples", "SmallMultiples"),   # 20.10.2026
}

# גל 42: שם והסבר קצר לכל סוג - למדריך המנוע (help.py) ולמסך
CHART_INFO: Dict[str, Tuple[str, str]] = {
    "bar_race": ("מרוץ עמודות", "העמודות מתחלפות במקומות ככל שהסכום המצטבר גדל - הקלאסי."),
    "line_race": ("מרוץ קווים", "קו לכל ישות לאורך הזמן, עם השם והערך בקצה הקו."),
    "stacked_area_race": ("שטח מוערם", "כמה כל ישות תורמת לסכום הכולל לאורך הזמן."),
    "scatter_race": ("פיזור", "מצטבר מול מה שנוסף בימים האחרונים - מי גדל עכשיו ומי כבר גדול."),
    "bump_race": ("גרף דירוגים", "המקום בדירוג לאורך הזמן - מי עלה ומי ירד."),
    "heatmap_race": ("מפת חום", "שורה לכל ישות וצבע לכל יום - מי הובילה ומתי, במבט אחד."),
    "map_race": ("מפה", "כל אזור בקובץ GeoJSON נצבע לפי הערך של הישות באותו שם, עם הדירוג לצד המפה."),
    "pie_race": ("עוגה", "הנתח של כל ישות מהסכום הכולל ברגע הנוכחי - טבעת שמתחלפת, והשאר ב\"אחרים\"."),
    "small_multiples": ("גרפים קטנים", "גרף קו קטן לכל ישות, כל אחד עם ציר משלו וזמן משותף - לסדרות ביחידות שונות (טמפרטורה ומפלס)."),
}


def chart_class(name: str) -> Any:
    if name not in CHART_MODULES:
        raise ValueError(f"סוג תרשים לא מוכר: {name!r} (קיימים: {', '.join(CHART_MODULES)})")
    module, cls = CHART_MODULES[name]
    return getattr(importlib.import_module(module), cls)


def make_chart(ctx: Mapping[str, Any]) -> Any:
    return chart_class(ctx["chart"])(ctx)
