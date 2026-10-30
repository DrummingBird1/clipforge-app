# dataviz/charts/base.py
#
# המסגרת המשותפת לכל סוגי התרשימים: כותרת ותת-כותרת, מקרא (מלא / מרקם פסים), מונה
# כולל, תאריך, שנה גדולה ברקע, ציר זמן בתחתית עם נקודות אירוע, הערות מקור, כרטיס
# אירוע, התראת "שיא חדש", אינטרו ותיבת הסיום. כל תרשים יורש ומממש רק את אזור הנתונים
# (setup_data_axes + draw_data) - כך שהוספת סוג תרשים היא מודול אחד קטן.
#
# ביצועים: הדמות נבנית פעם אחת בכל תהליך רינדור. כל מה שקבוע (כותרות, מקרא, הערות,
# שלד ציר הזמן) נוצר כאן פעם אחת ורק מוסתר/מוצג לפי סוג הפריים; בכל פריים נוצרים רק
# הרכיבים המשתנים, ונמחקים בתחילת הפריים הבא (בלי ax.clear() - יקר). אסור fig.text
# בתוך לולאת הציור: טקסט ברמת הדמות לא נמחק עם הצירים, נערם ומאט כל פריים.
#
# המיקומים והגדלים זהים לסרטון הראשון (1440x888); הם יחסיים לדמות, אז גודל אחר משנה
# רק את הצפיפות.

import math
import os
import re
import textwrap
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Mapping, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, to_rgb  # noqa: E402
from matplotlib.patches import Ellipse, Rectangle  # noqa: E402
from matplotlib.ticker import Formatter, MaxNLocator  # noqa: E402

from dataviz.themes import apply_rc, palette_positions, theme_from_dict  # noqa: E402

MARGINS = {"left": 0.085, "right": 0.96, "top": 0.84, "bottom": 0.215}
TIMELINE_RECT = (0.085, 0.108, 0.875, 0.05)
# גל 41: פריים לאורך (Shorts / TikTok, גובה > רוחב) - יותר מקום לכותרת ולתוויות, הציר נמוך יותר.
# פריים לרוחב לא משתנה בכלל.
MARGINS_PORTRAIT = {"left": 0.13, "right": 0.95, "top": 0.80, "bottom": 0.17}
TIMELINE_RECT_PORTRAIT = (0.13, 0.085, 0.82, 0.035)
LOGO_POSITIONS = {"top-left": (0.02, 0.98, "left", "top"), "top-right": (0.98, 0.98, "right", "top"),
                  "bottom-left": (0.02, 0.02, "left", "bottom"), "bottom-right": (0.98, 0.02, "right", "bottom")}
NOTE_Y = (0.05, 0.022)
NOTE_STEP = 0.028
NOTE_TOP_GAP, NOTE_MIN_Y = 0.03, 0.01   # 18.10.2026: שלוש הערות ומעלה - נערמות בין התחתית לציר הזמן
LEGEND_X0, LEGEND_STEP = 0.985, 0.4


def round_half_up(value: float, decimals: int = 0) -> float:
    """עיגול "של בית ספר": חצי תמיד הלאה מאפס (2.5 -> 3, 0.125 -> 0.13). עד 16.10.2026 int() קטם - 2014 בפרק הראשון
    (4,035.99 אחרי הפיזור היומי) הוצגה 4,035 במקום 4,036 - ו-round() / format של פייתון מעגלים חצי לזוגי.
    str(value) - הייצוג הקצר, כדי ש-2.675 ייחשב 2.675 ולא 2.67499... של הייצוג הבינארי."""
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))


def format_int(value: float) -> str:
    return f"{int(round_half_up(value)):,}"


# סבב הייצוב (16.10.2026): ⏸, ⏩ ו-▶ (ההזמנה בסוף ה-Shorts) לא קיימים ב-Segoe UI - יצאו ריבועים ריקים. בטקסטים
# שלהם רשימת גופנים עם גופן סמלים מיד אחרי הראשון, ו-matplotlib משלים ממנו אות-אות רק את מה שחסר. שאר הטקסט
# בגופנים של הערכה, כמו קודם
SYMBOL_FONT = "Segoe UI Symbol"


def with_symbol_font(fonts: Any) -> List[str]:
    fonts = list(fonts)
    return [fonts[0], SYMBOL_FONT, *(f for f in fonts[1:] if f != SYMBOL_FONT)] if fonts and fonts[0] != SYMBOL_FONT else fonts


# גל 49: קיצורים לפי הסגנון (compact = אותיות, words = מילים). 23.10.2026 (נ14): גם טריליון - "$2,500B" היה ארוך
_UNITS = ((1e12, "T", " טריליון"), (1e9, "B", " מיליארד"), (1e6, "M", " מיליון"), (1e3, "K", " אלף"))
# 25.10.2026: מכאן מספר בסגנון plain (ברירת המחדל) נכתב compact - "1.8T" ולא 1,830,000,000,000 שנחתך בקצה הפריים
AUTO_COMPACT = 1e12
_UNITS_EN = (" trillion", " billion", " million", " thousand")   # גל 55: מספרים במילים בגרסה באנגלית
TEXT_EDGE = 0.005   # 23.10.2026 (ב16): שם ארוך לא מתקרב לקצה הפריים יותר מזה (חלק מרוחב הפריים)
UP_COLOR, DOWN_COLOR = "#2f9e6e", "#d1495b"     # חיצי דירוג - ירוק עלה, אדום ירד (קריאים בבהיר ובכהה)


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
IMAGE_PX = 160      # כל תמונה נטענת פעם אחת בגודל הזה (ריבוע), והציור מקטין אותה


def image_name(entity: Any) -> str:
    """שם הקובץ (בלי סיומת) של התמונה של ישות - בלי התווים שאסורים בשם קובץ."""
    return re.sub(r'[\\/:*?"<>|]', "-", str(entity)).strip()


def load_entity_images(settings: Mapping[str, Any], entities: List[Any]) -> Dict[str, Any]:
    """גל 51: ישות (כטקסט) -> תמונה (מערך RGBA) מהתיקייה images.folder. שם הקובץ = שם הישות, ואפשר גם
    "<שם>@<משהו>" (העלאה מהמסך) - החדש ביותר גובר. shape: circle (חיתוך עגול), square, original."""
    folder = str(settings.get("folder") or "")
    wanted = {image_name(e): str(e) for e in entities}
    newest: Dict[str, tuple] = {}
    for name in os.listdir(folder) if folder and os.path.isdir(folder) else []:
        stem, ext = os.path.splitext(name)
        key = stem.rsplit("@", 1)[0]
        if ext.lower() in IMAGE_EXT and key in wanted:
            mtime = os.path.getmtime(os.path.join(folder, name))
            if key not in newest or mtime > newest[key][0]:
                newest[key] = (mtime, os.path.join(folder, name))
    # 27.10.2026: images.flags - ישות שהיא מדינה ואין לה תמונה משלה מקבלת את הדגל שלה (<קוד>.png בתיקיית הדגלים).
    # תמונה שהמשתמש העלה גוברת תמיד
    flags_dir = str(settings.get("flags_dir") or "")
    if settings.get("flags") and flags_dir and os.path.isdir(flags_dir):
        from dataviz.countries import country_code
        for key, entity in wanted.items():
            code = country_code(entity)
            flag = os.path.join(flags_dir, f"{code}.png") if code else ""
            if key not in newest and flag and os.path.isfile(flag):
                newest[key] = (0.0, flag)
    if not newest:
        return {}
    from PIL import Image, ImageDraw
    shape = settings.get("shape", "circle")
    result: Dict[str, Any] = {}
    for key, (_mtime, path) in newest.items():
        try:
            image = Image.open(path).convert("RGBA")
        except (OSError, ValueError):
            continue    # קובץ פגום - בלי תמונה לישות הזו
        if shape == "original":
            ratio = IMAGE_PX / max(image.size)     # מתאים לריבוע בשני הכיוונים (thumbnail רק מקטין)
            image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))))
            canvas = Image.new("RGBA", (IMAGE_PX, IMAGE_PX), (0, 0, 0, 0))
            canvas.paste(image, ((IMAGE_PX - image.width) // 2, (IMAGE_PX - image.height) // 2))
            image = canvas
        else:
            side = min(image.size)
            left, top = (image.width - side) // 2, (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side)).resize((IMAGE_PX, IMAGE_PX))
            if shape == "circle":
                mask = Image.new("L", (IMAGE_PX, IMAGE_PX), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, IMAGE_PX - 1, IMAGE_PX - 1), fill=255)
                image.putalpha(Image.composite(image.getchannel("A"), mask, mask))
        result[wanted[key]] = np.asarray(image)
    return result


def format_number(value: float, numbers: Mapping[str, Any] | None = None) -> str:
    """גל 49: מספר לפי numbers בהגדרות הפרק. בלי הגדרות, או בברירת המחדל (plain, 0 ספרות, פסיק בין אלפים, בלי
    קידומת וסיומת) - בדיוק format_int. בכל הסגנונות העיגול הוא round_half_up."""
    huge = abs(float(value)) >= AUTO_COMPACT
    if not numbers and not huge:
        return format_int(value)
    numbers = numbers or {}
    style = numbers.get("style", "plain")
    decimals = int(numbers.get("decimals") or 0)
    if style == "plain" and huge:   # 25.10.2026: מטריליון "plain" הוא 17+ ספרות שנחתכות בקצה ועולות זו על זו בציר
        style, decimals = "compact", max(decimals, 1)
    sep = "," if numbers.get("thousands", True) else ""
    number = float(value)
    negative = number < 0
    number = abs(number)
    unit = ""
    if style in ("compact", "words"):
        k = _unit_index(number, decimals)
        if k is not None:
            limit, letter, word = _UNITS[k]
            number /= limit
            unit = letter if style == "compact" else (_UNITS_EN[k] if numbers.get("lang") == "en" else word)
    number = round_half_up(number, decimals)
    sign = "-" if negative and number else ""   # נ13: -0.4 הוא "0" ולא "-0"
    text = f"{int(number):{sep}}" if decimals == 0 and not unit else f"{number:{sep}.{decimals}f}"
    if style in ("compact", "words") and "." in text:
        text = text.rstrip("0").rstrip(".")     # 1.0M -> 1M, 999.0 -> 999 (12.3 נשאר)
    # מילה (ק"מ, USD) מופרדת ברווח; סימן (%, ₪, $) צמוד למספר
    prefix, suffix = str(numbers.get("prefix") or ""), str(numbers.get("suffix") or "")
    prefix = prefix + " " if prefix[-1:].isalpha() else prefix
    suffix = " " + suffix if suffix[:1].isalpha() else suffix
    return f"{sign}{prefix}{text}{unit}{suffix}"


def _point(value: Any) -> Any:
    """27.10.2026: [x, y] של מיקום שנגרר בתצוגה (outro.position) - או None כשאין / לא תקין."""
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return float(value[0]), float(value[1])
    return None


def ltr_number(text: str) -> str:
    """25.10.2026: מספר שלילי אחרי שם בעברית באותה תווית ("כנרת  -210.1") - בשורה מימין לשמאל המינוס עבר לצד השני
    ("210.1-"). LRM לפני המספר מחזיק אותו (ואת החץ שאחריו) משמאל לימין. מספר חיובי - בלי שינוי, כדי שלא ישתנה אף פיקסל."""
    return "‎" + text if text.startswith("-") else text


def _unit_index(number: float, decimals: int) -> Any:
    """היחידה של compact / words למספר לא שלילי (מקום ב-_UNITS), או None מתחת לאלף."""
    k = next((i for i, (limit, _, _) in enumerate(_UNITS) if number >= limit), None)
    if k is None and round_half_up(number, decimals) >= 1000:
        k = len(_UNITS) - 1   # נ14: 999.6 בלי ספרות אחרי הנקודה - 1K ולא 1,000
    elif k and round_half_up(number / _UNITS[k][0], decimals) >= 1000:
        k -= 1     # 999,960 עם ספרה אחת אחרי הנקודה: 1M ולא 1000K
    return k


class NumberTicks(Formatter):
    """23.10.2026 (ב18): שנתות בסגנון compact / words - עם עוד ספרה אחרי הנקודה כשבלעדיה שתי שנתות יוצאות אותו
    דבר או לא מדויקות (1,500 ו-2,000 היו "2K" ו-"2K", ו-2,500 היה "3K"). שנתות שיוצאות מדויקות - בלי שינוי."""

    def __init__(self, numbers: Mapping[str, Any] | None):
        self.numbers = numbers

    def __call__(self, x: float, pos: Any = None) -> str:
        return format_number(x, self.numbers)

    def format_ticks(self, values: Any) -> List[str]:
        numbers = self.numbers or {}
        if numbers.get("style", "plain") == "plain" and any(abs(float(v)) >= AUTO_COMPACT for v in values):
            numbers = {**numbers, "style": "compact"}   # 25.10.2026: כמו format_number - כל השנתות באותו סגנון
        if numbers.get("style") not in ("compact", "words"):
            return [self(v) for v in values]
        decimals = int(numbers.get("decimals") or 0)
        labels: List[str] = []
        for extra in range(4):
            places = decimals + extra
            labels = [format_number(v, {**numbers, "decimals": places}) for v in values]
            if len(set(labels)) == len(labels) and all(_exact(float(v), places) for v in values):
                break
        return labels


def _exact(value: float, decimals: int) -> bool:
    number = abs(value)
    k = _unit_index(number, decimals)
    unit = _UNITS[k][0] if k is not None else 1.0
    return abs(round_half_up(number / unit, decimals) * unit - number) <= unit * 1e-9


class BaseChart:
    name = "base"
    # מיקום כרטיס האירוע, התראת "שיא חדש" ותיבת הסיום (צירי הנתונים: x, y, ha, va) - תרשים
    # שאזור הנתונים שלו צפוף במקום אחר (תוויות בקצה הקווים) מזיז אותם.
    CARD_AT = (0.985, 0.30, "right", "center")
    TOAST_AT = (0.62, 0.12, "center", "center")
    OUTRO_AT = (0.985, 0.30, "right", "center")
    HAS_TIME_AXIS = False     # גל 50: תרשים עם ציר זמן מצייר את התקופות המוצללות עליו; השאר - תגית
    ANNOTATES = False         # 20.10.2026: הערה על הגרף (תאריך + ערך) - רק כשציר ה-y הוא ערך (קווים, שטח)

    def __init__(self, ctx: Mapping[str, Any]):
        self.ctx = ctx
        self.theme = theme_from_dict(ctx["theme"])
        apply_rc(self.theme, plt.rcParams)
        self.top_n = int(ctx["top_n"])
        self.textures: Dict[Any, str] = dict(ctx.get("textures") or {})
        self._cmap = LinearSegmentedColormap.from_list("ordinal", list(self.theme.ordinal))
        self._positions = palette_positions(list(ctx["entities"]))
        self._categorical = ctx.get("palette") == "categorical"
        self._index = {e: i for i, e in enumerate(ctx["entities"])}
        self._fixed_colors: Dict[str, str] = dict(ctx.get("colors") or {})
        self.numbers = ctx.get("numbers") or None    # גל 49: פורמט המספרים
        self.style: Dict[str, Any] = {"bar_height": 0.7, "grid": True, "title_size": 21, "year_mark": True, **(ctx.get("style") or {})}   # גל 51
        images = ctx.get("images") or {}
        self._images = load_entity_images(images, list(ctx["entities"]))   # גל 51: תמונה לכל ישות
        self._image_scale = float(images.get("size") or 1.0)
        self.log = bool(ctx.get("log_scale"))        # גל 49: ציר לוגריתמי (כל תרשים מחליט מה זה אומר אצלו)

        dpi = ctx["dpi"]
        self.fig, self.ax = plt.subplots(figsize=(ctx["width"] / dpi, ctx["height"] / dpi), dpi=dpi)
        self.fig.patch.set_facecolor(self.theme.bg)
        portrait = ctx["height"] > ctx["width"]
        notes = list(ctx.get("notes") or [])
        margins, rect = dict(MARGINS_PORTRAIT if portrait else MARGINS), list(TIMELINE_RECT_PORTRAIT if portrait else TIMELINE_RECT)
        # 19.10.2026: הרבה שורות הערה (או מקורות בסיום) - הגרף וציר הזמן עולים כדי שלכל שורה יהיה NOTE_STEP. עד 3 שורות - כמו קודם
        lines = max(len(notes), len(ctx.get("credits") or []))
        lift = max(0.0, NOTE_MIN_Y + NOTE_STEP * (lines - 1) + NOTE_TOP_GAP - rect[1]) if lines > len(NOTE_Y) else 0.0
        margins["bottom"] += lift
        rect[1] += lift
        self.fig.subplots_adjust(**margins)
        self.tl = self.fig.add_axes((rect[0], rect[1], rect[2], rect[3]))
        self._add_logo(ctx.get("logo") or {})
        self.notes = [self.hit(self.fig.text(0.5, self._note_y(k, len(notes)), note, ha="center", fontsize=8.5, color=self.theme.muted), "path:notes")
                      for k, note in enumerate(notes)]
        self._dynamic: List[Any] = []
        self._retired: List[Any] = []
        self._fitted: Dict[Any, str] = {}   # ב16: שמות שהמקום שלהם קבוע - נמדדים פעם אחת
        self.setup_data_axes()
        self._header = self._build_header()
        self._build_timeline()

    def _add_logo(self, logo: Mapping[str, Any]) -> None:
        """גל 41: לוגו קבוע בפינה (מערכת ערוץ). בלי path - בלי שום שינוי בפריים."""
        path = logo.get("path")
        if not path:
            return
        import matplotlib.image as mpimg
        image = mpimg.imread(path)
        x, y, ha, va = LOGO_POSITIONS.get(str(logo.get("position")), LOGO_POSITIONS["top-left"])
        fig_w, fig_h = self.fig.get_size_inches()
        width = float(logo.get("scale") or 0.05)
        height = width * fig_w / fig_h * image.shape[0] / max(1, image.shape[1])
        left = x if ha == "left" else x - width
        bottom = y - height if va == "top" else y
        ax = self.fig.add_axes((left, bottom, width, height), zorder=20)
        ax.imshow(image, alpha=float(logo.get("opacity", 0.95)))
        ax.axis("off")

    def fmt(self, value: float) -> str:
        return format_number(value, self.numbers)

    # ------------------------------------------------------------ 27.10.2026: אזורי לחיצה בתצוגה החיה
    # רכיב שאפשר ללחוץ עליו בתצוגה (כותרת, ישות, תיבת הסיום, הערה) מסומן ב-gid "dvz:<מטרה>". המטרה: path:<נתיב בהגדרות>,
    # entity:<שם>, callout:<מספר ברשימה>, outro (גרירה), tab:<לשונית בעורך>. הסימון לא משנה אף פיקסל.
    @staticmethod
    def hit(artist: Any, target: str) -> Any:
        artist.set_gid("dvz:" + target)
        return artist

    def hit_regions(self) -> List[Dict[str, Any]]:
        """המלבנים של הרכיבים המסומנים בפריים האחרון שצויר - חלקים 0-1 של התמונה, מלמעלה-שמאל (כמו בדפדפן)."""
        renderer = self.fig.canvas.get_renderer()   # type: ignore[attr-defined]  # Agg
        width, height = self.fig.bbox.width, self.fig.bbox.height
        regions: List[Dict[str, Any]] = []
        artist: Any
        for artist in self.fig.findobj(lambda a: str(a.get_gid() or "").startswith("dvz:")):
            alpha = artist.get_alpha()
            if not artist.get_visible() or (alpha is not None and alpha < 0.2):
                continue
            patch = artist.get_bbox_patch() if hasattr(artist, "get_bbox_patch") else None
            try:
                if patch is not None:
                    artist.update_bbox_position_size(renderer)
                    box = patch.get_window_extent(renderer)
                else:
                    box = artist.get_window_extent(renderer)
            except (RuntimeError, ValueError, AttributeError):
                continue
            if box.width <= 0 or box.height <= 0:
                continue
            regions.append({"target": str(artist.get_gid())[4:],
                            "box": [round(max(0.0, box.x0 / width), 4), round(max(0.0, 1 - box.y1 / height), 4),
                                    round(min(1.0, box.x1 / width), 4), round(min(1.0, 1 - box.y0 / height), 4)]})
        return regions

    def fit_text(self, label: Any, lo: float = -math.inf, hi: float = math.inf, key: Any = None) -> None:
        """18.10.2026 (בקצה הקווים), 23.10.2026 (ב16 - גם בשאר התרשימים): טקסט שיוצא מהפריים (שם ארוך) נשבר לשורות עד
        שהוא בין lo ל-hi (פיקסלים מהשמאל), במקום להיחתך. טקסט שנכנס, או שכולו בחוץ - בלי שום שינוי. key: טקסט שהמקום
        שלו בפיקסלים לא זז בין הפריימים (השמות במרוץ העמודות) - נמדד פעם אחת."""
        if key is not None and key in self._fitted:
            label.set_text(self._fitted[key])
            return
        renderer = self.fig.canvas.get_renderer()   # type: ignore[attr-defined]  # Agg
        box = label.get_window_extent(renderer)
        if not ((box.x0 >= lo and box.x1 <= hi) or box.x1 <= lo or box.x0 >= hi):
            full = label.get_text()
            ha = label.get_horizontalalignment()
            middle = (box.x0 + box.x1) / 2
            room = box.x1 - lo if ha == "right" else hi - box.x0 if ha == "left" else 2 * min(middle - lo, hi - middle)
            chars = max(6, int(len(full) * room / box.width))
            while True:
                label.set_text("\n".join(textwrap.wrap(full, chars)))
                box = label.get_window_extent(renderer)
                if chars <= 6 or (box.x0 >= lo and box.x1 <= hi):
                    break
                chars = max(6, chars - max(1, chars // 10))
        if key is not None:
            self._fitted[key] = label.get_text()

    def whole_ticks(self, axis: Any) -> None:
        """סבב הייצוב: ציר ערכים בפורמט בלי ספרות אחרי הנקודה - רק שנתות שלמות. בטווח קטן (0 עד 1) השנתות 0.2, 0.4...
        הוצגו 0, 0, 0 (קטימה) או 0, 0, 1, 1 (עיגול). אותם צעדים כמו AutoLocator, אז בטווח רגיל השנתות לא זזות."""
        numbers = self.numbers or {}
        if numbers.get("style", "plain") == "plain" and not int(numbers.get("decimals") or 0):
            axis.set_major_locator(MaxNLocator(nbins="auto", steps=[1, 2, 2.5, 5, 10], integer=True))

    def draw_image(self, entity: Any, xy: Any, px: float, align: Any = (0, 0.5), alpha: float = 1.0) -> float:
        """גל 51: התמונה של הישות בנקודה xy (קואורדינטות הנתונים), בגובה px פיקסלים (כפול images.size).
        מחזיר את הרוחב בפיקסלים שהיא תפסה (0 = אין תמונה לישות)."""
        image = self._images.get(str(entity))
        if image is None or px <= 0:
            return 0.0
        from matplotlib.offsetbox import AnnotationBbox, OffsetImage
        size = px * self._image_scale
        zoom = size / image.shape[1] * 72 / self.fig.dpi      # OffsetImage מכפיל ב-dpi/72
        box = AnnotationBbox(OffsetImage(image, zoom=zoom, alpha=alpha), xy, box_alignment=align, frameon=False, pad=0,
                             annotation_clip=False, zorder=5)
        self.dyn(self.ax.add_artist(box))
        return size

    def move_text(self, entity: Any, frame: Mapping[str, Any]) -> tuple:
        """גל 49: (טקסט, צבע) של חץ הדירוג של הישות בפריים - ("", None) כשלא זזה או כשהחיצים כבויים."""
        move = (frame.get("moves") or {}).get(entity, 0)
        if not move:
            return "", None
        return (f"▲{move}", UP_COLOR) if move > 0 else (f"▼{-move}", DOWN_COLOR)

    # ------------------------------------------------------------ צבעים
    def color(self, entity: Any) -> Any:
        fixed = self._fixed_colors.get(str(entity))
        if fixed:
            return fixed
        if self._categorical:
            palette = self.theme.categorical
            return palette[self._index.get(entity, 0) % len(palette)]
        return self._cmap(self._positions.get(entity, 0.0))

    def swatch_color(self) -> Any:
        return self.theme.categorical[0] if self._categorical else self._cmap(self.theme.swatch_shade)

    def is_striped(self, entity: Any) -> bool:
        return self.textures.get(entity) == "stripes"

    # ------------------------------------------------------------ רכיבים קבועים
    def _note_y(self, k: int, n: int) -> float:
        """y של שורה k מתוך n שורות הערה. עד שתי שורות - בדיוק כמו קודם (NOTE_Y). 18.10.2026: משלוש ומעלה השורות
        נערמות מלמטה עד מתחת לציר הזמן - קודם השלישית ירדה ל-y שלילי, מתחת לתחתית הפריים, ונחתכה."""
        if n <= len(NOTE_Y):
            return NOTE_Y[k]
        top = self.tl.get_position().y0 - NOTE_TOP_GAP
        bottom = max(NOTE_MIN_Y, min(NOTE_Y[-1], top - NOTE_STEP * (n - 1)))
        return bottom + min(NOTE_STEP, (top - bottom) / (n - 1)) * (n - 1 - k)

    def _build_header(self) -> List[Any]:
        ax, th, ctx = self.ax, self.theme, self.ctx
        # סבב הייצוב: בגרסה בשפה שנכתבת משמאל לימין (ctx["ltr"]) הכותרת והמקרא משמאל, הסכום ב-0.60 והתאריך מימין.
        # בעברית - בדיוק כמו קודם
        ltr = bool(ctx.get("ltr"))
        side, align = (0.0, "left") if ltr else (1.0, "right")
        artists: List[Any] = [
            self.hit(ax.text(side, 1.165, ctx["title"], transform=ax.transAxes, ha=align, va="bottom", fontsize=self.style["title_size"],
                             fontweight="bold", color=th.ink), "path:title"),
        ]
        if ctx.get("subtitle"):
            artists.append(self.hit(ax.text(side, 1.105, ctx["subtitle"], transform=ax.transAxes, ha=align, va="bottom",
                                            fontsize=11, color=th.muted), "path:subtitle"))
        # מקרא: מלא / מרקם פסים (נתונים ברמת דיוק אחרת, למשל סיכום שנתי מול יומי)
        mid = to_rgb(self.swatch_color())
        legend = list(ctx.get("legend") or [])
        step = min(LEGEND_STEP, 0.9 / max(len(legend), 1))
        hatch_edge = (*th.hatch_rgb, 0.6)
        for k, (label, texture) in enumerate(legend):
            x_sw = (1 - LEGEND_X0 + 0.02 + step * k) if ltr else LEGEND_X0 - step * k   # הקצה הימני של הדוגמית
            artists.append(self.legend_swatch(x_sw, mid, texture == "stripes", hatch_edge))
            artists.append(ax.text(x_sw + 0.01 if ltr else x_sw - 0.03, 1.052, label, transform=ax.transAxes, ha="left" if ltr else "right",
                                   va="center", fontsize=9.5, color=th.muted))
        if ctx["labels"].get("total"):
            artists.append(self.hit(ax.text(self._total_x(), 1.205, ctx["labels"]["total"], transform=ax.transAxes, ha="center",
                                            va="bottom", fontsize=10, color=th.muted), "path:labels.total"))
        return artists

    def _total_x(self) -> float:
        return 0.60 if self.ctx.get("ltr") else 0.40

    def legend_swatch(self, x_sw: float, color: Any, striped: bool, hatch_edge: Any) -> Any:
        """דוגמית במקרא (ריבוע מלא או עם מרקם פסים). תרשים קווים מחליף אותה בקו."""
        ax = self.ax
        return ax.add_patch(Rectangle((x_sw - 0.02, 1.035), 0.02, 0.035, transform=ax.transAxes, clip_on=False,
                                      facecolor=color, edgecolor=hatch_edge if striped else "none",
                                      hatch="////" if striped else None, linewidth=0))

    def _build_timeline(self) -> None:
        tl, th, timeline = self.tl, self.theme, self.ctx["timeline"]
        tl.set_xlim(0, 1)
        tl.set_ylim(-2.4, 1.3)
        tl.axis("off")
        tl.plot([0, 1], [0, 0], color=th.grid, linewidth=3, solid_capstyle="round", zorder=1)
        (self._progress,) = tl.plot([0, 0], [0, 0], color=th.accent, linewidth=3, solid_capstyle="round", zorder=2)
        for xf, label in timeline["ticks"]:
            tl.plot([xf, xf], [-0.35, 0.35], color=th.muted, linewidth=1, zorder=2)
            tl.text(xf, -0.75, label, ha="center", va="top", fontsize=8.5, color=th.muted)
        self._event_dots = [(xf, tl.scatter([xf], [0], s=34, zorder=4, facecolor=th.bg, edgecolor=th.muted, linewidth=1.3))
                            for xf in timeline["events"]]
        span = max(len(self.ctx["dates"]) - 1, 1)
        for start, end, _label, color in self.ctx.get("periods") or []:   # גל 50: התקופות על ציר הזמן שבתחתית
            tl.add_patch(Rectangle((start / span, -0.34), max(end - start, 0.5) / span, 0.68, facecolor=color or th.accent,
                                   alpha=0.35, linewidth=0, zorder=1.5))
        self._now_dot = tl.scatter([0], [0], s=95, zorder=5, facecolor=th.card, edgecolor=th.accent, linewidth=2.4)

    # ------------------------------------------------------------ רכיבים משתנים
    def dyn(self, artist: Any) -> Any:
        """רושם רכיב של הפריים הנוכחי - נמחק בתחילת הפריים הבא."""
        self._dynamic.append(artist)
        return artist

    def _clear_dynamic(self) -> None:
        for artist in self._dynamic:
            artist.remove()
        # Agg זוכר את מסכת החיתוך האחרונה לפי הכתובת בזיכרון של מערך הקודקודים (lastclippath).
        # אם רכיבי הפריים הקודם משתחררים מיד, עמודה חדשה יכולה לקבל את אותה כתובת - וכשהציר לא
        # זז (אותה טרנספורמציה) Agg משתמש במסכה הישנה: עמודה קצרה וחתוכה. ax.clear() במקור השאיר
        # אותם בחיים עד איסוף-הזבל, אז שם זה לא קרה. לכן מחזיקים את הרכיבים עם מסכת החיתוך
        # מהפריים האחרון שהיו בו כאלה (פריים בלי עמודות לא מחליף את המסכה השמורה ב-Agg).
        clipped = [a for a in self._dynamic if a.get_clip_path() is not None]
        if clipped:
            self._retired = clipped
        self._dynamic = []

    def draw_header(self, date_text: str, year_mark: Any, total: float) -> None:
        ax, th = self.ax, self.theme
        if date_text:
            ltr = bool(self.ctx.get("ltr"))   # סבב הייצוב: בגרסה משמאל לימין התאריך מימין
            self.dyn(ax.text(1.0 if ltr else 0.0, 1.10, date_text, transform=ax.transAxes, ha="right" if ltr else "left", va="bottom",
                             fontsize=22, fontweight="bold", color=th.accent))
        if self.ctx["labels"].get("total"):
            self.dyn(ax.text(self._total_x(), 1.095, self.fmt(total), transform=ax.transAxes, ha="center", va="bottom",
                             fontsize=27, fontweight="bold", color=th.ink))
        if year_mark is not None and self.ctx.get("year_mark", True) and self.style.get("year_mark", True):
            self.dyn(ax.text(0.975, 0.015, str(year_mark), transform=ax.transAxes, ha="right", va="bottom",
                             fontsize=100, fontweight="bold", color=th.ink, alpha=0.06, zorder=1))

    def draw_timeline(self, frac: float) -> None:
        th = self.theme
        self._progress.set_data([0, frac], [0, 0])
        for xf, dot in self._event_dots:
            passed = xf <= frac
            dot.set_facecolor(th.accent if passed else th.bg)
            dot.set_edgecolor(th.accent if passed else th.muted)
        self._now_dot.set_offsets([[frac, 0]])

    def draw_card(self, card: Any) -> None:
        name, date, al = card
        th = self.theme
        x, y, ha, va = self.CARD_AT
        self.hit(self.dyn(self.ax.text(x, y, f"{name}\n{date}", transform=self.ax.transAxes, ha=ha, va=va,
                                       fontsize=19, fontweight="bold", color=th.accent, alpha=al, linespacing=1.5, zorder=6,
                                       bbox=dict(boxstyle="round,pad=0.8", facecolor=th.card, edgecolor=th.accent, linewidth=1.6, alpha=al))),
                 "tab:events")

    def draw_toast(self, toast: Any) -> None:
        text, al = toast
        th = self.theme
        x, y, ha, va = self.TOAST_AT
        self.dyn(self.ax.text(x, y, text, transform=self.ax.transAxes, ha=ha, va=va, fontsize=15,
                              fontweight="bold", color=th.on_accent, alpha=al, zorder=6,
                              bbox=dict(boxstyle="round,pad=0.5", facecolor=th.accent, edgecolor="none", alpha=al)))

    def draw_intro(self, frame: Mapping[str, Any]) -> None:
        ax, th, intro = self.ax, self.theme, self.ctx["intro"]
        t = frame["t"]
        a = min(1.0, t / 0.25, (1 - t) / 0.2)
        self.hit(self.dyn(ax.text(0.5, 0.60, intro.get("title") or self.ctx["title"], transform=ax.transAxes, ha="center",
                                  va="center", fontsize=46, fontweight="bold", color=th.ink, alpha=a)), "path:intro.title")
        if intro.get("subtitle"):
            self.hit(self.dyn(ax.text(0.5, 0.46, intro["subtitle"], transform=ax.transAxes, ha="center", va="center",
                                      fontsize=22, color=th.muted, alpha=a)), "path:intro.subtitle")
        if intro.get("question"):
            self.hit(self.dyn(ax.text(0.5, 0.36, intro["question"], transform=ax.transAxes, ha="center", va="center",
                                      fontsize=22, fontweight="bold", color=th.accent, alpha=a)), "path:intro.question")

    def draw_outro_box(self, frame: Mapping[str, Any]) -> None:
        th, outro = self.theme, self.ctx["outro"]
        al = min(1.0, frame["t"] / 0.2)
        lines = ([outro["title"]] if outro.get("title") else []) + [f"{place}: {e}" for place, (e, _) in zip(outro["places"], frame["top"])]
        x, y, ha, va = self.OUTRO_AT
        # 27.10.2026: outro.position - המקום שהמשתמש גרר אליו את התיבה בתצוגה (מרכז התיבה, חלקים של אזור הנתונים)
        placed = _point(outro.get("position"))
        ma = "left" if self.ctx.get("ltr") else ha
        if placed:
            (x, y), ha, va = placed, "center", "center"
        # סבב הייצוב: בגרסה משמאל לימין השורות בתיבה מיושרות לשמאל (התיבה נשארת באותו מקום)
        self.hit(self.dyn(self.ax.text(x, y, "\n".join(lines), transform=self.ax.transAxes, ha=ha, va=va, ma=ma,
                                       fontsize=17, fontweight="bold", color=th.ink, alpha=al, linespacing=1.6, zorder=6,
                                       bbox=dict(boxstyle="round,pad=0.9", facecolor=th.card, edgecolor=th.ink, linewidth=1.4, alpha=al))),
                 "outro")
        if self.OUTRO_SPOTS_FREE_OF_TEXT and not placed:
            self._move_outro_off_text(self._dynamic[-1])

    # 25.10.2026: מקומות חלופיים לתיבת הסיום (כמו OUTRO_AT) כשבמקום הקבוע היא מכסה טקסט של הנתונים (מספר בקצה
    # עמודה). הראשון שלא מכסה כלום - ואם אין כזה, זה שמכסה הכי מעט. ריק = התיבה תמיד ב-OUTRO_AT, כמו קודם
    OUTRO_SPOTS_FREE_OF_TEXT: Tuple[Tuple[float, float, str, str], ...] = ()

    def _move_outro_off_text(self, box_text: Any) -> None:
        renderer = self.fig.canvas.get_renderer()   # type: ignore[attr-defined]  # Agg
        # שנת הרקע (alpha 0.06) היא רקע ולא טקסט שצריך לקרוא - התיבה יכולה לשבת עליה
        others = [t.get_window_extent(renderer) for t in self.ax.texts if t is not box_text and t.get_visible() and t.get_text().strip()
                  and (t.get_alpha() or 1.0) >= 0.3]

        def covered(spot: Tuple[float, float, str, str]) -> float:
            x, y, ha, va = spot
            box_text.set_position((x, y))
            box_text.set_horizontalalignment(ha)
            box_text.set_verticalalignment(va)
            box_text.update_bbox_position_size(renderer)
            box = box_text.get_bbox_patch().get_window_extent(renderer)
            return sum(max(0.0, min(box.x1, o.x1) - max(box.x0, o.x0)) * max(0.0, min(box.y1, o.y1) - max(box.y0, o.y0)) for o in others)

        best: Tuple[float, Tuple[float, float, str, str]] | None = None
        for spot in (self.OUTRO_AT, *self.OUTRO_SPOTS_FREE_OF_TEXT):
            area = covered(spot)
            if best is None or area < best[0]:
                best = (area, spot)
            if area == 0:
                break
        assert best is not None
        covered(best[1])

    # ------------------------------------------------------------ גל 50: הסיפור
    def draw_periods(self, x: float) -> None:
        """תקופה מוצללת שהיום הנוכחי בתוכה - תגית בפינה (תרשים עם ציר זמן מצייר אותה על הציר עצמו)."""
        th = self.theme
        ltr = bool(self.ctx.get("ltr"))   # נ11: בגרסה משמאל לימין המקרא משמאל - התגית עוברת לימין
        for start, end, label, color in self.ctx.get("periods") or []:
            if start <= x <= end:
                self.dyn(self.ax.text(1.0 if ltr else 0.0, 1.035, label, transform=self.ax.transAxes, ha="right" if ltr else "left", va="center", fontsize=10,
                                      fontweight="bold", color=th.on_accent, zorder=6,
                                      bbox=dict(boxstyle="round,pad=0.35", facecolor=color or th.accent, edgecolor="none", alpha=0.9)))
                return

    def callout_anchor(self, entity: Any, frame: Mapping[str, Any]) -> Any:
        """(נקודה בקואורדינטות הנתונים, היסט בנקודות, יישור) שהערה לישות מצביעה ממנו, או None - ואז ההערה בפינה."""
        return None

    def focus(self, entity: Any, frame: Mapping[str, Any]) -> float:
        """20.10.2026: מצב פוקוס - 1 לישות בפוקוס (או כשאין פוקוס), focus_dim לשאר. רשימת פוקוס ריקה ברגע מסוים = כולן בפוקוס."""
        names = frame.get("focus")
        if not names or str(entity) in names:
            return 1.0
        return float(frame.get("focus_dim", 0.25))

    def draw_annotations(self, frame: Mapping[str, Any]) -> None:
        """20.10.2026: הערות על הגרף (story.annotations) - חץ מהטקסט לנקודה (יום, ערך). רק בתרשימים שבהם x הוא זמן ו-y
        ערך (ANNOTATES: קווים ושטח מוערם); בשאר אין "נקודה" במובן הזה, וההערה לא מצוירת."""
        if not self.ANNOTATES:
            return
        th = self.theme
        for day, value, text, dx, dy, style, al in frame.get("annotations") or []:
            al = max(0.0, min(1.0, al))
            color = {"accent": th.accent, "muted": th.muted}.get(style, th.ink)
            box = dict(boxstyle="round,pad=0.35", facecolor=th.card, edgecolor=color, linewidth=1.2, alpha=al)
            self.dyn(self.ax.annotate(text, (day, value), xytext=(dx, dy), textcoords="offset points", ha="center", va="center",
                                      fontsize=11.5, color=color, alpha=al, zorder=8, annotation_clip=False, bbox=box,
                                      arrowprops=dict(arrowstyle="-|>", color=color, alpha=al, linewidth=1.3, shrinkA=2, shrinkB=3)))

    def draw_callouts(self, frame: Mapping[str, Any]) -> None:
        ax, th = self.ax, self.theme
        corner = 0
        for entity, text, al, *rest in frame.get("callouts") or []:
            # 27.10.2026: (..., מספר ההערה ברשימה, dx, dy) - dx/dy כשהמשתמש גרר את ההערה בתצוגה (נקודות, כמו בהערה על הגרף)
            index, dx, dy = (rest + [None, None, None])[:3]
            target = f"callout:{index}" if index is not None else "tab:story"
            al = max(0.0, min(1.0, al))
            box = dict(boxstyle="round,pad=0.4", facecolor=th.card, edgecolor=self.color(entity), linewidth=1.4, alpha=al)
            anchor = self.callout_anchor(entity, frame)
            if anchor is None:
                self.hit(self.dyn(ax.text(0.02, 0.86 - 0.09 * corner, f"{entity}: {text}", transform=ax.transAxes, ha="left", va="top",
                                          fontsize=12, color=th.ink, alpha=al, zorder=7, bbox=box)), target)
                corner += 1
                continue
            point, offset, ha = anchor
            if dx is not None and dy is not None:
                offset = (dx, dy)
            if index is not None:   # ההיסט הנוכחי באזור הלחיצה - גרירה בתצוגה מזיזה ממנו
                target = f"callout:{index}:{int(offset[0])}:{int(offset[1])}"
            self.hit(self.dyn(ax.annotate(text, point, xytext=offset, textcoords="offset points", ha=ha, va="center", fontsize=12,
                                          color=th.ink, alpha=al, zorder=7, annotation_clip=False, bbox=box,
                                          arrowprops=dict(arrowstyle="-", color=th.muted, alpha=al, linewidth=1.2))), target)

    def draw_hold(self, hold: Mapping[str, Any]) -> None:
        """פריים קפוא: פרק = כרטיס כותרת על כל הפריים; עצירה = הסבר למעלה. כניסה ויציאה הדרגתיות."""
        ax, th = self.ax, self.theme
        t = float(hold.get("t", 0.5))
        a = max(0.0, min(1.0, t / 0.15, (1 - t) / 0.15))
        if hold.get("kind") == "chapter":
            # 27.10.2026: story.chapter_transition - איך כרטיס הפרק נכנס ויוצא. fade (ברירת המחדל) - בדיוק כמו קודם
            style = str(self.ctx.get("chapter_transition") or "fade")
            rise, size, cover = 0.0, 1.0, (0.0, 1.0)
            if style == "slide":
                rise = -0.12 * (1 - a)              # הכותרת עולה למקום מלמטה
            elif style == "zoom":
                size = 0.7 + 0.3 * a                # הכותרת גדלה למקום
            elif style == "wipe":
                cover = (1.0 - a, a)                # הרקע נמתח מימין לשמאל, אטום
            self.dyn(ax.add_patch(Rectangle((cover[0], 0), cover[1], 1, transform=self.fig.transFigure, facecolor=th.bg,
                                            alpha=0.88 if style == "wipe" else 0.88 * a, linewidth=0, zorder=30, clip_on=False)))
            self.hit(self.dyn(ax.text(0.5, 0.56 + rise, hold.get("title", ""), transform=ax.transAxes, ha="center", va="center", fontsize=40 * size,
                                      fontweight="bold", color=th.ink, alpha=a, zorder=31)), "tab:story")
            if hold.get("subtitle"):
                self.dyn(ax.text(0.5, 0.42 + rise, hold["subtitle"], transform=ax.transAxes, ha="center", va="center", fontsize=20 * size,
                                 color=th.muted, alpha=a, zorder=31))
            return
        if hold.get("kind") == "invite":
            # סבב הייצוב: ההזמנה בסוף ה-Short - כרטיס סיום במרכז מעל פריים מעומעם (למעלה היא כיסתה את עמודת המוביל).
            # רק כניסה הדרגתית - היא נשארת עד הפריים האחרון
            a = min(1.0, t / 0.15)
            self.dyn(ax.add_patch(Rectangle((0, 0), 1, 1, transform=self.fig.transFigure, facecolor=th.bg, alpha=0.6 * a,
                                            linewidth=0, zorder=30, clip_on=False)))
            self.dyn(ax.text(0.5, 0.5, str(hold.get("text", "")), transform=self.fig.transFigure, ha="center", va="center", fontsize=22,
                             fontweight="bold", color=th.ink, alpha=a, zorder=31, fontfamily=with_symbol_font(th.fonts),
                             bbox=dict(boxstyle="round,pad=0.8", facecolor=th.card, edgecolor=th.accent, linewidth=2, alpha=a)))
            return
        self.hit(self.dyn(ax.text(0.5, 0.95, "⏸ " + str(hold.get("text", "")), transform=ax.transAxes, ha="center", va="top", fontsize=17,
                                  fontweight="bold", color=th.ink, alpha=a, zorder=8, linespacing=1.4, fontfamily=with_symbol_font(th.fonts),
                                  bbox=dict(boxstyle="round,pad=0.7", facecolor=th.card, edgecolor=th.accent, linewidth=1.6, alpha=a))),
                 "tab:story")

    def draw_teaser(self, label: str) -> None:
        if label:
            th = self.theme
            self.dyn(self.ax.text(0.5, 0.97, "⏩ " + label, transform=self.ax.transAxes, ha="center", va="top", fontsize=15,
                                  fontweight="bold", color=th.on_accent, zorder=8, fontfamily=with_symbol_font(th.fonts),
                                  bbox=dict(boxstyle="round,pad=0.5", facecolor=th.accent, edgecolor="none")))

    def draw_end_screen(self, frame: Mapping[str, Any]) -> None:
        """מסך סיום ליוטיוב: הגרף מתעמעם, המקומות הראשונים בפינה העליונה, והחצי הימני והפינה התחתונה נשארים פנויים
        לסרטונים ולכפתור ההרשמה שיוטיוב מוסיף. guides מצייר את המקומות האלה בקו מקווקו (לבדיקה בלבד)."""
        ax, th, outro = self.ax, self.theme, self.ctx["outro"]
        settings = self.ctx.get("end_screen") or {}
        a = min(1.0, float(frame.get("end_screen") or 0) / 0.05)
        self.dyn(ax.add_patch(Rectangle((0, 0), 1, 1, transform=self.fig.transFigure, facecolor=th.bg, alpha=0.8 * a,
                                        linewidth=0, zorder=30, clip_on=False)))
        lines = ([outro["title"]] if outro.get("title") else []) + [f"{place}: {e}" for place, (e, _) in zip(outro["places"], frame["top"])]
        self.dyn(ax.text(0.04, 0.95, "\n".join(lines), transform=self.fig.transFigure, ha="left", va="top", fontsize=15,
                         fontweight="bold", color=th.ink, linespacing=1.5, zorder=31, clip_on=False,
                         bbox=dict(boxstyle="round,pad=0.8", facecolor=th.card, edgecolor=th.ink, linewidth=1.2)))
        if settings.get("text"):
            self.hit(self.dyn(ax.text(0.04, 0.55, settings["text"], transform=self.fig.transFigure, ha="left", va="top", fontsize=20,
                                      fontweight="bold", color=th.accent, zorder=31, clip_on=False)), "path:end_screen.text")
        if settings.get("guides"):
            for x0, y0, w, h in ((0.52, 0.52, 0.42, 0.32), (0.52, 0.12, 0.42, 0.32)):
                self.dyn(ax.add_patch(Rectangle((x0, y0), w, h, transform=self.fig.transFigure, facecolor="none", edgecolor=th.muted,
                                                linestyle="--", linewidth=1.5, zorder=32, clip_on=False)))
            fig_w, fig_h = self.fig.get_size_inches()
            self.dyn(ax.add_patch(Ellipse((0.2, 0.22), 0.14 * fig_h / fig_w, 0.14, transform=self.fig.transFigure, facecolor="none",
                                          edgecolor=th.muted, linestyle="--", linewidth=1.5, zorder=32, clip_on=False)))

    def draw_credits(self) -> None:
        """מקורות הנתונים (outro.credits) בסיום - במקום ההערות שבתחתית."""
        credits = self.ctx.get("credits") or []
        if not credits:
            return
        for note in self.notes:
            note.set_visible(False)
        for k, line in enumerate(credits):
            self.hit(self.dyn(self.ax.text(0.5, self._note_y(k, len(credits)), line, transform=self.fig.transFigure, ha="center", fontsize=8.5,
                                           color=self.theme.muted, clip_on=False, zorder=33)), "path:outro.credits")

    # ------------------------------------------------------------ אזור הנתונים (לכל תרשים)
    def setup_data_axes(self) -> None:
        """הגדרות קבועות של הציר הראשי (נקרא פעם אחת)."""

    def set_data_visible(self, visible: bool) -> None:
        """מסתיר/מציג רכיבים קבועים של אזור הנתונים (באינטרו)."""

    def draw_data(self, frame: Mapping[str, Any], highlight_current: bool) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------ פריים
    def render(self, frame: Mapping[str, Any]) -> bytes:
        self._clear_dynamic()
        kind = frame["k"]
        chrome = kind != "intro"
        for note in self.notes:
            note.set_visible(chrome)
        self.tl.set_visible(chrome)
        for artist in self._header:
            artist.set_visible(chrome)
        self.set_data_visible(chrome)
        if kind == "intro":
            self.ax.set_axis_off()
            self.draw_intro(frame)
        elif kind == "main":
            self.ax.set_axis_on()
            self.draw_data(frame, highlight_current=True)
            self.draw_header(frame["date"], frame.get("year"), frame["total"])
            self.draw_timeline(frame["frac"])
            if frame.get("card"):
                self.draw_card(frame["card"])
            if frame.get("toast"):
                self.draw_toast(frame["toast"])
            self.draw_periods(float(frame["x"]))
            if frame.get("callouts"):
                self.draw_callouts(frame)
            if frame.get("annotations"):
                self.draw_annotations(frame)
            if frame.get("hold"):
                self.draw_hold(frame["hold"])
            if frame.get("teaser"):
                self.draw_teaser(str(frame["teaser"]))
        else:
            self.ax.set_axis_on()
            self.draw_data(frame, highlight_current=False)
            self.draw_header("", None, frame["total"])
            self.draw_timeline(frame["frac"])
            self.draw_periods(float(frame["x"]))
            if frame.get("end_screen") is not None:
                self.draw_end_screen(frame)
            else:
                self.draw_outro_box(frame)
            self.draw_credits()
        self.fig.canvas.draw()
        return np.asarray(self.fig.canvas.buffer_rgba()).tobytes()  # type: ignore[attr-defined]  # Agg

    def save_png(self, path: str) -> None:
        self.fig.savefig(path, facecolor=self.theme.bg)

    def close(self) -> None:
        plt.close(self.fig)

    @property
    def size(self) -> tuple:
        w, h = (int(v) for v in self.fig.get_size_inches() * self.fig.dpi)
        return w, h
