# dataviz/looks.py
#
# גל 51: "מראות מוכנים" - כל מראה הוא קבוצת הגדרות (סגנון, צבעי הערכה, פורמט מספרים, חיצים ו-"+N") שמוחלת יחד
# בלחיצה בלשונית הצבעים. המסך מחיל אותן כטיוטה (התצוגה החיה מתעדכנת) ו"שמור" כותב אותן לקובץ השינויים - כמו כל שינוי.
# הגדרה שמראה אחר משנה ומראה זה לא - חוזרת לקובץ הפרק / לברירת המחדל, כך שמעבר בין מראות לא משאיר שאריות.

from typing import Any, Dict, List, Tuple

from dataviz.i18n_en import tr

VIVID = ["#ff5a5f", "#ffb400", "#00a699", "#7b61ff", "#fc642d", "#00d1c1", "#e84393", "#4fb3ff", "#9bdc28", "#ff8ad8"]

LOOKS: Tuple[Dict[str, Any], ...] = (
    {"id": "minimal", "title": "מינימלי", "about": "בלי רשת ובלי השנה ברקע, עמודות דקות ומספרים מקוצרים.",
     "set": {"style.grid": False, "style.year_mark": False, "style.bar_height": 0.55, "style.title_size": 20,
             "numbers.style": "compact", "numbers.decimals": 1}},
    {"id": "news", "title": "חדשותי", "about": "אדום של חדשות, כותרת גדולה, חיצי דירוג ו-\"+N\" ליד קפיצות.",
     "set": {"style.bar_height": 0.78, "style.title_size": 25, "theme_overrides.accent": "#c8102e",
             "labels.rank_arrows": True, "labels.gains": True}},
    {"id": "bold", "title": "בולט", "about": "רקע כהה, צבעים חזקים, עמודות עבות וכותרת ענקית.",
     "set": {"theme": "dark", "style.grid": False, "style.bar_height": 0.86, "style.title_size": 28,
             "theme_overrides.accent": "#ffcc00", "theme_overrides.categorical": VIVID}},
)


def all_paths() -> List[str]:
    """כל ההגדרות שמראה כלשהו משנה - מה שמראה אחר לא קובע חוזר לקובץ."""
    return sorted({path for look in LOOKS for path in look["set"]})


def looks(lang: str = "he") -> List[Dict[str, Any]]:
    return [{"id": look["id"], "title": tr(str(look["title"]), lang), "about": tr(str(look["about"]), lang), "set": dict(look["set"])}
            for look in LOOKS]
