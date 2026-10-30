# dataviz/help.py
#
# גל 42: "מדריך המנוע" במסך עורך הגרפים - כל מה שהמנוע יודע לעשות, במקום אחד ובעברית: סוגי התרשימים,
# מצבי ההרצה, היעדים, כתוביות / קריינות / שיתוף, וכל ההגדרות של config.yaml (נגזרות מהסכימה - הסבר,
# ברירת מחדל וטווח), ושורת הפקודה. נבנה מהקוד עצמו, כך שהמדריך לא מתיישן כשמוסיפים הגדרה.

from typing import Any, Dict, List

from dataviz.charts import CHART_INFO, CHART_MODULES
from dataviz.i18n_en import tr

MODE_INFO = (
    ("stills", "פריימים", "כמה פריימים בודדים (PNG) לבדיקת העיצוב - הכי מהיר."),
    ("preview", "תצוגה מקדימה", "5 שניות בחצי רזולוציה - לראות איך זה זז."),
    ("test", "בדיקה", "סרטון קצר (כ-7 שניות) ברזולוציה מלאה."),
    ("full", "מלא", "הסרטון המלא, עם המוזיקה, הכתוביות, הקריינות וחבילת הפרסום אם הופעלו."),
    ("share", "שיתוף", "תמונה ו-GIF קצר מהרגע החזק בסרטון (היום עם התוספת הגדולה ביותר), בתיקייה <שם>_share."),
    ("shorts", "Shorts אוטומטיים", "הרגעים הדרמטיים של הפרק (הקפיצה הגדולה, החלפת מוביל) כסרטונים קצרים לאורך, בקבצים <שם>_shorts_1.mp4 ואילך."),
)

TARGET_INFO = (
    ("youtube", "YouTube", "כמו בהגדרות הפרק (בדרך כלל 16:9)."),
    ("shorts", "YouTube Shorts", "לאורך 1080x1920, עם פריסה לאורך, בקובץ <שם>_shorts.mp4."),
    ("tiktok", "TikTok", "לאורך 1080x1920, בקובץ <שם>_tiktok.mp4."),
)

EXTRAS = (
    ("כתוביות (SRT)", "captions.enabled (או --captions): קובץ <שם>.srt ליד הסרטון - כרטיס לכל אירוע ו\"שיא חדש\", "
     "בדיוק בזמנים שהם על המסך. אפשר גם להוריד את הקובץ מהמסך בלי לרנדר."),
    ("קריינות", "narration.enabled: קול של Windows מקריא כל אירוע כשהכרטיס שלו עולה (בסרטון מלא ובבדיקה), מעל המוזיקה. "
     "narration.voice = שם קול מהרשימה למטה (ריק = ברירת המחדל של Windows), rate = מהירות (-10 עד 10)."),
    ("מפה", "chart: map_race + map.geojson (קובץ בתיקיית הפרק) + map.key (המאפיין עם שם האזור). אזור נצבע לפי הערך של "
     "הישות באותו שם; ישויות בלי אזור מופיעות רק בדירוג (\"בדיקה\" בחלון הנתונים מראה אותן)."),
    ("ערכת ערוץ ולוגו", "logo.path / position / scale / opacity - לוגו קבוע בפינה. ערכות נשמרות ומוחלות מ\"🏷️ ערכת ערוץ\"."),
    ("סדרה", "series.name / number - תגית על הכרטיס, ו\"הפרק הבא בסדרה\" משכפל עם המספר הבא."),
)

CLI = (
    ("--episode <שם>", "פרק תחת data/dataviz_episodes (או נתיב)."),
    ("--episodes a,b,c", "כמה פרקים בריצה אחת, לפי הסדר."),
    ("--mode full|test|stills|preview|share|shorts", "מה להפיק."),
    ("--lang en|both", "גרסה באנגלית (translations.en), או שתי השפות."),
    ("--chart <סוג>", "סוג תרשים במקום זה שבהגדרות."),
    ("--target youtube|shorts|tiktok", "יעד (לאורך = 1080x1920 בשם קובץ משלו)."),
    ("--captions", "כתוביות SRT גם אם captions כבוי."),
    ("--publish / --no-publish", "חבילת פרסום (תמונה, SEO, אישור) אחרי סרטון מלא."),
    ("--decide approved|rejected --package <נתיב>", "החלטה על חבילת פרסום."),
    ("--workers N", "תהליכי רינדור (ברירת מחדל לפי הליבות)."),
)


def _fmt_default(value: Any, lang: str = "he") -> str:
    if isinstance(value, bool):
        return tr("כן" if value else "לא", lang)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) or "—"
    text = str(value)
    return text if text else "—"


def help_sections(lang: str = "he") -> List[Dict[str, Any]]:
    """[{id, title, items: [{title, text, code?}]}] - הכל טקסט פשוט (המסך מציג, לא מפרש HTML).
    lang="en" (גל 47): כל הטקסטים באנגלית (dataviz/i18n_en.py)."""
    from dataviz.schema import FIELDS, GROUPS, default_value

    def t(text: str) -> str:
        return tr(text, lang)

    charts = [{"title": t(CHART_INFO.get(name, (name, ""))[0]), "code": name, "text": t(CHART_INFO.get(name, ("", ""))[1])}
              for name in CHART_MODULES]
    sections: List[Dict[str, Any]] = [
        {"id": "charts", "title": t("📊 סוגי תרשימים"), "items": charts},
        {"id": "modes", "title": t("▶️ מה להפיק"), "items": [{"title": t(label), "code": key, "text": t(text)} for key, label, text in MODE_INFO]},
        {"id": "targets", "title": t("📱 יעדים"), "items": [{"title": t(label), "code": key, "text": t(text)} for key, label, text in TARGET_INFO]},
        {"id": "extras", "title": t("✨ כתוביות, קריינות, מפה ומיתוג"), "items": [{"title": t(title), "text": t(text)} for title, text in EXTRAS]},
    ]
    for key, title, about in GROUPS:
        items = []
        for field in (f for f in FIELDS if f["group"] == key):
            parts = [t(field.get("help") or "")]
            if "min" in field and field["type"] in ("int", "number"):
                parts.append(t("טווח: {lo} עד {hi}.").format(lo=f"{field['min']:g}", hi=f"{field['max']:g}"))
            if field["type"] == "choice":
                labels = field.get("choice_labels") or {}
                parts.append(t("אפשרויות: {options}.").format(options=", ".join(t(labels.get(c, c)) for c in field["choices"])))
            parts.append(t("ברירת מחדל: {value}.").format(value=_fmt_default(default_value(field["path"]), lang)))
            # גל 45: מה שהמסך צריך כדי להראות "לפני / אחרי" (פריים בברירת המחדל מול ערך אחר)
            meta: Dict[str, Any] = {k: field[k] for k in ("type", "min", "max", "choices") if k in field}
            meta["default"] = default_value(field["path"])
            items.append({"title": t(field["label"]), "code": field["path"], "text": " ".join(p for p in parts if p), "field": meta})
        sections.append({"id": "group-" + key, "title": t(title), "about": t(about), "items": items})
    sections.append({"id": "cli", "title": t("⌨️ שורת הפקודה (dataviz_maker.py)"), "items": [{"title": t(flag), "code": t(flag), "text": t(text)} for flag, text in CLI]})
    return sections
