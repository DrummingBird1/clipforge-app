# utils/media/wrapped_stats.py
#
# הלוגיקה הטהורה (בלי ffmpeg/subprocess) מאחורי ה"Wrapped" השנתי (item: annual
# "Wrapped" video) - my_scripts/video/wrapped_generator.py קורא לפונקציות
# האלה ואז בונה בפועל את כרטיסי הסטטיסטיקה ומרכיב את הסרטון. מופרד מהסקריפט
# עצמו כדי שכל חישוב הנתונים ייבדק במלואו בלי לגעת בכלל ב-ffmpeg/PIL.
#
# "שנה" כאן = שנה קלנדרית (1 בינואר - 31 בדצמבר), בכוונה שונה מ-"year" period
# ב-weekly_compilation.py (שם זה 365 יום מתגלגלים אחורה בזמן) - "Wrapped" הוא
# "השנה שלך ב-2026", לא "365 הימים האחרונים שלך", בדיוק כמו Spotify Wrapped.

import glob
import json
import os
import re
from datetime import datetime

TAG_CACHE_FILENAME_PATTERN = re.compile(r"^(?P<basename>.+)\.(?P<mtime>\d+)\.json$")


def gather_year_clips(source_dir, year):
    """כל קבצי ה-mp4 ב-source_dir שנוצרו (mtime) בתוך השנה הקלנדרית הנתונה,
    ממוין מהישן לחדש. מדלג על פלטי ריקאפ/Wrapped קודמים - זהה לסינון
    "_Recap_" הקיים כבר ב-weekly_compilation.py, כדי שווידאו Wrapped קודם לא
    ייכלל בטעות כ"קליפ" בתוך Wrapped חדש."""
    year_start = datetime(year, 1, 1).timestamp()
    year_end = datetime(year + 1, 1, 1).timestamp()
    clips = []
    for path in glob.glob(os.path.join(source_dir, "*.mp4")):
        basename = os.path.basename(path)
        if "_Recap_" in basename or basename.startswith("Wrapped_"):
            continue
        mtime = os.path.getmtime(path)
        if year_start <= mtime < year_end:
            clips.append(path)
    clips.sort(key=os.path.getmtime)
    return clips


def sample_highlight_clips(clips, max_clips):
    """דוגם עד max_clips קליפים, פרוסים באופן שווה על פני הרשימה (לא רק
    ה-max_clips הראשונים) - כדי שה"היילייטס" ייצג את כל השנה, לא רק את
    ההתחלה שלה. פחות מ-max_clips קליפים בסך הכל - מחזיר את כולם כמות שהם."""
    if len(clips) <= max_clips:
        return list(clips)
    step = len(clips) / max_clips
    return [clips[int(i * step)] for i in range(max_clips)]


def count_successful_jobs_and_hours_for_year(job_rows, year):
    """job_rows: [(script_name, status, started_at, duration_seconds, result_json), ...] -
    אותה צורה בדיוק כמו utils/job_history.get_jobs_since/get_recent_jobs.
    סופר ריצות *מוצלחות* בלבד שהתחילו בתוך השנה הקלנדרית. מחזיר
    (run_count, total_hours)."""
    prefix = f"{year}-"
    total_seconds = 0.0
    run_count = 0
    for _script_name, status, started_at, duration_seconds, _result_json in job_rows:
        if status != "success" or not started_at.startswith(prefix):
            continue
        run_count += 1
        total_seconds += duration_seconds or 0.0
    return run_count, total_seconds / 3600


def get_top_tags_for_year(cache_dir, year, limit=3):
    """[(tag, count), ...] מהנפוץ לפחות-נפוץ, על-פני קליפים שתויגו ו-*נלכדו*
    בשנה הנתונה (item: annual "Wrapped" video). שם קובץ המטמון עצמו מקודד את
    mtime הקליפ המקורי (ראו utils/media/clip_tagger.py's tags_cache_path -
    "<basename>.<mtime>.json"), כך שאפשר לסנן לפי שנה גם אם הקליפ המקורי כבר
    לא קיים בדיסק (אושר/פורסם/נמחק בינתיים) - קובץ המטמון עצמו מספיק."""
    if not os.path.isdir(cache_dir):
        return []
    year_start = datetime(year, 1, 1).timestamp()
    year_end = datetime(year + 1, 1, 1).timestamp()
    counts = {}
    for name in os.listdir(cache_dir):
        match = TAG_CACHE_FILENAME_PATTERN.match(name)
        if not match:
            continue
        mtime = int(match.group("mtime"))
        if not (year_start <= mtime < year_end):
            continue
        try:
            with open(os.path.join(cache_dir, name), "r", encoding="utf-8") as f:
                tags = json.load(f).get("tags", [])
        except (OSError, ValueError):
            continue
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
