# utils/media/thumbnail_candidates.py
#
# מחלץ כמה תמונות ממוזערות "מועמדות" מקליפ (item: A/B thumbnail testing) -
# פריימים ב-20%/50%/80% מהאורך (אותו רעיון בדיוק כמו utils/media/clip_tagger.py's
# חילוץ 3 פריימים לתיוג AI, אבל כאן ברזולוציה המקורית - לא מוקטן - כי אלה
# מיועדות לשמש בפועל כתמונה ממוזערת אמיתית ב-YouTube, לא רק לניתוח AI פנימי).
#
# "A/B testing" כאן הוא במובן *רציף* (מחליפים תמונה ממוזערת, משווים ביצועים
# לפני/אחרי) - YouTube Data API הציבורי לא חושף בכלל את תכונת ה-"Test & Compare"
# הפנימית של YouTube Studio (פיצול תנועה בו-זמנית בין כמה תמונות) - אין דרך
# API לעשות את זה, אז לא מתיימרים לבנות את זה.

import os

from utils.media.thumbnail_generator import extract_frame_at_timestamp, get_video_duration_via_ffprobe

CANDIDATE_TIMESTAMP_FRACTIONS = (0.2, 0.5, 0.8)


def generate_candidates(video_path, out_dir, ffmpeg_exe, ffprobe_exe):
    """שולף עד len(CANDIDATE_TIMESTAMP_FRACTIONS) תמונות מועמדות ל-out_dir
    (candidate_0.jpg, candidate_1.jpg, ...). מחזיר רק את הנתיבים שחילוץ הפריים
    הצליח בהם בפועל - קליפ קצר במיוחד/פגום עשוי להניב פחות מהמלא."""
    duration = get_video_duration_via_ffprobe(video_path, ffprobe_exe)
    os.makedirs(out_dir, exist_ok=True)
    candidate_paths = []
    for i, fraction in enumerate(CANDIDATE_TIMESTAMP_FRACTIONS):
        out_path = os.path.join(out_dir, f"candidate_{i}.jpg")
        if extract_frame_at_timestamp(video_path, max(0.1, duration * fraction), out_path, ffmpeg_exe):
            candidate_paths.append(out_path)
    return candidate_paths
