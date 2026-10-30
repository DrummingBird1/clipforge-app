# utils.video.video_editor_scale - split out of the original module (no behavior change); the original module re-exports every name.

from typing import Any, Dict, List, Optional, Tuple
import re

from utils.media.timelapse import HORIZONTAL_SCALE_CHAIN, HORIZONTAL_SCALE_CHAIN_CUDA, VERTICAL_SCALE_CHAIN, VERTICAL_SCALE_CHAIN_CUDA
from utils.video.video_editor_fps_hdr import HDR_TONEMAP_FILTER
from utils.video.video_editor_naming import OUTPUT_DIMENSIONS


def resolve_scale_chain(
    vertical: bool,
    use_hwaccel: bool = False,
    crop_x_offset: Optional[float] = None,
    target_width: Optional[int] = None,
    target_height: Optional[int] = None,
) -> str:
    """crop_x_offset (item: smart crop, -1.0..1.0 מ-utils.media.smart_crop's
    compute_horizontal_crop_offset) מזיז את חלון הקרופ האנכי מהמרכז - רלוונטי
    רק ל-vertical (האופקי משתמש ב-pad, לא crop, אין ממנו מה "להזיז"). 0.0/None
    שקולים ל"בלי שינוי" (התנהגות המרכז המקורית) בכוונה, לא רק אופטימיזציה -
    הנוסחה למטה כבר מפיקה בדיוק את אותה תוצאה במקרה הזה.

    target_width/target_height (item: --preserve-resolution) - כשניתנים
    ושונים ממידות הפלט הקבועות (resolve_output_dimensions), מחליפים את
    המספרים הקבועים (1920/1080 או 1080/1920) בתבנית ה-chain במידות בפועל -
    כל שרשרת (אופקית/אנכית, CPU/CUDA) משתמשת בכל אחד מהמספרים הקבועים האלה
    בדיוק פעמיים (scale+pad או scale+crop) ובשום מקום אחר, אז replace גורף
    בטוח. None/זהה למידות הקבועות (ברירת המחדל) לא משנה כלום - זהה בדיוק
    להתנהגות הקודמת."""
    default_w, default_h = resolve_output_dimensions(vertical)
    target_w = target_width if target_width else default_w
    target_h = target_height if target_height else default_h
    if use_hwaccel:
        chain = VERTICAL_SCALE_CHAIN_CUDA if vertical else HORIZONTAL_SCALE_CHAIN_CUDA
    else:
        chain = VERTICAL_SCALE_CHAIN if vertical else HORIZONTAL_SCALE_CHAIN
    if (target_w, target_h) != (default_w, default_h):
        chain = chain.replace(str(default_w), str(target_w)).replace(str(default_h), str(target_h))
    if vertical and crop_x_offset:
        # (in_w-target_w)/2 הוא ה"מרחב" הזמין להזזה מהמרכז לכל כיוון (הפרש בין
        # הרוחב אחרי scale=...:increase, שתמיד >= target_w, לבין רוחב הפלט) -
        # offset=-1.0 מזיז את חלון הקרופ עד הקצה השמאלי לגמרי, +1.0 עד הקצה
        # הימני לגמרי.
        chain = chain.replace(
            f"crop={target_w}:{target_h}",
            f"crop={target_w}:{target_h}:x=(in_w-{target_w})/2*(1+{crop_x_offset:.4f}):y=(in_h-{target_h})/2",
        )
    return chain


def resolve_output_dimensions(vertical: bool) -> Tuple[int, int]:
    return OUTPUT_DIMENSIONS[bool(vertical)]


# --- גל 7 של 102-ההצעות: יחסי-רוחב, רזולוציה, אלגוריתם scale, צבע, סיבוב ---

# item 75: יחסי-רוחב נוספים - הצלע הקצרה 1080 (כמו 16:9/9:16 הקיימים).
ASPECT_PRESETS: Dict[str, Tuple[int, int]] = {
    "16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "4:3": (1440, 1080),
}


# item 78: פריסטים של רזולוציה - גובה/צלע-קצרה של הפלט.
RESOLUTION_SHORT_SIDE: Dict[str, int] = {"720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}


SCALE_ALGORITHMS: Tuple[str, ...] = ("bicubic", "lanczos", "bilinear", "spline", "neighbor", "area")


FIT_MODES: Tuple[str, ...] = ("auto", "crop", "pad")


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def resolve_aspect_dimensions(aspect: Optional[str], custom_width: Optional[int] = None, custom_height: Optional[int] = None) -> Optional[Tuple[int, int]]:
    """מידות פלט ליחס-רוחב שנבחר, או None (= ההתנהגות הרגילה לפי --vertical).
    "custom" דורש רוחב+גובה חיוביים (מעוגלים לזוגי - דרישת 4:2:0)."""
    if not aspect:
        return None
    if aspect == "custom":
        if not custom_width or not custom_height or custom_width <= 0 or custom_height <= 0:
            raise ValueError("יחס 'custom' דורש --custom-width ו---custom-height חיוביים")
        return _even(custom_width), _even(custom_height)
    if aspect not in ASPECT_PRESETS:
        raise ValueError(f"יחס-רוחב לא מוכר: {aspect!r} (אפשרויות: {', '.join(ASPECT_PRESETS)}, custom)")
    return ASPECT_PRESETS[aspect]


def apply_resolution_preset(dimensions: Tuple[int, int], preset: Optional[str]) -> Tuple[int, int]:
    """מקטין/מגדיל כך שהצלע הקצרה = הפריסט (720p/1080p/...), שומר יחס. None/"auto" = ללא שינוי."""
    if not preset or preset == "auto":
        return dimensions
    if preset not in RESOLUTION_SHORT_SIDE:
        raise ValueError(f"פריסט רזולוציה לא מוכר: {preset!r}")
    width, height = dimensions
    factor = RESOLUTION_SHORT_SIDE[preset] / min(width, height)
    return _even(width * factor), _even(height * factor)


def orientation_for_dimensions(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "vertical" if height > width else "horizontal"


def build_fit_scale_chain(width: int, height: int, fit: str = "auto", crop_x_offset: Optional[float] = None, pad_color: str = "black") -> str:
    """שרשרת scale ליחס-רוחב כלשהו (item 75). fit="crop" ממלא את המסגרת וחותך
    עודפים (כמו --vertical), "pad" מכניס את כל הפריים עם שוליים (כמו האופקי),
    "auto" = crop לאנכי/ריבוע ו-pad לאופקי (בדיוק כמו שני המצבים הקיימים)."""
    mode = fit if fit in ("crop", "pad") else ("pad" if width > height else "crop")
    if mode == "pad":
        return f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}"
    if crop_x_offset:
        return (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:x=(in_w-{width})/2*(1+{crop_x_offset:.4f}):y=(in_h-{height})/2")
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"


def apply_scale_algorithm(chain: str, algorithm: Optional[str]) -> str:
    """item 78: אלגוריתם scale - מוסיף :flags=<algo> לכל scale= של CPU בשרשרת
    (לא scale_cuda, שאין לו את אותה אופציה). None/"bicubic" (ברירת המחדל של ffmpeg) = ללא שינוי."""
    if not chain or not algorithm or algorithm == "bicubic":
        return chain
    if algorithm not in SCALE_ALGORITHMS:
        raise ValueError(f"אלגוריתם scale לא מוכר: {algorithm!r}")
    return re.sub(r"(?<![_\w])scale=([^,\[;]+)", lambda m: f"scale={m.group(1)}:flags={algorithm}", chain)


def apply_pad_color(chain: str, color: Optional[str]) -> str:
    """item 89: צבע letterbox - מוסיף :color= לכל pad= של CPU בשרשרת שעוד אין לו צבע."""
    if not chain or not color or color.lower() in ("black", "0x000000", "#000000"):
        return chain
    return re.sub(r"(?<![_\w])pad=([^,\[;]+)", lambda m: m.group(0) if ":color=" in m.group(0) else f"pad={m.group(1)}:color={color}", chain)


# item 84: רמות הפחתת-רעש/חידוד + אלגוריתם tone-mapping.
DENOISE_LEVELS: Dict[str, str] = {"light": "hqdn3d=2:1.5:3:2.25", "medium": "hqdn3d", "strong": "hqdn3d=8:6:12:9"}


SHARPEN_LEVELS: Dict[str, str] = {"light": "unsharp=5:5:0.5", "medium": "unsharp", "strong": "unsharp=5:5:1.8"}


TONEMAP_ALGORITHMS: Tuple[str, ...] = ("hable", "mobius", "reinhard")


def build_tonemap_filter(algorithm: str = "hable") -> str:
    if algorithm not in TONEMAP_ALGORITHMS:
        raise ValueError(f"אלגוריתם tone-mapping לא מוכר: {algorithm!r}")
    return HDR_TONEMAP_FILTER.replace("tonemap=tonemap=hable", f"tonemap=tonemap={algorithm}")


def build_eq_filter(brightness: float = 0.0, contrast: float = 1.0, saturation: float = 1.0, gamma: float = 1.0) -> str:
    """item 74: בהירות/ניגודיות/רוויה/גמא בלי LUT (ffmpeg eq). רק ערכים שאינם
    ברירת-מחדל נכללים; "" אם כולם ברירת-מחדל (אין צורך בפילטר בכלל)."""
    parts = []
    for name, value, default in (("brightness", brightness, 0.0), ("contrast", contrast, 1.0), ("saturation", saturation, 1.0), ("gamma", gamma, 1.0)):
        if abs(value - default) >= 0.001:
            parts.append(f"{name}={value:.3f}")
    return "eq=" + ":".join(parts) if parts else ""


def build_orientation_filters(rotate: int = 0, flip: str = "none") -> List[str]:
    """item 83: סיבוב 90/180/270 ומראה - שלבים לתחילת השרשרת."""
    filters: List[str] = []
    if rotate == 90:
        filters.append("transpose=1")
    elif rotate == 180:
        filters += ["hflip", "vflip"]
    elif rotate == 270:
        filters.append("transpose=2")
    elif rotate not in (0, None):
        raise ValueError("סיבוב חייב להיות 0/90/180/270")
    if flip in ("h", "both"):
        filters.append("hflip")
    if flip in ("v", "both"):
        filters.append("vflip")
    return filters


# --- גל 10: פייפליין GPU היברידי ---
# עם פילטרי CPU (צבע/טקסט/שכבות/סיבוב) הפייפליין המלא נופל ל"פענוח מואץ בלבד":
# הפריים המפוענח יורד ל-CPU מיד, ברזולוציית המקור (למשל 4K), וכל הסינון רץ שם.
# ההיברידי עושה קודם על ה-GPU את מה שיש לו פילטר CUDA - deinterlace, סיבוב/מראה
# והקטנה מוקדמת לגודל שמכסה את הפלט - ורק אז מוריד ל-CPU, שמעבד פריים קטן פי כמה.
CUDA_ORIENTATION_DIRS: Dict[str, str] = {"transpose=1": "clock", "transpose=2": "cclock", "hflip": "hflip", "vflip": "vflip"}


HYBRID_PRESCALE_MAX_RATIO = 0.95  # הקטנה מתחת ל-5% לא שווה מעבר נוסף על ה-GPU


def _even_ceil(value: float) -> int:
    return max(2, int(-(-value // 2)) * 2)


def build_hybrid_gpu_prefix(
    orientation_filters: Optional[List[str]],
    deinterlace: bool,
    source_width: Optional[int],
    source_height: Optional[int],
    output_width: Optional[int],
    output_height: Optional[int],
    allow_prescale: bool = True,
    available_filters: Optional[Any] = None,
) -> Tuple[List[str], bool, bool]:
    """-> (פילטרי CUDA לפני ה-hwdownload, הסיבוב עבר ל-GPU?, ה-deinterlace עבר ל-GPU?).

    source_width/height הן המידות *אחרי* הסיבוב (כמו שהרנדרר כבר מחשב), כי
    ה-scale_cuda בא אחרי ה-transpose_cuda. ההקטנה המוקדמת היא לגודל "כיסוי" (הצלע
    הקצרה-יחסית נוגעת בפלט) - כך גם קרופ וגם שוליים ב-CPU ממשיכים מאותה נקודה
    והפלט זהה בגיאומטריה. allow_prescale=False כשיש פילטר CPU שעובד בקואורדינטות
    המקור (delogo/ייצוב/כרומה-קי/רקע מטושטש). הקטנה לא נעשית אם הסיבוב או
    ה-deinterlace נשארו ב-CPU (אחרת הם היו רצים על פריים מוקטן/לא-מסובב)."""
    available = set(available_filters) if available_filters is not None else {"transpose_cuda", "bwdif_cuda", "scale_cuda"}
    gpu: List[str] = []
    deinterlace_on_gpu = bool(deinterlace) and "bwdif_cuda" in available
    if deinterlace_on_gpu:
        gpu.append("bwdif_cuda")
    orientation = list(orientation_filters or [])
    orientation_on_gpu = bool(orientation) and "transpose_cuda" in available and all(f in CUDA_ORIENTATION_DIRS for f in orientation)
    if orientation_on_gpu:
        dirs = [CUDA_ORIENTATION_DIRS[f] for f in orientation]
        if dirs[:2] == ["hflip", "vflip"]:  # 180° = חצי-סיבוב במעבר אחד
            dirs = ["reversal", *dirs[2:]]
        gpu += [f"transpose_cuda=dir={d}" for d in dirs]
    geometry_ok = (not orientation or orientation_on_gpu) and (not deinterlace or deinterlace_on_gpu)
    if (allow_prescale and geometry_ok and "scale_cuda" in available
            and source_width and source_height and output_width and output_height):
        cover = max(output_width / source_width, output_height / source_height)
        if cover < HYBRID_PRESCALE_MAX_RATIO:
            width = max(output_width, _even_ceil(source_width * cover))
            height = max(output_height, _even_ceil(source_height * cover))
            gpu.append(f"scale_cuda=w={width}:h={height}:interp_algo=lanczos")
    return gpu, orientation_on_gpu, deinterlace_on_gpu


def parse_cuda_filters(filters_listing: str) -> List[str]:
    """שמות פילטרי ה-CUDA מתוך הפלט של `ffmpeg -filters` (שורה: ' T. bwdif_cuda  V->V ...')."""
    names = []
    for line in filters_listing.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].endswith("_cuda"):
            names.append(parts[1])
    return names


def resolve_effective_output_dimensions(
    vertical: bool,
    preserve_resolution: bool,
    input_width: Optional[int],
    input_height: Optional[int],
) -> Tuple[int, int]:
    """item: --preserve-resolution - לא להקטין (או להגדיל) רזולוציית וידאו
    לרזולוציית הפלט הקבועה (1920x1080/1080x1920), אלא לשמר את רזולוציית
    המקור. preserve_resolution=False, או שמידות הקלט לא ידועות (None) -
    מחזיר את מידות הפלט הקבועות כרגיל (זהה להתנהגות הקודמת).

    אופקי (not vertical): מחזיר את מידות הקלט *כמו שהן* (מעוגלות לזוגי - קודקים
    דורשים מימדים זוגיים ל-4:2:0 chroma subsampling) - הפלט לא נחתך/נמרח
    לכפות יחס 16:9, ה-scale/pad chain יוצא no-op בפועל (should_skip_scale
    יזהה את זה ברוב המקרים כי היעד=הקלט בדיוק).

    אנכי (vertical): המרה ל-9:16 היא המטרה המוצהרת של --vertical עצמו, אז
    ה"שימור" כאן הוא רק שלא להקטין את "תקציב" הרזולוציה בקרופ - בונה קופסת
    9:16 שהצלע הגדולה שלה (הגובה) שווה לצלע הגדולה מבין רוחב/גובה הקלט (כדי
    שמקור בעל רזולוציה גבוהה מ-1080p לא יוקטן סתם), במקום קופסה קבועה
    1080x1920."""
    default_w, default_h = resolve_output_dimensions(vertical)
    if not preserve_resolution or not input_width or not input_height:
        return default_w, default_h
    if not vertical:
        target_w = input_width if input_width % 2 == 0 else input_width + 1
        target_h = input_height if input_height % 2 == 0 else input_height + 1
        return target_w, target_h
    box_h = max(input_width, input_height, default_h)
    box_h = box_h if box_h % 2 == 0 else box_h + 1
    box_w = int(round(box_h * 9 / 16 / 2)) * 2
    return box_w, box_h


def resolve_effort_thread_count(effort: str, cpu_count: Optional[int] = None) -> int:
    """ל---effort (item: דרגות מאמץ קידוד/משאבי-מחשב) - ממיר רמת-מאמץ ידידותית
    למספר threads בפועל ל-ffmpeg (-threads/-filter_threads - שניהם משפיעים על
    עומס ה-CPU בפועל: filter_threads רלוונטי לכל קודק כי שרשרת הפילטרים
    (scale/pad/watermark/וכו') רצה על CPU גם כש-NVENC מקודד את הוידאו עצמו,
    אלא אם גם --hwaccel פעיל). 0 (ברירת המחדל, "high") = בלי הגבלה בכלל
    (ffmpeg מחליט/כל הליבות) - זהה בדיוק להתנהגות הקודמת. cpu_count (בד"כ
    os.cpu_count(), שהקורא מעביר) עם fallback ל-4 אם לא ידוע (למשל בסביבת
    container מוגבלת), כדי ש-"medium"/"low" עדיין יתנו מספר סביר."""
    total = cpu_count if cpu_count else 4
    if effort == "low":
        return 2
    if effort == "medium":
        return max(2, total // 2)
    return 0


def should_skip_scale(
    input_width: Optional[int],
    input_height: Optional[int],
    vertical: bool,
    target_dimensions: Optional[Tuple[int, int]] = None,
) -> bool:
    """True אם input_width/height כבר בדיוק ברזולוציית הפלט (item: skip
    redundant scale/pad/crop) - False (לא מדלגים) אם המידות לא ידועות בכלל
    (None), כדי שלא נדלג בטעות על שינוי גודל שכן נחוץ. target_dimensions
    (item: --preserve-resolution) - מאפשר לבדוק מול יעד בפועל (למשל
    resolve_effective_output_dimensions) במקום מידות הפלט הקבועות כברירת
    מחדל (None)."""
    if input_width is None or input_height is None:
        return False
    target_w, target_h = target_dimensions if target_dimensions is not None else resolve_output_dimensions(vertical)
    return input_width == target_w and input_height == target_h
