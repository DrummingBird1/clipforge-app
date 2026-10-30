# dataviz/config.py
#
# הגדרות פרק (config.yaml): ברירות מחדל + ולידציה. ברירות המחדל הן בדיוק הערכים של
# הסרטון הראשון (ירי מעזה, 1440x888 ב-60 פריימים, 10 מובילים, STEP=0.5%), כך שפרק
# חדש צריך לכתוב רק את מה ששונה. כל שגיאה נאספת ומוחזרת יחד (ConfigError.errors),
# כדי לתקן קובץ הגדרות בסבב אחד ולא שגיאה-שגיאה.

import copy
import os
from typing import Any, Dict, List, Mapping

import pandas as pd
import yaml

from dataviz.charts import CHART_MODULES
from dataviz.sources import FILL_MODES, KINDS, MISSING_MODES, PERIODS, READERS, source_type, url_cache_path

CHARTS = tuple(CHART_MODULES)

MODES = ("full", "test", "stills", "preview", "share", "shorts")   # share (גל 42): תמונה ו-GIF מהרגע החזק; shorts (גל 55)
RECORD_RULES = ("current_takes_lead", "lead_change")

DEFAULTS: Dict[str, Any] = {
    "title": "",
    "subtitle": "",
    "chart": "bar_race",
    "theme": "light",
    "theme_overrides": {},
    "video": {"width": 1440, "height": 888, "dpi": 120, "fps": 60, "crf": 18, "preset": "veryfast", "output_name": ""},
    "timing": {
        # קצב: אף עמודה לא מתקדמת ביותר מ-step (חלק מהציר) בפריים אחד
        "step": 0.005,
        "strict_step": True,        # ראו plan.py - false משחזר את הסרטון הראשון פריים-פריים
        "base_frames_per_day": 0.7,
        "smooth_window": 5,
        "event_slowdown": {"before_days": 10, "after_days": 30, "extra": 2.0},
        "intro_seconds": 6,
        "outro_seconds": 10,
        "test_main_seconds": 7,
        "test_intro_seconds": 1,
        "test_outro_seconds": 1,
        "preview_seconds": 5,       # מצב preview: משך הקטע הראשי (ברזולוציה מוקטנת, ראו preview_config)
    },
    "ranking": {
        "top_n": 10,
        "smoothing": 0.07,          # דירוג מוחלק: כמה מהמרחק ליעד עוברים בכל פריים
        "axis_min": 60.0,
        "axis_headroom": 1.13,      # הציר = המוביל x 1.13 (מרווח לתווית הערך)
        "axis_min_headroom": 1.06,  # המוביל אף פעם לא יוצא מהציר
        "axis_rise": 0.05,          # ציר מוחלק: עולה מהר
        "axis_fall": 0.02,          # ויורד לאט
    },
    # "current": הישות של התקופה הנוכחית (שנה = השנה שמוצגת עכשיו) - מודגשת ותמיד בתמונה.
    # auto = year כשכל המקורות מזהים ישות לפי שנת התאריך, אחרת none.
    "current_entity": "auto",
    "records": {"enabled": True, "when": "current_takes_lead", "min_value": 100.0, "cooldown_frames": 240,
                "duration_frames": 150, "fade_in_frames": 15, "fade_out_frames": 25},
    "cards": {"min_frames": 150, "max_frames": 330, "gap_frames": 20, "fade_in_frames": 30, "fade_out_frames": 40},
    "labels": {"date_format": "%d/%m/%Y", "total": "", "leader": "", "record": "שיא חדש: {entity}"},
    "intro": {"title": "", "subtitle": "", "question": ""},
    "outro": {"title": "", "places": ["מקום ראשון", "מקום שני", "מקום שלישי"]},
    "notes": [],
    # scatter_race: X = מצטבר, Y = כמה נוסף ב-window_days הימים האחרונים
    "scatter": {"window_days": 30, "x_label": "מצטבר", "y_label": "ב-30 הימים האחרונים"},
    "timeline": {"tick_years": 5, "start": "", "end": ""},
    "events": [],
    "audio": {"path": "", "start": 0.0, "fade_in": 2.0, "fade_out": 6.0, "bitrate": "192k"},
    # פרסום (אופציונלי, כבוי כברירת מחדל): אחרי רינדור מלא נוצרים תמונה ממוזערת, דף SEO וקובץ אישור
    # (<שם>.publish.json, סטטוס pending_approval) - המנוע עצמו לא מעלה כלום. ראו utils/dataviz_publish.py.
    "publish": {"enabled": False, "title": "", "description": "", "hashtags": [], "seo_ai": False,
                "thumbnail": True, "approval": True},
    "sources": [],
    # גל 39: צבע קבוע לישות (שם הישות כטקסט -> #rrggbb), מעל הפלטה; ריק = לפי הפלטה
    "colors": {},
    # גל 39: שם חלופי לישות (שתי ישויות עם אותו שם חלופי מתמזגות - הסכומים מצטרפים), וישויות שלא מוצגות
    "entities": {"aliases": {}, "exclude": []},
    # גל 41: לוגו בפינה (ערכת ערוץ) - path יחסי לתיקיית הפרק או מלא; ריק = בלי לוגו
    "logo": {"path": "", "position": "bottom-right", "scale": 0.05, "opacity": 0.95},
    # גל 41: שייכות לסדרה (שם ומספר פרק) - לסידור ולשכפול "הפרק הבא"; לא משנה את הרינדור
    "series": {"name": "", "number": 0},
    # גל 42: כתוביות SRT ליד הסרטון - לכל כרטיס אירוע ולכל "שיא חדש", בזמנים של הסרטון (כבוי כברירת מחדל)
    "captions": {"enabled": False, "events": True, "records": True, "intro": False},
    # גל 42: קריינות - קול של Windows (SAPI) מקריא כל אירוע כשהכרטיס שלו עולה, מעל המוזיקה (כבוי כברירת מחדל)
    "narration": {"enabled": False, "voice": "", "rate": 0, "volume": 1.0, "events": True, "records": False,
                  "folder": "", "tts": True,   # גל 45: הקלטות לאירועים (שם קובץ = התאריך), ואם לקרוא בקול של Windows בלעדיהן
                  "track": "", "track_start": 0.0},   # 27.10.2026: הקלטה רציפה אחת (קובץ בתיקיית ההקלטות) מהשנייה track_start
    # גל 42: תרשים מפה (map_race) - קובץ GeoJSON בתיקיית הפרק, והמאפיין שבו שם האזור = שם הישות
    "map": {"geojson": "", "key": "name", "projection": "mercator"},   # גל 45: mercator (כמו מפות רשת) או equirect
    # גל 42: מצב share - תמונה ו-GIF קצר מהרגע החזק בסרטון (היום עם התוספת הגדולה ביותר)
    "share": {"gif_seconds": 3.0, "gif_fps": 12, "gif_scale": 0.5},
    # גל 43: אינטרו / אאוטרו מקליפ של הערוץ (ערכת ערוץ) - מתחברים לסרטון אחרי שהוא נוצר; ריק = בלי
    "bumpers": {"intro": "", "outro": ""},
    # גל 49: מה מוצג - מצטבר מההתחלה, או חלון מתגלגל (סכום window_days הימים האחרונים); ולנפש - חלוקה
    # באוכלוסייה של כל ישות (קובץ CSV בתיקיית הפרק: entity,population, או populations בהגדרות), כפול per
    "values": {"mode": "cumulative", "window_days": 30,
               "per_capita": {"enabled": False, "file": "", "per": 100000, "populations": {}}},
    # גל 49: איך מספר נכתב - plain (1,234,567), compact (1.2M), words (1.2 מיליון); ספרות אחרי הנקודה,
    # קידומת (₪, $) וסיומת (%, ק"מ). ברירת המחדל = בדיוק המספרים של הסרטון הראשון
    "numbers": {"style": "plain", "decimals": 0, "prefix": "", "suffix": "", "thousands": True},
}
# גל 50: הסיפור - פרקים (כרטיס כותרת על פריים קפוא), עצירות עם הסבר, הערה לישות בתאריך, תקופות מוצללות וקטעי
# מהירות; פתיח "טיזר" מהרגע החזק; מסך סיום עם מקום ל-End Screen של יוטיוב; ומקורות הנתונים בסיום
DEFAULTS["story"] = {"chapters": [], "chapter_seconds": 2.5, "pauses": [], "pause_seconds": 3.0,
                     "callouts": [], "callout_days": 30, "periods": [], "speed": [],
                     "annotations": [],   # 20.10.2026: חץ וטקסט בנקודה על הגרף (תאריך + ערך) - בתרשימים עם ציר זמן
                     "focus": [],         # 20.10.2026: מתאריך מסוים הפוקוס עובר לישויות אחרות
                     "script": [],        # 20.10.2026: תסריט קריינות - משפט שהקריינות מקריאה כשהסרטון מגיע לתאריך
                     "chapter_transition": "fade"}   # 27.10.2026: איך כרטיס הפרק נכנס - fade (כמו קודם), slide, zoom, wipe
CHAPTER_TRANSITIONS = ("fade", "slide", "zoom", "wipe")
VIDEO_PRIORITIES = ("low", "normal")
# 20.10.2026: מצב פוקוס - הישויות שברשימה בצבע מלא, השאר מעומעמות (dim). רשימה ריקה = בלי פוקוס, כמו תמיד
DEFAULTS["focus"] = {"entities": [], "dim": 0.25}
DEFAULTS["teaser"] = {"enabled": False, "seconds": 3.0, "label": "עוד רגע..."}
# 20.10.2026: ציר y שני ב-line_race - מקור עם axis: right מצויר על הציר הימני, ולכל ציר כותרת ופורמט מספרים משלו
# (מעל numbers). בלי מקור כזה - ציר אחד בדיוק כמו קודם
DEFAULTS["y_axes"] = {"left": {"label": "", "numbers": {}}, "right": {"label": "", "numbers": {}}}
DEFAULTS["end_screen"] = {"enabled": False, "seconds": 20.0, "text": "", "guides": False}
DEFAULTS["outro"]["credits"] = []
# גל 51: המראה - תמונה לכל ישות (קובץ בשם הישות בתיקייה), סגנון (עובי העמודות, רשת, גודל הכותרת, השנה הגדולה
# ברקע - "מראות מוכנים" משנים אותם), התווית "אחרים" בתרשים העוגה, ומקרא וצבעים ושמות אזורים על המפה
DEFAULTS["images"] = {"folder": "", "shape": "circle", "size": 1.0, "flags": False}   # 27.10.2026: flags - דגל לישות שהיא מדינה
# גל 52: ניקוי נתונים - ימים חסרים במקור יומי (zero / previous / interpolate; מקור יכול לקבוע missing משלו), תיקוני
# קפיצות חשודות (spread / smooth / set), ואיפה העותקים של מקורות מכתובת (ריק = .url_cache בתיקיית הפרק)
DEFAULTS["data"] = {"missing": "zero", "fixes": [], "cache_dir": ""}
# 27.10.2026: auto (NVENC כשהכרטיס וה-ffmpeg תומכים, אחרת המעבד) במקום cpu. ורינדור בעדיפות נמוכה (low) - המחשב נשאר זמין
DEFAULTS["video"]["encoder"] = "auto"
DEFAULTS["video"]["priority"] = "low"
# 27.10.2026: outro.position - מרכז תיבת הסיום אחרי שגררו אותה בתצוגה ([x, y] של אזור הנתונים). ריק = המקום האוטומטי
DEFAULTS["outro"]["position"] = []
# גל 55: גרסאות בשפות (translations.<שפה> - dataviz/languages.py), פרקים ביוטיוב מכרטיסי האירועים, ו-Shorts אוטומטיים
DEFAULTS["translations"] = {}
DEFAULTS["publish"]["chapters"] = True
DEFAULTS["shorts"] = {"count": 3, "seconds": 20.0, "cta": "הסרטון המלא בערוץ ▶"}   # גל 54: cpu (libx264), nvenc (כרטיס מסך של NVIDIA), auto - NVENC אם יש
DEFAULTS["style"] = {"bar_height": 0.7, "grid": True, "title_size": 21, "year_mark": True}
DEFAULTS["labels"]["others"] = "אחרים"
DEFAULTS["map"].update({"legend": False, "labels": "none"})
IMAGE_SHAPES = ("circle", "square", "original")
MAP_LABELS = ("none", "top", "all")
DEFAULTS["ranking"]["log_scale"] = False          # גל 49: ציר לוגריתמי (עמודות, קווים, פיזור, מפת חום ומפה)
DEFAULTS["labels"].update({
    "rank_arrows": False,       # גל 49: ▲▼ ליד ישות שעלתה / ירדה בדירוג לעומת rank_window_days ימים אחורה
    "rank_window_days": 7,
    "gains": False,             # גל 49: "+N" ליד עמודה שקפצה ביום שמונפש עכשיו
    "gains_min": 0.02,          # קפיצה מינימלית - חלק מהציר
})

VALUE_MODES = ("cumulative", "rolling")
NUMBER_STYLES = ("plain", "compact", "words")


class ConfigError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """מיזוג עמוק: dict בתוך dict מתמזג, כל השאר (כולל רשימות) מוחלף."""
    result = copy.deepcopy(dict(base))
    for key, value in (override or {}).items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str, overrides: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    """קורא config.yaml, ממזג עם ברירות המחדל ומוודא. base_dir = התיקייה של הקובץ."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except OSError as e:
        raise ConfigError([f"לא ניתן לקרוא את קובץ ההגדרות {path}: {e}"]) from e
    except yaml.YAMLError as e:
        raise ConfigError([f"קובץ ההגדרות {path} אינו YAML תקין: {e}"]) from e
    if not isinstance(raw, Mapping):
        raise ConfigError([f"קובץ ההגדרות {path} צריך להיות מילון (key: value) ברמה העליונה."])
    # overrides = שכבת שינויים חיצונית (למשל מהמסך בדפדפן) שנמזגת מעל config.yaml בלי לכתוב אליו
    user = merge(raw, overrides or {})
    config = merge(DEFAULTS, user)
    config["base_dir"] = os.path.dirname(os.path.abspath(path))
    config["name"] = os.path.basename(config["base_dir"])
    # 19.10.2026: אילו הגדרות מספרים המשתמש קבע בעצמו - ברירת מחדל שתלויה בנתונים (ספרה עשרונית לרמות) לא דורסת אותן
    config["numbers_set"] = sorted(user["numbers"]) if isinstance(user.get("numbers"), Mapping) else []
    errors = validate(config)
    if errors:
        raise ConfigError(errors)
    return config


def _positive(errors: List[str], section: Mapping[str, Any], key: str, where: str, allow_zero: bool = False) -> None:
    value = section.get(key)
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and (value >= 0 if allow_zero else value > 0)
    if not ok:
        errors.append(f"{where}.{key} צריך להיות מספר {'אי-שלילי' if allow_zero else 'חיובי'} (התקבל {value!r}).")


def validate(config: Mapping[str, Any]) -> List[str]:
    """רשימת שגיאות (ריקה = תקין). לא זורקת - load_config אוסף ומחליט."""
    errors: List[str] = []
    base_dir = config.get("base_dir", ".")
    if not str(config.get("title") or "").strip():
        errors.append("חסרה כותרת (title).")
    if config.get("chart") not in CHARTS:
        errors.append(f"chart לא מוכר: {config.get('chart')!r} (קיימים: {', '.join(CHARTS)}).")
    if config.get("theme") not in ("light", "dark"):
        errors.append(f"theme לא מוכרת: {config.get('theme')!r} (light או dark).")
    if config.get("current_entity") not in ("auto", "year", "none"):
        errors.append(f"current_entity צריך להיות auto, year או none (התקבל {config.get('current_entity')!r}).")

    video = config.get("video") or {}
    for key in ("width", "height", "dpi", "fps"):
        _positive(errors, video, key, "video")
    if isinstance(video.get("width"), int) and isinstance(video.get("height"), int) and (video["width"] % 2 or video["height"] % 2):
        errors.append("video.width ו-video.height צריכים להיות זוגיים (דרישת yuv420p).")

    timing = config.get("timing") or {}
    for key in ("step", "base_frames_per_day", "test_main_seconds"):
        _positive(errors, timing, key, "timing")
    for key in ("intro_seconds", "outro_seconds", "test_intro_seconds", "test_outro_seconds", "preview_seconds"):
        _positive(errors, timing, key, "timing", allow_zero=True)
    if not isinstance(timing.get("strict_step"), bool):
        errors.append("timing.strict_step צריך להיות true או false.")
    if not isinstance(timing.get("smooth_window"), int) or timing.get("smooth_window", 0) < 1:
        errors.append("timing.smooth_window צריך להיות מספר שלם חיובי.")

    ranking = config.get("ranking") or {}
    if not isinstance(ranking.get("top_n"), int) or not 1 <= ranking["top_n"] <= 30:
        errors.append("ranking.top_n צריך להיות מספר שלם בין 1 ל-30.")
    smoothing = ranking.get("smoothing")
    if not isinstance(smoothing, (int, float)) or not 0 < smoothing <= 1:
        errors.append("ranking.smoothing צריך להיות בין 0 (לא כולל) ל-1.")
    for key in ("axis_min", "axis_headroom", "axis_min_headroom", "axis_rise", "axis_fall"):
        _positive(errors, ranking, key, "ranking")

    # 23.10.2026: תאריך לא תקין, או התחלה אחרי סוף, הגיעו למנוע כשגיאה גולמית (DateParseError / argmax של רשימה ריקה)
    timeline = config.get("timeline") or {}
    bounds: Dict[str, Any] = {}
    for key in ("start", "end"):
        value = timeline.get(key)
        if value in (None, ""):
            continue
        try:
            bounds[key] = pd.Timestamp(str(value))
        except (ValueError, TypeError):
            errors.append(f"timeline.{key} צריך להיות תאריך (YYYY-MM-DD) - התקבל {value!r}.")
    if "start" in bounds and "end" in bounds and bounds["start"] > bounds["end"]:
        errors.append("timeline.start אחרי timeline.end.")

    records = config.get("records") or {}
    if records.get("when") not in RECORD_RULES:
        errors.append(f"records.when צריך להיות אחד מ: {', '.join(RECORD_RULES)}.")

    outro = config.get("outro") or {}
    if not isinstance(outro.get("places"), list) or len(outro["places"]) < 1:
        errors.append("outro.places צריכה להיות רשימה (לפחות מקום אחד).")

    scatter = config.get("scatter") or {}
    if not isinstance(scatter.get("window_days"), int) or scatter["window_days"] < 1:
        errors.append("scatter.window_days צריך להיות מספר שלם חיובי.")

    if not isinstance(config.get("notes"), list):
        errors.append("notes צריכה להיות רשימת שורות.")

    errors.extend(_validate_events(config.get("events"), base_dir))
    errors.extend(_validate_sources(config.get("sources"), base_dir, config))

    errors.extend(_validate_publish(config.get("publish")))
    errors.extend(_validate_entity_rules(config.get("colors"), config.get("entities")))
    series = config.get("series") or {}
    if not isinstance(series.get("name", ""), str) or not isinstance(series.get("number", 0), int) or series.get("number", 0) < 0:
        errors.append("series צריך name (טקסט) ו-number (מספר שלם אי-שלילי).")
    errors.extend(_validate_wave42(config, base_dir))
    errors.extend(_validate_numbers(config, base_dir))
    errors.extend(_validate_story(config))
    errors.extend(_validate_look(config, base_dir))
    errors.extend(_validate_data(config))
    from dataviz.render import ENCODERS
    if (config.get("video") or {}).get("encoder") not in ENCODERS:
        errors.append(f"video.encoder צריך להיות אחד מ: {', '.join(ENCODERS)}.")
    if (config.get("video") or {}).get("priority", "low") not in VIDEO_PRIORITIES:   # 27.10.2026
        errors.append(f"video.priority צריך להיות אחד מ: {', '.join(VIDEO_PRIORITIES)}.")
    position = (config.get("outro") or {}).get("position", [])
    if position != [] and not (isinstance(position, list) and len(position) == 2 and all(_number_in(v, -0.5, 1.5) for v in position)):
        errors.append("outro.position צריך להיות [x, y] (חלקים של אזור הנתונים, -0.5 עד 1.5) או ריק.")
    if (config.get("story") or {}).get("chapter_transition", "fade") not in CHAPTER_TRANSITIONS:
        errors.append(f"story.chapter_transition צריך להיות אחד מ: {', '.join(CHAPTER_TRANSITIONS)}.")
    if not isinstance((config.get("images") or {}).get("flags", False), bool):
        errors.append("images.flags צריך להיות true או false.")
    translations = config.get("translations")
    if not isinstance(translations, Mapping) or not all(isinstance(v, Mapping) for v in translations.values()):
        errors.append("translations צריך להיות מילון של שפה -> טקסטים מתורגמים.")
    shorts = config.get("shorts") or {}
    if not _is_int(shorts.get("count"), 1, 5) or not _number_in(shorts.get("seconds"), 8, 60) or not isinstance(shorts.get("cta"), str):
        errors.append("shorts צריך count (1 עד 5), seconds (8 עד 60) ו-cta (טקסט).")
    if not isinstance((config.get("publish") or {}).get("chapters"), bool):
        errors.append("publish.chapters צריך להיות true או false.")
    logo = config.get("logo") or {}
    if logo.get("path") and not os.path.isfile(os.path.join(base_dir, str(logo["path"]))):
        errors.append(f"קובץ הלוגו לא נמצא: {logo['path']}")
    if logo.get("position") not in ("top-left", "top-right", "bottom-left", "bottom-right"):
        errors.append("logo.position צריך להיות top-left, top-right, bottom-left או bottom-right.")

    audio = config.get("audio") or {}
    if audio.get("path") and not os.path.isfile(os.path.join(base_dir, str(audio["path"]))):
        errors.append(f"קובץ המוזיקה לא נמצא: {audio['path']}")
    for key in ("start", "fade_in", "fade_out"):
        _positive(errors, audio, key, "audio", allow_zero=True)
    return errors


def _validate_wave42(config: Mapping[str, Any], base_dir: str) -> List[str]:
    """כתוביות, קריינות, מפה ושיתוף (גל 42)."""
    errors: List[str] = []
    for section, keys in (("captions", ("enabled", "events", "records", "intro")), ("narration", ("enabled", "events", "records"))):
        values = config.get(section) or {}
        for key in keys:
            if not isinstance(values.get(key), bool):
                errors.append(f"{section}.{key} צריך להיות true או false.")
    narration = config.get("narration") or {}
    rate = narration.get("rate")
    if not isinstance(rate, int) or isinstance(rate, bool) or not -10 <= rate <= 10:
        errors.append("narration.rate צריך להיות מספר שלם בין -10 ל-10.")
    volume = narration.get("volume")
    if not isinstance(volume, (int, float)) or isinstance(volume, bool) or not 0 < volume <= 3:
        errors.append("narration.volume צריך להיות בין 0 (לא כולל) ל-3.")
    if not isinstance(narration.get("voice"), str):
        errors.append("narration.voice צריך להיות טקסט (שם קול של Windows, או ריק).")
    if not isinstance(narration.get("tts"), bool):
        errors.append("narration.tts צריך להיות true או false.")
    track = narration.get("track", "")
    if not isinstance(track, str) or "/" in track or "\\" in track:   # 27.10.2026: שם קובץ בתיקיית ההקלטות בלבד
        errors.append("narration.track צריך להיות שם של קובץ בתיקיית ההקלטות (או ריק).")
    if not _number_in(narration.get("track_start", 0.0), 0, 36000):
        errors.append("narration.track_start צריך להיות בין 0 ל-36000 שניות.")
    recordings = narration.get("folder")
    if not isinstance(recordings, str) or (recordings and not os.path.isdir(os.path.join(base_dir, recordings))):
        errors.append(f"תיקיית ההקלטות לא נמצאה: {recordings}")
    geo = config.get("map") or {}
    if geo.get("geojson") and not os.path.isfile(os.path.join(base_dir, str(geo["geojson"]))):
        errors.append(f"קובץ המפה לא נמצא: {geo['geojson']}")
    if config.get("chart") == "map_race" and not geo.get("geojson"):
        errors.append("תרשים מפה (map_race) צריך קובץ GeoJSON (map.geojson).")
    if not str(geo.get("key") or "").strip():
        errors.append("map.key צריך להיות שם המאפיין ב-GeoJSON (למשל name).")
    if geo.get("projection") not in ("mercator", "equirect"):
        errors.append("map.projection צריך להיות mercator או equirect.")
    bumpers = config.get("bumpers") or {}
    for key in ("intro", "outro"):
        clip = bumpers.get(key)
        if not isinstance(clip, str):
            errors.append(f"bumpers.{key} צריך להיות נתיב לקליפ (או ריק).")
        elif clip and not os.path.isfile(os.path.join(base_dir, clip)):
            errors.append(f"קליפ ה-{'אינטרו' if key == 'intro' else 'אאוטרו'} לא נמצא: {clip}")
    share = config.get("share") or {}
    _positive(errors, share, "gif_seconds", "share")
    _positive(errors, share, "gif_fps", "share")
    scale = share.get("gif_scale")
    if not isinstance(scale, (int, float)) or not 0.1 <= scale <= 1:
        errors.append("share.gif_scale צריך להיות בין 0.1 ל-1.")
    return errors


def _is_int(value: Any, lo: int, hi: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi


def _validate_y_axes(axes: Any) -> List[str]:
    """20.10.2026: y_axes.left / y_axes.right - כותרת ופורמט מספרים לכל ציר (רק המפתחות שנקבעו)."""
    if not isinstance(axes, Mapping):
        return ["y_axes צריך להיות מילון (left / right)."]
    errors: List[str] = []
    for side, axis in axes.items():
        where = f"y_axes.{side}"
        if side not in ("left", "right") or not isinstance(axis, Mapping):
            errors.append(f"{where}: רק left או right, כל אחד מילון.")
            continue
        if not isinstance(axis.get("label", ""), str) or len(axis.get("label", "")) > 60:
            errors.append(f"{where}.label צריך להיות טקסט קצר (עד 60 תווים).")
        numbers = axis.get("numbers", {})
        if not isinstance(numbers, Mapping):
            errors.append(f"{where}.numbers צריך להיות מילון.")
            continue
        if "style" in numbers and numbers["style"] not in NUMBER_STYLES:
            errors.append(f"{where}.numbers.style צריך להיות אחד מ: {', '.join(NUMBER_STYLES)}.")
        if "decimals" in numbers and not _is_int(numbers["decimals"], 0, 4):
            errors.append(f"{where}.numbers.decimals צריך להיות מספר שלם בין 0 ל-4.")
        for key in ("prefix", "suffix"):
            if key in numbers and (not isinstance(numbers[key], str) or len(numbers[key]) > 12):
                errors.append(f"{where}.numbers.{key} צריך להיות טקסט קצר (עד 12 תווים).")
        if "thousands" in numbers and not isinstance(numbers["thousands"], bool):
            errors.append(f"{where}.numbers.thousands צריך להיות true או false.")
    return errors


def _validate_numbers(config: Mapping[str, Any], base_dir: str) -> List[str]:
    """גל 49: מצב הערכים (מצטבר / חלון מתגלגל / לנפש), פורמט המספרים, ציר לוגריתמי, חיצים ו-"+N"."""
    errors: List[str] = []
    values = config.get("values") or {}
    if values.get("mode") not in VALUE_MODES:
        errors.append(f"values.mode צריך להיות אחד מ: {', '.join(VALUE_MODES)}.")
    if not _is_int(values.get("window_days"), 1, 3650):
        errors.append("values.window_days צריך להיות מספר שלם בין 1 ל-3650.")
    per_capita = values.get("per_capita") or {}
    if not isinstance(per_capita.get("enabled"), bool):
        errors.append("values.per_capita.enabled צריך להיות true או false.")
    _positive(errors, per_capita, "per", "values.per_capita")
    populations = per_capita.get("populations")
    if not isinstance(populations, Mapping) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in populations.values()):
        errors.append("values.per_capita.populations צריך להיות מילון של ישות -> אוכלוסייה (מספר חיובי).")
    pop_file = per_capita.get("file")
    if not isinstance(pop_file, str) or (pop_file and not os.path.isfile(os.path.join(base_dir, pop_file))):
        errors.append(f"קובץ האוכלוסייה לא נמצא: {pop_file}")
    if per_capita.get("enabled") is True and not pop_file and not populations:
        errors.append("מצב לנפש צריך קובץ אוכלוסייה (values.per_capita.file) או populations.")
    numbers = config.get("numbers") or {}
    if numbers.get("style") not in NUMBER_STYLES:
        errors.append(f"numbers.style צריך להיות אחד מ: {', '.join(NUMBER_STYLES)}.")
    if not _is_int(numbers.get("decimals"), 0, 4):
        errors.append("numbers.decimals צריך להיות מספר שלם בין 0 ל-4.")
    for key in ("prefix", "suffix"):
        if not isinstance(numbers.get(key), str) or len(numbers.get(key, "")) > 12:
            errors.append(f"numbers.{key} צריך להיות טקסט קצר (עד 12 תווים).")
    if not isinstance(numbers.get("thousands"), bool):
        errors.append("numbers.thousands צריך להיות true או false.")
    if not isinstance((config.get("ranking") or {}).get("log_scale"), bool):
        errors.append("ranking.log_scale צריך להיות true או false.")
    errors.extend(_validate_y_axes(config.get("y_axes")))
    labels = config.get("labels") or {}
    for key in ("rank_arrows", "gains"):
        if not isinstance(labels.get(key), bool):
            errors.append(f"labels.{key} צריך להיות true או false.")
    if not _is_int(labels.get("rank_window_days"), 1, 365):
        errors.append("labels.rank_window_days צריך להיות מספר שלם בין 1 ל-365.")
    gains_min = labels.get("gains_min")
    if not isinstance(gains_min, (int, float)) or isinstance(gains_min, bool) or not 0 <= gains_min <= 1:
        errors.append("labels.gains_min צריך להיות בין 0 ל-1.")
    return errors


MAX_STORY_ITEMS = 100
# פריט בכל רשימה של הסיפור: (שדות חובה, שדות תאריך)
STORY_ITEMS = {"chapters": (("date", "title"), ("date",)), "pauses": (("date", "text"), ("date",)),
               "callouts": (("date", "entity", "text"), ("date",)), "periods": (("start", "end", "label"), ("start", "end")),
               "speed": (("start", "end", "speed"), ("start", "end")),
               "annotations": (("date", "value", "text"), ("date",)),
               "focus": (("date", "entities"), ("date",)),
               "script": (("date", "text"), ("date",))}
ANNOTATION_STYLES = ("default", "accent", "muted")


def _number_in(value: Any, lo: float, hi: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and lo <= value <= hi


def _validate_story(config: Mapping[str, Any]) -> List[str]:
    """גל 50: רשימות הסיפור, הטיזר, מסך הסיום ומקורות הנתונים."""
    errors: List[str] = []
    story = config.get("story") or {}
    focus = config.get("focus") or {}   # 20.10.2026: מצב פוקוס
    if not isinstance(focus.get("entities"), list) or len(focus["entities"]) > 20:
        errors.append("focus.entities צריך להיות רשימה (עד 20 ישויות).")
    if not _number_in(focus.get("dim"), 0.05, 1.0):
        errors.append("focus.dim צריך להיות בין 0.05 ל-1.")
    for i, item in enumerate(story.get("focus") or []):
        if isinstance(item, Mapping) and (not isinstance(item.get("entities"), list) or len(item["entities"]) > 20):
            errors.append(f"story.focus[{i}].entities צריך להיות רשימה (עד 20 ישויות).")
    for i, item in enumerate(story.get("annotations") or []):   # 20.10.2026
        where = f"story.annotations[{i}]"
        if not isinstance(item, Mapping):
            continue
        if not _number_in(item.get("value"), -1e15, 1e15):
            errors.append(f"{where}: value צריך להיות מספר.")
        for key in ("dx", "dy"):
            if key in item and not _is_int(item[key], -400, 400):
                errors.append(f"{where}: {key} צריך להיות מספר שלם בין -400 ל-400.")
        if "style" in item and item["style"] not in ANNOTATION_STYLES:
            errors.append(f"{where}: style צריך להיות אחד מ: {', '.join(ANNOTATION_STYLES)}.")
    for key, (required, dates) in STORY_ITEMS.items():
        items = story.get(key)
        if not isinstance(items, list) or len(items) > MAX_STORY_ITEMS:
            errors.append(f"story.{key} צריך להיות רשימה (עד {MAX_STORY_ITEMS}).")
            continue
        for i, item in enumerate(items):
            where = f"story.{key}[{i}]"
            if not isinstance(item, Mapping) or any(item.get(k) in (None, "") for k in required):
                errors.append(f"{where} צריך {', '.join(required)}.")
                continue
            for k in dates:
                try:
                    pd.Timestamp(str(item[k]))
                except (ValueError, TypeError):
                    errors.append(f"{where}: תאריך לא תקין {item[k]!r}.")
            if "seconds" in item and not _number_in(item["seconds"], 0.5, 30):
                errors.append(f"{where}.seconds צריך להיות בין 0.5 ל-30.")
            if "days" in item and not _is_int(item["days"], 1, 3650):
                errors.append(f"{where}.days צריך להיות מספר שלם בין 1 ל-3650.")
            if key == "speed" and not _number_in(item["speed"], 0.1, 20):
                errors.append(f"{where}.speed צריך להיות בין 0.1 ל-20 (2 = פי שניים מהר יותר).")
            if key == "periods" and item.get("color") and not _is_hex_color(item["color"]):
                errors.append(f"{where}.color צריך להיות צבע #rrggbb.")
    for key, lo, hi in (("chapter_seconds", 0.5, 30), ("pause_seconds", 0.5, 30)):
        if not _number_in(story.get(key), lo, hi):
            errors.append(f"story.{key} צריך להיות בין {lo} ל-{hi}.")
    if not _is_int(story.get("callout_days"), 1, 3650):
        errors.append("story.callout_days צריך להיות מספר שלם בין 1 ל-3650.")
    teaser = config.get("teaser") or {}
    if not isinstance(teaser.get("enabled"), bool) or not _number_in(teaser.get("seconds"), 1, 15) or not isinstance(teaser.get("label"), str):
        errors.append("teaser צריך enabled (true/false), seconds (1 עד 15) ו-label (טקסט).")
    end_screen = config.get("end_screen") or {}
    if (not isinstance(end_screen.get("enabled"), bool) or not isinstance(end_screen.get("guides"), bool)
            or not _number_in(end_screen.get("seconds"), 5, 20) or not isinstance(end_screen.get("text"), str)):
        errors.append("end_screen צריך enabled ו-guides (true/false), seconds (5 עד 20, כמו ביוטיוב) ו-text.")
    credits = (config.get("outro") or {}).get("credits")
    if not isinstance(credits, list) or not all(isinstance(line, str) for line in credits):
        errors.append("outro.credits צריכה להיות רשימת שורות.")
    return errors


def _validate_data(config: Mapping[str, Any]) -> List[str]:
    """גל 52: ימים חסרים, תיקונים ותיקיית העותקים של מקורות מכתובת."""
    from dataviz.cleaning import FIX_ACTIONS
    from dataviz.sources import MISSING_MODES
    errors: List[str] = []
    data = config.get("data") or {}
    if data.get("missing") not in MISSING_MODES:
        errors.append(f"data.missing צריך להיות אחד מ: {', '.join(MISSING_MODES)}.")
    if not isinstance(data.get("cache_dir"), str):
        errors.append("data.cache_dir צריך להיות נתיב (או ריק).")
    fixes = data.get("fixes")
    if not isinstance(fixes, list) or len(fixes) > 500:
        return errors + ["data.fixes צריך להיות רשימה (עד 500)."]
    for i, fix in enumerate(fixes):
        if not isinstance(fix, Mapping) or not fix.get("entity") or fix.get("action") not in FIX_ACTIONS:
            errors.append(f"data.fixes[{i}] צריך entity, date ו-action ({', '.join(FIX_ACTIONS)}).")
            continue
        try:
            pd.Timestamp(str(fix.get("date")))
        except (ValueError, TypeError):
            errors.append(f"data.fixes[{i}]: תאריך לא תקין {fix.get('date')!r}.")
        if fix["action"] == "set" and not _number_in(fix.get("value"), -1e15, 1e15):
            errors.append(f"data.fixes[{i}]: set צריך value (מספר).")
    return errors


def _validate_look(config: Mapping[str, Any], base_dir: str) -> List[str]:
    """גל 51: תמונות לישויות, סגנון, "אחרים" ומקרא / שמות על המפה."""
    errors: List[str] = []
    images = config.get("images") or {}
    folder = images.get("folder")
    if not isinstance(folder, str) or (folder and not os.path.isdir(os.path.join(base_dir, folder))):
        errors.append(f"תיקיית התמונות לא נמצאה: {folder}")
    if images.get("shape") not in IMAGE_SHAPES:
        errors.append(f"images.shape צריך להיות אחד מ: {', '.join(IMAGE_SHAPES)}.")
    if not _number_in(images.get("size"), 0.3, 3):
        errors.append("images.size צריך להיות בין 0.3 ל-3.")
    style = config.get("style") or {}
    if not _number_in(style.get("bar_height"), 0.2, 0.95):
        errors.append("style.bar_height צריך להיות בין 0.2 ל-0.95.")
    if not _is_int(style.get("title_size"), 10, 48):
        errors.append("style.title_size צריך להיות מספר שלם בין 10 ל-48.")
    for key in ("grid", "year_mark"):
        if not isinstance(style.get(key), bool):
            errors.append(f"style.{key} צריך להיות true או false.")
    if not isinstance((config.get("labels") or {}).get("others"), str):
        errors.append("labels.others צריך להיות טקסט.")
    geo = config.get("map") or {}
    if not isinstance(geo.get("legend"), bool):
        errors.append("map.legend צריך להיות true או false.")
    if geo.get("labels") not in MAP_LABELS:
        errors.append(f"map.labels צריך להיות אחד מ: {', '.join(MAP_LABELS)}.")
    return errors


def _is_hex_color(value: Any) -> bool:
    text = str(value)
    return isinstance(value, str) and len(text) == 7 and text.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in text[1:])


def _validate_entity_rules(colors: Any, entities: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(colors, Mapping) or not all(_is_hex_color(v) for v in colors.values()):
        errors.append("colors צריך להיות מילון של ישות -> צבע #rrggbb.")
    if not isinstance(entities, Mapping):
        return errors + ["entities צריך להיות מילון (aliases, exclude)."]
    aliases = entities.get("aliases", {})
    if not isinstance(aliases, Mapping) or not all(str(v).strip() for v in aliases.values()):
        errors.append("entities.aliases צריך להיות מילון של ישות -> שם חלופי (לא ריק).")
    if not isinstance(entities.get("exclude", []), list):
        errors.append("entities.exclude צריך להיות רשימה.")
    return errors


def _validate_publish(publish: Any) -> List[str]:
    if not isinstance(publish, Mapping):
        return ["publish צריך להיות מילון."]
    errors = []
    for key in ("enabled", "seo_ai", "thumbnail", "approval"):
        if not isinstance(publish.get(key), bool):
            errors.append(f"publish.{key} צריך להיות true או false.")
    for key in ("title", "description"):
        if not isinstance(publish.get(key), str):
            errors.append(f"publish.{key} צריך להיות טקסט.")
    tags = publish.get("hashtags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        errors.append("publish.hashtags צריך להיות רשימת טקסטים.")
    return errors


def _validate_events(events: Any, base_dir: str) -> List[str]:
    if isinstance(events, str):
        if not os.path.isfile(os.path.join(base_dir, events)):
            return [f"קובץ האירועים לא נמצא: {events}"]
        return []
    if not isinstance(events, list):
        return ["events צריך להיות רשימה של {date, label} או שם קובץ CSV."]
    errors = []
    for i, event in enumerate(events):
        if not isinstance(event, Mapping) or not event.get("date") or not event.get("label"):
            errors.append(f"events[{i}] צריך date ו-label.")
            continue
        try:
            pd.Timestamp(str(event["date"]))
        except (ValueError, TypeError):
            errors.append(f"events[{i}]: תאריך לא תקין {event['date']!r}.")
    return errors


def _validate_sources(sources: Any, base_dir: str, config: Mapping[str, Any]) -> List[str]:
    if not isinstance(sources, list) or not sources:
        return ["צריך לפחות מקור נתונים אחד (sources)."]
    errors = []
    for i, spec in enumerate(sources):
        where = f"sources[{i}]"
        if not isinstance(spec, Mapping):
            errors.append(f"{where} צריך להיות מילון.")
            continue
        url = str(spec.get("url") or "")
        if url and not url.startswith(("http://", "https://")):
            errors.append(f"{where}: url צריך להתחיל ב-http:// או https://.")
        elif url and not spec.get("path"):   # גל 52: מקור מכתובת - נקרא מהעותק שהורד
            if not os.path.isfile(url_cache_path(spec, config)):
                errors.append(f"{where}: המקור מהכתובת עוד לא הורד - לחץ \"רענן נתונים\" (חלון הנתונים, לשונית \"מכתובת ותזמון\").")
        elif not spec.get("path"):
            errors.append(f"{where}: חסר path (או url).")
        elif not os.path.isfile(os.path.join(base_dir, str(spec["path"]))):
            errors.append(f"{where}: הקובץ לא נמצא: {spec['path']}")
        if spec.get("missing") not in (None,) + MISSING_MODES:
            errors.append(f"{where}: missing צריך להיות אחד מ: {', '.join(MISSING_MODES)}.")
        if spec.get("fill") not in (None,) + FILL_MODES:   # 20.10.2026
            errors.append(f"{where}: fill צריך להיות אחד מ: {', '.join(FILL_MODES)}.")
        if spec.get("axis") not in (None, "left", "right"):   # 20.10.2026
            errors.append(f"{where}: axis צריך להיות left או right.")
        if spec.get("kind") not in (None,) + KINDS:   # 18.10.2026
            errors.append(f"{where}: kind צריך להיות אחד מ: {', '.join(KINDS)}.")
        elif spec.get("kind") == "level" and spec.get("value", "count") == "count":
            errors.append(f"{where}: kind: level צריך עמודת ערך (value: {{column: ...}}) - אין רמה בספירת שורות.")
        if source_type(spec) not in READERS:
            errors.append(f"{where}: type לא מוכר {spec.get('type')!r} (קיימים: {', '.join(READERS)}).")
        time_spec = spec.get("time")
        if isinstance(time_spec, str):
            time_spec = {"column": time_spec}
        if not isinstance(time_spec, Mapping) or not time_spec.get("column"):
            errors.append(f"{where}: חסר time.column.")
        elif time_spec.get("period", "day") not in PERIODS:
            errors.append(f"{where}: time.period צריך להיות אחד מ: {', '.join(PERIODS)}.")
        value = spec.get("value", "count")
        if value != "count" and not (isinstance(value, Mapping) and value.get("column")) and not isinstance(value, str):
            errors.append(f"{where}: value צריך להיות count או {{column: ...}}.")
        entity = spec.get("entity", {"from_time": "year"})
        if isinstance(entity, Mapping) and not (entity.get("column") or entity.get("from_time") in ("year", "month")):
            errors.append(f"{where}: entity צריך column או from_time: year/month.")
        texture = spec.get("texture")
        if texture not in (None, "stripes", "solid"):
            errors.append(f"{where}: texture צריך להיות stripes או solid.")
        weights = (spec.get("spread") or {}).get("weights")
        if weights and not os.path.isfile(os.path.join(base_dir, str(weights.get("path", "")))):
            errors.append(f"{where}: קובץ המשקלות לא נמצא: {weights.get('path')}")
    return errors


def mode_timing(config: Mapping[str, Any], mode: str) -> Dict[str, int]:
    """פריימי אינטרו/אאוטרו ומשך הקטע הראשי (None = לפי הקצב) לכל מצב הרצה."""
    if mode not in MODES:
        raise ValueError(f"מצב הרצה לא מוכר: {mode!r} (קיימים: {', '.join(MODES)}).")
    fps = int(config["video"]["fps"])
    timing = config["timing"]
    if mode in ("full", "stills", "share", "shorts"):
        outro = float(timing["outro_seconds"])
        end_screen = config.get("end_screen") or {}
        if end_screen.get("enabled"):   # גל 50: יוטיוב מציג End Screen ב-5 עד 20 השניות האחרונות
            outro = max(outro, float(end_screen.get("seconds") or 20))
        return {"intro": int(timing["intro_seconds"] * fps), "outro": int(outro * fps), "main": 0}
    if mode == "preview":
        return {"intro": fps // 2, "outro": fps // 2, "main": int(timing["preview_seconds"] * fps)}
    return {"intro": int(timing["test_intro_seconds"] * fps), "outro": int(timing["test_outro_seconds"] * fps),
            "main": int(timing["test_main_seconds"] * fps)}


def preview_config(config: Mapping[str, Any], scale: float = 0.5) -> Dict[str, Any]:
    """עותק של ההגדרות לתצוגה מקדימה מהירה: גודל הפריים וה-dpi מוקטנים באותו יחס (גודל הפריים באינצ'ים
    width/dpi נשאר זהה, אז הפריסה זהה לגמרי, רק פחות פיקסלים), קידוד מהיר וגס. הקובץ עצמו לא משתנה."""
    if not 0 < scale <= 1:
        raise ValueError(f"scale צריך להיות בין 0 (לא כולל) ל-1 (התקבל {scale!r}).")
    result = copy.deepcopy(dict(config))
    video = result["video"]
    video["width"] = max(2, int(round(video["width"] * scale / 2)) * 2)
    video["height"] = max(2, int(round(video["height"] * scale / 2)) * 2)
    video["dpi"] = max(1, int(round(video["dpi"] * scale)))
    video["crf"] = 30
    video["preset"] = "ultrafast"
    return result
