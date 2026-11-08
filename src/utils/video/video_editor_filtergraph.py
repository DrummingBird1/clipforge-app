# utils.video.video_editor_filtergraph - split out of the original module (no behavior change); the original module re-exports every name.

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from utils.media.timelapse import build_atempo_chain
from utils.video.video_editor_filters_basic import AUTO_LEVELS_FILTER, NOISE_GATE_FILTER, _escape_ffmpeg_filter_path, build_chromakey_filters, build_fps_filter, build_silence_removal_filters, get_lut_filter, get_vidstabtransform_filter
from utils.video.video_editor_fps_hdr import HDR_TONEMAP_FILTER


# זהה בכוונה למחרוזת ה-loudnorm ב-my_scripts/video/rocket_shorts_publisher.py -
# עקביות נרמול שמע בין שני סקריפטי הרינדור, לא שני סטנדרטים שונים.
LOUDNORM_FILTER = "loudnorm=I=-14:LRA=11:TP=-1.5"
# 24.10.2026 (סיור הסטודיו, LUFS על הפלט): loudnorm מדפיס בסוף הקידוד את מה שמדד, כולל output_i - העוצמה של הפלט. רק הדפסה,
# בלי מעבר נוסף ובלי שינוי בשמע; video_editor.py קורא את הערך מה-stderr של אותו קידוד ושומר אותו ב-run manifest
LOUDNORM_STATS = ":print_format=json"
_LOUDNORM_OUTPUT_I = re.compile(r'"output_i"\s*:\s*"(-?\d+(?:\.\d+)?)"')
_LOUDNORM_TARGET_I = re.compile(r"\bI=(-?\d+(?:\.\d+)?)")


def loudnorm_output_lufs(stderr_text: str) -> Optional[float]:
    """העוצמה הכוללת של הפלט (LUFS) מהסיכום של loudnorm, או None בלי סיכום (נרמול כבוי, או שמע שקט: "-inf")."""
    found = _LOUDNORM_OUTPUT_I.findall(stderr_text or "")
    return float(found[-1]) if found else None


def loudnorm_target_lufs(loudnorm_filter: Optional[str] = None) -> float:
    """היעד של הנרמול: מתוך הדריסה (--loudnorm-target) או LOUDNORM_FILTER."""
    match = _LOUDNORM_TARGET_I.search(loudnorm_filter or LOUDNORM_FILTER)
    return float(match.group(1)) if match else -14.0


DENOISE_FILTER = "hqdn3d"


SHARPEN_FILTER = "unsharp"


DEFAULT_BACKGROUND_BLUR_SIGMA = 20


# --- כיתוב טקסט קבוע (item) ---

# אותן שלוש אפשרויות בדיוק כמו caption_position (--captions) - טקסט הוא טקסט,
# לא צריך את 7 האפשרויות העשירות יותר של watermark (מיקום תמונה).
_DRAWTEXT_POSITION_EXPR = {
    "bottom": "x=(w-text_w)/2:y=h-text_h-20",
    "top": "x=(w-text_w)/2:y=20",
    "center": "x=(w-text_w)/2:y=(h-text_h)/2",
}


# item: כיתוב טקסט קבוע - textfile= (לא text= עם הטקסט מוטמע ישירות במחרוזת
# ה-filter_complex) בכוונה. נבדק בפועל בכל שילוב הגיוני של תווים מיוחדים
# (':', "'", '%', '\\', מחרוזת ריקה): text= דרש שילוב לא-אינטואיטיבי של גם
# escaping (\\:) וגם quoting ('...') יחד כדי ש-':' יעבוד (התיעוד הרשמי של
# ffmpeg מתאר אותן כשיטות-חלופיות בלעדיות זו לזו, אבל בפועל, לפחות בגרסת
# ffmpeg כאן, רק השילוב עבד) - ואז ההתלכדות בין ה-quote-breakout (ל-"'")
# לבין ה--escape (ל-':') על אותה מחרוזת ממש השחיתה בשקט תו ' באמצע הטקסט
# בטסט אחד. textfile= עוקף את כל זה - הטקסט עצמו לא מוטמע בכלל בתחביר
# ה-filtergraph, רק נתיב-קובץ (שכבר יש לו escaping מוכח: _escape_ffmpeg_filter_path,
# אותו בדיוק כמו LUT). expansion=none על drawtext עצמו (לא escaping) הוא מה
# שסוגר את '%' - נבדק בפועל: '%' גולמי-לגמרי (בלי שום escaping) נכשל
# ("Stray %") כש-expansion לא מנוטרל, כי drawtext מפרש % כפתיחת ביטוי
# %{...} כברירת מחדל - זו לא תכונה שרוצים בכלל בכיתוב-טקסט סטטי.
def build_drawtext_filter(text_file_path: str, position: str, font: str, font_size: int, color: str) -> str:
    """בונה את ביטוי ה-drawtext filter לכיתוב טקסט קבוע (item) - text_file_path
    כבר קיים בפועל (הקורא - video_editor.py - כתב אליו את הטקסט פעם אחת)."""
    pos_expr = _DRAWTEXT_POSITION_EXPR.get(position, _DRAWTEXT_POSITION_EXPR["bottom"])
    return f"drawtext=textfile='{_escape_ffmpeg_filter_path(text_file_path)}':font={font}:fontsize={font_size}:fontcolor={color}:expansion=none:{pos_expr}"


def build_edit_filter_complex(
    scale_chain: str,
    output_fps: Union[int, str],
    setpts_expr: Optional[str] = None,
    watermark_geometry: Optional[Tuple[int, int, int, int]] = None,
    watermark_opacity: Optional[float] = None,
    removal_region: Optional[Tuple[int, int, int, int]] = None,
    speed_factor: Optional[float] = None,
    keep_audio: bool = False,
    loudnorm: bool = False,
    loudnorm_filter: Optional[str] = None,
    use_hwaccel: bool = False,
    output_width: Optional[int] = None,
    output_height: Optional[int] = None,
    blur_background: bool = False,
    denoise: bool = False,
    sharpen: bool = False,
    tonemap_to_sdr: bool = False,
    lut_path: Optional[str] = None,
    auto_levels: bool = False,
    smooth_fps: bool = False,
    noise_gate: bool = False,
    silence_removal_intervals: Optional[List[Tuple[float, float]]] = None,
    stabilize_transform_path: Optional[str] = None,
    chromakey_color: Optional[str] = None,
    chromakey_similarity: float = 0.2,
    chromakey_blend: float = 0.05,
    chromakey_bg_color: str = "0x000000",
    input_width: Optional[int] = None,
    input_height: Optional[int] = None,
    pip_geometry: Optional[Tuple[int, int, int, int]] = None,
    pip_opacity: Optional[float] = None,
    pip_input_index: Optional[int] = None,
    fade_in_seconds: float = 0.0,
    fade_out_seconds: float = 0.0,
    output_duration_seconds: Optional[float] = None,
    text_file_path: Optional[str] = None,
    text_position: str = "bottom",
    text_font: str = "Arial",
    text_font_size: int = 24,
    text_color: str = "#FFFFFF",
    replace_audio_input_index: Optional[int] = None,
    hwaccel_decode_only: bool = False,
    subtitle_filter: Optional[str] = None,
    deinterlace: bool = False,
    orientation_filters: Optional[List[str]] = None,
    denoise_filter: Optional[str] = None,
    sharpen_filter: Optional[str] = None,
    tonemap_filter: Optional[str] = None,
    eq_filter: str = "",
    lut_intensity: float = 1.0,
    audio_stream_index: Optional[int] = None,
    layers: Optional[List[Dict[str, Any]]] = None,
    layer_text_files: Optional[Dict[int, List[str]]] = None,
    layer_image_inputs: Optional[Dict[int, int]] = None,
    progress_bar: Optional[Dict[str, Any]] = None,
    frame_border: Optional[Tuple[str, int]] = None,
    frame_radius: int = 0,
    vignette_filter: str = "",
    ken_burns_filter: str = "",
    watermark_cycle_positions: Optional[List[Tuple[int, int]]] = None,
    watermark_cycle_seconds: float = 0.0,
    pip_audio_input_index: Optional[int] = None,
    pip_duck: bool = False,
    gpu_prefix: Optional[List[str]] = None,
    audio_fx_filters: Optional[List[str]] = None,
    broll_audio_sources: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, List[str]]:
    """בונה filter_complex יחיד לכל שילוב אפשרי של הפעולות (מהירות/watermark/סקייל) -
    מקביל ל-utils/media/timelapse.py.build_filter_complex, עם ענף watermark אופציונלי
    נוסף (קלט שני, [1:v], רק כש-watermark_geometry ניתן).

    removal_region (x, y, w, h מ-compute_removal_region, בקואורדינטות הקלט
    המקורי) מפעיל delogo *לפני* scale_chain בכוונה - delogo צריך לדעת את
    המיקום/גודל האמיתיים של ה-watermark הישן בפריים המקורי, לא בפריים אחרי
    שינוי גודל לרזולוציית הפלט. אפשר לשלב removal_region+watermark_geometry
    יחד (מוחקים watermark ישן ומוסיפים אחד חדש במקומו/במיקום אחר).

    keep_audio בלי atempo/loudnorm: ממפה את האודיו המקורי as-is דרך "0:a?" (ה-'?'
    מונע כישלון ffmpeg אם אין בכלל ערוץ אודיו במקור) - מהיר יותר (בלי re-encode
    מיותר). ברגע שצריך atempo (timelapse) ו/או loudnorm, האודיו חייב לעבור דרך
    filter_complex במקום מיפוי ישיר - ffmpeg לא מרשה -af על stream שכבר נגע בו
    -filter_complex. loudnorm_filter דורס את LOUDNORM_FILTER הקבוע (item:
    configurable loudnorm target) - None (ברירת מחדל) משתמש ב-LOUDNORM_FILTER.

    use_hwaccel (--hwaccel, my_scripts/video/video_editor.py): מניח שהקלט כבר
    מפוענח ל-CUDA (-hwaccel cuda -hwaccel_output_format cuda על שורת הפקודה,
    לא כאן) ושscale_chain הוא כבר אחד מ-utils/media/timelapse.py's *_CUDA. delogo
    (removal_region) אין לו מקבילת CUDA בכלל - יורד ל-CPU רק לשלב הזה
    (hwdownload/format=nv12) ועולה חזרה (format=nv12/hwupload_cuda) מיד
    אחריו, כדי שהמשך השרשרת (scale_cuda/pad_cuda) ימשיך על ה-GPU. אחרי
    overlay_cuda יש scale_cuda נוסף עם passthrough=0 - נבדק ידנית מול GPU
    NVIDIA אמיתי: overlay_cuda מדליף בפועל (לא רק במטא-דאטה) גובה מיושר-16
    (1088 במקום 1080 למשל) בלי זה, וה-scale_cuda הבא לא היה מתקן את זה כי
    ברירת המחדל שלו (passthrough=true) מדלגת על עיבוד כשה-w כבר תואם.

    watermark_opacity (item: watermark opacity) מיושם רק בנתיב ה-CPU
    (format=rgba,colorchannelmixer=aa=X לפני scale ה-watermark, זהה בדיוק
    ל-my_scripts/video/rocket_shorts_publisher.py) - מתעלם בשקט ב-hwaccel
    (nv12, שהחלק הזה מומר אליו לפני ה-overlay_cuda, אין לו ערוץ אלפא בכלל,
    אין דרך לבטא שקיפות שם בלי לרדת ל-CPU בשביל זה, מה שהיה מבטל את מטרת
    ה-hwaccel). הקורא (my_scripts/video/video_editor.py) אחראי להתריע על כך.

    pip_geometry/pip_opacity/pip_input_index (item: תמונה-בתוך-תמונה) - שלב
    overlay שני, נבנה *לפני* ה-watermark בשרשרת (אם שניהם ניתנו יחד) כך
    שה-watermark - שכבת מיתוג - נשאר תמיד העליון/האחרון. pip_input_index הוא
    אינדקס ה--i בפועל שהקורא בחר לקובץ ה-PiP (לא בהכרח 1 - תלוי אם watermark
    גם ניתן ובאיזה סדר ה-i-ים נבנו שם) - watermark_input_index מחושב כאן
    יחסית אליו (pip_input_index+1), כדי שקריאת [1:v] הקשיחה הישנה של
    watermark לא תישבר כש-PiP תופס את האינדקס הזה במקומה. לא נתמך עם
    use_hwaccel (אין מקבילת CUDA מוכחת בפרויקט הזה, אותו דפוס כמו
    chromakey/blur_background) - pip_geometry מתעלם בשקט אם use_hwaccel=True.

    blur_background (item: blurred background instead of black bars) בונה
    תת-גרף נפרד (split לשני ענפים - רקע ממולא-ומטושטש, חזית מוקטנת-שמורה-יחס
    - ו-overlay ביניהם) *במקום* scale_chain הרגיל, כי אי אפשר לבטא split+overlay
    כשרשרת-פסיקים ליניארית יחידה כמו שאר הפילטרים כאן. דורש output_width/
    output_height (בלעדיהם, fallback לנתיב הרגיל בלי אזהרה - הקורא צריך
    להעביר אותם יחד עם blur_background=True). לא נתמך עם use_hwaccel (gblur
    אין לו מקבילת CUDA מוכחת בפרויקט הזה) - מתעלם בשקט, הקורא אחראי להתריע.

    output_fps מקבל גם int/str פשוט וגם שבר בסגנון ffprobe ("30000/1001",
    item: קצבים לא-שלמים) - מוזן ישירות ל-fps=... בלי פירוש, ffmpeg עצמו
    מקבל את שתי הצורות.

    tonemap_to_sdr (item: שימור הגדרות HDR - נתיב ה-SDR fallback) מוסיף את
    HDR_TONEMAP_FILTER *לפני* כל שאר הפילטרים - ממיר תוכן HDR (PQ/HLG) ל-SDR
    נכון (במקום חיתוך נאיבי שמפיק תמונה שטופה) לפני שממשיכים לקרופ/סקייל/
    watermark הרגילים. לא נתמך עם use_hwaccel (אין מקבילת CUDA ל-zscale/
    tonemap מוכחת בפרויקט הזה) - אותו דפוס כמו denoise/sharpen/blur_background.

    stabilize_transform_path (item: ייצוב וידאו) מוסיף vidstabtransform
    *ראשון בשרשרת, אפילו לפני tonemap* - תיקון גיאומטרי (רעידה) הכי הגיוני
    על הפריימים הכי "גולמיים" האפשריים, לפני כל שינוי צבע/גודל. הקורא אחראי
    להריץ קודם מעבר vidstabdetect נפרד (get_vidstabdetect_filter) ולהעביר
    את נתיב קובץ ה-transforms שנוצר. לא נתמך עם use_hwaccel.

    lut_path (item: LUT אופציונלי) מוסיף lut3d *אחרי* fps/sharpen - גריידינג
    יצירתי אחרון בשרשרת, על הפריימים כבר בגודל הפלט הסופי (פחות פיקסלים
    לעבד). auto_levels (item) מוסיף NORMALIZE_FILTER לצד denoise, *לפני*
    scale - תיקון בסיסי (מתיחת טווח בהירות) צריך לקרות לפני גריידינג יצירתי,
    לא אחריו.

    smooth_fps (item: אינטרפולציית פריימים) מחליף את פילטר ה-fps הרגיל
    ב-minterpolate (ראו build_fps_filter) - לא נתמך עם use_hwaccel.

    noise_gate (item) מוסיף NOISE_GATE_FILTER לשרשרת האודיו, *לפני* loudnorm
    (מנקים רעש קודם, מנרמלים עוצמה של האות הנקי אחר-כך).

    silence_removal_intervals (item: הסרת שקט באמצע הקובץ) - רשימת (start,
    end) שניות שזוהו כשקט (מ-parse_silence_intervals). build_silence_removal_filters
    בונה זוג select/aselect *מסונכרן* משני הזרמים יחד (ראו התיעוד שם למה
    silenceremove על אודיו בלבד משבש סנכרון) - שלב הווידאו נכנס *ראשון*
    בשרשרת (מיד אחרי tonemap/delogo, לפני setpts_expr הקיים של timelapse),
    ושלב האודיו נכנס ראשון ברשימת audio_filters, כדי ששאר הפעולות (מהירות/
    שער-רעש/נרמול) יחולו על ציר הזמן כבר-נקי, לא המקורי.

    chromakey_color (item: כרומה קי) - כש-ניתן (וללא use_hwaccel), בונה ענף
    מקביל (build_chromakey_filters) *במקום* נתיב ה-scale_chain הרגיל, לפני
    blur_background בעדיפות אם שניהם ניתנו (הקורא אחראי לא לשלב אותם יחד
    בפועל - שני "איך בונים את הבסיס" סותרים). דורש input_width/input_height
    (מידות [0:v] המקוריות, *לא* output_width/height) כדי שרקע ה-color= יתאים
    בדיוק לגודל הפריים לפני ה-scale.

    early_fps_drop (item: טיימלאפס מהיר יותר) - כש-setpts_expr קיים (מצב
    --target-seconds) בלי אף פילטר תלוי-שכנים-בזמן (denoise/stabilize/
    silence-removal/smooth_fps) ובלי chromakey/blur_background/use_hwaccel,
    fps_and_sharpen (fps=/sharpen/lut, שקובע אילו פריימים שורדים) זז לפני
    scale_chain במקום אחריו - fps= בורר לפי PTS בלבד, לא תוכן, אז הזזתו לא
    משנה אילו פריימים מגיעים לפלט, רק חוסכת מ-scale/watermark/sharpen/lut
    לרוץ על עשרות/מאות הפריימים שנזרקים מיד אחר-כך בכל מקרה בטיימלאפס
    במהירות גבוהה (למשל שעות של גיימפליי שנדחסות לדקה). הפענוח עצמו (העלות
    הדומיננטית) לא מושפע - זו לא תלויה בסדר הפילטרים אחריו.

    fade_in_seconds/fade_out_seconds (item: Fade-in/fade-out) - fade=t=in/out
    על ה-video וגם afade=t=in/out על ה-audio (כש-keep_audio), *ממש בסוף* שתי
    השרשראות - על הפלט הסופי-לגמרי (אחרי watermark/PiP), לא הבסיס לפני
    הרכבה, כדי שה-fade יכהה/יבהיר גם את שכבות המיתוג. fade_out דורש
    output_duration_seconds (כדי לחשב מתי הוא *מתחיל*, st=duration-fade_out)
    - בלעדיו מתעלם בשקט מ-fade-out (fade-in לא תלוי בזה, תמיד מתחיל ב-st=0).

    text_file_path/text_position/text_font/text_font_size/text_color (item:
    כיתוב טקסט קבוע) - drawtext, מיושם *לפני* ה-fade (אם שניהם ניתנו) כדי
    שהטקסט גם הוא יכהה/יבהיר עם שאר הפריים, לא שכבה נפרדת-לגמרי מעליו.
    text_file_path (לא טקסט מוטמע ישירות) - ראו build_drawtext_filter לסיבה
    (escaping מהימן, לא ניחוש-וטעות עם quoting). font= (לא fontfile=) - שם
    גופן דרך fontconfig, אותו עיקרון בדיוק כמו utils/media/captions.py's font_name
    (ASS/libass) - לא דורש נתיב לקובץ פונט קונקרטי.

    replace_audio_input_index (item: החלפת פס קול חלופי) - כשניתן, מקור
    האודיו לכל שרשרת-האודיו (atempo/noise_gate/loudnorm/fade, ואם אין אף
    אחד מהם, המיפוי הישיר) הוא [{replace_audio_input_index}:a] במקום [0:a] -
    האודיו המקורי מושתק/מתעלם ממנו לגמרי, לא מעורבב. הקורא אחראי להוסיף את
    ה--i בפועל לקובץ האודיו החלופי ולחשב את האינדקס הנכון (אחרי video/PiP/
    watermark, לפי סדר ה--i-ים שהוא עצמו בונה).

    hwaccel_decode_only (item: פענוח מואץ-GPU בלי NVENC) - שונה לגמרי מ-
    use_hwaccel: לא בוחר אף פילטר CUDA-native (scale_chain/watermark/PiP כאן
    ממשיכים בדיוק כמו use_hwaccel=False, כי הפריימים כבר חוזרים ל-CPU), רק
    מוסיף hwdownload,format=nv12 כשלב *הראשון-לגמרי* בשרשרת (לפני אפילו
    stabilize/tonemap) - הקורא אחראי להוסיף בפועל -hwaccel cuda
    -hwaccel_output_format cuda ל--i הווידאו (כדי שיהיה בכלל מה להוריד).
    True יחד עם use_hwaccel=True הוא קלט לא-הגיוני (use_hwaccel כבר מניח
    שהפריימים *נשארים* ב-CUDA) - הקורא אחראי לא לשלב את השניים.
    """
    sharpen_suffix = f",{sharpen_filter or SHARPEN_FILTER}" if (sharpen and not use_hwaccel) else ""
    # גל 7 (item 73): LUT בעוצמה חלקית - במקום lut3d ישיר בשרשרת, שלב נפרד אחרי
    # הבסיס (split -> lut3d -> blend עם המקור בשקיפות = העוצמה), ראו למטה.
    partial_lut = bool(lut_path) and 0.0 < lut_intensity < 0.999
    lut_suffix = f",{get_lut_filter(lut_path)}" if (lut_path and not partial_lut) else ""
    eq_suffix = f",{eq_filter}" if (eq_filter and not use_hwaccel) else ""  # item 74
    # גל 7ב (item 88): וינייטה ו-Ken Burns חלים על הבסיס (לפני PiP/watermark/שכבות),
    # כדי שהזום/ההחשכה לא יחולו על שכבות המיתוג עצמן.
    base_suffix = ""
    if vignette_filter and not use_hwaccel:
        base_suffix += f",{vignette_filter}"
    if ken_burns_filter and not use_hwaccel:
        base_suffix += f",{ken_burns_filter}"
    fps_and_sharpen = f"{build_fps_filter(output_fps, smooth=smooth_fps and not use_hwaccel)}{eq_suffix}{sharpen_suffix}{lut_suffix}{base_suffix}"

    # item: טיימלאפס מהיר יותר - כש-setpts_expr קיים (רק במצב --target-seconds)
    # ואף פילטר תלוי-שכנים-בזמן לא מעורב (denoise/stabilize/silence-removal
    # תלויים בפריימים סמוכים בפועל; smooth_fps/minterpolate מייצר פריימים
    # חדשים בעצמו, לא רק בורר; chromakey/blur_background בונים ענף filter_complex
    # נפרד משלהם ולא עוברים כאן), fps= מוזז *לפני* scale/watermark/sharpen/lut
    # במקום אחריהם - fps= קובע אילו פריימים שורדים לפי PTS בלבד, לא לפי תוכן,
    # אז ההזזה לא משנה איזה פריימים מגיעים לפלט הסופי, רק חוסכת מכל שאר
    # השרשרת (שעלולה לכלול scale יקר מ-4K, watermark overlay, sharpen, LUT)
    # מלרוץ על ~99% מהפריימים המפוענחים שהיו נזרקים בכל מקרה - הפענוח עצמו
    # (העלות הדומיננטית בסרטוני גיימפליי ארוכים) לא משתנה, זו לא תלויה בסדר הפילטרים.
    early_fps_drop = bool(
        setpts_expr
        and not use_hwaccel
        and not denoise
        and not auto_levels
        and not stabilize_transform_path
        and not silence_removal_intervals
        and not smooth_fps
        and not chromakey_color
        and not blur_background
        and not ken_burns_filter  # zoompan מוציא מידות-פלט קבועות - חייב לבוא אחרי scale_chain
    )

    video_chain_parts = []
    if hwaccel_decode_only:
        # item: פענוח מואץ-GPU בלי NVENC - חייב לבוא ראשון-לגמרי, לפני stabilize/
        # tonemap/delogo/הכל - אלה כולם פילטרים רגילים ל-CPU שמצפים לפריים
        # רגיל, לא ל-frame בפורמט CUDA. משם והלאה כל השרשרת זהה לגמרי למצב
        # use_hwaccel=False הרגיל.
        # גל 10: gpu_prefix (build_hybrid_gpu_prefix) - deinterlace/סיבוב/הקטנה
        # מוקדמת על ה-GPU *לפני* ההורדה, כשהפריים עדיין בפורמט CUDA.
        video_chain_parts += [*(gpu_prefix or []), "hwdownload", "format=nv12"]
    if deinterlace and not use_hwaccel:
        video_chain_parts.append("bwdif")  # item 89: deinterlace - לפני כל ניתוח/סינון
    if stabilize_transform_path and not use_hwaccel:
        video_chain_parts.append(get_vidstabtransform_filter(stabilize_transform_path))
    if tonemap_to_sdr and not use_hwaccel:
        video_chain_parts.append(tonemap_filter or HDR_TONEMAP_FILTER)
    if removal_region:
        rx, ry, rw, rh = removal_region
        if use_hwaccel:
            video_chain_parts += ["hwdownload", "format=nv12", f"delogo=x={rx}:y={ry}:w={rw}:h={rh}", "format=nv12", "hwupload_cuda"]
        else:
            video_chain_parts.append(f"delogo=x={rx}:y={ry}:w={rw}:h={rh}")
    # item 83: סיבוב/מראה - *אחרי* delogo, כדי שאזור המחיקה יישאר בקואורדינטות
    # של המקור כפי שהמשתמש סימן אותו (על פריים לא-מסובב).
    if orientation_filters and not use_hwaccel:
        video_chain_parts += orientation_filters
    silence_video_filter, silence_audio_filter = build_silence_removal_filters(silence_removal_intervals or [])
    if silence_video_filter:
        video_chain_parts.append(silence_video_filter)
    if setpts_expr:
        video_chain_parts.append(setpts_expr)
    if early_fps_drop:
        video_chain_parts.append(fps_and_sharpen)
    if denoise and not use_hwaccel:
        video_chain_parts.append(denoise_filter or DENOISE_FILTER)
    if auto_levels and not use_hwaccel:
        video_chain_parts.append(AUTO_LEVELS_FILTER)
    pre_scale_parts = list(video_chain_parts)
    # scale_chain יכול להגיע ריק בכוונה (item: skip redundant scale אם ה-source
    # כבר בדיוק ברזולוציית הפלט, ראו should_skip_scale) - append מותנה, לא
    # ללא-תנאי, כדי לא להשאיר פסיק בודד/מיותר בשרשרת (",".join עם מחרוזת
    # ריקה היה מייצר "...,,..." או "[0:v],fps=..." לא תקין ל-ffmpeg).
    if scale_chain:
        video_chain_parts.append(scale_chain)
    video_chain = ",".join(video_chain_parts)

    pip_active = bool(pip_geometry) and not use_hwaccel and pip_input_index is not None
    base_label = "base" if (watermark_geometry or pip_active) else "outv"

    if chromakey_color and not use_hwaccel and input_width and input_height:
        pre_split_chain = ",".join(pre_scale_parts)
        pre_key = f"[0:v]{pre_split_chain}," if pre_split_chain else "[0:v]"
        key_filter, bg_filter = build_chromakey_filters(
            chromakey_color, chromakey_similarity, chromakey_blend, chromakey_bg_color, input_width, input_height
        )
        scale_suffix = f",{scale_chain}" if scale_chain else ""
        parts = [
            f"{pre_key}{key_filter}[__ck_fg]",
            f"{bg_filter}[__ck_bg]",
            f"[__ck_bg][__ck_fg]overlay=shortest=1{scale_suffix},{fps_and_sharpen}[{base_label}]",
        ]
    elif blur_background and not use_hwaccel and output_width and output_height:
        pre_split_chain = ",".join(pre_scale_parts)
        pre_split = f"[0:v]{pre_split_chain}," if pre_split_chain else "[0:v]"
        parts = [
            f"{pre_split}split=2[__bg_src][__fg_src]",
            f"[__bg_src]scale={output_width}:{output_height}:force_original_aspect_ratio=increase,"
            f"crop={output_width}:{output_height},gblur=sigma={DEFAULT_BACKGROUND_BLUR_SIGMA}[__bg]",
            f"[__fg_src]scale={output_width}:{output_height}:force_original_aspect_ratio=decrease[__fg]",
            f"[__bg][__fg]overlay=(W-w)/2:(H-h)/2,{fps_and_sharpen}[{base_label}]",
        ]
    else:
        # early_fps_drop כבר הטמיע את fps_and_sharpen בתוך video_chain (לפני
        # scale_chain) - הוספה נוספת כאן הייתה מכפילה את הפילטר פעמיים.
        base_chain = video_chain if early_fps_drop else (f"{video_chain},{fps_and_sharpen}" if video_chain else fps_and_sharpen)
        parts = [f"[0:v]{base_chain}[{base_label}]"]

    if partial_lut and lut_path:
        # הבסיס נכתב קודם ל-[__prelut] ורק אז מתמזג: blend=normal:opacity=X נותן
        # X*LUT + (1-X)*מקור - "LUT בעוצמה X%".
        last = parts[-1]
        parts[-1] = last[: last.rindex(f"[{base_label}]")] + "[__prelut]"
        parts += [
            "[__prelut]split=2[__lut_src][__lut_orig]",
            f"[__lut_src]{get_lut_filter(lut_path)}[__lut_graded]",
            f"[__lut_graded][__lut_orig]blend=all_mode=normal:all_opacity={lut_intensity:.3f}[{base_label}]",
        ]

    # PiP (item: תמונה-בתוך-תמונה) - שלב overlay שני, *לפני* ה-watermark אם שניהם
    # ניתנו (watermark, כשכבת המיתוג, נשאר תמיד עליון/אחרון) - current_label
    # עוקב איזו תווית-ביניים המשך השרשרת צריך לקרוא ממנה, כדי שקריאת ה-watermark
    # למטה תישאר תקינה גם כש-PiP לא ניתן בכלל (זהה להתנהגות הקודמת אז, base_label).
    current_label = base_label
    watermark_input_index = 1
    if pip_active and pip_geometry is not None and pip_input_index is not None:
        pip_w, pip_h, pip_x, pip_y = pip_geometry
        next_label = "after_pip" if watermark_geometry else "outv"
        opacity_prefix = ""
        if pip_opacity is not None and pip_opacity < 1.0:
            opacity_prefix = f"format=rgba,colorchannelmixer=aa={pip_opacity:.2f},"
        parts += [
            f"[{pip_input_index}:v]{opacity_prefix}scale={pip_w}:{pip_h}[pip]",
            f"[{current_label}][pip]overlay={pip_x}:{pip_y}[{next_label}]",
        ]
        current_label = next_label
        watermark_input_index = pip_input_index + 1

    if watermark_geometry:
        target_w, target_h, x, y = watermark_geometry
        if use_hwaccel:
            if not output_width or not output_height:
                raise ValueError("output_width/output_height נדרשים כש-use_hwaccel=True עם watermark_geometry")
            parts += [
                f"[{watermark_input_index}:v]format=nv12,hwupload_cuda,scale_cuda=w={target_w}:h={target_h}[wm]",
                f"[{current_label}][wm]overlay_cuda={x}:{y},scale_cuda=w={output_width}:h={output_height}:passthrough=0[outv]",
            ]
        else:
            opacity_prefix = ""
            if watermark_opacity is not None and watermark_opacity < 1.0:
                opacity_prefix = f"format=rgba,colorchannelmixer=aa={watermark_opacity:.2f},"
            position = f"{x}:{y}"
            if watermark_cycle_positions and len(watermark_cycle_positions) > 1 and watermark_cycle_seconds > 0:
                # item 87: watermark נודד - עובר בין המיקומים כל N שניות
                from utils.video.video_editor_layers import build_cycling_overlay_xy
                cycle_x, cycle_y = build_cycling_overlay_xy(watermark_cycle_positions, watermark_cycle_seconds)
                position = f"x='{cycle_x}':y='{cycle_y}'"
            parts += [
                f"[{watermark_input_index}:v]{opacity_prefix}scale={target_w}:{target_h}[wm]",
                f"[{current_label}][wm]overlay={position}[outv]",
            ]

    # item: כיתוב טקסט קבוע + Fade-in/fade-out - שלב אחרון-לגמרי על [outv]
    # (אחרי watermark/PiP אם היו) ל-label חדש [outv2], כדי שהטקסט/ה-fade
    # יחולו על הפריים הסופי-לגמרי כולל שכבות המיתוג, לא הבסיס לפני הרכבה.
    final_video_filters = []
    if text_file_path:
        final_video_filters.append(build_drawtext_filter(text_file_path, text_position, text_font, text_font_size, text_color))
    if subtitle_filter:
        # item 40 (תצוגה מקדימה מלאה): כתובית-לדוגמה בעיצוב האמיתי - רק בתצוגה
        # מקדימה; ברינדור רגיל הכתוביות נשרפות במעבר נפרד אחרי התמלול.
        final_video_filters.append(subtitle_filter)
    if fade_in_seconds > 0:
        final_video_filters.append(f"fade=t=in:st=0:d={fade_in_seconds:.3f}")
    if fade_out_seconds > 0 and output_duration_seconds is not None:
        fade_out_start = max(0.0, output_duration_seconds - fade_out_seconds)
        final_video_filters.append(f"fade=t=out:st={fade_out_start:.3f}:d={fade_out_seconds:.3f}")
    # גל 7ב (items 79-82, 88-89): שכבות מתוזמנות / טיימר / חותמת-זמן / סרגל
    # התקדמות / מסגרת - מעל הפריים המורכב, *לפני* ה-fade (כדי שגם הן יתעמעמו).
    layers_label = "outv"
    if (layers or progress_bar or (frame_border and frame_border[1] > 0)) and not use_hwaccel:
        from utils.video.video_editor_layers import build_layer_parts
        layer_parts, layers_label = build_layer_parts(
            "outv", layers or [], layer_text_files or {}, layer_image_inputs or {},
            output_width, output_fps, output_duration_seconds, progress_bar=progress_bar, frame_border=frame_border,
            output_height=output_height, frame_radius=frame_radius,
        )
        parts += layer_parts
    final_video_label = layers_label
    if final_video_filters:
        parts.append(f"[{layers_label}]{','.join(final_video_filters)}[outv2]")
        final_video_label = "outv2"

    # item: החלפת פס קול חלופי - מקור האודיו לכל השרשרת (ולמיפוי הישיר, בלי
    # אף פילטר) הוא ה--i החלופי, לא [0:a] - האודיו המקורי לא מעורב בכלל.
    audio_source_index = replace_audio_input_index if replace_audio_input_index is not None else 0
    # item 88: בחירת track אודיו (קבצים עם כמה ערוצי-שמע, למשל משחק+מיקרופון ב-OBS)
    audio_selector = f"{audio_source_index}:a:{audio_stream_index}" if (audio_stream_index is not None and replace_audio_input_index is None) else f"{audio_source_index}:a"

    maps = ["-map", f"[{final_video_label}]"]
    if keep_audio:
        audio_filters = []
        if silence_audio_filter:
            audio_filters.append(silence_audio_filter)
        if speed_factor:
            audio_filters.append(build_atempo_chain(speed_factor))
        # גל 25 (utils/video/color_audio.py): חיתוך נמוכים / הפחתת רעש / EQ / קומפרסור -
        # אחרי שינוי המהירות, לפני שער-הרעש והנרמול (שמודדים את התוצאה המעובדת)
        audio_filters += audio_fx_filters or []
        if noise_gate:
            audio_filters.append(NOISE_GATE_FILTER)
        if loudnorm:
            # loudnorm מעבד ומוציא 192kHz - בלי חזרה ל-48kHz ה-AAC יצא ב-96kHz (נמצא בהרצה אמיתית, 16.10)
            audio_filters += [(loudnorm_filter or LOUDNORM_FILTER) + LOUDNORM_STATS, "aresample=48000"]
        if fade_in_seconds > 0:
            audio_filters.append(f"afade=t=in:st=0:d={fade_in_seconds:.3f}")
        if fade_out_seconds > 0 and output_duration_seconds is not None:
            fade_out_start = max(0.0, output_duration_seconds - fade_out_seconds)
            audio_filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fade_out_seconds:.3f}")
        if pip_audio_input_index is not None:
            # item 88: שמע ה-PiP (למשל פרשנות/מצלמת-פנים) מעורבב מעל הסאונד הראשי;
            # pip_duck מנמיך את הראשי (sidechain) בכל פעם שמדברים ב-PiP.
            main_chain = ",".join(audio_filters) or "anull"
            parts.append(f"[{audio_selector}]{main_chain}[__main_a]")
            parts.append(f"[{pip_audio_input_index}:a]aresample=async=1[__pip_a]")
            if pip_duck:
                parts += [
                    "[__pip_a]asplit=2[__pip_sc][__pip_mix]",
                    "[__main_a][__pip_sc]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400[__ducked]",
                    "[__ducked][__pip_mix]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[outa]",
                ]
            else:
                parts.append("[__main_a][__pip_a]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[outa]")
            maps += ["-map", "[outa]"]
        elif audio_filters:
            parts.append(f"[{audio_selector}]{','.join(audio_filters)}[outa]")
            maps += ["-map", "[outa]"]
        else:
            maps += ["-map", f"{audio_selector}?"]
        if broll_audio_sources:
            # גל 26: שמע של שכבות B-roll (mix/replace) מעל השמע הראשי המוכן - התווית הסופית
            # של הראשי הופכת ל-[__amain], והערבוב מוציא את [outa]
            from utils.video.video_editor_layers import build_broll_audio_parts
            if "[outa]" in maps:
                parts[-1] = parts[-1][: parts[-1].rindex("[outa]")] + "[__amain]"
            else:
                parts.append(f"[{audio_selector}]anull[__amain]")
                maps = maps[:-2] + ["-map", "[outa]"]
            parts += build_broll_audio_parts("__amain", broll_audio_sources)
    return ";".join(parts), maps


# --- מעברים בין כמה קטעים (item: concat עם קרוספייד/דיסולב) ---

def compute_xfade_offsets(clip_durations: List[float], transition_duration: float) -> List[float]:
    """מחשב את ה-offset (בציר-הזמן של הזרם-המאוחד-עד-כה) שבו כל xfade צריך
    להתחיל - ראו build_concat_transitions_filter_complex. פונקציה נפרדת,
    טהורה, כדי שהמתמטיקה (הצטברות משך-מאוחד פחות חפיפה בכל שלב) תהיה
    בדיקה בפני עצמה, בלי לבנות מחרוזות filter_complex שלמות רק כדי לוודא
    שהמספרים נכונים. offset[i] מתאים למעבר בין clip i ל-clip i+1 (כלומר
    לרשימת clip_durations באורך N יש N-1 offsets, אחד לכל מעבר)."""
    if len(clip_durations) < 2:
        return []
    offsets = []
    merged_duration = clip_durations[0]
    for duration in clip_durations[1:]:
        offsets.append(merged_duration - transition_duration)
        merged_duration = merged_duration + duration - transition_duration
    return offsets


def build_concat_transitions_filter_complex(
    clip_durations: List[float],
    scale_chain: str,
    transition: str = "fade",
    transition_duration: float = 1.0,
    include_audio: bool = False,
) -> Tuple[str, List[str]]:
    """בונה filter_complex יחיד שמאחה len(clip_durations) קטעים (כל אחד קלט
    -i נפרד, [0:v]/[0:a], [1:v]/[1:a] וכו' - הקורא אחראי להוסיף את כל
    ה--i-ים בעצמו, באותו סדר בדיוק כמו clip_durations) לתוצר אחד (item:
    מעברים בין כמה קטעים). transition="fade" (ברירת מחדל, "קרוספייד/דיסולב"
    בניסוח הבקשה - שני שמות לאותו מעבר-חלק) משתמש ב-xfade/acrossfade;
    transition="none" (חיתוך קשה, בלי מעבר חלק) משתמש ב-concat הרגיל
    במקום - הרבה יותר פשוט (בלי offsets בכלל) כי אין חפיפה בין הקטעים.

    scale_chain (למשל HORIZONTAL_SCALE_CHAIN) מוחל על *כל* קלט בנפרד לפני
    ה-xfade/concat - כל הקטעים חייבים באותה רזולוציה/יחס-מסגרת בדיוק כדי
    ש-xfade/concat בכלל יעבדו; הקורא אחראי לחשב אותו פעם אחת (יעד-פלט
    משותף לכל הקטעים, לא לפי כל קטע בנפרד כמו בנתיב הרגיל של video_editor.py).

    include_audio=True מניח שלכל קטע יש בפועל ערוץ אודיו - בניגוד ל-'?'
    האופציונלי שהנתיב הרגיל (build_edit_filter_complex) כבר משתמש בו,
    xfade/concat לא יודעים "לדלג בחן" על קלט-אודיו חסר - קטע בלי אודיו
    כש-include_audio=True ייכשל ב-ffmpeg עם שגיאה ברורה, לא בשקט."""
    n = len(clip_durations)
    if n < 2:
        raise ValueError("צריך לפחות שני קטעים כדי לאחות")

    if transition == "none":
        video_prep = [f"[{i}:v]{scale_chain},setsar=1[s{i}]" for i in range(n)]
        video_inputs = "".join(f"[s{i}]" for i in range(n))
        if include_audio:
            interleaved = "".join(f"[s{i}][{i}:a]" for i in range(n))
            parts = video_prep + [f"{interleaved}concat=n={n}:v=1:a=1[outv][outa]"]
            maps = ["-map", "[outv]", "-map", "[outa]"]
        else:
            parts = video_prep + [f"{video_inputs}concat=n={n}:v=1:a=0[outv]"]
            maps = ["-map", "[outv]"]
        return ";".join(parts), maps

    # transition == "fade" (קרוספייד/דיסולב) - xfade לוידאו, acrossfade
    # לאודיו (אם include_audio) - שתי שרשראות-שרשור נפרדות, כל אחת עם
    # התחביר/הפרמטרים שהפילטר שלה דורש (xfade צריך offset מפורש לכל שלב,
    # acrossfade לא - הוא כבר "יודע" איפה שני הקלטים שלו מתחילים/נגמרים).
    offsets = compute_xfade_offsets(clip_durations, transition_duration)
    video_prep = [f"[{i}:v]{scale_chain},setsar=1[s{i}]" for i in range(n)]
    video_chain = []
    current_label = "s0"
    for i in range(1, n):
        next_label = f"vx{i}" if i < n - 1 else "outv"
        video_chain.append(
            f"[{current_label}][s{i}]xfade=transition=fade:duration={transition_duration:.3f}:offset={offsets[i - 1]:.3f}[{next_label}]"
        )
        current_label = next_label
    parts = video_prep + video_chain
    maps = ["-map", "[outv]"]

    if include_audio:
        audio_chain = []
        current_audio_label = "0:a"
        for i in range(1, n):
            next_audio_label = f"ax{i}" if i < n - 1 else "outa"
            audio_chain.append(f"[{current_audio_label}][{i}:a]acrossfade=d={transition_duration:.3f}[{next_audio_label}]")
            current_audio_label = next_audio_label
        parts += audio_chain
        maps += ["-map", "[outa]"]

    return ";".join(parts), maps
