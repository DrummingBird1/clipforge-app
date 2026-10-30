# utils.video.video_editor_naming - split out of the original module (no behavior change); the original module re-exports every name.

from typing import Dict, Optional, Tuple, Union
from datetime import datetime
import os


# רזולוציית הפלט הקבועה לכל שילוב אנכי/אופקי - זהה בכוונה ל-utils/media/timelapse.py
# כדי ששני הסקריפטים יפיקו תוצרים תואמים לאותה פלטפורמה (טיקטוק/שורטס = אנכי,
# יוטיוב רגיל = אופקי).
OUTPUT_DIMENSIONS: Dict[bool, Tuple[int, int]] = {
    False: (1920, 1080),
    True: (1080, 1920),
}


WATERMARK_POSITIONS = ("top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right", "center")


# item: מיכל יצוא נוסף (--container) - mkv (Matroska) מקבל h264/hevc/av1+aac
# בלי שום סייג, בדיוק כמו mp4. webm הושאר בכוונה בחוץ - הפורמט מגביל את עצמו
# ל-vp8/vp9/av1 (וידאו) + vorbis/opus (אודיו) בלבד, כך ש-h264/hevc/aac
# (הקודקים בפועל ב-CODEC_ARGS) לא יפיקו קובץ webm תקין בכלל - לא "לא נתמך
# עדיין", אלא אי-התאמה מובנית בין הקודקים הקיימים לפורמט הזה.
SUPPORTED_CONTAINERS: Tuple[str, ...] = ("mp4", "mkv")


DEFAULT_CONTAINER = "mp4"


# item: תבנית שם-קובץ מותאמת אישית (--output-template) - placeholder-ים
# זמינים בלי לדרוש probe מוקדם של הקובץ (name/codec/orientation ידועים כבר
# מהארגומנטים, date משעון-הריצה) - {res} (רזולוציית פלט) נשאר בכוונה בחוץ:
# חישובו דורש resolve_effective_output_dimensions שתלוי ב-ffprobe, ולולא
# הבדיקה-החכמה-לדילוג (process_video) קוראת ל-resolve_output_filename *לפני*
# ה-probe בכלל - הוספת {res} הייתה מחייבת probe אפילו לקבצים שידלגו על רינדור.
# {number} (item: מספור סרטונים) - מונה מתמשך (utils/video/video_editor_counter.py),
# מוקצה ע"י הקורא (my_scripts/video/video_editor.py) לפני הקריאה הזו, לא כאן
# (הפונקציה הזו טהורה - בלי קריאה/כתיבה לקובץ המונה).
_OUTPUT_TEMPLATE_SAMPLE_VALUES: Dict[str, Union[str, int]] = {
    "name": "sample", "codec": "h264", "orientation": "horizontal", "date": "20260101", "number": 1,
}


def resolve_output_filename(
    base_name: str,
    vertical: bool,
    no_suffix: bool = False,
    container: str = DEFAULT_CONTAINER,
    template: Optional[str] = None,
    codec: Optional[str] = None,
    number: Optional[int] = None,
    orientation: Optional[str] = None,
) -> str:
    """שם קובץ הפלט (בלי תיקייה) - שלוש שכבות עדיפות: template (אם ניתן, גובר
    על no_suffix), אחרת no_suffix (בלי סיומת _edited_.../בדיוק base_name),
    אחרת ברירת המחדל הישנה (base_name_edited_horizontal/vertical). container
    (item: מיכל יצוא) קובע רק את סיומת הקובץ - ffmpeg בוחר muxer לפי הסיומת
    בעצמו, אין צורך בשום דגל נוסף. number (item: מספור סרטונים, --number-videos)
    זמין כ-{number} ב-template - ריק/None אם המונה לא רלוונטי לריצה הזו (לא
    משפיע על כלום אם ה-template בכלל לא מזכיר {number}). KeyError/IndexError
    על placeholder לא מוכר ב-template מתפשטת לקורא (נבדק פעם אחת מראש
    ב---output-template, ראו my_scripts/video/video_editor.py, לא בכל קובץ
    בנפרד)."""
    # orientation מפורש (גל 7, item 75: יחסי-רוחב - "square" ל-1:1) גובר על vertical.
    orientation = orientation or ("vertical" if vertical else "horizontal")
    if template:
        name = template.format(
            name=base_name, codec=codec or "", orientation=orientation,
            date=datetime.now().strftime("%Y%m%d"), number=number if number is not None else "",
        )
        return f"{name}.{container}"
    if no_suffix:
        return f"{base_name}.{container}"
    return f"{base_name}_edited_{orientation}.{container}"


def validate_output_template(template: str) -> None:
    """ValueError על placeholder לא מוכר ב-template (item: תבנית שם-קובץ) -
    נבדק פעם אחת מראש (fail-fast, זהה בעיקרון ל---fps), לא באמצע batch על
    הקובץ הראשון שנתקל בו."""
    try:
        template.format(**_OUTPUT_TEMPLATE_SAMPLE_VALUES)
    except (KeyError, IndexError) as e:
        raise ValueError(f"placeholder לא מוכר: {e}") from e


# תת-תיקייה קבועה (זהה בעיקרון ל-"_previous" הקיים, item: versioning) - שם
# מתחיל בקו-תחתי כדי שתמיד יופיע ראשון/יתבלט כ"תיקיית מטא-דאטה" ברשימת
# תיקיית הפלט, לא סתם עוד תוצר-וידאו.
SIG_SUBDIR = "_sig"


def resolve_sig_path(output_path: str) -> str:
    """נתיב קובץ ה-.sig.json (item: תיקיית SIG נפרדת) - תת-תיקיית SIG_SUBDIR
    לצד קובץ הפלט, לא ליד הפלט עצמו כמו קודם - כדי שתיקיית הסרטונים
    (workspace/vertical|horizontal/edited_videos) תישאר נקייה מקבצי סייד-קאר,
    רק וידאו (ותמונות ממוזערות). שם הקובץ בפועל נשאר <שם-קובץ-הפלט>.sig.json,
    רק תחת תת-התיקייה - כדי שלא יתנגש עם sig של קובץ אחר בעל שם דומה בתיקיית
    פלט אחרת (כל sig עדיין ייחודי לפי שם קובץ הפלט המלא שלו)."""
    output_dir = os.path.dirname(output_path)
    return os.path.join(output_dir, SIG_SUBDIR, os.path.basename(output_path) + ".sig.json")
