# utils.video.video_editor_filters_basic - split out of the original module (no behavior change); the original module re-exports every name.

from typing import List, Tuple, Union


def _escape_ffmpeg_filter_path(path: str) -> str:
    """מכין נתיב קובץ לשיבוץ כערך פילטר ffmpeg מצוטט ('...') - הופך backslash
    ל-forward slash ובורח (\\:) מהנקודתיים של path בסגנון Windows (C:\\...),
    כי ':' הוא גם מפריד-אופציות בתחביר ה-filtergraph של ffmpeg עצמו. אותה
    טכניקה בדיוק כמו utils/media/captions.py's escaped_srt - משמשת כאן לכל פילטר
    שמקבל נתיב קובץ כארגומנט (lut3d, vidstabdetect/transform)."""
    return path.replace("\\", "/").replace(":", "\\:")


# --- LUT (item: צבע ו-HDR - LUT אופציונלי) ---

def get_lut_filter(lut_path: str) -> str:
    """מחזיר את פילטר ה-ffmpeg להחלת LUT תלת-ממדי (.cube, הפורמט הנפוץ
    ב-Adobe/DaVinci) - lut3d תומך בו ישירות. בדיקת קיום/סיומת הקובץ עצמה
    היא באחריות הקורא (video_editor.py) - זו רק בניית מחרוזת הפילטר."""
    return f"lut3d=file='{_escape_ffmpeg_filter_path(lut_path)}'"


# --- Auto-levels (item: צבע ו-HDR) ---

# "Normalize RGB video" - מותח אוטומטית את טווח הבהירות של כל פריים למקסימום
# הניגודיות התקין (0-255), בלי צורך בקלט ידני - שימושי לחומר גולמי חשוך/שטוח
# ממכונת-משחק ישנה שלא מנצל את מלוא טווח הבהירות.
AUTO_LEVELS_FILTER = "normalize"


# --- אינטרפולציית פריימים חלקה (item: FPS ותנועה) ---

def build_fps_filter(output_fps: Union[int, str], smooth: bool = False) -> str:
    """בונה את ביטוי פילטר קביעת-הקצב הסופי. smooth=False (ברירת מחדל): fps=X
    הרגיל - שכפול/השמטת פריימים גסה כדי להגיע לקצב היעד. smooth=True (item:
    אינטרפולציית פריימים) - minterpolate עם הערכת תנועה אמיתית (mi_mode=mci,
    motion-compensated interpolation) במקום שכפול, מייצר פריימי-ביניים
    אמיתיים - משמעותי בעיקר כשמעלים קצב (למשל 30->60), איטי משמעותית
    מ-fps= הרגיל. לא נתמך עם use_hwaccel - הקורא אחראי לא להעביר smooth=True
    יחד עם use_hwaccel (אין מקבילת CUDA ל-minterpolate מוכחת בפרויקט הזה)."""
    if smooth:
        return f"minterpolate=fps={output_fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
    return f"fps={output_fps}"


# --- הסרת שקט באמצע הקובץ, מסונכרן וידאו+אודיו (item: אודיו) ---

def build_silence_removal_filters(silence_intervals: List[Tuple[float, float]]) -> Tuple[str, str]:
    """בונה זוג פילטרים (video, audio) שמסירים בדיוק אותם טווחי-זמן שקטים
    (item: הסרת שקט באמצע הקובץ) *משני הזרמים יחד* - זו הדרך הנכונה היחידה
    לעשות את זה: הפילטר הייעודי silenceremove פועל רק על ערוץ האודיו, בלי
    מקבילה בווידאו - היה מזיז את ציר הזמן של האודיו קדימה בלי לגעת בווידאו,
    ומשבש סנכרון שפתיים לצמיתות מהשקט הראשון שמוסר. select/aselect עם אותו
    ביטוי בוליאני בדיוק (between(t,start,end) לכל טווח, מאוחד ב-'+' כ-OR
    בהקשר בוליאני-מספרי) מבטיח ששני הזרמים מסננים בדיוק את אותם פריימים/
    סמפלים, ו-setpts=N/FRAME_RATE/TB / asetpts=N/SR/TB מתקנים את חותמות הזמן
    ברצף אחרי ההסרה (בלי זה היו נשארים "חורים" בציר הזמן). מוחזר ("", "")
    אם אין בכלל טווחים להסיר - הקורא מדלג על הוספת הפילטרים בכלל."""
    if not silence_intervals:
        return "", ""
    condition = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in silence_intervals)
    video_filter = f"select='not({condition})',setpts=N/FRAME_RATE/TB"
    audio_filter = f"aselect='not({condition})',asetpts=N/SR/TB"
    return video_filter, audio_filter


# --- שער רעש (item: אודיו) ---

# מנמיך אוטומטית כל מה שמתחת ל--35dB (רעש רקע/hiss קבוע) בלי לגעת בדיבור -
# ratio=5 (יחס דחיסה מתון מתחת לסף), attack/release קצרים (5/50 מ"ש) כדי
# שהשער יגיב מהר לתחילת/סיום דיבור בלי לחתוך את תחילת המילים.
NOISE_GATE_FILTER = "agate=threshold=-35dB:ratio=5:attack=5:release=50"


# --- כרומה קי (item: פילטרים ויזואליים) ---

def build_chromakey_filters(color: str, similarity: float, blend: float, bg_color: str, input_width: int, input_height: int) -> List[str]:
    """מחזיר רשימת שלבי filter_complex שהופכים color (למשל "0x00FF00", ירוק
    סטנדרטי) לשקוף ומרכיבים על רקע bg_color אחיד במקומו (item: כרומה קי /
    מסך ירוק). color= הוא source filter פנימי לגרף עצמו (לא -i חיצוני) בגודל
    input_width/height - זהה בדיוק למידות [0:v] כדי שה-overlay יתיישר פיקסל-
    לפיקסל בלי scale נוסף. overlay=shortest=1 קריטי: color= בלי duration
    מייצר סטרים אינסופי, בלי shortest=1 ffmpeg היה מחכה שהוא ייגמר - לנצח
    (נבדק בפועל - בלעדיו הריצה נתקעת). מחזיר שני שלבי filter_complex נפרדים
    (לא שרשרת-פסיקים אחת) כי composite עם מקור נוסף (color=) הוא ענף מקביל,
    לא שלב ליניארי יחיד - אותו עיקרון כמו blur_background."""
    return [
        f"chromakey=color={color}:similarity={similarity}:blend={blend}",
        f"color=c={bg_color}:s={input_width}x{input_height}",
    ]


# --- ייצוב וידאו, two-pass (item: פילטרים ויזואליים) ---

def get_vidstabdetect_filter(transforms_path: str, shakiness: int = 5, accuracy: int = 15) -> str:
    """מעבר 1/2 (item: ייצוב וידאו) - vidstabdetect מנתח את התזוזה בין
    פריימים וכותב אותה ל-transforms_path (לא מייצר פלט וידאו בעצמו, הקורא
    מפנה ל--f null -). shakiness (1-10, כמה רועד המקור) ו-accuracy (1-15,
    דיוק הניתוח מול זמן ריצה) - ברירות המחדל תואמות את ההמלצה הרשמית
    ל"רוב המקרים" בתיעוד libvidstab עצמו."""
    return f"vidstabdetect=shakiness={shakiness}:accuracy={accuracy}:result='{_escape_ffmpeg_filter_path(transforms_path)}'"


def get_vidstabtransform_filter(transforms_path: str, smoothing: int = 15) -> str:
    """מעבר 2/2 - מחיל את התיקון שנכתב ב-transforms_path (ע"י vidstabdetect,
    מעבר 1) בפועל על הפריימים. zoom=0 (לא מזמזם/מגדיל כדי לכסות את הרעידה
    המתוקנת - יכול להשאיר שוליים ריקים קלים בקצוות בתמורה לפחות איבוד תוכן;
    smoothing=15 (ברירת מחדל הספרייה) קובע כמה פריימים נלקחים בחשבון להחלקת
    התנועה)."""
    return f"vidstabtransform=input='{_escape_ffmpeg_filter_path(transforms_path)}':zoom=0:smoothing={smoothing}"
