# dataviz/schema.py
#
# גל 39: סכימה אחת להגדרות פרק (config.yaml). רשימה הצהרתית של השדות שאפשר לערוך מהדפדפן - נתיב,
# טיפוס, טווח, קבוצה, תווית והסבר בעברית - שממנה נגזרים הטופס במסך, הבדיקה של כל ערך שמגיע
# מהדפדפן, ו-JSON Schema אמיתי של config.yaml (GET /api/dataviz/config_schema) לכלים חיצוניים.
# ברירות המחדל עצמן נשארות ב-DEFAULTS (config.py) - הטסט בודק שכל נתיב כאן קיים שם.

from typing import Any, Dict, List, Mapping, Optional, Tuple

from dataviz.config import DEFAULTS, RECORD_RULES

GROUPS: Tuple[Tuple[str, str, str], ...] = (
    # גל 59: מה שהיה בטופס "הגדרות הפרק (עריכה)" הנפרד - עכשיו בראש העורך המלא, טופס אחד לכל ההגדרות
    ("basic", "⭐ בסיסי", "הכותרת, סוג התרשים, ערכת הצבעים, כמה מקומות מוצגים וטקסטי הפרסום - מה שמשנים הכי הרבה."),
    ("texts", "📝 טקסטים", "הפתיח, הסיום, התוויות וההערות - הכל עם תצוגה חיה."),
    ("pacing", "⏱ קצב", "כמה מהר הסרטון מתקדם, והאטה סביב אירועים."),
    ("ranking", "📊 דירוג וציר", "כמה חלק הדירוג זז, ואיך הציר גדל ומצטמצם."),
    ("records", "🏆 שיאים", "ההתראה \"שיא חדש\" - מתי היא מופיעה וכמה זמן."),
    ("cards", "🗓️ כרטיסי אירועים", "כמה זמן כרטיס של אירוע נשאר על המסך."),
    ("timeline", "📅 ציר הזמן", "טווח התאריכים, סימוני השנים והישות של התקופה הנוכחית."),
    ("video", "🎬 וידאו", "גודל, קצב פריימים ואיכות הקידוד."),
    ("audio", "🎵 מוזיקה", "מתי המוזיקה מתחילה, כניסה הדרגתית ודעיכה."),
    ("publish", "📦 פרסום", "מה נוצר בחבילת הפרסום אחרי סרטון מלא."),
    ("brand", "🏷️ מיתוג ולוגו", "לוגו קבוע בפינה - בדרך כלל מערכת הערוץ."),
    ("series", "📚 סדרה", "לאיזו סדרה הפרק שייך ומה המספר שלו - לסידור ול\"הפרק הבא\"."),
    ("captions", "💬 כתוביות וקריינות", "קובץ SRT לאירועים ולשיאים, וקול שמקריא כל אירוע כשהכרטיס שלו עולה."),
    ("map", "🗺️ מפה", "לתרשים המפה: קובץ GeoJSON בתיקיית הפרק, והמאפיין שבו שם האזור."),
    ("share", "🖼️ שיתוף", "התמונה וה-GIF הקצר מהרגע החזק בסרטון (מצב \"שיתוף\")."),
    ("numbers", "🔢 מספרים וערכים", "מה מוצג (מצטבר, חלון מתגלגל, לנפש) ואיך כל מספר נכתב."),
    ("style", "🖌️ סגנון ותמונות", "עובי העמודות, רשת, גודל הכותרת, השנה ברקע ותמונות לישויות. \"מראות מוכנים\" בלשונית הצבעים משנים כמה מהם יחד."),
    ("data", "🧹 ניקוי נתונים", "ימים חסרים במקור שמדווח ערך לכל יום. הצעות מיזוג ותיקון קפיצות - בחלון הנתונים, לשונית \"ניקוי\"."),
    ("story", "📖 סיפור", "הפרקים, העצירות, ההערות, התקופות וקטעי המהירות נערכים בלשונית \"📖 סיפור\"; כאן - כמה זמן כל אחד, הטיזר ומסך הסיום."),
)

# (נתיב, טיפוס, קבוצה, תווית, הסבר, אפשרויות): טיפוסים - text, lines (רשימת שורות), int, number, bool, choice, date
# גל 59: סוגי התרשים לבחירה בקבוצה "בסיסי" - טסט מוודא שזו בדיוק הרשימה של dataviz/charts (ייבוא שלהם כאן היה מעגלי)
CHART_CHOICES: Dict[str, str] = {"bar_race": "מרוץ עמודות", "line_race": "מרוץ קווים", "stacked_area_race": "שטח מוערם", "scatter_race": "פיזור", "bump_race": "גרף דירוגים", "heatmap_race": "מפת חום", "map_race": "מפה", "pie_race": "עוגה", "small_multiples": "גרפים קטנים"}

FIELDS: Tuple[Dict[str, Any], ...] = (
    {"path": "title", "type": "text", "group": "basic", "label": "כותרת", "help": "הכותרת של הפרק - בפתיח, בראש הסרטון ובחבילת הפרסום.", "max": 200},
    {"path": "subtitle", "type": "text", "group": "basic", "label": "תת-כותרת", "help": "", "max": 200},
    {"path": "chart", "type": "choice", "group": "basic", "label": "סוג תרשים", "help": "לסוג אחר רק בהרצה אחת - \"סוג תרשים\" ליד ההרצה.",
     "choices": list(CHART_CHOICES), "choice_labels": dict(CHART_CHOICES)},
    {"path": "theme", "type": "choice", "group": "basic", "label": "ערכת צבעים", "help": "", "choices": ["light", "dark"],
     "choice_labels": {"light": "בהיר", "dark": "כהה"}},
    {"path": "ranking.top_n", "type": "int", "group": "basic", "label": "מספר מקומות להצגה", "help": "", "min": 3, "max": 30},
    {"path": "publish.title", "type": "text", "group": "basic", "label": "כותרת לפרסום", "help": "ריק = כותרת הפרק.", "max": 200},
    {"path": "publish.description", "type": "text", "group": "basic", "label": "תיאור לפרסום", "help": "", "max": 2000, "multiline": True},   # סבב הייצוב: בכמה שורות
    {"path": "publish.hashtags", "type": "lines", "group": "basic", "label": "תגיות", "help": "שורה לכל תגית.", "max_items": 30},
    {"path": "intro.title", "type": "text", "group": "texts", "label": "פתיח: כותרת", "help": "הכותרת הגדולה בפתיח. ריק = כותרת הפרק.", "max": 120},
    {"path": "intro.subtitle", "type": "text", "group": "texts", "label": "פתיח: תת-כותרת", "help": "שורה שנייה בפתיח.", "max": 160},
    {"path": "intro.question", "type": "text", "group": "texts", "label": "פתיח: שאלה", "help": "שאלה שמעוררת סקרנות לפני שהמרוץ מתחיל.", "max": 160},
    {"path": "outro.title", "type": "text", "group": "texts", "label": "סיום: כותרת", "help": "הכותרת של תיבת הסיום.", "max": 120},
    {"path": "outro.places", "type": "lines", "group": "texts", "label": "סיום: שמות המקומות", "help": "שורה לכל מקום (ראשון, שני...).", "max_items": 10},
    {"path": "labels.total", "type": "text", "group": "texts", "label": "תווית הסכום", "help": "הטקסט ליד הסכום הכולל בכותרת.", "max": 60},
    {"path": "labels.leader", "type": "text", "group": "texts", "label": "תווית המוביל", "help": "הטקסט ליד מי שמוביל עכשיו.", "max": 60},
    {"path": "labels.record", "type": "text", "group": "texts", "label": "התראת שיא", "help": "{entity} מוחלף בשם הישות.", "max": 80},
    {"path": "labels.date_format", "type": "text", "group": "texts", "label": "תבנית תאריך", "help": "למשל %d/%m/%Y או %m/%Y.", "max": 20},
    {"path": "labels.others", "type": "text", "group": "texts", "label": "עוגה: \"אחרים\"", "help": "השם של הפרוסה שמאחדת את כל מי שמחוץ לדירוג.", "max": 30},
    {"path": "notes", "type": "lines", "group": "texts", "label": "הערות בתחתית", "help": "שורה לכל הערה (מקור, הסבר).", "max_items": 6},
    {"path": "outro.credits", "type": "lines", "group": "texts", "label": "מקורות הנתונים", "help": "שורה לכל מקור - בסוף הסרטון (במקום ההערות) ובתיאור ביוטיוב.", "max_items": 6},
    {"path": "scatter.x_label", "type": "text", "group": "texts", "label": "פיזור: ציר X", "help": "רק בתרשים פיזור.", "max": 60},
    {"path": "scatter.y_label", "type": "text", "group": "texts", "label": "פיזור: ציר Y", "help": "רק בתרשים פיזור.", "max": 60},

    {"path": "timing.step", "type": "number", "group": "pacing", "label": "צעד מקסימלי לפריים", "help": "אף ערך לא מתקדם ביותר מהחלק הזה של הציר בפריים אחד - קטן יותר = סרטון ארוך ואיטי יותר.", "min": 0.0005, "max": 0.1},
    {"path": "timing.base_frames_per_day", "type": "number", "group": "pacing", "label": "פריימים ליום (בסיס)", "help": "הקצב של ימים שקטים.", "min": 0.01, "max": 20},
    {"path": "timing.smooth_window", "type": "int", "group": "pacing", "label": "החלקת הקצב (ימים)", "help": "על כמה ימים מחליקים את הקצב.", "min": 1, "max": 120},
    {"path": "timing.event_slowdown.before_days", "type": "int", "group": "pacing", "label": "האטה: ימים לפני אירוע", "help": "", "min": 0, "max": 365},
    {"path": "timing.event_slowdown.after_days", "type": "int", "group": "pacing", "label": "האטה: ימים אחרי אירוע", "help": "", "min": 0, "max": 365},
    {"path": "timing.event_slowdown.extra", "type": "number", "group": "pacing", "label": "האטה: פי כמה", "help": "כמה פריימים נוספים לכל יום סביב אירוע.", "min": 0, "max": 20},
    {"path": "timing.intro_seconds", "type": "number", "group": "pacing", "label": "אורך הפתיח (שניות)", "help": "", "min": 0, "max": 60},
    {"path": "timing.outro_seconds", "type": "number", "group": "pacing", "label": "אורך הסיום (שניות)", "help": "", "min": 0, "max": 60},
    {"path": "timing.test_main_seconds", "type": "number", "group": "pacing", "label": "סרטון בדיקה: אורך (שניות)", "help": "", "min": 1, "max": 120},
    {"path": "timing.preview_seconds", "type": "number", "group": "pacing", "label": "תצוגה מקדימה: אורך (שניות)", "help": "", "min": 1, "max": 120},

    {"path": "ranking.smoothing", "type": "number", "group": "ranking", "label": "החלקת הדירוג", "help": "כמה מהמרחק ליעד עוברים בכל פריים (0-1). קטן = תזוזה רכה יותר.", "min": 0.005, "max": 1},
    {"path": "ranking.axis_min", "type": "number", "group": "ranking", "label": "מינימום לציר", "help": "הציר לא קטן מהערך הזה.", "min": 0.0001, "max": 1e12},
    {"path": "ranking.axis_headroom", "type": "number", "group": "ranking", "label": "מרווח מעל המוביל", "help": "הציר = המוביל כפול המספר הזה.", "min": 1, "max": 3},
    {"path": "ranking.axis_rise", "type": "number", "group": "ranking", "label": "מהירות עליית הציר", "help": "", "min": 0.001, "max": 1},
    {"path": "ranking.axis_fall", "type": "number", "group": "ranking", "label": "מהירות ירידת הציר", "help": "", "min": 0.001, "max": 1},
    {"path": "y_axes.left.label", "type": "text", "group": "ranking", "label": "ציר שמאלי: כותרת", "help": "מעל הציר. ציר ימני - למקור עם \"ציר: ימין\" במיפוי (מרוץ קווים).", "max": 60},
    {"path": "y_axes.right.label", "type": "text", "group": "ranking", "label": "ציר ימני: כותרת", "help": "לסדרה ביחידות אחרות (מפלס מול טמפרטורה) - הציר מופיע רק כשיש מקור על הצד הימני.", "max": 60},
    {"path": "ranking.log_scale", "type": "bool", "group": "ranking", "label": "ציר לוגריתמי", "help": "כשהערכים רחוקים מאוד זה מזה. בעמודות, בקווים, בפיזור, במפת החום ובמפה."},
    {"path": "labels.rank_arrows", "type": "bool", "group": "ranking", "label": "חיצי שינוי מקום ▲▼", "help": "ליד ישות שעלתה או ירדה בדירוג (בעמודות ובקווים)."},
    {"path": "labels.rank_window_days", "type": "int", "group": "ranking", "label": "חיצים: לעומת כמה ימים אחורה", "help": "", "min": 1, "max": 365},
    {"path": "labels.gains", "type": "bool", "group": "ranking", "label": "תווית \"+N\" ליד קפיצה", "help": "כמה נוסף ביום שמונפש עכשיו, ליד עמודה (או קו) שקפצה."},
    {"path": "labels.gains_min", "type": "number", "group": "ranking", "label": "+N: קפיצה מינימלית", "help": "חלק מהציר - קפיצה קטנה מזה לא מקבלת תווית.", "min": 0, "max": 1},

    {"path": "records.enabled", "type": "bool", "group": "records", "label": "להציג \"שיא חדש\"", "help": ""},
    {"path": "records.when", "type": "choice", "group": "records", "label": "מתי זה שיא", "help": "", "choices": list(RECORD_RULES),
     "choice_labels": {"current_takes_lead": "כשהתקופה הנוכחית עוקפת", "lead_change": "בכל החלפת מוביל"}},
    {"path": "records.min_value", "type": "number", "group": "records", "label": "ערך מינימלי לשיא", "help": "", "min": 0, "max": 1e12},
    {"path": "records.cooldown_frames", "type": "int", "group": "records", "label": "פריימים בין שיאים", "help": "", "min": 0, "max": 10000},
    {"path": "records.duration_frames", "type": "int", "group": "records", "label": "משך ההתראה (פריימים)", "help": "", "min": 1, "max": 10000},

    {"path": "cards.min_frames", "type": "int", "group": "cards", "label": "משך מינימלי (פריימים)", "help": "", "min": 1, "max": 10000},
    {"path": "cards.max_frames", "type": "int", "group": "cards", "label": "משך מקסימלי (פריימים)", "help": "", "min": 1, "max": 10000},
    {"path": "cards.gap_frames", "type": "int", "group": "cards", "label": "רווח בין כרטיסים (פריימים)", "help": "", "min": 0, "max": 10000},

    {"path": "timeline.start", "type": "date", "group": "timeline", "label": "מתחיל ב-", "help": "ריק = מהיום הראשון בנתונים."},
    {"path": "timeline.end", "type": "date", "group": "timeline", "label": "מסתיים ב-", "help": "ריק = עד היום האחרון בנתונים."},
    {"path": "timeline.tick_years", "type": "int", "group": "timeline", "label": "סימון כל כמה שנים", "help": "", "min": 1, "max": 100},
    {"path": "current_entity", "type": "choice", "group": "timeline", "label": "הישות של התקופה הנוכחית", "help": "השנה שמוצגת עכשיו מודגשת ותמיד בתמונה.",
     "choices": ["auto", "year", "none"], "choice_labels": {"auto": "אוטומטי", "year": "השנה", "none": "בלי"}},

    {"path": "video.width", "type": "int", "group": "video", "label": "רוחב", "help": "מספר זוגי.", "min": 160, "max": 3840, "even": True},
    {"path": "video.height", "type": "int", "group": "video", "label": "גובה", "help": "מספר זוגי.", "min": 160, "max": 3840, "even": True},
    {"path": "video.fps", "type": "int", "group": "video", "label": "פריימים בשנייה", "help": "", "min": 10, "max": 120},
    {"path": "video.dpi", "type": "int", "group": "video", "label": "DPI", "help": "גודל הטקסט ביחס לפריים.", "min": 20, "max": 400},
    {"path": "video.crf", "type": "int", "group": "video", "label": "איכות (CRF)", "help": "נמוך = איכותי יותר.", "min": 0, "max": 40},
    {"path": "video.preset", "type": "choice", "group": "video", "label": "מהירות קידוד", "help": "",
     "choices": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]},
    {"path": "video.encoder", "type": "choice", "group": "video", "label": "קידוד", "help": "בכרטיס מסך של NVIDIA (NVENC) הרינדור המלא מהיר יותר; אם הקידוד בכרטיס נכשל - הסרטון נוצר שוב במעבד.",
     "choices": ["cpu", "nvenc", "auto"], "choice_labels": {"cpu": "מעבד (x264)", "nvenc": "כרטיס מסך (NVENC)", "auto": "אוטומטי - כרטיס מסך אם יש"}},
    {"path": "video.priority", "type": "choice", "group": "video", "label": "עדיפות הרינדור", "help": "נמוכה - המחשב נשאר זמין לגלישה ולצפייה בזמן הרינדור (הרינדור קצת יותר איטי כשמשתמשים במחשב).",
     "choices": ["low", "normal"], "choice_labels": {"low": "נמוכה - המחשב נשאר זמין", "normal": "רגילה - הכי מהר"}},
    {"path": "video.output_name", "type": "text", "group": "video", "label": "שם הקובץ", "help": "ריק = שם הפרק.", "max": 60, "pattern": "name"},

    {"path": "audio.start", "type": "number", "group": "audio", "label": "מתחילה מהשנייה", "help": "", "min": 0, "max": 36000},
    {"path": "audio.fade_in", "type": "number", "group": "audio", "label": "כניסה הדרגתית (שניות)", "help": "", "min": 0, "max": 60},
    {"path": "audio.fade_out", "type": "number", "group": "audio", "label": "דעיכה בסוף (שניות)", "help": "", "min": 0, "max": 60},

    {"path": "publish.seo_ai", "type": "bool", "group": "publish", "label": "SEO מ-Gemini", "help": "כותרת ותיאור מהפריימים (צריך מפתח Gemini)."},
    {"path": "publish.thumbnail", "type": "bool", "group": "publish", "label": "תמונה ממוזערת", "help": ""},
    {"path": "publish.chapters", "type": "bool", "group": "publish", "label": "פרקים ביוטיוב", "help": "חותמות זמן בתיאור - הפתיח, כל פרק של הסיפור וכל כרטיס אירוע (לפחות 3, כל אחד 10 שניות ומעלה)."},
    {"path": "publish.approval", "type": "bool", "group": "publish", "label": "קובץ אישור", "help": "החבילה ממתינה לאישור לפני שליחה."},

    {"path": "logo.path", "type": "text", "group": "brand", "label": "קובץ הלוגו", "help": "נתיב לתמונה (PNG שקוף מומלץ). ריק = בלי לוגו.", "max": 400},
    {"path": "logo.position", "type": "choice", "group": "brand", "label": "פינה", "help": "",
     "choices": ["bottom-right", "bottom-left", "top-right", "top-left"],
     "choice_labels": {"bottom-right": "למטה מימין", "bottom-left": "למטה משמאל", "top-right": "למעלה מימין", "top-left": "למעלה משמאל"}},
    {"path": "logo.scale", "type": "number", "group": "brand", "label": "גודל (חלק מהרוחב)", "help": "", "min": 0.02, "max": 0.3},
    {"path": "logo.opacity", "type": "number", "group": "brand", "label": "אטימות", "help": "", "min": 0.1, "max": 1},
    {"path": "bumpers.intro", "type": "text", "group": "brand", "label": "אינטרו מקליפ", "help": "קליפ של הערוץ לפני הסרטון (נתיב, יחסי לתיקיית הפרק או מלא). ריק = בלי.", "max": 400},
    {"path": "bumpers.outro", "type": "text", "group": "brand", "label": "אאוטרו מקליפ", "help": "קליפ של הערוץ אחרי הסרטון. ריק = בלי.", "max": 400},

    {"path": "series.name", "type": "text", "group": "series", "label": "שם הסדרה", "help": "", "max": 60},
    {"path": "series.number", "type": "int", "group": "series", "label": "מספר הפרק", "help": "", "min": 0, "max": 9999},

    {"path": "captions.enabled", "type": "bool", "group": "captions", "label": "כתוביות SRT ליד הסרטון", "help": "קובץ <שם>.srt עם האירועים והשיאים בזמנים של הסרטון."},
    {"path": "captions.events", "type": "bool", "group": "captions", "label": "כתוביות: אירועים", "help": ""},
    {"path": "captions.records", "type": "bool", "group": "captions", "label": "כתוביות: \"שיא חדש\"", "help": ""},
    {"path": "captions.intro", "type": "bool", "group": "captions", "label": "כתוביות: הפתיח", "help": "הכותרת והשאלה של הפתיח."},
    {"path": "narration.enabled", "type": "bool", "group": "captions", "label": "קריינות", "help": "קול של Windows מקריא כל אירוע (בסרטון מלא ובבדיקה)."},
    {"path": "narration.voice", "type": "text", "group": "captions", "label": "קול", "help": "שם קול של Windows (הרשימה ב\"מדריך\"). ריק = ברירת המחדל.", "max": 120},
    {"path": "narration.rate", "type": "int", "group": "captions", "label": "מהירות הדיבור", "help": "0 = רגיל.", "min": -10, "max": 10},
    {"path": "narration.volume", "type": "number", "group": "captions", "label": "עוצמת הקריינות", "help": "1 = כמו שהיא, מעל המוזיקה.", "min": 0.1, "max": 3},
    {"path": "narration.events", "type": "bool", "group": "captions", "label": "קריינות: אירועים", "help": ""},
    {"path": "narration.records", "type": "bool", "group": "captions", "label": "קריינות: \"שיא חדש\"", "help": ""},
    {"path": "narration.tts", "type": "bool", "group": "captions", "label": "קול של Windows לאירוע בלי הקלטה", "help": "כבוי = רק אירועים שהוקלטו מוקראים."},
    {"path": "narration.folder", "type": "text", "group": "captions", "label": "תיקיית ההקלטות", "help": "נקבעת לבד כשמקליטים בלשונית \"קריינות\". שם קובץ = התאריך של האירוע.", "max": 400},
    {"path": "narration.track", "type": "text", "group": "captions", "label": "הקלטה רציפה", "help": "נקבעת לבד כשמקליטים \"🎙 הקלטה רציפה\" מעל התצוגה. ריק = בלי.", "max": 120},
    {"path": "narration.track_start", "type": "number", "group": "captions", "label": "הקלטה רציפה: מתחילה בשנייה", "help": "הזמן בסרטון שבו ההקלטה מתחילה.", "min": 0, "max": 36000},

    {"path": "map.geojson", "type": "text", "group": "map", "label": "קובץ המפה (GeoJSON)", "help": "שם קובץ בתיקיית הפרק, למשל regions.geojson.", "max": 400},
    {"path": "map.key", "type": "text", "group": "map", "label": "המאפיין עם שם האזור", "help": "השם באזור צריך להיות זהה לשם הישות.", "max": 60},
    {"path": "map.projection", "type": "choice", "group": "map", "label": "הטלה", "help": "mercator - כמו מפות ברשת; equirect - פשוטה (קווי הרוחב ישרים).",
     "choices": ["mercator", "equirect"], "choice_labels": {"mercator": "מרקטור", "equirect": "פשוטה"}},

    {"path": "share.gif_seconds", "type": "number", "group": "share", "label": "אורך ה-GIF (שניות)", "help": "", "min": 1, "max": 10},
    {"path": "map.legend", "type": "bool", "group": "map", "label": "סקאלת צבעים", "help": "מה הצבע החזק והחלש שווים, בפינה של המפה."},
    {"path": "map.labels", "type": "choice", "group": "map", "label": "שמות על המפה", "help": "",
     "choices": ["none", "top", "all"], "choice_labels": {"none": "בלי", "top": "רק של המובילים", "all": "כל אזור עם ערך"}},
    {"path": "share.gif_fps", "type": "int", "group": "share", "label": "פריימים לשנייה ב-GIF", "help": "", "min": 4, "max": 30},
    {"path": "share.gif_scale", "type": "number", "group": "share", "label": "גודל ה-GIF (חלק מהסרטון)", "help": "", "min": 0.2, "max": 1},
    {"path": "shorts.count", "type": "int", "group": "share", "label": "Shorts אוטומטיים: כמה", "help": "הרגעים הדרמטיים (מצב \"Shorts\") - כל אחד סרטון קצר לאורך.", "min": 1, "max": 5},
    {"path": "shorts.seconds", "type": "number", "group": "share", "label": "Shorts: כמה שניות כל אחד", "help": "", "min": 8, "max": 60},
    {"path": "shorts.cta", "type": "text", "group": "share", "label": "Shorts: הזמנה בסוף", "help": "על הפריים האחרון, למשל \"הסרטון המלא בערוץ\".", "max": 60},

    {"path": "values.mode", "type": "choice", "group": "numbers", "label": "מה מוצג", "help": "מצטבר מההתחלה, או רק מה שנוסף בימים האחרונים (הערכים גם יורדים).",
     "choices": ["cumulative", "rolling"], "choice_labels": {"cumulative": "מצטבר", "rolling": "חלון מתגלגל"}},
    {"path": "values.window_days", "type": "int", "group": "numbers", "label": "חלון מתגלגל: כמה ימים", "help": "", "min": 1, "max": 3650},
    {"path": "values.per_capita.enabled", "type": "bool", "group": "numbers", "label": "לנפש (לפי אוכלוסייה)", "help": "כל ערך מחולק באוכלוסייה של הישות. ישות בלי אוכלוסייה לא מוצגת; כדאי להקטין גם את \"מינימום לציר\"."},
    {"path": "values.per_capita.file", "type": "text", "group": "numbers", "label": "קובץ האוכלוסייה", "help": "CSV בתיקיית הפרק עם העמודות entity,population (או שתי העמודות הראשונות).", "max": 400},
    {"path": "values.per_capita.per", "type": "number", "group": "numbers", "label": "לכל כמה תושבים", "help": "", "min": 1, "max": 1e9},
    {"path": "numbers.style", "type": "choice", "group": "numbers", "label": "תצוגת מספרים", "help": "",
     "choices": ["plain", "compact", "words"], "choice_labels": {"plain": "מלא (1,234,567)", "compact": "מקוצר (1.2M)", "words": "במילים (1.2 מיליון)"}},
    {"path": "numbers.decimals", "type": "int", "group": "numbers", "label": "ספרות אחרי הנקודה", "help": "", "min": 0, "max": 4},
    {"path": "numbers.prefix", "type": "text", "group": "numbers", "label": "לפני המספר", "help": "למשל ₪ או $.", "max": 12},
    {"path": "numbers.suffix", "type": "text", "group": "numbers", "label": "אחרי המספר", "help": "למשל % או ק\"מ.", "max": 12},
    {"path": "numbers.thousands", "type": "bool", "group": "numbers", "label": "פסיק בין אלפים", "help": ""},

    {"path": "style.bar_height", "type": "number", "group": "style", "label": "עובי העמודות", "help": "חלק מהשורה (0.7 = כמו בסרטון הראשון).", "min": 0.2, "max": 0.95},
    {"path": "style.grid", "type": "bool", "group": "style", "label": "קווי רשת", "help": ""},
    {"path": "style.title_size", "type": "int", "group": "style", "label": "גודל הכותרת", "help": "", "min": 10, "max": 48},
    {"path": "style.year_mark", "type": "bool", "group": "style", "label": "השנה הגדולה ברקע", "help": ""},
    {"path": "focus.dim", "type": "number", "group": "style", "label": "פוקוס: כמה לעמעם את השאר", "help": "0.25 = רבע. הישויות בפוקוס - בלשונית הישויות (\"בפוקוס\"); החלפה בתאריך - בלשונית הסיפור.", "min": 0.05, "max": 1},
    {"path": "images.folder", "type": "text", "group": "style", "label": "תיקיית התמונות", "help": "נקבעת לבד כשמעלים תמונה בלשונית הישויות. אפשר גם תיקייה בפרק עם קובץ בשם של כל ישות (png / jpg).", "max": 400},
    {"path": "images.shape", "type": "choice", "group": "style", "label": "צורת התמונה", "help": "",
     "choices": ["circle", "square", "original"], "choice_labels": {"circle": "עיגול", "square": "ריבוע", "original": "כמו שהיא"}},
    {"path": "images.size", "type": "number", "group": "style", "label": "גודל התמונה", "help": "1 = בגובה העמודה.", "min": 0.3, "max": 3},
    {"path": "images.flags", "type": "bool", "group": "style", "label": "דגלים למדינות", "help": "ישות שהיא מדינה (בעברית או באנגלית) מקבלת את הדגל שלה, כשאין לה תמונה משלה. את הדגלים מורידים פעם אחת בלשונית הישויות."},
    {"path": "data.missing", "type": "choice", "group": "data", "label": "יום חסר במקור יומי", "help": "לנתונים שבהם כל שורה היא ערך של יום (ולא מופע). מקור יכול לקבוע missing משלו.",
     "choices": ["zero", "previous", "interpolate"], "choice_labels": {"zero": "אפס (כמו שהוא)", "previous": "הערך של היום הקודם", "interpolate": "קו ישר בין הימים שסביבו"}},
    {"path": "story.chapter_seconds", "type": "number", "group": "story", "label": "פרק: כמה שניות כרטיס הכותרת", "help": "", "min": 0.5, "max": 30},
    {"path": "story.chapter_transition", "type": "choice", "group": "story", "label": "פרק: איך הכרטיס נכנס", "help": "המעבר של כרטיס הכותרת פנימה והחוצה.",
     "choices": ["fade", "slide", "zoom", "wipe"], "choice_labels": {"fade": "דהייה", "slide": "החלקה מלמטה", "zoom": "התקרבות", "wipe": "מחיקה מהצד"}},
    {"path": "story.pause_seconds", "type": "number", "group": "story", "label": "עצירה: כמה שניות", "help": "לעצירה בלי משך משלה.", "min": 0.5, "max": 30},
    {"path": "story.callout_days", "type": "int", "group": "story", "label": "הערה לישות: כמה ימים", "help": "להערה בלי משך משלה (בימי הנתונים).", "min": 1, "max": 3650},
    {"path": "teaser.enabled", "type": "bool", "group": "story", "label": "פתיח \"טיזר\" מהרגע החזק", "help": "כמה שניות מהיום עם התוספת הגדולה ביותר, לפני שהמרוץ מתחיל."},
    {"path": "teaser.seconds", "type": "number", "group": "story", "label": "טיזר: כמה שניות", "help": "", "min": 1, "max": 15},
    {"path": "teaser.label", "type": "text", "group": "story", "label": "טיזר: הכיתוב", "help": "מופיע למעלה בזמן הטיזר.", "max": 40},
    {"path": "end_screen.enabled", "type": "bool", "group": "story", "label": "מסך סיום ליוטיוב (End Screen)", "help": "בשניות האחרונות הגרף מתעמעם, המקומות הראשונים עוברים לפינה, והחצי הימני והפינה התחתונה פנויים לסרטונים ולכפתור ההרשמה."},
    {"path": "end_screen.seconds", "type": "number", "group": "story", "label": "מסך סיום: כמה שניות", "help": "יוטיוב מאפשר 5 עד 20.", "min": 5, "max": 20},
    {"path": "end_screen.text", "type": "text", "group": "story", "label": "מסך סיום: כיתוב", "help": "למשל \"צפו גם בפרק הבא\".", "max": 80},
    {"path": "end_screen.guides", "type": "bool", "group": "story", "label": "מסך סיום: לסמן איפה האלמנטים", "help": "קווים מקווקווים לבדיקה - לכבות לפני הרינדור הסופי."},
)

FIELD_BY_PATH: Dict[str, Dict[str, Any]] = {f["path"]: f for f in FIELDS}


class FieldError(ValueError):
    pass


def default_value(path: str) -> Any:
    node: Any = DEFAULTS
    for key in path.split("."):
        node = node[key]
    return node


def get_path(config: Mapping[str, Any], path: str) -> Tuple[bool, Any]:
    """(קיים?, ערך) של נתיב מקונן במילון."""
    node: Any = config
    for key in path.split("."):
        if not isinstance(node, Mapping) or key not in node:
            return False, None
        node = node[key]
    return True, node


def clean_value(path: str, value: Any) -> Any:
    """ערך שהגיע מהדפדפן לשדה בסכימה - מאומת ומומר לטיפוס הנכון. FieldError כשאינו תקין."""
    field = FIELD_BY_PATH.get(path)
    if field is None:
        raise FieldError(f"שדה לא נתמך: {path}")
    kind, label = field["type"], field["label"]
    if kind == "text":
        if not isinstance(value, str) or len(value) > field.get("max", 200):
            raise FieldError(f"{label}: טקסט עד {field.get('max', 200)} תווים.")
        text = value.strip()
        if field.get("pattern") == "name" and text and not all(c.isalnum() or c in "-_" for c in text):
            raise FieldError(f"{label}: אותיות, ספרות, מקף וקו תחתון בלבד.")
        return text
    if kind == "lines":
        lines = value.splitlines() if isinstance(value, str) else value
        if not isinstance(lines, list) or not all(isinstance(line, str) and len(line) <= 160 for line in lines):
            raise FieldError(f"{label}: שורות טקסט.")
        lines = [line.strip() for line in lines if line.strip()]
        if len(lines) > field.get("max_items", 10):
            raise FieldError(f"{label}: עד {field.get('max_items', 10)} שורות.")
        if path == "outro.places" and not lines:
            raise FieldError(f"{label}: לפחות שורה אחת.")
        return lines
    if kind == "bool":
        if not isinstance(value, bool):
            raise FieldError(f"{label}: כן או לא.")
        return value
    if kind == "choice":
        if value not in field["choices"]:
            raise FieldError(f"{label}: ערך לא מוכר.")
        return value
    if kind == "date":
        text = str(value or "").strip()
        if text:
            import pandas as pd
            try:
                text = pd.Timestamp(text).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                raise FieldError(f"{label}: תאריך לא תקין.") from None
        return text
    # int / number
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value).strip())
        except ValueError:
            raise FieldError(f"{label}: מספר.") from None
    if kind == "int":
        if float(value) != int(value):
            raise FieldError(f"{label}: מספר שלם.")
        value = int(value)
        if field.get("even") and value % 2:
            raise FieldError(f"{label}: מספר זוגי.")
    else:
        value = float(value)
    if not field.get("min", float("-inf")) <= value <= field.get("max", float("inf")):
        raise FieldError(f"{label}: בין {field.get('min')} ל-{field.get('max')}.")
    return value


def nest(path: str, value: Any) -> Dict[str, Any]:
    """'timing.event_slowdown.extra', 3 -> {'timing': {'event_slowdown': {'extra': 3}}}."""
    result: Dict[str, Any] = {}
    node = result
    keys = path.split(".")
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value
    return result


def _localized(field: Mapping[str, Any], lang: str) -> Dict[str, Any]:
    """השדה עם התווית, ההסבר ושמות האפשרויות בשפת הממשק (גל 47)."""
    from dataviz.i18n_en import tr
    out = {k: v for k, v in field.items() if k != "group"}
    out["label"] = tr(field["label"], lang)
    out["help"] = tr(field.get("help") or "", lang)
    if field.get("choice_labels"):
        out["choice_labels"] = {k: tr(v, lang) for k, v in field["choice_labels"].items()}
    return out


def form_groups(config: Mapping[str, Any], file_raw: Mapping[str, Any], overrides: Mapping[str, Any], lang: str = "he") -> List[Dict[str, Any]]:
    """הטופס במסך: קבוצות, ובכל שדה הערך האפקטיבי, ברירת המחדל של המנוע, הערך בקובץ הפרק (אם יש)
    והאם הוא שונה כאן (override)."""
    groups = []
    for key, title, about in GROUPS:
        rows = []
        for field in (f for f in FIELDS if f["group"] == key):
            path = field["path"]
            in_file, file_value = get_path(file_raw, path)
            overridden, _ = get_path(overrides, path)
            rows.append({**_localized(field, lang), "value": get_path(config, path)[1],
                         "default": default_value(path), "file": file_value if in_file else None, "in_file": in_file,
                         "overridden": overridden})
        from dataviz.i18n_en import tr
        groups.append({"id": key, "title": tr(title, lang), "about": tr(about, lang), "fields": rows})
    return groups


_JSON_TYPES = {"text": "string", "lines": "array", "int": "integer", "number": "number", "bool": "boolean", "choice": "string", "date": "string"}


def _json_type(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return None


def json_schema() -> Dict[str, Any]:
    """JSON Schema (draft 2020-12) של config.yaml: המבנה מ-DEFAULTS, ההסברים והטווחים מ-FIELDS."""
    def build(node: Any, prefix: str) -> Dict[str, Any]:
        field = FIELD_BY_PATH.get(prefix)
        schema: Dict[str, Any] = {}
        if field:
            schema["type"] = _JSON_TYPES[field["type"]]
            schema["title"] = field["label"]
            if field.get("help"):
                schema["description"] = field["help"]
            if "min" in field:
                schema["minimum"] = field["min"]
            if "max" in field and field["type"] in ("int", "number"):
                schema["maximum"] = field["max"]
            if field["type"] == "text" and "max" in field:
                schema["maxLength"] = field["max"]
            if field["type"] == "choice":
                schema["enum"] = list(field["choices"])
            if field["type"] == "lines":
                schema["items"] = {"type": "string"}
            if field["type"] == "date":
                schema["format"] = "date"
        elif isinstance(node, Mapping):
            schema["type"] = "object"
            if node:
                schema["properties"] = {k: build(v, f"{prefix}.{k}" if prefix else k) for k, v in node.items()}
        else:
            json_type = _json_type(node)
            if json_type:
                schema["type"] = json_type
        if not isinstance(node, (Mapping, list)):
            schema["default"] = node
        return schema

    root = build(DEFAULTS, "")
    root["properties"]["chart"]["enum"] = sorted(__import__("dataviz.charts", fromlist=["CHART_MODULES"]).CHART_MODULES)
    root["properties"]["theme"]["enum"] = ["light", "dark"]
    root["properties"]["events"] = {"description": "רשימה של {date, label} או שם קובץ CSV עם העמודות date,label.",
                                    "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "object", "required": ["date", "label"]}}]}
    root["properties"]["sources"] = {"type": "array", "description": "מקורות הנתונים - קובץ (path) או כתובת (url) עם מיפוי העמודות.",
                                     "items": {"type": "object", "properties": {"kind": {   # 18.10.2026
                                         "type": "string", "enum": ["amount", "level"], "default": "amount",
                                         "description": "amount - כל שורה מוסיפה לסכום (ברירת המחדל); level - כל ערך הוא רמה (טמפרטורה, מפלס): "
                                                        "הקו מתחיל בערך הראשון, בלי לצבור ובלי לפזר."}}}}
    root["properties"]["colors"] = {"type": "object", "description": "ישות -> צבע #rrggbb.", "additionalProperties": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"}}
    root.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "ClipForge dataviz episode (config.yaml)", "required": ["title", "sources"]})
    return root
