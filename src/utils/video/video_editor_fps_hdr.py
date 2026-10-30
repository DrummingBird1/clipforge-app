# utils.video.video_editor_fps_hdr - split out of the original module (no behavior change); the original module re-exports every name.

import re
from typing import List, Optional, Tuple


# --- שימור FPS מקורי (item) ---

DEFAULT_FPS = 30


def parse_fps_value(raw: str) -> float:
    """מפרש ערך FPS למספר ממשי - תומך גם במספר רגיל ("30", "29.97") וגם בשבר
    בסגנון ffprobe/ffmpeg ("30000/1001", איך ש-r_frame_rate מדווח קצבים
    לא-שלמים כמו NTSC 29.97/59.94 בלי אובדן דיוק מעיגול). ValueError על קלט
    לא תקין/לא-חיובי - עדיף כישלון מיידי וברור (item: קצבים לא-שלמים) מאשר
    ffmpeg שנכשל מאוחר יותר עם שגיאה עמומה."""
    text = raw.strip()
    if "/" in text:
        num_str, _, den_str = text.partition("/")
        try:
            num, den = float(num_str), float(den_str)
        except ValueError:
            raise ValueError(f"ערך FPS לא תקין: {raw!r}")
        if den == 0:
            raise ValueError(f"ערך FPS לא תקין (מכנה אפס): {raw!r}")
        value = num / den
    else:
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"ערך FPS לא תקין: {raw!r}")
    if value <= 0:
        raise ValueError(f"ערך FPS חייב להיות חיובי: {raw!r}")
    return value


def resolve_output_fps(
    explicit_fps: Optional[str], source_fps: Optional[str], default_fps: int = DEFAULT_FPS
) -> Tuple[str, float]:
    """קובע את קצב הפריימים הסופי של הפלט (item: שימור FPS מקורי כברירת מחדל) -
    מחזיר (ffmpeg_fps_string, numeric_value): המחרוזת מוזנת ישירות לפילטר
    fps=... (ffmpeg מקבל גם שבר "30000/1001" וגם עשרוני "29.97" בעצמו), הערך
    המספרי משמש לחישובי progress (total_frames) בקורא.

    סדר עדיפויות: explicit_fps (--fps מפורש מהמשתמש) קודם לכל אם ניתן -
    דריסה ידנית תמיד מנצחת. אחרת source_fps (fps מ-probe_video, שכבר עבר
    ffprobe's r_frame_rate/avg_frame_rate) - שימור קצב הפריימים המקורי של
    הקובץ הספציפי הזה, כברירת המחדל החדשה. רק אם גם source_fps חסר/לא-ניתן-
    לפרסור (קובץ פגום/פורמט לא-שגרתי) נופלים ל-default_fps הקבוע - לא
    ל-ValueError שהיה עוצר את כל הריצה על קובץ בודד באצווה."""
    if explicit_fps:
        return explicit_fps, parse_fps_value(explicit_fps)
    if source_fps:
        try:
            return source_fps, parse_fps_value(source_fps)
        except ValueError:
            pass
    return str(default_fps), float(default_fps)


# --- HDR (item: שימור הגדרות HDR) ---

# PQ (smpte2084 - HDR10/HDR10+/Dolby Vision הבסיסי) ו-HLG (arib-std-b67 -
# תקן השידור/יוטיוב) - שתי ה-transfer functions התקניות שמסמנות תוכן HDR
# אמיתי. Rec.2020 (bt2020) לבדו *לא* מספיק לזיהוי HDR - זה רק גמוט-צבעים
# רחב, אפשר לקודד גם תוכן SDR רגיל איתו; ה-transfer function (העקומה) הוא
# הפרמטר הקובע HDR-מול-SDR, לא ה-primaries.
HDR_TRANSFER_FUNCTIONS = {"smpte2084", "arib-std-b67"}


def is_hdr_source(color_transfer: Optional[str]) -> bool:
    """True אם color_transfer (משדה ffprobe שאותו שם, מ-probe_video) מזהה
    תוכן HDR אמיתי - ראו HDR_TRANSFER_FUNCTIONS לעיל."""
    return color_transfer is not None and color_transfer.strip().lower() in HDR_TRANSFER_FUNCTIONS


_HIGH_BIT_DEPTH = re.compile(r"p01[026]|1[026](le|be)$")


def is_high_bit_depth(pix_fmt: Optional[str]) -> bool:
    """True למקור של יותר מ-8 ביט לערוץ (yuv420p10le, p010le, yuv444p12le...) - גם SDR. נתיב ה-CUDA בפרויקט 8 ביט
    בלבד: hwdownload ל-nv12 נכשל על פריימים כאלה מיד ("Invalid output format nv12 for hwframe download") והקובץ לא
    רונדר בכלל (נמצא בהרצה אמיתית, 16.10: 3 מ-23 הקלטות משחק בפרויקט אמיתי הן 10 ביט SDR)."""
    return bool(pix_fmt and _HIGH_BIT_DEPTH.search(pix_fmt.strip().lower()))


def get_hdr_output_args(
    color_primaries: Optional[str], color_transfer: Optional[str], color_space: Optional[str]
) -> List[str]:
    """דגלי ffmpeg לשימור נכון של מטא-דאטת HDR בפלט (item: שימור הגדרות HDR
    מלא) - מעביר את ה-primaries/transfer/colorspace שזוהו במקור הלאה לפלט,
    במקום לתת ל-ffmpeg לתייג ברירת מחדל (בד"כ bt709/SDR) על תוכן שהוא בפועל
    HDR - זה בדיוק מה שגורם לנגן שמכבד את המטא-דאטה להציג תמונה שטופה/דהויה,
    גם כשהפיקסלים עצמם קודדו נכון. -pix_fmt p010le (10-bit) - HDR10/HLG
    תקניים דורשים לפחות 10 סיביות לערוץ; 8-bit (ברירת המחדל) יפיק banding
    חמור בגרדיאנטים של תוכן HDR. רלוונטי רק עם --codec hevc/av1 (NVENC) -
    הקורא (video_editor.py) אחראי לא לקרוא לפונקציה הזו עם h264 (אין תמיכת
    HDR10 metadata אמינה ב-libx264 בפרויקט הזה)."""
    args = ["-pix_fmt", "p010le"]
    if color_primaries:
        args += ["-color_primaries", color_primaries]
    if color_transfer:
        args += ["-color_trc", color_transfer]
    if color_space:
        args += ["-colorspace", color_space]
    return args


# שרשרת tone-mapping סטנדרטית להמרת HDR (PQ/HLG) ל-SDR *נכון* - נכנסת לתוקף
# רק כש-HDR מזוהה במקור אבל --codec הוא h264 (לא תומך בשימור HDR מלא, ראו
# get_hdr_output_args) - במקום שffmpeg יעשה חיתוך/scaling ליניארי נאיבי של
# ערכי 10-bit ל-8-bit (מה שמפיק תמונה שטופה/דהויה), tone-mapping אמיתי דוחס
# את טווח הבהירות הרחב (עד 1000+ nits) לטווח SDR (100 nits) תוך שמירה על
# פרטים בהיילייטס. zscale הראשון עובר למרחב ליניארי (נדרש לפני tonemap
# עצמו), tonemap=hable הוא האלגוריתם שמבצע את הדחיסה, zscale השני חוזר
# ל-BT.709/SDR הרגיל. דורש בניית ffmpeg עם תמיכת zscale/libzimg - רוב
# הבנייות המודרניות כוללות את זה, אבל לא כל בנייה. לא נתמך עם use_hwaccel
# (אין מקבילת CUDA ל-zscale/tonemap מוכחת בפרויקט הזה) - אותו דפוס בדיוק
# כמו denoise/sharpen/blur_background למעלה.
HDR_TONEMAP_FILTER = "zscale=transfer=linear:npl=100,tonemap=tonemap=hable:desat=0,zscale=transfer=bt709:matrix=bt709:primaries=bt709,format=yuv420p"
