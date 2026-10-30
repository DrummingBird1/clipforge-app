# utils/media/timelapse.py
#
# לוגיקה טהורה וניתנת-לבדיקה עבור my_scripts/video/timelapse_maker.py - חישוב
# מקדם המהירות, שרשור atempo (ל-audio מהיר במיוחד), ובניית ה-filter_complex.
# הקוד שבאמת מריץ ffmpeg נשאר בסקריפט עצמו (כמו בכל my_scripts/video/*.py אחר).

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".mov", ".avi", ".webm")

HORIZONTAL_SCALE_CHAIN = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
VERTICAL_SCALE_CHAIN = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"

# מקבילות CUDA (utils/video/video_editor.py's --hwaccel) - נבדקו ידנית מול GPU
# NVIDIA אמיתי, לא רק לפי תיעוד. scale_cuda/pad_cuda קיימים ותומכים באותם
# ארגומנטים בעיקרון כמו scale/pad הרגילים - אבל אין crop_cuda בכלל בבנייה
# הרגילה של ffmpeg, אז השרשרת האנכית עדיין צריכה סבב hwdownload/hwupload
# יחיד סביב ה-crop; האופקית (pad, לא crop) נשארת כולה על ה-GPU.
HORIZONTAL_SCALE_CHAIN_CUDA = "scale_cuda=w=1920:h=1080:force_original_aspect_ratio=decrease,pad_cuda=width=1920:height=1080:x=(ow-iw)/2:y=(oh-ih)/2"
VERTICAL_SCALE_CHAIN_CUDA = "scale_cuda=w=1080:h=1920:force_original_aspect_ratio=increase,hwdownload,format=nv12,crop=1080:1920,format=nv12,hwupload_cuda"


def compute_speed_factor(duration_seconds, target_seconds):
    """מחזיר פי-כמה להאיץ כדי לדחוס duration_seconds ל-target_seconds. None אם
    הסרטון כבר קצר מהיעד (אין מה להאיץ - setpts>1 היה מאט אותו, לא מהיר יותר)."""
    if target_seconds <= 0:
        raise ValueError("target_seconds חייב להיות חיובי")
    if duration_seconds <= target_seconds:
        return None
    return duration_seconds / target_seconds


def build_atempo_chain(speed_factor):
    """
    atempo תומך בטווח מוגבל (0.5-2.0 בגרסאות ffmpeg ישנות, עד 100 בחדשות) - כדי
    לתמוך במקדמי מהירות קיצוניים (מאות) בכל גרסה, משרשרים atempo=2.0 כמה פעמים
    שצריך ומשלימים את השארית במופע אחרון. מחזיר את מחרוזת הפילטר המשורשרת
    (בלי הסוגריים המרובעים של שם ה-pad - הקורא מוסיף אותם).
    """
    if speed_factor <= 0:
        raise ValueError("speed_factor חייב להיות חיובי")
    stages = []
    remaining = speed_factor
    while remaining > 2.0:
        stages.append("atempo=2.0")
        remaining /= 2.0
    # האטה (item: שינוי מהירות קבוע, 0.25x-4x) - אותו עיקרון בכיוון ההפוך: מתחת
    # ל-0.5 (המינימום של atempo בגרסאות ישנות) משרשרים atempo=0.5.
    while remaining < 0.5:
        stages.append("atempo=0.5")
        remaining /= 0.5
    stages.append(f"atempo={remaining:.6f}")
    return ",".join(stages)


def build_filter_complex(setpts_expr, video_scale_chain, output_fps, speed_factor, keep_audio):
    """
    בונה filter_complex יחיד (וידאו + אודיו אופציונלי) עם pad-ים בשם [outv]/[outa],
    ואת רשימת ה---map המתאימה. keep_audio=False (ברירת המחדל בסקריפט) לא מוסיף
    בכלל ענף אודיו - אודיו מואץ פי מאות הופך לרעש בלתי מובן ברוב המקרים.
    """
    parts = [f"[0:v]{setpts_expr},{video_scale_chain},fps={output_fps}[outv]"]
    maps = ["-map", "[outv]"]
    if keep_audio:
        atempo_chain = build_atempo_chain(speed_factor)
        parts.append(f"[0:a]{atempo_chain}[outa]")
        maps += ["-map", "[outa]"]
    return ";".join(parts), maps


def find_video_files(input_dir):
    import glob
    import os
    files = []
    for ext in VIDEO_EXTENSIONS:
        files.extend(glob.glob(os.path.join(input_dir, f"*{ext}")))
    return sorted(files)


def find_video_files_by_folder(input_dir):
    """
    עובר רקורסיבית על input_dir וכל תתי-התיקיות שלו ומחזיר [(folder_path, [video_paths...]), ...] -
    רשומה אחת לכל תיקייה שיש בה קובצי וידאו ישירות (קבצים של תת-תיקייה מקבלים רשומה
    נפרדת משלהם, לא נספרים גם בתיקיית האב). תיקיות בלי וידאו בכלל לא מופיעות ברשימה.
    משמש את video_editor.py כדי לעבד תיקיית-על שלמה עם תת-תיקיות (למשל תיקיה עם
    תת-תיקייה נפרדת לכל הקלטה) בלי שהמשתמש יצטרך להריץ את הסקריפט בנפרד על כל אחת.
    """
    import os
    groups = []
    for root, dirs, _files in os.walk(input_dir):
        dirs.sort()
        videos_here = find_video_files(root)
        if videos_here:
            groups.append((root, videos_here))
    groups.sort(key=lambda pair: pair[0])
    return groups
