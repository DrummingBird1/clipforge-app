# utils/media/shorts_naming.py
#
# 30.10.2026: הגדרות פרסום ה-Shorts ב-rocket_settings.json - שם הקובץ ("<title_prefix> #N"), המשחק שכותרות ה-AI מתארות
# (game_name; ריק = מזוהה משם הקליפ) ורזולוציית הפלט (output_resolution). מפתח שחסר בקובץ מקבל את NEW, ו-rocket_shorts_publisher
# כותב אותו לקובץ בהרצה הראשונה - כך ההגדרות גלויות בקובץ ונשמרות.
import re

NEW = {"title_prefix": "Shorts", "game_name": "", "output_resolution": "source"}
# "source" = הצלע הקצרה של המקור; אחרת גובה התמונה האופקית (1080 / 2160). הצלע הארוכה = 16:9
RESOLUTIONS = ("source", "1080", "2160")
_NOT_IN_FILENAME = re.compile(r'[\\/:*?"<>|]+')


def missing_naming(settings):
    """המפתחות של NEW שחסרים ב-settings, עם ברירת המחדל שלהם."""
    return {key: value for key, value in NEW.items() if key not in settings}


def clean_resolution(value):
    return value if value in RESOLUTIONS else NEW["output_resolution"]


def frame_sides(resolution, width, height):
    """(צלע ארוכה, צלע קצרה) של הפלט, זוגיות: 2160 -> (3840, 2160); "source" לפי הצלע הקצרה של המקור (width x height)."""
    short = int(resolution) if resolution in RESOLUTIONS[1:] else min(int(width), int(height))
    short = max(2, short - short % 2)
    long_side = short * 16 // 9
    return long_side - long_side % 2, short


def clean_prefix(value):
    """קידומת שאפשר לשים בשם קובץ ב-Windows. ריקה (או רק תווים אסורים) = ברירת המחדל החדשה."""
    return _NOT_IN_FILENAME.sub("", str(value or "")).strip() or NEW["title_prefix"]
