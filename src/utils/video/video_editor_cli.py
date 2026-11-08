# utils/video/video_editor_cli.py
#
# The argparse definition of my_scripts/video/video_editor.py, moved out of the 2.7k-line script so the
# script stays focused on rendering. build_parser() returns exactly the parser the script used to build inline.

from utils.video.video_editor import ASPECT_PRESETS, CODEC_ARGS, DEFAULT_CONTAINER, DENOISE_LEVELS, EFFORT_LEVELS, FIT_MODES, RESOLUTION_SHORT_SIDE, SCALE_ALGORITHMS, SHARPEN_LEVELS, SUPPORTED_CONTAINERS, TONEMAP_ALGORITHMS, WATERMARK_POSITIONS
from utils.video.color_audio import AUDIO_DENOISE_LEVELS, COMPRESSOR_PRESETS, CURVES_PRESETS, EQ_HIGH_HZ, EQ_LOW_HZ
from utils.video.video_editor_layers import LAYER_POSITIONS
import argparse


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=str, default="")
    parser.add_argument("--watermark_path", type=str, default="", help="נתיב לתמונת watermark/לוגו - ריק (ברירת מחדל) = בלי watermark.")
    parser.add_argument("--watermark_position", type=str, default="bottom-right", choices=list(WATERMARK_POSITIONS))
    parser.add_argument("--watermark_scale", type=float, default=0.15, help="רוחב ה-watermark כאחוז מרוחב הפלט (ברירת מחדל: 0.15 = 15%%).")
    parser.add_argument(
        "--watermark_opacity", type=float, default=1.0,
        help="שקיפות ה-watermark (0.0-1.0, ברירת מחדל: 1.0 = אטום לגמרי) - זהה ל-rocket_shorts_publisher.py's "
             "watermark_opacity. מתעלם בשקט עם --hwaccel (nv12 אין לו ערוץ אלפא)."
    )
    parser.add_argument(
        "--watermark_x", type=float, default=None,
        help="item: גרירת watermark חופשית - מרכז ה-watermark כאחוז מרוחב הפלט (0.0-1.0), גובר על --watermark_position. "
             "צריך גם --watermark_y (שניהם, אחרת מתעלם ומשתמש ב---watermark_position כרגיל)."
    )
    parser.add_argument(
        "--watermark_y", type=float, default=None,
        help="כמו --watermark_x, מרכז ה-watermark כאחוז מגובה הפלט (0.0-1.0).",
    )
    parser.add_argument(
        "--remove_watermark_position", type=str, default="", choices=list(WATERMARK_POSITIONS),
        help="מוחק (מטשטש) watermark ישן באזור הפינה/מרכז הזה בקלט - ריק (ברירת מחדל) = בלי מחיקה. "
             "אפשר לשלב עם --watermark_path כדי להחליף watermark ישן בחדש (אותו מיקום או מיקום אחר)."
    )
    parser.add_argument("--remove_watermark_width_fraction", type=float, default=0.2, help="רוחב אזור המחיקה כאחוז מרוחב הקלט (ברירת מחדל: 0.2 = 20%%).")
    parser.add_argument("--remove_watermark_height_fraction", type=float, default=0.12, help="גובה אזור המחיקה כאחוז מגובה הקלט (ברירת מחדל: 0.12 = 12%%).")
    parser.add_argument(
        "--pip", type=str, default="", dest="pip_path",
        help="item: תמונה-בתוך-תמונה (PiP) - נתיב לקובץ וידאו שני שמוצב כשכבה קטנה מעל הווידאו הראשי "
             "(אותה מערכת מיקום/גודל כמו watermark, אבל וידאו במקום תמונה סטטית). ריק (ברירת מחדל) = בלי PiP. "
             "מתעלם בשקט עם --hwaccel (אין מקבילת CUDA מוכחת בפרויקט הזה, אותו דפוס כמו chromakey/blur-background)."
    )
    parser.add_argument("--pip-position", type=str, default="bottom-right", choices=list(WATERMARK_POSITIONS), help="מיקום ה-PiP - אותן אפשרויות כמו --watermark_position.")
    parser.add_argument("--pip-scale", type=float, default=0.3, help="רוחב ה-PiP כאחוז מרוחב הפלט (ברירת מחדל: 0.3 = 30%%).")
    parser.add_argument(
        "--pip-x", type=float, default=None,
        help="גל 10: גרירת PiP חופשית על התצוגה המקדימה - מרכז ה-PiP כשבר מרוחב הפלט (0.0-1.0), גובר על "
             "--pip-position. צריך גם --pip-y (שניהם, אחרת מתעלם) - אותו עיקרון כמו --watermark_x/--watermark_y."
    )
    parser.add_argument("--pip-y", type=float, default=None, help="כמו --pip-x, מרכז ה-PiP כשבר מגובה הפלט (0.0-1.0).")
    parser.add_argument("--pip-opacity", type=float, default=1.0, help="שקיפות ה-PiP (0.0-1.0, ברירת מחדל: 1.0 = אטום לגמרי).")
    parser.add_argument("--vertical", action="store_true", help="ממיר לפורמט אנכי 9:16 (טיקטוק/יוטיוב שורטס) במקום אופקי 16:9.")
    parser.add_argument(
        "--preserve-resolution", action="store_true",
        help="לא מקטין (או מגדיל) את רזולוציית הפלט לרזולוציה קבועה (1920x1080/1080x1920) - שומר על "
             "רזולוציית המקור. באופקי: רזולוציית הפלט זהה בדיוק לרזולוציית הקלט (בלי scale/pad כלל). "
             "באנכי: הקרופ ל-9:16 נשאר (זו כל המטרה של --vertical), אבל בגודל תואם-מקור במקום 1080x1920 "
             "קבועים, כדי שמקור ברזולוציה גבוהה מ-1080p לא יוקטן סתם."
    )
    parser.add_argument("--target-seconds", type=int, default=0, help="אם גדול מ-0: דוחס/מאיץ את הסרטון לאורך הזה בשניות (כמו timelapse_maker.py). 0 (ברירת מחדל) = משאיר את המהירות המקורית.")
    parser.add_argument(
        "--fps", type=str, default=None,
        help="קצב פריימים של הפלט - ריק (ברירת מחדל) שומר על קצב הפריימים המקורי של כל קובץ בנפרד "
             "(כולל קצבים לא-שלמים כמו 29.97/59.94), לפי מה שמזוהה ב-ffprobe. אפשר לדרוס עם מספר קבוע "
             "(למשל 30) או שבר מדויק (למשל 30000/1001) שיחול על כל הקבצים בריצה."
    )
    parser.add_argument("--keep-audio", action="store_true", help="שומר אודיו (מואץ אם יש timelapse) - כבוי כברירת מחדל.")
    parser.add_argument("--loudnorm", action="store_true", help="מנרמל את עוצמת השמע (זהה ל-rocket_shorts_publisher.py) - רלוונטי רק עם --keep-audio.")
    parser.add_argument("--codec", type=str, default="h264", choices=list(CODEC_ARGS.keys()), help="קידוד יצוא: h264 (CPU, תאימות מקסימלית), hevc או av1 (NVENC, דורש GPU של NVIDIA).")
    parser.add_argument(
        "--hwaccel", action="store_true",
        help="פענוח מואץ ב-GPU (NVIDIA CUDA/NVDEC) לפני הקידוד - מפחית עומס CPU משמעותית "
             "(delogo/scale/pad/overlay עוברים ל-GPU, delogo בלבד נשאר על CPU כי אין לו מקבילת CUDA). "
             "רלוונטי רק עם --codec hevc/av1 (NVENC) - מתעלם ממנו בשקט עם --codec h264. ל-h264 (CPU) "
             "ראו --hwaccel-decode למטה - מאיץ רק את הפענוח, לא כרוך ב-NVENC."
    )
    parser.add_argument(
        "--output-subdir", type=str, default="",
        help="גל 12 (יעדים): תת-תיקייה בתוך תיקיית הפלט (למשל shorts/tiktok) - כמה יעדים באותו כיוון לא דורסים זה את זה. "
             "רק אותיות/ספרות/_/- (עד 40 תווים).",
    )
    parser.add_argument(
        "--no-gpu-hybrid", action="store_true",
        help="גל 10: מכבה את הפייפליין ההיברידי - כשהסינון עובר ל-CPU (צבע/טקסט/שכבות/סיבוב), לא להקדים "
             "deinterlace/סיבוב/הקטנה על ה-GPU לפני ההורדה (להשוואה/עקיפת תקלה).",
    )
    parser.add_argument(
        "--hwaccel-decode", action="store_true",
        help="item: פענוח מואץ-GPU בלי לדרוש NVENC ביציאה - בניגוד ל---hwaccel (שדורש --codec hevc/av1, "
             "כי פענוח-CUDA וקידוד-NVENC כרוכים יחד שם), זה מפעיל רק פענוח מואץ (NVDEC) על הקלט - הפריימים "
             "חוזרים ל-CPU מיד אחרי הפענוח (hwdownload), וכל שאר השרשרת (scale/watermark/קידוד) ממשיכה "
             "בדיוק כמו בלי GPU בכלל, כולל עם --codec h264 (CPU). מקצץ את העלות הדומיננטית ברינדור ארוך "
             "(פענוח שעות של קלט 4K, למשל בטיימלאפס) בלי לוותר על תאימות h264. מתעלם בשקט אם --hwaccel "
             "כבר פעיל (זה כבר כולל פענוח מואץ כחלק מהצינור המלא) או על מקור HDR (נתיב ה-CUDA כאן תומך "
             "רק ב-8-bit, אותה סיבה בדיוק כמו --hwaccel)."
    )
    parser.add_argument(
        "--nvenc-preset", type=str, default=None, choices=["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
        help="דורס את ה-preset של NVENC (ברירת מחדל: p5) - רלוונטי רק עם --codec hevc/av1. "
             "p1=מהיר ביותר, p7=איכות מרבית/הכי איטי. משמעותי בעיקר יחד עם --hwaccel."
    )
    parser.add_argument(
        "--nvenc-cq", type=int, default=None,
        help="דורס את ה-CQ (איכות) של NVENC - רלוונטי רק עם --codec hevc/av1. "
             "נמוך יותר = איכות גבוהה יותר/קובץ גדול יותר (ברירת מחדל: 19 ל-hevc, 24 ל-av1)."
    )
    parser.add_argument(
        "--target-size-mb", type=float, default=None,
        help="עובר למצב קידוד VBR two-pass עם יעד גודל קובץ (מגה-בייט) במקום מצב CQ/CRF הרגיל - "
             "שימושי כדי להתאים קליפ למגבלת גודל (למשל העלאה לדיסקורד/טוויטר). מתעלם מהדגל --nvenc-cq אם שניהם ניתנו יחד."
    )
    parser.add_argument(
        "--parallel", type=int, default=1,
        help="מספר סרטונים לקודד בו-זמנית (ברירת מחדל: 1 = ברצף, כמו קודם). ערך גבוה יותר מקצר את זמן "
             "הריצה הכולל על תיקייה עם הרבה קבצים, במחיר עומס CPU/GPU גבוה יותר בבת אחת - ראו גם "
             "--effort. עם --codec hevc/av1, --max-concurrent-nvenc מגביל אוטומטית כמה קידודי NVENC "
             "בפועל רצים בו-זמנית (בלי קשר לכמה קבצים --parallel מריץ) כדי למנוע התנגשות במגבלת ה-GPU "
             "מראש; מנגנון ניסיון-חוזר קיים (NVENC session-limit) עדיין פעיל גם הוא כרשת ביטחון לכל "
             "מקרה שהמגבלה בפועל נמוכה יותר משזוהה."
    )
    parser.add_argument(
        "--max-concurrent-nvenc", type=int, default=None,
        help="מגבלת קידודי NVENC (hevc/av1) מקבילים בפועל, בלי קשר לכמה קבצים --parallel מריץ בו-זמנית "
             "- כדי שלא כל קבצי ה---parallel ינסו לפתוח סשן NVENC באותה שנייה בדיוק ויתנגשו במגבלת "
             "ה-GPU בפועל. ברירת המחדל (לא מוגדר): נבדק פעם אחת אוטומטית בתחילת הריצה "
             "(utils/media/nvenc_probe.py - מריץ כמה קידודי NVENC זעירים בו-זמנית באמת וסופר כמה הצליחו יחד, "
             "לא טבלת-חיפוש לפי דגם כרטיס) - רלוונטי רק עם --parallel מעל 1 ו---codec hevc/av1 (h264 לא "
             "משתמש ב-NVENC בכלל, ועם --parallel 1 אין ממילא יותר מקידוד NVENC אחד בו-זמנית מהריצה "
             "הזאת). מנגנון הניסיון-החוזר הקיים (ראו --parallel) נשאר פעיל גם כשהמגבלה הזו פעילה - לא "
             "כל התנגשות אפשר למנוע מראש, למשל תוכנה חיצונית שמקודדת NVENC בו-זמנית (כמו OBS)."
    )
    parser.add_argument(
        "--effort", type=str, default="high", choices=list(EFFORT_LEVELS),
        help="דרגת מאמץ/צריכת משאבי-מחשב לקידוד: high (ברירת מחדל, בלי הגבלה - כל הליבות/GPU רגיל), "
             "medium (מגביל threads לחצי מהליבות, NVENC preset מהיר יותר), low (2 threads בלבד, NVENC "
             "preset הכי מהיר) - שימושי כדי להשאיר את המחשב שמיש לדברים אחרים בזמן רינדור ברקע, "
             "או כשמריצים כמה קבצים בו-זמנית עם --parallel."
    )
    parser.add_argument(
        "--no-suffix", action="store_true",
        help="לא מוסיף סיומת (_edited_horizontal/_edited_vertical) לשם קובץ הפלט - משתמש בשם הקובץ "
             "המקורי בדיוק. כבוי כברירת מחדל (מוסיף את הסיומת, כדי להבדיל בקלות בין "
             "קובצי-מקור לקובצי-פלט אם הם אי-פעם מגיעים לאותה תיקייה). מתעלם אם --output-template ניתן."
    )
    parser.add_argument(
        "--output-template", type=str, default="",
        help="תבנית מותאמת אישית לשם קובץ הפלט (בלי סיומת-קובץ) - גוברת על --no-suffix/--number-videos. "
             "placeholder-ים זמינים: {name} (שם הקובץ המקורי), {codec}, {orientation} (horizontal/vertical), "
             "{date} (YYYYMMDD, שעון הריצה), {number} (item: מספור סרטונים - ריק אם --number-videos לא "
             "ניתן). למשל: \"{date}_{name}_{codec}\" או \"{number}_{name}\"."
    )
    parser.add_argument(
        "--number-videos", action="store_true",
        help="ממספר כל קובץ שנוצר ברצף (למשל \"Clip #N\", כמו המספור של rocket_shorts_publisher.py) "
             "במקום השם המקורי - שם הפלט הופך ל-\"<--number-prefix> #<N>\". המונה נשמר בין ריצות "
             "(data/video_editor_counter.txt, נפרד מהמונה של rocket_shorts_publisher.py) - ריצה הבאה "
             "ממשיכה מהמספר הבא, לא מתחילה מחדש. גובר על --no-suffix, אבל --output-template גובר עליו "
             "(אפשר לשלב עם {number} בתבנית מותאמת אישית). כש---parallel>1, או כשקובץ נכשל, המספר "
             "שהוקצה לו לא חוזר למחזור (פער בסדרה) - כדי שלעולם לא יוקצה אותו מספר פעמיים."
    )
    parser.add_argument(
        "--number-prefix", type=str, default="Clip",
        help="הטקסט שלפני המספר עם --number-videos (ברירת מחדל: \"Clip\", למשל \"Clip #7\"). מתעלם בלי "
             "--number-videos."
    )
    parser.add_argument(
        "--number-start", type=int, default=None,
        help="המספר הראשוני עם --number-videos - רלוונטי רק בפעם הראשונה שאין עדיין קובץ מונה שמור "
             "(ברירת מחדל: 1). אם קובץ המונה כבר קיים מריצה קודמת, הערך השמור בו גובר תמיד - זה בדיוק "
             "המשמעות של \"לזכור את המספור האחרון\"."
    )
    parser.add_argument(
        "--container", type=str, default=DEFAULT_CONTAINER, choices=list(SUPPORTED_CONTAINERS),
        help="מיכל (container) יצוא - mp4 (ברירת מחדל) או mkv. webm לא נתמך בכוונה: מגביל את עצמו "
             "ל-vp8/vp9/av1 (וידאו) + vorbis/opus (אודיו), לא תואם ל-h264/hevc/aac שמשמשים כאן."
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="בודק שכל קובץ אכן מקבל שרשרת-פילטרים/פקודת ffmpeg תקינה (רינדור אמיתי-אבל-קצר, 0.3 שניות "
             "בלבד, לפלט null) במקום רינדור מלא - כדי לתפוס שילוב דגלים לא-תקין (למשל LUT/נתיב פגום) "
             "לפני שמתחילים רינדור מלא של באצ' גדול שיכול לקחת שעות. מתעלם מ---force/דילוג-חכם - בודק "
             "כל קובץ בכל מקרה, בלי קשר לפלט קיים מריצה קודמת."
    )
    parser.add_argument(
        "--notify-per-file", action="store_true",
        help="שולח התראה (Windows Toast + Webhook לדיסקורד אם מוגדר ב-config.json) על כל קובץ שמסתיים "
             "(הצלחה/כשל) בנפרד, לא רק סיכום אחד בסוף כל הריצה - שימושי בבאצ' גדול/איטי."
    )
    parser.add_argument(
        "--export-report", type=str, default=None, choices=["csv", "xlsx", "both"],
        help="מייצא דוח סיכום ריצה (זמן ריצה, ספירת קבצים, ורשימת כל קובץ שנוצר - שם/קודק/רזולוציה/"
             "משך/גודל/זמן רינדור) לקובץ CSV ו/או Excel מעוצב בתת-תיקייה workspace/reports/ - כבוי "
             "כברירת מחדל. מתעלם עם --validate-only (אין קבצים שנוצרו בפועל לדווח עליהם)."
    )
    parser.add_argument("--thumbnail", action="store_true", help="יוצר גם תמונה ממוזערת (thumbnail) לכל תוצר, זהה ל-rocket_shorts_publisher.py.")
    parser.add_argument(
        "--only-files", type=str, default=None,
        help="item: תור-אצווה ניתן-לעריכה - מערך JSON של שמות-קבצים (לא נתיבים מלאים) לעבד, בסדר הזה "
             "בדיוק - חל רק על קבצים בתיקיית השורש (--input_dir) עצמה, לא על תתי-תיקיות (שממשיכות "
             "להתעבד במלואן כרגיל, ראו find_video_files_by_folder). שם שלא קיים בפועל בתיקייה מתעלם "
             "בשקט. ריק (ברירת מחדל) = כל הקבצים בתיקיית השורש, בסדר האלפביתי הרגיל."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="מרנדר מחדש גם אם כבר קיים פלט מריצה קודמת לאותו קובץ מקור בדיוק - "
             "כבוי כברירת מחדל: דילוג על 'smart re-encode skip' חוסך זמן/GPU בהרצות חוזרות על אותה תיקייה, "
             "בלי קשר לשינויים בהגדרות הריצה (רק תוכן קובץ המקור עצמו קובע את הדילוג, לא ה-flags של הריצה)."
    )
    parser.add_argument(
        "--preview-only", action="store_true",
        help="במקום לרנדר, מייצר תמונת contact-sheet אחת (פריים מייצג + שם קובץ לכל סרטון שנמצא) "
             "ומסתיים - כדי לוודא שנבחרה התיקייה הנכונה לפני רינדור batch שלם שיכול לקחת דקות/שעות."
    )
    parser.add_argument(
        "--smart-crop", action="store_true",
        help="בפורמט אנכי (--vertical) בלבד: בוחר את מיקום חלון הקרופ לפי ניתוח תזוזה בווידאו "
             "(utils/media/smart_crop.py) במקום קרופ קבוע במרכז, כדי לא לחתוך פעולה שקורית בצד. "
             "מתעלם בשקט בלי --vertical (אין crop כלל בפלט אופקי, רק pad), וגם עם --blur-background "
             "(שם הפלט לא נחתך כלל - אין חלון קרופ להזיז)."
    )
    parser.add_argument(
        "--smart-crop-face", action="store_true",
        help="עם --smart-crop: בוחר את חלון הקרופ לפי מיקום פנים שזוהו (cv2.FaceDetectorYN + מודל "
             "YuNet ב-assets/) במקום ניתוח-תזוזה כללי - עדיף לראיונות/טוקינג-הד. נופל בחזרה ל-0.0 "
             "(מרכז) אם לא זוהו פנים בכלל, בדיוק כמו כשל ניתוח-תזוזה. מתעלם בשקט בלי --smart-crop."
    )
    parser.add_argument(
        "--captions", action="store_true",
        help="שורף כתוביות אוטומטיות (תמלול faster-whisper, זהה ל-rocket_shorts_publisher.py) "
             "לתוך הפלט אחרי הרינדור - דורש --keep-audio (בלי זה אין בכלל אודיו בפלט לתמלל, "
             "מתעלם בשקט). כשל בתמלול/שריפה לא עוצר את שאר הפייפליין."
    )
    parser.add_argument(
        "--captions-translate", action="store_true",
        help="מתרגם את הכתוביות לאנגלית (task=\"translate\" המובנה של Whisper עצמו - "
             "רק לאנגלית, לא כל שפה) במקום לתמלל בשפת-המקור כמו שהיא. מתעלם בשקט בלי --captions."
    )
    parser.add_argument("--caption-font", type=str, default="Arial", help="שם הגופן לכתוביות (--captions). ברירת מחדל: Arial.")
    parser.add_argument("--caption-font-size", type=int, default=16, help="גודל הגופן לכתוביות (--captions). ברירת מחדל: 16.")
    parser.add_argument("--caption-color", type=str, default="#FFFFFF", help="צבע הכתוביות כ-hex (--captions). ברירת מחדל: #FFFFFF (לבן).")
    parser.add_argument("--caption-position", type=str, default="bottom", choices=["bottom", "top", "center"], help="מיקום הכתוביות (--captions). ברירת מחדל: bottom.")
    parser.add_argument("--caption-max-chars", type=int, default=0, help="מספר תווים מרבי בשורה של כתובית שנשרפת (--captions): ארוך מזה עובר לשורה חדשה ברווח האחרון לפני הגבול. 0 = בלי שבירה (ברירת מחדל).")
    parser.add_argument(
        "--blur-background", action="store_true",
        help="ממלא את כל הפריים ברקע מטושטש-ממורכז-מוגדל של אותו קלט, סביב התוכן המוקטן-שמור-יחס "
             "(לא נחתך) - במקום padding שחור פשוט (ברירת המחדל). עם --vertical: זו הדרך להכניס "
             "סרטון אופקי לתוך מסגרת אנכית (טיקטוק/שורטס) בלי לחתוך ממנו בצדדים, במקום הקרופ "
             "הרגיל. ללא --hwaccel בלבד - מתעלם בשקט עם --hwaccel (אין ל-gblur מקבילת CUDA "
             "מוכחת בפרויקט הזה)."
    )
    parser.add_argument(
        "--trim-start", type=float, default=0.0,
        help="חותך N שניות מתחילת כל קובץ לפני העריכה (ברירת מחדל: 0 = בלי חיתוך)."
    )
    parser.add_argument(
        "--trim-duration", type=float, default=None,
        help="לאחר --trim-start (אם ניתן), מגביל את האורך המעובד ל-N שניות בלבד "
             "(ברירת מחדל: ריק = עד סוף הקובץ)."
    )
    parser.add_argument(
        "--trim-silence", action="store_true",
        help="מזהה ומדלג אוטומטית על שקט בתחילת/סוף כל קובץ (ffmpeg silencedetect) - לא שקט "
             "באמצע. מתעלם משילוב עם --trim-start/--trim-duration (עדיפות לחיתוך המפורש)."
    )
    parser.add_argument("--denoise", action="store_true", help="מפחית רעש (hqdn3d) לפני שינוי הגודל - שימושי לחומר גולמי דחוס/מכונת-משחק ישנה. מתעלם בשקט עם --hwaccel.")
    parser.add_argument("--sharpen", action="store_true", help="מחדד (unsharp) את הפלט אחרי שינוי הגודל. מתעלם בשקט עם --hwaccel.")
    parser.add_argument(
        "--loudnorm-target", type=float, default=None,
        help="דורס את יעד ה-LUFS הקבוע של --loudnorm (ברירת מחדל: -14, זהה ל-rocket_shorts_publisher.py) - "
             "רלוונטי רק עם --keep-audio --loudnorm יחד."
    )
    parser.add_argument(
        "--lut", type=str, default="",
        help="נתיב לקובץ LUT תלת-ממדי (.cube, פורמט Adobe/DaVinci) לגריידינג צבע - מוחל אחרון בשרשרת "
             "(אחרי שינוי גודל/חידוד). ריק (ברירת מחדל) = בלי LUT."
    )
    parser.add_argument(
        "--auto-levels", action="store_true",
        help="מותח אוטומטית את טווח הבהירות של כל פריים (ffmpeg normalize) לפני שינוי גודל - "
             "שימושי לחומר גולמי חשוך/שטוח שלא מנצל את מלוא טווח הבהירות."
    )
    parser.add_argument(
        "--smooth-fps", action="store_true",
        help="אינטרפולציית תנועה אמיתית (minterpolate) במקום שכפול/השמטת פריימים גסה בקביעת קצב הפלט - "
             "משמעותי בעיקר כשמעלים קצב (למשל --fps 60 על מקור 30fps). איטי משמעותית מברירת המחדל. "
             "מתעלם בשקט עם --hwaccel."
    )
    parser.add_argument(
        "--noise-gate", action="store_true",
        help="שער רעש (agate) על האודיו - מנמיך אוטומטית רעש רקע קבוע (מאוורר/hiss) מתחת לסף, "
             "בלי לגעת בדיבור. רלוונטי רק עם --keep-audio."
    )
    parser.add_argument(
        "--remove-mid-silence", action="store_true",
        help="מזהה ומסיר שקט גם באמצע הקובץ (לא רק בקצוות כמו --trim-silence) - מסיר מהווידאו ומהאודיו "
             "יחד, בסנכרון מלא, כל טווח שקט שזוהה. דורש --keep-audio (אין אודיו לזהות ממנו שקט בלעדיו). "
             "מתעלם משילוב עם --trim-start/--trim-duration/--trim-silence (עדיפות לחיתוך המפורש)."
    )
    parser.add_argument(
        "--stabilize", action="store_true",
        help="ייצוב וידאו (vidstabdetect+vidstabtransform, שני מעברי ffmpeg) לחומר גולמי רועד - "
             "מאט משמעותית את הרינדור (מעבר ניתוח נוסף על הקובץ המלא). מתעלם בשקט עם --hwaccel."
    )
    parser.add_argument(
        "--chromakey", action="store_true",
        help="הופך את --chromakey-color (ברירת מחדל: ירוק) לשקוף ומרכיב על רקע צבע אחיד "
             "(--chromakey-bg-color) - מסך ירוק בסיסי לרקע אחיד, לא רקע-תמונה. מתעלם בשקט עם "
             "--hwaccel/--blur-background (שני אופנים סותרים לבניית הבסיס)."
    )
    parser.add_argument("--chromakey-color", type=str, default="0x00FF00", help="הצבע שהופך לשקוף עם --chromakey (ברירת מחדל: ירוק סטנדרטי).")
    parser.add_argument("--chromakey-similarity", type=float, default=0.2, help="רגישות זיהוי הצבע עם --chromakey (0.0-1.0, ברירת מחדל 0.2).")
    parser.add_argument("--chromakey-blend", type=float, default=0.05, help="החלקת קצוות עם --chromakey (0.0-1.0, ברירת מחדל 0.05).")
    parser.add_argument("--chromakey-bg-color", type=str, default="0x000000", help="צבע הרקע שמחליף את --chromakey-color עם --chromakey (ברירת מחדל: שחור).")
    parser.add_argument(
        "--fade-in-seconds", type=float, default=0.0,
        help="item: Fade-in/fade-out - כמה שניות עמעום-כניסה (מלגמרי-שחור, ובאודיו מלגמרי-שקט אם --keep-audio) "
             "בתחילת הפלט. 0 (ברירת מחדל) = בלי fade-in."
    )
    parser.add_argument(
        "--fade-out-seconds", type=float, default=0.0,
        help="item: Fade-in/fade-out - כמה שניות עמעום-יציאה בסוף הפלט (מחושב לפי האורך הסופי בפועל - "
             "אחרי חיתוך/טיימלאפס, לא אורך המקור). 0 (ברירת מחדל) = בלי fade-out."
    )
    parser.add_argument(
        "--text", type=str, default="", help="item: כיתוב טקסט קבוע - טקסט סטטי (כותרת/lower-third) שנשרף לתוך הפלט "
             "לכל אורך הסרטון (לא רק זמן מוגבל) - ריק (ברירת מחדל) = בלי טקסט. להבדיל מ---captions (כתוביות "
             "אוטומטיות מתומלל, משתנות לאורך הסרטון)."
    )
    parser.add_argument("--text-position", type=str, default="bottom", choices=["bottom", "top", "center"], help="מיקום הטקסט (--text). ברירת מחדל: bottom.")
    parser.add_argument("--text-font", type=str, default="Arial", help="שם הגופן לטקסט (--text). ברירת מחדל: Arial.")
    parser.add_argument("--text-font-size", type=int, default=24, help="גודל הגופן לטקסט (--text). ברירת מחדל: 24.")
    parser.add_argument("--text-color", type=str, default="#FFFFFF", help="צבע הטקסט כ-hex (--text). ברירת מחדל: #FFFFFF (לבן).")
    parser.add_argument(
        "--replace-audio", type=str, default="",
        help="item: החלפת פס קול חלופי - נתיב לקובץ אודיו/וידאו שפס-הקול שלו יחליף לגמרי את האודיו המקורי "
             "(המקורי מושתק, לא מעורבב) - ריק (ברירת מחדל) = בלי החלפה. גובר על --keep-audio (מפעיל אותו "
             "אוטומטית, אין טעם להחליף אודיו שממילא לא נשמר בפלט)."
    )
    parser.add_argument(
        "--remove-ranges", type=str, default=None,
        help="item: חיתוך כמה טווחים - מערך JSON של [start,end] בשניות להסרה מהקובץ (למשל [[10,15],[40,42]]), "
             "מסונכרן במלואו בין וידאו לאודיו (אותו מנגנון select/aselect בדיוק כמו --remove-mid-silence - "
             "משולב איתו אם שניהם ניתנים יחד). נדחה הדדית מול --trim-start/--trim-duration/--trim-silence, "
             "אותה סיבה בדיוק כמו --remove-mid-silence: אלה 'בחר תת-טווח רציף אחד', זה 'הסר כמה טווחים פזורים'."
    )
    parser.add_argument(
        "--batch-overrides", type=str, default=None,
        help="item: ממשק batch לדריסת דגלים פר-קובץ - נתיב לקובץ JSON ({\"filename.mp4\": {\"watermark_path\": "
             "\"...\", \"trim_start\": 5}, ...}) שדורס עבור קובץ ספציפי (לפי שם-קובץ מדויק, לא נתיב מלא) את "
             "watermark_path/watermark_position/watermark_opacity/watermark_scale/trim_start/trim_duration "
             "הגלובליים של הריצה הזו - שדה שלא מוזכר לקובץ ממשיך להשתמש בערך הגלובלי הרגיל. קובץ בלי entry "
             "ב-JSON משתמש בערכים הגלובליים במלואם, ללא שינוי."
    )
    parser.add_argument(
        "--concat-files", type=str, default=None,
        help="item: מעברים בין כמה קטעים - מערך JSON של שמות-קבצים (בתוך --input_dir) או נתיבים מלאים, "
             "בסדר הזה בדיוק, לאיחוד לתוצר אחד עם מעבר-חלק (--concat-transition) ביניהם. כשניתן, מפעיל "
             "מצב-ריצה נפרד לגמרי - מדלג על הסריקה/עיבוד הרגיל של --input_dir (כולל כל שאר ההגדרות - "
             "watermark/trim/LUT/וכו' - שלא רלוונטיות לפעולת-איחוד, רק לעריכת קובץ יחיד). כל הקטעים "
             "עוברים scale למידות-פלט משותפות (--vertical קובע אילו) לפני האיחוד."
    )
    parser.add_argument(
        "--concat-transition", type=str, default="fade", choices=["fade", "none"],
        help="סוג המעבר בין קטעים (--concat-files) - fade (ברירת מחדל, \"קרוספייד/דיסולב\") מעבר-חלק עם "
             "חפיפה של --concat-transition-duration שניות; none חיתוך קשה בלי מעבר (concat רגיל)."
    )
    parser.add_argument(
        "--concat-transition-duration", type=float, default=1.0,
        help="משך המעבר בשניות (--concat-transition fade). מתעלם עם --concat-transition none."
    )
    parser.add_argument(
        "--concat-output-name", type=str, default="concat_result",
        help="שם קובץ הפלט (בלי סיומת) לתוצר האיחוד (--concat-files). ברירת מחדל: concat_result."
    )
    parser.add_argument(
        "--preview-frame", type=float, default=None,
        help="item: תצוגה מקדימה מלאה (עורך-העל בווב) - במקום לרנדר, מייצא פריים PNG יחיד של הקובץ הראשון "
             "בנקודה הזו (שניות בציר-הזמן של *הפלט*) עם שרשרת הפילטרים המלאה בדיוק כמו ברינדור (קרופ/LUT/"
             "watermark/PiP/טקסט/fade), וכתובית-לדוגמה בעיצוב שנבחר אם --captions. רץ תמיד ב-CPU, בלי "
             "נעילת-רינדור, בלי מספור ובלי לגעת בפלט קיים. דורש --preview-frame-out."
    )
    parser.add_argument("--preview-frame-out", type=str, default="", help="נתיב ה-PNG של פריים התצוגה המקדימה (--preview-frame).")
    parser.add_argument(
        "--preview-frame-before-out", type=str, default="",
        help="אופציונלי עם --preview-frame: גם פריים המקור הגולמי באותה נקודה (מוקטן לאותן מידות, עם שוליים) - ל'לפני/אחרי'."
    )
    parser.add_argument(
        "--preview-clip-seconds", type=float, default=0.0,
        help="גל 10: עם --preview-frame - במקום פריים PNG, קטע וידאו קצר (1-10 שניות) מאותה נקודה עם שמע, "
             "באותה שרשרת פילטרים בדיוק (H.264 מהיר ב-CPU). --preview-frame-out הוא אז נתיב ה-MP4, "
             "ו---preview-frame-before-out (אם ניתן) מקבל קטע מקור מקביל באותן מידות, בלי שמע."
    )
    parser.add_argument(
        "--silence-threshold-db", type=float, default=-30.0,
        help="item: סף שקט (dB) לזיהוי שקט (--trim-silence/--remove-mid-silence) - גבוה יותר (למשל -20) מחשיב "
             "יותר רעש-רקע כ'שקט'. ברירת מחדל: -30."
    )
    parser.add_argument(
        "--silence-min-duration", type=float, default=0.3,
        help="אורך מינימלי (שניות) של קטע שקט כדי שייחשב (--trim-silence/--remove-mid-silence). ברירת מחדל: 0.3."
    )
    # --- גל 7 של 102-ההצעות (items 69-78, 83-84, 86, 88-89): עריכה ותוכן ---
    parser.add_argument("--aspect", type=str, default=None, choices=list(ASPECT_PRESETS) + ["custom"],
                        help="item: יחסי-רוחב - 16:9/9:16/1:1/4:5/4:3/custom (עם --custom-width/--custom-height). גובר על --vertical.")
    parser.add_argument("--custom-width", type=int, default=None, help="רוחב פלט עם --aspect custom.")
    parser.add_argument("--custom-height", type=int, default=None, help="גובה פלט עם --aspect custom.")
    parser.add_argument("--fit", type=str, default="auto", choices=list(FIT_MODES),
                        help="איך הפריים נכנס למסגרת: crop (ממלא, חותך עודפים), pad (כל הפריים עם שוליים), auto (crop לאנכי/ריבוע, pad לאופקי).")
    parser.add_argument("--dual-output", action="store_true", help="item: פלט כפול - כל קובץ מרונדר גם אופקי (16:9) וגם אנכי (9:16) באותה ריצה.")
    parser.add_argument("--watermark-position-vertical", type=str, default="", choices=[""] + list(WATERMARK_POSITIONS),
                        help="item: מיקום watermark שונה לפלט אנכי (למשל מרכז-תחתון בשורטס) - ריק = כמו --watermark_position.")
    parser.add_argument("--speed", type=float, default=1.0, help="item: שינוי מהירות קבוע (0.25-4) - וידאו ואודיו יחד. מתעלם עם --target-seconds.")
    parser.add_argument("--crf", type=int, default=None, help="item: איכות H.264 (CRF 0-51, נמוך=איכותי יותר; ברירת מחדל 20). ל-HEVC/AV1 ראו --nvenc-cq.")
    parser.add_argument("--resolution", type=str, default="auto", choices=["auto"] + list(RESOLUTION_SHORT_SIDE),
                        help="item: פריסט רזולוציה - הצלע הקצרה של הפלט (720p/1080p/1440p/2160p), יחס נשמר.")
    parser.add_argument("--scale-algo", type=str, default="bicubic", choices=list(SCALE_ALGORITHMS), help="item: אלגוריתם שינוי-גודל (lanczos = חד יותר).")
    parser.add_argument("--lut-intensity", type=float, default=1.0, help="item: עוצמת ה-LUT (0-1, ברירת מחדל 1 = מלא).")
    parser.add_argument("--eq-brightness", type=float, default=0.0, help="item: בהירות (-1..1, 0 = ללא שינוי).")
    parser.add_argument("--eq-contrast", type=float, default=1.0, help="ניגודיות (0-3, 1 = ללא שינוי).")
    parser.add_argument("--eq-saturation", type=float, default=1.0, help="רוויה (0-3, 1 = ללא שינוי).")
    parser.add_argument("--eq-gamma", type=float, default=1.0, help="גמא (0.1-10, 1 = ללא שינוי).")
    # גל 25: תיקון צבע ושמע מקצועיים (utils/video/color_audio.py)
    parser.add_argument("--grade-shadows", type=str, default="", help="גלגל הצללים (lift): היסט R,G,B בין -1 ל-1, למשל 0,0,0.05.")
    parser.add_argument("--grade-midtones", type=str, default="", help="גלגל הגוונים האמצעיים (gamma): היסט R,G,B.")
    parser.add_argument("--grade-highlights", type=str, default="", help="גלגל ההדגשות (gain): היסט R,G,B.")
    parser.add_argument("--curves-preset", type=str, default="none", choices=list(CURVES_PRESETS), help="עקומה מוכנה (curves preset).")
    parser.add_argument("--curves-master", type=str, default="", help="נקודות העקומה הראשית: 'x/y x/y ...' בין 0 ל-1.")
    parser.add_argument("--curves-red", type=str, default="", help="נקודות עקומת האדום.")
    parser.add_argument("--curves-green", type=str, default="", help="נקודות עקומת הירוק.")
    parser.add_argument("--curves-blue", type=str, default="", help="נקודות עקומת הכחול.")
    parser.add_argument("--audio-highpass", type=int, default=0, help="חיתוך נמוכים (Hz, 0 = כבוי) - מסיר זמזום ורעש רוח.")
    parser.add_argument("--audio-eq-low", type=float, default=0.0, help=f"EQ נמוכים ({EQ_LOW_HZ}Hz) בדציבלים, -20 עד 20.")
    parser.add_argument("--audio-eq-mid", type=float, default=0.0, help="EQ אמצע בדציבלים, -20 עד 20.")
    parser.add_argument("--audio-eq-mid-freq", type=int, default=1000, help="תדר ה-EQ האמצעי (200-5000Hz).")
    parser.add_argument("--audio-eq-high", type=float, default=0.0, help=f"EQ גבוהים ({EQ_HIGH_HZ}Hz) בדציבלים, -20 עד 20.")
    parser.add_argument("--audio-compressor", type=str, default="off", choices=["off", *COMPRESSOR_PRESETS], help="קומפרסור: gentle/voice/strong.")
    parser.add_argument("--audio-denoise", type=str, default="off", choices=["off", *AUDIO_DENOISE_LEVELS], help="הפחתת רעש בשמע (afftdn).")
    parser.add_argument("--audio-denoise-model", type=str, default="", help="מודל RNNoise (.rnnn) - עם --audio-denoise משתמש ב-arnndn במקום afftdn.")
    parser.add_argument("--denoise-level", type=str, default="medium", choices=list(DENOISE_LEVELS), help="item: עוצמת הפחתת-רעש (עם --denoise).")
    parser.add_argument("--sharpen-level", type=str, default="medium", choices=list(SHARPEN_LEVELS), help="item: עוצמת חידוד (עם --sharpen).")
    parser.add_argument("--tonemap", type=str, default="hable", choices=list(TONEMAP_ALGORITHMS), help="item: אלגוריתם tone-mapping ל-HDR->SDR.")
    parser.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270], help="item: סיבוב הפלט (מעלות, עם כיוון השעון).")
    parser.add_argument("--flip", type=str, default="none", choices=["none", "h", "v", "both"], help="item: מראה - h אופקי, v אנכי.")
    parser.add_argument("--deinterlace", action="store_true", help="item: deinterlace (bwdif) לחומר משודר/ישן עם פסים.")
    parser.add_argument("--pad-color", type=str, default="black", help="item: צבע השוליים (letterbox) - שם צבע או #RRGGBB.")
    parser.add_argument("--audio-track", type=int, default=None, help="item: אינדקס ערוץ-השמע (0 = הראשון) לקבצים עם כמה ערוצים (משחק+מיקרופון).")
    parser.add_argument("--caption-style", type=str, default="classic", choices=["classic", "bold", "outline", "box", "karaoke"],
                        help="item: סגנון כתוביות - classic/bold (טיקטוק)/outline/box (רקע)/karaoke (מילה-מילה).")
    parser.add_argument("--captions-language", type=str, default="", help="item: שפת התמלול (he/en/...) - ריק = זיהוי אוטומטי.")
    parser.add_argument("--captions-model", type=str, default="small", choices=["tiny", "base", "small", "medium", "large-v3"],
                        help="item: גודל מודל Whisper - גדול יותר = מדויק ואיטי יותר.")
    parser.add_argument("--captions-export", type=str, default="", choices=["", "srt", "vtt", "both"], help="item: שמירת קובץ כתוביות לצד הפלט.")
    parser.add_argument("--captions-no-burn", action="store_true", help="עם --captions-export: רק לייצא קובץ כתוביות, לא לשרוף אותן לווידאו.")
    parser.add_argument("--captions-srt-dir", type=str, default="",
                        help="item: עורך תמלול - תיקייה עם תמלולים ערוכים (<sha1 של נתיב המקור>.srt) שגוברים על תמלול אוטומטי.")
    # --- גל 7ב של 102-ההצעות: שכבות, קישוטים ועיבוד-אחרי ---
    parser.add_argument("--layers-json", type=str, default="",
                        help="item: קובץ JSON עם שכבות טקסט/תמונה/טיימר/חותמת-זמן, לכל אחת טווח-זמן, מיקום והנפשה (fade/typewriter/slide).")
    parser.add_argument("--timestamp-overlay", type=str, default="", choices=[""] + list(LAYER_POSITIONS),
                        help="item: חותמת-זמן אמיתית (תאריך+שעה של ההקלטה, לפי זמן-הקובץ) בפינה שנבחרה.")
    parser.add_argument("--progress-bar", action="store_true", help="item: סרגל התקדמות שרוף לאורך הסרטון (שורטס).")
    parser.add_argument("--progress-bar-color", type=str, default="#FF0000", help="צבע סרגל ההתקדמות (#RRGGBB).")
    parser.add_argument("--progress-bar-position", type=str, default="bottom", choices=["bottom", "top"], help="מיקום סרגל ההתקדמות.")
    parser.add_argument("--progress-bar-height", type=int, default=8, help="עובי סרגל ההתקדמות בפיקסלים.")
    parser.add_argument("--frame-thickness", type=int, default=0, help="item: מסגרת סביב הפריים (עובי בפיקסלים, 0 = בלי).")
    parser.add_argument("--frame-color", type=str, default="#FFFFFF", help="צבע המסגרת (#RRGGBB).")
    parser.add_argument("--frame-radius", type=int, default=0, help="עיגול הפינות הפנימיות של המסגרת בפיקסלים (0 = פינות ישרות; דורש --frame-thickness).")
    parser.add_argument("--vignette", type=str, default="none", choices=["none", "light", "medium", "strong"], help="item: וינייטה (החשכת שוליים).")
    parser.add_argument("--ken-burns", type=float, default=0.0, help="item: Ken Burns - זום-אין איטי לאורך הסרטון (0-0.5, למשל 0.1 = 10%%).")
    parser.add_argument("--watermark-move-seconds", type=float, default=0.0,
                        help="item: watermark נודד - עובר בין ארבע הפינות כל N שניות (0 = קבוע). מקשה על חיתוך הלוגו.")
    parser.add_argument("--pip-audio", action="store_true", help="item: מערבב את השמע של קובץ ה-PiP (למשל פרשנות) מעל הסאונד הראשי.")
    parser.add_argument("--pip-duck", action="store_true", help="עם --pip-audio: מנמיך את הסאונד הראשי בכל פעם שמדברים ב-PiP (ducking).")
    parser.add_argument("--intro-path", type=str, default="", help="item: קליפ intro שמודבק לפני כל פלט (מותאם למידות הפלט).")
    parser.add_argument("--outro-path", type=str, default="", help="item: קליפ outro שמודבק אחרי כל פלט.")
    parser.add_argument("--boomerang", action="store_true", help="item: boomerang - הפלט קדימה ואז אחורה (קליפים עד 60 שניות).")
    parser.add_argument("--loop-count", type=int, default=1, help="item: חזרה על הפלט N פעמים ברצף (1-10).")
    parser.add_argument("--meta-title", type=str, default="", help="item: כותרת במטא-דאטה של הקובץ.")
    parser.add_argument("--meta-comment", type=str, default="", help="item: הערה/תיאור במטא-דאטה של הקובץ.")
    parser.add_argument("--chapters", type=str, default="", help='item: פרקים - "0:00 פתיחה|1:30 קרב בוס" (או שורה לכל פרק).')
    parser.add_argument("--export-gif", type=str, default="", choices=["", "gif", "webp", "both"], help="item: ייצוא נוסף של הפלט כ-GIF/WebP מונפש.")
    parser.add_argument("--gif-width", type=int, default=480, help="רוחב ה-GIF/WebP בפיקסלים.")
    parser.add_argument("--gif-fps", type=int, default=12, help="קצב הפריימים של ה-GIF/WebP.")
    parser.add_argument("--export-audio", type=str, default="", choices=["", "mp3", "m4a", "wav"], help="item: ייצוא נוסף של השמע בלבד.")
    parser.add_argument("--control-file", type=str, default="",
                        help="item: קובץ-בקרה (JSON) שהווב כותב תוך ריצה - השהיה/ביטול של קובץ בודד ושינוי סדר הקבצים שעוד לא התחילו.")
    parser.add_argument(
        "--no-subfolders", action="store_true",
        help="item: מתג תתי-תיקיות (עורך-העל בווב) - מעבד רק את קבצי הווידאו שישירות ב---input_dir, בלי לרדת "
             "לתתי-תיקיות (ברירת המחדל, בלי הדגל: כל תת-תיקייה מעובדת גם היא לתיקיית-פלט מקבילה)."
    )
    parser.add_argument(
        "--remove-watermark-region", type=str, default="",
        help="item: בחירת אזור מחיקת-watermark בגרירת מלבן - \"x,y,w,h\" כשברים (0-1) של פריים המקור. גובר על "
             "--remove_watermark_position/fractions ומפעיל מחיקה גם בלעדיהם."
    )
    return parser
